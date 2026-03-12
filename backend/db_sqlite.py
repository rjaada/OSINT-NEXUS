"""
SQLite schema initialisation.

Call ``init_db()`` once at startup; it returns the open connection.
All schema migrations are additive (ALTER TABLE ... ADD COLUMN guarded by
try/except OperationalError) so an existing database is safe to re-open.
"""

import sqlite3

try:
    from .config import DB_PATH  # type: ignore
    from . import mfa_totp  # type: ignore
    from . import auth_passkey as authpasskey  # type: ignore
except ImportError:
    from config import DB_PATH
    import mfa_totp
    import auth_passkey as authpasskey


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            incident_id TEXT,
            type TEXT,
            desc TEXT,
            lat REAL,
            lng REAL,
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_incident ON events(incident_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            incident_id TEXT,
            status TEXT NOT NULL,
            analyst TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_event ON reviews(event_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner TEXT NOT NULL,
            filters_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner TEXT NOT NULL,
            query TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pinned_incidents (
            incident_id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS handoff_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL,
            min_confidence INTEGER NOT NULL,
            event_types_json TEXT NOT NULL,
            channels_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_analysis (
            event_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            keyframes_json TEXT NOT NULL,
            ocr_snippets_json TEXT NOT NULL,
            stt_snippets_json TEXT NOT NULL,
            claim_alignment TEXT NOT NULL,
            credibility_note TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            truth_type TEXT,
            truth_lat REAL,
            truth_lng REAL,
            outcome TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            target_id TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            sig TEXT PRIMARY KEY,
            expires_epoch INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires ON revoked_tokens(expires_epoch)")
    # Backward-compatible schema expansion for optional media hook outputs.
    for stmt in [
        "ALTER TABLE media_analysis ADD COLUMN transcript_text TEXT DEFAULT ''",
        "ALTER TABLE media_analysis ADD COLUMN transcript_language TEXT DEFAULT ''",
        "ALTER TABLE media_analysis ADD COLUMN transcript_error TEXT DEFAULT ''",
        "ALTER TABLE media_analysis ADD COLUMN deepfake_score TEXT DEFAULT ''",
        "ALTER TABLE media_analysis ADD COLUMN deepfake_label TEXT DEFAULT ''",
        "ALTER TABLE media_analysis ADD COLUMN deepfake_error TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    mfa_totp.ensure_table(conn)
    authpasskey.ensure_table(conn)
    return conn
