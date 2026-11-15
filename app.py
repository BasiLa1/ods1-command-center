import json
import os
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="ODS1 Command Center | KD 4161 KvK 1",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main { background-color: #0b1120; color: #f8fafc; }
    .stApp { background-color: #0b1120; color: #f8fafc; }
    [data-testid="stSidebar"] { background-color: #0f172a; border-right: 1px solid #1e293b; }
    .metric-card {
        background: linear-gradient(145deg, #111827, #1e293b);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 14px 16px;
        margin-bottom: 8px;
    }
    .metric-label { font-size: 0.78rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { font-size: 1.5rem; font-weight: 700; color: #fbbf24; margin-top: 2px; }
    .metric-sub { font-size: 0.78rem; color: #cbd5e1; margin-top: 2px; }
</style>
""", unsafe_allow_html=True)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
BASELINE_PATH = os.path.join(DATA_DIR, "ods1_baseline.json")
STATE_PATH = os.path.join(DATA_DIR, "ods1_persistent_state.json")

DEFAULT_R5_IDS = {
    233428447: "R5 (Leader)",
    233185199: "R4 (Counselor / R5)",
}

DEFAULT_R4_IDS = {
    233184542: "R4 (Warlord)",
    233184517: "R4 (Envoy)",
    233190616: "R4 (Officer)",
    233196311: "R4 (Officer)",
    233183034: "R4 (Officer)",
    233183356: "R4 (Officer)",
}


def load_baseline_records() -> list:
    if os.path.exists(BASELINE_PATH):
        with open(BASELINE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def load_persistent_state() -> dict:
    default_state = {
        "custom_ranks": {},
        "excused_ids": [],
        "notes": {},
        "snapshots": [],
    }
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                default_state.update(loaded)
        except Exception:
            pass
    return default_state


def save_persistent_state(state: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def merge_uploaded_files(base_records: list, uploaded_files: list) -> list:
    by_id = {int(r["id"]): dict(r) for r in base_records}

    alliance_dfs = []
    kvk_dfs = []

    for uf in uploaded_files:
        try:
            xls = pd.ExcelFile(uf)
            sheet_name = "Data" if "Data" in xls.sheet_names else xls.sheet_names[0]
            df = pd.read_excel(uf, sheet_name=sheet_name)
        except Exception as e:
            st.error(f"Failed to read {uf.name}: {e}")
            continue

        cols = set(df.columns)
        if "Alliance helps" in cols and "Forts destroyed" in cols:
            alliance_dfs.append((uf.name, df))
        elif "Governor ID" in cols and ("DKP" in cols or "KP" in cols):
            kvk_dfs.append((uf.name, df))

    for _, df in alliance_dfs:
        is_alltime = len(df) > 180 or ("Usefulness Score" in df.columns and "Activity points" not in df.columns and len(df) >= 200)
        for _, row in df.iterrows():
            raw_id = row.get("ID")
            if pd.isna(raw_id):
                continue
            gov_id = int(raw_id)
            if gov_id not in by_id:
                by_id[gov_id] = {
                    "id": gov_id,
                    "name": str(row.get("Player", f"Gov-{gov_id}")).strip(),
                    "aliases": [],
                    "status": "Active in ODS1",
                    "in_active_126": True,
                    "in_kvk_4161": False,
                    "is_new_joiner": True,
                    "power": float(row.get("Power", 0) or 0),
                    "forts_7d": 0, "forts_all": 0,
                    "tech_7d": 0, "tech_all": 0,
                    "helps_7d": 0, "helps_all": 0,
                    "rss_7d": 0, "rss_all": 0,
                    "build_7d": 0, "build_all": 0,
                    "rok_use_7d": 0, "rok_use_all": 0,
                    "rok_act_7d": 0.0,
                    "kvk_kp": 0.0, "kvk_dkp": 0.0, "kvk_t4": 0.0, "kvk_t5": 0.0,
                    "kvk_dead": 0.0, "kvk_healed": 0.0, "kvk_acclaim": 0.0, "kvk_trades": 0.0,
                    "kd_rank": None, "camp_rank": None, "pwr_diff": 0.0,
                }

            rec = by_id[gov_id]
            p_name = str(row.get("Player", rec["name"])).strip()
            if p_name and p_name != rec["name"]:
                aliases = set(rec.get("aliases", []))
                if rec["name"] and rec["name"] != p_name:
                    aliases.add(rec["name"])
                aliases.discard(p_name)
                rec["aliases"] = sorted(list(aliases))
                rec["name"] = p_name

            if is_alltime:
                rec["forts_all"] = int(row.get("Forts destroyed", rec["forts_all"]) or 0)
                rec["tech_all"] = int(row.get("Technology points", rec["tech_all"]) or 0)
                rec["helps_all"] = int(row.get("Alliance helps", rec["helps_all"]) or 0)
                rec["rss_all"] = int(row.get("Resource assistance", rec["rss_all"]) or 0)
                rec["build_all"] = int(row.get("Building time (seconds)", rec["build_all"]) or 0)
                if "Usefulness Score" in row and pd.notna(row["Usefulness Score"]):
                    rec["rok_use_all"] = int(row["Usefulness Score"])
                if pd.notna(row.get("Last login")):
                    rec["last_login"] = str(row["Last login"])
            else:
                rec["in_active_126"] = True
                rec["status"] = "Active in ODS1"
                rec["power"] = float(row.get("Power", rec["power"]) or 0)
                rec["forts_7d"] = int(row.get("Forts destroyed", 0) or 0)
                rec["tech_7d"] = int(row.get("Technology points", 0) or 0)
                rec["helps_7d"] = int(row.get("Alliance helps", 0) or 0)
                rec["rss_7d"] = int(row.get("Resource assistance", 0) or 0)
                rec["build_7d"] = int(row.get("Building time (seconds)", 0) or 0)
                if "Activity points" in row and pd.notna(row["Activity points"]):
                    rec["rok_act_7d"] = float(row["Activity points"])
                if "Usefulness Score" in row and pd.notna(row["Usefulness Score"]):
                    rec["rok_use_7d"] = int(row["Usefulness Score"])
                if pd.notna(row.get("Last login")):
                    rec["last_login"] = str(row["Last login"])

    for _, df in kvk_dfs:
        df_sorted = df.reset_index(drop=True).copy()
        df_sorted["KD_Rank_Calc"] = np.arange(1, len(df_sorted) + 1)
        kvk_lookup = {}
        for _, row in df_sorted.iterrows():
            raw_gid = row.get("Governor ID")
            if pd.notna(raw_gid):
                kvk_lookup[int(raw_gid)] = row

        for gov_id, rec in by_id.items():
            if gov_id in kvk_lookup:
                krow = kvk_lookup[gov_id]
                rec["in_kvk_4161"] = True
                rec["kd_rank"] = int(krow["KD_Rank_Calc"])
                rec["camp_rank"] = int(krow["#"]) if "#" in krow and pd.notna(krow["#"]) else None
                rec["pwr_diff"] = float(krow.get("Power Diff", 0) or 0)
                rec["kvk_kp"] = float(krow.get("KP", 0) or 0)
                rec["kvk_t4"] = float(krow.get("T4", 0) or 0)
                rec["kvk_t5"] = float(krow.get("T5", 0) or 0)
                rec["kvk_dead"] = float(krow.get("Dead", 0) or 0)
                rec["kvk_dead_t4"] = float(krow.get("Dead T4", 0) or 0)
                rec["kvk_dead_t5"] = float(krow.get("Dead T5", 0) or 0)
                rec["kvk_healed"] = float(krow.get("Healed", 0) or 0)
                rec["kvk_acclaim"] = float(krow.get("Acclaim", 0) or 0)
                rec["kvk_dkp"] = float(krow.get("DKP", 0) or 0)
                rec["kvk_trades"] = float(krow.get("Trades", 0) or 0)
                if not rec.get("in_active_126"):
                    rec["power"] = float(krow.get("Power", rec["power"]) or 0)
                    rec["status"] = "Rotated Out (In KD 4161)"
                gname = str(krow.get("Governor Name", "")).strip()
                if gname and gname != rec["name"]:
                    aliases = set(rec.get("aliases", []))
                    if rec["name"]:
                        aliases.add(rec["name"])
                    aliases.discard(gname)
                    rec["aliases"] = sorted(list(aliases))
                    rec["name"] = gname

    return list(by_id.values())


def score_and_classify(records: list, state: dict, phase_mode: str, r3_cutoff: float, spec_threshold: float, auto_update_ranks: bool) -> pd.DataFrame:
    if phase_mode == "Early KvK (Day 8 - Forts/Flags Heavy)":
        w_use, w_kvk = 0.55, 0.45
    elif phase_mode == "Mid KvK (Pass Skirmishes)":
        w_use, w_kvk = 0.45, 0.55
    else:
        w_use, w_kvk = 0.30, 0.70

    custom_ranks = state.get("custom_ranks", {})
    excused_set = set(int(x) for x in state.get("excused_ids", []))
    notes_map = state.get("notes", {})

    rows = []
    for r in records:
        gov_id = int(r["id"])
        str_id = str(gov_id)
        in_active = bool(r.get("in_active_126", False))
        in_kvk = bool(r.get("in_kvk_4161", False))
        power = float(r.get("power", 0) or 0)
        forts_7d = int(r.get("forts_7d", 0) or 0)
        tech_7d = int(r.get("tech_7d", 0) or 0)
        helps_7d = int(r.get("helps_7d", 0) or 0)
        build_7d = int(r.get("build_7d", 0) or 0)
        forts_all = int(r.get("forts_all", 0) or 0)
        kvk_dkp = float(r.get("kvk_dkp", 0) or 0)
        kvk_kp = float(r.get("kvk_kp", 0) or 0)
        kvk_healed = float(r.get("kvk_healed", 0) or 0)
        kvk_acclaim = float(r.get("kvk_acclaim", 0) or 0)
        rok_use_all = int(r.get("rok_use_all", 0) or 0)
        is_new = bool(in_active and forts_all == forts_7d and tech_7d == int(r.get("tech_all", 0) or 0) and helps_7d == int(r.get("helps_all", 0) or 0))

        if in_active:
            s_forts = min(forts_7d / 100.0, 1.0) * 40.0
            s_tech = min(tech_7d / 75000.0, 1.0) * 25.0
            s_build = min(build_7d / 60000.0, 1.0) * 20.0
            s_helps = min(helps_7d / 2000.0, 1.0) * 15.0
            use_score = round(s_forts + s_tech + s_build + s_helps, 1)
        else:
            use_score = float(rok_use_all)

        pwr_m = power / 1e6
        if pwr_m < 12.0:
            t_ratio = 0.08
        elif pwr_m <= 20.0:
            t_ratio = 0.12
        else:
            t_ratio = 0.18
        ratio = (kvk_dkp / power) if power > 0 else 0.0
        r_score = min(ratio / t_ratio, 1.0) * 75.0
        h_bonus = min(kvk_healed / 350000.0, 1.0) * 15.0
        a_bonus = min(kvk_acclaim / 35000.0, 1.0) * 10.0
        kvk_score = round(min(r_score + h_bonus + a_bonus, 100.0), 1)

        vet_bonus = min(forts_all / 500.0, 1.0) * 5.0
        overall = round(min((w_use * use_score) + (w_kvk * kvk_score) + vet_bonus, 100.0), 1)

        is_excused = gov_id in excused_set
        is_specialist = (use_score >= spec_threshold) or (kvk_score >= spec_threshold)

        if gov_id in DEFAULT_R5_IDS:
            rec_rank = "R5"
            bucket = "Leadership (R5/R4)"
            reason = DEFAULT_R5_IDS[gov_id]
        elif gov_id in DEFAULT_R4_IDS:
            rec_rank = "R4"
            bucket = "Leadership (R5/R4)"
            reason = DEFAULT_R4_IDS[gov_id]
        elif not in_active:
            if in_kvk and (rok_use_all >= 10 or kvk_dkp >= 500000 or "ᴼᴰ" in str(r.get("name", "")) or "OD" in str(r.get("name", ""))):
                rec_rank = "R3" if kvk_dkp >= 1500000 else "R2"
                bucket = "Rotated Out (Active KD)"
                reason = "Rotated out of ODS1; active in KD 4161"
            else:
                rec_rank = "Left"
                bucket = "Departed / Left"
                reason = "Not in active ODS1 scan or KD 4161 leaderboard"
        else:
            if is_excused:
                rec_rank = custom_ranks.get(str_id, "R2")
                bucket = "Excused (Protected)"
                reason = "Excused absence / rebuild protection"
            elif is_specialist or overall >= r3_cutoff:
                rec_rank = "R3"
                bucket = "Promote / Keep R3"
                reason = "Specialist Immunity" if (is_specialist and overall < r3_cutoff) else "Top-Tier Active Core"
            elif overall >= 32.0 or use_score >= 48.0 or kvk_score >= 50.0:
                rec_rank = "R2"
                bucket = "Keep (R2 Core)"
                reason = "Solid steady contributor"
            elif overall >= 16.0 or rok_use_all >= 30:
                rec_rank = "R1"
                bucket = "Monitor / Warn (R1)"
                reason = "Veteran slump — check in" if rok_use_all >= 30 else "Below standard — monitor/warn"
            else:
                rec_rank = "Kick"
                bucket = "Kick Candidate"
                reason = "Low Usefulness & low KvK output"

        saved_rank = custom_ranks.get(str_id)
        if auto_update_ranks:
            active_rank = rec_rank
            custom_ranks[str_id] = rec_rank
        else:
            active_rank = saved_rank if saved_rank else rec_rank

        rows.append({
            **r,
            "id": gov_id,
            "power": power,
            "forts_7d": forts_7d,
            "tech_7d": tech_7d,
            "helps_7d": helps_7d,
            "build_7d": build_7d,
            "build_hrs_7d": round(build_7d / 3600.0, 2),
            "forts_all": forts_all,
            "kvk_dkp": kvk_dkp,
            "kvk_kp": kvk_kp,
            "kvk_healed": kvk_healed,
            "kvk_acclaim": kvk_acclaim,
            "dkp_ratio": round(ratio, 4),
            "ods1_usefulness": use_score,
            "kvk_score": kvk_score,
            "overall_score": overall,
            "is_specialist": is_specialist,
            "is_excused": is_excused,
            "is_new_joiner": is_new,
            "recommended_rank": rec_rank,
            "rank": active_rank,
            "bucket": bucket,
            "reason": reason,
            "alias_str": ", ".join(r.get("aliases", [])),
            "officer_note": notes_map.get(str_id, ""),
        })

    df_out = pd.DataFrame(rows)
    return df_out.sort_values(by=["overall_score", "kvk_dkp"], ascending=[False, False]).reset_index(drop=True)


def build_discord_briefing(df: pd.DataFrame, phase_mode: str) -> str:
    active = df[df["in_active_126"]]
    r3_list = active[active["rank"] == "R3"]["name"].tolist()
    warn_list = active[active["bucket"] == "Monitor / Warn (R1)"]["name"].tolist()
    kick_list = active[active["bucket"] == "Kick Candidate"]["name"].tolist()
    rot_list = df[df["bucket"] == "Rotated Out (Active KD)"].sort_values(by="kvk_dkp", ascending=False)["name"].head(12).tolist()

    lines = [
        f"**ODS1 (KD 4161) — KvK 1 Briefing | {phase_mode}**",
        f"Active Roster: **{len(active)}** | R3 Core: **{len(r3_list)}** ({len(r3_list)/max(len(active),1)*100:.1f}%)",
        "",
        f"**R3 Core / Specialists ({len(r3_list)}):** " + (", ".join(r3_list[:25]) + ("..." if len(r3_list) > 25 else "")),
        f"**Monitor / Warn ({len(warn_list)}):** " + (", ".join(warn_list) if warn_list else "None"),
        f"**Kick Candidates ({len(kick_list)}):** " + (", ".join(kick_list) if kick_list else "None"),
        f"**Top Rotated Active in KD 4161:** " + (", ".join(rot_list) if rot_list else "None"),
    ]
    return "\n".join(lines)


if "state" not in st.session_state:
    st.session_state.state = load_persistent_state()

if "base_records" not in st.session_state:
    st.session_state.base_records = load_baseline_records()

state = st.session_state.state

with st.sidebar:
    st.markdown("## ⚔️ ODS1 Command Center")
    st.caption("Kingdom 4161 • KvK 1 • Persistent Roster Engine")

    phase_mode = st.selectbox(
        "KvK Scoring Phase",
        [
            "Early KvK (Day 8 - Forts/Flags Heavy)",
            "Mid KvK (Pass Skirmishes)",
            "Late KvK (King's Land War)",
        ],
        index=0,
    )

    r3_cutoff = st.slider("R3 Overall Activity Cutoff", min_value=45.0, max_value=80.0, value=64.0, step=1.0)
    spec_threshold = st.slider("Specialist Immunity Score", min_value=65.0, max_value=95.0, value=82.0, step=1.0)

    auto_update_ranks = st.toggle(
        "Auto-Update Ranks on New Uploads",
        value=True,
        help="When ON, daily uploads automatically recalculate and save R3/R2/R1/Kick ranks based on your criteria while protecting R5/R4 and Excused members.",
    )

    st.markdown("---")
    st.markdown("### 📂 Daily / Weekly File Upload")
    uploaded_files = st.file_uploader(
        "Drop ROKSTATS .xlsx files (7d Activity, Usefulness, All-Time, or KD 4161 PlayersRanking)",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        if st.button("🔄 Merge Files & Save Snapshot", type="primary", use_container_width=True):
            updated_records = merge_uploaded_files(st.session_state.base_records, uploaded_files)
            st.session_state.base_records = updated_records
            with open(BASELINE_PATH, "w", encoding="utf-8") as f:
                json.dump(updated_records, f, ensure_ascii=False, indent=2)
            state["snapshots"].append({
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "files": [u.name for u in uploaded_files],
                "total_records": len(updated_records),
            })
            save_persistent_state(state)
            st.success(f"Merged {len(uploaded_files)} file(s) — {len(updated_records)} ODS1 records saved!")

    st.markdown("---")
    st.markdown("### 💾 Backup & Restore State")
    state_json_str = json.dumps(state, ensure_ascii=False, indent=2)
    st.download_button(
        "⬇️ Download Saved Ranks & Notes (.json)",
        data=state_json_str,
        file_name="ods1_persistent_state.json",
        mime="application/json",
        use_container_width=True,
    )
    restored_file = st.file_uploader("Restore Saved State (.json)", type=["json"], key="restore_json")
    if restored_file is not None:
        try:
            restored = json.load(restored_file)
            st.session_state.state = restored
            save_persistent_state(restored)
            st.success("Persistent state restored!")
        except Exception as e:
            st.error(f"Invalid JSON: {e}")

df_all = score_and_classify(
    st.session_state.base_records,
    state,
    phase_mode=phase_mode,
    r3_cutoff=r3_cutoff,
    spec_threshold=spec_threshold,
    auto_update_ranks=auto_update_ranks,
)
save_persistent_state(state)

active_df = df_all[df_all["in_active_126"]].copy()
rotated_df = df_all[(~df_all["in_active_126"]) & (df_all["in_kvk_4161"])].copy()
departed_df = df_all[(~df_all["in_active_126"]) & (~df_all["in_kvk_4161"])].copy()

st.title("ODS1 Command Center — KD 4161 KvK 1")
c1, c2, c3, c4, c5 = st.columns(5)
r3_count = int((active_df["rank"] == "R3").sum())
r3_pct = (r3_count / max(len(active_df), 1)) * 100.0
kick_count = int((active_df["bucket"] == "Kick Candidate").sum())
warn_count = int((active_df["bucket"] == "Monitor / Warn (R1)").sum())
total_ods1_dkp = active_df["kvk_dkp"].sum() + rotated_df["kvk_dkp"].sum()

for col_box, label, val, sub in [
    (c1, "Active ODS1 Roster", f"{len(active_df)}", f"+{len(rotated_df)} rotated in KD 4161"),
    (c2, "R3 Core Target", f"{r3_count} ({r3_pct:.1f}%)", f"Cutoff: {r3_cutoff:.0f} or Spec ≥{spec_threshold:.0f}"),
    (c3, "Monitor / Warn (R1)", f"{warn_count}", "Low output / veteran slumps"),
    (c4, "Kick Candidates", f"{kick_count}", "Low Usefulness & low KvK"),
    (c5, "ODS1 Combined DKP", f"{total_ods1_dkp/1e6:.1f}M", "Active + Rotated in #4161"),
]:
    col_box.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{val}</div><div class="metric-sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )

search_q = st.text_input("🔍 Search by Governor Name, Alias (AKA), or Governor ID", placeholder="e.g., Arthur, 233183356, MA7ZM, BasiLa...")
if search_q.strip():
    q = search_q.strip().lower()
    mask = (
        df_all["name"].str.lower().str.contains(q, na=False)
        | df_all["alias_str"].str.lower().str.contains(q, na=False)
        | df_all["id"].astype(str).str.contains(q, na=False)
    )
    filtered_df = df_all[mask].copy()
else:
    filtered_df = df_all.copy()

tabs = st.tabs([
    "📊 Overall Activity & Buckets",
    "🛠️ Usefulness Leaderboard",
    "⚔️ KvK Performance (#4161)",
    "🏰 Forts • 📜 Tech • 🤝 Helps",
    "🔁 Rotations, Name Changes & Left",
    "✏️ Rank & Excused Manager",
    "📋 Discord Briefing Export",
])

with tabs[0]:
    st.subheader("Overall Activity & Decision Buckets (Strict ODS1 Roster)")
    bucket_filter = st.multiselect(
        "Filter Bucket",
        options=sorted(df_all["bucket"].unique().tolist()),
        default=["Leadership (R5/R4)", "Promote / Keep R3", "Keep (R2 Core)", "Monitor / Warn (R1)", "Kick Candidate"],
    )
    view_df = filtered_df[filtered_df["bucket"].isin(bucket_filter)] if bucket_filter else filtered_df
    cols_0 = [
        "id", "name", "alias_str", "rank", "bucket", "overall_score",
        "ods1_usefulness", "kvk_score", "power", "kvk_dkp", "dkp_ratio",
        "forts_7d", "tech_7d", "helps_7d", "build_hrs_7d", "is_new_joiner", "reason"
    ]
    st.dataframe(view_df[cols_0], use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("Usefulness Leaderboard (Help Spam Capped at 2,000 • Flag Building Rewarded)")
    u_mode = st.radio("View Scope", ["Active ODS1 (126)", "All-Time ODS1 History (258)"], horizontal=True)
    u_df = filtered_df[filtered_df["in_active_126"]] if u_mode.startswith("Active") else filtered_df
    if u_mode.startswith("Active"):
        u_df = u_df.sort_values(by="ods1_usefulness", ascending=False)
        st.dataframe(
            u_df[["id", "name", "rank", "ods1_usefulness", "rok_use_7d", "rok_act_7d", "forts_7d", "tech_7d", "helps_7d", "build_hrs_7d", "forts_all"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        u_df = u_df.sort_values(by="rok_use_all", ascending=False)
        st.dataframe(
            u_df[["id", "name", "alias_str", "status", "rok_use_all", "forts_all", "tech_all", "helps_all", "rss_all", "last_login"]],
            use_container_width=True,
            hide_index=True,
        )

with tabs[2]:
    st.subheader("KvK Performance Leaderboard — Kingdom 4161 (Power-Bracket Adjusted)")
    k_df = filtered_df[filtered_df["in_kvk_4161"]].sort_values(by="kvk_dkp", ascending=False)
    st.dataframe(
        k_df[["kd_rank", "camp_rank", "id", "name", "alias_str", "status", "rank", "power", "pwr_diff", "kvk_kp", "kvk_t4", "kvk_t5", "kvk_dead", "kvk_healed", "kvk_dkp", "dkp_ratio", "kvk_score"]],
        use_container_width=True,
        hide_index=True,
    )

with tabs[3]:
    st.subheader("Top in Forts, Tech Donations & Alliance Helps (7-Day vs. All-Time)")
    c_f, c_t, c_h = st.columns(3)
    with c_f:
        st.markdown("#### 🏰 Top in Forts (7d)")
        st.dataframe(
            active_df.sort_values(by="forts_7d", ascending=False)[["name", "forts_7d", "forts_all", "ods1_usefulness"]].head(25),
            use_container_width=True,
            hide_index=True,
        )
    with c_t:
        st.markdown("#### 📜 Top in Tech Donations (7d)")
        st.dataframe(
            active_df.sort_values(by="tech_7d", ascending=False)[["name", "tech_7d", "tech_all", "ods1_usefulness"]].head(25),
            use_container_width=True,
            hide_index=True,
        )
    with c_h:
        st.markdown("#### 🤝 Top in Helps & Flag Hours (7d)")
        st.dataframe(
            active_df.sort_values(by="helps_7d", ascending=False)[["name", "helps_7d", "build_hrs_7d", "ods1_usefulness"]].head(25),
            use_container_width=True,
            hide_index=True,
        )

with tabs[4]:
    st.subheader("Rotated Out in KD 4161, Name Changes & Departed Accounts")
    st.markdown("#### 🔁 Rotated Out of ODS1 Snapshot but Active in KD 4161")
    st.dataframe(
        rotated_df.sort_values(by="kvk_dkp", ascending=False)[["id", "name", "alias_str", "kd_rank", "power", "kvk_kp", "kvk_dkp", "kvk_dead", "forts_all", "last_login"]],
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("#### 🏷️ Detected Name Changes Across Scans (Tracked by Governor ID)")
    changed_df = df_all[df_all["alias_str"].str.len() > 0][["id", "name", "alias_str", "status", "power", "kvk_dkp", "overall_score"]]
    st.dataframe(changed_df, use_container_width=True, hide_index=True)

    st.markdown("#### 🚪 Departed / Inactive Accounts (Not in Active 126 or KD 4161)")
    st.dataframe(
        departed_df[["id", "name", "alias_str", "power", "forts_all", "tech_all", "rok_use_all", "last_login"]],
        use_container_width=True,
        hide_index=True,
    )

with tabs[5]:
    st.subheader("Manual Rank Override, Excused Status & Officer Notes")
    sel_player = st.selectbox(
        "Select Governor to Override Rank / Mark Excused",
        options=df_all["id"].tolist(),
        format_func=lambda gid: f"{df_all[df_all['id']==gid]['name'].values[0]} (ID: {gid}) — Current: {df_all[df_all['id']==gid]['rank'].values[0]}",
    )
    curr_row = df_all[df_all["id"] == sel_player].iloc[0]
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        new_rank_choice = st.selectbox(
            "Saved Rank",
            ["R5", "R4", "R3", "R2", "R1", "Kick"],
            index=["R5", "R4", "R3", "R2", "R1", "Kick"].index(curr_row["rank"]) if curr_row["rank"] in ["R5", "R4", "R3", "R2", "R1", "Kick"] else 3,
        )
    with col_b:
        excused_choice = st.checkbox("Excused Absence / Rebuild Protection", value=bool(curr_row["is_excused"]))
    with col_c:
        note_choice = st.text_input("Officer Note", value=str(curr_row["officer_note"]))

    if st.button("💾 Save Player Override"):
        state["custom_ranks"][str(sel_player)] = new_rank_choice
        exc_list = set(int(x) for x in state.get("excused_ids", []))
        if excused_choice:
            exc_list.add(int(sel_player))
        else:
            exc_list.discard(int(sel_player))
        state["excused_ids"] = sorted(list(exc_list))
        state["notes"][str(sel_player)] = note_choice
        save_persistent_state(state)
        st.success(f"Saved override for {curr_row['name']} ({sel_player})!")
        st.rerun()

with tabs[6]:
    st.subheader("1-Click Discord / Leadership Briefing")
    briefing_text = build_discord_briefing(df_all, phase_mode)
    st.code(briefing_text, language="markdown")
