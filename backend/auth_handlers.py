import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request, Response


def register_user(
    *,
    db,
    payload,
    request: Request,
    enforce_rate_limit: Callable[[str, str, int, int], None],
    client_ip: Callable[[Request], str],
    rate_register_per_ip: int,
    rate_window_sec: int,
    check_password_policy: Callable[[str], Optional[str]],
    get_user: Callable[[str], Any],
    hash_password: Callable[[str], str],
    create_user: Callable[..., None],
    now_iso: Callable[[], str],
) -> dict:
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    enforce_rate_limit("register_ip", client_ip(request), rate_register_per_ip, rate_window_sec)
    username = payload.username.strip().lower()
    password = payload.password
    role = (payload.role or "viewer").strip().lower()
    if not re.match(r"^[a-z0-9_.-]{3,32}$", username):
        raise HTTPException(status_code=400, detail="Username must be 3-32 chars [a-z0-9_.-]")

    password_error = check_password_policy(password)
    if password_error:
        raise HTTPException(status_code=400, detail=password_error)
    if role not in {"viewer", "analyst", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    if get_user(username):
        raise HTTPException(status_code=409, detail="Username already exists")

    now = now_iso()
    create_user(
        db,
        username=username,
        password_hash=hash_password(password),
        role=role,
        now_iso=now_iso,
    )
    return {"ok": True, "username": username, "role": role, "created_at": now}


def login_user(
    *,
    db,
    payload,
    request: Request,
    response: Response,
    cleanup_revoked_tokens: Callable[[], None],
    client_ip: Callable[[Request], str],
    enforce_rate_limit: Callable[[str, str, int, int], None],
    rate_login_per_ip: int,
    rate_window_sec: int,
    failed_logins: Dict[str, Dict[str, Any]],
    login_max_attempts: int,
    login_lock_sec: int,
    get_user: Callable[[str], Any],
    verify_password: Callable[[str, str], bool],
    access_hours: int,
    auth_sign: Callable[[str, str, int], str],
    auth_cookie_secure: bool,
    mfa_required_for_role: Callable[[str], bool],
    mfa_enabled_for_user: Callable[[str], bool],
    mfa_verify_user_code: Callable[[str, str], bool],
    admin_password_block_reason: Callable[[str, str, str], Optional[str]],
) -> dict:
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    cleanup_revoked_tokens()
    ip = client_ip(request)
    enforce_rate_limit("login_ip", ip, rate_login_per_ip, rate_window_sec)
    username = payload.username.strip().lower()
    lock_key = f"{username}|{ip}"
    lock_state = failed_logins.get(lock_key) or {}
    lock_until = float(lock_state.get("lock_until", 0))
    if lock_until > time.time():
        wait_sec = max(1, int(lock_until - time.time()))
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Retry in {wait_sec}s")

    user = get_user(username)
    if not user:
        state = failed_logins.get(lock_key, {"count": 0, "lock_until": 0.0})
        state["count"] = int(state.get("count", 0)) + 1
        if state["count"] >= login_max_attempts:
            state["lock_until"] = time.time() + login_lock_sec
            state["count"] = 0
        failed_logins[lock_key] = state
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.password, str(user["password_hash"])):
        state = failed_logins.get(lock_key, {"count": 0, "lock_until": 0.0})
        state["count"] = int(state.get("count", 0)) + 1
        if state["count"] >= login_max_attempts:
            state["lock_until"] = time.time() + login_lock_sec
            state["count"] = 0
        failed_logins[lock_key] = state
        raise HTTPException(status_code=401, detail="Invalid credentials")

    failed_logins.pop(lock_key, None)
    role = str(user["role"])
    break_glass_code = str(getattr(payload, "break_glass_code", "") or "").strip()
    block_reason = admin_password_block_reason(username, role, break_glass_code)
    if block_reason:
        raise HTTPException(status_code=401, detail=block_reason)
    if mfa_required_for_role(role) and mfa_enabled_for_user(username):
        mfa_code = str(getattr(payload, "mfa_code", "") or "").strip()
        if not mfa_code:
            raise HTTPException(status_code=401, detail="MFA code required")
        if not mfa_verify_user_code(username, mfa_code):
            raise HTTPException(status_code=401, detail="Invalid MFA code")

    expiry_dt = datetime.now(timezone.utc) + timedelta(hours=access_hours)
    expires_epoch = int(expiry_dt.timestamp())
    token = auth_sign(username, role, expires_epoch)
    csrf_token = secrets.token_urlsafe(24)
    cookie_expires = expiry_dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

    for key, value in [
        ("osint_session", "1"),
        ("osint_role", role),
        ("osint_user", username),
        ("osint_auth", token),
        ("osint_csrf", csrf_token),
    ]:
        response.set_cookie(
            key=key,
            value=value,
            path="/",
            expires=cookie_expires,
            httponly=(key == "osint_auth"),
            samesite="lax",
            secure=auth_cookie_secure,
        )

    return {"ok": True, "username": username, "role": role, "expires_at": expiry_dt.isoformat(), "csrf": csrf_token}


def logout_user(
    *,
    request: Request,
    response: Response,
    enforce_csrf: Callable[[Request], None],
    auth_verify: Callable[[str], Optional[dict]],
    revoke_token: Callable[..., None],
    db,
    now_iso: Callable[[], str],
    auth_cookie_secure: bool,
) -> dict:
    enforce_csrf(request)
    token = request.cookies.get("osint_auth") or ""
    verified = auth_verify(token) if token else None
    if verified:
        revoke_token(
            db,
            sig=str(verified.get("sig", "")),
            expires_epoch=int(verified.get("expires", 0)),
            now_iso=now_iso,
        )

    for key in ["osint_session", "osint_role", "osint_user", "osint_auth", "osint_csrf"]:
        response.delete_cookie(key=key, path="/", samesite="lax", secure=auth_cookie_secure)
    return {"ok": True}


def session_user(
    *,
    request: Request,
    auth_verify: Callable[[str], Optional[dict]],
    is_token_revoked: Callable[[str], bool],
) -> dict:
    token = request.cookies.get("osint_auth") or ""
    if not token:
        return {"authenticated": False}
    verified = auth_verify(token)
    if not verified:
        return {"authenticated": False}
    if is_token_revoked(str(verified.get("sig", ""))):
        return {"authenticated": False}
    return {
        "authenticated": True,
        "username": str(verified.get("username", "")),
        "role": str(verified.get("role", "")),
        "expires": int(verified.get("expires", 0)),
        "csrf": request.cookies.get("osint_csrf", ""),
    }


def admin_list_users(*, actor: dict, list_users: Callable[[Any], list], db, now_iso: Callable[[], str]) -> dict:
    try:
        items = list_users(db)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {
        "items": items,
        "actor": str(actor.get("username", "")),
        "generated_at": now_iso(),
    }


def admin_set_role(
    *,
    username: str,
    role: str,
    actor: dict,
    db,
    now_iso: Callable[[], str],
    set_user_role: Callable[..., dict],
    audit_log: Callable[..., None],
) -> dict:
    target = username.strip().lower()
    if not re.match(r"^[a-z0-9_.-]{3,32}$", target):
        raise HTTPException(status_code=400, detail="Invalid username")
    next_role = str(role or "").strip().lower()
    if next_role not in {"viewer", "analyst", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")

    try:
        result = set_user_role(db, username=target, next_role=next_role, now_iso=now_iso)
    except LookupError:
        raise HTTPException(status_code=404, detail="User not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit_log(
        "admin.role.set",
        str(actor.get("username", "")),
        str(actor.get("role", "admin")),
        {"username": result["username"], "from": result["from"], "to": result["to"]},
        target_id=target,
    )
    return {
        "ok": True,
        "username": result["username"],
        "role": result["to"],
        "updated_at": result["updated_at"],
        "updated_by": str(actor.get("username", "")),
    }


def admin_delete(
    *,
    username: str,
    actor: dict,
    db,
    now_iso: Callable[[], str],
    delete_user: Callable[..., dict],
    audit_log: Callable[..., None],
) -> dict:
    target = username.strip().lower()
    if not re.match(r"^[a-z0-9_.-]{3,32}$", target):
        raise HTTPException(status_code=400, detail="Invalid username")

    actor_username = str(actor.get("username", "")).strip().lower()
    try:
        result = delete_user(
            db,
            username=target,
            actor_username=actor_username,
            now_iso=now_iso,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="User not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit_log(
        "admin.user.delete",
        str(actor.get("username", "")),
        str(actor.get("role", "admin")),
        {"username": result["username"], "role": result["role"]},
        target_id=target,
    )
    return {
        "ok": True,
        "username": result["username"],
        "deleted_at": result["deleted_at"],
        "deleted_by": str(actor.get("username", "")),
    }
