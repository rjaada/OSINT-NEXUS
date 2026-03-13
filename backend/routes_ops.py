"""
routes_ops.py — Health, stats, events, sources, alerts, analyst, metrics endpoints.

Deferred imports from main inside each route to avoid circular imports.
Auth dependencies that need to be resolved at definition time use a lazy
wrapper that delegates to main's actual function at call time.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response

router = APIRouter()


# ---------------------------------------------------------------------------
# Lazy auth dependency wrappers (evaluated at call time, not import time)
# ---------------------------------------------------------------------------

def _require_analyst_or_admin(request: Request) -> dict:
    import main as _m
    return _m.require_analyst_or_admin(request)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/api/health")
async def health():
    import main as _m
    return {
        "status": "ok",
        "clients": len(_m.manager.connections),
        "events_buffered": len(_m.events_buffer),
        "events_persisted": len(_m.events_history),
        "watchdog_warnings": _m._watchdog_check(),
    }


@router.get("/api/ops/health")
async def ops_health():
    import main as _m
    warnings = _m._watchdog_check()
    return {
        "status": "nominal" if not warnings else "degraded",
        "uptime_seconds": int(time.time() - _m._start_time),
        "metrics": _m.metrics,
        "warnings": warnings,
        "queues": {
            "events_history": len(_m.events_history),
            "events_buffer": len(_m.events_buffer),
            "seen_articles": len(_m.seen_articles),
            "seen_telegram_posts": len(_m.seen_telegram_posts),
        },
        "defcon_level": int(_m._defcon_state.get("level", 5)),
        "defcon_reason": str(_m._defcon_state.get("reason", "Baseline monitoring state")),
    }


@router.get("/api/stats")
async def stats():
    import main as _m
    mil_count = sum(1 for a in _m.last_aircraft if a.get("military"))
    return {
        "events_total": len(_m.events_history),
        "aircraft_tracked": len(_m.last_aircraft),
        "military_aircraft": mil_count,
        "sources_active": len(_m.RSS_FEEDS_EN) + len(_m.TELEGRAM_CHANNELS) + 1,
        "clients": len(_m.manager.connections),
        "uptime_seconds": int(time.time() - _m._start_time),
        "dedup_dropped": _m.metrics["dedup_dropped"],
    }


@router.get("/api/events")
async def get_events(limit: int = 80, _user: dict = Depends(_require_analyst_or_admin)):
    import main as _m
    limit = min(max(limit, 1), 300)
    return _m.events_history[-limit:][::-1]


@router.get("/api/sources/recent")
async def sources_recent(limit: int = 150, _user: dict = Depends(_require_analyst_or_admin)):
    import main as _m
    limit = min(max(limit, 1), 300)
    rows = _m.events_history[-limit:][::-1]
    grouped: dict = defaultdict(int)
    for r in rows:
        grouped[_m._extract_source(r)] += 1
    return {
        "items": rows,
        "counts_by_source": dict(sorted(grouped.items(), key=lambda x: x[1], reverse=True)),
        "generated_at": _m.utc_now_iso(),
    }


@router.get("/api/alerts/assessment")
async def alert_assessment(limit: int = 40, _user: dict = Depends(_require_analyst_or_admin)):
    import main as _m
    if not _m.events_history:
        return []
    limit = min(max(limit, 1), 100)
    now = datetime.now(timezone.utc)
    recent = _m.events_history[-500:]

    by_bucket: dict = defaultdict(list)
    for e in recent:
        lat_b = round(float(e.get("lat", 0.0)), 1)
        lng_b = round(float(e.get("lng", 0.0)), 1)
        by_bucket[(lat_b, lng_b)].append(e)

    candidates = [e for e in recent if e.get("type") in ("STRIKE", "CRITICAL")]
    cards = []

    for event in reversed(candidates):
        ts = _m._parse_iso(str(event.get("timestamp", _m.utc_now_iso())))
        age_min = max(0.0, (now - ts).total_seconds() / 60.0)
        lat_b = round(float(event.get("lat", 0.0)), 1)
        lng_b = round(float(event.get("lng", 0.0)), 1)
        nearby = by_bucket[(lat_b, lng_b)]

        score, reason, corroborating = _m.assess_confidence(event, nearby, age_min)
        confidence = "HIGH" if score >= 80 else ("MEDIUM" if score >= 55 else "LOW")

        cards.append({
            "id": event.get("id"),
            "incident_id": event.get("incident_id"),
            "type": event.get("type"),
            "desc": event.get("desc"),
            "timestamp": event.get("timestamp"),
            "lat": event.get("lat"),
            "lng": event.get("lng"),
            "source": _m._extract_source(event),
            "confidence_score": score,
            "confidence": confidence,
            "confidence_reason": reason,
            "eta_band": _m.eta_band(event),
            "age_minutes": round(age_min, 1),
            "corroborating_sources": corroborating,
            "video_url": event.get("video_url"),
            "video_assessment": event.get("video_assessment"),
            "video_confidence": event.get("video_confidence"),
            "video_clues": event.get("video_clues", []),
            "observed_facts": event.get("observed_facts", []),
            "model_inference": event.get("model_inference", []),
            "insufficient_evidence": bool(event.get("insufficient_evidence", False)),
        })

    return cards[:limit]


@router.get("/api/analyst")
async def analyst_endpoint(force: bool = False, _user: dict = Depends(_require_analyst_or_admin)):
    import main as _m
    latest = _m.events_history[-120:]
    latest_slice = [
        {
            "id": e.get("id"),
            "type": e.get("type"),
            "desc": e.get("desc"),
            "source": _m._extract_source(e),
            "timestamp": e.get("timestamp"),
        }
        for e in latest
    ]
    fingerprint_seed = "|".join([f"{x.get('id')}@{x.get('timestamp')}" for x in latest_slice[-40:]])
    event_fp = hashlib.sha256(fingerprint_seed.encode()).hexdigest() if fingerprint_seed else "empty"

    now_ts = time.time()
    ttl_seconds = 5 * 60
    age_ok = (now_ts - float(_m._analyst_state.get("last_generated_ts", 0.0))) < ttl_seconds
    same_events = _m._analyst_state.get("last_event_fp") == event_fp
    if (not force) and age_ok and same_events and _m._analyst_state.get("report"):
        return _m._analyst_state["report"]

    report = await _m.generate_analyst_report(latest_slice)
    _m._analyst_state["report"] = report
    _m._analyst_state["last_event_fp"] = event_fp
    _m._analyst_state["last_generated_ts"] = now_ts
    _m.persist_ai_report("analyst", report, event_fp)
    return report


@router.get("/metrics")
async def metrics_endpoint():
    import main as _m
    payload = _m.render_prometheus_metrics()
    return Response(content=payload, media_type="text/plain; version=0.0.4; charset=utf-8")
