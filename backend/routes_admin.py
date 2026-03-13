"""
routes_admin.py — All /api/admin/* endpoints.

Deferred imports from main inside each route to avoid circular imports.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/api/admin/users")
async def admin_list_users(request: Request):
    import main as _m
    actor = _m.require_admin(request)
    return _m.authhandlers.admin_list_users(
        actor=actor,
        list_users=_m.authstore.list_users,
        db=_m._db,
        now_iso=_m.utc_now_iso,
    )


@router.patch("/api/admin/users/{username}/role")
async def admin_set_user_role(username: str, request: Request):
    import main as _m
    _m.enforce_csrf(request)
    actor = _m.require_admin(request)
    if _m._db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    body = await request.json()
    _payload = _m.AdminSetRolePayload(**body)
    return _m.authhandlers.admin_set_role(
        username=username,
        role=_payload.role,
        actor=actor,
        db=_m._db,
        now_iso=_m.utc_now_iso,
        set_user_role=_m.authstore.set_user_role,
        audit_log=_m.audit_log,
    )


@router.delete("/api/admin/users/{username}")
async def admin_delete_user(username: str, request: Request):
    import main as _m
    _m.enforce_csrf(request)
    actor = _m.require_admin(request)
    if _m._db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return _m.authhandlers.admin_delete(
        username=username,
        actor=actor,
        db=_m._db,
        now_iso=_m.utc_now_iso,
        delete_user=_m.authstore.delete_user,
        audit_log=_m.audit_log,
    )
