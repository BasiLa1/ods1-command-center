"""ODS1 roster scoring, report imports and officer decisions."""

import copy
import csv
import hashlib
import io
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
from filelock import FileLock
from xlrd.biffh import XLRDError

import membership
from review_rules import PHASES, iso_day, low_week_streak, monday, n, overall_score, promotion_review, rank_band, support_score, war_score

REPO_DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR = Path(os.environ.get("ODS1_DATA_DIR") or REPO_DATA_DIR).expanduser()
# The confirmed 04:08 roster supersedes both published versions of the 03:14 report.
SUPERSEDED_WEEKLY_DIGESTS = {
    "f88635bba9e7169b859f1031aab9120aec62702960a569c71285adb3e1db3cea": (
        "356af0014b592690517b41af9a08332609bea94a7dfd0d4a97a3b69a0567f003",
        "c1c59d7b4a2fd6aed403397a452d744bea03abec4f0060eca8c556539685fd3b",
    ),
}
BASELINE = "ods1_baseline.json"
CLEAN_DATA_DIR = DATA_DIR / "clean-reports"
LEGACY_STATE = "ods1_persistent_state.json"
RANKS = ("R5", "R4", "R3", "R2", "R1")
ACTIONS = ("Keep current rank", "Promote", "Demote", "Monitor / warn", "Kick", "Review suggested rank")
DEFAULT_RULES = ("Early KvK", 45.0, 55.0)
COMMAND_AS_OF = "2026-11-20"
COMMAND = {
    233428447: ("R5", "Leader"),
    233185199: ("R4", "Officer"),
    233183034: ("R4", "Officer"),
    233183312: ("R4", "Officer"),
    233183356: ("R4", "Officer"),
    232674847: ("R4", "Officer"),
    233184517: ("R4", "Warlord"),
    233200204: ("R4", "Officer"),
    233196311: ("R4", "Officer"),
    233190616: ("R4", "Officer"),
    233184542: ("R4", "Envoy"),
}
# Ranks explicitly supplied by an officer in addition to the Nov 20 roster.
OFFICER_CORRECTIONS = {233185199: "R4", 233183034: "R4"}
WEEK, LIFETIME, WAR = "Weekly ODS1 roster", "All-time ODS1 activity", "Kingdom 4161 KvK"
BASE_LABEL = "Saved baseline"
ALREADY_IMPORTED = "These files are already reflected in this report."
ALL_TIME_LABEL = re.compile(r"all[\s_.-]*time|life[\s_.-]*time", re.I)
PERIOD_FIELDS = ("in_active_126", "rank", "last_active_rank", "restore_this_report", "return_rank", "first_seen_ods1",
                 "returned_date", "joined_date", "is_new_joiner", "forts_7d", "tech_7d", "helps_7d",
                 "rss_7d", "build_7d", "rok_use_7d", "rok_act_7d", "week_start", "week_open")
REPORT_TYPES = (WEEK, LIFETIME, WAR)
WEEK_METRICS = {
    "forts": "forts_7d", "tech": "tech_7d", "helps": "helps_7d", "build": "build_7d",
    "rss": "rss_7d", "usefulness": "rok_use_7d", "activity": "rok_act_7d",
}
ALL_METRICS = {
    "forts": "forts_all", "tech": "tech_all", "helps": "helps_all", "build": "build_all",
    "rss": "rss_all", "usefulness": "rok_use_all", "activity": "rok_act_all",
}
WAR_METRICS = {
    "dkp": "kvk_dkp", "kp": "kvk_kp", "t4": "kvk_t4", "t5": "kvk_t5",
    "dead": "kvk_dead", "dead t4": "kvk_dead_t4", "dead t5": "kvk_dead_t5",
    "healed": "kvk_healed", "acclaim": "kvk_acclaim", "trades": "kvk_trades",
    "power diff": "pwr_diff", "camp rank": "camp_rank", "kingdom rank": "kd_rank",
}
ALIASES = {
    "id": "id|governor id|governorid|player id|playerid", "name": "name|governor|governor name|player|player name",
    "forts": "forts|forts destroyed|barbarian forts|barbarian forts destroyed",
    "tech": "tech|tech donations|technology points|technology donations|technology donation points",
    "helps": "helps|alliance helps|alliance help",
    "build": "building time (seconds)|building time (s)|building time seconds|flag seconds",
    "rss": "resource assistance|rss assistance", "usefulness": "usefulness score|usefulness",
    "activity": "activity points|activity", "power": "power|governor power",
    "kp": "kp|kill points|killpoints", "dkp": "dkp|kvk dkp", "rank": "alliance rank|member rank",
    "camp rank": "#|camp rank", "kingdom rank": "kingdom rank|kd rank",
    "kingdom": "kingdom|kingdom id|kingdom number|kd", "alliance": "alliance|alliance tag",
    "joined": "joined date|join date|joined at|joined on|alliance join date",
    "last login": "last login|last login time",
    "report start": "report start|report start date|start date|period start|period start date|date from",
    "report end": "report end|report end date|end date|period end|period end date|date to|report date",
}
COLUMN_NAMES = {alias: target for target, variants in ALIASES.items() for alias in variants.split("|")}


def rank_code(value):
    text = str(value or "").strip().upper().replace(" (ROTATED)", "")
    return text if text in RANKS else None


def utc_day():
    return datetime.now(timezone.utc).date()


def report_today():
    return datetime.now(ZoneInfo("Asia/Tbilisi")).date()


def is_member(rec):
    return rec.get("current_member", rec.get("in_active_126", False))


def saved_rank(rec):
    if rec.get("roster_rank"):
        return rank_code(rec.get("officer_rank")) or OFFICER_CORRECTIONS.get(rec["id"]) or rec["roster_rank"]
    rank = rank_code(rec.get("officer_rank")) or rank_code(rec.get("rank"))
    if rec.get("in_active_126") and (rec.get("last_weekly_report") or "") >= COMMAND_AS_OF:
        if rec["id"] in COMMAND:
            return COMMAND[rec["id"]][0]
        if rec.get("last_weekly_report") == COMMAND_AS_OF and rank in ("R4", "R5"):
            return None
    return rank


def former_rank(rec):
    remembered = rank_code(rec.get("last_active_rank"))
    if remembered:
        return remembered
    for h in reversed(rec.get("history") or []):
        if h.get("in_active") and rank_code(h.get("rank")):
            return rank_code(h["rank"])
    if rec.get("in_active_126") or "(rotated)" in str(rec.get("rank", "")).lower():
        return saved_rank(rec)
    return None


def badge(rec, on_day):
    if not is_member(rec):
        return ""
    for field, label in (("returned_date", "Back on roster"), ("joined_date", "Joined")):
        observed = iso_day(rec.get(field))
        if observed and 0 <= (on_day - observed).days < 14:
            return f"{label} · {observed.strftime('%b')} {observed.day}"
    return ""


def classify(rec, rules=DEFAULT_RULES):
    active = bool(is_member(rec))
    end = iso_day(rec.get("last_weekly_report"))
    support = support_score(rec, iso_day(rec.get("week_start")), end) if active else n(rec.get("rok_use_all"))
    war = war_score(rec.get("power"), rec.get("kvk_dkp"), rec.get("kvk_healed"), rec.get("kvk_acclaim"))
    overall = overall_score(support, war, rules[0])
    held = saved_rank(rec)
    previous = rank_code(rec.get("return_rank")) if rec.get("restore_this_report") else None
    previous = previous or former_rank(rec)
    gid = int(rec["id"])
    command = COMMAND.get(gid)
    if rec.get("roster_rank") and command and command[0] != held:
        command = None
    promotion_score = None

    def decision(proposed, action, reason):
        return dict(support=support, war=war, overall=overall, proposed=proposed, action=action,
                    reason=reason, promotion_score=promotion_score)

    if not active:
        return decision(None, None, "Outside the current ODS1 roster")
    if command or held in ("R4", "R5"):
        proposed, reason = command or (held, "Officer rank")
        return decision(proposed, "Keep current rank" if held else "Review suggested rank", reason)
    if rec.get("is_excused"):
        return decision(held or previous, "Keep current rank" if held else "Monitor / warn", "Excused by an officer")
    if rec.get("has_weekly_activity") is False:
        return decision(held, "Monitor / warn", "Current member missing from the weekly export. Check report coverage.")
    if rec.get("restore_this_report") and previous:
        return decision(previous, "Keep current rank" if held == previous else "Review suggested rank",
                        f"Returned to ODS1 · last held {previous}")

    proposed, reason = rank_band(overall, support, war, rec.get("rok_use_all"), rules)
    if not held:
        if proposed == "Kick":
            return decision(None, "Monitor / warn", "Confirm the member’s current rank before reviewing activity.")
        return decision(proposed, "Review suggested rank", reason)
    if held in ("R1", "R2"):
        latest = rec.get("source_dates", {}).get(WEEK) or ""
        review_end = end if latest <= (rec.get("last_weekly_report") or "") else None
        target, promotion_score, evidence = promotion_review(rec, held, review_end, rules)
        if target != held:
            return decision(target, "Promote", evidence)
        if proposed in RANKS and RANKS.index(proposed) < RANKS.index(held):
            return decision(held, "Keep current rank", evidence)
    if proposed == held:
        return decision(held, "Keep current rank", reason)

    streak = low_week_streak(rec, held, rules, end, RANKS)
    if not streak:
        return decision(held, "Keep current rank", f"Hold {held}. No completed week qualifies for a low-activity check-in.")
    sunday = end - timedelta(days=(end.weekday() + 1) % 7)
    if streak == 1:
        return decision(held, "Monitor / warn", f"First low full week ending {sunday:%b %d}. Ask about barbarian or other KvK activity.")
    lower = "Kick" if held == "R1" else RANKS[RANKS.index(held) + 1]
    return decision(lower, "Kick" if lower == "Kick" else "Demote",
                    f"Two low full weeks ending {sunday - timedelta(days=7):%b %d} and {sunday:%b %d}. Officer review required.")


def snapshot(rec, rules, day):
    result = classify(rec, rules)
    return {
        "date": day, "name": rec["name"], "rank": saved_rank(rec),
        "last_active_rank": former_rank(rec), "in_active": bool(rec.get("in_active_126")),
        "in_kvk": bool(rec.get("in_kvk_4161")), "overall_score": result["overall"],
        "ods1_usefulness": result["support"], "kvk_score": result["war"], "target": result["proposed"],
        "action": result["action"], "power": rec.get("power"), "forts_7d": rec.get("forts_7d"),
        "tech_7d": rec.get("tech_7d"), "build_7d": rec.get("build_7d"), "helps_7d": rec.get("helps_7d"),
        "rss_7d": rec.get("rss_7d"), "rok_act_7d": rec.get("rok_act_7d"), "rok_use_7d": rec.get("rok_use_7d"),
        "kvk_dkp": rec.get("kvk_dkp"), "phase": rules[0], "week_start": rec.get("week_start"), "week_open": rec.get("week_open", False),
        "rok_use_all": rec.get("rok_use_all"), "is_excused": bool(rec.get("is_excused")),
    }


def baseline_entry(rec):
    # Missing legacy fields stay unknown. A saved score may have used different phase settings.
    fields = ("name", "power", "overall_score", "ods1_usefulness", "kvk_score", "forts_7d",
              "tech_7d", "build_7d", "helps_7d", "kvk_dkp", "last_active_rank")
    return {**{key: rec.get(key) for key in fields}, "date": BASE_LABEL,
            "in_active": bool(rec.get("in_active_126")), "in_kvk": bool(rec.get("in_kvk_4161")),
            "rank": saved_rank(rec)}


def read_records(directory=DATA_DIR):
    path = directory / BASELINE
    source_dir = directory
    if not path.exists() and directory == DATA_DIR and directory != REPO_DATA_DIR:
        source_dir = REPO_DATA_DIR
        path = source_dir / BASELINE
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=lambda value: None)
    if not isinstance(records, list):
        raise ValueError("The baseline must contain a list of governor records.")
    legacy_file = source_dir / LEGACY_STATE
    legacy = json.loads(legacy_file.read_text(encoding="utf-8-sig")) if legacy_file.exists() else {}
    excused = {str(gid) for gid in legacy.get("excused_ids", [])}
    seen = set()
    for rec in records:
        for field in ("current_member", "membership_date", "roster_rank", "has_weekly_activity"):
            rec.pop(field, None)
        gid = int(rec["id"])
        if gid in seen:
            raise ValueError(f"The baseline repeats Governor ID {gid}.")
        seen.add(gid)
        rec["id"] = gid
        latest_scan = rec.get("kvk_scans", {}).get(rec.get("source_dates", {}).get(WAR))
        if (latest_scan is not None and rec.get("in_kvk_4161")
                and all(latest_scan.get(k) == rec.get(WAR_METRICS[k]) for k in ("dkp", "t4", "t5"))):
            for field in ("healed", "acclaim"):
                if WAR_METRICS[field] in rec:
                    latest_scan.setdefault(field, rec[WAR_METRICS[field]])
        key = str(gid)
        rec.setdefault("officer_note", legacy.get("notes", {}).get(key, ""))
        rec.setdefault("is_excused", key in excused)
        if "officer_rank" not in rec and rank_code(legacy.get("custom_ranks", {}).get(key)):
            rec["officer_rank"] = rank_code(legacy["custom_ranks"][key])
        if not isinstance(rec.get("history"), list):
            rec["history"] = [baseline_entry(rec)]
        if "restore_this_report" not in rec and rec.get("returned_from_rotation"):
            rec["restore_this_report"] = bool(former_rank(rec))
    return records


def change_records(mutation, directory=DATA_DIR):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / BASELINE
    with FileLock(str(path) + ".lock", timeout=15):
        _, members = current_membership(directory)
        records, _ = load_report_records(directory, members)
        result = mutation(records)
        if result == ALREADY_IMPORTED and path.exists() and records == read_records(directory):
            return result
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as f:
            temporary = Path(f.name)
            try:
                json.dump(records, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return result


def latest_week(records):
    return max((r.get("last_weekly_report") for r in records if r.get("last_weekly_report")), default=None)


def normalized_heading(value):
    return " ".join(str(value).strip().lstrip("\ufeff").lower().replace("_", " ").split())


def has_id_header(cells):
    return any(COLUMN_NAMES.get(normalized_heading(cell)) == "id" for cell in cells)


def resolve_report_columns(frame, name):
    supported = set(COLUMN_NAMES.values()) | set(WAR_METRICS)
    headings = {normalized_heading(column) for column in frame}
    resolved = pd.DataFrame(index=frame.index)
    sources = {}
    for column in frame:
        heading = normalized_heading(column)
        # Pandas appends .1, .2, etc. to repeated headings.
        base = re.sub(r"\.\d+$", "", heading)
        if base in headings:
            heading = base
        field = COLUMN_NAMES.get(heading, heading)
        if field not in supported:
            continue
        values = frame[column]
        if field not in resolved:
            resolved[field] = values
            sources[field] = [str(column)]
            continue
        left = resolved[field].astype("string").str.strip()
        right = values.astype("string").str.strip()
        blanks = ["", "-", "–", "—"]
        left = left.mask(left.isin(blanks))
        right = right.mask(right.isin(blanks))
        conflicts = left.notna() & right.notna() & left.ne(right)
        sources[field].append(str(column))
        if conflicts.any():
            labels = ", ".join(sources[field])
            raise ValueError(f"{name} contains conflicting values for {field} in {labels}. Keep the intended column and upload again.")
        resolved[field] = resolved[field].where(left.notna(), values)
    return resolved


def prepare_file(name, data):
    header_error = f"{name} needs a Governor ID or ID column. Include the column headings when pasting."
    if name.lower().endswith((".csv", ".tsv", ".txt")):
        encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        try:
            lines = data.decode(encoding).splitlines(keepends=True)
        except UnicodeError:
            raise ValueError(f"Open {name} in Excel and save it as CSV UTF-8, or upload the Excel workbook.") from None
        for start, line in enumerate(lines[:40]):
            delimiter = next((sep for sep in (",", "\t", ";", "|")
                              if sep in line and has_id_header(next(csv.reader([line], delimiter=sep)))), None)
            if delimiter:
                break
        else:
            raise ValueError(header_error)
        metadata = [line.strip() for line in lines[:start]]
        try:
            df = pd.read_csv(io.StringIO("".join(lines[start:])), sep=delimiter, dtype=object)
        except pd.errors.ParserError as exc:
            raise ValueError(f"{name} contains a row with a different number of columns. Upload the original export.") from exc
    else:
        try:
            with pd.ExcelFile(io.BytesIO(data)) as book:
                for sheet in sorted(book.sheet_names, key=lambda s: s.strip().casefold() != "data"):
                    first = pd.read_excel(book, sheet_name=sheet, header=None, nrows=40, dtype=object)
                    start = next((i for i, cells in enumerate(first.itertuples(index=False, name=None))
                                  if has_id_header(cells)), None)
                    if start is not None:
                        metadata = [sheet, *(" ".join(str(c) for c in row if pd.notna(c))
                                             for row in first.iloc[:start].itertuples(index=False, name=None))]
                        df = pd.read_excel(book, sheet_name=sheet, header=start, dtype=object)
                        break
                else:
                    raise ValueError(header_error)
        except (BadZipFile, XLRDError, OSError) as exc:
            raise ValueError(f"Excel could not open {name}. Try the original workbook or export it as CSV.") from exc
    df = resolve_report_columns(df.dropna(how="all"), name).dropna(how="all")
    # Copied table pages can repeat their headings between groups of governors.
    repeated_headings = df["id"].map(lambda value: COLUMN_NAMES.get(normalized_heading(value)) == "id")
    df = df.loc[~repeated_headings].drop_duplicates()
    if df.empty:
        raise ValueError(f"{name} has column headings but no governor rows.")
    df.attrs["report_metadata"] = metadata
    return df


def long_activity_period(name, frame):
    for label in [name, *frame.attrs.get("report_metadata", [])]:
        dates = dates_in_label(label)
        if len(dates) >= 2 and (max(dates) - min(dates)).days >= 7:
            return True
    return False


def guess_type(name, frame):
    labels = " ".join([name, *frame.attrs.get("report_metadata", [])]).casefold()
    activity = set(frame) & set(WEEK_METRICS)
    if "dkp" in frame or ("kp" in frame and not activity):
        return WAR
    if activity and ALL_TIME_LABEL.search(labels):
        return LIFETIME
    if activity:
        return LIFETIME if long_activity_period(name, frame) else WEEK
    return None


def report_data(name, data, kind, *, end=None, start=None):
    frame = data if isinstance(data, pd.DataFrame) else prepare_file(name, data)
    if kind == WAR:
        if not {"dkp", "kp"} & set(frame):
            raise ValueError(f"{name} needs a DKP or KP column for a KvK import.")
        if "kingdom" in frame:
            match = frame["kingdom"].astype(str).str.contains(r"(?<!\d)4161(?!\d)", regex=True)
            frame = frame[match]
        elif len(frame) > 1500:
            raise ValueError(f"{name} needs a Kingdom column or a 4161-only export.")
    else:
        if not (set(frame) & set(ALL_METRICS | WEEK_METRICS)):
            raise ValueError(f"{name} needs alliance activity columns such as forts, helps or tech.")
        if "alliance" in frame:
            tags = frame["alliance"].astype(str).str.upper()
            frame = frame[tags.str.contains(r"(?<![A-Z0-9])ODS1(?![A-Z0-9])|^ODYSSEY\s*1$", regex=True)]
    if frame.empty:
        raise ValueError(f"{name} has no matching ODS1 or Kingdom 4161 rows.")
    ids = pd.to_numeric(frame["id"].astype("string").str.strip(), errors="coerce")
    invalid_ids = ids.isna() | (ids <= 0) | (ids >= 2**63) | (ids % 1 != 0)
    if invalid_ids.any():
        row = frame.loc[invalid_ids].iloc[0]
        raise ValueError(f"{name} needs a numeric Governor ID for {row.get('name') or 'a row'}. Check its ID cell.")
    if ids.duplicated().any():
        repeated = int(ids[ids.duplicated()].iloc[0])
        raise ValueError(f"{name} has two different rows for Governor ID {repeated}. Keep the correct row and try again.")
    frame = frame.copy()
    frame["id"] = ids.astype("int64")
    metrics = (WAR_METRICS if kind == WAR else ALL_METRICS | WEEK_METRICS)
    for col in set(frame) & (set(metrics) | {"power"}):
        raw = frame[col].astype("string").str.strip()
        raw = raw.mask(raw.isin(["", "—", "–", "-"]))
        number = raw.str.replace(r"\s", "", regex=True)
        # A decimal comma is common in semicolon-separated and pasted Excel tables.
        decimal_comma = number.str.fullmatch(r"(?i)[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{1,2}(?:[kmb%])?", na=False)
        number = number.where(~decimal_comma, number.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
        number = number.str.replace(",", "", regex=False)
        if col == "usefulness":
            number = number.str.removesuffix("%")
        suffix = number.str.extract(r"(?i)([kmb])$", expand=False).str.lower()
        scale = suffix.map({"k": 1e3, "m": 1e6, "b": 1e9}).fillna(1)
        values = pd.to_numeric(number.str.replace(r"(?i)[kmb]$", "", regex=True), errors="coerce") * scale
        invalid = raw.notna() & (values.isna() | values.isin([float("inf"), -float("inf")]))
        if invalid.any():
            index = invalid[invalid].index[0]
            raise ValueError(f"{name} has “{raw.loc[index]}” in {col} for Governor ID {frame.at[index, 'id']}. Check that cell.")
        if col not in ("power diff", "trades") and (values < 0).any():
            raise ValueError(f"{name} contains a negative value in {col}.")
        frame[col] = values
    if kind == WAR:
        frame["scan_time"] = kvk_filename_time(name)
    if kind == WEEK:
        end = end or detect_report_day(name, frame)
        if end:
            start = start or detect_week_start(name, frame, end)
            if not 0 <= (end - start).days < 7:
                raise ValueError(f"{name} needs a weekly period of one to seven days. Check the dates in Import options.")
            frame["week_start"] = start.isoformat()
            # An export captured on Sunday still has part of the last day ahead of it.
            stamp = re.search(r"(?<!\d)(20\d{6})[_-]\d{6}(?!\d)", name)
            captured = report_date_in_name(stamp[1]) if stamp else None
            frame["week_open"] = end.weekday() == 6 and (end == report_today() or captured == end)
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


def combine_report_files(kind, files):
    """Combine the two RokStats activity views after validating their shared rows."""
    if len(files) == 1:
        digest, (_, rows) = next(iter(files.items()))
        return digest, rows

    names = " and ".join(name for name, _ in files.values())
    mismatch = f"{names} share a date and report type. Check the periods in Import options or choose one export."
    if kind not in (WEEK, LIFETIME) or len(files) != 2:
        raise ValueError(mismatch)
    first, second = (rows for _, rows in files.values())
    basic, advanced = (first, second) if "usefulness" in first[0] else (second, first)
    if ("usefulness" not in basic[0] or "activity" in basic[0]
            or "activity" not in advanced[0] or "usefulness" in advanced[0]):
        raise ValueError(mismatch)

    advanced_by_id = {row["id"]: row for row in advanced}
    if {row["id"] for row in basic} != advanced_by_id.keys():
        raise ValueError(f"{names} cover different Governor IDs. Check the periods in Import options.")
    # The # column ranks usefulness in Basic and activity points in Advanced.
    shared = (basic[0].keys() & advanced[0].keys()) - {"camp rank"}
    shared_metrics = shared.intersection(WEEK_METRICS)
    matched_activity = False
    combined = []
    for row in basic:
        other = advanced_by_id[row["id"]]
        for field in shared:
            left, right = row[field], other[field]
            if left is None or right is None:
                continue
            if left != right and str(left).strip() != str(right).strip():
                raise ValueError(f"{names} disagree on {field} for Governor ID {row['id']}. Check the periods in Import options.")
            if field in shared_metrics:
                matched_activity = True
        merged = {**row, **{field: value for field, value in other.items() if value is not None}}
        merged.pop("camp rank", None)
        combined.append(merged)
    if not matched_activity:
        raise ValueError(mismatch)
    digest = hashlib.sha256("|".join(sorted(files)).encode()).hexdigest()
    return digest, combined


def apply_identity(rec, row, *, keep_current_name=False):
    if not row.get("name"):
        return
    new_name = str(row["name"]).strip()
    if new_name and new_name != rec.get("name"):
        aliases = set(rec.get("aliases") or [])
        current = rec.get("name")
        known_name = bool(current and current != f"Governor {rec['id']}")
        if keep_current_name and known_name:
            aliases.add(new_name)
        else:
            if known_name:
                aliases.add(current)
            rec["name"] = new_name
        aliases.discard(rec["name"])
        rec["aliases"] = sorted(aliases)


def bucket_status(rec):
    if is_member(rec):
        return "Active in ODS1"
    if "current_member" in rec:
        return "Outside the current ODS1 roster"
    return "Rotated Out (In KD 4161)" if rec.get("in_kvk_4161") else "Departed / Inactive"


def war_sample(row, power):
    sample = {key: row.get(key) for key in ("dkp", "t4", "t5", "healed", "acclaim")}
    if n(power) > 0 and all(row.get(key) is not None for key in ("dkp", "healed", "acclaim")):
        sample["score"] = war_score(power, row["dkp"], row["healed"], row["acclaim"])
    return sample


def apply_war_metrics(rec, row, position, day):
    for source, dest in WAR_METRICS.items():
        if row.get(source) is not None:
            rec[dest] = row[source]
    rec["in_kvk_4161"] = True
    rec["kd_rank"] = row.get("kingdom rank") or position
    power = row["power"] if row.get("power") is not None else rec.get("power")
    rec.setdefault("kvk_scans", {})[day] = war_sample(row, power)


def kvk_gains(before, after):
    before, after = before or {}, after or {}
    return {f"{key}_change": after[key] - before[key] if before.get(key) is not None and after.get(key) is not None else None
            for key in ("dkp", "t4", "t5")}


def kvk_comparison(records):
    """Use the same two distinct dates for everyone. Incomplete comparisons stay blank."""
    days = sorted({day for r in records for day in r.get("kvk_scans", {})}
                  | {r["source_dates"][WAR] for r in records if r.get("source_dates", {}).get(WAR)})
    latest = days[-1] if days else None
    previous = days[-2] if len(days) >= 2 else None
    changes = {}
    for rec in records:
        scans = rec.get("kvk_scans", {})
        changes[rec["id"]] = kvk_gains(scans.get(previous), scans.get(latest))
    return previous, latest, changes


def imported_event(rec, report_day, kind):
    events = rec.setdefault("membership_events", [])
    if not any(e.get("date") == report_day and e.get("type") == kind for e in events):
        events.append({"date": report_day, "type": kind, "rank": former_rank(rec)})


def merge_reports(records, reports, report_day, complete=False, rules=DEFAULT_RULES, restore=True, auto=False):
    """Apply validated files as a batch. The caller owns the transaction."""
    by_id = {r["id"]: r for r in records}
    day = date.fromisoformat(report_day)
    if day > report_today():
        raise ValueError("Choose a report date on or before today (Georgia time).")
    if len({kind for kind, _, _ in reports}) != len(reports):
        raise ValueError("Choose one file per report type in each import.")
    if not reports:
        raise ValueError("Choose a report first.")
    source_days = {kind: max((r.get("source_dates", {}).get(kind, "") for r in records), default="")
                   for kind, _, _ in reports}
    if any(report_day < latest for latest in source_days.values()):
        raise ValueError("This export predates the saved report for its type. Use its archived view instead.")
    reports = sorted(reports, key=lambda item: (LIFETIME, WEEK, WAR).index(item[0]))
    available = {}
    for rec in records:
        available.update(rec.get("source_fingerprints") or {})
    week_start = monday(day).isoformat()
    week_open = day.weekday() == 6 and day == report_today()
    report_digests = {}
    for kind, digest, rows in reports:
        fingerprint = (report_day, digest, complete if kind == WEEK else None)
        if kind == WEEK and rows:
            starts = {row.get("week_start") or week_start for row in rows}
            if len(starts) != 1:
                raise ValueError("Weekly rows must cover the same report period.")
            week_start = starts.pop()
            start = iso_day(week_start)
            if not start or not 0 <= (day - start).days < 7:
                raise ValueError("The weekly report must cover one to seven days ending on its report date.")
            week_open = week_open or any(row.get("week_open") for row in rows)
            if start != monday(day):
                fingerprint += (week_start,)
            if week_open:
                fingerprint += ("in progress",)
        report_digests[kind] = hashlib.sha256(repr(fingerprint).encode()).hexdigest()
    changed = sorted(
        (item for item in reports if available.get(item[0]) != report_digests[item[0]]),
        key=lambda item: REPORT_TYPES.index(item[0]),
    )
    if not changed:
        return ALREADY_IMPORTED
    was_active = {r["id"] for r in records if r.get("in_active_126")}
    joined, returned, departed = set(), set(), set()
    touched = set()
    weekly_rows = None
    for kind, _, rows in changed:
        if kind == WEEK:
            weekly_rows = {int(row["id"]) for row in rows}
            for rec in records:
                if not complete and rec["id"] not in weekly_rows:
                    continue
                if rec.get("last_weekly_report") == report_day and "period_start" in rec:
                    for field in PERIOD_FIELDS:
                        if field in rec["period_start"]:
                            rec[field] = rec["period_start"][field]
                        else:
                            rec.pop(field, None)
                    rec["membership_events"] = [e for e in rec.get("membership_events", []) if e.get("date") != report_day]
                    rec["history"] = [h for h in rec.get("history", []) if h.get("date") != report_day]
                else:
                    rec["period_start"] = {k: rec[k] for k in PERIOD_FIELDS if k in rec}
                if rec.get("in_active_126"):
                    was_active.add(rec["id"])
                else:
                    was_active.discard(rec["id"])
                if complete and rec["id"] in was_active and rec["id"] not in weekly_rows:
                    rec["last_active_rank"] = saved_rank(rec) or former_rank(rec)
                    rec["in_active_126"] = False
                    for field in WEEK_METRICS.values():
                        rec[field] = 0
                    imported_event(rec, report_day, "Left roster")
                    departed.add(rec["id"])
                    touched.add(rec["id"])
                if complete or rec["id"] in weekly_rows:
                    rec["restore_this_report"] = False

        if kind == WAR:
            if not any(row["id"] in by_id for row in rows):
                raise ValueError("The KvK export contains no governors tracked by ODS1.")
            for rec in records:
                rec["kvk_capture"] = report_day + ("T" + rows[0]["scan_time"] if rows[0].get("scan_time") else "")
                scans = rec.setdefault("kvk_scans", {})
                prior_day = rec.get("source_dates", {}).get(WAR)
                if prior_day:
                    scans.setdefault(prior_day, None)
                scans[report_day] = None
                rec["in_kvk_4161"] = False
                for field in WAR_METRICS.values():
                    rec.pop(field, None)
        metrics = {WEEK: WEEK_METRICS, LIFETIME: ALL_METRICS, WAR: WAR_METRICS}[kind]
        for position, row in enumerate(rows, start=1):
            gid = int(row["id"])
            # A kingdom leaderboard can include players who have never been in ODS1.
            if kind == WAR and gid not in by_id:
                continue
            if gid not in by_id:
                by_id[gid] = {"id": gid, "name": str(row.get("name") or f"Governor {gid}"), "aliases": [],
                             "in_active_126": False, "in_kvk_4161": False, "history": [], "is_new_joiner": False}
                records.append(by_id[gid])
            rec = by_id[gid]
            touched.add(gid)
            # An older spelling can persist in kingdom or all-time exports.
            name_day = rec.get("roster_name_date", rec.get("last_weekly_report") or "")
            if kind == WEEK:
                rec["roster_name_date"] = report_day if row.get("name") else name_day
            roster_name_is_current = kind != WEEK and rec.get("in_active_126") and name_day >= report_day
            apply_identity(rec, row, keep_current_name=roster_name_is_current)
            if kind == WEEK:
                for field in WEEK_METRICS.values():
                    rec.pop(field, None)
            if row.get("power") is not None and (kind == WEEK or not rec.get("in_active_126")):
                rec["power"] = row["power"]
            if kind == WAR:
                apply_war_metrics(rec, row, position, report_day)
            else:
                for source, dest in metrics.items():
                    if row.get(source) is not None:
                        rec[dest] = row[source]
            if kind == WEEK:
                rec.setdefault("period_start", {k: rec[k] for k in PERIOD_FIELDS if k in rec})
                if gid not in was_active:
                    known = rec.get("first_seen_ods1") or rec.get("joined_date") or former_rank(rec) or any(h.get("in_active") and h.get("date") != report_day
                                                   for h in rec.get("history", []))
                    if known:
                        returned.add(gid)
                        rec["returned_date"] = report_day
                        rec["return_rank"] = former_rank(rec)
                        rec["restore_this_report"] = restore and bool(rec["return_rank"])
                        imported_event(rec, report_day, "Returned")
                    else:
                        joined.add(gid)
                rec["in_active_126"] = True
                if rank_code(row.get("rank")):
                    rec["rank"] = rank_code(row["rank"])
                if rec.get("restore_this_report") and rec.get("return_rank"):
                    rec["rank"] = rec["return_rank"]
                joined_on = iso_day(row.get("joined"))
                if joined_on and joined_on <= day:
                    rec["joined_date"] = joined_on.isoformat()
            if row.get("last login"):
                rec["last_login"] = str(row["last login"])

    # Save the observed report, including its ranks and scores under the rules in use.
    has_week = weekly_rows is not None
    if not touched:
        raise ValueError("The report contains no governors tracked by ODS1.")
    for rec in records:
        rec["status"] = bucket_status(rec)
        for kind, _, _ in changed:
            rec.setdefault("source_dates", {})[kind] = report_day
            rec.setdefault("source_fingerprints", {})[kind] = report_digests[kind]
        if has_week and (complete or rec["id"] in weekly_rows):
            rec["last_weekly_report"] = report_day
            rec["week_start"] = week_start
            rec["week_open"] = week_open
            if rec.get("in_active_126"):
                result = classify(rec, rules)
                if (auto and (result["action"] == "Promote" or (result["action"] == "Review suggested rank" and not saved_rank(rec)))
                        and result["proposed"] in RANKS and not rec.get("officer_rank") and not rec.get("is_excused")):
                    rec["rank"] = result["proposed"]
                    if result["action"] == "Promote":
                        rec["promotion_applied"] = {"week": monday(day).isoformat(), "rank": rec["rank"]}
                if saved_rank(rec):
                    rec["last_active_rank"] = saved_rank(rec)
            hist = rec.setdefault("history", [])
            hist[:] = [h for h in hist if h.get("date") != report_day]
            hist.append(snapshot(rec, rules, report_day))
        elif rec["id"] in touched and report_day == rec.get("last_weekly_report"):
            hist = rec.get("history", [])
            for index, item in enumerate(hist):
                if item.get("date") == report_day:
                    hist[index] = snapshot(rec, rules, report_day)
                    break
    return f"Updated {len(touched)} governors · {len(joined)} first appearances in weekly reports · {len(returned)} returned · {len(departed)} left."


class OlderReports(ValueError):
    """The selected reports predate the saved roster and produced no changes."""


def merge_dated_reports(records, batches, complete=False, rules=DEFAULT_RULES, restore=True, auto=False):
    """Import each period in order inside the caller's single roster transaction."""
    newest = {}
    for rec in records:
        for kind, saved_day in (rec.get("source_dates") or {}).items():
            newest[kind] = max(newest.get(kind, ""), saved_day)
    changes = []
    skipped = []
    for day, reports in sorted(batches.items()):
        eligible = []
        for kind, digest, rows in reports:
            if day < newest.get(kind, ""):
                skipped.append(f"{kind} for {day} (latest saved {newest[kind]})")
            else:
                eligible.append((kind, digest, rows))
        if eligible:
            result = merge_reports(records, eligible, day, complete, rules, restore, auto)
            if result != ALREADY_IMPORTED:
                changes.append(f"{day} · {result}")
    if skipped:
        message = "Skipped older exports: " + ", ".join(skipped) + "."
        if not changes:
            raise OlderReports(message)
        changes.append(message)
    return "  \n".join(changes) or ALREADY_IMPORTED


def history_labels(records):
    labels = {h["date"] for r in records for h in r.get("history", []) if h.get("date")}
    return sorted(labels, key=lambda label: (iso_day(label) or date.min, label), reverse=True)


def save_officer(records, gid, override, note, excused, expected, *, scanned_rank=None):
    rec = next((r for r in records if r["id"] == gid), None)
    if rec is None:
        raise ValueError("This governor is no longer in the file. Refresh the roster.")
    if officer_values(rec) != expected:
        raise ValueError("Another officer updated this governor. Reload the saved values before saving.")
    if override is not None and override not in RANKS:
        raise ValueError("Choose a valid rank.")
    if not scanned_rank and override != rec.get("officer_rank") and gid in COMMAND and override not in (None, COMMAND[gid][0]):
        raise ValueError("The command rank is locked.")
    held = saved_rank({**rec, "roster_rank": scanned_rank}) if scanned_rank else saved_rank(rec)
    report_day = iso_day(rec.get("last_weekly_report"))
    if report_day and held and override and RANKS.index(override) < RANKS.index(held):
        rec["promotion_applied"] = {"week": monday(report_day).isoformat(), "rank": override}
    rec.update(officer_rank=override, officer_note=note.strip(), is_excused=bool(excused))
    if rec.get("in_active_126") and saved_rank(rec):
        rec["last_active_rank"] = saved_rank(rec)
    # A report is an as-imported snapshot. Officer edits affect only the current roster.


def officer_values(rec):
    return (rec.get("officer_rank"), rec.get("officer_note") or "", bool(rec.get("is_excused")))


def dates_in_label(name):
    matches = re.findall(r"(?<!\d)(20\d{2})[-_./]?(\d{2})[-_./]?(\d{2})(?!\d)", str(name))
    return [day for parts in matches if (day := iso_day("-".join(parts)))]


def report_date_in_name(name):
    return max(dates_in_label(name), default=None)


def kvk_filename_time(name):
    stamp = re.search(r"(?<!\d)20\d{2}[-_]?\d{2}[-_]?\d{2}[ T_-]+"
                      r"([01]\d|2[0-3])[:-]?([0-5]\d)[:-]?([0-5]\d)(?!\d)", name)
    return ":".join(stamp.groups()) if stamp else ""


def detect_report_day(name, frame):
    if "report end" in frame:
        ends = frame["report end"].dropna().unique()
        if len(ends) == 1 and (day := report_date_in_name(ends[0])):
            return day
    for line in frame.attrs.get("report_metadata", []):
        if re.search(r"\b(report end|end date|date to|period|date range|report date)\b", line, re.I):
            if day := report_date_in_name(line):
                return day
    return report_date_in_name(name)


def detect_week_start(name, frame, end):
    if "report start" in frame:
        starts = frame["report start"].dropna().unique()
        if len(starts) == 1 and (day := report_date_in_name(starts[0])):
            return day
    for label in [*frame.attrs.get("report_metadata", []), name]:
        days = dates_in_label(label)
        if len(days) >= 2 and end in days:
            return min(days)
    return monday(end)


def repository_reports(directory=DATA_DIR):
    directories = (REPO_DATA_DIR, directory) if directory == DATA_DIR and directory != REPO_DATA_DIR else (directory,)
    paths = {p.name: p for folder in directories if folder.is_dir() for p in folder.iterdir()
             if p.is_file() and not p.name.startswith(("~$", ".")) and p.suffix.lower() in {".xlsx", ".xls", ".csv", ".tsv"}}
    return sorted(paths.values(), key=lambda p: p.name)



def membership_folders(directory):
    # Clean reports and the previous activity data set describe the same alliance.
    return (DATA_DIR, REPO_DATA_DIR) if directory in (DATA_DIR, CLEAN_DATA_DIR) else (directory, None)


def current_membership(directory):
    return membership.latest(*membership_folders(directory))


def backfill_war_scans(records, sources, pending):
    """Recover observations for older saved rosters and members first tracked after a scan."""
    latest = max((r.get("source_dates", {}).get(WAR, "") for r in records), default="")
    for day, (name, digest, frame) in sources.items():
        needed = []
        for rec in records:
            scans = rec.get("kvk_scans", {})
            sample = scans.get(day)
            if day not in scans or (sample is not None and not {"healed", "acclaim"}.issubset(sample)):
                needed.append(rec)
        if day > latest or not needed:
            continue
        fingerprint = hashlib.sha256(repr((day, digest, None)).encode()).hexdigest()
        same_latest = day == latest and any(r.get("source_fingerprints", {}).get(WAR) == fingerprint for r in records)
        try:
            rows = {row["id"]: (i, row) for i, row in enumerate(report_data(name, frame, WAR), 1)}
        except ValueError as exc:
            warning = f"{name} · {exc}"
            if warning not in pending:
                pending.append(warning)
            continue
        if day < latest:
            # A corrected upload can differ from the bundled file for that date.
            known = [(r["id"], r["kvk_scans"][day]) for r in records if day in r.get("kvk_scans", {})]
            fields = ("dkp", "t4", "t5", "healed", "acclaim")
            if any((saved is None) != (gid not in rows)
                   or (saved is not None and any(saved[k] != rows[gid][1].get(k) for k in fields if k in saved))
                   for gid, saved in known):
                continue
        for rec in needed:
            position, row = rows.get(rec["id"], (None, None))
            if day == latest and not same_latest:
                if not row or not rec.get("in_kvk_4161") or not all(
                    row.get(k) is not None and row[k] == rec.get(WAR_METRICS[k]) for k in ("dkp", "t4", "t5")
                ):
                    continue
                # A corrected upload owns the readings for its date, including any missing fields.
                row = {key: rec.get(field) for key, field in WAR_METRICS.items()}
                row["power"] = rec.get("power")
            existing = rec.get("kvk_scans", {}).get(day)
            if existing is not None:
                if row and all(existing.get(k) == row.get(k) for k in ("dkp", "t4", "t5")):
                    observed = war_sample(row, row.get("power"))
                    if day == latest or (existing.get("score") is not None and observed.get("score") == existing["score"]):
                        for field in ("healed", "acclaim"):
                            existing.setdefault(field, observed[field])
                continue
            if row is None:
                rec.setdefault("kvk_scans", {})[day] = None
                if same_latest:
                    rec["in_kvk_4161"] = False
                    for field in WAR_METRICS.values():
                        rec.pop(field, None)
            elif same_latest:
                apply_war_metrics(rec, row, position, day)
                rec.setdefault("source_dates", {})[WAR] = day
                if rec.get("power") is None:
                    rec["power"] = row.get("power")
            else:
                rec.setdefault("kvk_scans", {})[day] = war_sample(row, row.get("power"))


def backfill_week_start(records, name, frame, day):
    # Recover a legacy period only when its dated source agrees with the saved activity.
    label = day.isoformat()
    missing = [(r, h) for r in records for h in r.get("history", [])
               if h.get("date") == label and h.get("in_active") and not h.get("week_start")]
    if not missing:
        return
    rows = {row["id"]: row for row in report_data(name, frame, WEEK, end=day)}
    for rec, entry in missing:
        row = rows.get(rec["id"])
        if row and all(row.get(k) == entry.get(WEEK_METRICS[k]) for k in ("forts", "tech", "build", "helps")):
            entry["week_start"] = row["week_start"]
            entry["week_open"] = row["week_open"]
            if rec.get("last_weekly_report") == label:
                rec.setdefault("week_start", row["week_start"])
                rec.setdefault("week_open", row["week_open"])


def load_report_records(directory, members):
    records = read_records(directory)
    tracked = {r["id"] for r in records}
    for gid in members.keys() - tracked:
        records.append({"id": gid, "name": members[gid]["name"], "aliases": [], "history": [],
                        "in_active_126": False, "in_kvk_4161": False, "is_new_joiner": False})
    pending = []
    scheduled = {}
    complete_days = set()
    saved_war_reports = {}
    war_sources = {}
    paths = repository_reports(directory)
    # Use an archived kingdom scan when it accompanies a weekly report in this data set.
    weekly_days = {report_date_in_name(p.name) for p in paths if "weekly" in p.name.lower()}
    war_days = {report_date_in_name(p.name) for p in paths if "kvk" in p.name.lower()}
    for folder in sorted({p.parent for p in paths}):
        for path in sorted((folder / "archive").glob("*_KvK.csv"), reverse=True):
            label = report_date_in_name(path.name)
            if label in weekly_days - war_days:
                paths.append(path)
                war_days.add(label)
    for path in paths:
        try:
            data = path.read_bytes()
            frame = prepare_file(path.name, data)
            day = detect_report_day(path.name, frame)
            if day is None:
                pending.append(f"{path.name} is undated. Open Import reports to use it.")
                continue
            kind = guess_type(path.name, frame)
            if not kind:
                pending.append(f"Choose a report type for {path.name} in Officer desk.")
                continue
            if kind == LIFETIME and long_activity_period(path.name, frame):
                labels = " ".join([path.name, *frame.attrs.get("report_metadata", [])])
                if not ALL_TIME_LABEL.search(labels):
                    pending.append(f"{path.name} spans more than a week. Review it in Import reports.")
                    continue
            if kind == WEEK and not re.search(r"7[ _-]?d|weekly|week|\d{4}-\d{2}-\d{2}.+\d{4}-\d{2}-\d{2}", path.name, re.I):
                pending.append(f"Confirm whether {path.name} is a weekly or all-time report in Officer desk.")
                continue
            latest = max((r.get("source_dates", {}).get(kind, "") for r in records), default="")
            complete = kind == WEEK and path.name.lower().startswith("ods1-complete-weekly-")
            digest = hashlib.sha256(data).hexdigest()
            if kind == WEEK and latest >= day.isoformat():
                backfill_week_start(records, path.name, frame, day)
            newer_capture = False
            if kind == WAR:
                prior = war_sources.get(day.isoformat())
                clock = kvk_filename_time(path.name)
                if prior and (clock, path.name) < (kvk_filename_time(prior[0]), prior[0]):
                    continue
                war_sources[day.isoformat()] = (path.name, digest, frame)
                stored = max((r.get("kvk_capture", "") for r in records), default="")
                newer_capture = bool(clock and stored.startswith(day.isoformat() + "T") and clock > stored[11:])
            partial_fingerprint = hashlib.sha256(repr((day.isoformat(), digest, False)).encode()).hexdigest()
            upgrade_partial = complete and any(r.get("source_fingerprints", {}).get(WEEK) == partial_fingerprint for r in records)
            upgrade_ranks = False
            if latest == day.isoformat() and complete and "rank" in frame and path.suffix.lower() == ".csv":
                # Recognize a previously imported copy of this exact report before ranks were supplied.
                source = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
                rank_headers = [c for c in source.fieldnames if COLUMN_NAMES.get(normalized_heading(c)) == "rank"]
                stripped = io.StringIO()
                writer = csv.DictWriter(stripped, [c for c in source.fieldnames if c not in rank_headers],
                                        extrasaction="ignore", lineterminator="\n")
                writer.writeheader()
                writer.writerows(source)
                old_digest = hashlib.sha256(stripped.getvalue().encode()).hexdigest()
                old_fingerprints = {hashlib.sha256(repr((day.isoformat(), prior_digest, full)).encode()).hexdigest()
                                    for prior_digest in (old_digest, *SUPERSEDED_WEEKLY_DIGESTS.get(digest, ()))
                                    for full in (False, True)}
                upgrade_ranks = any(r.get("source_fingerprints", {}).get(WEEK) in old_fingerprints for r in records)
            if kind == WAR and latest == day.isoformat():
                war_fingerprint = hashlib.sha256(repr((day.isoformat(), digest, None)).encode()).hexdigest()
                if any(r.get("source_fingerprints", {}).get(WAR) == war_fingerprint for r in records):
                    saved_war_reports[day.isoformat()] = (path.name, digest, frame)
            if latest > day.isoformat() or (latest == day.isoformat() and not (upgrade_partial or upgrade_ranks or newer_capture)):
                continue
            rows = report_data(path.name, frame, kind)
            batch = scheduled.setdefault(day.isoformat(), [])
            if kind == WAR:
                batch[:] = [item for item in batch if item[0] != WAR]
            batch.append((kind, digest, rows))
            if complete:
                complete_days.add(day.isoformat())
        except (OSError, ValueError, ImportError) as exc:
            pending.append(f"{path.name} · {exc}")
    latest_war = max((r.get("source_dates", {}).get(WAR, "") for r in records), default="")
    if latest_war and latest_war not in war_sources and directory == CLEAN_DATA_DIR:
        source = REPO_DATA_DIR / f"Kingdom-4161-KvK-{latest_war}.csv"
        if source.is_file():
            data = source.read_bytes()
            war_sources[latest_war] = (source.name, hashlib.sha256(data).hexdigest(), prepare_file(source.name, data))
    backfill_war_scans(records, war_sources, pending)
    for label, batch in sorted(scheduled.items()):
        try:
            # Missing members only leave when an officer confirms a complete roster.
            updated = copy.deepcopy(records)
            if label in complete_days and label in saved_war_reports and not any(kind == WAR for kind, _, _ in batch):
                # Match the same KvK report again after correcting the membership for that day.
                name, digest, frame = saved_war_reports[label]
                batch = [*batch, (WAR, digest, report_data(name, frame, WAR))]
                for rec in updated:
                    rec.get("source_fingerprints", {}).pop(WAR, None)
            merge_reports(updated, batch, label, complete=label in complete_days)
            records = updated
        except ValueError as exc:
            pending.append(f"{label} · {exc}")
    if scheduled:
        backfill_war_scans(records, war_sources, pending)
    return records, pending


def load_live(directory=DATA_DIR):
    captured, members = current_membership(directory)
    records, pending = load_report_records(directory, members)
    if captured is None:
        return records, pending
    week = latest_week(records)
    for rec in records:
        member = members.get(rec["id"])
        rec["current_member"] = member is not None
        rec["membership_date"] = captured.date().isoformat()
        if member:
            rec["roster_rank"] = member["rank"]
            apply_identity(rec, member)
            rec["has_weekly_activity"] = any(h.get("date") == week and h.get("in_active") for h in rec["history"])
            if not rec["has_weekly_activity"]:
                for field in WEEK_METRICS.values():
                    rec.pop(field, None)
        rec["status"] = bucket_status(rec)
    return records, pending
