from typing import Any, Dict, List, Optional


def ensure_table(db) -> None:
    """No-op: schema is managed by db_postgres.init_pg_schema."""
    return


def list_for_user(db, username: str) -> List[Dict[str, Any]]:
    if db is None:
        return []
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT username, credential_id, public_key_b64, sign_count, label, created_at, updated_at
            FROM user_passkeys
            WHERE username = %s
            ORDER BY id ASC
            """,
            (username.lower(),),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_by_credential_id(db, credential_id: str) -> Optional[Dict[str, Any]]:
    if db is None:
        return None
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT username, credential_id, public_key_b64, sign_count, label, created_at, updated_at
            FROM user_passkeys
            WHERE credential_id = %s
            LIMIT 1
            """,
            (credential_id,),
        )
        row = cur.fetchone()
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
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_passkeys (
                username, credential_id, public_key_b64, sign_count, label, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (credential_id) DO UPDATE SET
                username = EXCLUDED.username,
                public_key_b64 = EXCLUDED.public_key_b64,
                sign_count = EXCLUDED.sign_count,
                label = EXCLUDED.label,
                updated_at = EXCLUDED.updated_at
            """,
            (username.lower(), credential_id, public_key_b64, int(sign_count), label[:64], now_iso, now_iso),
        )
    db.commit()


def update_sign_count(db, *, credential_id: str, sign_count: int, now_iso: str) -> None:
    if db is None:
        return
    with db.cursor() as cur:
        cur.execute(
            "UPDATE user_passkeys SET sign_count = %s, updated_at = %s WHERE credential_id = %s",
            (int(sign_count), now_iso, credential_id),
        )
    db.commit()


def count_for_user(db, username: str) -> int:
    if db is None:
        return 0
    with db.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS c FROM user_passkeys WHERE username = %s",
            (username.lower(),),
        )
        row = cur.fetchone()
    return int(row["c"]) if row else 0
