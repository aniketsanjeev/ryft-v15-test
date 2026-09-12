import streamlit as st
import sqlite3
import math
import json
from datetime import datetime, timezone
import pandas as pd

# ==============================================================================
# 1. DATABASE INITIALIZATION & RELATIONAL SCHEMA
# ==============================================================================
DB_FILE = "ryft_v15_master.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON;")

    # 1. Locations Table
    c.execute('''
    CREATE TABLE IF NOT EXISTS locations (
        location_id TEXT PRIMARY KEY,
        location_type TEXT NOT NULL CHECK(location_type IN ('COUNTRY', 'STATE', 'CITY')),
        location_name TEXT NOT NULL,
        parent_id TEXT,
        country_code TEXT DEFAULT 'IND',
        intransitivity_idx REAL DEFAULT 0.0,
        hawking_offset REAL DEFAULT 0.0,
        suggested_offset REAL DEFAULT 0.0,
        readiness_score REAL DEFAULT 0.0,
        active_bridge_count INTEGER DEFAULT 0,
        total_active_players INTEGER DEFAULT 0,
        total_matches_played INTEGER DEFAULT 0,
        FOREIGN KEY (parent_id) REFERENCES locations(location_id) ON DELETE SET NULL
    )''')

    # 2. Venues Table
    c.execute('''
    CREATE TABLE IF NOT EXISTS venues (
        venue_id TEXT PRIMARY KEY,
        venue_name TEXT NOT NULL,
        raw_input_name TEXT,
        is_verified INTEGER DEFAULT 0,
        city_id TEXT NOT NULL,
        country_code TEXT NOT NULL,
        court_count INTEGER DEFAULT 1,
        total_matches_played INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (city_id) REFERENCES locations(location_id) ON DELETE CASCADE
    )''')

    # 3. Match Formats Table
    c.execute('''
    CREATE TABLE IF NOT EXISTS match_formats (
        format_id TEXT PRIMARY KEY,
        format_name TEXT NOT NULL,
        category TEXT NOT NULL,
        mc_weight REAL NOT NULL,
        total_points INTEGER,
        is_active INTEGER DEFAULT 1
    )''')

    # 4. Players Table
    c.execute('''
    CREATE TABLE IF NOT EXISTS players (
        player_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        initial_rating REAL NOT NULL,
        home_venue_id TEXT,
        home_city_id TEXT NOT NULL,
        home_country_code TEXT NOT NULL,
        latent_mmr REAL NOT NULL,
        display_rating REAL NOT NULL,
        rolling_90d_peak REAL NOT NULL,
        rolling_180d_peak REAL NOT NULL,
        rolling_365d_peak REAL NOT NULL,
        tournament_floor REAL DEFAULT 0.0,
        all_time_badge TEXT DEFAULT 'Intermediate',
        rating_deviation REAL NOT NULL,
        rating_accuracy_pct REAL DEFAULT 0.0,
        calibration_tier TEXT DEFAULT 'PROVISIONAL',
        is_provisional INTEGER DEFAULT 1,
        verified_matches_count INTEGER DEFAULT 0,
        matches_won_count INTEGER DEFAULT 0,
        matches_lost_count INTEGER DEFAULT 0,
        matches_tied_count INTEGER DEFAULT 0,
        unique_opponents_count INTEGER DEFAULT 0,
        unique_partners_count INTEGER DEFAULT 0,
        unique_venues_count INTEGER DEFAULT 0,
        unique_cities_count INTEGER DEFAULT 0,
        bridge_matches_count INTEGER DEFAULT 0,
        is_active_bridge INTEGER DEFAULT 0,
        graph_centrality REAL DEFAULT 0.20,
        is_quarantined INTEGER DEFAULT 0,
        is_anchor INTEGER DEFAULT 0,
        is_ceiling_anchor INTEGER DEFAULT 0,
        is_dummy INTEGER DEFAULT 0,
        last_match_time TEXT,
        FOREIGN KEY (home_venue_id) REFERENCES venues(venue_id) ON DELETE SET NULL,
        FOREIGN KEY (home_city_id) REFERENCES locations(location_id) ON DELETE CASCADE
    )''')

    # 5. Matches Table
    c.execute('''
    CREATE TABLE IF NOT EXISTS matches (
        match_id TEXT PRIMARY KEY,
        venue_id TEXT NOT NULL,
        format_id TEXT NOT NULL,
        session_id TEXT,
        session_players INTEGER DEFAULT 0,
        is_singles INTEGER DEFAULT 0,
        is_tournament INTEGER DEFAULT 0,
        is_venue_bridge INTEGER DEFAULT 0,
        is_city_bridge INTEGER DEFAULT 0,
        is_country_bridge INTEGER DEFAULT 0,
        team_a_p1_id TEXT NOT NULL,
        team_a_p2_id TEXT,
        team_b_p1_id TEXT NOT NULL,
        team_b_p2_id TEXT,
        score_team_a INTEGER NOT NULL,
        score_team_b INTEGER NOT NULL,
        set_scores_json TEXT NOT NULL,
        games_winner INTEGER NOT NULL,
        games_loser INTEGER NOT NULL,
        pre_rating_a REAL NOT NULL,
        pre_rating_b REAL NOT NULL,
        win_expectancy_a REAL NOT NULL,
        applied_m_c REAL NOT NULL,
        applied_s_margin REAL NOT NULL,
        delta_r_p1 REAL NOT NULL,
        delta_r_p2 REAL DEFAULT 0.0,
        delta_r_p3 REAL NOT NULL,
        delta_r_p4 REAL DEFAULT 0.0,
        match_timestamp TEXT NOT NULL,
        FOREIGN KEY (venue_id) REFERENCES venues(venue_id) ON DELETE RESTRICT
    )''')

    # 6. Match Logs Table
    c.execute('''
    CREATE TABLE IF NOT EXISTS match_logs (
        log_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        player_id TEXT NOT NULL,
        pre_latent_mmr REAL NOT NULL,
        post_latent_mmr REAL NOT NULL,
        pre_rd REAL NOT NULL,
        post_rd REAL NOT NULL,
        pre_accuracy_pct REAL NOT NULL,
        post_accuracy_pct REAL NOT NULL,
        delta_r REAL NOT NULL,
        is_elevator_active INTEGER DEFAULT 0,
        guardrails_triggered TEXT DEFAULT '[]',
        logged_at TEXT NOT NULL,
        FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,
        FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE
    )''')

    # 7. Global Configuration Table
    c.execute('''
    CREATE TABLE IF NOT EXISTS global_config (
        param_key TEXT PRIMARY KEY,
        param_value REAL NOT NULL,
        is_active INTEGER DEFAULT 1,
        description TEXT
    )''')

    # Seed Master Parameters
    default_params = [
        ("R_MIN", 0.0000, 1, "Absolute Scale Floor"),
        ("R_MAX", 7.0000, 1, "Scale Ceiling (Hard Bound)"),
        ("R_ELITE_THRESHOLD", 6.3000, 1, "Elite Drag Threshold"),
        ("ELITE_DRAG_EXPONENT", 2.5, 1, "Elite Drag Curvature"),
        ("POWER_MEAN_P", 3.0, 1, "Anchor Cubing Exponent"),
        ("LOGISTIC_BETA", 2.0, 1, "Expectancy Logistic Scale"),
        ("K_MAX", 0.4000, 1, "Beginner Max Volatility"),
        ("K_MIN", 0.0800, 1, "Pro Minimum Volatility"),
        ("MARGIN_BASE", 0.80, 1, "Score Margin Floor"),
        ("MARGIN_SCALE", 0.40, 1, "Blowout Bonus Factor"),
        ("ELEVATOR_MARGIN_THRESH", 1.15, 1, "Elevator Margin Threshold"),
        ("ELEVATOR_ACCEL_FACTOR", 3.0, 1, "Elevator 3x Multiplier"),
        ("MAX_ELEVATOR_DELTA", 0.7500, 1, "Elevator Single Placement Cap"),
        ("MAX_8H_EXCHANGE_CAP", 0.0000, 0, "8-Hour Rolling Cap (Inactive)"),
        ("MAX_12H_EXCHANGE_CAP", 0.0000, 0, "12-Hour Rolling Cap (Inactive)"),
        ("MAX_24H_EXCHANGE_CAP", 0.1500, 1, "Casual 24h Daily Cap"),
        ("MAX_48H_EXCHANGE_CAP", 0.0000, 0, "48-Hour Rolling Cap (Inactive)"),
        ("SESSION_EXCHANGE_CAP", 0.3000, 1, "Verified Session Cap"),
        ("MIN_SESSION_PLAYERS", 6, 1, "Participant Floor for Session Cap"),
        ("RD_MIN", 30.0, 1, "Certainty Floor"),
        ("RD_MAX", 350.0, 1, "Unrated Starting Uncertainty"),
        ("RD_INFO_VARIANCE", 65.0, 1, "Contraction Speed Constant"),
        ("BRIDGE_RD_THRESHOLD", 80.0, 1, "Max RD to Qualify as Bridge Node"),
        ("BRIDGE_MIN_MATCHES", 5, 1, "Min Cross-Location Matches for Bridge"),
        ("LAMBDA_BRIDGE_DAMPING", 3.0, 1, "Tikhonov Bridge Shrinkage Lambda"),
        ("CIRCUIT_BREAKER", 0.0250, 1, "Macro Normalization Circuit Breaker"),
        ("ADMIN_OVERRIDE_MAX", 0.0750, 1, "Admin Sandbox Shift Window"),
        ("ACCURACY_WEIGHT_RD", 0.50, 1, "Certainty Metric Weight"),
        ("ACCURACY_WEIGHT_MATCHES", 0.25, 1, "Match Volume Metric Weight"),
        ("ACCURACY_WEIGHT_DIVERSITY", 0.25, 1, "Opponent Diversity Weight"),
        ("TIER_PROVISIONAL_MAX", 69.99, 1, "Provisional Ceiling %"),
        ("TIER_VERIFIED_MAX", 89.99, 1, "Verified Ceiling %"),
        ("TARGET_MATCHES_VERIFIED", 5, 1, "Verified Tier Match Quota"),
        ("TARGET_OPPONENTS_VERIFIED", 3, 1, "Verified Tier Opponent Quota")
    ]
    for k, v, act, desc in default_params:
        c.execute("INSERT OR IGNORE INTO global_config (param_key, param_value, is_active, description) VALUES (?, ?, ?, ?)", (k, v, act, desc))

    # Seed Baseline Formats
    default_formats = [
        ("STD_B03", "Best of 3 Sets", "MULTI_SET", 1.00, None),
        ("RACE_7", "Race to 7 Games", "RACE_GAMES", 0.80, None),
        ("RACE_4", "Race to 4 Sprint", "RACE_GAMES", 0.50, None),
        ("AMER_24", "Americano 24 Points", "AMERICANO", 0.30, 24)
    ]
    for fid, fname, cat, mc, tp in default_formats:
        c.execute("INSERT OR IGNORE INTO match_formats (format_id, format_name, category, mc_weight, total_points) VALUES (?, ?, ?, ?, ?)", (fid, fname, cat, mc, tp))

    # Seed Initial Locations & Venues
    c.execute("INSERT OR IGNORE INTO locations (location_id, location_type, location_name, country_code) VALUES ('LOC_IND', 'COUNTRY', 'India', 'IND')")
    c.execute("INSERT OR IGNORE INTO locations (location_id, location_type, location_name, parent_id, country_code) VALUES ('LOC_BLR', 'CITY', 'Bengaluru', 'LOC_IND', 'IND')")
    c.execute("INSERT OR IGNORE INTO locations (location_id, location_type, location_name, parent_id, country_code) VALUES ('LOC_DEL', 'CITY', 'Delhi', 'LOC_IND', 'IND')")
    c.execute("INSERT OR IGNORE INTO venues (venue_id, venue_name, city_id, country_code, is_verified, court_count) VALUES ('VEN_DEPOT18', 'Depot18 Koramangala', 'LOC_BLR', 'IND', 1, 3)")
    c.execute("INSERT OR IGNORE INTO venues (venue_id, venue_name, city_id, country_code, is_verified, court_count) VALUES ('VEN_DEL_HUB', 'Delhi Padel Hub', 'LOC_DEL', 'IND', 1, 4)")

    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 2. V.15 ALGORITHMIC CALCULATION ENGINE
# ==============================================================================
class RyftEngineV15:
    @staticmethod
    def get_configs():
        conn = get_db_connection()
        rows = conn.execute("SELECT param_key, param_value, is_active FROM global_config").fetchall()
        conn.close()
        return {r["param_key"]: (r["param_value"] if r["is_active"] == 1 else None) for r in rows}

    @classmethod
    def compute_match(cls, p1, p2, p3, p4, score_a, score_b, games_w, games_l, format_id, venue_id, is_singles=False, is_tournament=False, is_dry_run=False):
        cfg = cls.get_configs()

        p_exp = cfg.get("POWER_MEAN_P", 3.0) or 3.0
        if is_singles:
            team_a_r, team_b_r = p1["latent_mmr"], p3["latent_mmr"]
        else:
            team_a_r = ((p1["latent_mmr"]**p_exp + p2["latent_mmr"]**p_exp) / 2.0)**(1.0 / p_exp)
            team_b_r = ((p3["latent_mmr"]**p_exp + p4["latent_mmr"]**p_exp) / 2.0)**(1.0 / p_exp)

        beta = cfg.get("LOGISTIC_BETA", 2.0) or 2.0
        exp_a = 1.0 / (1.0 + 10.0**((team_b_r - team_a_r) / beta))
        act_a = 1.0 if score_a > score_b else (0.0 if score_b > score_a else 0.5)
        score_delta = act_a - exp_a

        m_base = cfg.get("MARGIN_BASE", 0.80) if cfg.get("MARGIN_BASE") is not None else 0.80
        m_scale = cfg.get("MARGIN_SCALE", 0.40) if cfg.get("MARGIN_SCALE") is not None else 0.40
        tot_games = games_w + games_l
        s_margin = m_base + (m_scale * ((games_w - games_l) / float(tot_games))) if tot_games > 0 else 1.000
        s_margin = max(0.800, min(1.200, s_margin))

        conn = get_db_connection()
        fmt = conn.execute("SELECT mc_weight FROM match_formats WHERE format_id = ?", (format_id,)).fetchone()
        conn.close()
        mc = fmt["mc_weight"] if fmt else 1.00

        if is_singles:
            participants = [(p1, True, None, p3["rating_deviation"]), (p3, False, None, p1["rating_deviation"])]
        else:
            opp_rd_b = max(p3["rating_deviation"], p4["rating_deviation"])
            opp_rd_a = max(p1["rating_deviation"], p2["rating_deviation"])
            participants = [
                (p1, True, p2["latent_mmr"], opp_rd_b),
                (p2, True, p1["latent_mmr"], opp_rd_b),
                (p3, False, p4["latent_mmr"], opp_rd_a),
                (p4, False, p3["latent_mmr"], opp_rd_a)
            ]

        results = []
        k_max = cfg.get("K_MAX", 0.4000) or 0.4000
        k_min = cfg.get("K_MIN", 0.0800) or 0.0800
        r_max = cfg.get("R_MAX", 7.0000) or 7.0000
        r_elite = cfg.get("R_ELITE_THRESHOLD", 6.3000) or 6.3000
        drag_exp = cfg.get("ELITE_DRAG_EXPONENT", 2.5) or 2.5

        for p_data, is_team_a, partner_r, opp_rd in participants:
            p_flags = []
            r_curr = p_data["latent_mmr"]
            p_rd = p_data["rating_deviation"]
            is_winner = (is_team_a and score_a > score_b) or (not is_team_a and score_b > score_a)
            
            k_base = k_max - (r_curr / r_max) * (k_max - k_min)

            is_elevator = False
            el_thresh = cfg.get("ELEVATOR_MARGIN_THRESH", 1.15) or 1.15
            el_factor = cfg.get("ELEVATOR_ACCEL_FACTOR", 3.0) or 3.0
            if p_data["is_provisional"] and s_margin >= el_thresh and is_winner and r_curr < r_elite:
                k_base *= el_factor
                is_elevator = True
                p_flags.append("ELEVATOR_3X_BOOST")

            decay = (r_max - r_curr) / r_max
            if r_curr >= r_elite:
                decay *= ((r_max - r_curr) / (r_max - r_elite)) ** drag_exp
                p_flags.append("ELITE_DRAG_ENGAGED")
            decay = max(0.0000001, decay)

            q = 0.0057565
            g_opp = 1.0 / math.sqrt(1.0 + (3.0 * (q**2) * (opp_rd**2)) / (math.pi**2))
            w_trust = 0.0000 if p_data["is_quarantined"] else min(1.0, p_data["graph_centrality"] / 0.20)
            if p_data["is_quarantined"]: p_flags.append("QUARANTINED_POINTS_FROZEN")

            direction = 1.0 if is_team_a else -1.0
            raw_delta = (k_base * decay * mc * s_margin * w_trust * g_opp) * (direction * score_delta)

            dampened_delta = raw_delta
            if not is_singles and partner_r is not None:
                gap = abs(r_curr - partner_r)
                d_factor = 1.0
                if gap >= 2.0: d_factor = 0.05
                elif gap >= 1.5: d_factor = 0.20
                elif gap >= 1.0: d_factor = 0.50

                if raw_delta < 0 and r_curr > partner_r and d_factor < 1.0:
                    dampened_delta = raw_delta * d_factor
                    p_flags.append(f"ICE_OUT_ANCHOR_SAVED_{int((1-d_factor)*100)}PCT")
                elif raw_delta > 0 and r_curr < partner_r and d_factor < 1.0:
                    dampened_delta = raw_delta * d_factor
                    p_flags.append(f"ICE_OUT_NOVICE_DAMPENED_{int((1-d_factor)*100)}PCT")

            if is_tournament:
                final_delta = dampened_delta
                p_flags.append("TOURNAMENT_UNCAPPED")
            elif is_elevator:
                max_el = cfg.get("MAX_ELEVATOR_DELTA", 0.7500) or 0.7500
                final_delta = max(-max_el, min(max_el, dampened_delta))
            else:
                cap_24 = cfg.get("MAX_24H_EXCHANGE_CAP", 0.1500) or 0.1500
                final_delta = max(-cap_24, min(cap_24, dampened_delta))
                if abs(dampened_delta) > cap_24:
                    p_flags.append("24H_EXCHANGE_CAP_CLAMPED")

            new_r = max(0.0000, min(6.9999, r_curr + final_delta))

            sigma_info = cfg.get("RD_INFO_VARIANCE", 65.0) or 65.0
            inv_prior = 1.0 / (p_rd**2)
            inv_info = (mc * s_margin * (g_opp**2)) / (sigma_info**2)
            new_rd = max(30.0, min(350.0, math.sqrt(1.0 / (inv_prior + inv_info))))

            s_rd = max(0.0, min(1.0, (350.0 - new_rd) / (350.0 - 30.0)))
            new_matches = p_data["verified_matches_count"] + (0 if is_dry_run else 1)
            new_opps = p_data["unique_opponents_count"] + (0 if is_dry_run else 1)
            s_match = min(1.0, new_matches / 5.0)
            s_opp = min(1.0, new_opps / 3.0)
            accuracy_pct = round(((0.50 * s_rd) + (0.25 * s_match) + (0.25 * s_opp)) * 100.0, 2)

            is_prov = 0 if (new_rd <= 100.0 and new_matches >= 5 and new_opps >= 3) else 1
            cal_tier = "ANCHOR" if accuracy_pct >= 90.0 else ("VERIFIED" if accuracy_pct >= 70.0 else "PROVISIONAL")

            results.append({
                "player_id": p_data["player_id"],
                "display_name": p_data["display_name"],
                "pre_r": r_curr,
                "post_r": round(new_r, 4),
                "delta_r": round(final_delta, 4),
                "pre_rd": p_rd,
                "post_rd": round(new_rd, 3),
                "accuracy_pct": accuracy_pct,
                "calibration_tier": cal_tier,
                "is_provisional": is_prov,
                "is_elevator": 1 if is_elevator else 0,
                "guardrails": p_flags
            })

        return {
            "team_a_r": round(team_a_r, 4),
            "team_b_r": round(team_b_r, 4),
            "win_expectancy_a": round(exp_a, 4),
            "applied_s_margin": round(s_margin, 4),
            "applied_m_c": mc,
            "player_results": results
        }

# ==============================================================================
# 3. STREAMLIT FRONT-END INTERFACE
# ==============================================================================
st.set_page_config(page_title="RYFT Engine V.15 Platform", layout="wide")

st.sidebar.title("⚡ RYFT Engine V.15")
active_user = st.sidebar.selectbox("Operator:", ["Aniket (Admin)", "Manish", "Nithin", "Ritesh", "Scorekeeper Desk"])
st.sidebar.caption("Deterministic Micro Physics & Topological Calibration")

nav = st.sidebar.radio("Navigation", [
    "📊 System Dashboard", 
    "🎾 Matches & Scoring", 
    "👥 Players Roster", 
    "🏢 Venues & Locations (CRUD)", 
    "🌐 Hawking Regional Control", 
    "⚙️ Global Config Switches",
    "🤖 Validation AI Agent"
])

# ------------------------------------------------------------------------------
# TAB 1: SYSTEM DASHBOARD
# ------------------------------------------------------------------------------
if nav == "📊 System Dashboard":
    st.title("System Health & Real-Time Operational Overview")
    conn = get_db_connection()
    n_p = conn.execute("SELECT COUNT(*) FROM players WHERE calibration_tier != 'INACTIVE'").fetchone()[0]
    n_m = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    n_v = conn.execute("SELECT COUNT(*) FROM venues WHERE is_active = 1").fetchone()[0]
    n_c = conn.execute("SELECT COUNT(*) FROM locations WHERE location_type = 'CITY'").fetchone()[0]
    conn.close()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active Players", n_p)
    m2.metric("Matches Executed", n_m)
    m3.metric("Active Venues", n_v)
    m4.metric("Active Cities", n_c)

    st.subheader("Live Verification Ledger & Audit Log")
    conn = get_db_connection()
    logs_df = pd.read_sql_query('''
        SELECT ml.logged_at, p.display_name, ml.pre_latent_mmr, ml.post_latent_mmr, 
               ml.delta_r, ml.post_rd, ml.post_accuracy_pct, ml.guardrails_triggered
        FROM match_logs ml
        JOIN players p ON ml.player_id = p.player_id
        ORDER BY ml.logged_at DESC LIMIT 15
    ''', conn)
    conn.close()
    if not logs_df.empty:
        st.dataframe(logs_df, use_container_width=True)
    else:
        st.info("No match audits committed yet. Log a match under 'Matches & Scoring'.")

# ------------------------------------------------------------------------------
# TAB 2: MATCHES & SCORING (SIMULATE, SAVE, UNDO)
# ------------------------------------------------------------------------------
elif nav == "🎾 Matches & Scoring":
    st.title("Match Simulation & Scoring Hub")
    conn = get_db_connection()
    p_rows = conn.execute("SELECT * FROM players WHERE calibration_tier != 'INACTIVE' ORDER BY display_name ASC").fetchall()
    v_rows = conn.execute("SELECT venue_id, venue_name FROM venues WHERE is_active = 1").fetchall()
    f_rows = conn.execute("SELECT format_id, format_name FROM match_formats WHERE is_active = 1").fetchall()
    conn.close()

    p_map = {f"{p['display_name']} ({p['latent_mmr']:.2f} | RD:{p['rating_deviation']:.0f} | {p['calibration_tier']})": p['player_id'] for p in p_rows}
    v_map = {v["venue_name"]: v["venue_id"] for v in v_rows}
    f_map = {f["format_name"]: f["format_id"] for f in f_rows}

    c_f, c_v, c_m = st.columns(3)
    fmt_sel = c_f.selectbox("Scoring Format", list(f_map.keys()))
    ven_sel = c_v.selectbox("Contested Venue", list(v_map.keys()))
    mode_sel = c_m.radio("Game Configuration", ["2v2 Doubles", "1v1 Singles"], horizontal=True)

    st.markdown("---")
    t_a, t_b = st.columns(2)
    with t_a:
        st.markdown("### 🔵 Team A")
        p1_pick = st.selectbox("Player A1", ["-- Select --"] + list(p_map.keys()), key="p1")
        p2_pick = "-- None --"
        if mode_sel == "2v2 Doubles":
            p2_pick = st.selectbox("Player A2", ["-- Select --"] + list(p_map.keys()), key="p2")
        score_a = st.number_input("Team A Score", min_value=0, value=2)
        games_a = st.number_input("Team A Games Won", min_value=0, value=12)

    with t_b:
        st.markdown("### 🔴 Team B")
        p3_pick = st.selectbox("Player B1", ["-- Select --"] + list(p_map.keys()), key="p3")
        p4_pick = "-- None --"
        if mode_sel == "2v2 Doubles":
            p4_pick = st.selectbox("Player B2", ["-- Select --"] + list(p_map.keys()), key="p4")
        score_b = st.number_input("Team B Score", min_value=0, value=0)
        games_b = st.number_input("Team B Games Won", min_value=0, value=4)

    col_sim, col_save = st.columns(2)
    run_sim = col_sim.button("🔬 Dry Run (Simulate Only)", use_container_width=True)
    run_save = col_save.button("💾 Verify & Save Match Record", type="primary", use_container_width=True)

    if run_sim or run_save:
        is_doubles = (mode_sel == "2v2 Doubles")
        if p1_pick == "-- Select --" or p3_pick == "-- Select --" or (is_doubles and (p2_pick == "-- Select --" or p4_pick == "-- Select --")):
            st.error("Assign active players to all required roster slots before running match equations.")
        else:
            p1_id, p3_id = p_map[p1_pick], p_map[p3_pick]
            p2_id = p_map[p2_pick] if is_doubles else None
            p4_id = p_map[p4_pick] if is_doubles else None

            conn = get_db_connection()
            p1_d = dict(conn.execute("SELECT * FROM players WHERE player_id = ?", (p1_id,)).fetchone())
            p3_d = dict(conn.execute("SELECT * FROM players WHERE player_id = ?", (p3_id,)).fetchone())
            p2_d = dict(conn.execute("SELECT * FROM players WHERE player_id = ?", (p2_id,)).fetchone()) if is_doubles else None
            p4_d = dict(conn.execute("SELECT * FROM players WHERE player_id = ?", (p4_id,)).fetchone()) if is_doubles else None
            conn.close()

            res = RyftEngineV15.compute_match(
                p1_d, p2_d, p3_d, p4_d, score_a, score_b, 
                max(games_a, games_b), min(games_a, games_b),
                f_map[fmt_sel], v_map[ven_sel], is_singles=not is_doubles, is_dry_run=run_sim
            )

            st.success(f"Computation Finished • Win Odds: A ({res['win_expectancy_a']*100:.1f}%) vs B ({(1-res['win_expectancy_a'])*100:.1f}%) • Margin Factor: {res['applied_s_margin']}")
            
            st.dataframe(pd.DataFrame([
                {
                    "Player": r["display_name"],
                    "Pre Rating": r["pre_r"],
                    "Committed Delta": f"{r['delta_r']:+0.4f}",
                    "Post Latent": r["post_r"],
                    "RD Contraction": f"{r['pre_rd']:.1f} -> {r['post_rd']:.1f}",
                    "Accuracy Score": f"{r['accuracy_pct']:.1f}%",
                    "Calibration Tier": r["calibration_tier"],
                    "Active Guardrails": ", ".join(r["guardrails"]) if r["guardrails"] else "Standard Exchange"
                } for r in res["player_results"]
            ]), use_container_width=True)

            if run_save:
                conn = get_db_connection()
                m_id = f"M_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                ts = datetime.now(timezone.utc).isoformat()
                
                conn.execute('''
                    INSERT INTO matches (match_id, venue_id, format_id, is_singles, team_a_p1_id, team_a_p2_id,
                                        team_b_p1_id, team_b_p2_id, score_team_a, score_team_b, set_scores_json,
                                        games_winner, games_loser, pre_rating_a, pre_rating_b, win_expectancy_a,
                                        applied_m_c, applied_s_margin, delta_r_p1, delta_r_p2, delta_r_p3, delta_r_p4, match_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    m_id, v_map[ven_sel], f_map[fmt_sel], 0 if is_doubles else 1,
                    p1_id, p2_id, p3_id, p4_id, score_a, score_b, json.dumps([[games_a, games_b]]),
                    max(games_a, games_b), min(games_a, games_b), res["team_a_r"], res["team_b_r"], res["win_expectancy_a"],
                    res["applied_m_c"], res["applied_s_margin"],
                    res["player_results"][0]["delta_r"],
                    res["player_results"][1]["delta_r"] if is_doubles else 0.0,
                    res["player_results"][2]["delta_r"] if is_doubles else res["player_results"][1]["delta_r"],
                    res["player_results"][3]["delta_r"] if is_doubles else 0.0,
                    ts
                ))

                for r in res["player_results"]:
                    conn.execute('''
                        UPDATE players SET 
                            latent_mmr = ?, display_rating = ?, rating_deviation = ?,
                            rating_accuracy_pct = ?, calibration_tier = ?, is_provisional = ?,
                            verified_matches_count = verified_matches_count + 1,
                            matches_won_count = matches_won_count + ?,
                            matches_lost_count = matches_lost_count + ?,
                            rolling_90d_peak = max(rolling_90d_peak, ?),
                            last_match_time = ?
                        WHERE player_id = ?
                    ''', (
                        r["post_r"], r["post_r"], r["post_rd"], r["accuracy_pct"], r["calibration_tier"], r["is_provisional"],
                        1 if r["delta_r"] > 0 else 0, 1 if r["delta_r"] < 0 else 0, r["post_r"], ts, r["player_id"]
                    ))

                    conn.execute('''
                        INSERT INTO match_logs (log_id, match_id, player_id, pre_latent_mmr, post_latent_mmr,
                                               pre_rd, post_rd, pre_accuracy_pct, post_accuracy_pct, delta_r,
                                               is_elevator_active, guardrails_triggered, logged_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        f"LOG_{r['player_id']}_{m_id}", m_id, r["player_id"], r["pre_r"], r["post_r"],
                        r["pre_rd"], r["post_rd"], r["accuracy_pct"], r["accuracy_pct"], r["delta_r"],
                        r["is_elevator"], json.dumps(r["guardrails"]), ts
                    ))

                conn.execute("UPDATE venues SET total_matches_played = total_matches_played + 1 WHERE venue_id = ?", (v_map[ven_sel],))
                conn.commit()
                conn.close()
                st.balloons()
                st.success("✅ Match successfully committed to all databases! Player profiles and audit trails updated.")

    # --- 1-CLICK MATCH UNDO / ROLLBACK TOOL ---
    st.markdown("---")
    with st.expander("⚠️ Undo / Rollback Latest Match Entry"):
        st.caption("Accidentally entered an incorrect score? Revert the most recent match to restore prior ratings and uncertainty meters.")
        conn = get_db_connection()
        last_m = conn.execute("SELECT match_id, match_timestamp FROM matches ORDER BY match_timestamp DESC LIMIT 1").fetchone()
        
        if last_m:
            st.write(f"Latest Recorded Match: **{last_m['match_id']}** (Timestamp: {last_m['match_timestamp']})")
            if st.button("🚨 Revert This Match & Restore Ratings", type="secondary"):
                m_id = last_m["match_id"]
                logs = conn.execute("SELECT player_id, pre_latent_mmr, pre_rd, pre_accuracy_pct FROM match_logs WHERE match_id = ?", (m_id,)).fetchall()
                for l in logs:
                    conn.execute("""
                        UPDATE players SET 
                            latent_mmr = ?, 
                            display_rating = ?, 
                            rating_deviation = ?, 
                            rating_accuracy_pct = ?,
                            verified_matches_count = max(0, verified_matches_count - 1)
                        WHERE player_id = ?
                    """, (l["pre_latent_mmr"], l["pre_latent_mmr"], l["pre_rd"], l["pre_accuracy_pct"], l["player_id"]))
                
                conn.execute("DELETE FROM match_logs WHERE match_id = ?", (m_id,))
                conn.execute("DELETE FROM matches WHERE match_id = ?", (m_id,))
                conn.commit()
                st.warning(f"Match {m_id} successfully reverted! All ratings restored to pre-match states.")
                st.rerun()
        else:
            st.info("No recorded matches available to undo.")
        conn.close()

# ------------------------------------------------------------------------------
# TAB 3: PLAYERS ROSTER (WITH INACTIVATION & OVERRIDES)
# ------------------------------------------------------------------------------
elif nav == "👥 Players Roster":
    st.title("Player Roster & Calibration Inspector")
    conn = get_db_connection()
    players_df = pd.read_sql_query('''
        SELECT p.player_id, p.display_name, p.latent_mmr, p.rating_deviation, p.rating_accuracy_pct,
               p.calibration_tier, p.verified_matches_count, l.location_name as city
        FROM players p JOIN locations l ON p.home_city_id = l.location_id
        ORDER BY p.latent_mmr DESC
    ''', conn)
    conn.close()
    st.dataframe(players_df, use_container_width=True)

    c_add, c_edit = st.columns(2)
    with c_add:
        with st.expander("➕ Register New Player"):
            with st.form("add_player_form"):
                name = st.text_input("Player Full Name")
                init_r = st.number_input("Declared Skill MMR", 0.000, 6.999, 3.000, 0.025)
                conn = get_db_connection()
                cities = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'CITY'").fetchall()
                venues = conn.execute("SELECT venue_id, venue_name FROM venues WHERE is_active = 1").fetchall()
                conn.close()
                c_pick = st.selectbox("Home City", [c["location_name"] for c in cities])
                v_pick = st.selectbox("Home Venue (Optional)", ["None"] + [v["venue_name"] for v in venues])
                
                if st.form_submit_button("Commit Profile Registration"):
                    c_id = [c["location_id"] for c in cities if c["location_name"] == c_pick][0]
                    v_id = [v["venue_id"] for v in venues if v["venue_name"] == v_pick][0] if v_pick != "None" else None
                    p_uuid = f"P_{datetime.now().strftime('%d%H%M%S')}"
                    conn = get_db_connection()
                    conn.execute('''
                        INSERT INTO players (player_id, display_name, initial_rating, home_venue_id, home_city_id,
                                             home_country_code, latent_mmr, display_rating, rolling_90d_peak, rolling_180d_peak,
                                             rolling_365d_peak, rating_deviation)
                        VALUES (?, ?, ?, ?, ?, 'IND', ?, ?, ?, ?, ?, 350.0)
                    ''', (p_uuid, name, init_r, v_id, c_id, init_r, init_r, init_r, init_r, init_r))
                    conn.commit()
                    conn.close()
                    st.success(f"Registered {name}!")
                    st.rerun()

    with c_edit:
        with st.expander("✏️ Modify / Inactivate Player"):
            conn = get_db_connection()
            all_players = conn.execute("SELECT * FROM players ORDER BY display_name ASC").fetchall()
            conn.close()
            
            if all_players:
                p_select = st.selectbox("Select Player to Edit", [p["player_id"] for p in all_players], format_func=lambda x: [p["display_name"] for p in all_players if p["player_id"] == x][0])
                p_row = [p for p in all_players if p["player_id"] == p_select][0]

                with st.form("edit_player_form"):
                    e_name = st.text_input("Name", value=p_row["display_name"])
                    e_mmr = st.number_input("Latent MMR Override", value=float(p_row["latent_mmr"]), step=0.01)
                    e_rd = st.number_input("Rating Deviation (RD)", value=float(p_row["rating_deviation"]), step=1.0)
                    
                    col_t1, col_t2 = st.columns(2)
                    is_active = col_t1.checkbox("Active on Roster", value=(p_row["calibration_tier"] != "INACTIVE"))
                    is_quar = col_t2.checkbox("Quarantined (Freeze Gain)", value=bool(p_row["is_quarantined"]))
                    
                    b_sub, b_del = st.columns(2)
                    if b_sub.form_submit_button("Update Player"):
                        new_tier = p_row["calibration_tier"] if is_active else "INACTIVE"
                        conn = get_db_connection()
                        conn.execute('''
                            UPDATE players SET display_name = ?, latent_mmr = ?, display_rating = ?,
                                               rating_deviation = ?, calibration_tier = ?, is_quarantined = ?
                            WHERE player_id = ?
                        ''', (e_name, e_mmr, e_mmr, e_rd, new_tier, 1 if is_quar else 0, p_select))
                        conn.commit()
                        conn.close()
                        st.success("Player details updated!")
                        st.rerun()
                    
                    if b_del.form_submit_button("🗑️ Hard Delete Player"):
                        conn = get_db_connection()
                        m_played = conn.execute("SELECT COUNT(*) FROM match_logs WHERE player_id = ?", (p_select,)).fetchone()[0]
                        if m_played > 0:
                            st.error(f"Cannot permanently delete: Player has {m_played} recorded matches. Uncheck 'Active on Roster' to inactivate instead.")
                        else:
                            conn.execute("DELETE FROM players WHERE player_id = ?", (p_select,))
                            conn.commit()
                            st.warning(f"Player {p_row['display_name']} permanently deleted.")
                            st.rerun()
                        conn.close()

# ------------------------------------------------------------------------------
# TAB 4: VENUES & LOCATIONS (FULL CRUD & ALIAS MERGE)
# ------------------------------------------------------------------------------
elif nav == "🏢 Venues & Locations (CRUD)":
    st.title("Venues & Geospatial Topology Manager")
    st.caption("Manage Clubs, Cities, and Countries, and merge duplicate venue aliases.")

    sec = st.radio("Domain", ["🏟️ Venues", "🏙️ Cities", "🌍 Countries"], horizontal=True)
    conn = get_db_connection()

    # --- VENUES MANAGEMENT ---
    if sec == "🏟️ Venues":
        st.subheader("Active Venues Ledger")
        v_df = pd.read_sql_query('''
            SELECT v.venue_id, v.venue_name, l.location_name as city, v.country_code, 
                   v.court_count, v.is_verified, v.is_active, v.total_matches_played
            FROM venues v JOIN locations l ON v.city_id = l.location_id
        ''', conn)
        st.dataframe(v_df, use_container_width=True)

        # Merge Tool
        with st.expander("🔗 Venue Alias Merge & Clean-Up Tool"):
            st.caption("Merge duplicate or misspelled venues into a single verified venue.")
            v_all = conn.execute("SELECT venue_id, venue_name FROM venues").fetchall()
            v_dict = {v["venue_name"]: v["venue_id"] for v in v_all}
            
            col_m1, col_m2 = st.columns(2)
            source_venues = col_m1.multiselect("Select Duplicate / Typo Venues to Merge", list(v_dict.keys()))
            target_venue = col_m2.selectbox("Select Master Target Venue to Keep", list(v_dict.keys()))
            
            if st.button("Execute Venue Merge"):
                if not source_venues or not target_venue:
                    st.error("Select at least one duplicate venue and one master target venue.")
                else:
                    target_id = v_dict[target_venue]
                    for s_name in source_venues:
                        s_id = v_dict[s_name]
                        if s_id != target_id:
                            conn.execute("UPDATE matches SET venue_id = ? WHERE venue_id = ?", (target_id, s_id))
                            conn.execute("UPDATE players SET home_venue_id = ? WHERE home_venue_id = ?", (target_id, s_id))
                            conn.execute("DELETE FROM venues WHERE venue_id = ?", (s_id,))
                    conn.commit()
                    st.success(f"Merged {len(source_venues)} duplicate venue(s) into {target_venue}!")
                    st.rerun()

        col_v1, col_v2 = st.columns(2)
        with col_v1:
            with st.form("add_venue_form"):
                st.markdown("#### ➕ Add New Venue")
                v_name = st.text_input("Venue Name")
                cities = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'CITY'").fetchall()
                v_city = st.selectbox("City", [c["location_name"] for c in cities])
                v_courts = st.number_input("Court Count", 1, 30, 2)
                v_ver = st.checkbox("Verified Desk Override Authority", value=True)
                if st.form_submit_button("Register Venue"):
                    city_id = [c["location_id"] for c in cities if c["location_name"] == v_city][0]
                    v_id = f"VEN_{datetime.now().strftime('%H%M%S')}"
                    conn.execute("INSERT INTO venues (venue_id, venue_name, city_id, country_code, court_count, is_verified) VALUES (?, ?, ?, 'IND', ?, ?)",
                                 (v_id, v_name, city_id, v_courts, 1 if v_ver else 0))
                    conn.commit()
                    st.success(f"Registered {v_name}!")
                    st.rerun()

        with col_v2:
            st.markdown("#### ✏️ Modify / Delete Venue")
            v_all = conn.execute("SELECT * FROM venues").fetchall()
            if v_all:
                sel_v_id = st.selectbox("Select Venue", [v["venue_id"] for v in v_all], format_func=lambda x: [v["venue_name"] for v in v_all if v["venue_id"] == x][0])
                v_row = [v for v in v_all if v["venue_id"] == sel_v_id][0]
                
                with st.form("edit_venue_form"):
                    up_name = st.text_input("Clean Name", value=v_row["venue_name"])
                    up_courts = st.number_input("Courts", 1, 30, value=v_row["court_count"])
                    up_ver = st.checkbox("Verified Desk Authority", value=bool(v_row["is_verified"]))
                    up_act = st.checkbox("Active Venue", value=bool(v_row["is_active"]))
                    
                    e_col1, e_col2 = st.columns(2)
                    if e_col1.form_submit_button("Save Changes"):
                        conn.execute("UPDATE venues SET venue_name = ?, court_count = ?, is_verified = ?, is_active = ? WHERE venue_id = ?",
                                     (up_name, up_courts, 1 if up_ver else 0, 1 if up_act else 0, sel_v_id))
                        conn.commit()
                        st.success("Venue updated.")
                        st.rerun()
                    if e_col2.form_submit_button("🗑️ Delete Venue"):
                        m_count = conn.execute("SELECT COUNT(*) FROM matches WHERE venue_id = ?", (sel_v_id,)).fetchone()[0]
                        if m_count > 0:
                            st.error(f"Cannot delete: {m_count} match records are linked to it. Uncheck 'Active Venue' to inactivate instead.")
                        else:
                            conn.execute("DELETE FROM venues WHERE venue_id = ?", (sel_v_id,))
                            conn.commit()
                            st.warning(f"Deleted venue {v_row['venue_name']}.")
                            st.rerun()

    # --- CITIES MANAGEMENT ---
    elif sec == "🏙️ Cities":
        st.subheader("Registered Cities")
        c_df = pd.read_sql_query('''
            SELECT l.location_id, l.location_name as city, p.location_name as country, 
                   l.active_bridge_count, l.hawking_offset, l.suggested_offset, l.readiness_score
            FROM locations l LEFT JOIN locations p ON l.parent_id = p.location_id
            WHERE l.location_type = 'CITY'
        ''', conn)
        st.dataframe(c_df, use_container_width=True)

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            with st.form("add_city_form"):
                st.markdown("#### ➕ Add New City")
                new_c_name = st.text_input("City Name")
                countries = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'COUNTRY'").fetchall()
                parent_c = st.selectbox("Parent Country", [ct["location_name"] for ct in countries])
                if st.form_submit_button("Create City Node"):
                    parent_id = [ct["location_id"] for ct in countries if ct["location_name"] == parent_c][0]
                    c_uuid = f"LOC_{new_c_name[:3].upper()}_{datetime.now().strftime('%S')}"
                    conn.execute("INSERT INTO locations (location_id, location_type, location_name, parent_id, country_code) VALUES (?, 'CITY', ?, ?, 'IND')",
                                 (c_uuid, new_c_name, parent_id))
                    conn.commit()
                    st.success(f"Added city node {new_c_name}!")
                    st.rerun()

        with col_c2:
            st.markdown("#### ✏️ Modify / Delete City")
            c_all = conn.execute("SELECT * FROM locations WHERE location_type = 'CITY'").fetchall()
            if c_all:
                sel_c_id = st.selectbox("Select City", [c["location_id"] for c in c_all], format_func=lambda x: [c["location_name"] for c in c_all if c["location_id"] == x][0])
                c_curr = [c for c in c_all if c["location_id"] == sel_c_id][0]

                with st.form("edit_city_form"):
                    renamed_c = st.text_input("Rename City", value=c_curr["location_name"])
                    b1, b2 = st.columns(2)
                    if b1.form_submit_button("Update City"):
                        conn.execute("UPDATE locations SET location_name = ? WHERE location_id = ?", (renamed_c, sel_c_id))
                        conn.commit()
                        st.success("City renamed.")
                        st.rerun()
                    if b2.form_submit_button("🗑️ Delete City"):
                        p_linked = conn.execute("SELECT COUNT(*) FROM players WHERE home_city_id = ?", (sel_c_id,)).fetchone()[0]
                        v_linked = conn.execute("SELECT COUNT(*) FROM venues WHERE city_id = ?", (sel_c_id,)).fetchone()[0]
                        if p_linked > 0 or v_linked > 0:
                            st.error(f"Cannot delete: Linked to {p_linked} players and {v_linked} venues.")
                        else:
                            conn.execute("DELETE FROM locations WHERE location_id = ?", (sel_c_id,))
                            conn.commit()
                            st.warning(f"Deleted city {c_curr['location_name']}.")
                            st.rerun()

    # --- COUNTRIES MANAGEMENT ---
    elif sec == "🌍 Countries":
        st.subheader("Registered Countries")
        co_df = pd.read_sql_query("SELECT location_id, location_name, country_code FROM locations WHERE location_type = 'COUNTRY'", conn)
        st.dataframe(co_df, use_container_width=True)

        col_co1, col_co2 = st.columns(2)
        with col_co1:
            with st.form("add_country_form"):
                st.markdown("#### ➕ Add New Country Node")
                co_name = st.text_input("Country Name (e.g. United Arab Emirates)")
                co_code = st.text_input("ISO 3-Letter Code (e.g. UAE)").upper()
                if st.form_submit_button("Create Country Node"):
                    co_id = f"LOC_{co_code}"
                    conn.execute("INSERT INTO locations (location_id, location_type, location_name, country_code) VALUES (?, 'COUNTRY', ?, ?)",
                                 (co_id, co_name, co_code))
                    conn.commit()
                    st.success(f"Added {co_name} ({co_code})!")
                    st.rerun()

        with col_co2:
            st.markdown("#### ✏️ Delete Country")
            co_all = conn.execute("SELECT * FROM locations WHERE location_type = 'COUNTRY'").fetchall()
            if co_all:
                sel_co_id = st.selectbox("Select Country", [c["location_id"] for c in co_all], format_func=lambda x: [c["location_name"] for c in co_all if c["location_id"] == x][0])
                if st.button("🗑️ Delete Selected Country"):
                    child_cities = conn.execute("SELECT COUNT(*) FROM locations WHERE parent_id = ?", (sel_co_id,)).fetchone()[0]
                    if child_cities > 0:
                        st.error(f"Cannot delete: {child_cities} cities are assigned to this country.")
                    else:
                        conn.execute("DELETE FROM locations WHERE location_id = ?", (sel_co_id,))
                        conn.commit()
                        st.warning("Country deleted.")
                        st.rerun()
    conn.close()

# ------------------------------------------------------------------------------
# TAB 5: HAWKING REGIONAL CONTROL (SUGGESTED OFFSET MODAL)
# ------------------------------------------------------------------------------
elif nav == "🌐 Hawking Regional Control":
    st.title("Hawking Macro Normalization & Regional Offset Control")
    st.caption("Review municipal readiness, evaluate projected misalignments, and deploy regularized offsets.")

    conn = get_db_connection()
    cities = conn.execute("SELECT * FROM locations WHERE location_type = 'CITY'").fetchall()
    conn.close()

    for c in cities:
        st.markdown(f"### Municipality: {c['location_name']}")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Bridge Nodes (K)", c["active_bridge_count"])
        k2.metric("Intransitivity Index", f"{c['intransitivity_idx']:.3f}")
        k3.metric("Current Offset", f"{c['hawking_offset']:+0.4f}")
        k4.metric("Suggested Offset Required", f"{c['suggested_offset']:+0.4f}")

        with st.expander(f"Review & Apply Offset for {c['location_name']}"):
            suggested = float(c["suggested_offset"]) if c["suggested_offset"] != 0.0 else -0.0450
            approved_step = st.number_input(f"Approved Offset Step ({c['location_name']})", value=suggested, step=0.005, format="%.4f", key=f"inp_{c['location_id']}")
            
            if st.button(f"Apply Offset to {c['location_name']}", key=f"btn_{c['location_id']}"):
                conn = get_db_connection()
                conn.execute("UPDATE locations SET hawking_offset = hawking_offset + ? WHERE location_id = ?", (approved_step, c["location_id"]))
                conn.execute('''
                    UPDATE players SET 
                        latent_mmr = latent_mmr + (? * (latent_mmr / 4.50)),
                        display_rating = display_rating + (? * (latent_mmr / 4.50))
                    WHERE home_city_id = ? AND is_provisional = 0
                ''', (approved_step, approved_step, c["location_id"]))
                conn.commit()
                conn.close()
                st.success(f"Applied {approved_step:+0.4f} offset across verified players in {c['location_name']}!")
                st.rerun()

# ------------------------------------------------------------------------------
# TAB 6: GLOBAL CONFIG SWITCHES
# ------------------------------------------------------------------------------
elif nav == "⚙️ Global Config Switches":
    st.title("Algorithmic Bit Governance & Parameter Matrix")
    st.caption("Toggle bits on/off and modify operational parameters live without touching code.")

    conn = get_db_connection()
    configs = conn.execute("SELECT * FROM global_config ORDER BY param_key ASC").fetchall()
    conn.close()

    for cfg in configs:
        c1, c2, c3 = st.columns([3, 2, 2])
        c1.write(f"**{cfg['param_key']}** — *{cfg['description']}*")
        v = c2.number_input("Value", value=float(cfg["param_value"]), step=0.05, key=f"cfg_{cfg['param_key']}")
        act = c3.checkbox("Active", value=bool(cfg["is_active"]), key=f"act_{cfg['param_key']}")

        if v != cfg["param_value"] or act != bool(cfg["is_active"]):
            conn = get_db_connection()
            conn.execute("UPDATE global_config SET param_value = ?, is_active = ? WHERE param_key = ?", (v, 1 if act else 0, cfg["param_key"]))
            conn.commit()
            conn.close()
            st.toast(f"Saved {cfg['param_key']}")

# ------------------------------------------------------------------------------
# TAB 7: VALIDATION AI AGENT
# ------------------------------------------------------------------------------
elif nav == "🤖 Validation AI Agent":
    st.title("Validation AI Agent — Test Harness Suite")
    st.markdown("""
    Use this pre-engineered master prompt in **Google AI Studio** or **Gemini Pro** to generate synthetic padel match fixtures, inject edge-case smurfs, and stress-test our engine.
    """)

    validation_prompt = """You are the Senior Algorithmic QA Lead for the RYFT Padel Rating Engine (Version V.15). 
Your objective is to generate rigorous, sequential test cases to stress-test our implementation and certify that it is mathematically bullet-proof for real-world launch.

SYSTEM ENVIRONMENT UNDER TEST:
• Scale: 0.0000 to 6.9999 (Bit 1)
• Exponential Anchor Carry: Cubic Power-Mean (p=3.0) gives a 70/30 weight to the stronger doubles partner (Bit 4)
• Logistic Win Expectancy: Beta = 2.0 (Bit 5)
• Score Entropy: S_margin in [0.80, 1.20] (Bit 6)
• Continuous Volatility Decay: K_base from 0.400 down to 0.080 (Bit 7)
• Pro Drag: Exponential drag above 6.3000 (Bit 8)
• Directional Asymmetric Ice-Out: Dampens anchor loss on freezeout loss; dampens novice gain on carried win (Bit 10)
• Glicko Uncertainty Contraction: g(RD) opponent buffering and post-match Bayesian contraction with sigma_info=65.0 (Bit 11)
• Elevator Protocol: Triples K on provisional blowout and overrides daily cap up to 0.7500 (Bit 12)
• Anti-Farming Ceilings: Multi-window caps (24h default 0.1500; 6+ player session 0.3000; tournament uncapped) (Bits 13–15)
• 3-Tier Rating Accuracy & Tri-Gate: Provisional [PR], Verified, and Anchor tiers governed by RD <= 100, matches >= 5, and unique opponents >= 3 (Bit 20, Bit 25)
• Hawking Macro Diffusion: Traveler Bridge Nodes (K >= 1) with Tikhonov damping W_conf = K/(K+3.0) and Jacobian elasticity pro scaling (Bits 20–22)

Generate 5 sequential test fixtures using named players across Bengaluru and Delhi, providing participant states, computations, guardrails fired, and post-match criteria."""

    st.text_area("Master Test Prompt for Google AI Studio:", value=validation_prompt, height=350)
