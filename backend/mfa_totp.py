import time
from typing import Optional

import pyotp

# TOTP step is 30s; valid_window=1 means ±1 step → max valid age is 90s.
_TOTP_STEP = 30
_REPLAY_TTL = 90


def ensure_table(db) -> None:
    """Ensure replay storage exists for tests and non-Postgres deployments."""
    if db is None:
        return
    cur = db.cursor()
    try:
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
        db.commit()
    finally:
        cur.close()


def get_record(db, username: str):
    if db is None:
        return None
    with db.cursor() as cur:
        cur.execute(
            "SELECT username, secret, enabled, created_at, updated_at FROM user_mfa_totp WHERE username = %s",
            (username.lower(),),
        )
        return cur.fetchone()


def create_or_rotate_secret(db, username: str, now_iso: str) -> str:
    secret = pyotp.random_base32()
    if db is None:
        return secret
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_mfa_totp (username, secret, enabled, created_at, updated_at)
            VALUES (%s, %s, 0, %s, %s)
            ON CONFLICT (username) DO UPDATE SET
                secret = EXCLUDED.secret,
                enabled = 0,
                updated_at = EXCLUDED.updated_at
            """,
            (username.lower(), secret, now_iso, now_iso),
        )
    db.commit()
    return secret


def enable_totp(db, username: str, now_iso: str) -> None:
    if db is None:
        return
    with db.cursor() as cur:
        cur.execute(
            "UPDATE user_mfa_totp SET enabled = 1, updated_at = %s WHERE username = %s",
            (now_iso, username.lower()),
        )
    db.commit()


def disable_totp(db, username: str, now_iso: str) -> None:
    if db is None:
        return
    with db.cursor() as cur:
        cur.execute(
            "UPDATE user_mfa_totp SET enabled = 0, updated_at = %s WHERE username = %s",
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
    """Atomically verify and consume a TOTP code.

    When replay storage is supplied, database errors fail closed: accepting a
    valid code without recording its use would make replay protection illusory.
    """
    code = str(code).strip()
    try:
        if not pyotp.TOTP(secret).verify(code, valid_window=valid_window):
            return False
    except Exception:
        return False

    if db is None:
        return True

    now = int(time.time())
    placeholder = "?" if db.__class__.__module__.startswith("sqlite3") else "%s"
    cur = db.cursor()
    try:
        # Pruning is housekeeping only; failure must not block the atomic insert.
        try:
            cur.execute(
                f"DELETE FROM totp_used_codes WHERE used_at < {placeholder}",
                (now - _REPLAY_TTL,),
            )
        except Exception:
            db.rollback()
            cur.close()
            cur = db.cursor()

        cur.execute(
            f"""
            INSERT INTO totp_used_codes (username, code, used_at)
            VALUES ({placeholder}, {placeholder}, {placeholder})
            ON CONFLICT (username, code) DO NOTHING
            RETURNING 1
            """,
            (username.lower(), code, now),
        )
        inserted = cur.fetchone()
        db.commit()
        return bool(inserted)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return False
    finally:
        cur.close()


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
