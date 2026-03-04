import base64
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request, WebSocket


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: Optional[bytes] = None, iterations: int = 240_000) -> str:
    salt_bytes = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt_bytes).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iter_str, salt_b64, hash_b64 = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(hash_b64.encode())
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(expected, got)
    except Exception:
        return False


def auth_sign(auth_secret: str, username: str, role: str, expires_epoch: int) -> str:
    payload = f"{username}|{role}|{expires_epoch}"
    sig = hmac.new(auth_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = f"{payload}|{sig}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")


def auth_verify(auth_secret: str, token: str) -> Optional[dict]:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        username, role, expires_txt, sig = decoded.split("|", 3)
        payload = f"{username}|{role}|{expires_txt}"
        expected = hmac.new(auth_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        expires = int(expires_txt)
        if int(time.time()) > expires:
            return None
        return {"username": username, "role": role, "expires": expires, "sig": sig}
    except Exception:
        return None


def auth_token_signature(auth_secret: str, token: str) -> Optional[str]:
    verified = auth_verify(auth_secret, token)
    if not verified:
        return None
    return str(verified.get("sig") or "")


def check_password_policy(password: str) -> Optional[str]:
    if len(password) < 10:
        return "Password must be at least 10 characters"
    if not re.search(r"[a-z]", password):
        return "Password must include a lowercase letter"
    if not re.search(r"[A-Z]", password):
        return "Password must include an uppercase letter"
    if not re.search(r"[0-9]", password):
        return "Password must include a number"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must include a symbol"
    common = {"password", "12345678", "qwerty", "letmein", "admin123", "osint123"}
    if password.lower() in common:
        return "Password is too common"
    return None


def is_local_origin(origin: str) -> bool:
    try:
        parsed = urlparse(origin)
        host = (parsed.hostname or "").lower()
        return host in {"localhost", "127.0.0.1"}
    except Exception:
        return False


def is_local_dev_mode(cors_origins: List[str]) -> bool:
    if not cors_origins:
        return False
    return all(is_local_origin(o) for o in cors_origins)


def validate_security_config(
    auth_secret: str,
    auth_default_admin_password: str,
    auth_cookie_secure: bool,
    cors_origins: List[str],
    allow_insecure_defaults: bool,
) -> None:
    insecure_reasons: List[str] = []
    blocked_secrets = {"", "dev-change-me", "change-me", "secret", "osint"}
    if auth_secret.strip() in blocked_secrets or len(auth_secret.strip()) < 32:
        insecure_reasons.append("AUTH_SECRET must be set and at least 32 chars (non-default)")
    password_error = check_password_policy(auth_default_admin_password or "")
    if password_error:
        insecure_reasons.append(f"AUTH_DEFAULT_ADMIN_PASSWORD invalid: {password_error}")
    if not auth_cookie_secure and not is_local_dev_mode(cors_origins):
        insecure_reasons.append("AUTH_COOKIE_SECURE must be enabled outside local localhost dev mode")

    if insecure_reasons and not allow_insecure_defaults:
        raise RuntimeError(
            "Security configuration invalid: "
            + "; ".join(insecure_reasons)
            + ". For local-only experiments you may set ALLOW_INSECURE_DEFAULTS=1."
        )
    if insecure_reasons and allow_insecure_defaults:
        print("[SECURITY][WARNING] Insecure configuration allowed via ALLOW_INSECURE_DEFAULTS=1")
        for reason in insecure_reasons:
            print(f"[SECURITY][WARNING] {reason}")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.client.host if request.client else "unknown").strip() or "unknown"


def enforce_rate_limit(
    store: Dict[str, List[float]],
    bucket: str,
    key: str,
    max_events: int,
    window_sec: int,
) -> None:
    now = time.time()
    token = f"{bucket}:{key}"
    events = store.get(token, [])
    events = [t for t in events if now - t <= window_sec]
    if len(events) >= max_events:
        raise HTTPException(status_code=429, detail="Too many requests, retry later")
    events.append(now)
    store[token] = events


def enforce_csrf(request: Request) -> None:
    csrf_cookie = request.cookies.get("osint_csrf", "")
    csrf_header = request.headers.get("x-csrf-token", "")
    if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def is_token_revoked(db, sig: str) -> bool:
    if not sig or db is None:
        return False
    row = db.execute("SELECT sig FROM revoked_tokens WHERE sig = ?", (sig,)).fetchone()
    return row is not None


def cleanup_revoked_tokens(db) -> None:
    if db is None:
        return
    db.execute("DELETE FROM revoked_tokens WHERE expires_epoch < ?", (int(time.time()),))
    db.commit()


def auth_user_from_request(request: Request, auth_secret: str, db) -> dict:
    token = request.cookies.get("osint_auth") or ""
    verified = auth_verify(auth_secret, token) if token else None
    if not verified:
        raise HTTPException(status_code=401, detail="Authentication required")
    if is_token_revoked(db, str(verified.get("sig", ""))):
        raise HTTPException(status_code=401, detail="Session revoked")
    return verified


def auth_user_from_websocket(websocket: WebSocket, auth_secret: str, db) -> Optional[dict]:
    token = websocket.cookies.get("osint_auth") or websocket.query_params.get("token", "")
    if not token:
        return None
    verified = auth_verify(auth_secret, token)
    if not verified:
        return None
    if is_token_revoked(db, str(verified.get("sig", ""))):
        return None
    return verified


def build_auth_card_payload(
    verified: dict,
    auth_secret: str,
    auth_access_hours: int,
    auth_card_theater: str,
) -> dict:
    username = str(verified.get("username", "")).strip().lower()
    role = str(verified.get("role", "viewer")).strip().lower()
    expires = int(verified.get("expires", 0))
    sig = str(verified.get("sig", ""))
    base = f"{username}|{role}|{expires}|{sig}"
    session_digest = hashlib.sha256(base.encode("utf-8")).hexdigest()
    operator_id = f"NX-{session_digest[:4].upper()}-{session_digest[4:8].upper()}"
    signature_preview = f"{sig[:12]}...{sig[-8:]}" if len(sig) > 24 else sig
    token_preview = f"{session_digest[:20]}...{session_digest[-12:]}"

    hash_lines: List[str] = []
    for i in range(7):
        chain = hmac.new(
            auth_secret.encode("utf-8"),
            f"{base}|{i}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        hash_lines.append(chain)

    bit_source = bin(int(session_digest, 16))[2:].zfill(256)
    grid_bits = [1 if ch == "1" else 0 for ch in bit_source[:100]]
    issued_epoch = max(0, expires - auth_access_hours * 3600)
    now_epoch = int(time.time())

    session_state = "verified" if expires > now_epoch else "expired"
    fingerprint_source = f"{username}|{issued_epoch}|{expires}|{sig[:16]}"
    fingerprint_digest = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    fingerprint_id = f"FP-{fingerprint_digest[:12].upper()}"
    audit_source = f"audit|{username}|{role}|{issued_epoch}|{expires}"
    audit_stamp = hmac.new(auth_secret.encode("utf-8"), audit_source.encode("utf-8"), hashlib.sha256).hexdigest()[:20].upper()

    return {
        "username": username,
        "role": role,
        "operator_id": operator_id,
        "theater": auth_card_theater,
        "issued_at": datetime.fromtimestamp(issued_epoch, tz=timezone.utc).isoformat(),
        "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat() if expires > 0 else None,
        "expires_in_sec": max(0, expires - now_epoch),
        "token_preview": token_preview,
        "signature_preview": signature_preview,
        "hash_lines": hash_lines,
        "grid_bits": grid_bits,
        "chain_status": session_state,
        "fingerprint_id": fingerprint_id,
        "audit_stamp": audit_stamp,
        "security_grade": "S3" if role == "viewer" else ("S4" if role == "analyst" else "S5"),
        "generated_at": utc_now_iso(),
    }
