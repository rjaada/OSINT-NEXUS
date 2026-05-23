"""
db_postgres.py — PostgreSQL schema initialisation and connection helper.

Uses psycopg (v3) which is already in requirements.txt as psycopg[binary].
Provides:
  - init_pg_schema(conn)  — CREATE TABLE IF NOT EXISTS for all 14 tables
  - get_pg_conn()         — returns a psycopg connection with row_factory=dict_row
                            so rows behave like dicts (compatible with former
                            sqlite3.Row dict-style access).
"""

from __future__ import annotations

try:
    from .config import DATABASE_URL  # type: ignore
except ImportError:
    from config import DATABASE_URL

import psycopg
from psycopg.rows import dict_row


def get_pg_conn() -> psycopg.Connection:
    """Return an open psycopg3 connection using DATABASE_URL from config.

    The connection uses dict_row so every fetchone()/fetchall() result is a
    plain dict — identical access pattern to sqlite3.Row with row_factory.
    """
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return conn


def init_pg_schema(conn: psycopg.Connection) -> None:
    """Create all application tables in PostgreSQL if they do not already exist.

    Safe to call on every startup (all statements use IF NOT EXISTS).
    """
    with conn.cursor() as cur:
        # ── events ────────────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                incident_id TEXT,
                type TEXT,
                "desc" TEXT,
                lat DOUBLE PRECISION,
                lng DOUBLE PRECISION,
                source TEXT,
                timestamp TEXT,
                url TEXT,
                video_url TEXT,
                lang TEXT,
                confidence_score INTEGER,
                confidence_reason TEXT,
                observed_facts TEXT,
                model_inference TEXT,
                video_assessment TEXT,
                video_confidence TEXT,
                video_clues TEXT,
                created_at TEXT
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_incident ON events(incident_id)"
        )

        # ── reviews ───────────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                event_id TEXT NOT NULL,
                incident_id TEXT,
                status TEXT NOT NULL,
                analyst TEXT,
                note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_reviews_event ON reviews(event_id)"
        )

        # ── saved_views ───────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_views (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                filters_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # ── watchlists ────────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlists (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                owner TEXT NOT NULL,
                query TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # ── pinned_incidents ──────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pinned_incidents (
                incident_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        # ── handoff_notes ─────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS handoff_notes (
                id SERIAL PRIMARY KEY,
                incident_id TEXT NOT NULL,
                owner TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # ── notification_rules ────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_rules (
                id SERIAL PRIMARY KEY,
                owner TEXT NOT NULL,
                min_confidence INTEGER NOT NULL,
                event_types_json TEXT NOT NULL,
                channels_json TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )

        # ── media_analysis ────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS media_analysis (
                event_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                keyframes_json TEXT NOT NULL,
                ocr_snippets_json TEXT NOT NULL,
                stt_snippets_json TEXT NOT NULL,
                claim_alignment TEXT NOT NULL,
                credibility_note TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                transcript_text TEXT DEFAULT '',
                transcript_language TEXT DEFAULT '',
                transcript_error TEXT DEFAULT '',
                deepfake_score TEXT DEFAULT '',
                deepfake_label TEXT DEFAULT '',
                deepfake_error TEXT DEFAULT ''
            )
            """
        )

        # ── eval_samples ──────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS eval_samples (
                id SERIAL PRIMARY KEY,
                event_id TEXT NOT NULL,
                truth_type TEXT,
                truth_lat DOUBLE PRECISION,
                truth_lng DOUBLE PRECISION,
                outcome TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # ── audit_logs ────────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                actor TEXT NOT NULL,
                role TEXT NOT NULL,
                action TEXT NOT NULL,
                target_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # ── users ─────────────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"
        )

        # ── revoked_tokens ────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                sig TEXT PRIMARY KEY,
                expires_epoch INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires ON revoked_tokens(expires_epoch)"
        )

        # ── user_mfa_totp ─────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_mfa_totp (
                username TEXT PRIMARY KEY,
                secret TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # ── totp_used_codes ───────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS totp_used_codes (
                username TEXT NOT NULL,
                code TEXT NOT NULL,
                used_at INTEGER NOT NULL,
                PRIMARY KEY (username, code)
            )
            """
        )

        # ── user_passkeys ─────────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_passkeys (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                credential_id TEXT NOT NULL UNIQUE,
                public_key_b64 TEXT NOT NULL,
                sign_count INTEGER NOT NULL DEFAULT 0,
                label TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_passkeys_username ON user_passkeys(username)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hypotheses (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                statement TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                confidence INTEGER NOT NULL DEFAULT 50,
                evidence_ids TEXT[] DEFAULT '{}',
                analyst_notes TEXT DEFAULT '',
                analyst TEXT DEFAULT 'AI-NEXUS-01',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                tags TEXT[] DEFAULT '{}'
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_hypotheses_status ON hypotheses(status)"
        )

        # ── doctrine_profiles ─────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS doctrine_profiles (
                actor TEXT NOT NULL,
                theater TEXT NOT NULL DEFAULT 'global',
                feature_name TEXT NOT NULL,
                bucket_start TIMESTAMPTZ NOT NULL,
                observation_value DOUBLE PRECISION NOT NULL,
                ewma_mean DOUBLE PRECISION NOT NULL,
                ewma_var DOUBLE PRECISION NOT NULL,
                z_score DOUBLE PRECISION,
                deviation_level TEXT NOT NULL DEFAULT 'NORMAL',
                event_count INTEGER NOT NULL DEFAULT 1,
                sample_n INTEGER NOT NULL DEFAULT 1,
                excluded_spike BOOLEAN NOT NULL DEFAULT FALSE,
                source_event_ids TEXT[] NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (actor, theater, feature_name, bucket_start)
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_doctrine_profiles_actor_feature_time
                ON doctrine_profiles(actor, feature_name, bucket_start DESC)
            """
        )

        # ── doctrine_alerts ───────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS doctrine_alerts (
                id BIGSERIAL PRIMARY KEY,
                actor TEXT NOT NULL,
                theater TEXT NOT NULL DEFAULT 'global',
                event_id TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                observed_value DOUBLE PRECISION NOT NULL,
                expected_mean DOUBLE PRECISION NOT NULL,
                expected_sd DOUBLE PRECISION NOT NULL,
                z_score DOUBLE PRECISION NOT NULL,
                deviation_level TEXT NOT NULL,
                supporting_event_ids TEXT[] NOT NULL DEFAULT '{}',
                payload_json JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_doctrine_alerts_actor_time
                ON doctrine_alerts(actor, created_at DESC)
            """
        )

        # ── analyst_judgments ─────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS analyst_judgments (
                id              SERIAL PRIMARY KEY,
                analyst_id      TEXT NOT NULL,
                judgment_type   TEXT NOT NULL,
                event_id        TEXT,
                hypothesis_id   TEXT,
                stated_prob     DOUBLE PRECISION NOT NULL,
                judgment_text   TEXT,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolve_at_24h  TIMESTAMPTZ NOT NULL,
                resolve_at_7d   TIMESTAMPTZ NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_aj_analyst ON analyst_judgments(analyst_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_aj_resolve ON analyst_judgments(resolve_at_24h, resolve_at_7d)"
        )

        # ── judgment_outcomes ─────────────────────────────────────────────────
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS judgment_outcomes (
                id                   SERIAL PRIMARY KEY,
                judgment_id          INTEGER NOT NULL REFERENCES analyst_judgments(id),
                resolution_window    TEXT NOT NULL,
                outcome_prob         DOUBLE PRECISION NOT NULL,
                brier_score          DOUBLE PRECISION NOT NULL,
                resolved_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ground_truth_source  TEXT NOT NULL,
                UNIQUE (judgment_id, resolution_window)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_jo_judgment ON judgment_outcomes(judgment_id)"
        )

    conn.commit()
