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

    conn.commit()
