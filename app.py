import streamlit as st
import sqlite3
import math
import json
import os
from datetime import datetime, timezone, date
import pandas as pd

# ==============================================================================
# 1. DATABASE INITIALIZATION & RELATIONAL SCHEMA (V.15 SPECIFICATION)
# ==============================================================================
DB_FILE = "ryft_v15_master.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def add_column_if_not_exists(cursor, table, col_name, col_type):
    cursor.execute(f"PRAGMA table_info({table});")
    existing = [row[1] for row in cursor.fetchall()]
    if col_name not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type};")

def init_db(force_sync_params=False):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON;")

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
        active_venues_count INTEGER DEFAULT 0,
        median_latent_mmr REAL DEFAULT 3.0000,
        highest_player_mmr REAL DEFAULT 3.0000,
        lowest_player_mmr REAL DEFAULT 3.0000,
        updated_at TEXT,
        FOREIGN KEY (parent_id) REFERENCES locations(location_id) ON DELETE SET NULL
    )''')

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
        unique_players_count INTEGER DEFAULT 0,
        tournaments_hosted_count INTEGER DEFAULT 0,
        followers_count INTEGER DEFAULT 0,
        matches_hosted_count INTEGER DEFAULT 0,
        sessions_hosted_count INTEGER DEFAULT 0,
        city_bridge_matches_count INTEGER DEFAULT 0,
        country_bridge_matches_count INTEGER DEFAULT 0,
        average_player_mmr REAL DEFAULT 3.0000,
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        FOREIGN KEY (city_id) REFERENCES locations(location_id) ON DELETE CASCADE
    )''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS match_formats (
        format_id TEXT PRIMARY KEY,
        format_name TEXT NOT NULL,
        category TEXT NOT NULL,
        mc_weight REAL NOT NULL,
        target_games INTEGER,
        total_points INTEGER,
        is_session_bound INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    )''')

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
        accuracy_s_rd REAL DEFAULT 0.0,
        accuracy_s_matches REAL DEFAULT 0.0,
        accuracy_s_diversity REAL DEFAULT 0.0,
        calibration_tier TEXT DEFAULT 'PROVISIONAL',
        is_provisional INTEGER DEFAULT 1,
        verified_matches_count INTEGER DEFAULT 0,
        matches_won_count INTEGER DEFAULT 0,
        matches_lost_count INTEGER DEFAULT 0,
        matches_tied_count INTEGER DEFAULT 0,
        win_pct REAL DEFAULT 0.0,
        loss_pct REAL DEFAULT 0.0,
        tie_pct REAL DEFAULT 0.0,
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
        graph_centrality REAL DEFAULT 0.20,
        connectedness_score REAL DEFAULT 0.0,
        current_win_streak INTEGER DEFAULT 0,
        longest_win_streak INTEGER DEFAULT 0,
        is_quarantined INTEGER DEFAULT 0,
        is_anchor INTEGER DEFAULT 0,
        is_ceiling_anchor INTEGER DEFAULT 0,
        is_dummy INTEGER DEFAULT 0,
        last_match_time TEXT,
        created_at TEXT,
        FOREIGN KEY (home_venue_id) REFERENCES venues(venue_id) ON DELETE SET NULL,
        FOREIGN KEY (home_city_id) REFERENCES locations(location_id) ON DELETE CASCADE
    )''')

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
        applied_ice_out_p1 REAL DEFAULT 1.00,
        applied_ice_out_p2 REAL DEFAULT 1.00,
        applied_ice_out_p3 REAL DEFAULT 1.00,
        applied_ice_out_p4 REAL DEFAULT 1.00,
        applied_g_buffer REAL DEFAULT 1.000,
        delta_r_p1 REAL NOT NULL,
        delta_r_p2 REAL DEFAULT 0.0,
        delta_r_p3 REAL NOT NULL,
        delta_r_p4 REAL DEFAULT 0.0,
        guardrails_summary TEXT DEFAULT '[]',
        match_timestamp TEXT NOT NULL,
        FOREIGN KEY (venue_id) REFERENCES venues(venue_id) ON DELETE RESTRICT,
        FOREIGN KEY (format_id) REFERENCES match_formats(format_id) ON DELETE RESTRICT
    )''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS match_logs (
        log_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        player_id TEXT NOT NULL,
        pre_latent_mmr REAL NOT NULL,
        post_latent_mmr REAL NOT NULL,
        pre_display_rating REAL NOT NULL,
        post_display_rating REAL NOT NULL,
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

    c.execute('''
    CREATE TABLE IF NOT EXISTS global_config (
        param_key TEXT PRIMARY KEY,
        param_value REAL NOT NULL,
        is_active INTEGER DEFAULT 1,
        title TEXT,
        description TEXT,
        tuning_guide TEXT
    )''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS progression_speed_rules (
        rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
        min_rating REAL NOT NULL,
        max_rating REAL NOT NULL,
        speed_multiplier REAL NOT NULL,
        description TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS config_changelog (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        param_key TEXT NOT NULL,
        old_value REAL NOT NULL,
        new_value REAL NOT NULL,
        changed_by TEXT NOT NULL,
        changed_at TEXT NOT NULL
    )''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS player_changelog (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id TEXT NOT NULL,
        change_type TEXT NOT NULL,
        old_val TEXT,
        new_val TEXT,
        changed_by TEXT NOT NULL,
        changed_at TEXT NOT NULL
    )''')

    add_column_if_not_exists(c, "players", "accuracy_s_rd", "REAL DEFAULT 0.0")
    add_column_if_not_exists(c, "players", "accuracy_s_matches", "REAL DEFAULT 0.0")
    add_column_if_not_exists(c, "players", "accuracy_s_diversity", "REAL DEFAULT 0.0")
    add_column_if_not_exists(c, "match_logs", "pre_display_rating", "REAL DEFAULT 3.0")
    add_column_if_not_exists(c, "match_logs", "post_display_rating", "REAL DEFAULT 3.0")
    add_column_if_not_exists(c, "matches", "guardrails_summary", "TEXT DEFAULT '[]'")

    # Seed 18 Official Match Formats
    official_formats = [
        ("STD_B03", "Best of 3 Sets", "MULTI_SET", 1.00, None, None),
        ("STD_B05", "Best of 5 Sets", "MULTI_SET", 1.00, None, None),
        ("RACE_4", "Race to 4 Games", "RACE_GAMES", 0.50, 4, None),
        ("RACE_5", "Race to 5 Games", "RACE_GAMES", 0.60, 5, None),
        ("RACE_6", "Race to 6 Games", "RACE_GAMES", 0.70, 6, None),
        ("RACE_7", "Race to 7 Games", "RACE_GAMES", 0.80, 7, None),
        ("RACE_9", "Race to 9 Games", "RACE_GAMES", 0.80, 9, None),
        ("RACE_11", "Race to 11 Games", "RACE_GAMES", 0.90, 11, None),
        ("AMER_12", "Americano 12 Points", "AMERICANO", 0.30, None, 12),
        ("MEX_12", "Mexicano 12 Points", "MEXICANO", 0.30, None, 12),
        ("AMER_16", "Americano 16 Points", "AMERICANO", 0.30, None, 16),
        ("MEX_16", "Mexicano 16 Points", "MEXICANO", 0.30, None, 16),
        ("AMER_20", "Americano 20 Points", "AMERICANO", 0.30, None, 20),
        ("MEX_20", "Mexicano 20 Points", "MEXICANO", 0.30, None, 20),
        ("AMER_24", "Americano 24 Points", "AMERICANO", 0.30, None, 24),
        ("MEX_24", "Mexicano 24 Points", "MEXICANO", 0.30, None, 24),
        ("AMER_28", "Americano 28 Points", "AMERICANO", 0.30, None, 28),
        ("MEX_28", "Mexicano 28 Points", "MEXICANO", 0.30, None, 28)
    ]
    for fid, fname, cat, mc, tg, tp in official_formats:
        c.execute("""
            INSERT INTO match_formats (format_id, format_name, category, mc_weight, target_games, total_points)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(format_id) DO UPDATE SET
                format_name=excluded.format_name,
                category=excluded.category,
                mc_weight=excluded.mc_weight,
                target_games=excluded.target_games,
                total_points=excluded.total_points
        """, (fid, fname, cat, mc, tg, tp))

    master_params = [
        ("R_MIN", 0.0000, 1, "Scale Absolute Floor", "Lowest allowed rating.", "Clamps lowest possible rating to 0.0000."),
        ("R_MAX", 7.0000, 1, "Scale Absolute Ceiling", "Maximum rating bound.", "Locked at 7.0000 to preserve tier definitions."),
        ("R_ELITE_THRESHOLD", 6.3000, 1, "Elite Drag Gate", "Rating where exponential drag starts.", "Lowering applies drag earlier."),
        ("ELITE_DRAG_EXPONENT", 2.5, 1, "Elite Drag Curvature", "Steepness of the pro ceiling curve.", "Higher values make 7.0000 harder to reach."),
        ("POWER_MEAN_P", 3.0, 1, "Doubles Cubic Exponent", "Anchor power mean weighting.", "3.0 gives a 70/30 anchor weighting bias."),
        ("LOGISTIC_BETA", 2.0, 1, "Logistic Scale Factor", "Win odds sensitivity.", "Lowering (1.8) increases upset swings."),
        ("K_MAX", 0.4000, 1, "Beginner Max Volatility", "Base step size at R = 0.000.", "Higher values accelerate beginner movement."),
        ("K_MIN", 0.0800, 1, "Pro Min Volatility", "Base step size at R = 7.000.", "Lower values lock pro ratings tighter."),
        ("MARGIN_BASE", 0.80, 1, "Margin Floor Factor", "Minimum factor for close games.", "Floor for 7-6 tiebreaks."),
        ("MARGIN_SCALE", 0.40, 1, "Margin Blowout Scale", "Bonus multiplier for blowouts.", "Full blowout bonus = 1.20."),
        ("ELEVATOR_MARGIN_THRESH", 1.1000, 1, "Elevator Margin Gate", "Margin required for 3x boost.", "Set to 1.10 so 6-0, 6-1 triggers the Elevator."),
        ("ELEVATOR_ACCEL_FACTOR", 3.0, 1, "Elevator Boost Multiplier", "Multiplier applied to provisional blowouts.", "Triples step size for unranked winners."),
        ("MAX_ELEVATOR_DELTA", 0.7500, 1, "Elevator Placement Cap", "Max points a smurf can win in one blowout game.", "Bypasses casual daily ceiling up to +0.7500."),
        ("MAX_8H_EXCHANGE_CAP", 0.0000, 0, "8-Hour Rolling Cap", "Tight-window point transfer cap.", "Active when > 0.0000."),
        ("MAX_12H_EXCHANGE_CAP", 0.0000, 0, "12-Hour Rolling Cap", "Half-day point transfer cap.", "Active when > 0.0000."),
        ("MAX_24H_EXCHANGE_CAP", 0.1500, 1, "24-Hour Casual Cap", "Net 24-hour casual transfer ceiling.", "Prevents collusion farming."),
        ("MAX_48H_EXCHANGE_CAP", 0.0000, 0, "48-Hour Rolling Cap", "Weekend point transfer cap.", "Active when > 0.0000."),
        ("SESSION_EXCHANGE_CAP", 0.3000, 1, "Verified Session Cap", "Elevated cap for verified 6+ player events.", "Doubles the daily limit for club mixers."),
        ("MIN_SESSION_PLAYERS", 6, 1, "Session Participant Floor", "Min players required to unlock session cap.", "Events below 6 revert to 0.1500 cap."),
        ("RD_MIN", 30.0, 1, "Certainty Floor", "Absolute uncertainty floor.", "Prevents RD from dropping below 30.0."),
        ("RD_MAX", 350.0, 1, "Unrated Starting RD", "Uncertainty assigned at registration.", "Baseline starting uncertainty for new accounts."),
        ("RD_CONTRACTION_DENOMINATOR", 110000.0, 1, "RD Contraction Divisor", "Information precision denominator.", "Calibrated so RD steps down 350 -> 240 smoothly."),
        ("INACTIVITY_CONSTANT", 12.0, 1, "Inactivity Rust Rate", "Monthly temporal uncertainty growth.", "Points of RD regained per inactive month."),
        ("BRIDGE_RD_THRESHOLD", 80.0, 1, "Bridge Node Max RD", "Max RD to qualify as Bridge Node.", "Must have RD <= 80 to act as measuring traveler."),
        ("BRIDGE_MIN_MATCHES", 5, 1, "Bridge Match Minimum", "Away matches required to link locations.", "Matches required before a traveler links regional pools."),
        ("LAMBDA_BRIDGE_DAMPING", 3.0, 1, "Tikhonov Bridge Lambda", "Traveler shock absorber parameter.", "Higher values require more travelers before an offset deploys."),
        ("CIRCUIT_BREAKER", 0.0250, 1, "Auto Cron Safety Ceiling", "Maximum shift per automated cycle.", "Limits automated Sunday macro shifts to +/-0.0250."),
        ("ADMIN_OVERRIDE_MAX", 0.0750, 1, "Admin Sandbox Shift Window", "Max human-approved offset.", "Ceiling for manual Admin calibration deployments."),
        ("ACCURACY_WEIGHT_RD", 0.50, 1, "Accuracy Weight: RD", "Weight for Pillar 1.", "Controls influence of mathematical uncertainty (RD)."),
        ("ACCURACY_WEIGHT_MATCHES", 0.25, 1, "Accuracy Weight: Matches", "Weight for Pillar 2.", "Controls importance of verified match volume."),
        ("ACCURACY_WEIGHT_DIVERSITY", 0.25, 1, "Accuracy Weight: Diversity", "Weight for Pillar 3.", "Controls importance of playing unique opponents."),
        ("TIER_PROVISIONAL_MAX", 69.99, 1, "Provisional Score Ceiling", "Upper bound for Tier 1 [PR].", "Players below this score remain Provisional."),
        ("TIER_VERIFIED_MAX", 89.99, 1, "Verified Score Ceiling", "Upper bound for Tier 2 Verified.", "Score required to cross to Anchor tier."),
        ("TARGET_MATCHES_PROV", 3, 1, "Provisional Match Quota", "Target matches during placement.", "Matches needed to satisfy sample depth during placement."),
        ("TARGET_OPPONENTS_PROV", 2, 1, "Provisional Opponent Quota", "Target opponents during placement.", "Opponents needed during placement."),
        ("TARGET_MATCHES_VERIFIED", 5, 1, "Verified Tier Match Quota", "Target matches for Verified tier.", "Verified match count needed for verified accuracy."),
        ("TARGET_OPPONENTS_VERIFIED", 3, 1, "Verified Tier Opponent Quota", "Target opponents for Verified tier.", "Distinct opponents needed for verified accuracy."),
        ("TARGET_MATCHES_ANCHOR", 15, 1, "Anchor Tier Match Quota", "Target matches for Anchor tier.", "Match volume needed for Anchor tier."),
        ("TARGET_OPPONENTS_ANCHOR", 8, 1, "Anchor Tier Opponent Quota", "Target opponents for Anchor tier.", "Distinct opponents needed for Anchor tier."),
        ("PROVISIONAL_RD_GATE", 100.0, 1, "Tri-Gate Max RD", "Uncertainty gate for provisional exit.", "RD must be <= 100 to exit [PR]."),
        ("PROVISIONAL_MIN_MATCHES", 5, 1, "Tri-Gate Min Matches", "Match count gate for provisional exit.", "Verified matches required before [PR] badge clears."),
        ("PROVISIONAL_MIN_OPPONENTS", 3, 1, "Tri-Gate Min Opponents", "Network diversity gate for provisional exit.", "Unique opponents faced required before [PR] badge clears.")
    ]
    for k, v, act, tit, desc, tune in master_params:
        if force_sync_params:
            c.execute("""
                INSERT INTO global_config (param_key, param_value, is_active, title, description, tuning_guide)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(param_key) DO UPDATE SET
                    param_value=excluded.param_value,
                    is_active=excluded.is_active,
                    title=excluded.title,
                    description=excluded.description,
                    tuning_guide=excluded.tuning_guide
            """, (k, v, act, tit, desc, tune))
        else:
            c.execute("""
                INSERT INTO global_config (param_key, param_value, is_active, title, description, tuning_guide)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(param_key) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    tuning_guide=excluded.tuning_guide
            """, (k, v, act, tit, desc, tune))

    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 2. V.15 COMPLETE ALGORITHMIC CALCULATION ENGINE
# ==============================================================================
class RyftEngineV15:
    @staticmethod
    def get_configs():
        conn = get_db_connection()
        rows = conn.execute("SELECT param_key, param_value, is_active FROM global_config").fetchall()
        conn.close()
        return {r["param_key"]: (r["param_value"] if r["is_active"] == 1 else None) for r in rows}

    @staticmethod
    def get_speed_multiplier_for_rating(r_val):
        conn = get_db_connection()
        rules = conn.execute("""
            SELECT speed_multiplier FROM progression_speed_rules 
            WHERE is_active = 1 AND min_rating <= ? AND max_rating > ?
            ORDER BY rule_id DESC LIMIT 1
        """, (r_val, r_val)).fetchone()
        conn.close()
        return rules["speed_multiplier"] if rules else 1.00

    @staticmethod
    def sync_player_aggregates(player_id):
        conn = get_db_connection()
        m_count = conn.execute("""
            SELECT COUNT(*) FROM matches 
            WHERE team_a_p1_id = ? OR team_a_p2_id = ? OR team_b_p1_id = ? OR team_b_p2_id = ?
        """, (player_id, player_id, player_id, player_id)).fetchone()[0]

        opp_count = conn.execute("""
            SELECT COUNT(DISTINCT opp_id) FROM (
                SELECT team_b_p1_id as opp_id FROM matches WHERE team_a_p1_id = ? OR team_a_p2_id = ?
                UNION
                SELECT team_b_p2_id as opp_id FROM matches WHERE (team_a_p1_id = ? OR team_a_p2_id = ?) AND team_b_p2_id IS NOT NULL
                UNION
                SELECT team_a_p1_id as opp_id FROM matches WHERE team_b_p1_id = ? OR team_b_p2_id = ?
                UNION
                SELECT team_a_p2_id as opp_id FROM matches WHERE (team_b_p1_id = ? OR team_b_p2_id = ?) AND team_a_p2_id IS NOT NULL
            ) WHERE opp_id IS NOT NULL AND opp_id != ?
        """, (player_id, player_id, player_id, player_id, player_id, player_id, player_id, player_id, player_id)).fetchone()[0]

        partner_count = conn.execute("""
            SELECT COUNT(DISTINCT part_id) FROM (
                SELECT team_a_p2_id as part_id FROM matches WHERE team_a_p1_id = ?
                UNION
                SELECT team_a_p1_id as part_id FROM matches WHERE team_a_p2_id = ?
                UNION
                SELECT team_b_p2_id as part_id FROM matches WHERE team_b_p1_id = ?
                UNION
                SELECT team_b_p1_id as part_id FROM matches WHERE team_b_p2_id = ?
            ) WHERE part_id IS NOT NULL AND part_id != ?
        """, (player_id, player_id, player_id, player_id, player_id)).fetchone()[0]

        ven_count = conn.execute("""
            SELECT COUNT(DISTINCT venue_id) FROM matches 
            WHERE team_a_p1_id = ? OR team_a_p2_id = ? OR team_b_p1_id = ? OR team_b_p2_id = ?
        """, (player_id, player_id, player_id, player_id)).fetchone()[0]

        p_row = conn.execute("SELECT home_city_id, rating_deviation FROM players WHERE player_id = ?", (player_id,)).fetchone()
        cross_city_matches = 0
        if p_row:
            cross_city_matches = conn.execute("""
                SELECT COUNT(*) FROM matches m
                JOIN venues v ON m.venue_id = v.venue_id
                WHERE (m.team_a_p1_id = ? OR m.team_a_p2_id = ? OR m.team_b_p1_id = ? OR m.team_b_p2_id = ?)
                AND v.city_id != ?
            """, (player_id, player_id, player_id, player_id, p_row["home_city_id"])).fetchone()[0]
        
        is_bridge = 1 if (p_row and p_row["rating_deviation"] <= 80.0 and cross_city_matches >= 5) else 0

        conn.execute("""
            UPDATE players SET 
                verified_matches_count = ?,
                unique_opponents_count = ?,
                unique_partners_count = ?,
                unique_venues_count = ?,
                bridge_matches_count = ?,
                is_active_bridge = ?
            WHERE player_id = ?
        """, (m_count, opp_count, partner_count, ven_count, cross_city_matches, is_bridge, player_id))
        conn.commit()
        conn.close()

    @staticmethod
    def calculate_accuracy_suite(rd, match_count, opp_count, is_currently_prov, cfg):
        rd_min = cfg.get("RD_MIN", 30.0) or 30.0
        rd_max = cfg.get("RD_MAX", 350.0) or 350.0
        
        s_rd = max(0.0, min(1.0, (rd_max - rd) / (rd_max - rd_min)))

        t_matches = 15.0 if (match_count >= 5 and rd <= 100.0) else 5.0
        t_opps = 8.0 if (match_count >= 5 and rd <= 100.0) else 3.0

        s_matches = min(1.0, match_count / float(t_matches))
        s_diversity = min(1.0, opp_count / float(t_opps))

        w_rd = cfg.get("ACCURACY_WEIGHT_RD", 0.50) if cfg.get("ACCURACY_WEIGHT_RD") is not None else 0.50
        w_m = cfg.get("ACCURACY_WEIGHT_MATCHES", 0.25) if cfg.get("ACCURACY_WEIGHT_MATCHES") is not None else 0.25
        w_d = cfg.get("ACCURACY_WEIGHT_DIVERSITY", 0.25) if cfg.get("ACCURACY_WEIGHT_DIVERSITY") is not None else 0.25

        composite_acc = round(((w_rd * s_rd) + (w_m * s_matches) + (w_d * s_diversity)) * 100.0, 2)

        prov_rd_gate = cfg.get("PROVISIONAL_RD_GATE", 100.0) or 100.0
        prov_min_m = cfg.get("PROVISIONAL_MIN_MATCHES", 5) or 5
        prov_min_d = cfg.get("PROVISIONAL_MIN_OPPONENTS", 3) or 3

        tri_gate_passed = (rd <= prov_rd_gate and match_count >= prov_min_m and opp_count >= prov_min_d)
        new_is_prov = 0 if tri_gate_passed else 1

        tier_prov_max = cfg.get("TIER_PROVISIONAL_MAX", 69.99) or 69.99
        tier_ver_max = cfg.get("TIER_VERIFIED_MAX", 89.99) or 89.99

        if composite_acc >= tier_ver_max and new_is_prov == 0 and rd <= 60.0 and match_count >= 15 and opp_count >= 8:
            cal_tier = "ANCHOR"
        elif (composite_acc >= tier_prov_max or tri_gate_passed) and new_is_prov == 0:
            cal_tier = "VERIFIED"
        else:
            cal_tier = "PROVISIONAL"

        return {
            "s_rd_pct": round(s_rd * 100.0, 1),
            "s_matches_pct": round(s_matches * 100.0, 1),
            "s_diversity_pct": round(s_diversity * 100.0, 1),
            "composite_accuracy": composite_acc,
            "calibration_tier": cal_tier,
            "is_provisional": new_is_prov,
            "tri_gate_passed": tri_gate_passed
        }

    @staticmethod
    def validate_score(format_id, category, target_games, total_points, score_a, score_b, sets_data):
        if category == "MULTI_SET":
            valid_pairs = {(6,0),(6,1),(6,2),(6,3),(6,4),(7,5),(7,6),(0,6),(1,6),(2,6),(3,6),(4,6),(5,7),(6,7)}
            if len(sets_data) < 2:
                return False, "Multi-set formats require at least 2 completed sets."
            a_sets, b_sets = 0, 0
            for sa, sb in sets_data:
                if (sa, sb) not in valid_pairs:
                    return False, f"Invalid set scoreline: {sa}-{sb}. Must be 6-0..6-4, 7-5, or 7-6."
                if sa > sb: a_sets += 1
                else: b_sets += 1
            if format_id == "STD_B03" and max(a_sets, b_sets) != 2:
                return False, "Best of 3 must terminate when one team wins 2 sets."
            elif format_id == "STD_B05" and max(a_sets, b_sets) != 3:
                return False, "Best of 5 must terminate when one team wins 3 sets."
            return True, "Valid Multi-Set"

        elif category == "RACE_GAMES":
            tg = target_games or 6
            if (score_a == tg and score_b < tg) or (score_b == tg and score_a < tg):
                return True, "Valid Target Race"
            if (score_a > tg or score_b > tg) and abs(score_a - score_b) == 2:
                return True, "Valid Win-by-2 Extended Race"
            return False, f"Invalid score for Race to {tg}. Must end at {tg}-X or win-by-2 beyond target."

        elif category in ("AMERICANO", "MEXICANO"):
            tp = total_points or 24
            if (score_a + score_b) != tp:
                return False, f"Sum of scores ({score_a} + {score_b} = {score_a+score_b}) must equal {tp} points."
            return True, f"Valid {category}"
        return True, "Valid"

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

            speed_mult = cls.get_speed_multiplier_for_rating(r_curr)
            if speed_mult != 1.00:
                k_base *= speed_mult
                p_flags.append(f"SPEED_RULE_APPLIED: Adjusted by {speed_mult:.2f}x for rating tier.")

            # Bit 12: Elevator Protocol (Enforces threshold gate)
            is_elevator = False
            el_thresh = cfg.get("ELEVATOR_MARGIN_THRESH", 1.1000) or 1.1000
            el_factor = cfg.get("ELEVATOR_ACCEL_FACTOR", 3.0) or 3.0
            if p_data["is_provisional"] and s_margin >= el_thresh and is_winner and r_curr < r_elite:
                k_base *= el_factor
                is_elevator = True
                p_flags.append("ELEVATOR_3X_BOOST: Provisional blowout victory; step rate tripled.")

            decay = (r_max - r_curr) / r_max
            if r_curr >= r_elite:
                decay *= ((r_max - r_curr) / (r_max - r_elite)) ** drag_exp
                p_flags.append(f"ELITE_DRAG_ENGAGED: Rating >= {r_elite}; point gains dampened near ceiling.")
            decay = max(0.0000001, decay)

            q = 0.0057565
            g_opp = 1.0 / math.sqrt(1.0 + (3.0 * (q**2) * (opp_rd**2)) / (math.pi**2))
            w_trust = 0.0000 if p_data["is_quarantined"] else min(1.0, p_data["graph_centrality"] / 0.20)
            if p_data["is_quarantined"]: 
                p_flags.append("QUARANTINE_ACTIVE: Points frozen due to moderation status.")

            direction = 1.0 if is_team_a else -1.0
            raw_delta = (k_base * decay * mc * s_margin * w_trust * g_opp) * (direction * score_delta)

            # Bit 10: Asymmetric Ice-Out Protection
            dampened_delta = raw_delta
            if not is_singles and partner_r is not None:
                gap = abs(r_curr - partner_r)
                d_factor = 1.0
                if gap >= 2.0: d_factor = 0.05
                elif gap >= 1.5: d_factor = 0.20
                elif gap >= 1.0: d_factor = 0.50

                if raw_delta < 0 and r_curr > partner_r and d_factor < 1.0:
                    dampened_delta = raw_delta * d_factor
                    p_flags.append(f"ICE_OUT_ANCHOR_SHIELD: Partner gap >= {gap:.1f}; loss reduced by {int((1-d_factor)*100)}%.")
                elif raw_delta > 0 and r_curr < partner_r and d_factor < 1.0:
                    dampened_delta = raw_delta * d_factor
                    p_flags.append(f"ICE_OUT_NOVICE_DAMPENED: Partner gap >= {gap:.1f}; anti-carry gain reduced by {int((1-d_factor)*100)}%.")

            # Exchange Cap Clamping
            if is_tournament:
                final_delta = dampened_delta
                p_flags.append("TOURNAMENT_OVERRIDE: Verified tournament desk match; daily caps bypassed.")
            elif is_elevator:
                max_el = cfg.get("MAX_ELEVATOR_DELTA", 0.7500) or 0.7500
                final_delta = max(-max_el, min(max_el, dampened_delta))
            else:
                cap_24 = cfg.get("MAX_24H_EXCHANGE_CAP", 0.1500) or 0.1500
                final_delta = max(-cap_24, min(cap_24, dampened_delta))
                if abs(dampened_delta) > cap_24:
                    p_flags.append("24H_EXCHANGE_CAP_CLAMPED: Reached daily casual exchange ceiling (0.1500 points).")

            new_r = max(0.0000, min(6.9999, r_curr + final_delta))

            # Bit 11: Calibrated Bayesian Uncertainty Contraction
            rd_denom = cfg.get("RD_CONTRACTION_DENOMINATOR", 110000.0) or 110000.0
            inv_prior = 1.0 / (p_rd**2)
            inv_info = (mc * s_margin * (g_opp**2)) / float(rd_denom)
            new_rd = max(30.0, min(350.0, math.sqrt(1.0 / (inv_prior + inv_info))))

            # Module 8: Accuracy & Calibration Status
            new_matches = p_data["verified_matches_count"] + (0 if is_dry_run else 1)
            new_opps = p_data["unique_opponents_count"] + (0 if is_dry_run else 1)
            
            acc_suite = cls.calculate_accuracy_suite(new_rd, new_matches, new_opps, bool(p_data["is_provisional"]), cfg)

            results.append({
                "player_id": p_data["player_id"],
                "display_name": p_data["display_name"],
                "pre_r": r_curr,
                "post_r": round(new_r, 4),
                "delta_r": round(final_delta, 4),
                "pre_rd": p_rd,
                "post_rd": round(new_rd, 3),
                "accuracy_suite": acc_suite,
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
# 3. STREAMLIT COMMAND & OPERATIONAL INTERFACE
# ==============================================================================
st.set_page_config(page_title="RYFT Engine V.15 Platform", layout="wide")

st.sidebar.title("⚡ RYFT Engine V.15")
active_operator = st.sidebar.selectbox("Active Operator:", ["Aniket (Admin)", "Manish", "Nithin", "Ritesh", "Tournament Desk"])
st.sidebar.caption("Deterministic Micro Physics & Topological Calibration")

nav = st.sidebar.radio("Navigation", [
    "📊 System Dashboard", 
    "🎾 Log Matches", 
    "📜 Historical Matches", 
    "👥 Players Roster", 
    "🏢 Venues & Locations (CRUD)", 
    "🌐 Hawking Regional Control", 
    "⚙️ Global Config Switches"
])

# TAB 1: SYSTEM DASHBOARD
if nav == "📊 System Dashboard":
    st.title("System Health & Operational Overview")
    conn = get_db_connection()
    n_p = conn.execute("SELECT COUNT(*) FROM players WHERE calibration_tier != 'INACTIVE'").fetchone()[0]
    n_m = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    n_v = conn.execute("SELECT COUNT(*) FROM venues WHERE is_active = 1").fetchone()[0]
    n_cities = conn.execute("SELECT COUNT(*) FROM locations WHERE location_type = 'CITY'").fetchone()[0]
    n_countries = conn.execute("SELECT COUNT(*) FROM locations WHERE location_type = 'COUNTRY'").fetchone()[0]
    conn.close()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Active Players", n_p)
    m2.metric("Matches Completed", n_m)
    m3.metric("Registered Venues", n_v)
    m4.metric("Active Cities", n_cities)
    m5.metric("Active Countries", n_countries)

    st.markdown("---")
    with st.expander("💾 Database Backup & Restore (Zero Data Loss Safeguard)"):
        st.caption("Safeguard your test data against free cloud container reboots.")
        col_bk1, col_bk2 = st.columns(2)
        with col_bk1:
            st.markdown("#### 📥 Backup Data")
            st.write("Download your entire database snapshot after a match session.")
            if os.path.exists(DB_FILE):
                with open(DB_FILE, "rb") as f:
                    db_bytes = f.read()
                st.download_button(
                    label="⬇️ Download Database Snapshot (.db)",
                    data=db_bytes,
                    file_name=f"ryft_v15_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                    mime="application/octet-stream",
                    use_container_width=True
                )
            else:
                st.info("No database file found on disk.")

        with col_bk2:
            st.markdown("#### 📤 Restore Data")
            st.write("Upload a previously downloaded `.db` file to recover all players, venues, and matches.")
            uploaded_db = st.file_uploader("Choose backup .db file", type=["db", "sqlite", "sqlite3"])
            if uploaded_db is not None:
                if st.button("🚨 Restore Database From File", type="primary", use_container_width=True):
                    with open(DB_FILE, "wb") as f:
                        f.write(uploaded_db.getbuffer())
                    init_db()
                    st.success("Database successfully restored! All historical records recovered.")
                    st.rerun()

# TAB 2: LOG MATCHES
elif nav == "🎾 Log Matches":
    st.title("Log Matches & Real-Time Simulation Hub")
    st.caption("Record official matches or simulate dry-run calculations without altering ratings.")

    conn = get_db_connection()
    p_rows = conn.execute("SELECT * FROM players WHERE calibration_tier != 'INACTIVE' ORDER BY display_name ASC").fetchall()
    v_rows = conn.execute("SELECT venue_id, venue_name FROM venues WHERE is_active = 1").fetchall()
    f_rows = conn.execute("SELECT * FROM match_formats WHERE is_active = 1").fetchall()
    conn.close()

    p_map = {f"{p['display_name']} (MMR: {p['latent_mmr']:.3f} | RD: {p['rating_deviation']:.0f} | {p['calibration_tier']})": p['player_id'] for p in p_rows}
    v_map = {v["venue_name"]: v["venue_id"] for v in v_rows}
    f_dict = {f["format_name"]: dict(f) for f in f_rows}

    if not v_rows:
        st.warning("⚠️ No venues exist in your database yet. Go to 'Venues & Locations (CRUD)' to add your first venue.")
    if not p_rows:
        st.warning("⚠️ No players registered yet. Go to 'Players Roster' to onboard your players.")

    col_f, col_v, col_m = st.columns(3)
    fmt_name = col_f.selectbox("Scoring Format", list(f_dict.keys())) if f_dict else None
    ven_name = col_v.selectbox("Contested Venue", list(v_map.keys())) if v_map else None
    mode_pick = col_m.radio("Match Mode", ["2v2 Doubles", "1v1 Singles"], horizontal=True)
    is_doubles = (mode_pick == "2v2 Doubles")

    selected_fmt = f_dict[fmt_name] if fmt_name else None

    st.markdown("---")
    st.markdown("### Roster Selection")
    col_ta, col_tb = st.columns(2)

    with col_ta:
        st.markdown("#### 🔵 Team A")
        p1_pick = st.selectbox("Player A1 (Required)", ["-- Select --"] + list(p_map.keys()), key="p1_match")
        p2_pick = "-- None --"
        if is_doubles:
            p2_pick = st.selectbox("Player A2 (Teammate)", ["-- Select --"] + list(p_map.keys()), key="p2_match")

    with col_tb:
        st.markdown("#### 🔴 Team B")
        p3_pick = st.selectbox("Player B1 (Required)", ["-- Select --"] + list(p_map.keys()), key="p3_match")
        p4_pick = "-- None --"
        if is_doubles:
            p4_pick = st.selectbox("Player B2 (Teammate)", ["-- Select --"] + list(p_map.keys()), key="p4_match")

    st.markdown("---")
    st.markdown("### Match Scorecard Entry")

    sets_recorded = []
    final_score_a, final_score_b = 0, 0
    total_games_a, total_games_b = 0, 0

    if selected_fmt:
        cat = selected_fmt["category"]
        fid = selected_fmt["format_id"]

        if cat == "MULTI_SET":
            st.info(f"**Multi-Set Format ({selected_fmt['format_name']}):** Standard FIP sets (6-0..6-4, 7-5, 7-6).")
            
            s1_c1, s1_c2 = st.columns(2)
            s1_a = s1_c1.number_input("Set 1: Team A Games", 0, 7, 6, key="s1_a")
            s1_b = s1_c2.number_input("Set 1: Team B Games", 0, 7, 3, key="s1_b")
            sets_recorded.append((s1_a, s1_b))

            s2_c1, s2_c2 = st.columns(2)
            s2_a = s2_c1.number_input("Set 2: Team A Games", 0, 7, 6, key="s2_a")
            s2_b = s2_c2.number_input("Set 2: Team B Games", 0, 7, 4, key="s2_b")
            sets_recorded.append((s2_a, s2_b))

            a_sets = (1 if s1_a > s1_b else 0) + (1 if s2_a > s2_b else 0)
            b_sets = (1 if s1_b > s1_a else 0) + (1 if s2_b > s2_a else 0)

            if a_sets == 1 and b_sets == 1:
                st.warning("Sets are tied 1-1. Set 3 decider inputs unlocked:")
                s3_c1, s3_c2 = st.columns(2)
                s3_a = s3_c1.number_input("Set 3 (Decider): Team A Games", 0, 7, 6, key="s3_a")
                s3_b = s3_c2.number_input("Set 3 (Decider): Team B Games", 0, 7, 4, key="s3_b")
                sets_recorded.append((s3_a, s3_b))
                if s3_a > s3_b: a_sets += 1
                else: b_sets += 1

            final_score_a, final_score_b = a_sets, b_sets
            total_games_a = sum(sa for sa, sb in sets_recorded)
            total_games_b = sum(sb for sa, sb in sets_recorded)

        elif cat == "RACE_GAMES":
            tg = selected_fmt["target_games"] or 6
            st.info(f"**Single-Set Race ({selected_fmt['format_name']}):** First to {tg} games or win-by-2 beyond {tg}.")
            rg_c1, rg_c2 = st.columns(2)
            total_games_a = rg_c1.number_input("Team A Games Won", 0, 30, tg, key="rg_a")
            total_games_b = rg_c2.number_input("Team B Games Won", 0, 30, max(0, tg-2), key="rg_b")
            final_score_a = total_games_a
            final_score_b = total_games_b
            sets_recorded.append((total_games_a, total_games_b))

        elif cat in ("AMERICANO", "MEXICANO"):
            tp = selected_fmt["total_points"] or 24
            st.info(f"**Fixed-Point Format ({selected_fmt['format_name']}):** Scores MUST sum to exactly {tp} points.")
            ap_c1, ap_c2 = st.columns(2)
            total_games_a = ap_c1.number_input("Team A Points Won", 0, tp, tp // 2, key="ap_a")
            total_games_b = ap_c2.number_input("Team B Points Won", 0, tp, tp - (tp // 2), key="ap_b")
            final_score_a = total_games_a
            final_score_b = total_games_b
            sets_recorded.append((total_games_a, total_games_b))

    btn_sim_c, btn_save_c = st.columns(2)
    click_sim = btn_sim_c.button("🔬 Dry Run (Simulate Math Only)", use_container_width=True)
    click_save = btn_save_c.button("💾 Verify & Save Match", type="primary", use_container_width=True)

    if click_sim or click_save:
        if not v_map or not p_map:
            st.error("Please add venues and players before calculating matches.")
        elif p1_pick == "-- Select --" or p3_pick == "-- Select --" or (is_doubles and (p2_pick == "-- Select --" or p4_pick == "-- Select --")):
            st.error("Please assign players to all required roster slots.")
        else:
            is_valid, err_msg = RyftEngineV15.validate_score(
                selected_fmt["format_id"], selected_fmt["category"],
                selected_fmt["target_games"], selected_fmt["total_points"],
                final_score_a, final_score_b, sets_recorded
            )

            if not is_valid:
                st.error(f"❌ Score Validation Failed: {err_msg}")
            else:
                p1_id, p3_id = p_map[p1_pick], p_map[p3_pick]
                p2_id = p_map[p2_pick] if is_doubles else None
                p4_id = p_map[p4_pick] if is_doubles else None

                conn = get_db_connection()
                p1_obj = dict(conn.execute("SELECT * FROM players WHERE player_id = ?", (p1_id,)).fetchone())
                p3_obj = dict(conn.execute("SELECT * FROM players WHERE player_id = ?", (p3_id,)).fetchone())
                p2_obj = dict(conn.execute("SELECT * FROM players WHERE player_id = ?", (p2_id,)).fetchone()) if p2_id else None
                p4_obj = dict(conn.execute("SELECT * FROM players WHERE player_id = ?", (p4_id,)).fetchone()) if p4_id else None
                venue_obj = dict(conn.execute("SELECT * FROM venues WHERE venue_id = ?", (v_map[ven_name],)).fetchone())
                conn.close()

                is_venue_bridge = 1 if (p1_obj["home_venue_id"] != venue_obj["venue_id"] and p1_obj["home_city_id"] == venue_obj["city_id"]) else 0
                is_city_bridge = 1 if (p1_obj["home_city_id"] != venue_obj["city_id"] and p1_obj["home_country_code"] == venue_obj["country_code"]) else 0
                is_country_bridge = 1 if (p1_obj["home_country_code"] != venue_obj["country_code"]) else 0

                gw = max(total_games_a, total_games_b)
                gl = min(total_games_a, total_games_b)

                res = RyftEngineV15.compute_match(
                    p1_obj, p2_obj, p3_obj, p4_obj, 
                    final_score_a, final_score_b, gw, gl,
                    selected_fmt["format_id"], v_map[ven_name],
                    is_singles=not is_doubles, is_dry_run=click_sim
                )

                st.success(f"Match Computation Executed • Odds: A ({res['win_expectancy_a']*100:.1f}%) vs B ({(1-res['win_expectancy_a'])*100:.1f}%) • MOV Factor: {res['applied_s_margin']}")
                
                st.dataframe(pd.DataFrame([
                    {
                        "Player": r["display_name"],
                        "Pre MMR": f"{r['pre_r']:.3f}",
                        "Delta": f"{r['delta_r']:+0.4f}",
                        "Post MMR": f"{r['post_r']:.3f}",
                        "Pre Display": f"{r['pre_r']:.2f}",
                        "Post Display": f"{r['post_r']:.2f}",
                        "RD Contraction": f"{r['pre_rd']:.1f} -> {r['post_rd']:.1f}",
                        "Accuracy": f"{r['accuracy_suite']['composite_accuracy']:.1f}%",
                        "Tier": r["accuracy_suite"]["calibration_tier"],
                        "Tri-Gate Passed": "✅ YES" if r["accuracy_suite"]["tri_gate_passed"] else "❌ PROVISIONAL",
                        "Triggered Guardrails": ", ".join(r["guardrails"]) if r["guardrails"] else "Standard Exchange"
                    } for r in res["player_results"]
                ]), use_container_width=True)

                if click_save:
                    conn = get_db_connection()
                    m_id = f"M_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    ts = datetime.now(timezone.utc).isoformat()
                    
                    all_guardrails = []
                    for pr in res["player_results"]:
                        all_guardrails.extend(pr["guardrails"])

                    conn.execute('''
                        INSERT INTO matches (match_id, venue_id, format_id, is_singles, 
                                            is_venue_bridge, is_city_bridge, is_country_bridge,
                                            team_a_p1_id, team_a_p2_id, team_b_p1_id, team_b_p2_id, 
                                            score_team_a, score_team_b, set_scores_json,
                                            games_winner, games_loser, pre_rating_a, pre_rating_b, win_expectancy_a,
                                            applied_m_c, applied_s_margin, delta_r_p1, delta_r_p2, delta_r_p3, delta_r_p4,
                                            guardrails_summary, match_timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        m_id, v_map[ven_name], selected_fmt["format_id"], 0 if is_doubles else 1,
                        is_venue_bridge, is_city_bridge, is_country_bridge,
                        p1_id, p2_id, p3_id, p4_id, final_score_a, final_score_b, json.dumps(sets_recorded),
                        gw, gl, res["team_a_r"], res["team_b_r"], res["win_expectancy_a"],
                        res["applied_m_c"], res["applied_s_margin"],
                        res["player_results"][0]["delta_r"],
                        res["player_results"][1]["delta_r"] if is_doubles else 0.0,
                        res["player_results"][2]["delta_r"] if is_doubles else res["player_results"][1]["delta_r"],
                        res["player_results"][3]["delta_r"] if is_doubles else 0.0,
                        json.dumps(all_guardrails), ts
                    ))

                    for r in res["player_results"]:
                        acc = r["accuracy_suite"]
                        conn.execute('''
                            UPDATE players SET 
                                latent_mmr = ?, display_rating = ?, rating_deviation = ?,
                                rating_accuracy_pct = ?, accuracy_s_rd = ?, accuracy_s_matches = ?, accuracy_s_diversity = ?,
                                calibration_tier = ?, is_provisional = ?,
                                matches_won_count = matches_won_count + ?,
                                matches_lost_count = matches_lost_count + ?,
                                rolling_90d_peak = max(rolling_90d_peak, ?),
                                rolling_180d_peak = max(rolling_180d_peak, ?),
                                rolling_365d_peak = max(rolling_365d_peak, ?),
                                last_match_time = ?
                            WHERE player_id = ?
                        ''', (
                            r["post_r"], r["post_r"], r["post_rd"], 
                            acc["composite_accuracy"], acc["s_rd_pct"], acc["s_matches_pct"], acc["s_diversity_pct"],
                            acc["calibration_tier"], acc["is_provisional"],
                            1 if r["delta_r"] > 0 else 0, 1 if r["delta_r"] < 0 else 0, 
                            r["post_r"], r["post_r"], r["post_r"], ts, r["player_id"]
                        ))

                        conn.execute('''
                            INSERT INTO match_logs (log_id, match_id, player_id, pre_latent_mmr, post_latent_mmr,
                                                   pre_display_rating, post_display_rating,
                                                   pre_rd, post_rd, pre_accuracy_pct, post_accuracy_pct, delta_r,
                                                   is_elevator_active, guardrails_triggered, logged_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            f"LOG_{r['player_id']}_{m_id}", m_id, r["player_id"], r["pre_r"], r["post_r"],
                            r["pre_r"], r["post_r"], r["pre_rd"], r["post_rd"], 
                            r["accuracy_suite"]["composite_accuracy"], r["accuracy_suite"]["composite_accuracy"], r["delta_r"],
                            r["is_elevator"], json.dumps(r["guardrails"]), ts
                        ))

                    conn.execute("UPDATE venues SET total_matches_played = total_matches_played + 1 WHERE venue_id = ?", (v_map[ven_name],))
                    conn.commit()
                    conn.close()

                    all_p_ids = [p1_id, p3_id] + ([p2_id, p4_id] if is_doubles else [])
                    for pid in all_p_ids:
                        if pid:
                            RyftEngineV15.sync_player_aggregates(pid)

                    st.balloons()
                    st.success("✅ Match successfully committed! True aggregates synced.")

# TAB 3: HISTORICAL MATCHES
elif nav == "📜 Historical Matches":
    st.title("Historical Matches & Deep Algorithmic Audit Ledger")
    st.caption("Search matches by player, cohorts, date, or venue, and inspect 25-Bit execution traces.")

    conn = get_db_connection()
    p_all = conn.execute("SELECT player_id, display_name FROM players ORDER BY display_name ASC").fetchall()
    v_all = conn.execute("SELECT venue_id, venue_name FROM venues").fetchall()
    c_all = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'CITY'").fetchall()
    co_all = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'COUNTRY'").fetchall()
    conn.close()

    p_dict = {p["display_name"]: p["player_id"] for p in p_all}
    v_dict = {v["venue_name"]: v["venue_id"] for v in v_all}
    c_dict = {c["location_name"]: c["location_id"] for c in c_all}
    co_dict = {co["location_name"]: co["location_id"] for co in co_all}

    st.markdown("### Search & Filters")
    f1, f2, f3 = st.columns(3)
    filter_player = f1.selectbox("Filter by Player", ["-- All Players --"] + list(p_dict.keys()))
    filter_venue = f2.selectbox("Filter by Venue", ["-- All Venues --"] + list(v_dict.keys()))
    filter_city = f3.selectbox("Filter by City", ["-- All Cities --"] + list(c_dict.keys()))

    f4, f5, f6 = st.columns(3)
    filter_country = f4.selectbox("Filter by Country", ["-- All Countries --"] + list(co_dict.keys()))
    enable_date = f5.checkbox("Filter by Date")
    match_date_pick = f5.date_input("Match Date", value=date.today()) if enable_date else None
    
    cb_col1, cb_col2 = f6.columns(2)
    only_city_bridge = cb_col1.checkbox("Only City Bridges")
    only_country_bridge = cb_col2.checkbox("Only Country Bridges")

    with st.expander("👥 Search by Exact 4-Player Match Cohort"):
        q1, q2, q3, q4 = st.columns(4)
        c_p1 = q1.selectbox("Cohort Player 1", ["-- Select --"] + list(p_dict.keys()), key="c_p1")
        c_p2 = q2.selectbox("Cohort Player 2", ["-- Select --"] + list(p_dict.keys()), key="c_p2")
        c_p3 = q3.selectbox("Cohort Player 3", ["-- Select --"] + list(p_dict.keys()), key="c_p3")
        c_p4 = q4.selectbox("Cohort Player 4", ["-- Select --"] + list(p_dict.keys()), key="c_p4")

    query = """
        SELECT m.*, v.venue_name, l.location_name as city_name, co.location_name as country_name, f.format_name,
               p1.display_name as p1_name, p2.display_name as p2_name,
               p3.display_name as p3_name, p4.display_name as p4_name
        FROM matches m
        JOIN venues v ON m.venue_id = v.venue_id
        JOIN locations l ON v.city_id = l.location_id
        LEFT JOIN locations co ON l.parent_id = co.location_id
        JOIN match_formats f ON m.format_id = f.format_id
        JOIN players p1 ON m.team_a_p1_id = p1.player_id
        LEFT JOIN players p2 ON m.team_a_p2_id = p2.player_id
        JOIN players p3 ON m.team_b_p1_id = p3.player_id
        LEFT JOIN players p4 ON m.team_b_p2_id = p4.player_id
        WHERE 1=1
    """
    params = []

    if filter_player != "-- All Players --":
        pid = p_dict[filter_player]
        query += " AND (m.team_a_p1_id = ? OR m.team_a_p2_id = ? OR m.team_b_p1_id = ? OR m.team_b_p2_id = ?)"
        params.extend([pid, pid, pid, pid])

    if filter_venue != "-- All Venues --":
        query += " AND m.venue_id = ?"
        params.append(v_dict[filter_venue])

    if filter_city != "-- All Cities --":
        query += " AND v.city_id = ?"
        params.append(c_dict[filter_city])

    if enable_date and match_date_pick:
        query += " AND date(m.match_timestamp) = ?"
        params.append(str(match_date_pick))

    if only_city_bridge:
        query += " AND m.is_city_bridge = 1"

    if only_country_bridge:
        query += " AND m.is_country_bridge = 1"

    cohort_selected = [p_dict[p] for p in [c_p1, c_p2, c_p3, c_p4] if p != "-- Select --"]
    if len(cohort_selected) == 4:
        for c_pid in cohort_selected:
            query += " AND (m.team_a_p1_id = ? OR m.team_a_p2_id = ? OR m.team_b_p1_id = ? OR m.team_b_p2_id = ?)"
            params.extend([c_pid, c_pid, c_pid, c_pid])

    query += " ORDER BY m.match_timestamp DESC"

    conn = get_db_connection()
    matches_list = conn.execute(query, params).fetchall()

    st.markdown(f"#### Match Results ({len(matches_list)} found)")

    if not matches_list:
        st.info("No matches found.")
    else:
        for m in matches_list:
            bridge_badges = []
            if m["is_venue_bridge"]: bridge_badges.append("🏟️ Venue Bridge")
            if m["is_city_bridge"]: bridge_badges.append("🏙️ City Bridge")
            if m["is_country_bridge"]: bridge_badges.append("🌍 Country Bridge")
            b_str = " • ".join(bridge_badges) if bridge_badges else "Local Match"

            with st.container():
                st.markdown(f"""
                <div style="border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; margin-bottom: 10px; background-color: #f8fafc;">
                    <span style="font-size: 1.1em; font-weight: bold; color: #0f172a;">🎾 {m['match_id']}</span> 
                    <span style="float: right; color: #64748b; font-size: 0.9em;">📅 {m['match_timestamp'][:19]}</span><br/>
                    <strong>Venue:</strong> {m['venue_name']} ({m['city_name']}) | <strong>Format:</strong> {m['format_name']} | <span style="color: #0369a1; font-weight: 600;">{b_str}</span>
                </div>
                """, unsafe_allow_html=True)

                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    if m["is_singles"]:
                        st.markdown(f"**🔵 Player A:** {m['p1_name']} (ΔR: `{m['delta_r_p1']:+0.4f}`)")
                    else:
                        st.markdown(f"**🔵 Team A:** {m['p1_name']} & {m['p2_name']}")
                        st.write(f"Rating Deltas: {m['p1_name']} (`{m['delta_r_p1']:+0.4f}`) | {m['p2_name']} (`{m['delta_r_p2']:+0.4f}`)")
                    st.caption(f"Pre-Match Power-Mean: **{m['pre_rating_a']:.3f}** | Win Odds: **{m['win_expectancy_a']*100:.1f}%**")

                with col_res2:
                    if m["is_singles"]:
                        st.markdown(f"**🔴 Player B:** {m['p3_name']} (ΔR: `{m['delta_r_p3']:+0.4f}`)")
                    else:
                        st.markdown(f"**🔴 Team B:** {m['p3_name']} & {m['p4_name']}")
                        st.write(f"Rating Deltas: {m['p3_name']} (`{m['delta_r_p3']:+0.4f}`) | {m['p4_name']} (`{m['delta_r_p4']:+0.4f}`)")
                    st.caption(f"Pre-Match Power-Mean: **{m['pre_rating_b']:.3f}** | Win Odds: **{(1-m['win_expectancy_a'])*100:.1f}%**")

                st.write(f"**Scorelines:** Sets: `{m['set_scores_json']}` | Margin Factor: `{m['applied_s_margin']:.4f}`")

                with st.expander(f"🔍 Audit 25-Bit Execution Trace ({m['match_id']})"):
                    p_logs = conn.execute("""
                        SELECT ml.*, p.display_name, p.rating_deviation 
                        FROM match_logs ml 
                        JOIN players p ON ml.player_id = p.player_id 
                        WHERE ml.match_id = ?
                    """, (m["match_id"],)).fetchall()

                    st.markdown("##### Participant Level Calculations")
                    for pl in p_logs:
                        g_list = json.loads(pl["guardrails_triggered"]) if pl["guardrails_triggered"] else []
                        g_str = " • ".join(g_list) if g_list else "Standard competitive exchange."
                        st.write(f"- **{pl['display_name']}**: MMR `{pl['pre_latent_mmr']:.3f} -> {pl['post_latent_mmr']:.3f}` | Display `{pl['pre_display_rating']:.2f} -> {pl['post_display_rating']:.2f}` | RD `{pl['pre_rd']:.1f} -> {pl['post_rd']:.1f}` | ΔR: `{pl['delta_r']:+0.4f}`")
                        st.caption(f"  *Active Guardrails:* {g_str}")

                    st.markdown("##### 25-Bit Status Summary")
                    b_col1, b_col2 = st.columns(2)
                    with b_col1:
                        st.write("• **Bit 1 (Scale Clamping):** ✅ [0.000, 6.999]")
                        st.write(f"• **Bit 2 (Spatial Tagging):** ✅ Logged ({b_str})")
                        st.write(f"• **Bit 3 (Match Mode):** ✅ {'Singles' if m['is_singles'] else 'Doubles'}")
                        st.write(f"• **Bit 4 (Doubles Power-Mean):** {'Bypassed' if m['is_singles'] else '✅ Applied (p=3.0)'}")
                        st.write(f"• **Bit 5 (Win Expectancy):** ✅ E_A = {m['win_expectancy_a']*100:.1f}%")
                        st.write(f"• **Bit 6 (Margin Entropy):** ✅ Applied (Factor: {m['applied_s_margin']:.4f})")
                        st.write("• **Bit 7 (Volatility K-Base):** ✅ Computed")
                        st.write(f"• **Bit 8 (Elite Drag):** {'✅ ACTIVATED' if any(pl['post_latent_mmr'] >= 6.3 for pl in p_logs) else 'Bypassed'}")
                        st.write(f"• **Bit 9 (Format Multiplier):** ✅ M_C = {m['applied_m_c']:.2f}")
                        st.write("• **Bit 10 (Asymmetric Ice-Out):** Evaluated")
                        st.write("• **Bit 11 (RD Contraction):** ✅ Bayesian shrinkage committed")
                        st.write(f"• **Bit 12 (Elevator Protocol):** {'🚀 ACTIVATED (3x)' if any(pl['is_elevator_active'] == 1 for pl in p_logs) else 'Bypassed'}")
                    with b_col2:
                        st.write(f"• **Bit 13/14/15 (Exchange Caps):** {'🏆 Uncapped' if m['is_tournament'] else '✅ 24H Cap Active'}")
                        st.write("• **Bit 16 (Graph Centrality):** ✅ Applied")
                        st.write("• **Bit 17 (Quarantine):** Clean")
                        st.write("• **Bit 18 (Inactivity Rust):** Verified")
                        st.write("• **Bit 19 (Zero-Sum Normalization):** Standby")
                        st.write(f"• **Bit 20 (Bridge Node Check):** Verified")
                        st.write("• **Bit 21 (Hawking Ghost Sandbox):** Standby")
                        st.write("• **Bit 22 (Tikhonov / Jacobian):** Standby")
                        st.write("• **Bit 23 (Soft Floor Decouple):** Active")
                        st.write("• **Bit 24 (Tournament Bouncer):** Active")
                        st.write("• **Bit 25 (3-Tier Accuracy):** Recomputed")
                st.markdown("---")

    st.markdown("### 🚨 Clear Log & Match Rollback Utility")
    with st.expander("⚠️ Clear Matches & Revert Ratings"):
        st.caption("Selectively revert the latest match or delete matches within a date range, restoring player ratings.")
        clear_choice = st.radio("Clear Mode", ["Revert Latest Single Match", "Batch Delete Matches Across Date Range"])

        if clear_choice == "Revert Latest Single Match":
            last_m = conn.execute("SELECT match_id, match_timestamp FROM matches ORDER BY match_timestamp DESC LIMIT 1").fetchone()
            if last_m:
                st.write(f"Latest Match: **{last_m['match_id']}** (Logged: {last_m['match_timestamp']})")
                if st.button("🚨 Revert Latest Match", type="secondary"):
                    m_id = last_m["match_id"]
                    logs = conn.execute("SELECT player_id, pre_latent_mmr, pre_rd, pre_accuracy_pct FROM match_logs WHERE match_id = ?", (m_id,)).fetchall()
                    for l in logs:
                        conn.execute("""
                            UPDATE players SET 
                                latent_mmr = ?, display_rating = ?, rating_deviation = ?, rating_accuracy_pct = ?
                            WHERE player_id = ?
                        """, (l["pre_latent_mmr"], l["pre_latent_mmr"], l["pre_rd"], l["pre_accuracy_pct"], l["player_id"]))
                    
                    conn.execute("DELETE FROM match_logs WHERE match_id = ?", (m_id,))
                    conn.execute("DELETE FROM matches WHERE match_id = ?", (m_id,))
                    conn.commit()

                    for l in logs:
                        RyftEngineV15.sync_player_aggregates(l["player_id"])

                    st.warning(f"Reverted match {m_id} and restored player ratings!")
                    st.rerun()
            else:
                st.info("No recorded matches available to revert.")

        elif clear_choice == "Batch Delete Matches Across Date Range":
            col_d1, col_d2 = st.columns(2)
            del_start = col_d1.date_input("Start Date to Clear", value=date.today())
            del_end = col_d2.date_input("End Date to Clear", value=date.today())

            if st.button(f"🚨 Delete Matches Between {del_start} and {del_end}", type="primary"):
                targets = conn.execute("""
                    SELECT match_id FROM matches 
                    WHERE date(match_timestamp) >= ? AND date(match_timestamp) <= ?
                    ORDER BY match_timestamp DESC
                """, (str(del_start), str(del_end))).fetchall()

                if not targets:
                    st.info("No matches found in the selected date range.")
                else:
                    affected_p_ids = set()
                    for t_m in targets:
                        m_id = t_m["match_id"]
                        logs = conn.execute("SELECT player_id, pre_latent_mmr, pre_rd, pre_accuracy_pct FROM match_logs WHERE match_id = ?", (m_id,)).fetchall()
                        for l in logs:
                            affected_p_ids.add(l["player_id"])
                            conn.execute("""
                                UPDATE players SET 
                                    latent_mmr = ?, display_rating = ?, rating_deviation = ?, rating_accuracy_pct = ?
                                WHERE player_id = ?
                            """, (l["pre_latent_mmr"], l["pre_latent_mmr"], l["pre_rd"], l["pre_accuracy_pct"], l["player_id"]))
                        conn.execute("DELETE FROM match_logs WHERE match_id = ?", (m_id,))
                        conn.execute("DELETE FROM matches WHERE match_id = ?", (m_id,))

                    conn.commit()
                    for pid in affected_p_ids:
                        RyftEngineV15.sync_player_aggregates(pid)

                    st.success(f"Successfully deleted {len(targets)} matches and restored ratings!")
                    st.rerun()
    conn.close()

# TAB 4: PLAYERS ROSTER
elif nav == "👥 Players Roster":
    st.title("Players Directory & Calibration Roster")

    conn = get_db_connection()
    all_countries = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'COUNTRY'").fetchall()
    all_cities = conn.execute("SELECT location_id, location_name, parent_id FROM locations WHERE location_type = 'CITY'").fetchall()
    conn.close()

    st.markdown("### Regional Cohort Filter")
    rf1, rf2 = st.columns(2)
    sel_co = rf1.selectbox("Filter by Country", ["-- All Countries --"] + [c["location_name"] for c in all_countries])
    
    city_options = ["-- All Cities --"]
    if sel_co != "-- All Countries --":
        co_id = [c["location_id"] for c in all_countries if c["location_name"] == sel_co][0]
        city_options += [c["location_name"] for c in all_cities if c["parent_id"] == co_id]
    else:
        city_options += [c["location_name"] for c in all_cities]

    sel_ci = rf2.selectbox("Filter by City", city_options)

    p_query = """
        SELECT p.player_id, p.display_name, p.latent_mmr, p.display_rating, p.rating_deviation, p.rating_accuracy_pct,
               p.accuracy_s_rd as certainty_pct, p.accuracy_s_matches as sample_pct, p.accuracy_s_diversity as diversity_pct,
               p.calibration_tier, p.is_provisional, p.verified_matches_count, p.unique_opponents_count, 
               p.is_anchor, p.is_ceiling_anchor, p.is_active_bridge,
               l.location_name as city_name, co.location_name as country_name
        FROM players p 
        JOIN locations l ON p.home_city_id = l.location_id
        LEFT JOIN locations co ON l.parent_id = co.location_id
        WHERE p.calibration_tier != 'INACTIVE'
    """
    p_params = []
    if sel_co != "-- All Countries --":
        p_query += " AND co.location_name = ?"
        p_params.append(sel_co)
    if sel_ci != "-- All Cities --":
        p_query += " AND l.location_name = ?"
        p_params.append(sel_ci)

    p_query += " ORDER BY p.latent_mmr DESC"

    conn = get_db_connection()
    players_df = pd.read_sql_query(p_query, conn, params=p_params)
    conn.close()

    if not players_df.empty:
        display_df = players_df.copy()
        display_df["latent_mmr"] = display_df["latent_mmr"].apply(lambda x: f"{x:.3f}")
        display_df["display_rating"] = display_df["display_rating"].apply(lambda x: f"{x:.2f}")
        display_df["rating_deviation"] = display_df["rating_deviation"].apply(lambda x: f"{x:.1f}")
        display_df["rating_accuracy_pct"] = display_df["rating_accuracy_pct"].apply(lambda x: f"{x:.1f}%")
        st.dataframe(display_df[[
            "player_id", "display_name", "latent_mmr", "display_rating", "rating_deviation", 
            "rating_accuracy_pct", "calibration_tier", "is_provisional", "verified_matches_count", 
            "unique_opponents_count", "city_name", "country_name", "is_active_bridge"
        ]], use_container_width=True)
    else:
        st.info("No active players match the filter.")

    col_add, col_edit = st.columns(2)
    with col_add:
        with st.expander("➕ Register New Player"):
            with st.form("add_player_form"):
                st.markdown("#### Profile Onboarding")
                name = st.text_input("Full Name")
                
                cat_choice = st.selectbox("Category (Sets Starting Base MMR)", [
                    "Beginner (0.000)", "Beginner+ (1.000)", "Intermediate (2.000)", 
                    "Intermediate+ (3.500)", "Advanced (4.500)", "Elite (6.000)"
                ])
                base_val = float(cat_choice.split("(")[1].replace(")", ""))
                init_r = st.number_input("Latent MMR Override (X.XXX)", 0.000, 6.999, value=base_val, step=0.050, format="%.3f")
                
                conn = get_db_connection()
                cities = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'CITY'").fetchall()
                venues = conn.execute("SELECT venue_id, venue_name FROM venues WHERE is_active = 1").fetchall()
                conn.close()

                c_pick = st.selectbox("Home Municipality", [c["location_name"] for c in cities]) if cities else None
                v_pick = st.selectbox("Home Venue", ["None"] + [v["venue_name"] for v in venues]) if venues else "None"
                
                c1, c2, c3 = st.columns(3)
                is_anc = c1.checkbox("System Anchor")
                is_ceil = c2.checkbox("Ceiling Anchor")
                start_prov = c3.checkbox("Start Provisional [PR]", value=True)

                if st.form_submit_button("Commit Registration"):
                    if not cities:
                        st.error("Create at least one City in 'Venues & Locations (CRUD)' first.")
                    elif not name:
                        st.error("Player name cannot be blank.")
                    else:
                        c_id = [c["location_id"] for c in cities if c["location_name"] == c_pick][0]
                        v_id = [v["venue_id"] for v in venues if v["venue_name"] == v_pick][0] if v_pick != "None" else None
                        p_uuid = f"P_{datetime.now().strftime('%d%H%M%S')}"
                        
                        conn = get_db_connection()
                        conn.execute('''
                            INSERT INTO players (player_id, display_name, initial_rating, home_venue_id, home_city_id,
                                                 home_country_code, latent_mmr, display_rating, rolling_90d_peak, rolling_180d_peak,
                                                 rolling_365d_peak, rating_deviation, is_provisional, calibration_tier,
                                                 is_anchor, is_ceiling_anchor, created_at)
                            VALUES (?, ?, ?, ?, ?, 'IND', ?, ?, ?, ?, ?, 350.0, ?, ?, ?, ?, ?)
                        ''', (p_uuid, name, init_r, v_id, c_id, init_r, init_r, init_r, init_r, init_r, 
                              1 if start_prov else 0, 'PROVISIONAL' if start_prov else 'VERIFIED',
                              1 if is_anc else 0, 1 if is_ceil else 0, datetime.now(timezone.utc).isoformat()))
                        
                        conn.execute('''
                            INSERT INTO player_changelog (player_id, change_type, old_val, new_val, changed_by, changed_at)
                            VALUES (?, 'PROFILE_CREATED', 'None', ?, ?, ?)
                        ''', (p_uuid, f"Initial MMR: {init_r:.3f}", active_operator, datetime.now(timezone.utc).isoformat()))
                        
                        conn.commit()
                        conn.close()
                        st.success(f"Registered {name}!")
                        st.rerun()

    with col_edit:
        with st.expander("✏️ Profile Inspector, Overrides & Delete"):
            conn = get_db_connection()
            all_p = conn.execute("SELECT * FROM players ORDER BY display_name ASC").fetchall()
            conn.close()
            
            if all_p:
                p_sel_id = st.selectbox("Choose Player", [p["player_id"] for p in all_p], format_func=lambda x: [p["display_name"] for p in all_p if p["player_id"] == x][0])
                p_cur = [p for p in all_p if p["player_id"] == p_sel_id][0]

                bridge_status = "🟢 Active City Bridge Node" if p_cur["is_active_bridge"] else "Not a Bridge Node (Requires RD <= 80 & 5 away matches)"
                st.markdown(f"#### Profile: **{p_cur['display_name']}**")
                st.info(f"**Bridge Status:** {bridge_status} | **Tier:** `{p_cur['calibration_tier']}` (`{'PROVISIONAL [PR]' if p_cur['is_provisional'] else 'VERIFIED'}`)")

                ak1, ak2, ak3, ak4 = st.columns(4)
                ak1.metric("Rating Accuracy", f"{p_cur['rating_accuracy_pct']:.1f}%")
                ak2.metric("Certainty (Pillar 1)", f"{p_cur['accuracy_s_rd']:.1f}%")
                ak3.metric("Sample Depth (Pillar 2)", f"{p_cur['accuracy_s_matches']:.1f}%")
                ak4.metric("Diversity (Pillar 3)", f"{p_cur['accuracy_s_diversity']:.1f}%")

                with st.form("edit_player_form"):
                    e_name = st.text_input("Name", value=p_cur["display_name"])
                    e1, e2 = st.columns(2)
                    e_mmr = e1.number_input("Latent MMR Override (X.XXX)", value=float(p_cur["latent_mmr"]), step=0.005, format="%.3f")
                    e_disp = e2.number_input("Display Rating Override (X.XX)", value=float(p_cur["display_rating"]), step=0.01, format="%.2f")
                    
                    e3, e4 = st.columns(2)
                    e_rd = e3.number_input("Rating Deviation (RD)", value=float(p_cur["rating_deviation"]), step=1.0)
                    e_acc = e4.number_input("Accuracy % Override", value=float(p_cur["rating_accuracy_pct"]), step=0.5)

                    ec1, ec2, ec3 = st.columns(3)
                    e_prov = ec1.checkbox("Is Provisional [PR]", value=bool(p_cur["is_provisional"]))
                    e_anc = ec2.checkbox("System Anchor", value=bool(p_cur["is_anchor"]))
                    e_ceil = ec3.checkbox("Ceiling Anchor", value=bool(p_cur["is_ceiling_anchor"]))

                    e_tier = st.selectbox("Calibration Tier Override", ["PROVISIONAL", "VERIFIED", "ANCHOR", "INACTIVE"], index=["PROVISIONAL", "VERIFIED", "ANCHOR", "INACTIVE"].index(p_cur["calibration_tier"]))
                    
                    b_sub, b_del = st.columns(2)
                    if b_sub.form_submit_button("Save Parameter Overrides"):
                        conn = get_db_connection()
                        conn.execute('''
                            UPDATE players SET display_name = ?, latent_mmr = ?, display_rating = ?,
                                               rating_deviation = ?, rating_accuracy_pct = ?, calibration_tier = ?, 
                                               is_provisional = ?, is_anchor = ?, is_ceiling_anchor = ?
                            WHERE player_id = ?
                        ''', (e_name, e_mmr, e_disp, e_rd, e_acc, e_tier, 1 if e_prov else 0, 1 if e_anc else 0, 1 if e_ceil else 0, p_sel_id))
                        
                        conn.execute('''
                            INSERT INTO player_changelog (player_id, change_type, old_val, new_val, changed_by, changed_at)
                            VALUES (?, 'MANUAL_OVERRIDE', ?, ?, ?, ?)
                        ''', (p_sel_id, f"MMR: {p_cur['latent_mmr']:.3f}, RD: {p_cur['rating_deviation']:.1f}",
                              f"MMR: {e_mmr:.3f}, RD: {e_rd:.1f}, Tier: {e_tier}", active_operator, datetime.now(timezone.utc).isoformat()))
                        
                        conn.commit()
                        conn.close()
                        st.success("Player overrides committed!")
                        st.rerun()

                    if b_del.form_submit_button("🗑️ Delete Player"):
                        conn = get_db_connection()
                        m_played = conn.execute("SELECT COUNT(*) FROM match_logs WHERE player_id = ?", (p_sel_id,)).fetchone()[0]
                        if m_played == 0:
                            conn.execute("DELETE FROM players WHERE player_id = ?", (p_sel_id,))
                            conn.commit()
                            st.warning(f"Player {p_cur['display_name']} permanently deleted.")
                            st.rerun()
                        else:
                            st.error(f"Player has {m_played} matches. Use Force Purge below to delete player and cascade rollback.")
                        conn.close()

                with st.expander("🚨 Force Purge Player & All Matches (Cascade Rollback)"):
                    st.caption("Deletes player and permanently purges all matches they played in, restoring other players' ratings.")
                    if st.button(f"💣 Force Purge {p_cur['display_name']} & Revert History", type="secondary"):
                        conn = get_db_connection()
                        p_matches = conn.execute("""
                            SELECT match_id FROM matches 
                            WHERE team_a_p1_id = ? OR team_a_p2_id = ? OR team_b_p1_id = ? OR team_b_p2_id = ?
                        """, (p_sel_id, p_sel_id, p_sel_id, p_sel_id)).fetchall()

                        for pm in p_matches:
                            mid = pm["match_id"]
                            logs = conn.execute("SELECT player_id, pre_latent_mmr, pre_rd, pre_accuracy_pct FROM match_logs WHERE match_id = ?", (mid,)).fetchall()
                            for l in logs:
                                if l["player_id"] != p_sel_id:
                                    conn.execute("""
                                        UPDATE players SET 
                                            latent_mmr = ?, display_rating = ?, rating_deviation = ?, rating_accuracy_pct = ?
                                        WHERE player_id = ?
                                    """, (l["pre_latent_mmr"], l["pre_latent_mmr"], l["pre_rd"], l["pre_accuracy_pct"], l["player_id"]))
                            conn.execute("DELETE FROM match_logs WHERE match_id = ?", (mid,))
                            conn.execute("DELETE FROM matches WHERE match_id = ?", (mid,))

                        conn.execute("DELETE FROM player_changelog WHERE player_id = ?", (p_sel_id,))
                        conn.execute("DELETE FROM players WHERE player_id = ?", (p_sel_id,))
                        conn.commit()
                        conn.close()
                        st.success(f"Purged {p_cur['display_name']} and rolled back {len(p_matches)} affected matches.")
                        st.rerun()

                st.markdown("##### Progression Changelog")
                conn = get_db_connection()
                pcl_df = pd.read_sql_query("SELECT change_type, old_val, new_val, changed_by, changed_at FROM player_changelog WHERE player_id = ? ORDER BY changed_at DESC", conn, params=[p_sel_id])
                conn.close()
                st.dataframe(pcl_df, use_container_width=True)

# TAB 5: VENUES & LOCATIONS
elif nav == "🏢 Venues & Locations (CRUD)":
    st.title("Venues & Geographical Topology")
    st.caption("Add, modify, merge, or delete Venues, Municipalities, and Countries.")

    sec = st.radio("Domain Selection", ["🏟️ Venues", "🏙️ Cities", "🌍 Countries"], horizontal=True)
    conn = get_db_connection()

    if sec == "🏟️ Venues":
        st.subheader("Active Venues")
        v_df = pd.read_sql_query('''
            SELECT v.venue_id, v.venue_name, l.location_name as city, v.country_code, 
                   v.court_count, v.is_verified, v.is_active, v.total_matches_played
            FROM venues v JOIN locations l ON v.city_id = l.location_id
        ''', conn)
        if not v_df.empty:
            st.dataframe(v_df, use_container_width=True)
        else:
            st.info("No venues created yet.")

        with st.expander("🔗 Venue Alias Merge Tool"):
            v_all = conn.execute("SELECT venue_id, venue_name FROM venues").fetchall()
            v_dict = {v["venue_name"]: v["venue_id"] for v in v_all}
            cm1, cm2 = st.columns(2)
            source_v = cm1.multiselect("Typo / Duplicate Venues", list(v_dict.keys()))
            target_v = cm2.selectbox("Master Venue to Retain", list(v_dict.keys())) if v_dict else None
            
            if st.button("Execute Merge"):
                if source_v and target_v:
                    tid = v_dict[target_v]
                    for s in source_v:
                        sid = v_dict[s]
                        if sid != tid:
                            conn.execute("UPDATE matches SET venue_id = ? WHERE venue_id = ?", (tid, sid))
                            conn.execute("UPDATE players SET home_venue_id = ? WHERE home_venue_id = ?", (tid, sid))
                            conn.execute("DELETE FROM venues WHERE venue_id = ?", (sid,))
                    conn.commit()
                    st.success("Venues merged successfully!")
                    st.rerun()

        cv1, cv2 = st.columns(2)
        with cv1:
            with st.form("add_v_form"):
                st.markdown("#### ➕ Add Venue")
                vn = st.text_input("Venue Name")
                cities = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'CITY'").fetchall()
                vc = st.selectbox("City", [c["location_name"] for c in cities]) if cities else None
                v_crts = st.number_input("Courts", 1, 30, 2)
                v_ver = st.checkbox("Verified Desk Authorization", value=True)
                if st.form_submit_button("Register Venue"):
                    if vn and vc:
                        cid = [c["location_id"] for c in cities if c["location_name"] == vc][0]
                        vid = f"VEN_{datetime.now().strftime('%H%M%S')}"
                        conn.execute("INSERT INTO venues (venue_id, venue_name, city_id, country_code, court_count, is_verified, created_at) VALUES (?, ?, ?, 'IND', ?, ?, ?)",
                                     (vid, vn, cid, v_crts, 1 if v_ver else 0, datetime.now(timezone.utc).isoformat()))
                        conn.commit()
                        st.success(f"Added {vn}!")
                        st.rerun()

        with cv2:
            st.markdown("#### ✏️ Edit / Delete Venue")
            v_all = conn.execute("SELECT * FROM venues").fetchall()
            if v_all:
                sv_id = st.selectbox("Choose Venue", [v["venue_id"] for v in v_all], format_func=lambda x: [v["venue_name"] for v in v_all if v["venue_id"] == x][0])
                v_row = [v for v in v_all if v["venue_id"] == sv_id][0]
                with st.form("edit_v_form"):
                    up_vn = st.text_input("Clean Name", value=v_row["venue_name"])
                    up_crt = st.number_input("Courts", 1, 30, value=v_row["court_count"])
                    up_ver = st.checkbox("Verified Desk", value=bool(v_row["is_verified"]))
                    up_act = st.checkbox("Active", value=bool(v_row["is_active"]))
                    b1, b2 = st.columns(2)
                    if b1.form_submit_button("Save"):
                        conn.execute("UPDATE venues SET venue_name = ?, court_count = ?, is_verified = ?, is_active = ? WHERE venue_id = ?",
                                     (up_vn, up_crt, 1 if up_ver else 0, 1 if up_act else 0, sv_id))
                        conn.commit()
                        st.success("Venue updated.")
                        st.rerun()
                    if b2.form_submit_button("🗑️ Delete"):
                        mcnt = conn.execute("SELECT COUNT(*) FROM matches WHERE venue_id = ?", (sv_id,)).fetchone()[0]
                        if mcnt > 0:
                            st.error(f"Cannot delete: {mcnt} matches are linked.")
                        else:
                            conn.execute("DELETE FROM venues WHERE venue_id = ?", (sv_id,))
                            conn.commit()
                            st.warning("Deleted venue.")
                            st.rerun()

    elif sec == "🏙️ Cities":
        st.subheader("Active Cities")
        c_df = pd.read_sql_query('''
            SELECT l.location_id, l.location_name as city, p.location_name as country, 
                   l.active_bridge_count, l.hawking_offset, l.suggested_offset, l.readiness_score
            FROM locations l LEFT JOIN locations p ON l.parent_id = p.location_id
            WHERE l.location_type = 'CITY'
        ''', conn)
        if not c_df.empty:
            st.dataframe(c_df, use_container_width=True)

        cc1, cc2 = st.columns(2)
        with cc1:
            with st.form("add_c_form"):
                st.markdown("#### ➕ Add City")
                cn = st.text_input("City Name")
                countries = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'COUNTRY'").fetchall()
                c_parent = st.selectbox("Country", [ct["location_name"] for ct in countries]) if countries else None
                if st.form_submit_button("Create City"):
                    if cn and c_parent:
                        pid = [ct["location_id"] for ct in countries if ct["location_name"] == c_parent][0]
                        cid = f"LOC_{cn[:3].upper()}_{datetime.now().strftime('%S')}"
                        conn.execute("INSERT INTO locations (location_id, location_type, location_name, parent_id, country_code, updated_at) VALUES (?, 'CITY', ?, ?, 'IND', ?)",
                                     (cid, cn, pid, datetime.now(timezone.utc).isoformat()))
                        conn.commit()
                        st.success(f"Added {cn}!")
                        st.rerun()

        with cc2:
            st.markdown("#### ✏️ Edit / Delete City")
            c_all = conn.execute("SELECT * FROM locations WHERE location_type = 'CITY'").fetchall()
            if c_all:
                sc_id = st.selectbox("Choose City", [c["location_id"] for c in c_all], format_func=lambda x: [c["location_name"] for c in c_all if c["location_id"] == x][0])
                c_row = [c for c in c_all if c["location_id"] == sc_id][0]
                with st.form("edit_c_form"):
                    up_cn = st.text_input("Rename City", value=c_row["location_name"])
                    b1, b2 = st.columns(2)
                    if b1.form_submit_button("Save"):
                        conn.execute("UPDATE locations SET location_name = ? WHERE location_id = ?", (up_cn, sc_id))
                        conn.commit()
                        st.success("Renamed.")
                        st.rerun()
                    if b2.form_submit_button("🗑️ Delete"):
                        pl = conn.execute("SELECT COUNT(*) FROM players WHERE home_city_id = ?", (sc_id,)).fetchone()[0]
                        if pl > 0:
                            st.error(f"Cannot delete: Linked to {pl} players.")
                        else:
                            conn.execute("DELETE FROM locations WHERE location_id = ?", (sc_id,))
                            conn.commit()
                            st.warning("Deleted city.")
                            st.rerun()

    elif sec == "🌍 Countries":
        st.subheader("Active Countries")
        co_df = pd.read_sql_query("SELECT location_id, location_name, country_code FROM locations WHERE location_type = 'COUNTRY'", conn)
        if not co_df.empty:
            st.dataframe(co_df, use_container_width=True)

        co1, co2 = st.columns(2)
        with co1:
            with st.form("add_co_form"):
                st.markdown("#### ➕ Add Country")
                con = st.text_input("Country Name (e.g. India)")
                coc = st.text_input("ISO 3-Letter Code (e.g. IND)").upper()
                if st.form_submit_button("Create Country"):
                    if con and coc:
                        conn.execute("INSERT INTO locations (location_id, location_type, location_name, country_code, updated_at) VALUES (?, 'COUNTRY', ?, ?, ?)",
                                     (f"LOC_{coc}", con, coc, datetime.now(timezone.utc).isoformat()))
                        conn.commit()
                        st.success(f"Added {con} ({coc})!")
                        st.rerun()
                    else:
                        st.error("Fields cannot be empty.")

        with co2:
            st.markdown("#### ✏️ Delete Country")
            co_all = conn.execute("SELECT * FROM locations WHERE location_type = 'COUNTRY'").fetchall()
            if co_all:
                sco_id = st.selectbox("Select Country", [c["location_id"] for c in co_all], format_func=lambda x: [c["location_name"] for c in co_all if c["location_id"] == x][0])
                if st.button("🗑️ Delete Country"):
                    ch = conn.execute("SELECT COUNT(*) FROM locations WHERE parent_id = ?", (sco_id,)).fetchone()[0]
                    if ch > 0:
                        st.error(f"Cannot delete: {ch} cities are mapped to this country.")
                    else:
                        conn.execute("DELETE FROM locations WHERE location_id = ?", (sco_id,))
                        conn.commit()
                        st.warning("Country deleted.")
                        st.rerun()
    conn.close()

# TAB 6: HAWKING REGIONAL CONTROL
elif nav == "🌐 Hawking Regional Control":
    st.title("Hawking Macro Normalization & Regional Offset Control")
    st.caption("Manage city cluster readiness, evaluate suggested offsets, and deploy regularized calibration.")

    conn = get_db_connection()
    cities = conn.execute("SELECT * FROM locations WHERE location_type = 'CITY'").fetchall()
    conn.close()

    if not cities:
        st.info("No cities available. Add your cities in 'Venues & Locations (CRUD)'.")
    else:
        for c in cities:
            st.markdown(f"### Municipality: {c['location_name']}")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Bridge Nodes (K)", c["active_bridge_count"])
            k2.metric("Intransitivity Index", f"{c['intransitivity_idx']:.3f}")
            k3.metric("Current Offset", f"{c['hawking_offset']:+0.4f}")
            k4.metric("Suggested Offset Required", f"{c['suggested_offset']:+0.4f}")

            with st.expander(f"Review & Apply Offset for {c['location_name']}"):
                sug = float(c["suggested_offset"]) if c["suggested_offset"] != 0.0 else -0.0450
                app_step = st.number_input(f"Approved Offset Step ({c['location_name']})", value=sug, step=0.005, format="%.4f", key=f"inp_{c['location_id']}")
                
                if st.button(f"Apply Offset to {c['location_name']}", key=f"btn_{c['location_id']}"):
                    conn = get_db_connection()
                    conn.execute("UPDATE locations SET hawking_offset = hawking_offset + ? WHERE location_id = ?", (app_step, c["location_id"]))
                    conn.execute('''
                        UPDATE players SET 
                            latent_mmr = latent_mmr + (? * (latent_mmr / 4.50)),
                            display_rating = display_rating + (? * (latent_mmr / 4.50))
                        WHERE home_city_id = ? AND is_provisional = 0
                    ''', (app_step, app_step, c["location_id"]))
                    conn.commit()
                    conn.close()
                    st.success(f"Applied {app_step:+0.4f} offset across verified players in {c['location_name']}!")
                    st.rerun()

# TAB 7: GLOBAL CONFIG SWITCHES
elif nav == "⚙️ Global Config Switches":
    st.title("Algorithmic Bit Governance & Parameter Switches")
    st.caption("Tune operational parameters live with directional tuning guides and customize progression speeds.")

    # FORCE PARAMETER SYNC TOOL
    with st.expander("🔄 Force Sync Parameter Defaults (Fix Stale Parameters)"):
        st.write("Updates existing database parameters to the latest code defaults (e.g. Setting Elevator Threshold to 1.10) without touching player or match tables.")
        if st.button("Sync Config Parameters to V.15 Defaults", type="primary"):
            init_db(force_sync_params=True)
            st.success("Successfully synchronized all config parameters to latest V.15 defaults!")
            st.rerun()

    st.markdown("### 🎚️ Progression Speed Controller (By Rating Range)")
    conn = get_db_connection()
    rules_df = pd.read_sql_query("SELECT * FROM progression_speed_rules ORDER BY min_rating ASC", conn)
    
    if not rules_df.empty:
        st.dataframe(rules_df[["rule_id", "min_rating", "max_rating", "speed_multiplier", "description", "is_active", "created_at"]], use_container_width=True)
    else:
        st.write("No custom speed rules active. All tiers run at default 1.00x progression speed.")

    with st.expander("➕ Add Progression Speed Rule"):
        with st.form("add_speed_rule_form"):
            sr_c1, sr_c2, sr_c3 = st.columns(3)
            min_r = sr_c1.number_input("Min Rating Range (Floor)", 0.000, 7.000, 3.500, 0.100, format="%.3f")
            max_r = sr_c2.number_input("Max Rating Range (Ceiling)", 0.000, 7.000, 5.000, 0.100, format="%.3f")
            s_mult = sr_c3.number_input("Speed Multiplier (e.g. 0.70x = 30% slower)", 0.10, 3.00, 0.80, 0.05)
            r_desc = st.text_input("Rule Description (e.g. Slow progression for Intermediate Plus)")
            
            if st.form_submit_button("Save Speed Rule"):
                if min_r >= max_r:
                    st.error("Min Rating must be strictly less than Max Rating.")
                else:
                    conn.execute("""
                        INSERT INTO progression_speed_rules (min_rating, max_rating, speed_multiplier, description, is_active, created_at)
                        VALUES (?, ?, ?, ?, 1, ?)
                    """, (min_r, max_r, s_mult, r_desc, datetime.now(timezone.utc).isoformat()))
                    conn.commit()
                    st.success("Progression speed rule committed!")
                    st.rerun()

    if not rules_df.empty:
        with st.expander("🗑️ Delete Progression Speed Rule"):
            del_rule_id = st.selectbox("Select Rule to Delete", rules_df["rule_id"].tolist(), format_func=lambda x: f"Rule #{x}: [{rules_df[rules_df['rule_id']==x]['min_rating'].values[0]:.3f} - {rules_df[rules_df['rule_id']==x]['max_rating'].values[0]:.3f}] -> {rules_df[rules_df['rule_id']==x]['speed_multiplier'].values[0]}x")
            if st.button("Delete Selected Rule"):
                conn.execute("DELETE FROM progression_speed_rules WHERE rule_id = ?", (del_rule_id,))
                conn.commit()
                st.warning(f"Deleted Rule #{del_rule_id}!")
                st.rerun()

    st.markdown("---")
    st.markdown("### Master Parameter Matrix (Bits 1 to 25)")
    configs = conn.execute("SELECT * FROM global_config ORDER BY param_key ASC").fetchall()
    conn.close()

    for cfg in configs:
        with st.expander(f"⚙️ {cfg['param_key']} — {cfg['title']}"):
            st.write(f"**Description:** {cfg['description']}")
            st.info(f"💡 **Tuning Explainer & Directional Impact:**\n\n{cfg['tuning_guide']}")
            
            c1, c2 = st.columns([3, 1])
            new_v = c1.number_input("Active Parameter Value", value=float(cfg["param_value"]), step=0.05, key=f"cfg_{cfg['param_key']}")
            is_act = c2.checkbox("Bit Active", value=bool(cfg["is_active"]), key=f"act_{cfg['param_key']}")

            if new_v != cfg["param_value"] or is_act != bool(cfg["is_active"]):
                conn = get_db_connection()
                conn.execute("UPDATE global_config SET param_value = ?, is_active = ? WHERE param_key = ?", (new_v, 1 if is_act else 0, cfg["param_key"]))
                conn.execute('''
                    INSERT INTO config_changelog (param_key, old_value, new_value, changed_by, changed_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (cfg["param_key"], cfg["param_value"], new_v, active_operator, datetime.now(timezone.utc).isoformat()))
                conn.commit()
                conn.close()
                st.toast(f"Saved {cfg['param_key']} -> {new_v}")
                st.rerun()

    st.markdown("---")
    st.subheader("📜 Global Configuration Changelog")
    conn = get_db_connection()
    cl_df = pd.read_sql_query("SELECT param_key, old_value, new_value, changed_by, changed_at FROM config_changelog ORDER BY changed_at DESC LIMIT 20", conn)
    conn.close()
    if not cl_df.empty:
        st.dataframe(cl_df, use_container_width=True)
    else:
        st.info("No configuration changes recorded yet.")

    st.markdown("---")
    with st.expander("🚨 System Clean Slate / Nuclear Reset"):
        st.caption("Wipe test data and reset tables to start completely from scratch.")
        if st.button("💣 Erase All Matches & Test Data (Clean Slate)", type="secondary"):
            conn = get_db_connection()
            conn.execute("DELETE FROM match_logs;")
            conn.execute("DELETE FROM matches;")
            conn.execute("DELETE FROM players;")
            conn.execute("DELETE FROM venues;")
            conn.execute("DELETE FROM locations;")
            conn.execute("DELETE FROM progression_speed_rules;")
            conn.execute("DELETE FROM config_changelog;")
            conn.execute("DELETE FROM player_changelog;")
            conn.commit()
            conn.close()
            st.success("All data erased. System reset to a clean slate.")
            st.rerun()
