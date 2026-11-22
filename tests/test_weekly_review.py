import copy
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import roster as db
from review_rules import promotion_war, support_score


def activity(gid=1, rank="R3", **extra):
    return {"id": gid, "name": f"Player {gid}", "rank": rank, "power": 10000000,
            "forts": 0, "tech": 0, "build": 0, "helps": 0, **extra}


def fighter(gid=1, **extra):
    return {"id": gid, "power": 10000000, "dkp": 0, "t4": 0, "t5": 0, "healed": 0, "acclaim": 0, **extra}


def import_week(records, day, member=None, *, war=True, auto=False):
    rows = [member or activity()]
    reports = [(db.WEEK, repr(rows), rows)]
    if war:
        reports.append((db.WAR, "scan", [fighter()]))
    db.merge_reports(records, reports, day, complete=True, auto=auto)
    return db.classify(records[0])


class WeeklyReviewTests(unittest.TestCase):
    def test_targets_scale_with_days_and_forts_are_optional(self):
        start = date(2020, 1, 6)
        for days in (1, 3, 7):
            end = date(2020, 1, 5 + days)
            for pace, expected in ((0, 0), (10, 10), (15, 15), (30, 15)):
                self.assertEqual(support_score({"forts_7d": pace * days}, start, end), expected)
            other = {"tech_7d": 100000 * days / 7, "build_7d": 90000 * days / 7, "helps_7d": 2500 * days / 7}
            self.assertEqual(support_score(other, start, end), 85)
            self.assertEqual(support_score({**other, "forts_7d": 15 * days}, start, end), 100)

    def test_streak_only_advances_on_distinct_consecutive_full_weeks(self):
        records = []
        first = import_week(records, "2020-01-05")
        self.assertEqual((first["action"], first["proposed"]), ("Monitor / warn", "R3"))
        for day in ("2020-01-08", "2020-01-10"):
            self.assertEqual(import_week(records, day)["action"], "Monitor / warn")
        second = import_week(records, "2020-01-12", auto=True)
        self.assertEqual((second["action"], second["proposed"]), ("Demote", "R2"))
        self.assertEqual(db.saved_rank(records[0]), "R3")
        self.assertEqual(import_week(records, "2020-01-12")["action"], "Demote")
        self.assertEqual(len([h for h in records[0]["history"] if h["date"] == "2020-01-12"]), 1)
        self.assertEqual(import_week(records, "2020-01-26")["action"], "Monitor / warn")

    def test_corrected_period_and_missing_evidence_break_the_streak(self):
        records = []
        import_week(records, "2020-01-05")
        self.assertEqual(import_week(records, "2020-01-12", war=False)["action"], "Keep current rank")
        self.assertEqual(import_week(records, "2020-01-12")["action"], "Demote")
        shortened = activity(week_start="2020-01-09")
        result = import_week(records, "2020-01-12", shortened)
        self.assertEqual(result["action"], "Keep current rank")
        saved = records[0]["history"]
        self.assertEqual(next(h for h in saved if h["date"] == "2020-01-12")["week_start"], "2020-01-09")
        self.assertEqual(import_week(records, "2020-01-19")["action"], "Monitor / warn")
        records[0]["has_weekly_activity"] = False
        self.assertEqual(db.classify(records[0])["proposed"], "R3")

    def test_sunday_morning_capture_is_still_a_partial_week(self):
        raw = b"ID,Player,Forts destroyed,Technology points,Alliance helps,Building time (seconds)\n1,One,0,0,0,0\n"
        rows = db.report_data("Alliance_activity_20200112_080000.csv", raw, db.WEEK)
        self.assertTrue(rows[0]["week_open"])
        records = []
        import_week(records, "2020-01-05")
        self.assertEqual(import_week(records, "2020-01-12", {**activity(), **rows[0]})["action"], "Keep current rank")

    def test_forts_alone_cannot_trigger_a_warning_or_demotion(self):
        records = []
        for day in ("2020-01-05", "2020-01-12"):
            # 40 actual support, or 55 (R3 specialist) when the fort allowance is included.
            result = import_week(records, day, activity(tech=100000, helps=500))
            self.assertEqual((result["support"], result["action"]), (40, "Keep current rank"))
        result = import_week(records, "2020-01-19", activity(rank="R2", tech=100000, build=90000, helps=2500))
        self.assertEqual((result["action"], result["proposed"]), ("Promote", "R3"))

    def test_promotion_uses_earned_support_and_advances_only_one_rank(self):
        fast_start = import_week([], "2020-01-06", activity(rank="R1", forts=15, tech=16000), war=False)
        self.assertGreater(fast_start["support"], 30)  # The activity display still shows the daily pace.
        self.assertEqual((fast_start["action"], fast_start["promotion_score"]), ("Keep current rank", 4.2))
        for rank, next_rank in (("R1", "R2"), ("R2", "R3")):
            with self.subTest(rank=rank):
                forts_only = import_week([], "2020-01-08", activity(rank=rank, forts=500))
                self.assertEqual((forts_only["action"], forts_only["proposed"]), ("Keep current rank", rank))
                earned = activity(rank=rank, tech=100000, build=90000, helps=2500)
                result = import_week([], "2020-01-06", earned, war=False)
                self.assertEqual((result["action"], result["proposed"]), ("Promote", next_rank))
                self.assertIn("KvK gains need two daily scans", result["reason"])

    def test_only_kvk_gains_inside_the_activity_period_earn_promotion_credit(self):
        records = []

        def report(day, dkp):
            member = activity(rank="R1")
            scan = fighter(dkp=dkp, healed=500000, acclaim=50000)
            db.merge_reports(records, [(db.WEEK, "activity", [member]), (db.WAR, str(dkp), [scan])], day, complete=True)
            return db.classify(records[0])

        report("2020-01-05", 0)
        single = report("2020-01-06", 2000000)
        self.assertEqual((single["war"], single["promotion_score"], single["action"]), (100, 0, "Keep current rank"))
        flat = report("2020-01-08", 2000000)
        self.assertIn("0 KvK from Jan 06–Jan 08 gains", flat["reason"])
        gain = report("2020-01-09", 3000000)
        self.assertEqual((gain["action"], gain["proposed"], gain["promotion_score"]), ("Promote", "R2", 33.8))
        corrected = report("2020-01-09", 2000000)
        self.assertEqual(corrected["action"], "Keep current rank")
        db.merge_reports(records, [(db.WAR, "next scan", [fighter(dkp=4000000)])], "2020-01-10")
        self.assertEqual(db.classify(records[0])["promotion_score"], 0)
        # A partial export for a different governor advances the global date, not this governor's activity.
        db.merge_reports(records, [(db.WEEK, "other member", [activity(gid=2)])], "2020-01-10")
        self.assertIsNone(db.classify(records[0])["promotion_score"])

    def test_closed_week_comparison_handles_sparse_scans_joins_and_counter_resets(self):
        start, end = date(2020, 1, 6), date(2020, 1, 12)
        scans = {"2020-01-05": {"dkp": 1000000}, "2020-01-12": {"dkp": 2000000}}
        rec = {"power": 10000000, "kvk_scans": scans}
        self.assertEqual(promotion_war(rec, start, end)[0], 75)
        self.assertEqual(promotion_war({**rec, "week_open": True}, start, end)[0], 0)
        self.assertEqual(promotion_war({**rec, "joined_date": "2020-01-06"}, start, end)[0], 0)
        scans["2020-01-08"] = {"dkp": 1750000}
        self.assertEqual(promotion_war(rec, start, end)[0], 75)  # Adding a midweek scan preserves measured gains.
        scans["2020-01-08"]["dkp"] = 100000  # Reset between the two endpoints.
        scans["2020-01-12"].update(healed=500000, acclaim=50000)
        self.assertIn("unavailable", promotion_war(rec, start, end)[1])
        scans["2020-01-05"]["healed"] = 0
        self.assertEqual(promotion_war(rec, start, end)[0], 15)

    def test_an_accepted_promotion_cannot_repeat_in_the_same_week(self):
        for path in ("auto", "officer", "reported"):
            with self.subTest(path=path):
                records = []
                member = activity(rank="R1", tech=100000, build=90000, helps=2500)
                result = import_week(records, "2020-01-06", member, auto=path == "auto")
                if path == "auto":
                    self.assertEqual((result["action"], db.saved_rank(records[0])), ("Keep current rank", "R2"))
                elif path == "officer":
                    db.save_officer(records, 1, "R2", "Reviewed", False, db.officer_values(records[0]), scanned_rank="R1")
                    self.assertEqual(db.classify(records[0])["action"], "Keep current rank")
                else:
                    self.assertEqual(result["action"], "Promote")
                member["rank"] = "R2"
                same_week = import_week(records, "2020-01-08", member)
                self.assertEqual((same_week["action"], same_week["proposed"]), ("Keep current rank", "R2"))
                new_week = import_week(records, "2020-01-13", member)
                self.assertEqual((new_week["action"], new_week["proposed"]), ("Promote", "R3"))

    def test_old_scan_uses_the_officers_corrected_export_even_if_a_packaged_file_has_the_same_dkp(self):
        day = "2020-01-08"
        records = []
        import_week(records, day, activity(rank="R1"), war=False)
        corrected = fighter(dkp=1000000, healed=2000, acclaim=None)
        db.merge_reports(records, [(db.WAR, "officer upload", [corrected])], day)
        saved = records[0]["kvk_scans"][day]
        for field in ("healed", "acclaim"):
            del saved[field]
        raw = b"ID,DKP,T4,T5,Power,Healed,Acclaim\n1,1000000,0,0,10000000,500000,50000\n"
        warnings = []
        db.backfill_war_scans(records, {day: ("kvk.csv", "packaged export", raw)}, warnings)
        self.assertFalse(warnings)
        self.assertEqual(saved["healed"], 2000)
        self.assertIsNone(saved["acclaim"])

    def test_officer_excuses_new_members_and_rank_changes(self):
        records = []
        import_week(records, "2020-01-05", activity(rank="R2"))
        self.assertEqual(import_week(records, "2020-01-12")["action"], "Monitor / warn")
        records[0]["is_excused"] = True
        self.assertEqual(import_week(records, "2020-01-19")["action"], "Keep current rank")
        records[0]["is_excused"] = False
        self.assertEqual(import_week(records, "2020-01-26")["action"], "Monitor / warn")
        records[0]["joined_date"] = "2020-01-23"
        self.assertEqual(db.classify(records[0])["action"], "Keep current rank")
        records[0]["officer_rank"] = "R4"
        self.assertEqual(db.classify(records[0])["proposed"], "R4")

    def test_kvk_tracks_same_day_replacements_missing_rows_and_genuine_zero(self):
        records = []
        db.merge_reports(records, [(db.WEEK, "week", [activity(i) for i in (1, 2, 3)])], "2020-01-03")
        def war(day, label, *rows):
            db.merge_reports(records, [(db.WAR, label, list(rows))], day)
            return db.kvk_comparison(records)
        previous, _, changes = war("2020-01-03", "A", fighter(dkp=10, t4=5), fighter(2))
        self.assertIsNone(previous)
        self.assertIsNone(changes[1]["dkp_change"])
        _, _, changes = war("2020-01-04", "B", fighter(dkp=13, t4=5, t5=None), fighter(3, dkp=100))
        self.assertEqual(changes[1], {"dkp_change": 3, "t4_change": 0, "t5_change": None})
        self.assertIsNone(changes[3]["dkp_change"])
        self.assertFalse(records[1]["in_kvk_4161"])
        self.assertNotIn("kvk_dkp", records[1])
        prior, latest, changes = war("2020-01-04", "corrected", fighter(dkp=9, t4=6, t5=2), fighter(3))
        self.assertEqual((prior, latest), ("2020-01-03", "2020-01-04"))
        self.assertEqual(changes[1], {"dkp_change": -1, "t4_change": 1, "t5_change": 2})
        state = copy.deepcopy(records)
        war("2020-01-04", "corrected", fighter(dkp=9, t4=6, t5=2), fighter(3))
        self.assertEqual(records, state)
        _, _, changes = war("2020-01-06", "C", fighter(2, dkp=60))
        self.assertIsNone(changes[2]["dkp_change"])

    def test_import_period_detection_and_officer_correction(self):
        data = b"Report period: 2020-01-08 to 2020-01-10\nID,Player,Forts destroyed\n1,One,45\n"
        rows = db.report_data("weekly.csv", data, db.WEEK)
        self.assertEqual(rows[0]["week_start"], "2020-01-08")
        records = []
        db.merge_reports(records, [(db.WEEK, "same-file", rows)], "2020-01-10")
        self.assertEqual(db.classify(records[0])["support"], 15)
        rows = db.report_data("weekly.csv", data, db.WEEK, end=date(2020, 1, 10), start=date(2020, 1, 6))
        db.merge_reports(records, [(db.WEEK, "same-file", rows)], "2020-01-10")
        self.assertEqual(db.classify(records[0])["support"], 9)

    @patch.object(db, "report_today", return_value=date(2026, 11, 22))
    def test_real_scans_match_current_members_and_upgrade_a_saved_baseline(self, _today):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for path in db.REPO_DATA_DIR.glob("*.csv"):
                if path.name.endswith(("2026-11-20.csv", "2026-11-21.csv", "2026-11-15.csv")):
                    shutil.copy(path, directory)
            (directory / "membership").mkdir()
            shutil.copy(db.REPO_DATA_DIR / "membership/2026-11-21.csv", directory / "membership")
            rows, pending = db.load_live(directory)
            self.assertFalse(pending)
            current = [r for r in rows if db.is_member(r)]
            self.assertEqual(len(current), 123)
            self.assertEqual(sum(r["has_weekly_activity"] is False for r in current), 4)
            prev, latest, changes = db.kvk_comparison(rows)
            self.assertEqual((prev, latest), ("2026-11-20", "2026-11-21"))
            self.assertEqual(changes[233190616], {"dkp_change": 636748, "t4_change": 127502, "t5_change": 12077})
            self.assertTrue(all(all(v is not None for v in changes[r["id"]].values()) for r in current))
            decisions = {r["id"]: db.classify(r) for r in current}
            self.assertTrue(any(result["action"] == "Promote" for result in decisions.values()))
            for r in rows:
                for sample in r.get("kvk_scans", {}).values():
                    if sample is not None:
                        sample.pop("healed", None)
                        sample.pop("acclaim", None)
            (directory / db.BASELINE).write_text(json.dumps(rows))
            upgraded, pending = db.load_live(directory)
            self.assertFalse(pending)
            self.assertEqual(decisions, {r["id"]: db.classify(r) for r in upgraded if db.is_member(r)})
            for r in rows:
                r.pop("kvk_scans", None)
                r.pop("week_start", None)
                for h in r["history"]:
                    h.pop("week_start", None)
            rows[0]["officer_note"] = "Keep this note"
            (directory / db.BASELINE).write_text(json.dumps(rows))
            restored, pending = db.load_live(directory)
            self.assertFalse(pending)
            self.assertEqual(db.kvk_comparison(restored), (prev, latest, changes))
            self.assertEqual(restored[0]["officer_note"], "Keep this note")
            self.assertEqual(next(r for r in restored if r["id"] == 233190616)["week_start"], "2026-11-16")


if __name__ == "__main__":
    unittest.main()
