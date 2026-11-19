"""ODS1 Command Center. Start with streamlit run app.py from the repository."""
import hashlib
import json
import re
from html import escape

import pandas as pd
import streamlit as st
from filelock import Timeout

import roster as db


VIEWS = ("Roster review", "Overview", "Activity", "Leaderboards", "KvK war", "Rotations", "Officer desk")
PRIORITY = {"Promote": 0, "Demote": 1, "Monitor / warn": 2, "Kick": 3, "Keep current rank": 4, "Review suggested rank": 2}
ACTION_STYLE = dict(zip(db.ACTIONS, ("keep", "promote", "demote", "monitor", "kick", "promote")))
SHORT_ACTION = {"Keep current rank": "Keep", "Kick": "Kick review"}
CSS = """
<style>
:root{--ink:#10151a;--panel:#192026;--line:#333b40;--paper:#f2f0e9;--muted:#a8b1b4;--gold:#e5bd68}
[data-testid="stAppViewContainer"],.stApp{background:var(--ink);color:var(--paper)}
[data-testid="stSidebar"]{background:#171d22;border-right:1px solid var(--line)}
[data-testid="stHeader"]{background:var(--ink)}
[data-testid="stMainBlockContainer"],.main .block-container{max-width:1480px;padding-top:3.5rem;padding-bottom:3rem}
[data-testid="stVerticalBlock"]{gap:.85rem}
h2,h3{letter-spacing:-.025em;color:var(--paper)}
.mast{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:8px 0 24px;border-bottom:1px solid #4b4436;margin-bottom:2px}
.identity{display:flex;align-items:center;gap:17px}.sigil{width:54px;height:64px;flex-shrink:0;background:#c9a553;clip-path:polygon(0 0,100% 0,100% 73%,50% 100%,0 73%);display:grid;place-items:center}
.sigil span{display:grid;place-items:center;width:50px;height:60px;background:#1b2022;clip-path:inherit;font:700 24px Georgia,serif;letter-spacing:-.075em;color:#f1d48f;padding-bottom:5px}
.overline,.stamp small,.stat-label,.subhead,.council thead th{font:700 .74rem/1.4 Inter,system-ui,sans-serif;letter-spacing:.095em;text-transform:uppercase}
.overline{color:var(--gold);margin-bottom:3px}.mast h1{font:normal clamp(2.05rem,3.6vw,3.35rem)/1.06 Georgia,'Times New Roman',serif;letter-spacing:-.045em;color:var(--paper);margin:0;padding:0}
.stamp{border-left:2px solid #b19457;padding-left:15px;display:grid;gap:3px}.stamp small{color:var(--muted)}.stamp strong{font-size:1rem;color:var(--paper)}.stamp span{font-size:.83rem;color:#c9b27e}
.st-key-section{width:100%!important}.st-key-section [role="radiogroup"]{width:100%;display:grid!important;grid-template-columns:repeat(7,minmax(0,1fr));gap:.25rem;padding:.28rem;border:1px solid var(--line);border-radius:10px;background:#151b20;flex-wrap:nowrap}
.st-key-section [role="radiogroup"]>div{min-width:0;display:flex}.st-key-section [data-testid="stRadioOption"]>div>div:first-child:not([data-testid="stMarkdownContainer"]){display:none}.st-key-section [role="radiogroup"] label{position:relative;display:flex!important;justify-content:center;align-items:center;flex:1 1 0;margin:0!important;min-height:50px;border-radius:6px;padding:.35rem .5rem!important;cursor:pointer;white-space:nowrap}
.st-key-section [role="radiogroup"] label>div:first-child{position:absolute!important;opacity:0;width:1px;height:1px;overflow:hidden}
.st-key-section [role="radiogroup"] label p{font-size:1rem;font-weight:650;margin:0;color:#c4cbcd}
.st-key-section [role="radiogroup"] label:hover{background:#252c30}
.st-key-section [role="radiogroup"] label:has(input:checked){background:#e5bd68}
.st-key-section [role="radiogroup"] label:has(input:checked) p{color:#211d13}
.st-key-section [role="radiogroup"] label:focus-within{outline:2px solid #f2d693;outline-offset:1px}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid var(--line);border-radius:10px;background:var(--panel);overflow:hidden;margin:4px 0 2px}
.stat{padding:16px 21px 15px;border-right:1px solid var(--line)}.stat:last-child{border:0}.stat-label{color:var(--muted);letter-spacing:.075em}
.stat-value{font:550 2.12rem/1.1 Inter,system-ui,sans-serif;letter-spacing:-.055em;color:#f3f0e7;font-variant-numeric:tabular-nums;margin:4px 0}
.stat small{font-size:.8rem;color:#aeb8b9}.stat:first-child .stat-value{color:#efd69b}
.section-title{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:12px 0 0}
.section-title h2{font:normal 1.75rem/1.15 Georgia,serif;letter-spacing:-.035em;padding:0;margin:0;color:var(--paper)}.section-title span{font-size:.87rem;color:var(--muted)}
.council-wrap{overflow:hidden;border:1px solid var(--line);border-radius:10px}
.council{border-collapse:collapse!important;border:0!important;width:100%;margin:0!important;text-align:left;color:var(--paper);font:400 .92rem/1.4 Inter,system-ui,sans-serif}
.council thead th{background:#21282c;color:#bdc5c5;letter-spacing:.055em;text-align:left;font-size:.72rem}
.council td,.council th{padding:11px 12px!important;border:0!important;vertical-align:middle}
.council td{border-top:1px solid #2a3135!important}.council tbody tr:nth-child(even){background:#151b20}.council tbody tr:hover{background:#20272b}
.council .pos{color:#95a0a4;width:36px;text-align:right;font-variant-numeric:tabular-nums}
.council a{color:#f0ece2!important;text-decoration:none;font-weight:640;overflow-wrap:anywhere}.council a:hover,.council a:focus-visible{color:#f3d38f!important;text-decoration:underline}
.rank-pair{white-space:nowrap;font-variant-numeric:tabular-nums;font-weight:650}.rank-pair i{font-weight:400;color:#8b989d;font-style:normal;margin:0 .25rem}
.reason{color:#c5cdce}.score{font-variant-numeric:tabular-nums;font-weight:650}.chip,.join-tag{display:inline-block;vertical-align:middle;font:650 .78rem/1.5 Inter,system-ui,sans-serif;border-radius:4px;white-space:nowrap}
.chip{padding:2px 8px;border:1px solid}.keep{background:#232b2e;border-color:#465258;color:#c7d1d2}.promote{background:#17332d;border-color:#32564a;color:#a3e0bc}
.demote{background:#352b20;border-color:#665139;color:#edc38e}.monitor{background:#343022;border-color:#625837;color:#ead28f}.kick{background:#372329;border-color:#64444b;color:#f3adb1}
.join-tag{font-size:.7rem;color:#e9ce8d;border:1px solid #5e5134;background:#29271f;padding:0 5px;margin-left:5px}.subhead{color:var(--muted);margin:0 0 5px}
.profile{padding:18px 20px;background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--gold);border-radius:8px}
.profile strong{display:block;font-size:1.3rem}.profile p{margin:5px 0 0;color:#c6ced0;font-size:.94rem}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:8px;overflow:hidden}
@media(max-width:820px){.stat{padding:12px}.council .reason-col{display:none}.mast{padding-bottom:16px}.st-key-section [role="radiogroup"] label p{font-size:.9rem}}
@media(max-width:600px){[data-testid="stMainBlockContainer"]{padding:3rem .85rem 2rem}.mast{align-items:flex-start;gap:8px}.identity{gap:9px}.sigil{width:35px;height:42px}.sigil span{width:32px;height:38px;font-size:17px}.overline{font-size:.64rem}.mast h1{font-size:1.9rem}.stamp{padding-left:8px}.stamp small,.stamp span{font-size:.64rem}.stamp strong{font-size:.78rem}
.st-key-section [role="radiogroup"]{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:2px}.st-key-section [role="radiogroup"]>*{grid-column:span 2}.st-key-section [role="radiogroup"] label{min-height:40px;padding:.3rem .15rem!important}
.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.stat:nth-child(2){border-right:0}.stat:nth-child(-n+2){border-bottom:1px solid var(--line)}.stat-value{font-size:1.65rem}
.council .score-col{display:none}.council td,.council th{padding:9px 5px!important}.council .pos{width:22px}.council{font-size:.85rem}.council .chip{font-size:.68rem;padding:1px 4px}.join-tag{display:table;margin:3px 0 0}.rank-pair i{margin:0 .08rem}.section-title h2{font-size:1.55rem}}
</style>
"""


def html(markup):
    st.html(markup)


def esc(value):
    return escape(str(value), quote=True)


def title(label, detail=""):
    html(f'<div class="section-title"><h2>{esc(label)}</h2><span>{esc(detail)}</span></div>')


def stats(values):
    blocks = [f'<div class="stat"><div class="stat-label">{esc(label)}</div><div class="stat-value">{esc(value)}</div>'
              f'<small>{esc(detail)}</small></div>' for label, value, detail in values]
    html('<div class="metrics">' + ''.join(blocks) + '</div>')


def compact(value):
    return f"{value / 1e6:,.1f}M" if abs(value) >= 1e6 else f"{value:,.0f}"


def matches(rec, query):
    term = query.strip().casefold()
    return any(term in str(v).casefold() for v in (rec["name"], rec["id"], *(rec.get("aliases") or [])))


def display_name(rec):
    tag = db.badge(rec, db.utc_day())
    return f"{rec['name']}  ·  {tag}" if tag else rec["name"]


def frame_table(rows, key, empty="No governors match this view."):
    if not rows:
        st.info(empty)
        return
    frame = pd.DataFrame(rows)
    frame.insert(0, "#", range(1, len(frame) + 1))
    st.dataframe(frame, hide_index=True, use_container_width=True, key=key)


def open_import():
    st.session_state.section = "Officer desk"
    st.session_state.officer_mode = "Import reports"


def review_page(scored):
    active = [r for r in scored if r["in_active_126"]]
    counts = {action: sum(r["action"] == action for r in active) for action in db.ACTIONS}
    stats([("Active roster", len(active), "In the saved ODS1 roster"),
           ("Rank suggestions", counts["Promote"] + counts["Demote"] + counts["Review suggested rank"], f'{counts["Promote"]} promote · {counts["Demote"]} demote · {counts["Review suggested rank"]} to review'),
           ("Check-ins", counts["Monitor / warn"], "Monitor / warn queue"),
           ("Kick review", counts["Kick"], "Officer decision required")])
    heading, upload = st.columns([4, 1])
    with heading:
        title("Weekly review", f"{len(active)} active governors")
    upload.button("Import reports", type="primary", on_click=open_import, key="open_import", use_container_width=True)
    a, b, c, d = st.columns([2.1, 1.3, 1, 1])
    query = a.text_input("Find a governor", placeholder="Name, alias or Governor ID", key="review_search")
    action = b.selectbox("Decision", ("All decisions", *db.ACTIONS), key="action_filter")
    rank = c.selectbox("Saved rank", ("All ranks", *db.RANKS, "Unrecorded"), key="rank_filter")
    target = d.selectbox("Suggested rank", ("All suggestions", *db.RANKS, "Kick"), key="target_filter")
    selected = [r for r in active if (target == "All suggestions" or r["proposed"] == target) and matches(r, query) and (action == "All decisions" or r["action"] == action)
                and (rank == "All ranks" or (r["held"] or "Unrecorded") == rank)]
    selected.sort(key=lambda r: (PRIORITY[r["action"]], -r["overall"] if r["action"] in ("Promote", "Keep current rank") else r["overall"],
                                r["name"].casefold(), r["id"]))
    if not selected:
        st.info("No governors match these filters.")
        return
    signature = (query, action, rank, target)
    if st.session_state.get("review_signature") != signature:
        st.session_state.review_page = 1
        st.session_state.review_signature = signature
    pages = (len(selected) + 14) // 15
    page = min(int(st.session_state.get("review_page", 1)), pages)
    start = (page - 1) * 15
    rows = []
    for number, rec in enumerate(selected[start:start + 15], start=start + 1):
        joined = db.badge(rec, db.utc_day())
        tag = f'<span class="join-tag">{esc(joined)}</span>' if joined else ""
        decision = rec["action"]
        decision_label = f'Suggest {rec["proposed"]}' if decision == "Review suggested rank" else SHORT_ACTION.get(decision, decision)
        rows.append(f'<tr><td class="pos">{number}.</td><td><a target="_self" href="?governor={int(rec["id"])}">{esc(rec["name"])}</a>{tag}</td>'
                    f'<td class="rank-pair">{esc(rec["held"] or "—")}<i>→</i>{esc(rec["proposed"] or "—")}</td>'
                    f'<td><span class="chip {ACTION_STYLE[decision]}">{esc(decision_label)}</span></td>'
                    f'<td class="score score-col">{rec["overall"]:.1f}</td><td class="reason reason-col">{esc(rec["reason"])}</td></tr>')
    html('<div class="council-wrap"><table class="council"><thead><tr><th class="pos">#</th><th>Governor</th>'
         '<th>Saved → suggested</th><th>Decision</th><th class="score-col">Overall</th><th class="reason-col">Reason</th>'
         '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')
    a, b, c = st.columns([2.2, 1, 1])
    a.caption(f"{start + 1}–{min(start + 15, len(selected))} of {len(selected)} · Rank changes first")
    if pages > 1:
        if b.button("Previous", disabled=page == 1, key="previous_review", use_container_width=True):
            st.session_state.review_page = page - 1
            st.rerun()
        if c.button("Next", disabled=page == pages, key="next_review", use_container_width=True):
            st.session_state.review_page = page + 1
            st.rerun()
    csv_rows = [{"#": idx, "Governor ID": r["id"], "Governor": r["name"], "Saved rank": r["held"],
                 "Suggested rank": r["proposed"], "Decision": r["action"], "Reason": r["reason"],
                 "Overall": r["overall"], "Support": r["support"], "KvK": r["war"], "Officer note": r.get("officer_note", "")}
                for idx, r in enumerate(selected, start=1)]
    st.download_button("Download filtered review", pd.DataFrame(csv_rows).to_csv(index=False).encode("utf-8-sig"),
                       "ods1-roster-review.csv", "text/csv")


ACTIVITY_FIELDS = {
    "Forts": ("forts_7d", "forts_all"),
    "Helps": ("helps_7d", "helps_all"),
    "Tech donations": ("tech_7d", "tech_all"),
    "Flag hours": ("build_7d", "build_all"),
    "Activity Points": ("rok_act_7d", "rok_act_all"),
    "Usefulness": ("rok_use_7d", "rok_use_all"),
    "RSS assistance": ("rss_7d", "rss_all"),
}


def activity_members(records, key):
    period = st.radio("Period", ("Weekly", "All-time"), horizontal=True, key=f"{key}_period")
    if period == "All-time":
        return 1, [(display_name(record), record["id"], record) for record in records]
    weeks = db.history_labels(records)
    if not weeks:
        st.info("Import a weekly RokStats report to see that week's activity.")
        return 0, []
    week = st.selectbox("Weekly report ending", weeks, key=f"{key}_week")
    return 0, [
        (entry.get("name") or f"Governor {record['id']}", record["id"], entry)
        for record in records
        for entry in record.get("history", [])
        if entry.get("date") == week and entry.get("in_active")
    ]


def activity_value(entry, field):
    value = entry.get(field)
    if field.startswith("build_") and value is not None:
        return round(db.n(value) / 3600, 1)
    return value


@st.cache_data(show_spinner=False)
def overview_export(path, modified, size):
    frame = pd.read_csv(path)
    id_column = next((c for c in ("Governor ID", "ID") if c in frame), None)
    if id_column is None:
        return pd.DataFrame()
    ids = pd.to_numeric(frame.pop(id_column), errors="coerce")
    frame.index = ids.rename("Governor ID")
    if ids.isna().any() or not ids.is_unique:
        return pd.DataFrame()
    return frame


def overview_page(scored):
    title("Active roster overview")
    active = {r["id"]: r for r in scored if r.get("in_active_126")}
    if not active:
        st.info("No current members in this roster.")
        return
    search, period = st.columns(2)
    query = search.text_input("Find a player", placeholder="Name or Governor ID").strip().casefold()
    weeks = db.history_labels(scored)
    week = period.selectbox("Weekly report ending", weeks or ["No weekly reports"])
    rows = []
    for r in active.values():
        snapshot = next((h for h in r.get("history", []) if h.get("date") == week and h.get("in_active")), {})
        row = {"Governor ID": r["id"], "Governor": r["name"],
               "Saved rank": r["held"], "Suggested rank": r["proposed"], "Decision": r["action"],
               "Power": r.get("power"), "Overall": r["overall"], "Support": r["support"], "KvK score": r["war"],
               "Officer note": r.get("officer_note"), "Excused": bool(r.get("is_excused"))}
        for metric, (weekly, lifetime) in ACTIVITY_FIELDS.items():
            row[f"Weekly · {metric}"] = activity_value(snapshot, weekly)
            row[f"All-time · {metric}"] = activity_value(r, lifetime)
        row.update({f"KvK · {metric.upper() if metric in ('kp', 'dkp') else metric.title()}": r.get(field)
                    for metric, field in db.WAR_METRICS.items()})
        rows.append(row)
    frame = pd.DataFrame(rows).set_index("Governor ID")
    # Include export-only fields such as gifts, goals and individual troop tiers.
    sources = {}
    for path in db.repository_reports(st.session_state.data_directory):
        if path.suffix.lower() != ".csv":
            continue
        name = path.name.casefold()
        day = db.report_date_in_name(name)
        if not day:
            continue
        if "weekly" in name and day.isoformat() == week:
            group = "Weekly"
        elif "all-time" in name:
            group = "All-time"
        elif "kvk" in name:
            group = "KvK"
        else:
            continue
        if group not in sources or day > sources[group][0]:
            sources[group] = day, path
    for group, (day, path) in sources.items():
        info = path.stat()
        raw = overview_export(path, info.st_mtime_ns, info.st_size)
        if raw.empty:
            continue
        extras = raw.drop(columns=["Player", "Governor Name"], errors="ignore")
        for column in extras:
            heading = db.normalized_heading(column)
            field = db.COLUMN_NAMES.get(heading, heading)
            represented = db.WAR_METRICS if group == "KvK" else db.WEEK_METRICS
            if field in represented:
                continue
            label = f"{group} · {column}"
            if label not in frame:
                frame[label] = extras[column].reindex(frame.index)
    frame = frame.sort_values("Governor")
    if query and not frame.empty:
        frame = frame.loc[[gid for gid, name in frame["Governor"].items() if query in f"{name} {gid}".casefold()]]
    if frame.empty:
        st.info("No governors match this view.")
        return
    st.caption(f"{len(frame):,} current members · Scroll sideways for more stats. Select an ODS1 player to edit their rank, note or excused status.")
    visible = frame.reset_index()
    table_key = hashlib.sha256(repr((str(st.session_state.data_directory), week, tuple(frame.index))).encode()).hexdigest()[:16]
    event = st.dataframe(visible, key=f"overview_{table_key}", height=540, hide_index=True,
                         use_container_width=True, on_select="rerun", selection_mode="single-row")
    if event.selection.rows and event.selection.rows[0] < len(visible):
        gid = int(visible.iloc[event.selection.rows[0]]["Governor ID"])
        member_detail([active[gid]], gid, selected=active[gid])


def activity_page(scored):
    title("Alliance activity")
    period, members = activity_members(scored, "activity")
    query = st.text_input("Find a governor", placeholder="Name or Governor ID", key="activity_search")
    fields = {label: columns[period] for label, columns in ACTIVITY_FIELDS.items() if columns[period]}
    frame_table([
        {"Governor": name, "Governor ID": gid,
         **{label: activity_value(entry, field) for label, field in fields.items()}}
        for name, gid, entry in members if query.strip().casefold() in f"{name} {gid}".casefold()
    ], "activity_table", empty="No activity rows in this report.")


def leaderboards_page(scored):
    title("Leaderboards")
    period, members = activity_members(scored, "leaderboards")
    metrics = [name for name, fields in ACTIVITY_FIELDS.items() if fields[period]]
    metric = st.selectbox("Stat", metrics, key="leaderboard_stat")
    field = ACTIVITY_FIELDS[metric][period]
    ranked = sorted(
        ((name, gid, entry) for name, gid, entry in members if entry.get(field) is not None),
        key=lambda member: (-db.n(member[2][field]), member[1]),
    )
    frame_table([
        {"Place": place, "Governor": name, "Governor ID": gid, metric: activity_value(entry, field)}
        for place, (name, gid, entry) in enumerate(ranked[:25], start=1)
    ], "leaderboard", empty=f"This report has no values for {metric}.")


def war_page(scored):
    fighters = [r for r in scored if r.get("in_kvk_4161")]
    title("KvK war", "Kingdom 4161")
    stats([("Tracked fighters", len(fighters), "ODS1-linked governor IDs"),
           ("Combined DKP", compact(sum(db.n(r.get("kvk_dkp")) for r in fighters)), "Active and rotated members"),
           ("Kill points", compact(sum(db.n(r.get("kvk_kp")) for r in fighters)), "Recorded in the KvK export"),
           ("Troops healed", compact(sum(db.n(r.get("kvk_healed")) for r in fighters)), "Recorded in the KvK export")])
    query = st.text_input("Find a fighter", placeholder="Name, alias or ID", key="war_search")
    fighters = sorted((r for r in fighters if matches(r, query)), key=lambda r: (-db.n(r.get("kvk_dkp")), r["id"]))
    frame_table([{"Governor": display_name(r), "KD rank": r.get("kd_rank"), "KvK / 100": r["war"], "DKP": r.get("kvk_dkp"),
                  "Kill points": r.get("kvk_kp"), "Power": r.get("power"), "Healed": r.get("kvk_healed"),
                  "Acclaim": r.get("kvk_acclaim"), "Status": r.get("status")} for r in fighters], "war_table")


def snapshot_rows(records, label):
    rows = []
    for rec in records:
        entry = next((h for h in rec.get("history", []) if h.get("date") == label), None)
        if entry is None:
            continue
        rows.append({"Governor": entry.get("name") or f'ID {rec["id"]}', "Governor ID": rec["id"],
                     "In ODS1": bool(entry.get("in_active")), "Saved rank": entry.get("rank"),
                     "Prior rank": entry.get("last_active_rank"), "Overall": entry.get("overall_score"),
                     "Support": entry.get("ods1_usefulness"), "KvK": entry.get("kvk_score"), "Forts": entry.get("forts_7d"),
                     "Tech points": entry.get("tech_7d"), "DKP": entry.get("kvk_dkp")})
    return sorted(rows, key=lambda r: (not r["In ODS1"], -(r["Overall"] if r["Overall"] is not None else -1), r["Governor ID"]))


def rotations_page(scored):
    title("Rotations & history")
    mode = st.radio("Show", ("Rotated out", "Departed", "Movement log", "Past reports", "Former names"), horizontal=True)
    query = st.text_input("Find a governor", placeholder="Name, alias or ID", key="rotation_search")
    members = [r for r in scored if matches(r, query)]
    if mode == "Past reports":
        labels = db.history_labels(scored)
        if not labels:
            st.info("The first weekly roster import will start the report archive.")
            return
        label = st.selectbox("Saved report", labels)
        st.caption("Read-only · Blank fields were absent from the saved report.")
        frame_table(snapshot_rows(members, label), "snapshot")
    elif mode == "Movement log":
        events = [(e.get("date", ""), r["name"], e) for r in members for e in r.get("membership_events", []) if e.get("type") != "First seen"]
        frame_table([{"Report date": d, "Governor": name, "Movement": e.get("type"), "Previous rank": e.get("rank")}
                     for d, name, e in sorted(events, key=lambda item: item[0], reverse=True)], "events",
                    "No dated roster movements have been recorded for this selection.")
        legacy = db.DATA_DIR / db.LEGACY_STATE
        if legacy.exists():
            historical = json.loads(legacy.read_text(encoding="utf-8-sig")).get("movement_log", [])
            if historical:
                with st.expander("Earlier movement log"):
                    for item in historical:
                        st.text(f"{item.get('timestamp', '')}   Joined / returned: {', '.join(item.get('joined', [])) or '—'}"
                                f"   Left: {', '.join(item.get('left', [])) or '—'}")
    elif mode == "Former names":
        frame_table([{"Governor": r["name"], "Governor ID": r["id"], "Former names": ", ".join(r["aliases"])}
                     for r in members if r.get("aliases")], "aliases")
    else:
        rows = [r for r in members if not r["in_active_126"] and bool(r.get("in_kvk_4161")) == (mode == "Rotated out")]
        rows.sort(key=lambda r: (-db.n(r.get("kvk_dkp" if mode == "Rotated out" else "forts_all")), r["id"]))
        frame_table([{"Governor": r["name"], "Previous rank": db.former_rank(r), "Governor ID": r["id"], "Power": r.get("power"),
                      "DKP": r.get("kvk_dkp"), "All-time forts": r.get("forts_all")} for r in rows], "memberships")


def member_detail(scored, preferred=None, selected=None):
    members = {r["id"]: r for r in sorted(scored, key=lambda r: r["name"].casefold())}
    ids = list(members)
    if not ids:
        st.info("Import a roster to review a governor.")
        return
    gid = selected["id"] if selected else st.selectbox("Governor", ids, index=ids.index(preferred) if preferred in ids else 0,
                       format_func=lambda key: f'{members[key]["name"]} · {key}', key="officer_governor")
    rec = members[gid]
    tag = db.badge(rec, db.utc_day())
    html(f'<div class="profile"><div class="subhead">{esc(db.bucket_status(rec))}</div>'
         f'<strong>{esc(rec["name"])} {f"<small class=join-tag>{esc(tag)}</small>" if tag else ""}</strong>'
         f'<p>Saved rank <b>{esc(rec["held"] or "Unrecorded")}</b> · Previous <b>{esc(db.former_rank(rec) or "Unrecorded")}</b>'
         f' · Suggested <b>{esc(rec["proposed"] or "—")}</b></p><p>{esc(rec["reason"])}</p></div>')
    stats([("Overall", f'{rec["overall"]:.1f}', "Score out of 100"), ("Support", f'{rec["support"]:.1f}', "Alliance usefulness"),
           ("KvK", f'{rec["war"]:.1f}', "War contribution"), ("Power", compact(db.n(rec.get("power"))), "Recorded power")])
    report_days = [day for h in rec.get("history", []) if h.get("in_active")
                   and (day := db.iso_day(h.get("date")))]
    first_report = min(report_days).strftime("%d %b %Y") if report_days else "No weekly record"
    joined = db.iso_day(rec.get("joined_date"))
    st.caption(f"Earliest weekly report (end date) · {first_report} · Alliance join date: "
               f"{joined.strftime('%d %b %Y') if joined else 'Unknown'}")
    expected_key = f"seen_officer_{gid}"
    expected = st.session_state.setdefault(expected_key, db.officer_values(rec))
    with st.form(f"officer_form_{gid}"):
        choices = (None, *(db.RANKS if gid not in db.COMMAND else (db.COMMAND[gid][0],)))
        current = rec.get("officer_rank")
        a, b = st.columns([1.1, 1])
        override = a.selectbox("Officer rank override", choices, index=choices.index(current) if current in choices else 0,
                               format_func=lambda v: v or "Use saved report rank", key=f"override_{gid}")
        excused = b.checkbox("Excused for rebuild or absence", value=bool(rec.get("is_excused")), key=f"excused_{gid}")
        note = st.text_area("Officer note", value=rec.get("officer_note") or "", key=f"note_{gid}",
                            placeholder="Ask about activity and review next report.")
        submitted = st.form_submit_button("Save officer decision", type="primary")
    if submitted:
        try:
            db.change_records(lambda records: db.save_officer(records, gid, override, note, excused, expected),
                              directory=st.session_state.data_directory)
            st.session_state.pop(expected_key, None)
            st.session_state.notice = f'Saved the officer decision for {rec["name"]}.'
            st.rerun()
        except (ValueError, OSError, Timeout) as exc:
            st.error(str(exc))
            st.caption("Refresh the browser to load the latest officer decision.")
    with st.expander("Governor report history"):
        history = sorted(rec.get("history", []), key=lambda h: (db.iso_day(h.get("date")) or db.date.min, str(h.get("date"))))
        prior = None
        rows = []
        for h in history:
            score = h.get("overall_score")
            delta = round(score - prior, 1) if score is not None and prior is not None else None
            rows.append({"Report": h.get("date"), "In ODS1": h.get("in_active"), "Saved rank": h.get("rank"),
                         "Overall": score, "Change": delta, "Support": h.get("ods1_usefulness"), "KvK": h.get("kvk_score")})
            prior = score
        frame_table(list(reversed(rows)), "governor_history")


def commit_import(batches, full, restore, auto):
    try:
        result = db.change_records(lambda records: db.merge_dated_reports(
            records, batches, full, st.session_state.rules, restore, auto),
            directory=st.session_state.data_directory)
    except db.OlderReports as exc:
        st.session_state.import_info = str(exc)
    except (ValueError, OSError, Timeout) as exc:
        st.session_state.import_error = str(exc)
    else:
        st.session_state.import_generation = st.session_state.get("import_generation", 0) + 1
        st.session_state.notice = result


def report_import(scored):
    generation = st.session_state.get("import_generation", 0)
    if message := st.session_state.pop("import_error", None):
        st.error(message)
    if message := st.session_state.pop("import_info", None):
        st.info(message)
    if st.session_state.data_directory == db.CLEAN_DATA_DIR:
        st.caption("Import the older week first. Check that each weekly report shows the date the week ended.")
    uploads = st.file_uploader("Drop your RokStats exports", type=["xlsx", "xls", "csv", "tsv", "txt"],
                               accept_multiple_files=True, key=f"rok_upload_{generation}",
                               help="Excel, CSV or a tab-separated table. You can drop several reports together.")
    files = [(f.name, f.getvalue()) for f in uploads]
    with st.expander("Paste a table"):
        pasted = st.text_area("Paste the headings and rows from Excel or RokStats", key=f"paste_csv_{generation}",
                              placeholder="Paste here, then press Ctrl+Enter to preview.")
    if pasted.strip():
        files.append(("Pasted table.tsv", pasted.encode("utf-8")))
    paths = db.repository_reports(st.session_state.data_directory)
    if paths:
        with st.expander("Use files already in data/"):
            chosen = st.multiselect("Available exports", paths, format_func=lambda path: path.name,
                                    key=f"repo_files_{generation}")
        try:
            files.extend((p.name, p.read_bytes()) for p in chosen)
        except OSError as exc:
            st.error(f"Could not open the selected repository file. {exc}")
            return
    if not files:
        return

    preview = st.container()
    action = st.container()
    options = st.expander("Import options")
    batches = {}
    seen = {}
    weekly_ids = []
    today = db.report_today()
    for idx, (name, data) in enumerate(files):
        try:
            frame = db.prepare_file(name, data)
            guess = db.guess_type(name, frame)
            if guess is None:
                raise ValueError(f"{name} needs an activity column such as forts or helps, or a war column such as DKP.")
            detected_day = db.detect_report_day(name, frame)
            digest = hashlib.sha256(data).hexdigest()
            key = f"{generation}_{idx}_{digest[:16]}"
            with options:
                if len(files) > 1:
                    st.text(name)
                left, right = st.columns(2)
                kind = left.selectbox("Report type", db.REPORT_TYPES, index=db.REPORT_TYPES.index(guess), key=f"kind_{key}")
                day = right.date_input("Report end date", value=detected_day or today, key=f"date_{key}") or detected_day or today
            if day > today:
                raise ValueError(f"{name} is dated {day}, which is in the future. Check the date in Import options.")
            rows = db.report_data(name, frame, kind)
        except (ValueError, OSError, ImportError) as exc:
            preview.error(str(exc))
            return

        slot = (day.isoformat(), kind)
        if slot in seen:
            previous_name, previous_digest = seen[slot]
            if digest == previous_digest:
                continue
            preview.error(f"{previous_name} and {name} are both set to {kind} for {day}. "
                          "Choose one file or correct its type or date in Import options.")
            return
        seen[slot] = (name, digest)
        batches.setdefault(day.isoformat(), []).append((kind, digest, rows))
        if kind == db.WEEK:
            weekly_ids.append({r["id"] for r in rows})
        date_text = day.strftime("%d %b %Y")
        if detected_day is None and day == today:
            date_text += " (using today)"
        if len(files) > 1:
            preview.text(name)
        unit = "governor" if len(rows) == 1 else "governors"
        preview.write(f"**{kind}** · {date_text} · {len(rows):,} {unit}")
        if kind == db.LIFETIME and db.long_activity_period(name, frame):
            labels = " ".join([name, *frame.attrs.get("report_metadata", [])])
            if not db.ALL_TIME_LABEL.search(labels):
                preview.caption("This export spans more than a week. Import as all-time totals if it covers ODS1’s full history.")

    full = auto = False
    restore = True
    if weekly_ids:
        with options:
            selection = [(slot, digest) for slot, (_, digest) in seen.items()]
            option_key = hashlib.sha256(repr((generation, selection)).encode()).hexdigest()[:16]
            full = st.checkbox("Mark missing governors as having left (complete weekly rosters only)", key=f"full_{option_key}")
            restore = st.checkbox("Restore the saved rank for returners", value=True, key=f"restore_{option_key}")
            auto = st.checkbox("Apply suggested ranks on import", key=f"auto_{option_key}")
        if full and len(weekly_ids) == 1:
            leaving = sum(bool(r.get("in_active_126")) and r["id"] not in weekly_ids[0] for r in scored)
            preview.caption(f"{leaving} currently active governors are absent from this weekly file.")
        elif full:
            preview.caption("Each weekly file will be treated as a complete roster.")
    action.button("Import", type="primary", key="run_import", on_click=commit_import, args=(batches, full, restore, auto))


def briefing(scored, phase):
    active = [r for r in scored if r["in_active_126"]]
    parts = [f"ODS1 • Kingdom 4161 | {phase}", f"Weekly officer review · {len(active)} active governors", ""]
    for action in db.ACTIONS:
        names = sorted((r["name"] for r in active if r["action"] == action), key=str.casefold)
        parts.extend([f"{action} ({len(names)})", ", ".join(names) or "None", ""])
    return "\n".join(parts).strip()


def start_clean_reports():
    try:
        # Creating a separate roster leaves the previous reports available in the dashboard.
        db.change_records(lambda records: None, directory=db.CLEAN_DATA_DIR)
    except (OSError, ValueError, Timeout) as exc:
        st.session_state.import_error = str(exc)
    else:
        st.session_state.report_dataset = "Clean reports"
        st.session_state.import_generation = st.session_state.get("import_generation", 0) + 1
        st.session_state.notice = "Clean reports are ready. Upload last week's report first."


def officer_page(scored, records, preferred):
    title("Officer desk")
    mode = st.radio("Tools", ("Governor profile", "Import reports", "Leadership briefing"), horizontal=True, key="officer_mode")
    if mode == "Governor profile":
        member_detail(scored, preferred)
    elif mode == "Import reports":
        report_import(scored)
        if not (db.CLEAN_DATA_DIR / db.BASELINE).exists():
            with st.expander("Start fresh"):
                st.caption("Open an empty roster for new imports. You can reopen the previous roster from Review settings.")
                st.button("Start clean reports", on_click=start_clean_reports)
        with st.expander("Download current roster backup"):
            st.caption("This file includes officer notes and saved ranks. Keep a private copy after each review.")
            st.download_button("Download ods1_baseline.json", json.dumps(records, ensure_ascii=False, indent=2).encode(),
                               db.BASELINE, "application/json")
    else:
        report = briefing(scored, st.session_state.rules[0])
        st.code(report, language=None)
        st.download_button("Download leadership briefing", report, "ods1-leadership-briefing.txt", "text/plain")


def main():
    st.set_page_config(page_title="ODS1 · Alliance command", page_icon="♜", layout="wide", initial_sidebar_state="collapsed")
    html(CSS)
    clean_exists = (db.CLEAN_DATA_DIR / db.BASELINE).exists()
    dataset = "Previous roster"
    if clean_exists:
        dataset = st.sidebar.radio("Data set", ("Clean reports", "Previous roster"), key="report_dataset")
    directory = db.CLEAN_DATA_DIR if dataset == "Clean reports" else db.DATA_DIR
    st.session_state.data_directory = directory
    try:
        records, pending = db.load_live(directory)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        st.error(f"Could not load the ODS1 roster. {exc}")
        st.stop()
    with st.sidebar:
        st.header("Review settings")
        phase = st.radio("KvK stage", tuple(db.PHASES), key="phase")
        w1, w2 = db.PHASES[phase]
        st.caption(f"Overall score · {w1:.0%} support and {w2:.0%} KvK")
        with st.expander("Rank cutoffs"):
            cutoff = st.slider("R3 overall cutoff", 30.0, 75.0, 45.0, 1.0)
            specialist = st.slider("R3 support specialist", 40.0, 85.0, 55.0, 1.0)
            st.caption("R3 also qualifies at 75 KvK. R2 starts at 24 overall, 30 support or 40 KvK. R1 starts at 12 overall or 30 lifetime usefulness.")
    rules = (phase, cutoff, specialist)
    st.session_state.rules = rules
    scored = [{**r, **db.classify(r, rules), "held": db.saved_rank(r)} for r in records]
    latest = db.latest_week(records)
    label = (db.iso_day(latest).strftime("%d %b %Y") if latest and db.iso_day(latest) else ("No weekly reports" if clean_exists and dataset == "Clean reports" else "Saved baseline"))
    html('<div class="mast"><div class="identity"><div class="sigil" aria-hidden="true"><span>O1</span></div><div>'
         '<div class="overline">Odyssey 1 &nbsp; / &nbsp; Kingdom 4161</div><h1>Alliance command</h1></div></div>'
         f'<div class="stamp"><small>Roster source</small><strong>{esc(label)}</strong><span>{esc(phase)} · KvK 1</span></div></div>')
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    if pending:
        with st.expander(f"Repository imports needing review ({len(pending)})"):
            for item in pending:
                st.write(item)
    requested = st.query_params.get("governor", "")
    preferred = int(requested) if re.fullmatch(r"\d{1,18}", str(requested)) else None
    if preferred and st.session_state.get("opened_governor") != preferred and any(r["id"] == preferred for r in records):
        st.session_state.section = "Officer desk"
        st.session_state.officer_mode = "Governor profile"
        st.session_state.officer_governor = preferred
        st.session_state.opened_governor = preferred
    view = st.radio("Command navigation", VIEWS, horizontal=True, label_visibility="collapsed", key="section")
    if view == "Roster review":
        review_page(scored)
    elif view == "Overview":
        overview_page(scored)
    elif view == "Activity":
        activity_page(scored)
    elif view == "Leaderboards":
        leaderboards_page(scored)
    elif view == "KvK war":
        war_page(scored)
    elif view == "Rotations":
        rotations_page(scored)
    else:
        officer_page(scored, records, preferred)


if __name__ == "__main__":
    main()
