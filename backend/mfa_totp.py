import time
from typing import Optional

import pyotp

# TOTP step is 30s; valid_window=1 means ±1 step → max valid age is 90s.
_TOTP_STEP = 30
_REPLAY_TTL = 90


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
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS totp_used_codes (
            username TEXT NOT NULL,
            code TEXT NOT NULL,
            used_at INTEGER NOT NULL,
            PRIMARY KEY (username, code)
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


def verify_and_consume(db, username: str, secret: str, code: str, valid_window: int = 1) -> bool:
    """Verify a TOTP code and mark it as used to prevent replay attacks.

    Returns False if the code is invalid OR has already been used within the
    replay window, even if pyotp would otherwise accept it.
    """
    code = str(code).strip()
    try:
        t = pyotp.TOTP(secret)
        if not t.verify(code, valid_window=valid_window):
            return False
    except Exception:
        return False

    if db is None:
        return True  # no DB — degrade gracefully, still better than nothing

    now = int(time.time())

    # Prune expired entries first (keep table small).
    try:
        db.execute(
            "DELETE FROM totp_used_codes WHERE used_at < ?",
            (now - _REPLAY_TTL,),
        )
    except Exception:
        pass

    # Reject if this (username, code) pair was already consumed.
    try:
        row = db.execute(
            "SELECT 1 FROM totp_used_codes WHERE username = ? AND code = ?",
            (username.lower(), code),
        ).fetchone()
        if row:
            return False
    except Exception:
        pass

    # Mark consumed.
    try:
        db.execute(
            "INSERT OR IGNORE INTO totp_used_codes (username, code, used_at) VALUES (?, ?, ?)",
            (username.lower(), code, now),
        )
        db.commit()
    except Exception:
        pass

    return True


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
