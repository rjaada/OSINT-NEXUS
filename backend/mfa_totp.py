from typing import Optional

import pyotp


def ensure_table(db) -> None:
    if db is None:
        return
    db.execute(
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
    db.commit()


def get_record(db, username: str):
    if db is None:
        return None
    return db.execute(
        "SELECT username, secret, enabled, created_at, updated_at FROM user_mfa_totp WHERE username = ?",
        (username.lower(),),
    ).fetchone()


def create_or_rotate_secret(db, username: str, now_iso: str) -> str:
    secret = pyotp.random_base32()
    if db is None:
        return secret
    db.execute(
        """
        INSERT INTO user_mfa_totp (username, secret, enabled, created_at, updated_at)
        VALUES (?, ?, 0, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            secret = excluded.secret,
            enabled = 0,
            updated_at = excluded.updated_at
        """,
        (username.lower(), secret, now_iso, now_iso),
    )
    db.commit()
    return secret


def enable_totp(db, username: str, now_iso: str) -> None:
    if db is None:
        return
    db.execute(
        "UPDATE user_mfa_totp SET enabled = 1, updated_at = ? WHERE username = ?",
        (now_iso, username.lower()),
    )
    db.commit()


def disable_totp(db, username: str, now_iso: str) -> None:
    if db is None:
        return
    db.execute(
        "UPDATE user_mfa_totp SET enabled = 0, updated_at = ? WHERE username = ?",
        (now_iso, username.lower()),
    )
    db.commit()


def verify_code(secret: str, code: str, valid_window: int = 1) -> bool:
    try:
        t = pyotp.TOTP(secret)
        return bool(t.verify(str(code).strip(), valid_window=valid_window))
    except Exception:
        return False


def is_enabled(db, username: str) -> bool:
    row = get_record(db, username)
    if not row:
        return False
    return bool(int(row["enabled"] or 0))


def get_secret(db, username: str) -> Optional[str]:
    row = get_record(db, username)
    if not row:
        return None
    return str(row["secret"])
