"""
routes_auth.py — All /api/auth/* endpoints.

All imports from main are deferred (inside each route function) to avoid
circular imports at module load time. State and mutable objects are accessed
via the live main module object so tests that reload main still see the same
mutable dicts/references.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth: register / login / logout / session / card
# ---------------------------------------------------------------------------

@router.post("/api/auth/register")
async def auth_register(request: Request):
    import main as _m
    body = await request.json()
    _payload = _m.AuthRegisterPayload(**body)
    return _m.authhandlers.register_user(
        db=_m._db,
        payload=_payload,
        request=request,
        enforce_rate_limit=_m.enforce_rate_limit,
        client_ip=_m._client_ip,
        rate_register_per_ip=_m.AUTH_RATE_REGISTER_PER_IP,
        rate_window_sec=_m.AUTH_RATE_WINDOW_SEC,
        check_password_policy=_m.check_password_policy,
        get_user=_m.get_user,
        hash_password=_m.hash_password,
        create_user=_m.authstore.create_user,
        now_iso=_m.utc_now_iso,
    )


@router.post("/api/auth/login")
async def auth_login(request: Request, response: Response):
    import main as _m
    body = await request.json()
    _payload = _m.AuthLoginPayload(**body)
    return _m.authhandlers.login_user(
        db=_m._db,
        payload=_payload,
        request=request,
        response=response,
        cleanup_revoked_tokens=_m.cleanup_revoked_tokens,
        client_ip=_m._client_ip,
        enforce_rate_limit=_m.enforce_rate_limit,
        rate_login_per_ip=_m.AUTH_RATE_LOGIN_PER_IP,
        rate_window_sec=_m.AUTH_RATE_WINDOW_SEC,
        failed_logins=_m._failed_logins,
        login_max_attempts=_m.AUTH_LOGIN_MAX_ATTEMPTS,
        login_lock_sec=_m.AUTH_LOGIN_LOCK_SEC,
        get_user=_m.get_user,
        verify_password=_m.verify_password,
        access_hours=_m.AUTH_ACCESS_HOURS,
        auth_sign=_m.auth_sign,
        auth_cookie_secure=_m.AUTH_COOKIE_SECURE,
        mfa_required_for_role=_m.mfa_required_for_role,
        mfa_enabled_for_user=_m.mfa_enabled_for_user,
        mfa_verify_user_code=_m.mfa_verify_user_code,
        admin_password_block_reason=_m.admin_password_block_reason,
    )


@router.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    import main as _m
    return _m.authhandlers.logout_user(
        request=request,
        response=response,
        enforce_csrf=_m.enforce_csrf,
        auth_verify=_m.auth_verify,
        revoke_token=_m.authstore.revoke_token,
        db=_m._db,
        now_iso=_m.utc_now_iso,
        auth_cookie_secure=_m.AUTH_COOKIE_SECURE,
    )


@router.get("/api/auth/session")
async def auth_session(request: Request):
    import main as _m
    return _m.authhandlers.session_user(
        request=request,
        auth_verify=_m.auth_verify,
        is_token_revoked=_m.is_token_revoked,
    )


@router.get("/api/auth/card")
async def auth_card(request: Request):
    import main as _m
    verified = _m.auth_user_from_request(request)
    return {"card": _m.build_auth_card_payload(verified)}


# ---------------------------------------------------------------------------
# Auth: MFA / TOTP
# ---------------------------------------------------------------------------

@router.get("/api/auth/mfa/totp/status")
async def auth_mfa_totp_status(request: Request):
    import main as _m
    verified = _m.auth_user_from_request(request)
    username = str(verified.get("username", "")).strip().lower()
    role = str(verified.get("role", "viewer")).strip().lower()
    return {
        "enabled": _m.mfa_enabled_for_user(username),
        "required_for_role": _m.mfa_required_for_role(role),
        "role": role,
        "method": "totp",
    }


@router.post("/api/auth/mfa/totp/setup")
async def auth_mfa_totp_setup(request: Request):
    import main as _m
    _m.enforce_csrf(request)
    verified = _m.auth_user_from_request(request)
    username = str(verified.get("username", "")).strip().lower()
    if not _m.AUTH_ENABLE_TOTP:
        raise HTTPException(status_code=400, detail="TOTP is disabled by configuration")
    if _m._db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    secret = _m.mfa_totp.create_or_rotate_secret(_m._db, username, _m.utc_now_iso())
    uri = f"otpauth://totp/OSINT%20Nexus:{username}?secret={secret}&issuer=OSINT%20Nexus"
    _m.audit_log(
        "auth.mfa.totp.setup",
        actor=username,
        role=str(verified.get("role", "viewer")),
        payload={"enabled": False},
        target_id=username,
    )
    return {"secret": secret, "otpauth_uri": uri, "enabled": False}


@router.post("/api/auth/mfa/totp/enable")
async def auth_mfa_totp_enable(request: Request):
    import main as _m
    _m.enforce_csrf(request)
    verified = _m.auth_user_from_request(request)
    username = str(verified.get("username", "")).strip().lower()
    if not _m.AUTH_ENABLE_TOTP:
        raise HTTPException(status_code=400, detail="TOTP is disabled by configuration")
    if _m._db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    body = await request.json()
    _payload = _m.AuthTotpCodePayload(**body)
    secret = _m.mfa_totp.get_secret(_m._db, username)
    if not secret:
        raise HTTPException(status_code=400, detail="Setup required before enabling TOTP")
    if not _m.mfa_totp.verify_code(secret, _payload.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    _m.mfa_totp.enable_totp(_m._db, username, _m.utc_now_iso())
    _m.audit_log(
        "auth.mfa.totp.enable",
        actor=username,
        role=str(verified.get("role", "viewer")),
        payload={"enabled": True},
        target_id=username,
    )
    return {"ok": True, "enabled": True}


@router.post("/api/auth/mfa/totp/disable")
async def auth_mfa_totp_disable(request: Request):
    import main as _m
    _m.enforce_csrf(request)
    verified = _m.auth_user_from_request(request)
    username = str(verified.get("username", "")).strip().lower()
    if _m._db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    _m.mfa_totp.disable_totp(_m._db, username, _m.utc_now_iso())
    _m.audit_log(
        "auth.mfa.totp.disable",
        actor=username,
        role=str(verified.get("role", "viewer")),
        payload={"enabled": False},
        target_id=username,
    )
    return {"ok": True, "enabled": False}


# ---------------------------------------------------------------------------
# Auth: Passkeys
# ---------------------------------------------------------------------------

@router.post("/api/auth/passkey/register/options")
async def auth_passkey_register_options(request: Request):
    import main as _m
    if not _m.WEBAUTHN_AVAILABLE:
        raise HTTPException(status_code=503, detail="Passkey support unavailable on server")
    from webauthn import generate_registration_options
    from webauthn.helpers import base64url_to_bytes, options_to_json
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor, PublicKeyCredentialType
    _m.enforce_csrf(request)
    verified = _m.auth_user_from_request(request)
    username = str(verified.get("username", "")).strip().lower()
    existing = _m.authpasskey.list_for_user(_m._db, username)
    exclude = [
        PublicKeyCredentialDescriptor(
            id=base64url_to_bytes(str(x.get("credential_id", ""))),
            type=PublicKeyCredentialType.PUBLIC_KEY,
        )
        for x in existing
        if str(x.get("credential_id", "")).strip()
    ]
    options = generate_registration_options(
        rp_id=_m.PASSKEY_RP_ID,
        rp_name=_m.PASSKEY_RP_NAME,
        user_name=username,
        user_id=username.encode("utf-8"),
        user_display_name=username,
        exclude_credentials=exclude,
        authenticator_selection=None,
    )
    _m._prune_passkey_challenges()
    _m._passkey_reg_challenges[username] = {
        "challenge": options.challenge,
        "expires_at": time.time() + _m.PASSKEY_CHALLENGE_TTL_SEC,
    }
    return {"options": json.loads(options_to_json(options))}


@router.get("/api/auth/passkey/status")
async def auth_passkey_status(request: Request):
    import main as _m
    verified = _m.auth_user_from_request(request)
    username = str(verified.get("username", "")).strip().lower()
    role = str(verified.get("role", "viewer")).strip().lower()
    return {
        "enabled": _m.passkey_count_for_user(username) > 0,
        "count": _m.passkey_count_for_user(username),
        "required_for_role": role == "admin" and _m.AUTH_ADMIN_REQUIRE_PASSKEY,
    }


@router.post("/api/auth/passkey/register/verify")
async def auth_passkey_register_verify(request: Request):
    import main as _m
    if not _m.WEBAUTHN_AVAILABLE:
        raise HTTPException(status_code=503, detail="Passkey support unavailable on server")
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
    _m.enforce_csrf(request)
    verified = _m.auth_user_from_request(request)
    username = str(verified.get("username", "")).strip().lower()
    _m._prune_passkey_challenges()
    body = await request.json()
    _payload = _m.PasskeyRegisterVerifyPayload(**body)
    ch = _m._passkey_reg_challenges.get(username)
    if not ch:
        raise HTTPException(status_code=400, detail="Passkey registration challenge expired")
    try:
        vr = verify_registration_response(
            credential=_payload.credential,
            expected_challenge=ch["challenge"],
            expected_rp_id=_m.PASSKEY_RP_ID,
            expected_origin=_m.PASSKEY_ORIGINS,
            require_user_verification=True,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Passkey registration failed: {e}")
    cred_id_b64 = bytes_to_base64url(vr.credential_id)
    pub_b64 = bytes_to_base64url(vr.credential_public_key)
    _m.authpasskey.upsert_passkey(
        _m._db,
        username=username,
        credential_id=cred_id_b64,
        public_key_b64=pub_b64,
        sign_count=int(vr.sign_count),
        label=str(_payload.label or "primary"),
        now_iso=_m.utc_now_iso(),
    )
    _m._passkey_reg_challenges.pop(username, None)
    _m.audit_log(
        "auth.passkey.register",
        actor=username,
        role=str(verified.get("role", "viewer")),
        payload={"credential_id": cred_id_b64[:14] + "..."},
        target_id=username,
    )
    return {"ok": True, "credential_id": cred_id_b64}


@router.post("/api/auth/passkey/login/options")
async def auth_passkey_login_options(request: Request):
    import main as _m
    if not _m.WEBAUTHN_AVAILABLE:
        raise HTTPException(status_code=503, detail="Passkey support unavailable on server")
    from webauthn import generate_authentication_options
    from webauthn.helpers import base64url_to_bytes, options_to_json
    from webauthn.helpers.structs import (
        PublicKeyCredentialDescriptor,
        PublicKeyCredentialType,
        UserVerificationRequirement,
    )
    body = await request.json()
    _payload = _m.PasskeyUserPayload(**body)
    username = _payload.username.strip().lower()
    user = _m.get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if str(user["role"]).strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="Passkey login is currently required for admin users")
    creds = _m.authpasskey.list_for_user(_m._db, username)
    if not creds:
        raise HTTPException(status_code=400, detail="No passkey enrolled for this account")
    allow = [
        PublicKeyCredentialDescriptor(
            id=base64url_to_bytes(str(c.get("credential_id", ""))),
            type=PublicKeyCredentialType.PUBLIC_KEY,
        )
        for c in creds
    ]
    options = generate_authentication_options(
        rp_id=_m.PASSKEY_RP_ID,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _m._prune_passkey_challenges()
    _m._passkey_auth_challenges[username] = {
        "challenge": options.challenge,
        "expires_at": time.time() + _m.PASSKEY_CHALLENGE_TTL_SEC,
    }
    return {"options": json.loads(options_to_json(options))}


@router.post("/api/auth/passkey/login/verify")
async def auth_passkey_login_verify(request: Request, response: Response):
    import main as _m
    if not _m.WEBAUTHN_AVAILABLE:
        raise HTTPException(status_code=503, detail="Passkey support unavailable on server")
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes
    body = await request.json()
    _payload = _m.PasskeyLoginVerifyPayload(**body)
    username = _payload.username.strip().lower()
    user = _m.get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    role = str(user["role"]).strip().lower()
    if role != "admin":
        raise HTTPException(status_code=403, detail="Passkey login is currently required for admin users")
    _m._prune_passkey_challenges()
    ch = _m._passkey_auth_challenges.get(username)
    if not ch:
        raise HTTPException(status_code=400, detail="Passkey authentication challenge expired")
    cred_id = str(_payload.credential.get("id") or "").strip()
    row = _m.authpasskey.get_by_credential_id(_m._db, cred_id)
    if not row or str(row.get("username", "")).strip().lower() != username:
        raise HTTPException(status_code=401, detail="Unknown passkey")
    try:
        va = verify_authentication_response(
            credential=_payload.credential,
            expected_challenge=ch["challenge"],
            expected_rp_id=_m.PASSKEY_RP_ID,
            expected_origin=_m.PASSKEY_ORIGINS,
            credential_public_key=base64url_to_bytes(str(row.get("public_key_b64", ""))),
            credential_current_sign_count=int(row.get("sign_count") or 0),
            require_user_verification=True,
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Passkey verification failed: {e}")
    _m.authpasskey.update_sign_count(
        _m._db,
        credential_id=cred_id,
        sign_count=int(va.new_sign_count),
        now_iso=_m.utc_now_iso(),
    )
    _m._passkey_auth_challenges.pop(username, None)
    _m.audit_log(
        "auth.passkey.login",
        actor=username,
        role=role,
        payload={"credential_id": cred_id[:14] + "..."},
        target_id=username,
    )
    return _m._set_auth_cookies(response, username, role)
