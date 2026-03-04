import sqlite3
from typing import Callable, Dict, List, Optional


def ensure_default_admin(
    db: Optional[sqlite3.Connection],
    default_admin_user: str,
    default_admin_password: str,
    hash_password: Callable[[str], str],
    now_iso: Callable[[], str],
) -> None:
    if db is None:
        return
    row = db.execute("SELECT id FROM users WHERE username = ?", (default_admin_user.lower(),)).fetchone()
    if row:
        return
    now = now_iso()
    db.execute(
        """
        INSERT INTO users (username, password_hash, role, created_at, updated_at)
        VALUES (?, ?, 'admin', ?, ?)
        """,
        (
            default_admin_user.lower(),
            hash_password(default_admin_password),
            now,
            now,
        ),
    )
    db.commit()


def get_user(db: Optional[sqlite3.Connection], username: str) -> Optional[sqlite3.Row]:
    if db is None:
        return None
    return db.execute("SELECT * FROM users WHERE username = ?", (username.lower(),)).fetchone()


def create_user(
    db: Optional[sqlite3.Connection],
    username: str,
    password_hash: str,
    role: str,
    now_iso: Callable[[], str],
) -> None:
    if db is None:
        raise RuntimeError("Database unavailable")
    now = now_iso()
    db.execute(
        """
        INSERT INTO users (username, password_hash, role, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (username.lower(), password_hash, role, now, now),
    )
    db.commit()


def revoke_token(
    db: Optional[sqlite3.Connection],
    sig: str,
    expires_epoch: int,
    now_iso: Callable[[], str],
) -> None:
    if db is None:
        return
    db.execute(
        "INSERT OR IGNORE INTO revoked_tokens (sig, expires_epoch, created_at) VALUES (?, ?, ?)",
        (sig, expires_epoch, now_iso()),
    )
    db.commit()


def list_users(db: Optional[sqlite3.Connection]) -> List[Dict[str, str]]:
    if db is None:
        raise RuntimeError("Database unavailable")
    rows = db.execute(
        """
        SELECT username, role, created_at, updated_at
        FROM users
        ORDER BY username ASC
        """
    ).fetchall()
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
    db: Optional[sqlite3.Connection],
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
        admin_count = int(db.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'").fetchone()["c"])
        if admin_count <= 1:
            raise ValueError("Cannot demote the last admin account")

    now = now_iso()
    db.execute(
        """
        UPDATE users
        SET role = ?, updated_at = ?
        WHERE username = ?
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
    db: Optional[sqlite3.Connection],
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
        admin_count = int(db.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'").fetchone()["c"])
        if admin_count <= 1:
            raise ValueError("Cannot delete the last admin account")

    db.execute("DELETE FROM users WHERE username = ?", (target,))
    db.commit()
    return {
        "username": target,
        "role": current_role,
        "deleted_at": now_iso(),
    }
