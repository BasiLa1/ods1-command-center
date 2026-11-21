"""Read and retain complete rosters from the ODS1 Members page."""

import csv
import io
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from filelock import FileLock


GUILD_ID = "8843313"
MEMBERS_URL = f"https://app.rokstats.online/guilds/overview/{GUILD_ID}"
LOCAL_ZONE = ZoneInfo("Asia/Tbilisi")
HEADER = ["Governor ID", "Player", "Alliance rank"]


def parse(data):
    try:
        rows = csv.reader(io.StringIO(data.decode("utf-8-sig")), strict=True)
        marker, guild, timestamp, size = next(rows)
        if marker != "ODS1 Members" or guild != GUILD_ID or next(rows) != HEADER:
            raise ValueError
        captured = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=LOCAL_ZONE)
        captured = captured.astimezone(LOCAL_ZONE)
        count = int(size)
        players = {}
        for cells in rows:
            if not cells:
                continue
            governor, name, rank = cells
            if not re.fullmatch(r"[1-9]\d{0,17}", governor) or not name.strip() or rank not in ("R1", "R2", "R3", "R4", "R5"):
                raise ValueError
            gid = int(governor)
            if gid in players:
                raise ValueError
            players[gid] = {"id": gid, "name": name.strip(), "rank": rank}
    except (UnicodeError, ValueError, csv.Error, StopIteration):
        raise ValueError("Use a complete ODS1 Members CSV from the roster scanner.") from None
    if count < 1 or count != len(players):
        raise ValueError(f"The guild page reported {count} members, but the scan contains {len(players)} unique governors. Scan again.")
    return captured, players


def latest(directory, packaged=None):
    files = {}
    for parent in (packaged, directory):
        if parent is not None:
            files.update({p.name: p for p in (parent / "membership").glob("*.csv")})
    if not files:
        return None, {}
    return parse(files[max(files)].read_bytes())


def save(data, directory, packaged=None):
    captured, players = parse(data)
    if captured.date() > datetime.now(LOCAL_ZONE).date():
        raise ValueError("The member scan is dated after today.")
    folder = directory / "membership"
    folder.mkdir(parents=True, exist_ok=True)
    with FileLock(str(folder / ".write.lock"), timeout=15):
        previous, saved = latest(directory, packaged)
        if previous and previous > captured:
            raise ValueError("A newer member scan is already in use.")
        if previous == captured:
            if saved != players:
                raise ValueError("Another roster is saved for that scan time. Run a fresh scan.")
            return f"Already using this roster of {len(players)} members."
        target = folder / f"{captured:%Y-%m-%dT%H-%M-%S-%f}.csv"
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as f:
            temp = Path(f.name)
        try:
            temp.write_bytes(data)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    return f"Saved {len(players)} current members from RokStats."
