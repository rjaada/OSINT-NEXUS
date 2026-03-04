from typing import Any, Dict, List, Optional


def ensure_table(db) -> None:
    if db is None:
        return
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_passkeys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    db.execute("CREATE INDEX IF NOT EXISTS idx_user_passkeys_username ON user_passkeys(username)")
    db.commit()


def list_for_user(db, username: str) -> List[Dict[str, Any]]:
    if db is None:
        return []
    rows = db.execute(
        """
        SELECT username, credential_id, public_key_b64, sign_count, label, created_at, updated_at
        FROM user_passkeys
        WHERE username = ?
        ORDER BY id ASC
        """,
        (username.lower(),),
    ).fetchall()
    return [dict(r) for r in rows]


def get_by_credential_id(db, credential_id: str) -> Optional[Dict[str, Any]]:
    if db is None:
        return None
    row = db.execute(
        """
        SELECT username, credential_id, public_key_b64, sign_count, label, created_at, updated_at
        FROM user_passkeys
        WHERE credential_id = ?
        LIMIT 1
        """,
        (credential_id,),
    ).fetchone()
    return dict(row) if row else None


def upsert_passkey(
    db,
    *,
    username: str,
    credential_id: str,
    public_key_b64: str,
    sign_count: int,
    label: str,
    now_iso: str,
) -> None:
    if db is None:
        return
    db.execute(
        """
        INSERT INTO user_passkeys (
            username, credential_id, public_key_b64, sign_count, label, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(credential_id) DO UPDATE SET
            username = excluded.username,
            public_key_b64 = excluded.public_key_b64,
            sign_count = excluded.sign_count,
            label = excluded.label,
            updated_at = excluded.updated_at
        """,
        (username.lower(), credential_id, public_key_b64, int(sign_count), label[:64], now_iso, now_iso),
    )
    db.commit()


def update_sign_count(db, *, credential_id: str, sign_count: int, now_iso: str) -> None:
    if db is None:
        return
    db.execute(
        "UPDATE user_passkeys SET sign_count = ?, updated_at = ? WHERE credential_id = ?",
        (int(sign_count), now_iso, credential_id),
    )
    db.commit()


def count_for_user(db, username: str) -> int:
    if db is None:
        return 0
    row = db.execute(
        "SELECT COUNT(*) AS c FROM user_passkeys WHERE username = ?",
        (username.lower(),),
    ).fetchone()
    return int(row["c"]) if row else 0
