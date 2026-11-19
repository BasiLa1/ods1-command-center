"""ODS1 roster scoring, report imports and officer decisions."""

import copy
import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
from filelock import FileLock
from xlrd.biffh import XLRDError

REPO_DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR = Path(os.environ.get("ODS1_DATA_DIR") or REPO_DATA_DIR).expanduser()
BASELINE = "ods1_baseline.json"
CLEAN_DATA_DIR = DATA_DIR / "clean-reports"
LEGACY_STATE = "ods1_persistent_state.json"
RANKS = ("R5", "R4", "R3", "R2", "R1")
ACTIONS = ("Keep current rank", "Promote", "Demote", "Monitor / warn", "Kick", "Review suggested rank")
PHASES = {"Early KvK": (0.55, 0.45), "Mid KvK": (0.50, 0.50), "Late KvK": (0.30, 0.70)}
DEFAULT_RULES = ("Early KvK", 45.0, 55.0)
COMMAND = {
    233428447: ("R5", "Leader"), 233185199: ("R5", "Counselor / R5"),
    233184542: ("R4", "Warlord"), 233184517: ("R4", "Envoy"),
    233190616: ("R4", "Officer"), 233196311: ("R4", "Officer"),
    233183034: ("R4", "Officer"), 233183356: ("R4", "Officer"),
}
WEEK, LIFETIME, WAR = "Weekly ODS1 roster", "All-time ODS1 activity", "Kingdom 4161 KvK"
BASE_LABEL = "Saved baseline"
ALREADY_IMPORTED = "These files are already reflected in this report."
ALL_TIME_LABEL = re.compile(r"all[\s_.-]*time|life[\s_.-]*time", re.I)
PERIOD_FIELDS = ("in_active_126", "rank", "last_active_rank", "restore_this_report", "return_rank", "first_seen_ods1",
                 "returned_date", "joined_date", "is_new_joiner", "forts_7d", "tech_7d", "helps_7d",
                 "rss_7d", "build_7d", "rok_use_7d", "rok_act_7d")
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
    "report end": "report end|report end date|end date|period end|period end date|date to|report date",
}
COLUMN_NAMES = {alias: target for target, variants in ALIASES.items() for alias in variants.split("|")}


def n(value):
    try:
        amount = float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0
    return amount if math.isfinite(amount) else 0.0


def rank_code(value):
    text = str(value or "").strip().upper().replace(" (ROTATED)", "")
    return text if text in RANKS else None


def iso_day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def utc_day():
    return datetime.now(timezone.utc).date()


def report_today():
    return datetime.now(ZoneInfo("Asia/Tbilisi")).date()


def saved_rank(rec):
    return rank_code(rec.get("officer_rank")) or rank_code(rec.get("rank"))


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
    if not rec.get("in_active_126"):
        return ""
    for field, label in (("returned_date", "Returned"), ("joined_date", "New"), ("first_seen_ods1", "First seen")):
        observed = iso_day(rec.get(field))
        if observed and 0 <= (on_day - observed).days < 14:
            return f"{label} · {observed.strftime('%b')} {observed.day}"
    if rec.get("is_new_joiner") and not any(rec.get(k) for k in ("joined_date", "first_seen_ods1", "returned_date")):
        return "Join date unknown"
    return ""


def classify(rec, rules=DEFAULT_RULES):
    phase, r3_cutoff, specialist = rules
    active = bool(rec.get("in_active_126"))
    support = round(
        min(n(rec.get("forts_7d")) / 200, 1) * 52
        + min(n(rec.get("tech_7d")) / 100000, 1) * 20
        + min(n(rec.get("build_7d")) / 90000, 1) * 20
        + min(n(rec.get("helps_7d")) / 2500, 1) * 8, 1,
    ) if active else n(rec.get("rok_use_all"))
    power, dkp = n(rec.get("power")), n(rec.get("kvk_dkp"))
    ratio = dkp / power if power > 0 else 0
    target = 0.10 if power < 12e6 else 0.15 if power <= 20e6 else 0.22
    war = round(min(ratio / target, 1) * 75 + min(n(rec.get("kvk_healed")) / 500000, 1) * 15
                + min(n(rec.get("kvk_acclaim")) / 50000, 1) * 10, 1)
    w_support, w_war = PHASES[phase]
    overall = round(min(support * w_support + war * w_war, 100), 1)
    held = saved_rank(rec)
    previous = rank_code(rec.get("return_rank")) if rec.get("restore_this_report") else None
    previous = previous or former_rank(rec)
    gid = int(rec["id"])
    if not active:
        proposed, reason = None, "Outside the current ODS1 roster"
    elif gid in COMMAND or held in ("R4", "R5"):
        proposed, reason = COMMAND[gid] if gid in COMMAND else (held, "Officer rank")
    elif rec.get("is_excused"):
        proposed, reason = held or previous, "Excused by an officer"
    elif rec.get("restore_this_report") and previous:
        proposed, reason = previous, f"Returned to ODS1 · last held {previous}"
    elif overall >= r3_cutoff:
        proposed, reason = "R3", f"Overall {overall:g} meets the R3 cutoff of {r3_cutoff:g}"
    elif support >= specialist:
        proposed, reason = "R3", f"Support specialist · {support:g} usefulness"
    elif war >= 75:
        proposed, reason = "R3", f"War specialist · {war:g} KvK"
    elif overall >= 24 or support >= 30 or war >= 40:
        proposed = "R2"
        reason = (f"{overall:g} overall meets the core cutoff of 24" if overall >= 24 else
                  f"{support:g} support meets the core cutoff of 30" if support >= 30 else
                  f"{war:g} KvK meets the core cutoff of 40")
    elif overall >= 12 or n(rec.get("rok_use_all")) >= 30:
        proposed, reason = "R1", ("Veteran with a slow week" if overall < 12 else "Weekly score in the R1 band")
    else:
        proposed, reason = "Kick", f"{overall:g} overall (under 12) · {n(rec.get('rok_use_all')):g} lifetime (under 30)"

    if not active:
        action = None
    elif rec.get("is_excused") or (held and (gid in COMMAND or (rec.get("restore_this_report") and previous == held))):
        action = ACTIONS[0] if held else ACTIONS[3]
    elif proposed == "Kick":
        action = ACTIONS[4]
    elif not held:
        action = "Review suggested rank"
    elif proposed == "R1" and held == "R1":
        action = ACTIONS[3]
    elif proposed == held:
        action = ACTIONS[0]
    elif RANKS.index(proposed) < RANKS.index(held):
        action = ACTIONS[1]
    else:
        action = ACTIONS[2]
    return dict(support=support, war=war, overall=overall, proposed=proposed, action=action, reason=reason)


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
        "kvk_dkp": rec.get("kvk_dkp"), "phase": rules[0],
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
        gid = int(rec["id"])
        if gid in seen:
            raise ValueError(f"The baseline repeats Governor ID {gid}.")
        seen.add(gid)
        rec["id"] = gid
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
        records, _ = load_live(directory)
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
        if len(dates) >= 2 and (max(dates) - min(dates)).days > 7:
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


def report_data(name, data, kind):
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
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


def apply_identity(rec, row):
    if not row.get("name"):
        return
    new_name = str(row["name"]).strip()
    if new_name and new_name != rec.get("name"):
        aliases = set(rec.get("aliases") or [])
        if rec.get("name"):
            aliases.add(rec["name"])
        aliases.discard(new_name)
        rec.update(name=new_name, aliases=sorted(aliases))


def bucket_status(rec):
    if rec.get("in_active_126"):
        return "Active in ODS1"
    return "Rotated Out (In KD 4161)" if rec.get("in_kvk_4161") else "Departed / Inactive"


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
    report_digests = {kind: hashlib.sha256(repr((report_day, digest, complete if kind == WEEK else None)).encode()).hexdigest()
                      for kind, digest, _ in reports}
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

        if kind == WAR and not any(row["id"] in by_id for row in rows):
            raise ValueError("The KvK export contains no governors tracked by ODS1.")
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
            apply_identity(rec, row)
            if kind == WEEK:
                for field in WEEK_METRICS.values():
                    rec.pop(field, None)
            if row.get("power") is not None and (kind == WEEK or not rec.get("in_active_126")):
                rec["power"] = row["power"]
            for source, dest in metrics.items():
                if row.get(source) is not None:
                    rec[dest] = row[source]
            if kind == WAR:
                rec["in_kvk_4161"] = True
                rec["kd_rank"] = row.get("kingdom rank") or position
            elif kind == WEEK:
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
                        rec["first_seen_ods1"] = report_day
                        rec["is_new_joiner"] = True
                        imported_event(rec, report_day, "First seen")
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
            if rec.get("in_active_126"):
                result = classify(rec, rules)
                if auto and result["proposed"] in RANKS and not rec.get("officer_rank") and not rec.get("is_excused"):
                    rec["rank"] = result["proposed"]
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
    return f"Updated {len(touched)} governors · {len(joined)} first seen · {len(returned)} returned · {len(departed)} left."


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


def save_officer(records, gid, override, note, excused, expected):
    rec = next((r for r in records if r["id"] == gid), None)
    if rec is None:
        raise ValueError("This governor is no longer in the file. Refresh the roster.")
    if officer_values(rec) != expected:
        raise ValueError("Another officer updated this governor. Reload the saved values before saving.")
    if override is not None and override not in RANKS:
        raise ValueError("Choose a valid rank.")
    if override != rec.get("officer_rank") and gid in COMMAND and override not in (None, COMMAND[gid][0]):
        raise ValueError("The command rank is locked.")
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


def repository_reports(directory=DATA_DIR):
    directories = (REPO_DATA_DIR, directory) if directory == DATA_DIR and directory != REPO_DATA_DIR else (directory,)
    paths = {p.name: p for folder in directories if folder.is_dir() for p in folder.iterdir()
             if p.is_file() and not p.name.startswith(("~$", ".")) and p.suffix.lower() in {".xlsx", ".xls", ".csv", ".tsv"}}
    return sorted(paths.values(), key=lambda p: p.name)



def load_live(directory=DATA_DIR):
    records = read_records(directory)
    pending = []
    scheduled = {}
    complete_days = set()
    for path in repository_reports(directory):
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
            partial_fingerprint = hashlib.sha256(repr((day.isoformat(), digest, False)).encode()).hexdigest()
            upgrade_partial = complete and any(r.get("source_fingerprints", {}).get(WEEK) == partial_fingerprint for r in records)
            if latest > day.isoformat() or (latest == day.isoformat() and not upgrade_partial):
                continue
            rows = report_data(path.name, frame, kind)
            scheduled.setdefault(day.isoformat(), []).append((kind, digest, rows))
            if complete:
                complete_days.add(day.isoformat())
        except (OSError, ValueError, ImportError) as exc:
            pending.append(f"{path.name} · {exc}")
    for label, batch in sorted(scheduled.items()):
        try:
            # Missing members only leave when an officer confirms a complete roster.
            updated = copy.deepcopy(records)
            merge_reports(updated, batch, label, complete=label in complete_days)
            records = updated
        except ValueError as exc:
            pending.append(f"{label} · {exc}")
    return records, pending
