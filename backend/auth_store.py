"""
auth_store.py — User CRUD and token revocation via PostgreSQL (psycopg3).

All functions accept `db` as first argument (a psycopg connection) so call
sites in main.py / routes_auth.py do not need to change.
Rows returned by psycopg3 with dict_row are plain dicts — dict-style access
(row["field"]) works identically to the former sqlite3.Row behaviour.
SQL placeholders use %s (psycopg3 style, not ? which is sqlite3 style).
"""

from typing import Any, Callable, Dict, List, Optional


def ensure_default_admin(
    db: Optional[Any],
    default_admin_user: str,
    default_admin_password: str,
    hash_password: Callable[[str], str],
    now_iso: Callable[[], str],
) -> None:
    if db is None:
        return
    with db.cursor() as cur:
        cur.execute(
            "SELECT id FROM users WHERE username = %s",
            (default_admin_user.lower(),),
        )
        row = cur.fetchone()
    if row:
        return
    now = now_iso()
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at, updated_at)
            VALUES (%s, %s, 'admin', %s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            (
                default_admin_user.lower(),
                hash_password(default_admin_password),
                now,
                now,
            ),
        )
    db.commit()


def get_user(db: Optional[Any], username: str) -> Optional[Dict[str, Any]]:
    if db is None:
        return None
    with db.cursor() as cur:
        cur.execute(
            "SELECT * FROM users WHERE username = %s",
            (username.lower(),),
        )
        return cur.fetchone()


def create_user(
    db: Optional[Any],
    username: str,
    password_hash: str,
    role: str,
    now_iso: Callable[[], str],
) -> None:
    if db is None:
        raise RuntimeError("Database unavailable")
    now = now_iso()
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (username.lower(), password_hash, role, now, now),
        )
    db.commit()


def revoke_token(
    db: Optional[Any],
    sig: str,
    expires_epoch: int,
    now_iso: Callable[[], str],
) -> None:
    if db is None:
        return
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO revoked_tokens (sig, expires_epoch, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (sig) DO NOTHING
            """,
            (sig, expires_epoch, now_iso()),
        )
    db.commit()


def list_users(db: Optional[Any]) -> List[Dict[str, str]]:
    if db is None:
        raise RuntimeError("Database unavailable")
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT username, role, created_at, updated_at
            FROM users
            ORDER BY username ASC
            """
        )
        rows = cur.fetchall()
    return [
        {
            "username": str(r["username"]),
            "role": str(r["role"]),
            "created_at": str(r["created_at"]),
            "updated_at": str(r["updated_at"]),
        }
        for r in rows
    ]


def set_user_role(
    db: Optional[Any],
    username: str,
    next_role: str,
    now_iso: Callable[[], str],
) -> Dict[str, str]:
    if db is None:
        raise RuntimeError("Database unavailable")
    target = username.strip().lower()
    row = get_user(db, target)
    if not row:
        raise LookupError("User not found")

    current_role = str(row["role"]).lower()
    if current_role == next_role:
        return {
            "username": target,
            "from": current_role,
            "to": current_role,
            "updated_at": str(row["updated_at"]),
        }

    if current_role == "admin" and next_role != "admin":
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")
            admin_count = int(cur.fetchone()["c"])
        if admin_count <= 1:
            raise ValueError("Cannot demote the last admin account")

    now = now_iso()
    with db.cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET role = %s, updated_at = %s
            WHERE username = %s
            """,
            (next_role, now, target),
        )
    db.commit()
    return {
        "username": target,
        "from": current_role,
        "to": next_role,
        "updated_at": now,
    }


def delete_user(
    db: Optional[Any],
    username: str,
    actor_username: str,
    now_iso: Callable[[], str],
) -> Dict[str, str]:
    if db is None:
        raise RuntimeError("Database unavailable")
    target = username.strip().lower()
    actor = actor_username.strip().lower()
    row = get_user(db, target)
    if not row:
        raise LookupError("User not found")
    if target == actor:
        raise ValueError("You cannot delete your own account")

    current_role = str(row["role"]).lower()
    if current_role == "admin":
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")
            admin_count = int(cur.fetchone()["c"])
        if admin_count <= 1:
            raise ValueError("Cannot delete the last admin account")

    with db.cursor() as cur:
        cur.execute("DELETE FROM users WHERE username = %s", (target,))
    db.commit()
    return {
        "username": target,
        "role": current_role,
        "deleted_at": now_iso(),
    }
