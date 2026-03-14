"""
routes_v2.py — All /api/v2/*, /api/media/consume, and WebSocket endpoints.

Each route function does `import main as _m` at call time to avoid circular
imports. Python caches the module so this is cheap after first call.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, WebSocket
from fastapi.websockets import WebSocketDisconnect

router = APIRouter()

# ── Lazy proxies for main.py functions (avoids circular import at load time) ───
def _lazy(fn_name):
    def _proxy(*args, **kwargs):
        import main as _m
        return getattr(_m, fn_name)(*args, **kwargs)
    _proxy.__name__ = fn_name
    return _proxy

_extract_source        = _lazy("_extract_source")
_is_telegram_source    = _lazy("_is_telegram_source")
_normalize_threat_level = _lazy("_normalize_threat_level")
_parse_iso             = _lazy("_parse_iso")
_safe_v2_report        = _lazy("_safe_v2_report")
_v2_events_for_ai      = _lazy("_v2_events_for_ai")
_watchdog_check        = _lazy("_watchdog_check")
assess_confidence_v2   = _lazy("assess_confidence_v2")
audit_log              = _lazy("audit_log")
auth_user_from_request = _lazy("auth_user_from_request")
build_event_graph      = _lazy("build_event_graph")
build_ops_alerts       = _lazy("build_ops_alerts")
cluster_events_for_map = _lazy("cluster_events_for_map")
eta_band               = _lazy("eta_band")
fetch_ai_report_history = _lazy("fetch_ai_report_history")
fetch_metoc            = _lazy("fetch_metoc")
fetch_recent_v2_events_pg = _lazy("fetch_recent_v2_events_pg")
get_media_analysis     = _lazy("get_media_analysis")
is_playable_video_url  = _lazy("is_playable_video_url")
load_overlays          = _lazy("load_overlays")
mgrs_from_latlng       = _lazy("mgrs_from_latlng")
persist_ai_report      = _lazy("persist_ai_report")
persist_event          = _lazy("persist_event")
postgres_status        = _lazy("postgres_status")
require_analyst_or_admin = _lazy("require_analyst_or_admin")
resolve_write_identity = _lazy("resolve_write_identity")
source_ops_metrics     = _lazy("source_ops_metrics")
utc_now_iso            = _lazy("utc_now_iso")

# ── Shared state from state.py (same object as main.py uses) ──────────────────
import state as _state
_v2_report_state    = _state._v2_report_state
_analyst_state      = _state._analyst_state
_defcon_state       = _state._defcon_state
_media_job_state    = _state._media_job_state
seen_articles       = _state.seen_articles
seen_telegram_posts = _state.seen_telegram_posts
metrics             = _state.metrics
manager             = _state.manager
last_aircraft       = _state.last_aircraft
_start_time         = _state._start_time
_media_jobs         = _state._media_jobs
_review_cache       = _state._review_cache
_ollama_available_models = _state._ollama_available_models
events_buffer       = _state.events_buffer
events_history      = _state.events_history
graph_logger        = _state.graph_logger


# ── Live-rebound state: proxy to always reflect current value ─────────────────
class _DbProxy:
    """Forwards attribute/call access to state._db (set at startup)."""
    def __getattr__(self, name):
        db = _state._db
        if db is None:
            raise RuntimeError("DB not initialized")
        return getattr(db, name)
_db = _DbProxy()


class _SchedulerProxy:
    """Forwards attribute access to state._v2_ai_scheduler (set at startup)."""
    def __getattr__(self, name):
        s = _state._v2_ai_scheduler
        if s is None:
            import main as _m
            s = _m._v2_ai_scheduler
        return getattr(s, name)
_v2_ai_scheduler = _SchedulerProxy()


class _GraphStoreProxy:
    """Forwards attribute access to state._graph_store (set at startup)."""
    def __getattr__(self, name):
        gs = _state._graph_store
        return getattr(gs, name) if gs is not None else None
_graph_store = _GraphStoreProxy()

# ── Config constants ──────────────────────────────────────────────────────────
from config import (
    V2_MODEL_REPORT, V2_MODEL_VERIFY, V2_MODEL_DEFAULT,
    OLLAMA_MODEL, OLLAMA_FALLBACK_MODEL,
    STORAGE_BACKEND,
    TELEGRAM_MEDIA_DIR, TELEGRAM_SOURCE_SET,
    V2_API_KEY,
    V2_REPORT_CACHE_TTL_SEC,
    SOURCE_RELIABILITY,
)
from pydantic import BaseModel


class OpsBriefPayload(BaseModel):
    mode: str = "INTSUM"
    limit: int = 20


def _require_analyst_or_admin(request: Request) -> dict:
    import main as _m
    return _m.require_analyst_or_admin(request)

@router.get("/api/v2/ai/policy")
async def v2_ai_policy():
    return _v2_ai_scheduler.status()


@router.get("/api/v2/ai/report")
async def v2_ai_report(force: bool = False, _user: dict = Depends(_require_analyst_or_admin)):
    latest = _v2_events_for_ai(limit=160)
    latest_slice = [
        {
            "id": e.get("id"),
            "type": e.get("type"),
            "desc": e.get("description") or e.get("desc"),
            "source": _extract_source(e),
            "timestamp": e.get("timestamp"),
            "confidence": e.get("confidence_score"),
            "insufficient_evidence": bool(e.get("insufficient_evidence", False)),
        }
        for e in latest[-120:]
    ]
    fingerprint_seed = "|".join([f"{x.get('id')}@{x.get('timestamp')}" for x in latest_slice[-50:]])
    event_fp = hashlib.sha256(fingerprint_seed.encode()).hexdigest() if fingerprint_seed else "empty"

    now_ts = time.time()
    age_ok = (now_ts - float(_v2_report_state.get("last_generated_ts", 0.0))) < V2_REPORT_CACHE_TTL_SEC
    same_events = _v2_report_state.get("last_event_fp") == event_fp
    if (not force) and age_ok and same_events and _v2_report_state.get("report"):
        return _v2_report_state["report"]
    if not latest_slice:
        return _safe_v2_report("No recent events available for v2 report generation.")

    evidence_lines = "\n".join(
        [
            f"- [{e.get('type', 'UNKNOWN')}] {e.get('desc', '')} "
            f"(source={e.get('source', '')}, confidence={e.get('confidence')}, insufficient={e.get('insufficient_evidence')})"
            for e in latest_slice[-45:]
        ]
    )
    prompt = f"""You are an OSINT report reasoning engine.
Return ONLY strict JSON:
{{
  "summary": "2-3 sentence report",
  "threat_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "key_developments": ["item1","item2","item3"],
  "insufficient_evidence": true|false
}}
Rules:
- Use only the evidence provided.
- If evidence is weak/contradictory: insufficient_evidence=true.
- If insufficient_evidence=true, threat_level cannot exceed MEDIUM.
- No markdown and no extra keys.

EVIDENCE:
{evidence_lines}
"""
    try:
        data = await _v2_ai_scheduler.run_json("report", prompt=prompt, temperature=0.05)
    except HTTPException:
        return _safe_v2_report("Report model unavailable or timed out.")

    key_developments = data.get("key_developments") if isinstance(data.get("key_developments"), list) else []
    key_developments = [str(x)[:220] for x in key_developments[:5]] or ["Insufficient verified evidence"]
    insufficient = bool(data.get("insufficient_evidence", False))
    threat = _normalize_threat_level(str(data.get("threat_level", "MEDIUM")))
    if insufficient and threat in {"HIGH", "CRITICAL"}:
        threat = "MEDIUM"
    summary = str(data.get("summary", "")).strip() or "Insufficient evidence to produce a stable v2 report."

    report = {
        "summary": summary,
        "threat_level": threat,
        "key_developments": key_developments,
        "insufficient_evidence": insufficient,
        "generated_at": utc_now_iso(),
        "model": V2_MODEL_REPORT,
    }
    _v2_report_state["report"] = report
    _v2_report_state["last_event_fp"] = event_fp
    _v2_report_state["last_generated_ts"] = now_ts
    persist_ai_report("v2", report, event_fp)
    return report


@router.post("/api/v2/ai/verify")
async def v2_ai_verify(payload: Dict[str, Any], _user: dict = Depends(_require_analyst_or_admin)):
    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip()
    source = str(payload.get("source", "")).strip()
    published_at = str(payload.get("published_at", "")).strip()
    if not (title or body):
        raise HTTPException(status_code=400, detail="title or body is required")

    prompt = f"""You are an OSINT verification classifier.
Return ONLY strict JSON:
{{
  "classification": "verified|likely|uncertain|disputed",
  "confidence_0_to_100": 0,
  "reasoning": ["reason1","reason2","reason3"],
  "required_follow_up": ["step1","step2"],
  "insufficient_evidence": true|false
}}
Rules:
- Prefer uncertain when evidence is limited.
- Keep each reason under 140 characters.
- No markdown and no extra keys.

SOURCE: {source or "unknown"}
PUBLISHED_AT: {published_at or "unknown"}
TITLE: {title}
BODY: {body}
"""
    data = await _v2_ai_scheduler.run_json("verify", prompt=prompt, temperature=0.0)
    classification = str(data.get("classification", "uncertain")).lower().strip()
    if classification not in {"verified", "likely", "uncertain", "disputed"}:
        classification = "uncertain"
    confidence = int(data.get("confidence_0_to_100", 40))
    reasons = data.get("reasoning") if isinstance(data.get("reasoning"), list) else []
    follow_up = data.get("required_follow_up") if isinstance(data.get("required_follow_up"), list) else []
    return {
        "classification": classification,
        "confidence_0_to_100": max(0, min(100, confidence)),
        "reasoning": [str(x)[:160] for x in reasons[:4]],
        "required_follow_up": [str(x)[:160] for x in follow_up[:4]],
        "insufficient_evidence": bool(data.get("insufficient_evidence", classification in {"uncertain", "disputed"})),
        "model": V2_MODEL_VERIFY,
        "generated_at": utc_now_iso(),
    }


@router.get("/api/v2/reports/history")
async def v2_reports_history(
    report_type: str = "v2",
    limit: int = 50,
    _user: dict = Depends(_require_analyst_or_admin),
):
    limit = min(max(limit, 1), 200)
    if report_type not in {"v2", "analyst"}:
        raise HTTPException(status_code=400, detail="report_type must be 'v2' or 'analyst'")
    return fetch_ai_report_history(report_type, limit=limit)


@router.get("/api/v2/graph")
async def v2_event_graph(request: Request, limit: int = 350):
    require_analyst_or_admin(request)
    safe_limit = min(max(limit, 30), 1500)
    if _state._graph_store is not None and _graph_store.status().get("connected"):
        try:
            graph = await asyncio.to_thread(_graph_store.get_graph_data, safe_limit)
            return {
                "backend": "neo4j",
                "nodes": graph.get("nodes", []),
                "edges": graph.get("edges", []),
                "generated_at": utc_now_iso(),
            }
        except Exception as exc:
            graph_logger.warning("[GRAPH] graph query failed, falling back: %s", exc)

    rows = fetch_recent_v2_events_pg(limit=safe_limit)
    if not rows:
        rows = events_history[-safe_limit:]
    fallback_graph = build_event_graph(rows)
    return {
        "backend": "fallback",
        "nodes": fallback_graph.get("nodes", []),
        "edges": fallback_graph.get("edges", []),
        "generated_at": utc_now_iso(),
    }


@router.get("/api/v2/graph/node/{node_id}")
async def v2_graph_node_profile(node_id: str, request: Request):
    require_analyst_or_admin(request)
    if _state._graph_store is None or not _graph_store.status().get("connected"):
        raise HTTPException(status_code=503, detail="Graph store unavailable")
    profile = await asyncio.to_thread(_graph_store.get_node_profile, node_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Node not found")
    return profile


@router.post("/api/v2/graph/node/assess")
async def v2_graph_node_assess(payload: Dict[str, Any], request: Request):
    require_analyst_or_admin(request)
    node_id = str(payload.get("node_id") or "").strip()
    node_type = str(payload.get("node_type") or "UNKNOWN").strip().upper()
    node_data = payload.get("node_data") if isinstance(payload.get("node_data"), dict) else {}
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required")

    compact = {
        "node_id": node_id,
        "node_type": node_type,
        "label": node_data.get("label"),
        "confidence_score": node_data.get("confidence_score") or node_data.get("confidence"),
        "source": node_data.get("source"),
        "timestamp": node_data.get("timestamp"),
        "incident_id": node_data.get("incident_id"),
        "lat": node_data.get("lat"),
        "lng": node_data.get("lng"),
        "description": node_data.get("description") or node_data.get("desc"),
        "reliability": node_data.get("reliability"),
        "event_count": node_data.get("event_count"),
        "trend": node_data.get("trend"),
    }
    prompt = f"""You are an OSINT analyst assistant.
Return ONLY strict JSON:
{{
  "assessment": "2-3 concise advisory sentences grounded in provided node evidence."
}}
Rules:
- Keep neutral analytical tone.
- Mention uncertainty if evidence is weak or sparse.
- No markdown and no extra keys.

NODE_PAYLOAD:
{json.dumps(compact, ensure_ascii=False)}
"""
    try:
        data = await _v2_ai_scheduler.run_json("report", prompt=prompt, temperature=0.05)
        text = str(data.get("assessment", "")).strip()
        if not text:
            text = "Insufficient verified evidence for a stable node-level assessment."
        return {
            "node_id": node_id,
            "node_type": node_type,
            "assessment": text,
            "model": V2_MODEL_REPORT,
            "generated_at": utc_now_iso(),
            "offline": False,
        }
    except HTTPException:
        return {
            "node_id": node_id,
            "node_type": node_type,
            "assessment": "AI ANALYST OFFLINE",
            "model": V2_MODEL_REPORT,
            "generated_at": utc_now_iso(),
            "offline": True,
        }


@router.post("/api/media/consume")
async def media_consume(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    event_id = str(payload.get("event_id", "")).strip()
    video_url = str(payload.get("video_url", "")).strip()
    if not video_url.startswith("/media/telegram/"):
        raise HTTPException(status_code=400, detail="Only local telegram media can be consumed")

    filename = Path(video_url).name
    media_path = (TELEGRAM_MEDIA_DIR / filename).resolve()
    telegram_root = TELEGRAM_MEDIA_DIR.resolve()
    if telegram_root not in media_path.parents:
        raise HTTPException(status_code=400, detail="Invalid media path")

    removed = False
    if media_path.exists() and media_path.is_file():
        media_path.unlink(missing_ok=True)
        removed = True

    # Clear stale video_url from runtime + DB.
    if event_id:
        for e in events_history:
            if str(e.get("id")) == event_id:
                e["video_url"] = None
                persist_event(e)
                break
    else:
        for e in events_history:
            if str(e.get("video_url", "")) == video_url:
                e["video_url"] = None
                persist_event(e)

    return {"ok": True, "removed": removed, "video_url": video_url}


@router.get("/api/v2/system")
async def v2_system():
    pg = postgres_status()
    ai_status = _v2_ai_scheduler.status()
    graph_status = _graph_store.status() if _state._graph_store is not None else {"enabled": False, "connected": False, "error": "not initialized"}
    return {
        "version": "v2-beta",
        "storage_backend": STORAGE_BACKEND,
        "ollama_model_primary": OLLAMA_MODEL,
        "ollama_model_fallback": OLLAMA_FALLBACK_MODEL,
        "ollama_models_available": sorted(_ollama_available_models),
        "v2_ai_models": {
            "default": V2_MODEL_DEFAULT,
            "verify": V2_MODEL_VERIFY,
            "report": V2_MODEL_REPORT,
        },
        "postgres": pg,
        "neo4j": graph_status,
        "queue": {
            "media_jobs_pending": _media_jobs.qsize(),
            "media_jobs_tracked": len(_media_job_state),
        },
        "defcon_level": int(_defcon_state.get("level", 5)),
        "defcon_reason": str(_defcon_state.get("reason", "Baseline monitoring state")),
        "ai_policy": ai_status.get("policy"),
        "ai_runtime": ai_status.get("runtime"),
        "generated_at": utc_now_iso(),
    }


@router.get("/api/v2/overlays")
async def v2_overlays():
    return {
        "items": load_overlays(),
        "generated_at": utc_now_iso(),
    }


@router.get("/api/v2/metoc")
async def v2_metoc(lat: Optional[float] = None, lng: Optional[float] = None):
    if lat is None or lng is None:
        sample = fetch_recent_v2_events_pg(limit=120, source_whitelist=sorted(TELEGRAM_SOURCE_SET))
        if not sample:
            sample = list(events_history[-120:])
        if sample:
            lat = sum(float(e.get("lat", 0.0)) for e in sample) / len(sample)
            lng = sum(float(e.get("lng", 0.0)) for e in sample) / len(sample)
        else:
            lat, lng = 31.7683, 35.2137
    metoc = await fetch_metoc(float(lat), float(lng))
    return metoc


@router.post("/api/v2/ai/ops-brief")
async def v2_ai_ops_brief(payload: OpsBriefPayload):
    mode = str(payload.mode or "INTSUM").upper()
    limit = min(max(int(payload.limit or 20), 5), 40)
    recent = fetch_recent_v2_events_pg(
        limit=500,
        source_whitelist=sorted(TELEGRAM_SOURCE_SET),
        type_whitelist=["STRIKE", "CRITICAL", "CLASH", "MOVEMENT", "NOTAM"],
    )
    if not recent:
        recent = [e for e in events_history[-1200:] if _is_telegram_source(e)]
    recent_sorted = sorted(recent, key=lambda x: _parse_iso(str(x.get("timestamp", utc_now_iso()))), reverse=True)
    sample = recent_sorted[:limit]
    if not sample:
        return {"mode": mode, "summary": "No events available.", "verify": [], "report": None, "generated_at": utc_now_iso()}

    verify_cards = []
    for e in sample[: min(5, len(sample))]:
        try:
            verify_prompt = f"""You verify intelligence claims.
Return strict JSON:
{{
  "classification": "credible|uncertain|unlikely",
  "confidence_0_to_100": 0,
  "reasoning": ["..."],
  "required_follow_up": ["..."],
  "insufficient_evidence": false
}}
Title: {str(e.get('desc','')).replace('[','(').replace(']',')')[:180]}
Body: {str(e.get('desc',''))[:400]}
Source: {str(e.get('source',''))}
Timestamp: {str(e.get('timestamp',''))}
"""
            vr = await _v2_ai_scheduler.run_json("verify", verify_prompt, temperature=0.0)
            verify_cards.append(
                {
                    "event_id": e.get("id"),
                    "desc": str(e.get("desc", "")).replace("[", "(").replace("]", ")")[:200],
                    "source": e.get("source"),
                    "timestamp": e.get("timestamp"),
                    "result": vr,
                }
            )
        except Exception:
            continue

    context_lines = []
    for e in sample[:25]:
        mgrs_code = mgrs_from_latlng(float(e.get("lat", 0.0)), float(e.get("lng", 0.0))) or "N/A"
        context_lines.append(
            f"- [{e.get('type')}] {str(e.get('timestamp',''))} {str(e.get('source',''))} MGRS:{mgrs_code} :: {str(e.get('desc',''))[:180]}"
        )
    for v in verify_cards:
        res = v.get("result", {})
        context_lines.append(
            f"- VERIFY {v.get('event_id')} => {res.get('classification')} ({res.get('confidence_0_to_100')})"
        )

    report_prompt = f"""You are an operational intelligence reporting assistant.
Mode: {mode}
Return strict JSON:
{{
  "title": "string",
  "summary": "string",
  "paragraphs": ["..."],
  "priority_actions": ["..."],
  "risk_level": "low|medium|high|critical"
}}
Context:
{chr(10).join(context_lines)}
"""
    report_json = await _v2_ai_scheduler.run_json("report", report_prompt, temperature=0.1)
    priority_actions = report_json.get("priority_actions") if isinstance(report_json.get("priority_actions"), list) else []
    commander_chat = {
        "one_line_risk": str(report_json.get("summary", "")).strip()[:240],
        "next_actions": [str(x)[:180] for x in priority_actions[:5]],
    }
    generated_at = utc_now_iso()
    dt = _parse_iso(generated_at)
    document_control = f"OSINT-NEXUS-{dt.strftime('%Y%m%d')}-{dt.strftime('%H%M')}-{mode.replace(' ', '-')}"
    await manager.broadcast(
        {
            "type": "report_generated",
            "data": {
                "report_type": mode,
                "document_control": document_control,
                "generated_at": generated_at,
            },
        }
    )
    return {
        "mode": mode,
        "verify": verify_cards,
        "report": report_json,
        "commander_chat": commander_chat,
        "model_policy": _v2_ai_scheduler.status().get("policy"),
        "generated_at": generated_at,
        "document_control": document_control,
    }


@router.get("/api/v2/events")
async def v2_events(limit: int = 120, clustered: bool = False):
    limit = min(max(limit, 1), 400)
    rows = fetch_recent_v2_events_pg(limit=limit, source_whitelist=sorted(TELEGRAM_SOURCE_SET))
    if not rows:
        rows = [e for e in events_history[-1200:][::-1] if _is_telegram_source(e)][:limit]
    now = datetime.now(timezone.utc)
    by_bucket = defaultdict(list)
    for e in rows:
        key = (round(float(e.get("lat", 0.0)), 1), round(float(e.get("lng", 0.0)), 1))
        by_bucket[key].append(e)
    enriched = []
    for e in rows:
        x = dict(e)
        ts = _parse_iso(str(e.get("timestamp", utc_now_iso())))
        age_min = max(0.0, (now - ts).total_seconds() / 60.0)
        nearby = by_bucket[(round(float(e.get("lat", 0.0)), 1), round(float(e.get("lng", 0.0)), 1))]
        score, reason, corroborating = assess_confidence_v2(e, nearby, age_min)
        x["media"] = get_media_analysis(str(e.get("id", "")))
        if not is_playable_video_url(str(x.get("video_url") or "")):
            x["video_url"] = None
        x["review"] = _review_cache.get(str(e.get("id", "")))
        x["confidence_score"] = score
        x["confidence"] = "HIGH" if score >= 78 else ("MEDIUM" if score >= 55 else "LOW")
        x["confidence_reason"] = reason
        x["corroborating_sources"] = corroborating
        x["fact_vs_inference"] = {
            "facts": x.get("observed_facts", []),
            "inference": x.get("model_inference", []),
        }
        x["mgrs"] = mgrs_from_latlng(float(x.get("lat", 0.0)), float(x.get("lng", 0.0)))
        enriched.append(x)
    if clustered:
        return {"clusters": cluster_events_for_map(enriched), "items": enriched}
    return enriched


@router.get("/api/v2/alerts")
async def v2_alerts(limit: int = 60):
    limit = min(max(limit, 1), 120)
    now = datetime.now(timezone.utc)
    recent = fetch_recent_v2_events_pg(
        limit=700,
        source_whitelist=sorted(TELEGRAM_SOURCE_SET),
        type_whitelist=["STRIKE", "CRITICAL", "CLASH"],
    )
    if not recent:
        recent = [e for e in events_history[-1000:] if _is_telegram_source(e) and e.get("type") in {"STRIKE", "CRITICAL", "CLASH"}]
    by_bucket = defaultdict(list)
    for e in recent:
        by_bucket[(round(float(e.get("lat", 0.0)), 1), round(float(e.get("lng", 0.0)), 1))].append(e)

    cards = []
    alert_candidates = [x for x in recent if x.get("type") in ("STRIKE", "CRITICAL", "CLASH")]
    alert_candidates.sort(key=lambda x: _parse_iso(str(x.get("timestamp", utc_now_iso()))), reverse=True)
    for e in alert_candidates:
        ts = _parse_iso(str(e.get("timestamp", utc_now_iso())))
        age_min = max(0.0, (now - ts).total_seconds() / 60.0)
        nearby = by_bucket[(round(float(e.get("lat", 0.0)), 1), round(float(e.get("lng", 0.0)), 1))]
        score, reason, corroborating = assess_confidence_v2(e, nearby, age_min)
        confidence = "HIGH" if score >= 78 else ("MEDIUM" if score >= 55 else "LOW")
        cards.append(
            {
                "id": e.get("id"),
                "incident_id": e.get("incident_id"),
                "type": e.get("type"),
                "desc": e.get("desc"),
                "timestamp": e.get("timestamp"),
                "lat": e.get("lat"),
                "lng": e.get("lng"),
                "source": _extract_source(e),
                "confidence_score": score,
                "confidence": confidence,
                "confidence_reason": reason,
                "corroborating_sources": corroborating,
                "eta_band": eta_band(e),
                "age_minutes": round(age_min, 1),
                "observed_facts": e.get("observed_facts", []),
                "model_inference": e.get("model_inference", []),
                "insufficient_evidence": bool(e.get("insufficient_evidence", False)),
                "video_url": e.get("video_url") if is_playable_video_url(str(e.get("video_url") or "")) else None,
                "video_assessment": e.get("video_assessment"),
                "video_confidence": e.get("video_confidence"),
                "mgrs": mgrs_from_latlng(float(e.get("lat", 0.0)), float(e.get("lng", 0.0))),
                "media": get_media_analysis(str(e.get("id", ""))),
                "review": _review_cache.get(str(e.get("id", ""))),
            }
        )
    return cards[:limit]


@router.get("/api/v2/sources")
async def v2_sources(limit: int = 200):
    limit = min(max(limit, 1), 400)
    rows = fetch_recent_v2_events_pg(limit=limit, source_whitelist=sorted(TELEGRAM_SOURCE_SET))
    if not rows:
        rows = [r for r in events_history[-1200:][::-1] if _is_telegram_source(r)][:limit]
    grouped = defaultdict(int)
    for r in rows:
        grouped[_extract_source(r)] += 1
    ops = source_ops_metrics(window_minutes=120)
    degraded = [k for k, v in ops["per_source"].items() if v.get("degraded")]
    return {
        "items": rows,
        "counts_by_source": dict(sorted(grouped.items(), key=lambda x: x[1], reverse=True)),
        "reliability_profile": SOURCE_RELIABILITY,
        "ops": ops,
        "degraded_sources": degraded,
        "generated_at": utc_now_iso(),
    }


@router.post("/api/v2/reviews")
async def v2_reviews(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    event_id = str(payload.get("event_id", "")).strip()
    status = str(payload.get("status", "")).strip().lower()
    note = str(payload.get("note", "")).strip()[:500]
    if status not in {"confirm", "reject", "needs_review"}:
        raise HTTPException(status_code=400, detail="invalid status")
    if not event_id:
        raise HTTPException(status_code=400, detail="missing event_id")
    incident_id = next((e.get("incident_id") for e in events_history if e.get("id") == event_id), None)
    if _db is not None:
        _db.execute(
            """
            INSERT INTO reviews (event_id, incident_id, status, analyst, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, incident_id, status, actor, note, utc_now_iso()),
        )
        _db.commit()
    _review_cache[event_id] = {"status": status, "analyst": actor, "note": note, "updated_at": utc_now_iso()}
    audit_log("review.set", actor, role, payload, target_id=event_id)
    return {"ok": True, "event_id": event_id, "status": status}


@router.get("/api/v2/reviews")
async def v2_reviews_list(limit: int = 200):
    limit = min(max(limit, 1), 500)
    if _db is None:
        return []
    rows = _db.execute(
        """
        SELECT id, event_id, incident_id, status, analyst, note, created_at
        FROM reviews ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/v2/saved-views")
async def v2_saved_views_create(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    name = str(payload.get("name", "")).strip()[:120]
    filters = payload.get("filters", {})
    if not name:
        raise HTTPException(status_code=400, detail="missing name")
    if _db is not None:
        _db.execute(
            "INSERT INTO saved_views (name, owner, filters_json, created_at) VALUES (?, ?, ?, ?)",
            (name, actor, json.dumps(filters, ensure_ascii=False), utc_now_iso()),
        )
        _db.commit()
    audit_log("saved_view.create", actor, role, payload, target_id=name)
    return {"ok": True}


@router.get("/api/v2/saved-views")
async def v2_saved_views(request: Request, owner: str = "anon", x_api_key: Optional[str] = Header(default=None, alias="x-api-key")):
    if x_api_key != V2_API_KEY:
        owner = auth_user_from_request(request).get("username", "anon")
    if _db is None:
        return []
    rows = _db.execute(
        "SELECT id, name, owner, filters_json, created_at FROM saved_views WHERE owner = ? ORDER BY id DESC",
        (owner,),
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "owner": r["owner"],
                "filters": json.loads(r["filters_json"] or "{}"),
                "created_at": r["created_at"],
            }
        )
    return out


@router.post("/api/v2/watchlists")
async def v2_watchlist_create(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    name = str(payload.get("name", "")).strip()[:120]
    query = str(payload.get("query", "")).strip()[:220]
    tags = payload.get("tags", [])
    if not name or not query:
        raise HTTPException(status_code=400, detail="missing name/query")
    if _db is not None:
        _db.execute(
            "INSERT INTO watchlists (name, owner, query, tags_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, actor, query, json.dumps(tags, ensure_ascii=False), utc_now_iso()),
        )
        _db.commit()
    audit_log("watchlist.create", actor, role, payload, target_id=name)
    return {"ok": True}


@router.get("/api/v2/watchlists")
async def v2_watchlists(request: Request, owner: str = "anon", x_api_key: Optional[str] = Header(default=None, alias="x-api-key")):
    if x_api_key != V2_API_KEY:
        owner = auth_user_from_request(request).get("username", "anon")
    if _db is None:
        return []
    rows = _db.execute(
        "SELECT id, name, owner, query, tags_json, created_at FROM watchlists WHERE owner = ? ORDER BY id DESC",
        (owner,),
    ).fetchall()
    out = []
    for r in rows:
        query = str(r["query"])
        matched = [
            e for e in events_history[-300:]
            if query.lower() in str(e.get("desc", "")).lower() or query.lower() in str(_extract_source(e)).lower()
        ]
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "owner": r["owner"],
                "query": query,
                "tags": json.loads(r["tags_json"] or "[]"),
                "hits": len(matched),
                "created_at": r["created_at"],
            }
        )
    return out


@router.post("/api/v2/pins")
async def v2_pin_incident(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    incident_id = str(payload.get("incident_id", "")).strip()
    note = str(payload.get("note", "")).strip()[:400]
    if not incident_id:
        raise HTTPException(status_code=400, detail="missing incident_id")
    if _db is not None:
        _db.execute(
            """
            INSERT OR REPLACE INTO pinned_incidents (incident_id, owner, note, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (incident_id, actor, note, utc_now_iso()),
        )
        _db.commit()
    audit_log("pin.set", actor, role, payload, target_id=incident_id)
    return {"ok": True}


@router.get("/api/v2/pins")
async def v2_pins(request: Request, owner: str = "anon", x_api_key: Optional[str] = Header(default=None, alias="x-api-key")):
    if x_api_key != V2_API_KEY:
        owner = auth_user_from_request(request).get("username", "anon")
    if _db is None:
        return []
    rows = _db.execute(
        "SELECT incident_id, owner, note, created_at FROM pinned_incidents WHERE owner = ? ORDER BY created_at DESC",
        (owner,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/v2/handoff")
async def v2_handoff_add(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    incident_id = str(payload.get("incident_id", "")).strip()
    note = str(payload.get("note", "")).strip()[:1000]
    if not incident_id or not note:
        raise HTTPException(status_code=400, detail="missing incident_id/note")
    if _db is not None:
        _db.execute(
            "INSERT INTO handoff_notes (incident_id, owner, note, created_at) VALUES (?, ?, ?, ?)",
            (incident_id, actor, note, utc_now_iso()),
        )
        _db.commit()
    audit_log("handoff.add", actor, role, payload, target_id=incident_id)
    return {"ok": True}


@router.get("/api/v2/handoff")
async def v2_handoff(incident_id: str):
    if _db is None:
        return []
    rows = _db.execute(
        "SELECT id, incident_id, owner, note, created_at FROM handoff_notes WHERE incident_id = ? ORDER BY id DESC",
        (incident_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/v2/notifications")
async def v2_notifications_create(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    min_confidence = int(payload.get("min_confidence", 75))
    event_types = payload.get("event_types", ["CRITICAL"])
    channels = payload.get("channels", ["in_app"])
    enabled = 1 if payload.get("enabled", True) else 0
    if _db is not None:
        _db.execute(
            """
            INSERT INTO notification_rules (owner, min_confidence, event_types_json, channels_json, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (actor, min_confidence, json.dumps(event_types), json.dumps(channels), enabled, utc_now_iso()),
        )
        _db.commit()
    audit_log("notifications.create", actor, role, payload)
    return {"ok": True}


@router.get("/api/v2/notifications")
async def v2_notifications(request: Request, owner: str = "anon", x_api_key: Optional[str] = Header(default=None, alias="x-api-key")):
    if x_api_key != V2_API_KEY:
        owner = auth_user_from_request(request).get("username", "anon")
    if _db is None:
        return []
    rows = _db.execute(
        """
        SELECT id, owner, min_confidence, event_types_json, channels_json, enabled, created_at
        FROM notification_rules WHERE owner = ? ORDER BY id DESC
        """,
        (owner,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "owner": r["owner"],
            "min_confidence": r["min_confidence"],
            "event_types": json.loads(r["event_types_json"] or "[]"),
            "channels": json.loads(r["channels_json"] or "[]"),
            "enabled": bool(r["enabled"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.get("/api/v2/evaluation/scorecard")
async def v2_eval_scorecard():
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    reviews = []
    if _db is not None:
        reviews = _db.execute(
            "SELECT event_id, status, created_at FROM reviews WHERE created_at >= ?",
            (week_ago,),
        ).fetchall()
    total = len(reviews)
    confirmed = sum(1 for r in reviews if r["status"] == "confirm")
    rejected = sum(1 for r in reviews if r["status"] == "reject")
    needs_review = sum(1 for r in reviews if r["status"] == "needs_review")
    false_positive_rate = round((rejected / total) * 100.0, 2) if total else 0.0
    geo_with_evidence = [e for e in events_history[-600:] if not e.get("insufficient_evidence")]
    geo_accuracy_proxy = round((len(geo_with_evidence) / max(1, len(events_history[-600:]))) * 100.0, 2)
    return {
        "window_days": 7,
        "reviewed_total": total,
        "confirmed": confirmed,
        "rejected": rejected,
        "needs_review": needs_review,
        "false_positive_rate_pct": false_positive_rate,
        "geo_accuracy_proxy_pct": geo_accuracy_proxy,
        "generated_at": utc_now_iso(),
    }


@router.get("/api/v2/onboarding")
async def v2_onboarding():
    return {
        "title": "How to read confidence",
        "steps": [
            "Observed Facts are extracted signal data.",
            "Model Inference is machine-generated interpretation and can be wrong.",
            "High confidence requires source reliability plus corroboration.",
            "Always validate critical alerts with official civil-defense channels.",
        ],
        "disclaimer": "This dashboard is advisory and not an official warning system.",
    }


@router.get("/api/v2/ops/dashboard")
async def v2_ops_dashboard():
    warnings = _watchdog_check()
    pg = postgres_status()
    return {
        "status": "nominal" if not warnings else "degraded",
        "uptime_seconds": int(time.time() - _start_time),
        "watchdog_warnings": warnings,
        "metrics": metrics,
        "queues": {
            "events_history": len(events_history),
            "events_buffer": len(events_buffer),
            "media_jobs_pending": _media_jobs.qsize(),
            "media_jobs_tracked": len(_media_job_state),
            "seen_articles": len(seen_articles),
            "seen_telegram_posts": len(seen_telegram_posts),
        },
        "postgres": pg,
        "generated_at": utc_now_iso(),
    }


@router.get("/api/v2/ops/alerts")
async def v2_ops_alerts():
    alerts = build_ops_alerts()
    return {
        "alerts": alerts,
        "total": len(alerts),
        "critical": sum(1 for a in alerts if a.get("severity") == "critical"),
        "warning": sum(1 for a in alerts if a.get("severity") == "warning"),
        "generated_at": utc_now_iso(),
    }


@router.websocket("/ws/live/v2")
async def ws_endpoint_v2(websocket: WebSocket):
    import main as _m
    if not _m.auth_user_from_websocket(websocket):
        await websocket.close(code=1008, reason="Authentication required")
        return
    if not await _m.manager.connect(websocket):
        return
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "SYSTEM",
                    "message": "Connected to OSINT Nexus v2 stream (diff + compact updates).",
                }
            )
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _m.manager.disconnect(websocket)


@router.websocket("/ws/live")
async def ws_endpoint(websocket: WebSocket):
    import main as _m
    if not _m.auth_user_from_websocket(websocket):
        await websocket.close(code=1008, reason="Authentication required")
        return
    if not await _m.manager.connect(websocket):
        return
    try:
        await websocket.send_text(json.dumps({
            "type": "SYSTEM",
            "message": "Connected to OSINT Nexus — Real-time feeds active",
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _m.manager.disconnect(websocket)
