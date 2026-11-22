"""ODS1 Command Center. Start with streamlit run app.py from the repository."""
import hashlib
import json
import sqlite3
from collections import Counter
import re
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, JsCode
from filelock import Timeout

import roster as db
import fights
import membership
from review_rules import FORTS_PER_DAY


VIEWS = ("Roster review", "Overview", "Activity", "Leaderboards", "KvK war", "Rotations", "Officer desk")
MISSING_STATS = "Missing weekly stats"
REVIEW_FILTERS = (*db.ACTIONS, MISSING_STATS)
PRIORITY = {MISSING_STATS: 5, "Promote": 0, "Demote": 1, "Monitor / warn": 2, "Kick": 3, "Keep current rank": 4, "Review suggested rank": 2}
ACTION_STYLE = dict(zip(db.ACTIONS, ("keep", "promote", "demote", "monitor", "kick", "promote")))
ACTION_STYLE[MISSING_STATS] = "missing"
SHORT_ACTION = {"Keep current rank": "Keep", "Demote": "Demotion review", "Kick": "Kick review"}
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
    tag = db.badge(rec, db.report_today())
    return f"{rec['name']}  ·  {tag}" if tag else rec["name"]


def numbered_grid(frame, key, height=400, selectable=False, position_label="#"):
    frame = frame.rename(columns={"#": "Export rank"})
    position = {"headerName": position_label, "colId": "visiblePosition", "pinned": "left",
                "width": 75, "sortable": False, "filter": False, "lockPosition": True,
                "valueGetter": JsCode("function(p) { return p.node.rowIndex + 1; }")}
    options = {
        "columnDefs": [position, *({"field": field} for field in frame.columns)],
        "defaultColDef": {"sortable": True, "filter": True, "resizable": True, "width": 150},
        "onModelUpdated": JsCode("""function(p) {
            requestAnimationFrame(() => {
                if (!p.api.isDestroyed()) p.api.refreshCells({columns: ['visiblePosition'], force: true});
            });
        }"""),
    }
    if selectable:
        options["rowSelection"] = {"mode": "singleRow", "enableClickSelection": True, "checkboxes": False}
    return AgGrid(frame, gridOptions=options, key=key, height=height, allow_unsafe_jscode=True,
                  update_on=["selectionChanged"] if selectable else [])


def frame_table(rows, key, empty="No governors match this view."):
    if not rows:
        st.info(empty)
        return
    frame = pd.DataFrame(rows)
    position_label = "Place" if "Place" in frame else "#"
    numbered_grid(frame.drop(columns=["Place"], errors="ignore"), key, position_label=position_label)


def open_import():
    st.session_state.section = "Officer desk"
    st.session_state.officer_mode = "Import reports"


def review_page(scored):
    active = [r for r in scored if db.is_member(r)]
    counts = {action: sum(r["action"] == action for r in active) for action in REVIEW_FILTERS}
    scanned = any(r.get("membership_date") for r in scored)
    without_leader = sum(r.get("roster_rank") != "R5" for r in active)
    roster_detail = f"{without_leader} excluding the alliance leader" if scanned else "Latest weekly report"
    stats([("Active roster" if scanned else "Report participants", len(active), roster_detail),
           ("Rank suggestions", counts["Promote"] + counts["Demote"] + counts["Review suggested rank"], f'{counts["Promote"]} promote · {counts["Demote"]} demote · {counts["Review suggested rank"]} to review'),
           ("Check-ins", counts["Monitor / warn"], f'{counts[MISSING_STATS]} members missing weekly stats'),
           ("Kick review", counts["Kick"], "Officer decision required")])
    heading, upload = st.columns([4, 1])
    with heading:
        title("Weekly review", f"{len(active)} {'current members' if scanned else 'report participants'}")
    upload.button("Import reports", type="primary", on_click=open_import, key="open_import", use_container_width=True)
    week = db.latest_week(scored)
    if scanned and week:
        participants = {r["id"] for r in scored for h in r.get("history", [])
                        if h.get("date") == week and h.get("in_active")}
        matched = sum(r["id"] in participants for r in active)
        st.caption(f"{matched} of {len(active)} current members appear in the {db.iso_day(week):%b %d} activity report "
                   f"({len(participants)} governors in total).")
    with st.expander("How weekly reviews work"):
        st.write("Forts earn up to 15 support points, tech donations 35, building time 25 and helps 25. "
                 "Targets scale with the days in the report. An average of 10 forts per day earns 10 points and 15 earns all 15.")
        st.write("A governor can earn one rank increase per week. The promotion score uses support already earned toward seven-day "
                 "targets and gains in DKP, troops healed and acclaim between daily KvK scans in the report. "
                 "Support can qualify a member on its own. For a closed week, consecutive Sunday scans can also measure gains.")
        st.write("These exports omit normal barbarian kills. For a warning or demotion review, we check whether "
                 "the member would still fall below their rank with full fort credit. One low Monday–Sunday week "
                 "prompts a check-in. Two in a row prompt an officer review. Each week needs an activity row and a KvK scan "
                 "covering that member.")
    a, b, c, d = st.columns([2.1, 1.3, 1, 1])
    query = a.text_input("Find a governor", placeholder="Name, alias or Governor ID", key="review_search")
    action = b.selectbox("Decision", ("All decisions", *REVIEW_FILTERS), key="action_filter")
    rank = c.selectbox("Saved rank", ("All ranks", *db.RANKS, "Unrecorded"), key="rank_filter")
    target = d.selectbox("Suggested rank", ("All suggestions", *db.RANKS, "Kick"), key="target_filter")
    selected = [r for r in active if (target == "All suggestions" or r["proposed"] == target) and matches(r, query) and (action == "All decisions" or r["action"] == action)
                and (rank == "All ranks" or (r["held"] or "Unrecorded") == rank)]

    def review_order(rec):
        decision = rec["action"]
        score = rec["promotion_score"] if decision == "Promote" else rec["overall"]
        if decision in ("Promote", "Keep current rank"):
            score = -score
        return PRIORITY[decision], score, rec["name"].casefold(), rec["id"]

    selected.sort(key=review_order)
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
    showing_promotions = action == "Promote"
    score_label = "Promotion score" if showing_promotions else "Overall"
    rows = []
    for number, rec in enumerate(selected[start:start + 15], start=start + 1):
        joined = db.badge(rec, db.report_today())
        tag = f'<span class="join-tag">{esc(joined)}</span>' if joined else ""
        decision = rec["action"]
        decision_label = f'Suggest {rec["proposed"]}' if decision == "Review suggested rank" else SHORT_ACTION.get(decision, decision)
        value = rec["promotion_score"] if showing_promotions else rec["overall"]
        score = f"{value:.1f}" if rec.get("has_weekly_activity", True) else "—"
        rows.append(f'<tr><td class="pos">{number}.</td><td><a target="_self" href="?governor={int(rec["id"])}">{esc(rec["name"])}</a>{tag}</td>'
                    f'<td class="rank-pair">{esc(rec["held"] or "—")}<i>→</i>{esc(rec["proposed"] or "—")}</td>'
                    f'<td><span class="chip {ACTION_STYLE[decision]}">{esc(decision_label)}</span></td>'
                    f'<td class="score score-col">{score}</td><td class="reason reason-col">{esc(rec["reason"])}</td></tr>')
    html('<div class="council-wrap"><table class="council"><thead><tr><th class="pos">#</th><th>Governor</th>'
         f'<th>Saved → suggested</th><th>Decision</th><th class="score-col">{score_label}</th><th class="reason-col">Reason</th>'
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
                 "Overall": r["overall"] if r.get("has_weekly_activity", True) else None,
                 "Promotion score": r["promotion_score"],
                 "Support": r["support"] if r.get("has_weekly_activity", True) else None,
                 "KvK": r["war"], "Officer note": r.get("officer_note", "")}
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


def activity_members(records, key, period):
    weeks = db.history_labels(records)
    if key == "leaderboards" or st.checkbox("Current ODS1 members only", value=True, key="activity_current_only"):
        records = [r for r in records if db.is_member(r)]
    if period == "All-time":
        return 1, [(display_name(record), record["id"], record) for record in records]
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
    active = {r["id"]: r for r in scored if db.is_member(r)}
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
               "RokStats rank": r.get("roster_rank"), "Saved rank": r["held"], "Suggested rank": r["proposed"], "Decision": r["action"],
               "Power": r.get("power"), "Overall": r["overall"] if r.get("has_weekly_activity", True) else None,
               "Promotion score": r["promotion_score"],
               "Support": r["support"] if r.get("has_weekly_activity", True) else None, "KvK score": r["war"],
               "Officer note": r.get("officer_note"), "Excused": bool(r.get("is_excused"))}
        for metric, (weekly, lifetime) in ACTIVITY_FIELDS.items():
            row[f"Weekly · {metric}"] = activity_value(snapshot, weekly)
            row[f"All-time · {metric}"] = activity_value(r, lifetime)
        row.update({f"KvK · {metric.upper() if metric in ('kp', 'dkp') else metric.title()}": r.get(field)
                    for metric, field in db.WAR_METRICS.items()})
        row.update({f"KvK · {label}": r.get(field) for label, field in KVK_CHANGES.items()})
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
    result = numbered_grid(visible, f"overview_{table_key}", height=540, selectable=True)
    selected = result.selected_rows
    if selected is not None and not selected.empty:
        gid = int(selected.iloc[0]["Governor ID"])
        member_detail([active[gid]], gid, selected=active[gid])


def activity_page(scored):
    title("Alliance activity")
    period = st.radio("Period", ("Weekly", "All-time"), horizontal=True, key="activity_period")
    period, members = activity_members(scored, "activity", period)
    query = st.text_input("Find a governor", placeholder="Name or Governor ID", key="activity_search")
    fields = {label: columns[period] for label, columns in ACTIVITY_FIELDS.items() if columns[period]}
    frame_table([
        {"Governor": name, "Governor ID": gid,
         **{label: activity_value(entry, field) for label, field in fields.items()}}
        for name, gid, entry in members if query.strip().casefold() in f"{name} {gid}".casefold()
    ], "activity_table", empty="No activity rows in this report.")


KVK_CHANGES = {"DKP change": "dkp_change", "T4 kills change": "t4_change", "T5 kills change": "t5_change"}


def kvk_dates_caption(scan_dates):
    previous, latest = (db.iso_day(day) for day in scan_dates)
    if previous and latest:
        st.caption(f"Changes from {previous:%d %b %Y} to {latest:%d %b %Y}. A blank means a value is missing from one of the scans.")
    elif latest:
        st.caption(f"Latest scan · {latest:%d %b %Y}. Changes will appear after a second dated KvK scan.")


def leaderboards_page(scored, scan_dates):
    title("Leaderboards")
    period = st.radio("Leaderboard", ("Weekly", "All-time", "KvK performance"), horizontal=True, key="leaderboards_period")
    if period == "KvK performance":
        active = [r for r in scored if db.is_member(r)]
        fighters = [r for r in active if r.get("in_kvk_4161")]
        fields = {"KvK score / 100": "war", "DKP": "kvk_dkp", "DKP change": "dkp_change",
                  "T4 kills": "kvk_t4", "T4 kills change": "t4_change",
                  "T5 kills": "kvk_t5", "T5 kills change": "t5_change", "Kill points": "kvk_kp", "Dead": "kvk_dead",
                  "Healed": "kvk_healed", "Acclaim": "kvk_acclaim"}
        metric = st.selectbox("Rank by", list(fields), key="kvk_leaderboard_metric")
        field = fields[metric]
        ranked = sorted((r for r in fighters if r.get(field) is not None),
                        key=lambda r: (-db.n(r[field]), -db.n(r.get("kvk_dkp")), r["id"]))
        st.caption(f"{len(fighters)} of {len(active)} current members matched to KvK records · Ties sorted by DKP, then Governor ID.")
        kvk_dates_caption(scan_dates)
        st.button("Open fight summaries", on_click=open_fights, key="leaderboard_fights")
        frame_table([
            {"Place": place, "Governor": r["name"], metric: r[field],
             **{label: r.get(column) for label, column in fields.items() if column != field},
             "Governor ID": r["id"]}
            for place, r in enumerate(ranked, 1)
        ], "kvk_leaderboard", empty=f"No current members have a recorded value for {metric}.")
        return
    period, members = activity_members(scored, "leaderboards", period)
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


def open_fights():
    st.session_state.section = "KvK war"
    st.session_state.war_view = "Fight summaries"


def fight_page(scored):
    directory = st.session_state.data_directory
    if not any(r.get("membership_date") for r in scored):
        st.info("Import an ODS1 Members scan to see fight results for the current alliance roster.")
        st.button("Import reports", on_click=open_import, key="fight_members_import")
        return
    try:
        scans, saved = fights.catalog(scored, directory)
    except (OSError, ValueError, sqlite3.Error) as exc:
        st.error(f"Could not open the fight archive. {exc}")
        return
    ends = [key for key, scan in scans.items() if any(fights.precedes(s.stamp, scan.stamp) for s in scans.values())]
    if not ends:
        st.info("Import two KvK exports taken before and after the fight. For two scans on the same day, include both capture times.")
        st.button("Import reports", on_click=open_import, key="fight_scans_import")
        return

    counts = Counter(s.stamp for s in scans.values())
    def label(key):
        stamp = scans[key].stamp
        suffix = f" · {key[-6:]}" if counts[stamp] > 1 else ""
        return fights.scan_label(stamp) + suffix

    prefix = f"fight_{directory}"
    key = prefix + "_choice"
    if opened := st.session_state.pop(prefix + "_saved", None):
        st.session_state[key] = opened
    name = st.selectbox("Fight", [None, *saved], format_func=lambda v: v or "Choose scans", key=key)
    if name is not None:
        start, end = saved[name]
        st.caption(f"{label(start)} → {label(end)}")
    else:
        left, right = st.columns(2)
        end = right.selectbox("After the fight", ends, index=len(ends) - 1, format_func=label, key=prefix + "_end")
        starts = [k for k, s in scans.items() if fights.precedes(s.stamp, scans[end].stamp)]
        start = left.selectbox("Before the fight", starts, index=len(starts) - 1, format_func=label, key=prefix + "_start")

    rows = fights.summary(scored, scans[start], scans[end])
    fields = {"DKP gained": "dkp_change", "T4 kills gained": "t4_change", "T5 kills gained": "t5_change"}
    matched = sum(row["in_both"] for row in rows)
    cards = []
    for heading, field in fields.items():
        values = [row[field] for row in rows if row[field] is not None]
        cards.append((heading, f"{sum(values):,.0f}" if values else "—", f"{len(values)} members with both readings"))
    stats([*cards, ("In both scans", f"{matched}/{len(rows)}", "Current ODS1 members")])
    st.caption("Gains cover all activity between the two scans. A blank means a reading is missing.")
    metric = st.selectbox("Rank fight by", list(fields), key=prefix + "_metric")
    field = fields[metric]
    ranked = sorted(rows, key=lambda r: (r[field] is None, -db.n(r[field]), r["dkp_change"] is None,
                                        -db.n(r["dkp_change"]), r["id"]))
    table = [{"Governor": r["name"], metric: r[field], **{col: r[k] for col, k in fields.items() if k != field},
              "Governor ID": r["id"]} for r in ranked]
    frame_table([dict(row, Place=i) for i, row in enumerate(table, 1)], f"fight_results_{field}_{start}_{end}")
    export = pd.DataFrame(table).assign(Fight=name or "", **{"Before scan": scans[start].stamp, "After scan": scans[end].stamp})
    st.download_button("Download fight CSV", export.to_csv(index=False).encode("utf-8-sig"),
                       f"ODS1-fight-{scans[start].stamp.replace(':', '')}_{scans[end].stamp.replace(':', '')}.csv", "text/csv")
    if name is None:
        with st.form(prefix + "_save"):
            entered = st.text_input("Fight name", placeholder="Pass 4 opening", max_chars=80)
            submit = st.form_submit_button("Save fight")
        if submit:
            try:
                name = fights.save_fight(directory, entered, scans[start], scans[end])
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(str(exc))
            else:
                st.session_state[prefix + "_saved"] = name
                st.session_state.notice = f"Saved {name} with these two scans."
                st.rerun()


def war_page(scored, scan_dates):
    fighters = [r for r in scored if db.is_member(r) and r.get("in_kvk_4161")]
    title("KvK war", "Kingdom 4161")
    view = st.radio("War view", ("Kingdom totals", "Fight summaries"), horizontal=True, key="war_view")
    if view == "Fight summaries":
        fight_page(scored)
        return
    stats([("Tracked fighters", len(fighters), "Current ODS1 members"),
           ("Combined DKP", compact(sum(db.n(r.get("kvk_dkp")) for r in fighters)), "Current members in the KvK report"),
           ("Kill points", compact(sum(db.n(r.get("kvk_kp")) for r in fighters)), "Recorded in the KvK export"),
           ("Troops healed", compact(sum(db.n(r.get("kvk_healed")) for r in fighters)), "Recorded in the KvK export")])
    kvk_dates_caption(scan_dates)
    query = st.text_input("Find a fighter", placeholder="Name, alias or ID", key="war_search")
    fighters = sorted((r for r in fighters if matches(r, query)), key=lambda r: (-db.n(r.get("kvk_dkp")), r["id"]))
    frame_table([{"Governor": display_name(r), "KD rank": r.get("kd_rank"), "KvK / 100": r["war"], "DKP": r.get("kvk_dkp"),
                  "DKP change": r["dkp_change"], "T4 kills": r.get("kvk_t4"), "T4 kills change": r["t4_change"],
                  "T5 kills": r.get("kvk_t5"), "T5 kills change": r["t5_change"],
                  "Kill points": r.get("kvk_kp"), "Power": r.get("power"), "Healed": r.get("kvk_healed"),
                  "Acclaim": r.get("kvk_acclaim"), "Status": r.get("status")} for r in fighters], "war_table")


def snapshot_rows(records, label):
    rows = []
    for rec in records:
        entry = next((h for h in rec.get("history", []) if h.get("date") == label), None)
        if entry is None:
            continue
        rows.append({"Governor": entry.get("name") or f'ID {rec["id"]}', "Governor ID": rec["id"],
                     "In weekly report": bool(entry.get("in_active")), "Saved rank": entry.get("rank"),
                     "Prior rank": entry.get("last_active_rank"), "Overall": entry.get("overall_score"),
                     "Support": entry.get("ods1_usefulness"), "KvK": entry.get("kvk_score"), "Forts": entry.get("forts_7d"),
                     "Tech points": entry.get("tech_7d"), "DKP": entry.get("kvk_dkp")})
    return sorted(rows, key=lambda r: (not r["In weekly report"], -(r["Overall"] if r["Overall"] is not None else -1), r["Governor ID"]))


def rotations_page(scored):
    title("Rotations & history")
    mode = st.radio("Show", ("Rotated out", "Departed", "Movement log", "Past reports", "Export archive", "Former names"), horizontal=True)
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
    elif mode == "Export archive":
        directory = st.session_state.data_directory
        folders = [directory / "archive"]
        if directory == db.DATA_DIR:
            folders.insert(0, db.REPO_DATA_DIR / "archive")
        paths = {path.name: path for folder in folders for path in folder.glob("*.csv")}
        paths.update({p.name: p for p in db.repository_reports(directory)
                      if p.suffix.lower() == ".csv" and p.name.startswith(("ODS1-", "Kingdom-4161-KvK-"))
                      and db.report_date_in_name(p.name)})
        if not paths:
            st.info("No historical exports in this data set.")
            return
        ordered = sorted(paths, key=lambda n: (db.report_date_in_name(n) or db.date.min, n), reverse=True)
        name = st.selectbox("Historical export", ordered, format_func=lambda n: n[:-4]
                            .replace("-complete-weekly-", "-weekly-").replace("_to_", " to ").replace("_", " · "))
        path = paths[name]
        info = path.stat()
        frame = overview_export(path, info.st_mtime_ns, info.st_size)
        total = len(frame)
        if st.checkbox("Current ODS1 members only", value=True):
            frame = frame.loc[frame.index.isin(r["id"] for r in scored if db.is_member(r))]
        if query.strip():
            names = frame["Player"] if "Player" in frame else frame["Governor Name"]
            term = query.strip().casefold()
            frame = frame.loc[[gid for gid, player in names.items() if term in f"{player} {gid}".casefold()]]
        st.caption(f"{len(frame):,} of {total:,} governors · Dates and times identify individual exports.")
        numbered_grid(frame.reset_index(), f"archive_{name}", height=520)
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
        rows = [r for r in members if not db.is_member(r) and bool(r.get("in_kvk_4161")) == (mode == "Rotated out")]
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
    tag = db.badge(rec, db.report_today())
    observed = f' · RokStats <b>{esc(rec["roster_rank"])}</b>' if rec.get("roster_rank") else ""
    html(f'<div class="profile"><div class="subhead">{esc(db.bucket_status(rec))}</div>'
         f'<strong>{esc(rec["name"])} {f"<small class=join-tag>{esc(tag)}</small>" if tag else ""}</strong>'
         f'<p>Saved rank <b>{esc(rec["held"] or "Unrecorded")}</b>{observed} · Previous <b>{esc(db.former_rank(rec) or "Unrecorded")}</b>'
         f' · Suggested <b>{esc(rec["proposed"] or "—")}</b></p><p>{esc(rec["reason"])}</p></div>')
    has_week = rec.get("has_weekly_activity", True)
    stats([("Overall", f'{rec["overall"]:.1f}' if has_week else "—", "Score out of 100"),
           ("Support", f'{rec["support"]:.1f}' if has_week else "—", "Alliance usefulness"),
           ("KvK", f'{rec["war"]:.1f}', "War contribution"), ("Power", compact(db.n(rec.get("power"))), "Recorded power")])
    end = db.iso_day(rec.get("last_weekly_report"))
    if has_week and end and rec.get("forts_7d") is not None:
        start = db.iso_day(rec.get("week_start")) or db.monday(end)
        cap = ((end - start).days + 1) * FORTS_PER_DAY
        st.caption(f"{start:%d %b}–{end:%d %b} · {db.n(rec['forts_7d']):g} forts recorded · {cap} earns full fort credit (15 support points).")
    report_days = [day for h in rec.get("history", []) if h.get("in_active")
                   and (day := db.iso_day(h.get("date")))]
    first_report = min(report_days).strftime("%d %b %Y") if report_days else "No weekly record"
    joined = db.iso_day(rec.get("joined_date"))
    st.caption(f"Earliest weekly report (end date) · {first_report} · Alliance join date: "
               f"{joined.strftime('%d %b %Y') if joined else 'Unknown'}")
    expected_key = f"seen_officer_{gid}"
    expected = st.session_state.setdefault(expected_key, db.officer_values(rec))
    with st.form(f"officer_form_{gid}"):
        choices = (None, *(db.RANKS if rec.get("roster_rank") or gid not in db.COMMAND else (db.COMMAND[gid][0],)))
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
            db.change_records(lambda records: db.save_officer(records, gid, override, note, excused, expected, scanned_rank=rec.get("roster_rank")),
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
            rows.append({"Report": h.get("date"), "In weekly report": h.get("in_active"), "Saved rank": h.get("rank"),
                         "Overall": score, "Change": delta, "Support": h.get("ods1_usefulness"), "KvK": h.get("kvk_score")})
            prior = score
        frame_table(list(reversed(rows)), "governor_history")


def commit_import(batches, full, restore, auto, member_scan=None, captures=()):
    messages = []
    try:
        directory = st.session_state.data_directory
        if member_scan is not None:
            messages.append(membership.save(member_scan, *db.membership_folders(directory)))
        if batches or captures:
            messages.append(fights.import_reports(directory, batches, captures, full, st.session_state.rules, restore, auto))
    except db.OlderReports as exc:
        st.session_state.import_info = str(exc)
    except (ValueError, OSError, sqlite3.Error, Timeout) as exc:
        st.session_state.import_error = str(exc)
    else:
        st.session_state.import_generation = st.session_state.get("import_generation", 0) + 1
    if messages:
        st.session_state.notice = "  \n".join(messages)


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
    with st.expander("Scan current members"):
        st.write("Add the scanner bookmark to your browser once. On the ODS1 Members page, click the bookmark and drop its CSV above.")
        st.download_button("Download bookmark setup", Path(__file__).with_name("roster-scanner.html").read_bytes(),
                           "ODS1-roster-scanner.html", "text/html")
        st.link_button("Open ODS1 Members", membership.MEMBERS_URL)
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
    grouped = {}
    using_today = set()
    weekly_ids = []
    captures = []
    member_scan = None
    today = db.report_today()
    for idx, (name, data) in enumerate(files):
        try:
            if name.lower().startswith("ods1-members-") or data[:40].decode("utf-8-sig", errors="ignore").lstrip('"').startswith("ODS1 Members"):
                if member_scan is not None and member_scan != data:
                    raise ValueError("Choose one current member scan for this import.")
                captured, members = membership.parse(data)
                member_scan = data
                preview.write(f"**Current ODS1 members** · {captured:%d %b %Y} · {len(members):,} governors")
                continue
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
                kind = left.selectbox("Report type", db.REPORT_TYPES, index=db.REPORT_TYPES.index(guess), key=f"kind_{key}",
                                      format_func=lambda k: "Weekly ODS1 activity" if k == db.WEEK else k)
                day = right.date_input("Report end date", value=detected_day or today, key=f"date_{key}") or detected_day or today
                start = stamp = None
                if kind == db.WAR:
                    clock = st.text_input("Scan time (optional)", value=db.kvk_filename_time(name), key=f"clock_{key}",
                                          placeholder="HH:MM:SS", help="Uses the time in the export filename. Same-day fight comparisons need both times.")
                    stamp = fights.scan_stamp(day, clock)
                if kind == db.WEEK:
                    start = st.date_input("Weekly report starts", value=db.detect_week_start(name, frame, day),
                                          key=f"start_{key}_{day}", help="Defaults to Monday when the export only gives an end date.")
            if day > today:
                raise ValueError(f"{name} is dated {day}, which is in the future. Check the date in Import options.")
            rows = db.report_data(name, frame, kind, end=day, start=start)
        except (ValueError, OSError, ImportError) as exc:
            preview.error(str(exc))
            return

        slot = (day.isoformat(), kind, stamp)
        grouped.setdefault(slot, {}).setdefault(digest, (name, rows))
        if detected_day is None and day == today:
            using_today.add(slot)
        if kind == db.LIFETIME and db.long_activity_period(name, frame):
            labels = " ".join([name, *frame.attrs.get("report_metadata", [])])
            if not db.ALL_TIME_LABEL.search(labels):
                preview.caption("This export spans more than a week. Import as all-time totals if it covers ODS1’s full history.")

    for (end, kind, stamp), parts in grouped.items():
        try:
            if kind == db.WAR and len(parts) > 1:
                raise ValueError("These KvK exports have the same scan time. Set their capture times in Import options or choose one export.")
            digest, rows = db.combine_report_files(kind, parts)
        except ValueError as exc:
            preview.error(str(exc))
            return
        if kind == db.WAR:
            captures.append((stamp, digest, rows))
        else:
            batches.setdefault(end, []).append((kind, digest, rows))
        if kind == db.WEEK:
            weekly_ids.append({r["id"] for r in rows})
        date_text = db.iso_day(end).strftime("%d %b %Y")
        if kind == db.WEEK:
            start = db.iso_day(rows[0]["week_start"])
            date_text = f"{start:%d %b} – {date_text} · {(db.iso_day(end) - start).days + 1} days"
        if kind == db.WAR:
            date_text = fights.scan_label(stamp)
        if (end, kind, stamp) in using_today:
            date_text += " (using today)"
        unit = "governor" if len(rows) == 1 else "governors"
        report_label = "Weekly ODS1 activity" if kind == db.WEEK else kind
        preview.write(f"**{report_label}** · {date_text} · {len(rows):,} {unit}")
        if kind == db.WEEK and rows[0].get("week_open"):
            preview.caption("Sunday was still in progress at export. This report can update scores and rankings. A completed week is needed for a rank warning.")
        if len(parts) == 2:
            preview.caption("Basic and Advanced matched by Governor ID.")

    full = auto = False
    restore = True
    if weekly_ids:
        with options:
            selection = sorted((slot, sorted(parts)) for slot, parts in grouped.items())
            option_key = hashlib.sha256(repr((generation, selection)).encode()).hexdigest()[:16]
            full = st.checkbox("Replace the participant list for each complete weekly report", key=f"full_{option_key}")
            restore = st.checkbox("Restore prior report ranks for returning participants", value=True, key=f"restore_{option_key}")
            if member_scan is None and not any(r.get("membership_date") for r in scored):
                auto = st.checkbox("Apply promotions and fill unrecorded ranks on import", key=f"auto_{option_key}")
        if full and len(weekly_ids) == 1:
            leaving = sum(bool(r.get("in_active_126")) and r["id"] not in weekly_ids[0] for r in scored)
            preview.caption(f"{leaving} previous activity participants are absent from this weekly file.")
        elif full:
            preview.caption("Each weekly file supplies a complete activity participant list.")
    action.button("Import", type="primary", key="run_import", on_click=commit_import, args=(batches, full, restore, auto, member_scan, captures))


def briefing(scored, phase):
    active = [r for r in scored if db.is_member(r)]
    parts = [f"ODS1 • Kingdom 4161 | {phase}", f"Weekly officer review · {len(active)} active governors", ""]
    for action in REVIEW_FILTERS:
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
            st.caption("Promotion cutoffs use earned weekly support and measured KvK gains. The main KvK score uses season totals.")
    rules = (phase, cutoff, specialist)
    st.session_state.rules = rules
    previous_scan, latest_scan, changes = db.kvk_comparison(records)
    scored = []
    for rec in records:
        result = db.classify(rec, rules)
        if rec.get("has_weekly_activity") is False and result["action"] == "Monitor / warn" and not rec.get("is_excused"):
            result["action"] = MISSING_STATS
        scored.append({**rec, **result, **changes[rec["id"]], "held": db.saved_rank(rec)})
    latest = db.latest_week(records)
    membership_day = next((r["membership_date"] for r in records if r.get("membership_date")), None)
    source_day = db.iso_day(membership_day or latest)
    label = source_day.strftime("%d %b %Y") if source_day else "No dated report"
    html('<div class="mast"><div class="identity"><div class="sigil" aria-hidden="true"><span>O1</span></div><div>'
         '<div class="overline">Odyssey 1 &nbsp; / &nbsp; Kingdom 4161</div><h1>Alliance command</h1></div></div>'
         f'<div class="stamp"><small>{"ODS1 Members scan" if membership_day else "Weekly activity"}</small><strong>{esc(label)}</strong><span>{esc(phase)} · KvK 1</span></div></div>')
    if records and not membership_day:
        st.info("This data set shows weekly report participants. Upload an ODS1 Members scan to verify current membership.")
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
        leaderboards_page(scored, (previous_scan, latest_scan))
    elif view == "KvK war":
        war_page(scored, (previous_scan, latest_scan))
    elif view == "Rotations":
        rotations_page(scored)
    else:
        officer_page(scored, records, preferred)


if __name__ == "__main__":
    main()
