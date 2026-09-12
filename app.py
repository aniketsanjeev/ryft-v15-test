import streamlit as st
import sqlite3
import math
import json
import os
from datetime import datetime, timezone
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
        active_venues_count INTEGER DEFAULT 0,
        median_latent_mmr REAL DEFAULT 3.0000,
        highest_player_mmr REAL DEFAULT 3.0000,
        lowest_player_mmr REAL DEFAULT 3.0000,
        updated_at TEXT,
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

    # 3. Match Formats Table
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

    # 4. Tournament Hosts (V15.1 Extension)
    c.execute('''
    CREATE TABLE IF NOT EXISTS tournament_hosts (
        host_id TEXT PRIMARY KEY,
        organization_name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        is_venue INTEGER DEFAULT 0,
        venue_id TEXT,
        is_verified INTEGER DEFAULT 0,
        verification_tier TEXT DEFAULT 'COMMUNITY',
        contact_email TEXT NOT NULL,
        city_id TEXT NOT NULL,
        country_code TEXT NOT NULL,
        total_tournaments INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (venue_id) REFERENCES venues(venue_id) ON DELETE SET NULL,
        FOREIGN KEY (city_id) REFERENCES locations(location_id) ON DELETE RESTRICT
    )''')

    # 5. Tournament Sponsors (V15.1 Extension)
    c.execute('''
    CREATE TABLE IF NOT EXISTS tournament_sponsors (
        sponsor_id TEXT PRIMARY KEY,
        host_id TEXT NOT NULL,
        sponsor_name TEXT NOT NULL,
        logo_svg_url TEXT,
        placement_type TEXT DEFAULT 'MATCH_CARD_BADGE',
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (host_id) REFERENCES tournament_hosts(host_id) ON DELETE CASCADE
    )''')

    # 6. Players Table
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
        last_tournament_sync_at TEXT,
        created_at TEXT,
        FOREIGN KEY (home_venue_id) REFERENCES venues(venue_id) ON DELETE SET NULL,
        FOREIGN KEY (home_city_id) REFERENCES locations(location_id) ON DELETE CASCADE
    )''')

    # 7. Matches Table
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
        host_id TEXT,
        sponsor_id TEXT,
        is_retroactive INTEGER DEFAULT 0,
        processed_at TEXT,
        match_timestamp TEXT NOT NULL,
        FOREIGN KEY (venue_id) REFERENCES venues(venue_id) ON DELETE RESTRICT,
        FOREIGN KEY (format_id) REFERENCES match_formats(format_id) ON DELETE RESTRICT
    )''')

    # 8. Match Logs Table
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
        is_retroactive INTEGER DEFAULT 0,
        logged_at TEXT NOT NULL,
        FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,
        FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE
    )''')

    # 9. Global Configuration Parameter Matrix
    c.execute('''
    CREATE TABLE IF NOT EXISTS global_config (
        param_key TEXT PRIMARY KEY,
        param_value REAL NOT NULL,
        is_active INTEGER DEFAULT 1,
        title TEXT,
        description TEXT,
        tuning_guide TEXT
    )''')

    # 10. Config ChangeLog
    c.execute('''
    CREATE TABLE IF NOT EXISTS config_changelog (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        param_key TEXT NOT NULL,
        old_value REAL NOT NULL,
        new_value REAL NOT NULL,
        changed_by TEXT NOT NULL,
        changed_at TEXT NOT NULL
    )''')

    # 11. Player Profile ChangeLog
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

    # Safe Column Migrations for Existing Tables
    add_column_if_not_exists(c, "players", "accuracy_s_rd", "REAL DEFAULT 0.0")
    add_column_if_not_exists(c, "players", "accuracy_s_matches", "REAL DEFAULT 0.0")
    add_column_if_not_exists(c, "players", "accuracy_s_diversity", "REAL DEFAULT 0.0")
    add_column_if_not_exists(c, "match_logs", "pre_display_rating", "REAL DEFAULT 3.0")
    add_column_if_not_exists(c, "match_logs", "post_display_rating", "REAL DEFAULT 3.0")
    add_column_if_not_exists(c, "matches", "guardrails_summary", "TEXT DEFAULT '[]'")

    # Seed All 18 Official Match Formats using in-place UPSERT (Never deletes referenced rows)
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

    # Master Configuration Parameters
    master_params = [
        ("R_MIN", 0.0000, 1, "Scale Floor", "Absolute rating floor.", "Clamps lowest possible rating to 0.0000."),
        ("R_MAX", 7.0000, 1, "Scale Ceiling", "Absolute unbreachable rating ceiling.", "Must remain 7.0000 to preserve tier definitions."),
        ("R_ELITE_THRESHOLD", 6.3000, 1, "Elite Drag Gate", "Rating where exponential drag engages.", "Lowering applies drag earlier."),
        ("ELITE_DRAG_EXPONENT", 2.5, 1, "Elite Drag Exponent", "Curvature steepness of pro ceiling resistance.", "Higher values make 7.0000 harder to reach."),
        ("POWER_MEAN_P", 3.0, 1, "Doubles Cubic Exponent", "Cubic weighting power mean for doubles.", "3.0 gives a 70/30 anchor weighting bias."),
        ("LOGISTIC_BETA", 2.0, 1, "Logistic Scale Factor", "Logistic expectancy curve scale denominator.", "Lowering boosts upset rewards."),
        ("K_MAX", 0.4000, 1, "Beginner Max Volatility", "Base step volatility for players at R = 0.000.", "Higher values accelerate beginner tier progression."),
        ("K_MIN", 0.0800, 1, "Pro Min Volatility", "Base step volatility for players at R = 7.000.", "Lower values lock pro ratings tighter against variance."),
        ("MARGIN_BASE", 0.80, 1, "Margin Floor Factor", "Minimum score factor for narrow finishes.", "Points floor for tight 7-6 tiebreaks."),
        ("MARGIN_SCALE", 0.40, 1, "Margin Blowout Scale", "Maximum bonus factor for blowouts.", "Full blowout bonus = Base + Scale = 1.20."),
        ("ELEVATOR_MARGIN_THRESH", 1.15, 1, "Elevator Margin Gate", "Score margin needed to trip 3x Elevator boost.", "Requires blowout (>= 1.15) to accelerate unranked smurfs."),
        ("ELEVATOR_ACCEL_FACTOR", 3.0, 1, "Elevator Boost Multiplier", "Multiplier applied to provisional blowouts.", "Triples step size for unranked winners."),
        ("MAX_ELEVATOR_DELTA", 0.7500, 1, "Elevator Placement Cap", "Max points a smurf can win in one blowout game.", "Bypasses casual daily ceiling up to +0.7500."),
        ("MAX_8H_EXCHANGE_CAP", 0.0000, 0, "8-Hour Rolling Cap", "Tight-window point transfer cap.", "Active when > 0.0000."),
        ("MAX_12H_EXCHANGE_CAP", 0.0000, 0, "12-Hour Rolling Cap", "Half-day point transfer cap.", "Active when > 0.0000."),
        ("MAX_24H_EXCHANGE_CAP", 0.1500, 1, "24-Hour Casual Cap", "Net 24-hour casual transfer ceiling between 4 players.", "Prevents friend groups from farming rating points."),
        ("MAX_48H_EXCHANGE_CAP", 0.0000, 0, "48-Hour Rolling Cap", "Weekend point transfer cap.", "Active when > 0.0000."),
        ("SESSION_EXCHANGE_CAP", 0.3000, 1, "Verified Session Cap", "Elevated cap for verified club events with 6+ players.", "Doubles the daily limit for official club mixers."),
        ("MIN_SESSION_PLAYERS", 6, 1, "Session Participant Floor", "Min players required to unlock session cap.", "Events with fewer than 6 players revert to 0.1500 cap."),
        ("RD_MIN", 30.0, 1, "Certainty Floor", "Absolute uncertainty floor.", "Prevents RD from dropping below 30.0."),
        ("RD_MAX", 350.0, 1, "Unrated Starting RD", "Uncertainty assigned at registration.", "Baseline starting uncertainty for all new accounts."),
        ("RD_INFO_VARIANCE", 65.0, 1, "Bayesian Contraction Speed", "Denominator in per-match RD shrinkage formula.", "Lower values shrink RD faster per match."),
        ("INACTIVITY_CONSTANT", 12.0, 1, "Inactivity Rust Rate", "Monthly temporal uncertainty growth.", "Points of RD regained per inactive month."),
        ("BRIDGE_RD_THRESHOLD", 80.0, 1, "Bridge Node Max RD", "Max RD to qualify as Bridge Node.", "Only players with RD <= 80 count as measuring travelers."),
        ("BRIDGE_MIN_MATCHES", 5, 1, "Bridge Match Minimum", "Away matches required to link locations.", "Matches required before a traveler links regional pools."),
        ("LAMBDA_BRIDGE_DAMPING", 3.0, 1, "Tikhonov Bridge Lambda", "Traveler shock absorber damping parameter.", "Higher values require more travelers before an offset deploys."),
        ("CIRCUIT_BREAKER", 0.0250, 1, "Auto Cron Safety Ceiling", "Maximum shift per automated weekly cycle.", "Limits automated Sunday macro shifts to +/-0.0250."),
        ("ADMIN_OVERRIDE_MAX", 0.0750, 1, "Admin Sandbox Shift Window", "Max human-approved offset for unlinked cities.", "Ceiling for manual Admin calibration deployments."),
        ("ACCURACY_WEIGHT_RD", 0.50, 1, "Accuracy Weight: RD", "Weight for Pillar 1 (Statistical Certainty).", "Controls influence of mathematical uncertainty (RD)."),
        ("ACCURACY_WEIGHT_MATCHES", 0.25, 1, "Accuracy Weight: Matches", "Weight for Pillar 2 (Match Depth).", "Controls importance of verified match volume."),
        ("ACCURACY_WEIGHT_DIVERSITY", 0.25, 1, "Accuracy Weight: Diversity", "Weight for Pillar 3 (Network Diversity).", "Controls importance of playing unique opponents."),
        ("TIER_PROVISIONAL_MAX", 69.99, 1, "Provisional Score Ceiling", "Upper score bound for Tier 1 [PR].", "Players with accuracy below this score remain Provisional."),
        ("TIER_VERIFIED_MAX", 89.99, 1, "Verified Score Ceiling", "Upper score bound for Tier 2 Verified.", "Score required to cross to elite Anchor tier."),
        ("TARGET_MATCHES_PROV", 3, 1, "Provisional Match Quota", "Target matches during onboarding placement.", "Matches needed to satisfy sample depth during placement."),
        ("TARGET_OPPONENTS_PROV", 2, 1, "Provisional Opponent Quota", "Target opponents during onboarding placement.", "Opponents needed during placement."),
        ("TARGET_MATCHES_VERIFIED", 5, 1, "Verified Tier Match Quota", "Target matches required for Verified tier.", "Verified match count needed for verified accuracy."),
        ("TARGET_OPPONENTS_VERIFIED", 3, 1, "Verified Tier Opponent Quota", "Target opponents required for Verified tier.", "Distinct opponents needed for verified accuracy."),
        ("TARGET_MATCHES_ANCHOR", 15, 1, "Anchor Tier Match Quota", "Target matches required for Anchor tier.", "Match volume needed for Anchor tier."),
        ("TARGET_OPPONENTS_ANCHOR", 8, 1, "Anchor Tier Opponent Quota", "Target opponents required for Anchor tier.", "Distinct opponents needed for Anchor tier."),
        ("PROVISIONAL_RD_GATE", 100.0, 1, "Tri-Gate Max RD", "Uncertainty gate for provisional exit.", "RD must be <= 100 to exit [PR]."),
        ("PROVISIONAL_MIN_MATCHES", 5, 1, "Tri-Gate Min Matches", "Match count gate for provisional exit.", "Verified matches required before [PR] badge clears."),
        ("PROVISIONAL_MIN_OPPONENTS", 3, 1, "Tri-Gate Min Opponents", "Network diversity gate for provisional exit.", "Unique opponents faced required before [PR] badge clears."),
        ("MAX_RETROACTIVE_INGESTION_DAYS", 7, 1, "Retroactive Cutoff Window", "Max age in days for tournament uploads.", "Batches older than this window are rejected."),
        ("ALLOW_ASYNC_TOURNAMENT_STACKING", 1, 1, "Async Additive Stacking Toggle", "Authorizes forward delta stacking.", "Permits delayed tournament results to stack additively.")
    ]
    for k, v, act, tit, desc, tune in master_params:
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
# 2. V.15 COMPLETE ALGORITHMIC CALCULATION ENGINES
# ==============================================================================
class RyftEngineV15:
    @staticmethod
    def get_configs():
        conn = get_db_connection()
        rows = conn.execute("SELECT param_key, param_value, is_active FROM global_config").fetchall()
        conn.close()
        return {r["param_key"]: (r["param_value"] if r["is_active"] == 1 else None) for r in rows}

    @staticmethod
    def calculate_accuracy_suite(rd, match_count, opp_count, is_currently_prov, cfg):
        rd_min = cfg.get("RD_MIN", 30.0) or 30.0
        rd_max = cfg.get("RD_MAX", 350.0) or 350.0
        
        # Pillar 1: Statistical Certainty Score (0.0 to 1.0)
        s_rd = max(0.0, min(1.0, (rd_max - rd) / (rd_max - rd_min)))

        # Dynamic Tier Targets based on active calibration status
        if is_currently_prov:
            t_matches = cfg.get("TARGET_MATCHES_VERIFIED", 5) or 5
            t_opps = cfg.get("TARGET_OPPONENTS_VERIFIED", 3) or 3
        else:
            t_matches = cfg.get("TARGET_MATCHES_ANCHOR", 15) or 15
            t_opps = cfg.get("TARGET_OPPONENTS_ANCHOR", 8) or 8

        # Pillar 2: Match Sample Depth Score (0.0 to 1.0)
        s_matches = min(1.0, match_count / float(t_matches))

        # Pillar 3: Opponent Network Diversity Score (0.0 to 1.0)
        s_diversity = min(1.0, opp_count / float(t_opps))

        # Weights
        w_rd = cfg.get("ACCURACY_WEIGHT_RD", 0.50) if cfg.get("ACCURACY_WEIGHT_RD") is not None else 0.50
        w_m = cfg.get("ACCURACY_WEIGHT_MATCHES", 0.25) if cfg.get("ACCURACY_WEIGHT_MATCHES") is not None else 0.25
        w_d = cfg.get("ACCURACY_WEIGHT_DIVERSITY", 0.25) if cfg.get("ACCURACY_WEIGHT_DIVERSITY") is not None else 0.25

        composite_acc = round(((w_rd * s_rd) + (w_m * s_matches) + (w_d * s_diversity)) * 100.0, 2)

        # Tri-Gate Provisional Exit Enforcement
        prov_rd_gate = cfg.get("PROVISIONAL_RD_GATE", 100.0) or 100.0
        prov_min_m = cfg.get("PROVISIONAL_MIN_MATCHES", 5) or 5
        prov_min_d = cfg.get("PROVISIONAL_MIN_OPPONENTS", 3) or 3

        tri_gate_passed = (rd <= prov_rd_gate and match_count >= prov_min_m and opp_count >= prov_min_d)
        new_is_prov = 0 if tri_gate_passed else 1

        tier_prov_max = cfg.get("TIER_PROVISIONAL_MAX", 69.99) or 69.99
        tier_ver_max = cfg.get("TIER_VERIFIED_MAX", 89.99) or 89.99

        if composite_acc >= tier_ver_max and new_is_prov == 0 and rd <= 60.0:
            cal_tier = "ANCHOR"
        elif composite_acc >= tier_prov_max and new_is_prov == 0:
            cal_tier = "VERIFIED"
        else:
            cal_tier = "PROVISIONAL"

        return {
            "s_rd_pct": round(s_rd * 100.0, 1),
            "s_matches_pct": round(s_matches * 100.0, 1),
            "s_diversity_pct": round(s_diversity * 100.0, 1),
            "composite_accuracy": composite_acc,
            "calibration_tier": cal_tier,
            "is_provisional": new_is_prov
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

            is_elevator = False
            el_thresh = cfg.get("ELEVATOR_MARGIN_THRESH", 1.15) or 1.15
            el_factor = cfg.get("ELEVATOR_ACCEL_FACTOR", 3.0) or 3.0
            if p_data["is_provisional"] and s_margin >= el_thresh and is_winner and r_curr < r_elite:
                k_base *= el_factor
                is_elevator = True
                p_flags.append("ELEVATOR_3X_BOOST: Provisional blowout victory; learning rate tripled.")

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

            # Bit 11: Bayesian Contraction Formula
            sigma_info = cfg.get("RD_INFO_VARIANCE", 65.0) or 65.0
            inv_prior = 1.0 / (p_rd**2)
            inv_info = (mc * s_margin * (g_opp**2)) / (sigma_info**2)
            new_rd = max(30.0, min(350.0, math.sqrt(1.0 / (inv_prior + inv_info))))

            # Module 8: Comprehensive Rating Accuracy & Calibration Status
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
    "🎾 Matches Hub", 
    "👥 Players Roster", 
    "🏢 Venues & Locations (CRUD)", 
    "🌐 Hawking Regional Control", 
    "⚙️ Global Config Switches"
])

# ------------------------------------------------------------------------------
# TAB 1: SYSTEM DASHBOARD
# ------------------------------------------------------------------------------
if nav == "📊 System Dashboard":
    st.title("System Health & Operational Overview")
    conn = get_db_connection()
    n_p = conn.execute("SELECT COUNT(*) FROM players WHERE calibration_tier != 'INACTIVE'").fetchone()[0]
    n_m = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    n_v = conn.execute("SELECT COUNT(*) FROM venues WHERE is_active = 1").fetchone()[0]
    n_c = conn.execute("SELECT COUNT(*) FROM locations WHERE location_type = 'CITY'").fetchone()[0]
    conn.close()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active Players", n_p)
    m2.metric("Matches Completed", n_m)
    m3.metric("Registered Venues", n_v)
    m4.metric("Active Municipalities", n_c)

    # 1-CLICK BACKUP & RESTORE TOOL
    with st.expander("💾 Database Backup & Restore (Zero Data Loss Safeguard)"):
        st.caption("Safeguard your test data against free cloud container reboots.")
        col_bk1, col_bk2 = st.columns(2)
        with col_bk1:
            st.markdown("#### 📥 Backup Data")
            st.write("Download your entire database file to your computer or phone after a match session.")
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

    st.subheader("Live Verification Ledger & Recent Audits")
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
        st.info("No match audits committed yet. Log a match under 'Matches Hub'.")

# ------------------------------------------------------------------------------
# TAB 2: MATCHES HUB (DYNAMIC SCORING, ALL MATCHES LEDGER, UNDO)
# ------------------------------------------------------------------------------
elif nav == "🎾 Matches Hub":
    st.title("Matches Management & Verification Hub")
    match_section = st.radio("Section View", ["🎮 Log & Simulate Match", "📜 All Matches Ledger"], horizontal=True)

    conn = get_db_connection()
    p_rows = conn.execute("SELECT * FROM players WHERE calibration_tier != 'INACTIVE' ORDER BY display_name ASC").fetchall()
    v_rows = conn.execute("SELECT venue_id, venue_name FROM venues WHERE is_active = 1").fetchall()
    f_rows = conn.execute("SELECT * FROM match_formats WHERE is_active = 1").fetchall()
    conn.close()

    p_map = {f"{p['display_name']} ({p['latent_mmr']:.2f} | RD:{p['rating_deviation']:.0f} | {p['calibration_tier']})": p['player_id'] for p in p_rows}
    v_map = {v["venue_name"]: v["venue_id"] for v in v_rows}
    f_dict = {f["format_name"]: dict(f) for f in f_rows}

    # SUB-TAB 1: LOG & SIMULATE
    if match_section == "🎮 Log & Simulate Match":
        st.subheader("Record / Simulate Match Transaction")

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
                    conn.close()

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
                            "Pre Rating": r["pre_r"],
                            "Rating Delta": f"{r['delta_r']:+0.4f}",
                            "Post Latent": r["post_r"],
                            "RD Contraction": f"{r['pre_rd']:.1f} -> {r['post_rd']:.1f}",
                            "Certainty (S_RD)": f"{r['accuracy_suite']['s_rd_pct']:.1f}%",
                            "Matches (S_N)": f"{r['accuracy_suite']['s_matches_pct']:.1f}%",
                            "Diversity (S_D)": f"{r['accuracy_suite']['s_diversity_pct']:.1f}%",
                            "Total Accuracy": f"{r['accuracy_suite']['composite_accuracy']:.1f}%",
                            "Calibration Tier": r["accuracy_suite"]["calibration_tier"],
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
                            INSERT INTO matches (match_id, venue_id, format_id, is_singles, team_a_p1_id, team_a_p2_id,
                                                team_b_p1_id, team_b_p2_id, score_team_a, score_team_b, set_scores_json,
                                                games_winner, games_loser, pre_rating_a, pre_rating_b, win_expectancy_a,
                                                applied_m_c, applied_s_margin, delta_r_p1, delta_r_p2, delta_r_p3, delta_r_p4,
                                                guardrails_summary, match_timestamp)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            m_id, v_map[ven_name], selected_fmt["format_id"], 0 if is_doubles else 1,
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
                                    verified_matches_count = verified_matches_count + 1,
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
                        st.balloons()
                        st.success("✅ Match successfully committed to all relational databases! Player cards updated.")

        # Undo Tool
        with st.expander("⚠️ Undo / Rollback Latest Match Entry"):
            conn = get_db_connection()
            last_m = conn.execute("SELECT match_id, match_timestamp FROM matches ORDER BY match_timestamp DESC LIMIT 1").fetchone()
            if last_m:
                st.write(f"Latest Recorded Match: **{last_m['match_id']}** (Recorded: {last_m['match_timestamp']})")
                if st.button("🚨 Revert This Match & Restore Prior Ratings", type="secondary"):
                    m_id = last_m["match_id"]
                    logs = conn.execute("SELECT player_id, pre_latent_mmr, pre_rd, pre_accuracy_pct FROM match_logs WHERE match_id = ?", (m_id,)).fetchall()
                    for l in logs:
                        conn.execute("""
                            UPDATE players SET 
                                latent_mmr = ?, display_rating = ?, rating_deviation = ?, 
                                rating_accuracy_pct = ?, verified_matches_count = max(0, verified_matches_count - 1)
                            WHERE player_id = ?
                        """, (l["pre_latent_mmr"], l["pre_latent_mmr"], l["pre_rd"], l["pre_accuracy_pct"], l["player_id"]))
                    conn.execute("DELETE FROM match_logs WHERE match_id = ?", (m_id,))
                    conn.execute("DELETE FROM matches WHERE match_id = ?", (m_id,))
                    conn.commit()
                    st.warning(f"Match {m_id} reverted successfully.")
                    st.rerun()
            else:
                st.info("No matches recorded yet.")
            conn.close()

    # SUB-TAB 2: ALL MATCHES LEDGER
    elif match_section == "📜 All Matches Ledger":
        st.subheader("All Matches Ledger & Deep Card Inspector")
        conn = get_db_connection()
        
        f_c1, f_c2 = st.columns(2)
        sort_order = f_c1.selectbox("Sort By Timestamp", ["Newest First", "Oldest First"])
        ven_filter = f_c2.selectbox("Filter by Venue", ["All Venues"] + list(v_map.keys()))
        
        query = '''
            SELECT m.*, v.venue_name, l.location_name as city, f.format_name,
                   p1.display_name as p1_name, p2.display_name as p2_name,
                   p3.display_name as p3_name, p4.display_name as p4_name
            FROM matches m
            JOIN venues v ON m.venue_id = v.venue_id
            JOIN locations l ON v.city_id = l.location_id
            JOIN match_formats f ON m.format_id = f.format_id
            JOIN players p1 ON m.team_a_p1_id = p1.player_id
            LEFT JOIN players p2 ON m.team_a_p2_id = p2.player_id
            JOIN players p3 ON m.team_b_p1_id = p3.player_id
            LEFT JOIN players p4 ON m.team_b_p2_id = p4.player_id
        '''
        params = []
        if ven_filter != "All Venues":
            query += " WHERE v.venue_name = ?"
            params.append(ven_filter)
            
        query += " ORDER BY m.match_timestamp " + ("DESC" if sort_order == "Newest First" else "ASC")
        matches_list = conn.execute(query, params).fetchall()

        if not matches_list:
            st.info("No matches found matching the filter criteria.")
        else:
            for m in matches_list:
                with st.expander(f"🎾 {m['match_id']} • {m['venue_name']} ({m['city']}) • Score: {m['score_team_a']}-{m['score_team_b']} ({m['format_name']})"):
                    t_col1, t_col2 = st.columns(2)
                    with t_col1:
                        if m['is_singles']:
                            st.write(f"**🔵 Player A:** {m['p1_name']} (ΔR: {m['delta_r_p1']:+0.4f})")
                        else:
                            st.write(f"**🔵 Team A:** {m['p1_name']} & {m['p2_name']}")
                            st.write(f"Points Delta: {m['p1_name']} ({m['delta_r_p1']:+0.4f}) | {m['p2_name']} ({m['delta_r_p2']:+0.4f})")
                        st.caption(f"Pre-Match Team Rating: **{m['pre_rating_a']:.4f}** • Win Odds: **{m['win_expectancy_a']*100:.1f}%**")

                    with t_col2:
                        if m['is_singles']:
                            st.write(f"**🔴 Player B:** {m['p3_name']} (ΔR: {m['delta_r_p3']:+0.4f})")
                        else:
                            st.write(f"**🔴 Team B:** {m['p3_name']} & {m['p4_name']}")
                            st.write(f"Points Delta: {m['p3_name']} ({m['delta_r_p3']:+0.4f}) | {m['p4_name']} ({m['delta_r_p4']:+0.4f})")
                        st.caption(f"Pre-Match Team Rating: **{m['pre_rating_b']:.4f}** • Win Odds: **{(1-m['win_expectancy_a'])*100:.1f}%**")

                    st.markdown("---")
                    st.write(f"**Scorelines:** Sets: `{m['set_scores_json']}` | MOV Multiplier: `{m['applied_s_margin']:.4f}` | Recorded: `{m['match_timestamp']}`")

                    p_logs = conn.execute("""
                        SELECT ml.*, p.display_name 
                        FROM match_logs ml 
                        JOIN players p ON ml.player_id = p.player_id 
                        WHERE ml.match_id = ?
                    """, (m["match_id"],)).fetchall()

                    st.markdown("##### Individual Player Audit Snapshots & Guardrails")
                    for pl in p_logs:
                        g_list = json.loads(pl["guardrails_triggered"]) if pl["guardrails_triggered"] else []
                        g_text = " • ".join(g_list) if g_list else "Standard competitive exchange; no guardrails tripped."
                        st.write(f"- **{pl['display_name']}**: Rating `{pl['pre_latent_mmr']:.4f} -> {pl['post_latent_mmr']:.4f}` | RD `{pl['pre_rd']:.1f} -> {pl['post_rd']:.1f}` | ΔR: `{pl['delta_r']:+0.4f}`")
                        st.caption(f"  *Guardrails:* {g_text}")
        conn.close()

# ------------------------------------------------------------------------------
# TAB 3: PLAYERS ROSTER
# ------------------------------------------------------------------------------
elif nav == "👥 Players Roster":
    st.title("Players Directory & Calibration Roster")
    conn = get_db_connection()
    players_df = pd.read_sql_query('''
        SELECT p.player_id, p.display_name, p.latent_mmr, p.rating_deviation, p.rating_accuracy_pct,
               p.accuracy_s_rd as certainty_pct, p.accuracy_s_matches as sample_pct, p.accuracy_s_diversity as diversity_pct,
               p.calibration_tier, p.verified_matches_count, p.unique_opponents_count, p.is_anchor, p.is_ceiling_anchor, l.location_name as city
        FROM players p JOIN locations l ON p.home_city_id = l.location_id
        ORDER BY p.latent_mmr DESC
    ''', conn)
    conn.close()

    if not players_df.empty:
        st.dataframe(players_df, use_container_width=True)
    else:
        st.info("No players onboarded yet. Register your first player below.")

    col_add, col_edit = st.columns(2)
    with col_add:
        with st.expander("➕ Register New Player"):
            with st.form("add_player_form"):
                st.markdown("#### Profile Onboarding")
                name = st.text_input("Full Name")
                init_r = st.number_input("Declared Latent MMR", 0.000, 6.999, 3.000, 0.050)
                
                conn = get_db_connection()
                cities = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'CITY'").fetchall()
                venues = conn.execute("SELECT venue_id, venue_name FROM venues WHERE is_active = 1").fetchall()
                conn.close()

                c_pick = st.selectbox("Home Municipality", [c["location_name"] for c in cities]) if cities else None
                v_pick = st.selectbox("Home Venue", ["None"] + [v["venue_name"] for v in venues]) if venues else "None"
                
                c1, c2 = st.columns(2)
                is_anc = c1.checkbox("System Anchor (is_anchor)")
                is_ceil = c2.checkbox("Ceiling Anchor (is_ceiling_anchor)")

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
                                                 rolling_365d_peak, rating_deviation, is_anchor, is_ceiling_anchor, created_at)
                            VALUES (?, ?, ?, ?, ?, 'IND', ?, ?, ?, ?, ?, 350.0, ?, ?, ?)
                        ''', (p_uuid, name, init_r, v_id, c_id, init_r, init_r, init_r, init_r, init_r, 1 if is_anc else 0, 1 if is_ceil else 0, datetime.now(timezone.utc).isoformat()))
                        
                        conn.execute('''
                            INSERT INTO player_changelog (player_id, change_type, old_val, new_val, changed_by, changed_at)
                            VALUES (?, 'PROFILE_CREATED', 'None', ?, ?, ?)
                        ''', (p_uuid, f"Initial MMR: {init_r:.4f}", active_operator, datetime.now(timezone.utc).isoformat()))
                        
                        conn.commit()
                        conn.close()
                        st.success(f"Registered {name}!")
                        st.rerun()

    with col_edit:
        with st.expander("✏️ Profile Inspector & Accuracy Breakdown"):
            conn = get_db_connection()
            all_p = conn.execute("SELECT * FROM players ORDER BY display_name ASC").fetchall()
            conn.close()
            
            if all_p:
                p_sel_id = st.selectbox("Choose Player", [p["player_id"] for p in all_p], format_func=lambda x: [p["display_name"] for p in all_p if p["player_id"] == x][0])
                p_cur = [p for p in all_p if p["player_id"] == p_sel_id][0]

                st.markdown(f"#### Calibration Health: **{p_cur['display_name']}**")
                ak1, ak2, ak3, ak4 = st.columns(4)
                ak1.metric("Rating Accuracy", f"{p_cur['rating_accuracy_pct']:.1f}%")
                ak2.metric("Certainty (Pillar 1)", f"{p_cur['accuracy_s_rd']:.1f}%")
                ak3.metric("Sample Depth (Pillar 2)", f"{p_cur['accuracy_s_matches']:.1f}%")
                ak4.metric("Diversity (Pillar 3)", f"{p_cur['accuracy_s_diversity']:.1f}%")

                with st.form("edit_player_form"):
                    e_name = st.text_input("Name", value=p_cur["display_name"])
                    e_mmr = st.number_input("Latent MMR Override", value=float(p_cur["latent_mmr"]), step=0.01)
                    e_rd = st.number_input("Rating Deviation (RD)", value=float(p_cur["rating_deviation"]), step=1.0)
                    
                    ec1, ec2, ec3 = st.columns(3)
                    e_act = ec1.checkbox("Active on Roster", value=(p_cur["calibration_tier"] != "INACTIVE"))
                    e_anc = ec2.checkbox("System Anchor", value=bool(p_cur["is_anchor"]))
                    e_ceil = ec3.checkbox("Ceiling Anchor", value=bool(p_cur["is_ceiling_anchor"]))
                    
                    if st.form_submit_button("Save Parameter Overrides"):
                        new_tier = p_cur["calibration_tier"] if e_act else "INACTIVE"
                        conn = get_db_connection()
                        conn.execute('''
                            UPDATE players SET display_name = ?, latent_mmr = ?, display_rating = ?,
                                               rating_deviation = ?, calibration_tier = ?, is_anchor = ?, is_ceiling_anchor = ?
                            WHERE player_id = ?
                        ''', (e_name, e_mmr, e_mmr, e_rd, new_tier, 1 if e_anc else 0, 1 if e_ceil else 0, p_sel_id))
                        
                        conn.execute('''
                            INSERT INTO player_changelog (player_id, change_type, old_val, new_val, changed_by, changed_at)
                            VALUES (?, 'MANUAL_OVERRIDE', ?, ?, ?, ?)
                        ''', (p_sel_id, f"MMR: {p_cur['latent_mmr']:.2f}, RD: {p_cur['rating_deviation']:.0f}",
                              f"MMR: {e_mmr:.2f}, RD: {e_rd:.0f}, Tier: {new_tier}", active_operator, datetime.now(timezone.utc).isoformat()))
                        
                        conn.commit()
                        conn.close()
                        st.success("Player overrides committed!")
                        st.rerun()

                st.markdown("##### Historical Progression Changelog")
                conn = get_db_connection()
                pcl_df = pd.read_sql_query("SELECT change_type, old_val, new_val, changed_by, changed_at FROM player_changelog WHERE player_id = ? ORDER BY changed_at DESC", conn, params=[p_sel_id])
                conn.close()
                st.dataframe(pcl_df, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 4: VENUES & LOCATIONS (CRUD)
# ------------------------------------------------------------------------------
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
            st.info("No venues created yet. Use the registration form below.")

        with st.expander("🔗 Venue Alias Merge Tool"):
            st.caption("Merge user typos into one master verified venue.")
            v_all = conn.execute("SELECT venue_id, venue_name FROM venues").fetchall()
            v_dict = {v["venue_name"]: v["venue_id"] for v in v_all}
            
            cm1, cm2 = st.columns(2)
            source_v = cm1.multiselect("Select Typo / Duplicate Venues", list(v_dict.keys()))
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
                    st.success(f"Merged {len(source_v)} venues into {target_v}!")
                    st.rerun()

        cv1, cv2 = st.columns(2)
        with cv1:
            with st.form("add_v_form"):
                st.markdown("#### ➕ Add Venue")
                vn = st.text_input("Venue Name")
                cities = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'CITY'").fetchall()
                vc = st.selectbox("City", [c["location_name"] for c in cities]) if cities else None
                v_crts = st.number_input("Courts", 1, 30, 2)
                v_ver = st.checkbox("Verified Club Desk Override", value=True)
                if st.form_submit_button("Register Venue"):
                    if not cities:
                        st.error("Please add a City under 'Cities' first.")
                    elif not vn:
                        st.error("Venue name cannot be blank.")
                    else:
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
                    if b1.form_submit_button("Save Changes"):
                        conn.execute("UPDATE venues SET venue_name = ?, court_count = ?, is_verified = ?, is_active = ? WHERE venue_id = ?",
                                     (up_vn, up_crt, 1 if up_ver else 0, 1 if up_act else 0, sv_id))
                        conn.commit()
                        st.success("Venue updated.")
                        st.rerun()
                    if b2.form_submit_button("🗑️ Delete"):
                        mcnt = conn.execute("SELECT COUNT(*) FROM matches WHERE venue_id = ?", (sv_id,)).fetchone()[0]
                        if mcnt > 0:
                            st.error(f"Cannot delete: {mcnt} matches are linked. Uncheck Active instead.")
                        else:
                            conn.execute("DELETE FROM venues WHERE venue_id = ?", (sv_id,))
                            conn.commit()
                            st.warning(f"Deleted {v_row['venue_name']}.")
                            st.rerun()

    elif sec == "🏙️ Cities":
        st.subheader("Active Municipalities")
        c_df = pd.read_sql_query('''
            SELECT l.location_id, l.location_name as city, p.location_name as country, 
                   l.active_bridge_count, l.hawking_offset, l.suggested_offset, l.readiness_score
            FROM locations l LEFT JOIN locations p ON l.parent_id = p.location_id
            WHERE l.location_type = 'CITY'
        ''', conn)
        if not c_df.empty:
            st.dataframe(c_df, use_container_width=True)
        else:
            st.info("No cities created yet.")

        cc1, cc2 = st.columns(2)
        with cc1:
            with st.form("add_c_form"):
                st.markdown("#### ➕ Add City")
                cn = st.text_input("City Name")
                countries = conn.execute("SELECT location_id, location_name FROM locations WHERE location_type = 'COUNTRY'").fetchall()
                c_parent = st.selectbox("Country", [ct["location_name"] for ct in countries]) if countries else None
                if st.form_submit_button("Create City"):
                    if not countries:
                        st.error("Please add a Country under 'Countries' first.")
                    elif not cn:
                        st.error("City name cannot be blank.")
                    else:
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
                        vl = conn.execute("SELECT COUNT(*) FROM venues WHERE city_id = ?", (sc_id,)).fetchone()[0]
                        if pl > 0 or vl > 0:
                            st.error(f"Cannot delete: Linked to {pl} players and {vl} venues.")
                        else:
                            conn.execute("DELETE FROM locations WHERE location_id = ?", (sc_id,))
                            conn.commit()
                            st.warning(f"Deleted {c_row['location_name']}.")
                            st.rerun()

    elif sec == "🌍 Countries":
        st.subheader("Active Countries")
        co_df = pd.read_sql_query("SELECT location_id, location_name, country_code FROM locations WHERE location_type = 'COUNTRY'", conn)
        if not co_df.empty:
            st.dataframe(co_df, use_container_width=True)
        else:
            st.info("No countries created yet. Add one below.")

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
                sco_id = st.selectbox("Select Country to Delete", [c["location_id"] for c in co_all], format_func=lambda x: [c["location_name"] for c in co_all if c["location_id"] == x][0])
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

# ------------------------------------------------------------------------------
# TAB 5: HAWKING REGIONAL CONTROL
# ------------------------------------------------------------------------------
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

# ------------------------------------------------------------------------------
# TAB 6: GLOBAL CONFIG SWITCHES
# ------------------------------------------------------------------------------
elif nav == "⚙️ Global Config Switches":
    st.title("Algorithmic Bit Governance & Parameter Switches")
    st.caption("Tune operational parameters with real-time operational explainers and system changelogs.")

    conn = get_db_connection()
    configs = conn.execute("SELECT * FROM global_config ORDER BY param_key ASC").fetchall()
    conn.close()

    for cfg in configs:
        with st.expander(f"⚙️ {cfg['param_key']} — {cfg['title']}"):
            st.write(f"**Description:** {cfg['description']}")
            st.info(f"💡 **Tuning Explainer:** {cfg['tuning_guide']}")
            
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

    # NUCLEAR RESET TOOL
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
            conn.execute("DELETE FROM config_changelog;")
            conn.execute("DELETE FROM player_changelog;")
            conn.commit()
            conn.close()
            st.success("All data erased. System reset to a clean slate.")
            st.rerun()
