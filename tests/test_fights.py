import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import fights
import roster as db


def war_row(gid, dkp, t4=0, t5=0):
    return {"id": gid, "dkp": dkp, "t4": t4, "t5": t5, "power": 10000000, "healed": 0, "acclaim": 0}


def capture(directory, *reports):
    return fights.import_reports(directory, {}, reports, False, db.DEFAULT_RULES, True, False)


class FightTests(unittest.TestCase):
    def test_two_readings_per_stat_and_current_members_only(self):
        members = [{"id": i, "name": str(i), "current_member": i != 4, "in_kvk_4161": False} for i in range(1, 6)]
        start = fights.Scan("2020-01-05T12:00:00", {str(i): fights.readings(war_row(i, 100, 10, None)) for i in (1, 2, 4)})
        end = fights.Scan("2020-01-05T18:00:00", {str(i): fights.readings(war_row(i, 95, 10, 3)) for i in (1, 3, 4)})
        rows = {r["id"]: r for r in fights.summary(members, start, end)}
        self.assertEqual(set(rows), {1, 2, 3, 5})
        self.assertTrue(rows[1]["in_both"])
        self.assertEqual((rows[1]["dkp_change"], rows[1]["t4_change"], rows[1]["t5_change"]), (-5, 0, None))
        for gid in (2, 3, 5):
            self.assertFalse(rows[gid]["in_both"])
            self.assertIsNone(rows[gid]["dkp_change"])
        for first, last in ((end, start), (start, start), (fights.Scan("2020-01-05", {}), end)):
            with self.assertRaises(ValueError):
                fights.summary(members, first, last)

    def test_export_clocks_and_unknown_dates(self):
        for name, clock in (("PlayersRanking_20261121_015612.xlsx", "01:56:12"),
                            ("2026-11-15_16-49-51_KvK.csv", "16:49:51"),
                            ("Kingdom-4161-KvK-2026-11-20.csv", "")):
            self.assertEqual(db.kvk_filename_time(name), clock)
        day = date(2020, 1, 5)
        self.assertEqual(fights.scan_stamp(day, " 16:34 "), "2020-01-05T16:34:00")
        self.assertEqual(fights.scan_stamp(day, ""), "2020-01-05")
        with self.assertRaises(ValueError):
            fights.scan_stamp(day, "25:77")
        self.assertFalse(fights.precedes("2020-01-05", "2020-01-05T23:00:00"))
        self.assertTrue(fights.precedes("2020-01-05T23:59:59", "2020-01-06"))

    def test_out_of_order_uploads_pin_the_fight_and_do_not_rewind_the_roster(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            baseline = [{"id": 1, "name": "One", "in_active_126": True, "history": [], "officer_note": "Keep this note"}]
            (directory / db.BASELINE).write_text(json.dumps(baseline))
            a = ("2020-01-05T08:00:00", "first", [war_row(1, 10), war_row(2, 5)])
            b = ("2020-01-05T19:00:00", "second", [war_row(1, 30, 9, 2), war_row(2, 10)])
            self.assertIn("Saved 2", capture(directory, b, a))
            records, pending = db.load_live(directory)
            self.assertFalse(pending)
            self.assertEqual(records[0]["kvk_dkp"], 30)
            self.assertEqual(records[0]["kvk_capture"], b[0])
            scans, _ = fights.catalog(records, directory)
            self.assertEqual([s.stamp for s in scans.values()], [a[0], b[0]])
            first, second = scans.values()
            self.assertEqual(fights.save_fight(directory, "Pass opening", first, second), "Pass opening")
            self.assertEqual(fights.save_fight(directory, "PASS OPENING", first, second), "Pass opening")
            self.assertEqual(capture(directory, a, b), db.ALREADY_IMPORTED)

            capture(directory, ("2020-01-06", "next-date", [war_row(1, 100)]))
            capture(directory, ("2020-01-05T12:00:00", "uploaded-late", [war_row(1, 12)]))
            capture(directory, ("2020-01-05T19:00:00", "revision", [war_row(1, 31, 9, 2)]))
            records, _ = db.load_live(directory)
            self.assertEqual(records[0]["kvk_dkp"], 100)
            self.assertEqual(records[0]["officer_note"], "Keep this note")
            scans, names = fights.catalog(records, directory)
            self.assertEqual(len(scans), 5)
            before, after = (scans[k] for k in names["Pass opening"])
            self.assertEqual(fights.summary(records, before, after)[0]["dkp_change"], 20)
            # A returning governor can be matched against the original kingdom rows.
            new_member = {"id": 2, "name": "New name", "current_member": True}
            self.assertEqual(fights.summary([new_member], before, after)[0]["dkp_change"], 5)
            with self.assertRaises(ValueError):
                fights.save_fight(directory, "Pass opening", before, list(scans.values())[-1])

    def test_invalid_batch_rolls_back_and_the_empty_archive_still_opens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = [{"id": 1, "name": "One", "in_active_126": True, "history": []}]
            (root / db.BASELINE).write_text(json.dumps(baseline))
            saved = (root / db.BASELINE).read_bytes()
            with self.assertRaises(ValueError):
                capture(root, ("2020-01-05T08:00:00", "valid", [war_row(1, 10)]),
                        ("2020-01-05T12:00:00", "no matching governors", [war_row(9, 1)]))
            self.assertEqual((root / db.BASELINE).read_bytes(), saved)
            self.assertEqual(fights.catalog(baseline, root), ({}, {}))
            with self.assertRaises(ValueError):
                capture(root, ("2020-01-05", "before", [war_row(1, 8)]), ("2020-01-05", "after", [war_row(1, 15)]))
            self.assertEqual(fights.catalog(baseline, root), ({}, {}))

    def test_two_packaged_exports_on_one_day_and_a_later_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / db.BASELINE).write_text(json.dumps([{"id": 1, "name": "One", "in_active_126": True, "history": []}]))
            def write(clock, amount):
                fn = root / f"PlayersRanking_20200105_{clock}.csv"
                fn.write_text(f"Governor ID,DKP,T4,T5,KD\n1,{amount},0,0,4161\n")
            write("080000", 10)
            write("190000", 35)
            db.change_records(lambda records: None, root)
            records, pending = db.load_live(root)
            self.assertFalse(pending)
            self.assertEqual(records[0]["kvk_dkp"], 35)
            catalog, _ = fights.catalog(records, root)
            self.assertEqual(len(catalog), 2)
            self.assertEqual(fights.summary(records, *catalog.values())[0]["dkp_change"], 25)
            write("210000", 45)
            records, pending = db.load_live(root)
            self.assertFalse(pending)
            self.assertEqual(records[0]["kvk_dkp"], 45)
            self.assertEqual(len(fights.catalog(records, root)[0]), 3)

    @patch.object(db, "report_today", return_value=date(2026, 11, 22))
    def test_published_scans_match_the_members_roster_and_full_interval(self, _today):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in ("membership/2026-11-21.csv", "ODS1-weekly-2026-11-09_to_2026-11-15.csv",
                         "ODS1-complete-weekly-2026-11-16_to_2026-11-21.csv", "archive/2026-11-15_16-49-51_KvK.csv",
                         "Kingdom-4161-KvK-2026-11-20.csv", "Kingdom-4161-KvK-2026-11-21.csv"):
                target = directory / name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(db.REPO_DATA_DIR / name, target)
            records, pending = db.load_live(directory)
            self.assertFalse(pending)
            scans, _ = fights.catalog(records, directory)
        by_day = {s.stamp[:10]: s for s in scans.values()}
        for day, expected in (("2026-11-20", (64359342, 14811078, 460740)),
                              ("2026-11-15", (289164994, 66182926, 2145342))):
            rows = fights.summary(records, by_day[day], by_day["2026-11-21"])
            self.assertEqual(len(rows), 123)
            self.assertTrue(all(r["in_both"] for r in rows))
            self.assertEqual(tuple(sum(r[f"{m}_change"] for r in rows) for m in fights.METRICS), expected)


if __name__ == "__main__":
    unittest.main()
