import tempfile
import unittest
from pathlib import Path

import membership
import roster


def scan(day, rows, count=None):
    total = len(rows) if count is None else count
    header = f"ODS1 Members,8843313,{day},{total}\nGovernor ID,Player,Alliance rank\n"
    return (header + "\n".join(rows)).encode()


class MembershipTests(unittest.TestCase):
    def test_activity_and_kingdom_imports_do_not_define_the_roster(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            week = directory / "ODS1-complete-weekly-2020-01-01_to_2020-01-02.csv"
            week.write_text("ID,Player,Forts destroyed\n1,One,10\n2,Two,20\n")
            war = directory / "Kingdom-4161-KvK-2020-01-02.csv"
            war.write_text("Governor ID,Governor Name,KD,DKP,Power\n1,One,4161,100,1000\n3,Three,4161,300,3000\n")
            roster.change_records(lambda records: None, directory)
            membership.save(scan("2020-01-02", ["1,One,R5", "3,Three,R3"]), directory)

            records, pending = roster.load_live(directory)
            self.assertFalse(pending)
            by_id = {r["id"]: r for r in records}
            self.assertEqual({i for i,r in by_id.items() if roster.is_member(r)}, {1, 3})
            self.assertEqual(by_id[2]["forts_7d"], 20)
            self.assertEqual(by_id[3]["kvk_dkp"], 300)
            self.assertNotIn("forts_7d", by_id[3])
            self.assertEqual(roster.classify(by_id[3])["action"], "Monitor / warn")

            later = [(roster.WEEK, "later", [{"id": 2, "name": "Two", "forts": 25}, {"id": 4, "name": "Four", "forts": 5}])]
            roster.change_records(lambda rs: roster.merge_reports(rs, later, "2020-01-03", complete=True), directory)
            records, _ = roster.load_live(directory)
            self.assertEqual({r["id"] for r in records if roster.is_member(r)}, {1, 3})
            self.assertEqual({r["id"] for r in records for h in r["history"]
                              if h["date"] == "2020-01-03" and h["in_active"]}, {2, 4})

    def test_only_complete_current_scans_can_replace_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            rows = ["1,One,R5", "2,Two,R1"]
            data = scan("2020-01-02", rows)
            membership.save(data, directory)
            membership.save(data, directory)
            for invalid in (scan("2020-01-02", rows[:1], 2), scan("2020-01-02", rows[:1] * 2),
                            scan("2020-01-01", rows), data.replace(b"8843313", b"1111111")):
                with self.assertRaises(ValueError):
                    membership.save(invalid, directory)
            _, saved = membership.latest(directory)
            self.assertEqual(set(saved), {1, 2})
            membership.save(scan("2020-01-02T05:00:00Z", ["1,One,R5", "3,Three,R4"]), directory)
            self.assertEqual(set(membership.latest(directory)[1]), {1, 3})


if __name__ == "__main__":
    unittest.main()
