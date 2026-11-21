"""Compare immutable RokStats captures for a named KvK fight."""

import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property, lru_cache

import roster as db


ARCHIVE = "kvk_fights.sqlite3"
METRICS = ("dkp", "t4", "t5")


def scan_stamp(day, clock):
    clock = clock.strip()
    if not clock:
        return day.isoformat()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?", clock):
        raise ValueError("Enter the KvK scan time as HH:MM or HH:MM:SS.")
    return f"{day.isoformat()}T{clock}" + (":00" if len(clock) == 5 else "")


def scan_label(stamp):
    day = datetime.fromisoformat(stamp)
    return day.strftime("%d %b %Y · %H:%M:%S" if "T" in stamp else "%d %b %Y · time unknown")


def precedes(before, after):
    if before[:10] != after[:10]:
        return before[:10] < after[:10]
    return len(before) > 10 and len(after) > 10 and before < after


def readings(row):
    values = {key: row.get(key) for key in METRICS}
    return {key: int(v) if isinstance(v, float) and v.is_integer() else v for key, v in values.items()}


@dataclass
class Scan:
    stamp: str
    values: dict

    @cached_property
    def payload(self):
        return json.dumps(self.values, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @cached_property
    def key(self):
        return self.stamp + "/" + hashlib.sha256(self.payload.encode()).hexdigest()

    def covers(self, daily):
        return self.stamp[:10] == daily.stamp and all(self.values.get(gid) == v for gid, v in daily.values.items())


def daily_scans(records, days=None):
    by_day = defaultdict(dict)
    for rec in records:
        for day, sample in rec.get("kvk_scans", {}).items():
            if sample is not None and (days is None or day in days):
                by_day[day][str(rec["id"])] = readings(sample)
    return [Scan(day, values) for day, values in by_day.items()]


@contextmanager
def database(directory, *, write=False):
    if write:
        directory.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(directory / ARCHIVE, timeout=15)) as conn, conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if write:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS scans (id TEXT PRIMARY KEY, stamp TEXT NOT NULL, data TEXT NOT NULL)")
            conn.execute("CREATE INDEX IF NOT EXISTS capture_time ON scans(stamp)")
            conn.execute("CREATE TABLE IF NOT EXISTS fights (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                         "before_id TEXT NOT NULL REFERENCES scans(id), after_id TEXT NOT NULL REFERENCES scans(id))")
            conn.commit()
            conn.execute("BEGIN IMMEDIATE")
        yield conn


def store_scan(conn, scan):
    return conn.execute("INSERT OR IGNORE INTO scans VALUES (?, ?, ?)",
                        (scan.key, scan.stamp, scan.payload)).rowcount


@lru_cache(maxsize=48)
def packaged_scan(path, modified, size):
    frame = db.prepare_file(path.name, path.read_bytes())
    day = db.detect_report_day(path.name, frame)
    if not day or db.guess_type(path.name, frame) != db.WAR:
        return None
    rows = db.report_data(path.name, frame, db.WAR)
    return Scan(scan_stamp(day, db.kvk_filename_time(path.name)), {str(r["id"]): readings(r) for r in rows})


def repository_scans(directory):
    paths = db.repository_reports(directory)
    folders = {p.parent for p in paths} | {directory}
    sources = [p for p in paths if re.search(r"kvk|players[ _-]?ranking", p.name, re.I)]
    for folder in folders:
        sources.extend((folder / "archive").glob("*_KvK.csv"))
    scans = []
    for path in sorted(sources):
        try:
            stat = path.stat()
            scan = packaged_scan(path, stat.st_mtime_ns, stat.st_size)
            if scan is not None and scan.stamp[:10] <= db.report_today().isoformat():
                scans.append(scan)
        except (ValueError, OSError, ImportError):
            # The daily roster still exposes usable legacy observations.
            continue
    return scans


def catalog(records, directory):
    scans = repository_scans(directory)
    saved = {}
    if (directory / ARCHIVE).is_file():
        with database(directory) as conn:
            scans.extend(Scan(stamp, json.loads(data)) for stamp, data in conn.execute("SELECT stamp, data FROM scans"))
            saved = {name: (before, after) for name, before, after in conn.execute(
                "SELECT name, before_id, after_id FROM fights ORDER BY name COLLATE NOCASE")}
    for daily in daily_scans(records):
        if not any(scan.covers(daily) for scan in scans):
            scans.append(daily)
    return {s.key: s for s in sorted(scans, key=lambda s: (s.stamp, s.key))}, saved


def save_fight(directory, name, before, after):
    name = name.strip()
    if not 1 <= len(name) <= 80:
        raise ValueError("Give the fight a name of up to 80 characters.")
    if not precedes(before.stamp, after.stamp):
        raise ValueError("Pick an earlier scan and a later scan. Same-day fights need both scan times.")
    with database(directory, write=True) as conn:
        existing = conn.execute("SELECT name, before_id, after_id FROM fights WHERE id=?", (name.casefold(),)).fetchone()
        if existing:
            if existing[1:] != (before.key, after.key):
                raise ValueError("That fight name is already used for another pair of scans. Choose a different name.")
            return existing[0]
        store_scan(conn, before)
        store_scan(conn, after)
        conn.execute("INSERT INTO fights VALUES (?, ?, ?, ?)", (name.casefold(), name, before.key, after.key))
    return name


def summary(records, before, after):
    if not precedes(before.stamp, after.stamp):
        raise ValueError("The starting scan must be earlier than the ending scan.")
    rows = []
    for rec in records:
        if not db.is_member(rec):
            continue
        gid = str(rec["id"])
        old, new = before.values.get(gid), after.values.get(gid)
        rows.append({"id": rec["id"], "name": rec["name"], "in_both": old is not None and new is not None,
                     **db.kvk_gains(old, new)})
    return rows


def import_reports(directory, batches, captures, full, rules, restore, auto):
    """Save all distinct fight scans, applying just the latest capture of each day to the daily roster."""
    if not captures:
        return db.change_records(lambda records: db.merge_dated_reports(records, batches, full, rules, restore, auto), directory)
    with database(directory, write=True) as conn:
        exports = []
        added = 0
        by_stamp = {}
        for stamp, digest, rows in captures:
            if datetime.fromisoformat(stamp).date() > db.report_today():
                raise ValueError("A KvK scan cannot be dated after today.")
            if stamp in by_stamp and digest != by_stamp[stamp][0]:
                raise ValueError("Two KvK exports have the same capture time. Check their times in Import options.")
            by_stamp[stamp] = (digest, rows)
        for stamp, (digest, rows) in sorted(by_stamp.items()):
            scan = Scan(stamp, {str(r["id"]): readings(r) for r in rows})
            added += store_scan(conn, scan)
            exports.append((scan, digest, rows))

        packaged = repository_scans(directory)

        def apply(records):
            daily_batches = {day: list(reports) for day, reports in batches.items()}
            tracked = {r["id"] for r in records}
            tracked.update(r["id"] for reports in batches.values() for _, _, rows in reports for r in rows)
            latest = max((r.get("source_dates", {}).get(db.WAR, "") for r in records), default="")
            days = {scan.stamp[:10] for scan, _, _ in exports}
            current_capture = max((r.get("kvk_capture", "") for r in records), default="")
            # Keep the old date-only snapshot when the first timestamped upload would overwrite it.
            for daily in daily_scans(records, days):
                archived = conn.execute("SELECT stamp, data FROM scans WHERE stamp BETWEEN ? AND ?",
                                        (daily.stamp, daily.stamp + "T23:59:59"))
                if (not any(scan.covers(daily) for scan in packaged)
                        and not any(Scan(stamp, json.loads(data)).covers(daily) for stamp, data in archived)):
                    store_scan(conn, daily)
            for scan, digest, rows in exports:
                if not any(r["id"] in tracked for r in rows):
                    raise ValueError("The KvK export contains no governors tracked by ODS1.")
                day = scan.stamp[:10]
                newest_stamp, = conn.execute("SELECT MAX(stamp) FROM scans WHERE stamp BETWEEN ? AND ?",
                                             (day, day + "T23:59:59")).fetchone()
                known = [s.stamp for s in packaged if s.stamp[:10] == day]
                if current_capture[:10] == day:
                    known.append(current_capture)
                if day >= latest and scan.stamp == max([newest_stamp, *known]):
                    live_rows = [dict(row, scan_time=scan.stamp[11:]) for row in rows]
                    daily_batches.setdefault(day, []).append((db.WAR, digest, live_rows))
            if not daily_batches:
                return db.ALREADY_IMPORTED
            try:
                return db.merge_dated_reports(records, daily_batches, full, rules, restore, auto)
            except db.OlderReports as exc:
                return str(exc)

        result = db.change_records(apply, directory)
    if not added:
        return result
    message = f"Saved {added} KvK fight scan{'s' if added != 1 else ''}."
    return message if result == db.ALREADY_IMPORTED else f"{message}  \n{result}"
