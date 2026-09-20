"""Authenticated Nexus Command snapshot route and defensive data collectors."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request

from command_intelligence import build_command_snapshot


router = APIRouter()


def _require_analyst_or_admin(request: Request) -> dict[str, Any]:
    import main as _m

    return _m.require_analyst_or_admin(request)


def _record_error(errors: list[str], source: str) -> None:
    """Record only a stable code; operational exception text may contain secrets."""
    errors.append(f"{source}:unavailable")


def _fetch_hypotheses(_m: Any) -> list[dict[str, Any]]:
    if _m.psycopg is None or not str(_m.DATABASE_URL).startswith("postgres"):
        raise RuntimeError("postgres unavailable")
    with _m.psycopg.connect(_m.DATABASE_URL, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, statement, status, confidence, evidence_ids, "
                "analyst_notes, analyst, created_at, updated_at, tags "
                "FROM hypotheses ORDER BY updated_at DESC LIMIT 100"
            )
            rows = cur.fetchall()
    columns = (
        "id", "title", "statement", "status", "confidence", "evidence_ids",
        "analyst_notes", "analyst", "created_at", "updated_at", "tags",
    )
    return [dict(zip(columns, row)) for row in rows]


def _fetch_events_by_ids(_m: Any, event_ids: list[str]) -> list[dict[str, Any]]:
    if not event_ids:
        return []
    if _m.psycopg is None or not str(_m.DATABASE_URL).startswith("postgres"):
        raise RuntimeError("postgres unavailable")
    import v2_store

    with _m.psycopg.connect(_m.DATABASE_URL, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, type, source, timestamp, lat, lng, description, payload_json, notes "
                "FROM events_v2 WHERE id = ANY(%s)",
                (event_ids,),
            )
            rows = cur.fetchall()
    return [v2_store._decode_pg_event(row, now_iso=_m.utc_now_iso) for row in rows]


def _fetch_system(_m: Any, errors: list[str]) -> dict[str, Any]:
    try:
        postgres = _m.postgres_status()
    except Exception:
        postgres = {"connected": False, "error": "status unavailable"}
        _record_error(errors, "postgres_status")

    try:
        graph = (
            _m._graph_store.status()
            if _m._graph_store is not None
            else {"enabled": False, "connected": False, "error": "not initialized"}
        )
    except Exception:
        graph = {"enabled": False, "connected": False, "error": "status unavailable"}
        _record_error(errors, "graph_status")

    try:
        scheduler = _m._v2_ai_scheduler.status()
        ai_available = bool(
            getattr(_m, "_ollama_available_models", set())
            or _m.groq_client.groq_available()
        )
        ai_runtime = {"available": ai_available, **(scheduler.get("runtime") or {})}
    except Exception:
        ai_runtime = {"available": False, "error": "status unavailable"}
        _record_error(errors, "ai_status")
    return {"postgres": postgres, "neo4j": graph, "ai_runtime": ai_runtime}


def _fetch_sitrep(_m: Any) -> dict[str, Any]:
    latest = _m.load_latest_ai_report("sitrep") or {}
    report = latest.get("report") if isinstance(latest, dict) else {}
    if not isinstance(report, dict):
        return {}
    sitrep = report.get("sitrep") if isinstance(report.get("sitrep"), dict) else report
    return {
        **sitrep,
        "generated_at": sitrep.get("generated_at") or report.get("generated_at"),
    }


def _fetch_escalation(_m: Any) -> dict[str, Any]:
    import escalation_classifier

    theaters = escalation_classifier.get_all_theater_states(_m.DATABASE_URL, _m.psycopg)
    return {"theaters": theaters, "scanned_at": datetime.now(timezone.utc).isoformat()}


def _collect_command_inputs() -> dict[str, Any]:
    """Collect each source independently so one outage cannot erase the snapshot."""
    import main as _m

    errors: list[str] = []
    try:
        events = _m.fetch_recent_v2_events_pg(limit=250)
        if not events:
            events = list(reversed(list(_m.events_history)[-250:]))
    except Exception:
        events = list(reversed(list(getattr(_m, "events_history", []))[-250:]))
        _record_error(errors, "events")

    try:
        hypotheses = _fetch_hypotheses(_m)
    except Exception:
        hypotheses = []
        _record_error(errors, "hypotheses")

    loaded_ids = {str(event.get("id")) for event in events if event.get("id") is not None}
    referenced_ids = {
        str(event_id)
        for hypothesis in hypotheses
        for event_id in (hypothesis.get("evidence_ids") or [])
        if event_id is not None
    }
    missing_referenced = sorted(referenced_ids - loaded_ids)
    if missing_referenced:
        try:
            archived = _fetch_events_by_ids(_m, missing_referenced)
            events.extend(event for event in archived if str(event.get("id")) not in loaded_ids)
        except Exception:
            _record_error(errors, "evidence_lookup")

    system = _fetch_system(_m, errors)

    try:
        sitrep = _fetch_sitrep(_m)
    except Exception:
        sitrep = {}
        _record_error(errors, "sitrep")

    try:
        escalation = _fetch_escalation(_m)
    except Exception:
        escalation = {"theaters": []}
        _record_error(errors, "escalation")

    return {
        "events": events,
        "hypotheses": hypotheses,
        "system": system,
        "sitrep": sitrep,
        "escalation": escalation,
        "collection_errors": errors,
    }


@router.get("/api/v2/command/snapshot")
async def command_snapshot(_user: dict = Depends(_require_analyst_or_admin)) -> dict[str, Any]:
    inputs = await asyncio.to_thread(_collect_command_inputs)
    return build_command_snapshot(**inputs)
