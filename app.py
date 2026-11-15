import json
import os
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="ODS1 Command Center | KD 4161",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .stApp {
        background-color: #090d16;
        color: #f1f5f9;
    }
    .main .block-container {
        padding-top: 1.75rem;
        padding-bottom: 2.5rem;
        max-width: 1420px;
    }
    [data-testid="stSidebar"] {
        background-color: #0e1422;
        border-right: 1px solid #1e293b;
    }

    /* Header Banner */
    .ods1-header {
        display: flex;
        flex-wrap: wrap;
        justify-content: space-between;
        align-items: center;
        background: linear-gradient(135deg, #111827 0%, #172033 100%);
        border: 1px solid #263349;
        border-radius: 14px;
        padding: 18px 22px;
        margin-bottom: 18px;
    }
    .ods1-title {
        font-size: 1.55rem;
        font-weight: 700;
        color: #f8fafc;
        margin: 0;
        letter-spacing: -0.02em;
    }
    .ods1-subtitle {
        font-size: 0.85rem;
        color: #94a3b8;
        margin-top: 4px;
    }
    .ods1-pill {
        background: rgba(251, 191, 36, 0.12);
        border: 1px solid rgba(251, 191, 36, 0.35);
        color: #fbbf24;
        padding: 6px 12px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
    }

    /* KPI Cards */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 12px;
        margin-bottom: 18px;
    }
    @media (max-width: 1100px) {
        .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    .kpi-card {
        background: #111827;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 14px 16px;
        transition: border-color 0.15s ease;
    }
    .kpi-card:hover { border-color: #334155; }
    .kpi-label {
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #94a3b8;
    }
    .kpi-val {
        font-size: 1.45rem;
        font-weight: 700;
        color: #f8fafc;
        margin-top: 4px;
    }
    .kpi-val.gold { color: #fbbf24; }
    .kpi-sub {
        font-size: 0.76rem;
        color: #64748b;
        margin-top: 3px;
    }

    /* Tab Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: #0e1422;
        padding: 6px;
        border-radius: 12px;
        border: 1px solid #1e293b;
        margin-bottom: 14px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 0.84rem;
        font-weight: 500;
        color: #94a3b8;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e293b !important;
        color: #fbbf24 !important;
        font-weight: 600;
    }

    /* Dataframe polish */
    [data-testid="stDataFrame"] {
        border: 1px solid #1e293b;
        border-radius: 12px;
        overflow: hidden;
    }
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


def fmt_power(val: float) -> str:
    v = float(val or 0)
    if abs(v) >= 1e9:
        return f"{v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"{v/1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"{v/1e3:.1f}K"
    return f"{v:.0f}"


def fmt_num(val: float) -> str:
    v = float(val or 0)
    if abs(v) >= 1e6:
        return f"{v/1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"{v/1e3:.1f}K"
    return f"{v:,.0f}"


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
        is_alltime = len(df) > 180 or (
            "Usefulness Score" in df.columns
            and "Activity points" not in df.columns
            and len(df) >= 200
        )
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
                    "forts_7d": 0,
                    "forts_all": 0,
                    "tech_7d": 0,
                    "tech_all": 0,
                    "helps_7d": 0,
                    "helps_all": 0,
                    "rss_7d": 0,
                    "rss_all": 0,
                    "build_7d": 0,
                    "build_all": 0,
                    "rok_use_7d": 0,
                    "rok_use_all": 0,
                    "rok_act_7d": 0.0,
                    "kvk_kp": 0.0,
                    "kvk_dkp": 0.0,
                    "kvk_t4": 0.0,
                    "kvk_t5": 0.0,
                    "kvk_dead": 0.0,
                    "kvk_healed": 0.0,
                    "kvk_acclaim": 0.0,
                    "kvk_trades": 0.0,
                    "kd_rank": None,
                    "camp_rank": None,
                    "pwr_diff": 0.0,
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


def score_and_classify(
    records: list,
    state: dict,
    phase_mode: str,
    r3_cutoff: float,
    spec_threshold: float,
    auto_update_ranks: bool,
) -> pd.DataFrame:
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
        is_new = bool(
            in_active
            and forts_all == forts_7d
            and tech_7d == int(r.get("tech_all", 0) or 0)
            and helps_7d == int(r.get("helps_all", 0) or 0)
        )

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
            if in_kvk and (
                rok_use_all >= 10
                or kvk_dkp >= 500000
                or "ᴼᴰ" in str(r.get("name", ""))
                or "OD" in str(r.get("name", ""))
            ):
                rec_rank = "R3" if kvk_dkp >= 1500000 else "R2"
                bucket = "Rotated Out (Active KD)"
                reason = "Rotated out in KD 4161"
            else:
                rec_rank = "Left"
                bucket = "Departed / Left"
                reason = "Not in active scan or KD 4161"
        else:
            if is_excused:
                rec_rank = custom_ranks.get(str_id, "R2")
                bucket = "Excused (Protected)"
                reason = "Excused / rebuild protection"
            elif is_specialist or overall >= r3_cutoff:
                rec_rank = "R3"
                bucket = "Promote / Keep R3"
                reason = "Specialist Immunity" if (is_specialist and overall < r3_cutoff) else "Top-Tier Core"
            elif overall >= 32.0 or use_score >= 48.0 or kvk_score >= 50.0:
                rec_rank = "R2"
                bucket = "Keep (R2 Core)"
                reason = "Standard contributor"
            elif overall >= 16.0 or rok_use_all >= 30:
                rec_rank = "R1"
                bucket = "Monitor / Warn (R1)"
                reason = "Veteran slump — check in" if rok_use_all >= 30 else "Below standard — warn"
            else:
                rec_rank = "Kick"
                bucket = "Kick Candidate"
                reason = "Low Usefulness & low KvK"

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
            "power_fmt": fmt_power(power),
            "forts_7d": forts_7d,
            "tech_7d": tech_7d,
            "tech_7d_fmt": fmt_num(tech_7d),
            "helps_7d": helps_7d,
            "helps_7d_fmt": fmt_num(helps_7d),
            "build_7d": build_7d,
            "build_hrs_7d": round(build_7d / 3600.0, 1),
            "forts_all": forts_all,
            "kvk_dkp": kvk_dkp,
            "kvk_dkp_fmt": fmt_num(kvk_dkp),
            "kvk_kp": kvk_kp,
            "kvk_kp_fmt": fmt_num(kvk_kp),
            "kvk_healed": kvk_healed,
            "kvk_healed_fmt": fmt_num(kvk_healed),
            "kvk_acclaim": kvk_acclaim,
            "dkp_ratio_pct": round(ratio * 100.0, 2),
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
    rot_list = (
        df[df["bucket"] == "Rotated Out (Active KD)"]
        .sort_values(by="kvk_dkp", ascending=False)["name"]
        .head(12)
        .tolist()
    )

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
    st.markdown("### ⚔️ ODS1 Controls")
    st.caption("KD 4161 • KvK 1 (Day 8)")

    phase_mode = st.selectbox(
        "Scoring Phase",
        [
            "Early KvK (Day 8 - Forts/Flags Heavy)",
            "Mid KvK (Pass Skirmishes)",
            "Late KvK (King's Land War)",
        ],
        index=0,
    )

    with st.expander("Rank & Specialist Thresholds", expanded=False):
        r3_cutoff = st.slider("R3 Overall Cutoff", min_value=45.0, max_value=80.0, value=64.0, step=1.0)
        spec_threshold = st.slider("Specialist Immunity", min_value=65.0, max_value=95.0, value=82.0, step=1.0)

    auto_update_ranks = st.toggle(
        "Auto-Update Ranks on Upload",
        value=True,
    )

    st.markdown("---")
    st.markdown("### 📂 Update Data")
    uploaded_files = st.file_uploader(
        "Upload ROKSTATS .xlsx files",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        if st.button("Merge & Save Snapshot", type="primary", use_container_width=True):
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
            st.success(f"Merged {len(uploaded_files)} file(s).")

    with st.expander("Backup & Restore (.json)", expanded=False):
        state_json_str = json.dumps(state, ensure_ascii=False, indent=2)
        st.download_button(
            "Download Saved State",
            data=state_json_str,
            file_name="ods1_persistent_state.json",
            mime="application/json",
            use_container_width=True,
        )
        restored_file = st.file_uploader("Restore State JSON", type=["json"], key="restore_json")
        if restored_file is not None:
            try:
                restored = json.load(restored_file)
                st.session_state.state = restored
                save_persistent_state(restored)
                st.success("State restored.")
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

st.markdown(
    f"""
    <div class="ods1-header">
        <div>
            <h1 class="ods1-title">ODYSSEY1 (ODS1) Command Center</h1>
            <div class="ods1-subtitle">Kingdom 4161 • KvK 1 • Persistent Roster, Rotation &amp; Performance Tracker</div>
        </div>
        <div class="ods1-pill">{phase_mode.split(" (")[0]}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

r3_count = int((active_df["rank"] == "R3").sum())
r3_pct = (r3_count / max(len(active_df), 1)) * 100.0
kick_count = int((active_df["bucket"] == "Kick Candidate").sum())
warn_count = int((active_df["bucket"] == "Monitor / Warn (R1)").sum())
total_ods1_dkp = active_df["kvk_dkp"].sum() + rotated_df["kvk_dkp"].sum()

st.markdown(
    f"""
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Active ODS1</div>
            <div class="kpi-val">{len(active_df)}</div>
            <div class="kpi-sub">+{len(rotated_df)} rotated in #4161</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">R3 Core</div>
            <div class="kpi-val gold">{r3_count} ({r3_pct:.0f}%)</div>
            <div class="kpi-sub">Target ~30% • Cutoff {r3_cutoff:.0f}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Monitor / Warn</div>
            <div class="kpi-val">{warn_count}</div>
            <div class="kpi-sub">R1 watch / veteran slump</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Kick Candidates</div>
            <div class="kpi-val">{kick_count}</div>
            <div class="kpi-sub">Low support &amp; low KvK</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">ODS1 KvK DKP</div>
            <div class="kpi-val gold">{fmt_num(total_ods1_dkp)}</div>
            <div class="kpi-sub">Active + Rotated #4161</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

f_col1, f_col2 = st.columns([2.2, 1.8])
with f_col1:
    search_q = st.text_input(
        "Search Governor",
        placeholder="Search name, former alias, or ID...",
        label_visibility="collapsed",
    )
with f_col2:
    bucket_filter = st.multiselect(
        "Filter Buckets",
        options=sorted(df_all["bucket"].unique().tolist()),
        default=["Leadership (R5/R4)", "Promote / Keep R3", "Keep (R2 Core)", "Monitor / Warn (R1)", "Kick Candidate"],
        label_visibility="collapsed",
    )

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
    "Overview",
    "Usefulness",
    "KvK (#4161)",
    "Forts • Tech • Helps",
    "Rotations & Aliases",
    "Rank & Excused",
    "Briefing",
])

with tabs[0]:
    view_df = filtered_df[filtered_df["bucket"].isin(bucket_filter)] if bucket_filter else filtered_df
    cols_0 = [
        "name", "id", "rank", "bucket", "overall_score", "ods1_usefulness",
        "kvk_score", "power_fmt", "kvk_dkp_fmt", "dkp_ratio_pct",
        "forts_7d", "tech_7d_fmt", "helps_7d_fmt", "build_hrs_7d", "reason"
    ]
    st.dataframe(
        view_df[cols_0].rename(columns={
            "name": "Governor",
            "id": "ID",
            "rank": "Rank",
            "bucket": "Bucket",
            "overall_score": "Overall",
            "ods1_usefulness": "Usefulness",
            "kvk_score": "KvK Score",
            "power_fmt": "Power",
            "kvk_dkp_fmt": "KvK DKP",
            "dkp_ratio_pct": "DKP/Pwr %",
            "forts_7d": "Forts (7d)",
            "tech_7d_fmt": "Tech (7d)",
            "helps_7d_fmt": "Helps (7d)",
            "build_hrs_7d": "Build Hrs",
            "reason": "Notes / Status",
        }),
        use_container_width=True,
        hide_index=True,
    )

with tabs[1]:
    u_mode = st.radio("Roster Scope", ["Active ODS1 (126)", "All-Time ODS1 (258)"], horizontal=True, label_visibility="collapsed")
    u_df = filtered_df[filtered_df["in_active_126"]] if u_mode.startswith("Active") else filtered_df
    if u_mode.startswith("Active"):
        u_df = u_df.sort_values(by="ods1_usefulness", ascending=False)
        st.dataframe(
            u_df[["name", "id", "rank", "ods1_usefulness", "rok_use_7d", "forts_7d", "tech_7d_fmt", "helps_7d_fmt", "build_hrs_7d", "forts_all"]].rename(columns={
                "name": "Governor", "id": "ID", "rank": "Rank", "ods1_usefulness": "ODS1 Usefulness",
                "rok_use_7d": "ROK Usefulness", "forts_7d": "Forts (7d)", "tech_7d_fmt": "Tech (7d)",
                "helps_7d_fmt": "Helps (7d)", "build_hrs_7d": "Build Hrs", "forts_all": "All-Time Forts"
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        u_df = u_df.sort_values(by="rok_use_all", ascending=False)
        st.dataframe(
            u_df[["name", "id", "status", "rok_use_all", "forts_all", "tech_all", "helps_all"]].rename(columns={
                "name": "Governor", "id": "ID", "status": "Status", "rok_use_all": "All-Time Score",
                "forts_all": "Forts", "tech_all": "Tech", "helps_all": "Helps"
            }),
            use_container_width=True,
            hide_index=True,
        )

with tabs[2]:
    k_df = filtered_df[filtered_df["in_kvk_4161"]].sort_values(by="kvk_dkp", ascending=False)
    st.dataframe(
        k_df[["kd_rank", "name", "id", "status", "rank", "power_fmt", "kvk_kp_fmt", "kvk_dkp_fmt", "dkp_ratio_pct", "kvk_healed_fmt", "kvk_score"]].rename(columns={
            "kd_rank": "KD #", "name": "Governor", "id": "ID", "status": "Status", "rank": "Rank",
            "power_fmt": "Power", "kvk_kp_fmt": "KvK KP", "kvk_dkp_fmt": "KvK DKP",
            "dkp_ratio_pct": "DKP/Pwr %", "kvk_healed_fmt": "Healed", "kvk_score": "KvK Score"
        }),
        use_container_width=True,
        hide_index=True,
    )

with tabs[3]:
    c_f, c_t, c_h = st.columns(3)
    with c_f:
        st.markdown("#### Top in Forts (7d)")
        st.dataframe(
            active_df.sort_values(by="forts_7d", ascending=False)[["name", "forts_7d", "forts_all"]].head(25).rename(columns={
                "name": "Governor", "forts_7d": "7d", "forts_all": "All-Time"
            }),
            use_container_width=True,
            hide_index=True,
        )
    with c_t:
        st.markdown("#### Top in Tech (7d)")
        st.dataframe(
            active_df.sort_values(by="tech_7d", ascending=False)[["name", "tech_7d_fmt", "ods1_usefulness"]].head(25).rename(columns={
                "name": "Governor", "tech_7d_fmt": "Tech (7d)", "ods1_usefulness": "Usefulness"
            }),
            use_container_width=True,
            hide_index=True,
        )
    with c_h:
        st.markdown("#### Top in Helps & Flags (7d)")
        st.dataframe(
            active_df.sort_values(by="helps_7d", ascending=False)[["name", "helps_7d_fmt", "build_hrs_7d"]].head(25).rename(columns={
                "name": "Governor", "helps_7d_fmt": "Helps (7d)", "build_hrs_7d": "Build Hrs"
            }),
            use_container_width=True,
            hide_index=True,
        )

with tabs[4]:
    st.markdown("#### Rotated Out of ODS1 Snapshot (Active in KD 4161)")
    st.dataframe(
        rotated_df.sort_values(by="kvk_dkp", ascending=False)[["name", "alias_str", "id", "kd_rank", "power_fmt", "kvk_kp_fmt", "kvk_dkp_fmt", "forts_all"]].rename(columns={
            "name": "Current Name", "alias_str": "Former Name(s)", "id": "ID", "kd_rank": "KD #",
            "power_fmt": "Power", "kvk_kp_fmt": "KvK KP", "kvk_dkp_fmt": "KvK DKP", "forts_all": "ODS1 Forts"
        }),
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("#### Detected Name Changes (Tracked by Governor ID)")
    changed_df = df_all[df_all["alias_str"].str.len() > 0][["name", "alias_str", "id", "status", "kvk_dkp_fmt"]].rename(columns={
        "name": "Current Name", "alias_str": "Previous Name(s)", "id": "ID", "status": "Status", "kvk_dkp_fmt": "KvK DKP"
    })
    st.dataframe(changed_df, use_container_width=True, hide_index=True)

    st.markdown("#### Departed / Inactive Accounts")
    st.dataframe(
        departed_df[["name", "id", "power_fmt", "forts_all", "rok_use_all"]].rename(columns={
            "name": "Governor", "id": "ID", "power_fmt": "Power", "forts_all": "Forts", "rok_use_all": "All-Time Score"
        }),
        use_container_width=True,
        hide_index=True,
    )

with tabs[5]:
    sel_player = st.selectbox(
        "Select Governor",
        options=df_all["id"].tolist(),
        format_func=lambda gid: f"{df_all[df_all['id']==gid]['name'].values[0]} ({gid}) — {df_all[df_all['id']==gid]['rank'].values[0]}",
    )
    curr_row = df_all[df_all["id"] == sel_player].iloc[0]
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        new_rank_choice = st.selectbox(
            "Rank",
            ["R5", "R4", "R3", "R2", "R1", "Kick"],
            index=["R5", "R4", "R3", "R2", "R1", "Kick"].index(curr_row["rank"]) if curr_row["rank"] in ["R5", "R4", "R3", "R2", "R1", "Kick"] else 3,
        )
    with col_b:
        st.write("")
        st.write("")
        excused_choice = st.checkbox("Excused Absence / Protection", value=bool(curr_row["is_excused"]))
    with col_c:
        note_choice = st.text_input("Officer Note", value=str(curr_row["officer_note"]))

    if st.button("Save Changes", type="primary"):
        state["custom_ranks"][str(sel_player)] = new_rank_choice
        exc_list = set(int(x) for x in state.get("excused_ids", []))
        if excused_choice:
            exc_list.add(int(sel_player))
        else:
            exc_list.discard(int(sel_player))
        state["excused_ids"] = sorted(list(exc_list))
        state["notes"][str(sel_player)] = note_choice
        save_persistent_state(state)
        st.success("Saved.")
        st.rerun()

with tabs[6]:
    briefing_text = build_discord_briefing(df_all, phase_mode)
    st.code(briefing_text, language="markdown")
