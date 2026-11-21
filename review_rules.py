"""ODS1 contribution scores and evidence for a weekly rank review."""

import math
from datetime import date, timedelta


PHASES = {"Early KvK": (0.55, 0.45), "Mid KvK": (0.50, 0.50), "Late KvK": (0.30, 0.70)}
FORTS_PER_DAY = 15
# (Seven-day target, maximum support points)
SUPPORT_TARGETS = {
    "forts_7d": (7 * FORTS_PER_DAY, 15),
    "tech_7d": (100000, 35),
    "build_7d": (90000, 25),
    "helps_7d": (2500, 25),
}


def n(value):
    try:
        amount = float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0
    return amount if math.isfinite(amount) else 0.0


def iso_day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def monday(day):
    return day - timedelta(days=day.weekday())


def support_score(record, start, end, *, allow_fort_shortfall=False):
    days = (end - (start or monday(end))).days + 1 if end else 7
    points = 0.0
    for field, (weekly_target, maximum) in SUPPORT_TARGETS.items():
        if field == "forts_7d" and allow_fort_shortfall:
            points += maximum
        else:
            points += maximum * min(n(record.get(field)) / (weekly_target * days / 7), 1)
    return round(points, 1)


def war_score(power, dkp, healed, acclaim):
    power = n(power)
    ratio = n(dkp) / power if power > 0 else 0
    target = 0.10 if power < 12e6 else 0.15 if power <= 20e6 else 0.22
    return round(min(ratio / target, 1) * 75 + min(n(healed) / 500000, 1) * 15
                 + min(n(acclaim) / 50000, 1) * 10, 1)


def overall_score(support, war, phase):
    w_support, w_war = PHASES[phase]
    return round(min(support * w_support + war * w_war, 100), 1)


def rank_band(overall, support, war, lifetime, rules):
    _, r3_cutoff, specialist = rules
    if overall >= r3_cutoff:
        return "R3", f"Overall {overall:g} meets the R3 cutoff of {r3_cutoff:g}"
    if support >= specialist:
        return "R3", f"Support specialist · {support:g} usefulness"
    if war >= 75:
        return "R3", f"War specialist · {war:g} KvK"
    if overall >= 24:
        return "R2", f"{overall:g} overall meets the core cutoff of 24"
    if support >= 30:
        return "R2", f"{support:g} support meets the core cutoff of 30"
    if war >= 40:
        return "R2", f"{war:g} KvK meets the core cutoff of 40"
    if overall >= 12 or n(lifetime) >= 30:
        return "R1", "Veteran with a slow week" if overall < 12 else "Weekly score in the R1 band"
    return "Kick", f"{overall:g} overall (under 12) · {n(lifetime):g} lifetime (under 30)"


def low_week_streak(record, held, rules, end, ranks):
    """Count adjacent, documented Monday–Sunday periods. Midweek updates add no strikes."""
    if end is None:
        return 0
    sunday = end - timedelta(days=(end.weekday() + 1) % 7)
    history = {h.get("date"): h for h in record.get("history", [])}
    scans = record.get("kvk_scans", {})
    streak = 0
    for week_end in (sunday, sunday - timedelta(days=7)):
        label = week_end.isoformat()
        entry = record if week_end == end else history.get(label, {})
        start = monday(week_end)
        present = entry.get("in_active_126") if entry is record else entry.get("in_active")
        if (not present or entry.get("week_start") != start.isoformat() or entry.get("week_open") or entry.get("is_excused")
                or any(entry.get(key) is None for key in SUPPORT_TARGETS if key != "forts_7d")):
            break
        joined = iso_day(record.get("joined_date"))
        if joined and joined > start:
            break
        if entry is not record and entry.get("rank") and entry["rank"] != held:
            break
        scan_day = max((d for d in scans if start.isoformat() <= d <= label), default=None)
        war = (scans.get(scan_day) or {}).get("score")
        if war is None:
            break
        # A member who spent AP on normal barbarians must never be flagged for a fort shortfall alone.
        support = support_score(entry, start, week_end, allow_fort_shortfall=True)
        overall = overall_score(support, war, rules[0])
        lifetime = entry.get("rok_use_all")
        target, _ = rank_band(overall, support, war, lifetime, rules)
        if target == "Kick" and held == "R1" and lifetime is None:
            break
        if target != "Kick" and ranks.index(target) <= ranks.index(held):
            break
        streak += 1
    return streak
