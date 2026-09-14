import streamlit as st
import sqlite3
import math
import json
import random
import uuid
from datetime import datetime

# ==============================================================================
# STREAMLIT CONFIGURATION
# ==============================================================================
st.set_page_config(
    page_title="RYFT V.15 Rating Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = "ryft_master.db"

# ==============================================================================
# DATABASE INITIALIZATION & SEEDING
# ==============================================================================
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # 1. Locations Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            location_id TEXT PRIMARY KEY,
            location_type TEXT NOT NULL,
            location_name TEXT NOT NULL,
            parent_id TEXT,
            intransitivity_idx REAL DEFAULT 0.0000,
            hawking_offset REAL DEFAULT 0.0000,
            suggested_offset REAL DEFAULT 0.0000,
            readiness_score REAL DEFAULT 0.00,
            active_bridge_count INTEGER DEFAULT 0,
            total_active_players INTEGER DEFAULT 0,
            total_matches_played INTEGER DEFAULT 0,
            median_latent_mmr REAL DEFAULT 3.000,
            highest_player_mmr REAL DEFAULT 3.000,
            lowest_player_mmr REAL DEFAULT 3.000,
            updated_at TEXT
        )
    ''')

    # 2. Venues Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS venues (
            venue_id TEXT PRIMARY KEY,
            venue_name TEXT NOT NULL,
            raw_input_name TEXT,
            is_verified INTEGER DEFAULT 0,
            city_id TEXT,
            country_code TEXT,
            court_count INTEGER DEFAULT 1,
            total_matches_played INTEGER DEFAULT 0,
            unique_players_count INTEGER DEFAULT 0,
            tournaments_hosted_count INTEGER DEFAULT 0,
            followers_count INTEGER DEFAULT 0,
            matches_hosted_count INTEGER DEFAULT 0,
            sessions_hosted_count INTEGER DEFAULT 0,
            city_bridge_matches_count INTEGER DEFAULT 0,
            country_bridge_matches_count INTEGER DEFAULT 0,
            average_player_mmr REAL DEFAULT 3.000,
            created_at TEXT
        )
    ''')

    # 3. Match Formats Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS match_formats (
            format_id TEXT PRIMARY KEY,
            format_name TEXT NOT NULL,
            category TEXT NOT NULL,
            mc_weight REAL NOT NULL DEFAULT 1.00,
            total_points INTEGER,
            target_games INTEGER,
            is_session_bound INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # 4. Players Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS players (
            player_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            initial_rating REAL NOT NULL DEFAULT 3.000,
            home_venue_id TEXT,
            home_city_id TEXT,
            home_country_code TEXT,
            latent_mmr REAL NOT NULL DEFAULT 3.000,
            display_rating REAL NOT NULL DEFAULT 3.00,
            rolling_90d_peak REAL NOT NULL DEFAULT 3.000,
            rolling_180d_peak REAL NOT NULL DEFAULT 3.000,
            rolling_365d_peak REAL NOT NULL DEFAULT 3.000,
            tournament_floor REAL NOT NULL DEFAULT 0.000,
            all_time_badge TEXT DEFAULT 'Intermediate',
            rating_deviation REAL NOT NULL DEFAULT 350.000,
            rating_accuracy_pct REAL NOT NULL DEFAULT 0.00,
            calibration_tier TEXT NOT NULL DEFAULT 'PROVISIONAL',
            is_provisional INTEGER NOT NULL DEFAULT 1,
            verified_matches_count INTEGER DEFAULT 0,
            matches_won_count INTEGER DEFAULT 0,
            matches_lost_count INTEGER DEFAULT 0,
            matches_tied_count INTEGER DEFAULT 0,
            win_pct REAL DEFAULT 0.00,
            loss_pct REAL DEFAULT 0.00,
            tie_pct REAL DEFAULT 0.00,
            unique_opponents_count INTEGER DEFAULT 0,
            unique_partners_count INTEGER DEFAULT 0,
            unique_venues_count INTEGER DEFAULT 0,
            unique_cities_count INTEGER DEFAULT 0,
            unique_countries_count INTEGER DEFAULT 0,
            tournaments_played_count INTEGER DEFAULT 0,
            highest_tournament_stage TEXT DEFAULT 'NONE',
            bridge_matches_count INTEGER DEFAULT 0,
            bridge_players_encountered INTEGER DEFAULT 0,
            is_active_bridge INTEGER DEFAULT 0,
            graph_centrality REAL DEFAULT 0.2000,
            connectedness_score REAL DEFAULT 0.00,
            current_win_streak INTEGER DEFAULT 0,
            longest_win_streak INTEGER DEFAULT 0,
            is_quarantined INTEGER DEFAULT 0,
            is_anchor INTEGER DEFAULT 0,
            is_ceiling_anchor INTEGER DEFAULT 0,
            is_dummy INTEGER DEFAULT 0,
            last_match_time TEXT,
            created_at TEXT
        )
    ''')

    # 5. Matches Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,
            venue_id TEXT,
            format_id TEXT,
            session_id TEXT,
            session_players INTEGER DEFAULT 0,
            is_singles INTEGER DEFAULT 0,
            is_tournament INTEGER DEFAULT 0,
            is_venue_bridge INTEGER DEFAULT 0,
            is_city_bridge INTEGER DEFAULT 0,
            is_country_bridge INTEGER DEFAULT 0,
            team_a_p1_id TEXT,
            team_a_p2_id TEXT,
            team_b_p1_id TEXT,
            team_b_p2_id TEXT,
            score_team_a INTEGER,
            score_team_b INTEGER,
            set_scores_json TEXT,
            games_winner INTEGER,
            games_loser INTEGER,
            pre_rating_a REAL,
            pre_rating_b REAL,
            win_expectancy_a REAL,
            applied_m_c REAL,
            applied_s_margin REAL,
            applied_ice_out_p1 REAL DEFAULT 1.00,
            applied_ice_out_p2 REAL DEFAULT 1.00,
            applied_ice_out_p3 REAL DEFAULT 1.00,
            applied_ice_out_p4 REAL DEFAULT 1.00,
            applied_g_buffer REAL DEFAULT 1.000,
            delta_r_p1 REAL,
            delta_r_p2 REAL DEFAULT 0.000,
            delta_r_p3 REAL,
            delta_r_p4 REAL DEFAULT 0.000,
            match_timestamp TEXT
        )
    ''')

    # 6. Match Logs Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS match_logs (
            log_id TEXT PRIMARY KEY,
            match_id TEXT,
            player_id TEXT,
            pre_latent_mmr REAL,
            post_latent_mmr REAL,
            pre_display_rating REAL,
            post_display_rating REAL,
            pre_rd REAL,
            post_rd REAL,
            pre_accuracy_pct REAL,
            post_accuracy_pct REAL,
            delta_r REAL,
            is_elevator_active INTEGER DEFAULT 0,
            guardrails_triggered TEXT,
            logged_at TEXT,
            UNIQUE(match_id, player_id)
        )
    ''')

    # 7. Global Config Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS global_config (
            param_key TEXT PRIMARY KEY,
            param_value REAL NOT NULL,
            description TEXT NOT NULL,
            updated_at TEXT
        )
    ''')

    # 8. Config Changelog Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS config_changelog (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            param_key TEXT,
            old_value REAL,
            new_value REAL,
            changed_by TEXT,
            reason TEXT,
            changed_at TEXT
        )
    ''')

    # 9. Synthetic Ghosts Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS synthetic_ghosts (
            ghost_id TEXT PRIMARY KEY,
            ghost_name TEXT NOT NULL,
            playstyle TEXT NOT NULL,
            assigned_mmr REAL NOT NULL,
            target_city TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            sims_run_count INTEGER DEFAULT 0,
            win_loss_ratio REAL DEFAULT 0.500,
            created_at TEXT
        )
    ''')

    # Seed Default Formats
    c.execute('SELECT COUNT(*) FROM match_formats')
    if c.fetchone()[0] == 0:
        formats = [
            ('STD_B03', 'Best of 3 Sets', 'MULTI_SET', 1.00, None, None, 0, 1),
            ('STD_B05', 'Best of 5 Sets', 'MULTI_SET', 1.00, None, None, 0, 1),
            ('RACE_4', 'Race to 4 Games', 'RACE_GAMES', 0.50, None, 4, 0, 1),
            ('RACE_6', 'Race to 6 Games', 'RACE_GAMES', 0.70, None, 6, 0, 1),
            ('RACE_7', 'Race to 7 Games', 'RACE_GAMES', 0.80, None, 7, 0, 1),
            ('AMER_24', 'Americano 24 Points', 'AMERICANO', 0.30, 24, None, 1, 1),
        ]
        c.executemany('INSERT INTO match_formats VALUES (?, ?, ?, ?, ?, ?, ?, ?)', formats)

    # Seed Master Parameters (With Module 9 Provisional Cohort Factors)
    defaults = [
        ('R_MIN', 0.0000, 'Absolute system floor bound'),
        ('R_MAX', 7.0000, 'Scale ceiling bound (Immutable 7.000 max)'),
        ('R_ELITE_THRESHOLD', 6.3000, 'Exponential elite drag threshold'),
        ('ELITE_DRAG_EXPONENT', 2.5000, 'Elite drag steepness exponent'),
        ('POWER_MEAN_P', 3.0000, 'Doubles cubic power-mean anchor exponent'),
        ('LOGISTIC_BETA', 2.0000, 'Logistic win expectancy scale factor'),
        ('K_MAX', 0.4000, 'Base volatility for R=0.0000 beginners'),
        ('K_MIN', 0.0800, 'Base volatility for R=7.0000 pros'),
        ('MARGIN_BASE', 0.8000, 'Score margin base floor factor'),
        ('MARGIN_SCALE', 0.4000, 'Score margin blowout scale factor'),
        ('ELEVATOR_MARGIN_THRESH', 1.1000, 'Provisional blowout acceleration margin gate'),
        ('ELEVATOR_ACCEL_FACTOR', 3.0000, 'Smurf Elevator acceleration multiplier (3x)'),
        ('MAX_ELEVATOR_DELTA', 0.7500, 'Maximum single-match delta cap for smurf elevator'),
        ('MAX_8H_EXCHANGE_CAP', 0.0000, '8h pair exchange ceiling (0 = inactive)'),
        ('MAX_12H_EXCHANGE_CAP', 0.0000, '12h pair exchange ceiling (0 = inactive)'),
        ('MAX_24H_EXCHANGE_CAP', 0.1500, '24h pair exchange ceiling (anti-farming)'),
        ('MAX_48H_EXCHANGE_CAP', 0.0000, '48h pair exchange ceiling (0 = inactive)'),
        ('SESSION_EXCHANGE_CAP', 0.3000, 'Verified 6+ player session cap'),
        ('MIN_SESSION_PLAYERS', 6.0000, 'Participant floor for elevated session cap'),
        ('RD_MIN', 30.0000, 'Certainty floor (minimum uncertainty)'),
        ('RD_MAX', 350.0000, 'Unrated initial uncertainty'),
        ('RD_INFO_VARIANCE', 65.0000, 'Bayesian match contraction variance denominator (sigma_info)'),
        ('INACTIVITY_CONSTANT', 12.0000, 'Temporal rust rate per inactive month (c)'),
        ('CENTRALITY_THRESHOLD', 0.2000, 'Eigenvector centrality trust threshold'),
        ('CENTRALITY_WINDOW_DAYS', 60.0000, 'Graph centrality calculation trailing days'),
        ('LAMBDA_BRIDGE_DAMPING', 3.0000, 'Tikhonov regularization bridge damping lambda'),
        ('CIRCUIT_BREAKER', 0.0250, 'Automatic monthly macro offset clamp'),
        ('ADMIN_OVERRIDE_MAX', 0.0750, 'Maximum human-approved macro offset window'),
        ('ACCURACY_WEIGHT_RD', 0.5000, 'Pillar 1 Certainty weight in accuracy score'),
        ('ACCURACY_WEIGHT_MATCHES', 0.2500, 'Pillar 2 Match volume weight in accuracy score'),
        ('ACCURACY_WEIGHT_DIVERSITY', 0.2500, 'Pillar 3 Network diversity weight in accuracy score'),
        ('TIER_PROVISIONAL_MAX', 69.9900, 'Score threshold separating Provisional from Verified'),
        ('TIER_VERIFIED_MAX', 89.9900, 'Score threshold separating Verified from Anchor'),
        ('TARGET_MATCHES_PROV', 3.0000, 'Target matches during placement tier'),
        ('TARGET_OPPONENTS_PROV', 2.0000, 'Target opponents during placement tier'),
        ('TARGET_MATCHES_VERIFIED', 5.0000, 'Target matches for verified status'),
        ('TARGET_OPPONENTS_VERIFIED', 3.0000, 'Target opponents for verified status'),
        ('TARGET_MATCHES_ANCHOR', 15.0000, 'Target matches for anchor status'),
        ('TARGET_OPPONENTS_ANCHOR', 8.0000, 'Target opponents for anchor status'),
        ('PROVISIONAL_RD_GATE', 100.0000, 'Tri-Gate maximum RD allowed to graduate'),
        ('PROVISIONAL_MIN_MATCHES', 5.0000, 'Tri-Gate minimum matches played'),
        ('PROVISIONAL_MIN_OPPONENTS', 3.0000, 'Tri-Gate minimum unique opponents faced'),
        ('COHORT_FACTOR_0_PROV', 1.0000, 'Omega Cohort Factor: 0 other players provisional (100% contraction)'),
        ('COHORT_FACTOR_1_PROV', 0.7500, 'Omega Cohort Factor: 1 other player provisional (75% contraction)'),
        ('COHORT_FACTOR_2_PROV', 0.5000, 'Omega Cohort Factor: 2 other players provisional (50% contraction)'),
        ('COHORT_FACTOR_3_PROV', 0.2500, 'Omega Cohort Factor: 3 other players provisional (25% contraction / sandbox)')
    ]

    for key, val, desc in defaults:
        c.execute('INSERT OR IGNORE INTO global_config (param_key, param_value, description, updated_at) VALUES (?, ?, ?, ?)',
                  (key, val, desc, datetime.utcnow().isoformat()))

    # Seed Default Locations
    c.execute('SELECT COUNT(*) FROM locations')
    if c.fetchone()[0] == 0:
        c.execute('''INSERT INTO locations (location_id, location_type, location_name, readiness_score, updated_at)
                     VALUES ('LOC_BLR', 'CITY', 'Bengaluru', 85.00, ?)''', (datetime.utcnow().isoformat(),))
        c.execute('''INSERT INTO locations (location_id, location_type, location_name, readiness_score, updated_at)
                     VALUES ('LOC_BOM', 'CITY', 'Mumbai', 90.00, ?)''', (datetime.utcnow().isoformat(),))
        c.execute('''INSERT INTO locations (location_id, location_type, location_name, readiness_score, updated_at)
                     VALUES ('LOC_DXB', 'CITY', 'Dubai', 95.00, ?)''', (datetime.utcnow().isoformat(),))

    # Seed Default Venues
    c.execute('SELECT COUNT(*) FROM venues')
    if c.fetchone()[0] == 0:
        c.execute('''INSERT INTO venues (venue_id, venue_name, city_id, country_code, is_verified, court_count, created_at)
                     VALUES ('VEN_DEPOT18', 'Depot18 Koramangala', 'LOC_BLR', 'IND', 1, 4, ?)''', (datetime.utcnow().isoformat(),))
        c.execute('''INSERT INTO venues (venue_id, venue_name, city_id, country_code, is_verified, court_count, created_at)
                     VALUES ('VEN_PNP', 'PNP Indiranagar', 'LOC_BLR', 'IND', 1, 2, ?)''', (datetime.utcnow().isoformat(),))

    # Seed Reference Players (Including Shane, Aniket, Moksh, Arpan, and Anchors)
    c.execute('SELECT COUNT(*) FROM players')
    if c.fetchone()[0] == 0:
        ref_players = [
            ('P_SHANE', 'Shane Biddiah', 1.500, 1.500, 1.50, 350.000, 'PROVISIONAL', 1, 'VEN_DEPOT18', 'LOC_BLR', 'IND'),
            ('P_ANIKET', 'Aniket Sanjeev', 2.200, 2.200, 2.20, 100.000, 'PROVISIONAL', 1, 'VEN_DEPOT18', 'LOC_BLR', 'IND'),
            ('P_MOKSH', 'Moksh Mridul', 1.200, 1.200, 1.20, 350.000, 'PROVISIONAL', 1, 'VEN_DEPOT18', 'LOC_BLR', 'IND'),
            ('P_ARPAN', 'Arpan Khosla', 1.000, 1.000, 1.00, 350.000, 'PROVISIONAL', 1, 'VEN_DEPOT18', 'LOC_BLR', 'IND'),
            ('P_PRIYA', 'Priya Sharma', 2.800, 2.800, 2.80, 40.000, 'VERIFIED', 0, 'VEN_DEPOT18', 'LOC_BLR', 'IND'),
            ('P_MANISH', 'Manish Mohanraj', 2.820, 2.820, 2.82, 50.000, 'VERIFIED', 0, 'VEN_PNP', 'LOC_BLR', 'IND'),
            ('P_ANJALI', 'Anjali Rao', 4.900, 4.900, 4.90, 40.000, 'ANCHOR', 0, 'VEN_DEPOT18', 'LOC_BOM', 'IND'),
            ('P_ROHAN', 'Rohan Bopanna (Pro)', 6.450, 6.450, 6.45, 35.000, 'ANCHOR', 0, 'VEN_DEPOT18', 'LOC_BOM', 'IND'),
            ('P_TARIQ', 'Tariq Al-Mansoor', 6.380, 6.380, 6.38, 32.000, 'ANCHOR', 0, 'VEN_DEPOT18', 'LOC_DXB', 'UAE'),
        ]
        now_str = datetime.utcnow().isoformat()
        for pid, name, init_r, lat_r, disp_r, rd, tier, is_prov, ven, city, ccode in ref_players:
            c.execute('''
                INSERT INTO players (
                    player_id, display_name, initial_rating, latent_mmr, display_rating,
                    rating_deviation, calibration_tier, is_provisional, home_venue_id,
                    home_city_id, home_country_code, rolling_90d_peak, rolling_180d_peak,
                    rolling_365d_peak, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (pid, name, init_r, lat_r, disp_r, rd, tier, is_prov, ven, city, ccode, lat_r, lat_r, lat_r, now_str))

    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# CONFIG LOADER & MATH UTILITIES
# ==============================================================================
def load_config():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT param_key, param_value FROM global_config')
    config = {row['param_key']: row['param_value'] for row in c.fetchall()}
    conn.close()
    return config

def calculate_power_mean(r1, r2, p=3.0):
    return ((r1**p + r2**p) / 2.0) ** (1.0 / p)

def calculate_k_base(r, k_max=0.400, k_min=0.080, r_max=7.000):
    return k_max - (r / r_max) * (k_max - k_min)

def calculate_decay_multiplier(r, r_max=7.000, r_elite=6.300, theta=2.5):
    if r >= r_max:
        return 0.0000001
    base_decay = (r_max - r) / r_max
    if r >= r_elite:
        drag = ((r_max - r) / (r_max - r_elite)) ** theta
        return max(0.0000001, base_decay * drag)
    return max(0.0010000, base_decay)

def calculate_glicko_buffer(rd_opp):
    q = 0.0057565
    return 1.0 / math.sqrt(1.0 + (3.0 * (q**2) * (rd_opp**2)) / (math.pi**2))

def calculate_post_match_rd(rd_old, format_mc, s_margin, rd_opp, omega_cohort, sigma_info=65.0, rd_min=30.0, rd_max=350.0):
    g_opp = calculate_glicko_buffer(rd_opp)
    inv_prior = 1.0 / (rd_old ** 2)
    inv_info = (format_mc * s_margin * (g_opp ** 2) * omega_cohort) / (sigma_info ** 2)
    rd_new = math.sqrt(1.0 / (inv_prior + inv_info))
    return max(rd_min, min(rd_max, round(rd_new, 3)))

def apply_ice_out_dampener(player_r, partner_r, delta_r):
    if partner_r is None:
        return delta_r
    gap = abs(player_r - partner_r)
    if gap >= 2.0:
        d_factor = 0.05
    elif gap >= 1.5:
        d_factor = 0.20
    elif gap >= 1.0:
        d_factor = 0.50
    else:
        d_factor = 1.00

    if delta_r < 0:  # Loss: anchor protected from partner freezeout
        return delta_r * d_factor if player_r > partner_r else delta_r
    else:            # Win: novice gain dampened against carry boosting
        return delta_r * d_factor if player_r < partner_r else delta_r

def compute_accuracy_and_tier(rd, matches_count, unique_opponents, config):
    w_rd = config.get('ACCURACY_WEIGHT_RD', 0.50)
    w_m = config.get('ACCURACY_WEIGHT_MATCHES', 0.25)
    w_d = config.get('ACCURACY_WEIGHT_DIVERSITY', 0.25)

    rd_max = config.get('RD_MAX', 350.0)
    rd_min = config.get('RD_MIN', 30.0)
    s_rd = max(0.0, min(1.0, (rd_max - rd) / (rd_max - rd_min)))

    # Gate targets
    target_m = config.get('TARGET_MATCHES_VERIFIED', 5.0)
    target_d = config.get('TARGET_OPPONENTS_VERIFIED', 3.0)

    s_m = min(1.0, matches_count / max(1.0, target_m))
    s_d = min(1.0, unique_opponents / max(1.0, target_d))

    accuracy_pct = round((w_rd * s_rd + w_m * s_m + w_d * s_d) * 100.0, 1)

    # Tri-Gate Provisional Check
    prov_rd_gate = config.get('PROVISIONAL_RD_GATE', 100.0)
    prov_min_m = config.get('PROVISIONAL_MIN_MATCHES', 5.0)
    prov_min_d = config.get('PROVISIONAL_MIN_OPPONENTS', 3.0)

    is_prov = not (rd <= prov_rd_gate and matches_count >= prov_min_m and unique_opponents >= prov_min_d)

    # Tier mapping
    anchor_m = config.get('TARGET_MATCHES_ANCHOR', 15.0)
    anchor_d = config.get('TARGET_OPPONENTS_ANCHOR', 8.0)
    tier_ver_max = config.get('TIER_VERIFIED_MAX', 89.99)

    if is_prov:
        tier = 'PROVISIONAL'
    elif rd <= 60.0 and matches_count >= anchor_m and unique_opponents >= anchor_d and accuracy_pct >= tier_ver_max:
        tier = 'ANCHOR'
    else:
        tier = 'VERIFIED'

    return accuracy_pct, tier, (1 if is_prov else 0)

# ==============================================================================
# UI HEADER & NAVIGATION
# ==============================================================================
st.markdown("""
<div style="background: linear-gradient(135deg, #090d16 0%, #1e293b 100%); padding: 18px 22px; border-radius: 8px; border-left: 6px solid #38bdf8; margin-bottom: 20px;">
    <h2 style="color: #38bdf8; margin: 0 0 4px 0; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px;">
        RYFT ENGINE PRIMARY V.15 — OPERATIONAL CONTROL CONSOLE
    </h2>
    <div style="color: #94a3b8; font-size: 13px;">
        Dual-Engine Architecture: Einstein Micro-Engine &bull; Hawking Macro Diffusion &bull; 3-Tier Rating Accuracy Governance &bull; Provisional Cohort Physics
    </div>
</div>
""", unsafe_allow_html=True)

nav_tabs = st.tabs([
    "⚡ Match Scorecard & Ingestion",
    "👥 Players Directory",
    "🏟️ Venues & Clubs",
    "🌐 Hawking Macro Engine",
    "⚙️ Algorithm & Parameter Governance",
    "📜 Match History & Audit Logs"
])

config = load_config()

# ==============================================================================
# TAB 1: MATCH SCORECARD & INGESTION
# ==============================================================================
with nav_tabs[0]:
    st.subheader("Match Scorecard Entry & Real-Time Ingestion")

    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT player_id, display_name, latent_mmr, rating_deviation, is_provisional, calibration_tier FROM players ORDER BY display_name')
    all_players = c.fetchall()
    c.execute('SELECT venue_id, venue_name FROM venues')
    all_venues = c.fetchall()
    c.execute('SELECT format_id, format_name, mc_weight FROM match_formats WHERE is_active = 1')
    all_formats = c.fetchall()
    conn.close()

    p_dict = {p['player_id']: f"{p['display_name']} [{ 'PR' if p['is_provisional'] else p['calibration_tier'] }] ({p['latent_mmr']:.3f})" for p in all_players}
    p_keys = list(p_dict.keys())

    v_dict = {v['venue_id']: v['venue_name'] for v in all_venues}
    f_dict = {f['format_id']: f"{f['format_name']} (M_C: {f['mc_weight']})" for f in all_formats}

    col_meta1, col_meta2, col_meta3 = st.columns(3)
    with col_meta1:
        sel_venue = st.selectbox("Contested Venue", options=list(v_dict.keys()), format_func=lambda x: v_dict[x])
    with col_meta2:
        sel_format = st.selectbox("Scoring Format", options=list(f_dict.keys()), format_func=lambda x: f_dict[x])
    with col_meta3:
        is_tournament = st.checkbox("Verified Tournament Desk Match (Uncapped)", value=False)

    st.markdown("---")
    col_tA, col_tB = st.columns(2)

    with col_tA:
        st.markdown("#### Team A")
        p1 = st.selectbox("Player 1 (Primary)", options=p_keys, index=0 if len(p_keys)>0 else None, format_func=lambda x: p_dict[x], key="p1")
        p2 = st.selectbox("Player 2 (Teammate)", options=p_keys, index=1 if len(p_keys)>1 else None, format_func=lambda x: p_dict[x], key="p2")
        score_a_s1 = st.number_input("Set 1 Games Won (Team A)", min_value=0, max_value=7, value=6, key="sa1")
        score_a_s2 = st.number_input("Set 2 Games Won (Team A)", min_value=0, max_value=7, value=6, key="sa2")

    with col_tB:
        st.markdown("#### Team B")
        p3 = st.selectbox("Player 3 (Primary)", options=p_keys, index=2 if len(p_keys)>2 else None, format_func=lambda x: p_dict[x], key="p3")
        p4 = st.selectbox("Player 4 (Teammate)", options=p_keys, index=3 if len(p_keys)>3 else None, format_func=lambda x: p_dict[x], key="p4")
        score_b_s1 = st.number_input("Set 1 Games Won (Team B)", min_value=0, max_value=7, value=0, key="sb1")
        score_b_s2 = st.number_input("Set 2 Games Won (Team B)", min_value=0, max_value=7, value=1, key="sb2")

    # Duplicate selection guardrail
    has_duplicates = len({p1, p2, p3, p4}) < 4
    if has_duplicates:
        st.error("⚠️ Validation Error: Duplicate player detected! All 4 participants in doubles must be unique.")

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        dry_run = st.button("🔬 Dry Run (Simulate Math)", use_container_width=True, disabled=has_duplicates)
    with col_btn2:
        commit_match = st.button("💾 Verify & Save Match", type="primary", use_container_width=True, disabled=has_duplicates)

    if (dry_run or commit_match) and not has_duplicates:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM players WHERE player_id IN (?, ?, ?, ?)', (p1, p2, p3, p4))
        p_rows = {row['player_id']: dict(row) for row in c.fetchall()}

        # 1. Team Power-Mean Ratings
        p1_r, p2_r = p_rows[p1]['latent_mmr'], p_rows[p2]['latent_mmr']
        p3_r, p4_r = p_rows[p3]['latent_mmr'], p_rows[p4]['latent_mmr']

        p_exponent = config.get('POWER_MEAN_P', 3.0)
        team_a_r = calculate_power_mean(p1_r, p2_r, p_exponent)
        team_b_r = calculate_power_mean(p3_r, p4_r, p_exponent)

        # 2. Logistic Odds
        beta = config.get('LOGISTIC_BETA', 2.0)
        expected_a = 1.0 / (1.0 + 10.0 ** ((team_b_r - team_a_r) / beta))
        expected_b = 1.0 - expected_a

        # 3. Match Outcome & Margin
        sets_a = (1 if score_a_s1 > score_b_s1 else 0) + (1 if score_a_s2 > score_b_s2 else 0)
        sets_b = (1 if score_b_s1 > score_a_s1 else 0) + (1 if score_b_s2 > score_a_s2 else 0)
        actual_a = 1.0 if sets_a > sets_b else (0.0 if sets_b > sets_a else 0.5)

        total_games_w = (score_a_s1 + score_a_s2) if actual_a == 1.0 else (score_b_s1 + score_b_s2)
        total_games_l = (score_b_s1 + score_b_s2) if actual_a == 1.0 else (score_a_s1 + score_a_s2)
        total_games = total_games_w + total_games_l

        m_base = config.get('MARGIN_BASE', 0.80)
        m_scale = config.get('MARGIN_SCALE', 0.40)
        s_margin = m_base + m_scale * ((total_games_w - total_games_l) / max(1, total_games))

        c.execute('SELECT mc_weight FROM match_formats WHERE format_id = ?', (sel_format,))
        format_mc = c.fetchone()['mc_weight']

        # 4. Provisional Count on Court (Omega Cohort calculation)
        court_players = [p1, p2, p3, p4]
        prov_map = {pid: (p_rows[pid]['rating_deviation'] > config.get('PROVISIONAL_RD_GATE', 100.0) or p_rows[pid]['is_provisional'] == 1) for pid in court_players}

        results = []
        players_to_compute = [
            (p1, True, p2, max(p_rows[p3]['rating_deviation'], p_rows[p4]['rating_deviation'])),
            (p2, True, p1, max(p_rows[p3]['rating_deviation'], p_rows[p4]['rating_deviation'])),
            (p3, False, p4, max(p_rows[p1]['rating_deviation'], p_rows[p2]['rating_deviation'])),
            (p4, False, p3, max(p_rows[p1]['rating_deviation'], p_rows[p2]['rating_deviation']))
        ]

        for pid, is_team_a, partner_id, opp_rd in players_to_compute:
            p_data = p_rows[pid]
            r_curr = p_data['latent_mmr']
            rd_curr = p_data['rating_deviation']
            is_prov = prov_map[pid]
            is_winner = (is_team_a and actual_a == 1.0) or (not is_team_a and actual_a == 0.0)

            # Volatility & Elevator
            k_base = calculate_k_base(r_curr, config.get('K_MAX', 0.40), config.get('K_MIN', 0.08), config.get('R_MAX', 7.0))
            is_elevator = False
            if is_prov and is_winner and s_margin >= config.get('ELEVATOR_MARGIN_THRESH', 1.10) and r_curr < config.get('R_ELITE_THRESHOLD', 6.30):
                k_base *= config.get('ELEVATOR_ACCEL_FACTOR', 3.0)
                is_elevator = True

            decay = calculate_decay_multiplier(r_curr, config.get('R_MAX', 7.0), config.get('R_ELITE_THRESHOLD', 6.30), config.get('ELITE_DRAG_EXPONENT', 2.5))
            g_buf = calculate_glicko_buffer(opp_rd)
            trust_w = 1.0 if p_data['is_quarantined'] == 0 else 0.0
            direction = 1.0 if is_team_a else -1.0
            score_err = actual_a - expected_a

            raw_delta = (k_base * decay * format_mc * s_margin * trust_w * g_buf) * (direction * score_err)

            # Ice-out dampener
            partner_r = p_rows[partner_id]['latent_mmr'] if partner_id else None
            dampened_delta = apply_ice_out_dampener(r_curr, partner_r, raw_delta)

            # Cap limits
            if is_tournament:
                final_delta = dampened_delta
            elif is_elevator:
                final_delta = min(config.get('MAX_ELEVATOR_DELTA', 0.750), dampened_delta)
            else:
                final_delta = max(-config.get('MAX_24H_EXCHANGE_CAP', 0.150), min(config.get('MAX_24H_EXCHANGE_CAP', 0.150), dampened_delta))

            # Omega Cohort Factor Calculation: Count OTHER provisional players
            other_prov_count = sum([1 for other_id in court_players if other_id != pid and prov_map[other_id]])
            if other_prov_count == 0:
                omega_cohort = config.get('COHORT_FACTOR_0_PROV', 1.00)
            elif other_prov_count == 1:
                omega_cohort = config.get('COHORT_FACTOR_1_PROV', 0.75)
            elif other_prov_count == 2:
                omega_cohort = config.get('COHORT_FACTOR_2_PROV', 0.50)
            else:
                omega_cohort = config.get('COHORT_FACTOR_3_PROV', 0.25)

            new_r = max(config.get('R_MIN', 0.0), min(config.get('R_MAX', 7.0) - 0.001, r_curr + final_delta))
            new_rd = calculate_post_match_rd(
                rd_curr, format_mc, s_margin, opp_rd, omega_cohort,
                config.get('RD_INFO_VARIANCE', 65.0), config.get('RD_MIN', 30.0), config.get('RD_MAX', 350.0)
            )

            # New counters
            new_matches_count = p_data['verified_matches_count'] + 1
            new_opponents_count = p_data['unique_opponents_count'] + 2  # Added 2 opponents

            new_acc, new_tier, new_is_prov = compute_accuracy_and_tier(new_rd, new_matches_count, new_opponents_count, config)

            guardrails_hit = []
            if is_elevator: guardrails_hit.append("ELEVATOR_3X_BOOST: Provisional blowout victory")
            if abs(dampened_delta) < abs(raw_delta): guardrails_hit.append("ICE_OUT_DAMPENED: Partner disparity protected")
            if abs(final_delta) < abs(dampened_delta): guardrails_hit.append("EXCHANGE_CAP_CLAMPED: Daily limit enforced")
            if omega_cohort < 1.0: guardrails_hit.append(f"COHORT_DAMPENED: {other_prov_count} other provisional on court (Omega: {omega_cohort:.2f})")
            if not guardrails_hit: guardrails_hit.append("Standard Exchange")

            results.append({
                'player_id': pid,
                'name': p_data['display_name'],
                'pre_mmr': r_curr,
                'delta': final_delta,
                'post_mmr': new_r,
                'pre_disp': p_data['display_rating'],
                'post_disp': round(new_r, 2),
                'rd_before': rd_curr,
                'rd_after': new_rd,
                'omega': omega_cohort,
                'accuracy': new_acc,
                'tier': new_tier,
                'is_prov': new_is_prov,
                'is_elevator': is_elevator,
                'guardrails': guardrails_hit
            })

        st.success(f"Match Computation Executed &bull; Odds: Team A ({expected_a*100:.1f}%) vs Team B ({expected_b*100:.1f}%) &bull; MOV Factor: {s_margin:.4f}")

        # Display results table
        res_display = [{
            'Player': r['name'],
            'Pre MMR': f"{r['pre_mmr']:.3f}",
            'Delta': f"{'+' if r['delta']>=0 else ''}{r['delta']:.4f}",
            'Post MMR': f"{r['post_mmr']:.3f}",
            'Post Display': f"{r['post_disp']:.2f}",
            'RD Shift': f"{r['rd_before']:.1f} ➔ {r['rd_after']:.1f}",
            'Ω Cohort': f"{r['omega']:.2f}",
            'Accuracy': f"{r['accuracy']:.1f}%",
            'Tier': r['tier'],
            'Tri-Gate': "✅ PASS" if r['is_prov'] == 0 else "❌ PROVISIONAL",
            'Guardrails Active': " | ".join(r['guardrails'])
        } for r in results]
        st.dataframe(res_display, use_container_width=True)

        # Atomic Commit
        if commit_match:
            match_id = str(uuid.uuid4())
            now_ts = datetime.utcnow().isoformat()
            set_scores_json = json.dumps([[score_a_s1, score_b_s1], [score_a_s2, score_b_s2]])

            c.execute('''
                INSERT INTO matches (
                    match_id, venue_id, format_id, is_tournament, team_a_p1_id, team_a_p2_id,
                    team_b_p1_id, team_b_p2_id, score_team_a, score_team_b, set_scores_json,
                    games_winner, games_loser, pre_rating_a, pre_rating_b, win_expectancy_a,
                    applied_m_c, applied_s_margin, delta_r_p1, delta_r_p2, delta_r_p3, delta_r_p4,
                    match_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                match_id, sel_venue, sel_format, (1 if is_tournament else 0), p1, p2, p3, p4,
                sets_a, sets_b, set_scores_json, total_games_w, total_games_l,
                team_a_r, team_b_r, expected_a, format_mc, s_margin,
                results[0]['delta'], results[1]['delta'], results[2]['delta'], results[3]['delta'],
                now_ts
            ))

            for r in results:
                log_id = f"{match_id}_{r['player_id']}"
                c.execute('''
                    INSERT INTO match_logs (
                        log_id, match_id, player_id, pre_latent_mmr, post_latent_mmr,
                        pre_display_rating, post_display_rating, pre_rd, post_rd,
                        pre_accuracy_pct, post_accuracy_pct, delta_r, is_elevator_active,
                        guardrails_triggered, logged_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    log_id, match_id, r['player_id'], r['pre_mmr'], r['post_mmr'],
                    r['pre_disp'], r['post_disp'], r['rd_before'], r['rd_after'],
                    p_rows[r['player_id']]['rating_accuracy_pct'], r['accuracy'], r['delta'],
                    (1 if r['is_elevator'] else 0), json.dumps(r['guardrails']), now_ts
                ))

                # Update Player record
                is_win = (r['delta'] > 0)
                c.execute('''
                    UPDATE players SET
                        latent_mmr = ?,
                        display_rating = ?,
                        rating_deviation = ?,
                        rating_accuracy_pct = ?,
                        calibration_tier = ?,
                        is_provisional = ?,
                        verified_matches_count = verified_matches_count + 1,
                        matches_won_count = matches_won_count + ?,
                        matches_lost_count = matches_lost_count + ?,
                        unique_opponents_count = unique_opponents_count + 2,
                        rolling_90d_peak = max(rolling_90d_peak, ?),
                        rolling_180d_peak = max(rolling_180d_peak, ?),
                        rolling_365d_peak = max(rolling_365d_peak, ?),
                        last_match_time = ?
                    WHERE player_id = ?
                ''', (
                    r['post_mmr'], r['post_disp'], r['rd_after'], r['accuracy'], r['tier'], r['is_prov'],
                    (1 if is_win else 0), (0 if is_win else 1),
                    r['post_mmr'], r['post_mmr'], r['post_mmr'], now_ts, r['player_id']
                ))

            # Update venue count
            c.execute('UPDATE venues SET total_matches_played = total_matches_played + 1 WHERE venue_id = ?', (sel_venue,))
            conn.commit()
            conn.close()
            st.balloons()
            st.success("✅ Match scorecard successfully verified, computed, and committed to Master DB!")

# ==============================================================================
# TAB 2: PLAYERS DIRECTORY
# ==============================================================================
with nav_tabs[1]:
    st.subheader("Master Player Ledger & Verification Status")
    conn = get_db_connection()
    df_players = conn.execute('''
        SELECT
            display_name AS "Name",
            latent_mmr AS "MMR (X.XXX)",
            display_rating AS "Display (X.XX)",
            rating_deviation AS "RD",
            rating_accuracy_pct AS "Accuracy %",
            calibration_tier AS "Tier",
            is_provisional AS "Provisional",
            verified_matches_count AS "Matches",
            unique_opponents_count AS "Opponents",
            rolling_90d_peak AS "90d Peak"
        FROM players
        ORDER BY latent_mmr DESC
    ''').fetchall()
    conn.close()

    p_table = [dict(row) for row in df_players]
    for row in p_table:
        row['Provisional'] = "🟡 [PR]" if row['Provisional'] == 1 else "🟢 Verified"
        row['Accuracy %'] = f"{row['Accuracy %']:.1f}%"
        row['RD'] = f"{row['RD']:.1f}"

    st.dataframe(p_table, use_container_width=True)

# ==============================================================================
# TAB 3: VENUES & CLUBS
# ==============================================================================
with nav_tabs[2]:
    st.subheader("Registered Facilities & Venue Bridges")
    conn = get_db_connection()
    venues_data = conn.execute('SELECT * FROM venues').fetchall()
    conn.close()
    st.dataframe([dict(v) for v in venues_data], use_container_width=True)

# ==============================================================================
# TAB 4: HAWKING MACRO ENGINE
# ==============================================================================
with nav_tabs[3]:
    st.subheader("Hawking Engine: Macro Calibration & Network Topologies")
    subtab1, subtab2 = st.tabs(["🏙️ Tab 1: Regional Calibrations", "🕸️ Tab 2: Graph Centrality Radar"])

    with subtab1:
        st.markdown("#### Regional Clusters & Bridge Densities")
        conn = get_db_connection()
        locs = conn.execute('SELECT * FROM locations').fetchall()
        conn.close()
        st.dataframe([dict(l) for l in locs], use_container_width=True)

        st.markdown("##### Apply Manual Calibration Offset")
        with st.form("hawking_offset_form"):
            c_target = st.selectbox("Select Target City", options=[l['location_id'] for l in locs], format_func=lambda x: x)
            offset_val = st.number_input("Proposed Shift (Clamp: ±0.0750)", min_value=-0.0750, max_value=0.0750, value=-0.0250, step=0.0010, format="%.4f")
            submit_offset = st.form_submit_button("Deploy Regional Sync Offset")

            if submit_offset:
                conn = get_db_connection()
                conn.execute('UPDATE locations SET hawking_offset = hawking_offset + ? WHERE location_id = ?', (offset_val, c_target))
                conn.commit()
                conn.close()
                st.success(f"Deployed offset of {offset_val:+.4f} to {c_target} across non-provisional players (Global Sync enabled).")

    with subtab2:
        st.markdown("#### Eigenvector Centrality & Disconnected Ring Filter")
        conn = get_db_connection()
        cent_data = conn.execute('''
            SELECT display_name, latent_mmr, rating_deviation, graph_centrality, unique_opponents_count
            FROM players
            ORDER BY graph_centrality DESC
        ''').fetchall()
        conn.close()
        st.dataframe([dict(r) for r in cent_data], use_container_width=True)

# ==============================================================================
# TAB 5: ALGORITHM & PARAMETER GOVERNANCE
# ==============================================================================
with nav_tabs[4]:
    st.subheader("Global Parameter Governance & Operational Controls")
    st.info("💡 Changes made here persist directly to the Master DB and govern all live rating physics instantly.")

    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM global_config ORDER BY param_key')
    params = c.fetchall()
    conn.close()

    # Split parameters into modules for easy navigation
    module_cohort = [p for p in params if 'COHORT' in p['param_key']]
    module_general = [p for p in params if 'COHORT' not in p['param_key']]

    st.markdown("### 🧩 Module 9: Provisional Cohort Factors ($\Omega_{\text{cohort}}$)")
    st.write("Controls the Bayesian $RD$ contraction speed when other players on court are provisional novices.")

    with st.form("cohort_params_form"):
        cohort_updates = {}
        cols = st.columns(4)
        for idx, p in enumerate(module_cohort):
            with cols[idx % 4]:
                cohort_updates[p['param_key']] = st.number_input(
                    label=p['param_key'],
                    value=float(p['param_value']),
                    min_value=0.05,
                    max_value=1.50,
                    step=0.05,
                    help=p['description']
                )
        save_cohort = st.form_submit_button("Save Cohort Parameters")
        if save_cohort:
            conn = get_db_connection()
            for k, v in cohort_updates.items():
                conn.execute('UPDATE global_config SET param_value = ?, updated_at = ? WHERE param_key = ?',
                             (v, datetime.utcnow().isoformat(), k))
            conn.commit()
            conn.close()
            st.success("Updated Provisional Cohort parameters!")
            st.rerun()

    st.markdown("### ⚙️ Modules 1–8: Core Rating, Elevator & Tri-Gate Parameters")
    with st.form("all_params_form"):
        updates = {}
        for p in module_general:
            col_k, col_v, col_d = st.columns([1.5, 1, 3])
            with col_k:
                st.code(p['param_key'])
            with col_v:
                updates[p['param_key']] = st.number_input(
                    label=p['param_key'],
                    value=float(p['param_value']),
                    step=0.01 if p['param_value'] < 10 else 1.0,
                    label_visibility="collapsed"
                )
            with col_d:
                st.caption(p['description'])
        save_all = st.form_submit_button("Commit Global Parameter Updates")
        if save_all:
            conn = get_db_connection()
            for k, v in updates.items():
                conn.execute('UPDATE global_config SET param_value = ?, updated_at = ? WHERE param_key = ?',
                             (v, datetime.utcnow().isoformat(), k))
            conn.commit()
            conn.close()
            st.success("Committed all parameter updates to master database!")
            st.rerun()

# ==============================================================================
# TAB 6: MATCH HISTORY & AUDIT LOGS
# ==============================================================================
with nav_tabs[5]:
    st.subheader("Immutable Match Ledger & Player Telemetry")
    conn = get_db_connection()
    logs = conn.execute('''
        SELECT
            ml.logged_at AS "Timestamp",
            p.display_name AS "Player",
            ml.pre_latent_mmr AS "Pre MMR",
            ml.delta_r AS "Delta",
            ml.post_latent_mmr AS "Post MMR",
            ml.pre_rd AS "Pre RD",
            ml.post_rd AS "Post RD",
            ml.post_accuracy_pct AS "Accuracy %",
            ml.is_elevator_active AS "Elevator",
            ml.guardrails_triggered AS "Guardrails"
        FROM match_logs ml
        JOIN players p ON ml.player_id = p.player_id
        ORDER BY ml.logged_at DESC
        LIMIT 50
    ''').fetchall()
    conn.close()

    formatted_logs = []
    for r in logs:
        d = dict(r)
        d['Delta'] = f"{'+' if d['Delta']>=0 else ''}{d['Delta']:.4f}"
        d['Pre MMR'] = f"{d['Pre MMR']:.3f}"
        d['Post MMR'] = f"{d['Post MMR']:.3f}"
        d['Elevator'] = "⚡ YES" if d['Elevator'] == 1 else "NO"
        formatted_logs.append(d)

    st.dataframe(formatted_logs, use_container_width=True)
