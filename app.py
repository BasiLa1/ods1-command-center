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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .stApp {
        background-color: #070b14;
        color: #f8fafc;
    }
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1460px;
    }
    [data-testid="stSidebar"] {
        background-color: #0b1120;
        border-right: 1px solid #1e293b;
    }

    /* Sidebar Rules Card */
    .rules-card {
        background: #111827;
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 12px 14px;
        margin-top: 8px;
        margin-bottom: 12px;
        font-size: 0.8rem;
        line-height: 1.5;
        color: #cbd5e1;
    }
    .rules-card b {
        color: #fbbf24;
    }

    /* Hero Banner */
    .hero-banner {
        background: radial-gradient(circle at top right, rgba(245, 158, 11, 0.14), transparent 45%),
                    linear-gradient(135deg, #0f172a 0%, #111827 100%);
        border: 1px solid #1e293b;
        border-left: 5px solid #f59e0b;
        border-radius: 16px;
        padding: 22px 26px;
        margin-bottom: 22px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 14px;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.6);
    }
    .hero-title {
        font-size: 1.65rem;
        font-weight: 800;
        color: #ffffff;
        margin: 0;
        letter-spacing: -0.02em;
    }
    .hero-sub {
        font-size: 0.88rem;
        color: #94a3b8;
        margin-top: 5px;
    }
    .hero-badges {
        display: flex;
        gap: 10px;
        align-items: center;
        flex-wrap: wrap;
    }
    .pill-gold {
        background: rgba(245, 158, 11, 0.14);
        border: 1px solid rgba(245, 158, 11, 0.4);
        color: #fbbf24;
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.03em;
    }
    .pill-blue {
        background: rgba(56, 189, 248, 0.12);
        border: 1px solid rgba(56, 189, 248, 0.35);
        color: #38bdf8;
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
    }

    /* KPI Strip */
    .kpi-row {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 14px;
        margin-bottom: 26px;
    }
    @media (max-width: 1100px) {
        .kpi-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    .kpi-box {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 14px;
        padding: 16px 18px;
        position: relative;
        overflow: hidden;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
    }
    .kpi-box.accent-blue { border-top: 3px solid #38bdf8; }
    .kpi-box.accent-green { border-top: 3px solid #10b981; }
    .kpi-box.accent-amber { border-top: 3px solid #f59e0b; }
    .kpi-box.accent-red { border-top: 3px solid #ef4444; }
    .kpi-box.accent-purple { border-top: 3px solid #a855f7; }

    .kpi-head {
        font-size: 0.73rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #94a3b8;
    }
    .kpi-num {
        font-size: 1.65rem;
        font-weight: 800;
        color: #f8fafc;
        margin-top: 6px;
        line-height: 1.1;
    }
    .kpi-foot {
        font-size: 0.76rem;
        color: #64748b;
        margin-top: 6px;
    }

    /* Section Headers & Cards */
    .bucket-banner {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 11px 16px;
        border-radius: 10px;
        margin-top: 18px;
        margin-bottom: 10px;
        font-weight: 700;
        font-size: 0.95rem;
    }
    .bucket-r5 { background: rgba(168, 85, 247, 0.14); border-left: 4px solid #a855f7; color: #e9d5ff; }
    .bucket-r3 { background: rgba(16, 185, 129, 0.14); border-left: 4px solid #10b981; color: #a7f3d0; }
    .bucket-r2 { background: rgba(59, 130, 246, 0.14); border-left: 4px solid #3b82f6; color: #bfdbfe; }
    .bucket-r1 { background: rgba(245, 158, 11, 0.14); border-left: 4px solid #f59e0b; color: #fde68a; }
    .bucket-kick { background: rgba(239, 68, 68, 0.14); border-left: 4px solid #ef4444; color: #fecaca; }

    /* Podium Cards */
    .podium-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
        margin-bottom: 14px;
    }
    .podium-card {
        background: linear-gradient(145deg, #111827, #1e293b);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 12px 14px;
    }
    .podium-rank {
        font-size: 0.72rem;
        font-weight: 800;
        text-transform: uppercase;
        color: #fbbf24;
        letter-spacing: 0.05em;
    }
    .podium-name {
        font-size: 1.02rem;
        font-weight: 700;
        color: #ffffff;
        margin-top: 2px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .podium-stat {
        font-size: 0.84rem;
        color: #38bdf8;
        font-weight: 600;
        margin-top: 3px;
    }

    /* Navigation Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #0f172a;
        padding: 7px;
        border-radius: 12px;
        border: 1px solid #1e293b;
        margin-bottom: 18px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 9px 16px;
        font-size: 0.86rem;
        font-weight: 600;
        color: #94a3b8;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e293b !important;
        color: #fbbf24 !important;
        border: 1px solid rgba(251, 191, 36, 0.35) !important;
    }

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


def fmt_num(val: float) -> str:
    v = float(val or 0)
    if abs(v) >= 1e9:
        return f"{v/1e9:.2f}B"
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
    if phase_mode == "Early KvK (Forts & Flags Focus)":
        w_use, w_kvk = 0.55, 0.45
    elif phase_mode == "Mid KvK (Balanced 50/50)":
        w_use, w_kvk = 0.50, 0.50
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
            # Calibrated to match ROKSTATS native Usefulness scale (200 forts = 52 pts, 100k tech = 20 pts, 25h flags = 20 pts, 2.5k helps = 8 pts)
            s_forts = min(forts_7d / 200.0, 1.0) * 52.0
            s_tech = min(tech_7d / 100000.0, 1.0) * 20.0
            s_build = min(build_7d / 90000.0, 1.0) * 20.0
            s_helps = min(helps_7d / 2500.0, 1.0) * 8.0
            use_score = round(s_forts + s_tech + s_build + s_helps, 1)
        else:
            use_score = float(rok_use_all)

        pwr_m = power / 1e6
        if pwr_m < 12.0:
            t_ratio = 0.10
        elif pwr_m <= 20.0:
            t_ratio = 0.15
        else:
            t_ratio = 0.22
        ratio = (kvk_dkp / power) if power > 0 else 0.0
        r_score = min(ratio / t_ratio, 1.0) * 75.0
        h_bonus = min(kvk_healed / 500000.0, 1.0) * 15.0
        a_bonus = min(kvk_acclaim / 50000.0, 1.0) * 10.0
        kvk_score = round(min(r_score + h_bonus + a_bonus, 100.0), 1)

        overall = round(min((w_use * use_score) + (w_kvk * kvk_score), 100.0), 1)

        is_excused = gov_id in excused_set
        is_specialist = (use_score >= spec_threshold) or (kvk_score >= 75.0)

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
            elif overall >= 24.0 or use_score >= 30.0 or kvk_score >= 40.0:
                rec_rank = "R2"
                bucket = "Keep (R2 Core)"
                reason = "Standard contributor"
            elif overall >= 12.0 or rok_use_all >= 30:
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
            "power_m": round(power / 1e6, 2),
            "forts_7d": forts_7d,
            "tech_7d": tech_7d,
            "helps_7d": helps_7d,
            "build_7d": build_7d,
            "build_hrs_7d": round(build_7d / 3600.0, 1),
            "forts_all": forts_all,
            "kvk_dkp": kvk_dkp,
            "kvk_dkp_m": round(kvk_dkp / 1e6, 2),
            "kvk_kp": kvk_kp,
            "kvk_kp_m": round(kvk_kp / 1e6, 2),
            "kvk_healed": kvk_healed,
            "kvk_healed_k": round(kvk_healed / 1e3, 1),
            "kvk_acclaim": kvk_acclaim,
            "dkp_ratio_pct": round(ratio * 100.0, 1),
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


def render_table(df: pd.DataFrame) -> None:
    col_cfg = {
        "id": st.column_config.NumberColumn("Governor ID", format="%d"),
        "name": st.column_config.TextColumn("Governor", width="medium"),
        "alias_str": st.column_config.TextColumn("Former Name(s)", width="small"),
        "rank": st.column_config.TextColumn("Rank", width="small"),
        "bucket": st.column_config.TextColumn("Decision Bucket", width="medium"),
        "overall_score": st.column_config.ProgressColumn(
            "Overall Score", min_value=0, max_value=100, format="%.1f"
        ),
        "ods1_usefulness": st.column_config.ProgressColumn(
            "Usefulness", min_value=0, max_value=100, format="%.1f"
        ),
        "kvk_score": st.column_config.ProgressColumn(
            "KvK Score", min_value=0, max_value=100, format="%.1f"
        ),
        "power_m": st.column_config.NumberColumn("Power (M)", format="%.2fM"),
        "kvk_dkp_m": st.column_config.NumberColumn("KvK DKP (M)", format="%.2fM"),
        "kvk_kp_m": st.column_config.NumberColumn("KvK KP (M)", format="%.2fM"),
        "dkp_ratio_pct": st.column_config.NumberColumn("DKP / Power", format="%.1f%%"),
        "forts_7d": st.column_config.NumberColumn("Forts (7d)", format="%d"),
        "forts_all": st.column_config.NumberColumn("All-Time Forts", format="%d"),
        "tech_7d": st.column_config.NumberColumn("Tech (7d)", format="%d"),
        "helps_7d": st.column_config.NumberColumn("Helps (7d)", format="%d"),
        "build_hrs_7d": st.column_config.NumberColumn("Flag Build (Hrs)", format="%.1fh"),
        "kd_rank": st.column_config.NumberColumn("KD Rank", format="#%d"),
        "kvk_healed_k": st.column_config.NumberColumn("Healed (K)", format="%.1fK"),
        "reason": st.column_config.TextColumn("Status / Protection", width="medium"),
    }
    active_cfg = {k: v for k, v in col_cfg.items() if k in df.columns}
    st.dataframe(df, column_config=active_cfg, use_container_width=True, hide_index=True)


def render_podium(df: pd.DataFrame, val_col: str, suffix: str = "") -> None:
    top3 = df.head(3).to_dict("records")
    if not top3:
        return
    medals = ["🥇 #1", "🥈 #2", "🥉 #3"]
    cards_html = '<div class="podium-grid">'
    for idx, row in enumerate(top3):
        val = row.get(val_col, 0)
        val_str = f"{val:,.0f}{suffix}" if isinstance(val, (int, float)) else f"{val}{suffix}"
        cards_html += (
            f'<div class="podium-card">'
            f'<div class="podium-rank">{medals[idx]}</div>'
            f'<div class="podium-name">{row.get("name", "")}</div>'
            f'<div class="podium-stat">{val_str}</div>'
            f'</div>'
        )
    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)


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
    return chr(10).join(lines)


if "state" not in st.session_state:
    st.session_state.state = load_persistent_state()

if "base_records" not in st.session_state:
    st.session_state.base_records = load_baseline_records()

state = st.session_state.state

# --- CLEAN, SIMPLIFIED SIDEBAR ---
with st.sidebar:
    st.markdown("## ⚔️ ODS1 Command")
    st.caption("Kingdom 4161 • KvK 1")

    # 1. Simple Upload Box
    st.markdown("### 1. Update Roster Data")
    uploaded_files = st.file_uploader(
        "Drop ROKSTATS Excel files here",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        help="Upload your 7-day Activity, Usefulness, or Kingdom PlayersRanking .xlsx files.",
    )

    if uploaded_files:
        if st.button("🔄 Update Dashboard", type="primary", use_container_width=True):
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
            st.success("Roster updated!")

    st.markdown("---")

    # 2. Simple KvK Phase Switcher
    st.markdown("### 2. KvK Stage")
    phase_mode = st.radio(
        "Select current KvK focus:",
        [
            "Early KvK (Forts & Flags Focus)",
            "Mid KvK (Balanced 50/50)",
            "Late KvK (Pass & King's Land War)",
        ],
        index=0,
        label_visibility="collapsed",
    )

    # 3. Clean Summary of How Ranks Work (No confusing math)
    st.markdown("### 3. Rank Rules Summary")
    st.markdown(
        """
        <div class="rules-card">
            • <b>R4 / R5:</b> Locked Leadership<br>
            • <b>R3 (Top ~30%):</b> Score <b>45+</b> OR Specialist (<b>55+</b> Usefulness or <b>75+</b> KvK)<br>
            • <b>R2 (Core):</b> Score <b>24 – 44</b><br>
            • <b>R1 (Warn):</b> Score <b>12 – 23</b><br>
            • <b>Kick:</b> Score <b>Under 12</b> (Inactive in both)
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 4. Optional Fine-Tuning tucked away cleanly
    with st.expander("⚙️ Fine-Tune Cutoffs & Backup", expanded=False):
        r3_cutoff = st.slider("R3 Score Requirement", min_value=30.0, max_value=75.0, value=45.0, step=1.0)
        spec_threshold = st.slider("Specialist Usefulness Score", min_value=40.0, max_value=85.0, value=55.0, step=1.0)
        auto_update_ranks = st.toggle("Auto-Assign Ranks on Upload", value=True)
        st.markdown("---")
        state_json_str = json.dumps(state, ensure_ascii=False, indent=2)
        st.download_button(
            "⬇️ Backup Ranks (.json)",
            data=state_json_str,
            file_name="ods1_persistent_state.json",
            mime="application/json",
            use_container_width=True,
        )
        restored_file = st.file_uploader("Restore Backup (.json)", type=["json"], key="restore_json")
        if restored_file is not None:
            try:
                restored = json.load(restored_file)
                st.session_state.state = restored
                save_persistent_state(restored)
                st.success("Backup restored!")
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

r3_count = int((active_df["rank"] == "R3").sum())
r3_pct = (r3_count / max(len(active_df), 1)) * 100.0
r2_count = int((active_df["rank"] == "R2").sum())
warn_count = int((active_df["bucket"] == "Monitor / Warn (R1)").sum())
kick_count = int((active_df["bucket"] == "Kick Candidate").sum())
total_ods1_dkp = active_df["kvk_dkp"].sum() + rotated_df["kvk_dkp"].sum()

# Hero Banner
st.markdown(
    f"""
    <div class="hero-banner">
        <div>
            <h1 class="hero-title">⚔️ ODYSSEY1 (ODS1) Command Center</h1>
            <div class="hero-sub">Kingdom 4161 • KvK 1 Roster Intelligence, Anti-Padding Usefulness &amp; War Performance</div>
        </div>
        <div class="hero-badges">
            <span class="pill-gold">{phase_mode}</span>
            <span class="pill-blue">R5: MA7ZM &amp; ᴼᴰ AYHAM</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Color-Coded KPI Cards
st.markdown(
    f"""
    <div class="kpi-row">
        <div class="kpi-box accent-blue">
            <div class="kpi-head">Active ODS1 Roster</div>
            <div class="kpi-num">{len(active_df)}</div>
            <div class="kpi-foot">+{len(rotated_df)} rotated out in KD 4161</div>
        </div>
        <div class="kpi-box accent-green">
            <div class="kpi-head">R3 Core &amp; Specialists</div>
            <div class="kpi-num">{r3_count} ({r3_pct:.0f}%)</div>
            <div class="kpi-foot">R2 Core: {r2_count} members</div>
        </div>
        <div class="kpi-box accent-amber">
            <div class="kpi-head">Monitor / Warn (R1)</div>
            <div class="kpi-num">{warn_count}</div>
            <div class="kpi-foot">Low weekly output or slump</div>
        </div>
        <div class="kpi-box accent-red">
            <div class="kpi-head">Kick Candidates</div>
            <div class="kpi-num">{kick_count}</div>
            <div class="kpi-foot">Failing both support &amp; KvK</div>
        </div>
        <div class="kpi-box accent-purple">
            <div class="kpi-head">ODS1 Combined DKP</div>
            <div class="kpi-num">{fmt_num(total_ods1_dkp)}</div>
            <div class="kpi-foot">Active + Rotated in #4161</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Search Bar
search_q = st.text_input(
    "🔍 Search Governor",
    placeholder="Search by current name, former alias (e.g. A c e ツ), or Governor ID...",
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
    "🗂️ Roster Decision Buckets",
    "📊 Master Table",
    "🛠️ Usefulness",
    "⚔️ KvK War (#4161)",
    "🏆 Forts • Tech • Helps",
    "🔁 Rotations & Aliases",
    "⚙️ Rank Manager & Briefing",
])

# TAB 0: Visual Separated Decision Buckets
with tabs[0]:
    st.caption("Each tier is separated into its own section with visual progress bars for Overall Score, Usefulness, and KvK Score.")
    active_filtered = filtered_df[filtered_df["in_active_126"]].copy()

    bucket_specs = [
        ("Leadership (R5/R4)", "👑 Command Leadership (R5 / R4 Protected)", "bucket-r5", True),
        ("Promote / Keep R3", "🟢 R3 Elite Core & Protected Specialists", "bucket-r3", True),
        ("Keep (R2 Core)", "🔵 R2 Standard Core Contributors", "bucket-r2", False),
        ("Monitor / Warn (R1)", "🟠 R1 Monitor / Warning List", "bucket-r1", True),
        ("Kick Candidate", "🔴 Kick / Replacement Candidates", "bucket-kick", True),
    ]

    cols_bucket = [
        "name", "id", "rank", "overall_score", "ods1_usefulness", "kvk_score",
        "power_m", "kvk_dkp_m", "forts_7d", "tech_7d", "build_hrs_7d", "reason"
    ]

    for b_key, b_title, b_css, default_open in bucket_specs:
        sub_df = active_filtered[active_filtered["bucket"] == b_key]
        st.markdown(
            f'<div class="bucket-banner {b_css}"><span>{b_title}</span><span>{len(sub_df)} Members</span></div>',
            unsafe_allow_html=True,
        )
        with st.expander(f"View {b_title} ({len(sub_df)})", expanded=default_open):
            render_table(sub_df[cols_bucket])

# TAB 1: Master Filterable Table
with tabs[1]:
    bucket_sel = st.multiselect(
        "Filter Buckets",
        options=sorted(df_all["bucket"].unique().tolist()),
        default=["Leadership (R5/R4)", "Promote / Keep R3", "Keep (R2 Core)", "Monitor / Warn (R1)", "Kick Candidate"],
    )
    view_df = filtered_df[filtered_df["bucket"].isin(bucket_sel)] if bucket_sel else filtered_df
    render_table(view_df[[
        "name", "alias_str", "id", "rank", "bucket", "overall_score",
        "ods1_usefulness", "kvk_score", "power_m", "kvk_dkp_m", "dkp_ratio_pct",
        "forts_7d", "tech_7d", "helps_7d", "build_hrs_7d", "reason"
    ]])

# TAB 2: Usefulness Leaderboard
with tabs[2]:
    u_scope = st.radio("Scope", ["Active ODS1 Roster (126)", "All-Time ODS1 History (258)"], horizontal=True, label_visibility="collapsed")
    if u_scope.startswith("Active"):
        u_df = filtered_df[filtered_df["in_active_126"]].sort_values(by="ods1_usefulness", ascending=False)
        render_podium(u_df, "ods1_usefulness", " / 100 Usefulness")
        render_table(u_df[[
            "name", "id", "rank", "ods1_usefulness", "forts_7d", "tech_7d",
            "helps_7d", "build_hrs_7d", "forts_all", "reason"
        ]])
    else:
        u_df = filtered_df.sort_values(by="forts_all", ascending=False)
        render_podium(u_df, "forts_all", " All-Time Forts")
        render_table(u_df[[
            "name", "alias_str", "id", "status", "forts_all", "power_m", "kvk_dkp_m"
        ]])

# TAB 3: KvK Performance Leaderboard
with tabs[3]:
    k_df = filtered_df[filtered_df["in_kvk_4161"]].sort_values(by="kvk_dkp", ascending=False)
    render_podium(k_df, "kvk_dkp", " DKP")
    render_table(k_df[[
        "kd_rank", "name", "alias_str", "id", "status", "rank",
        "kvk_score", "power_m", "kvk_kp_m", "kvk_dkp_m", "dkp_ratio_pct", "kvk_healed_k"
    ]])

# TAB 4: Forts, Tech & Helps Side-by-Side Cards with Top 3 Podiums
with tabs[4]:
    c_f, c_t, c_h = st.columns(3)
    with c_f:
        st.markdown("#### 🏰 Top in Forts (7d)")
        f_top = active_df.sort_values(by="forts_7d", ascending=False)
        render_podium(f_top, "forts_7d", " Forts")
        render_table(f_top[["name", "forts_7d", "forts_all", "ods1_usefulness"]].head(25))
    with c_t:
        st.markdown("#### 📜 Top in Tech (7d)")
        t_top = active_df.sort_values(by="tech_7d", ascending=False)
        render_podium(t_top, "tech_7d", " Tech")
        render_table(t_top[["name", "tech_7d", "ods1_usefulness"]].head(25))
    with c_h:
        st.markdown("#### 🤝 Top in Flag Hours & Helps (7d)")
        h_top = active_df.sort_values(by="build_hrs_7d", ascending=False)
        render_podium(h_top, "build_hrs_7d", "h Flags")
        render_table(h_top[["name", "build_hrs_7d", "helps_7d", "ods1_usefulness"]].head(25))

# TAB 5: Rotations & Name Changes
with tabs[5]:
    col_rot, col_aka = st.columns([1.35, 1.0])
    with col_rot:
        st.markdown("#### 🔁 Rotated Out of ODS1 (Active in KD 4161)")
        render_table(rotated_df.sort_values(by="kvk_dkp", ascending=False)[[
            "name", "alias_str", "id", "kd_rank", "power_m", "kvk_dkp_m", "forts_all"
        ]])
    with col_aka:
        st.markdown("#### 🏷️ Detected Name Changes (20 IDs)")
        changed_df = df_all[df_all["alias_str"].str.len() > 0]
        render_table(changed_df[[
            "name", "alias_str", "id", "status", "kvk_dkp_m"
        ]])

# TAB 6: Rank Override & Discord Briefing
with tabs[6]:
    col_mgr, col_disc = st.columns([1.1, 1.2])
    with col_mgr:
        st.markdown("#### ✏️ Manual Rank Override & Excused Toggle")
        sel_player = st.selectbox(
            "Select Governor",
            options=df_all["id"].tolist(),
            format_func=lambda gid: f"{df_all[df_all['id']==gid]['name'].values[0]} ({gid}) — {df_all[df_all['id']==gid]['rank'].values[0]}",
        )
        curr_row = df_all[df_all["id"] == sel_player].iloc[0]
        new_rank_choice = st.selectbox(
            "Set Saved Rank",
            ["R5", "R4", "R3", "R2", "R1", "Kick"],
            index=["R5", "R4", "R3", "R2", "R1", "Kick"].index(curr_row["rank"]) if curr_row["rank"] in ["R5", "R4", "R3", "R2", "R1", "Kick"] else 3,
        )
        excused_choice = st.checkbox("Mark Excused (Rebuild / Vacation Immunity)", value=bool(curr_row["is_excused"]))
        note_choice = st.text_input("Officer Note", value=str(curr_row["officer_note"]))

        if st.button("💾 Save Override", type="primary"):
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

    with col_disc:
        st.markdown("#### 📋 1-Click Discord / R4 Briefing")
        briefing_text = build_discord_briefing(df_all, phase_mode)
        st.code(briefing_text, language="markdown")
