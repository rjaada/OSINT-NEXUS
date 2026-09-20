"""Deterministic command-level intelligence aggregation.

This module deliberately contains no I/O.  Every conclusion in a command
snapshot is derived from the supplied records so callers can audit and test it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


_THREAT_WEIGHT = {
    "CRITICAL": 5,
    "STRIKE": 5,
    "ALERT": 4,
    "FIRE": 3,
    "ACTIVITY": 2,
    "MARITIME": 1,
    "FLIGHT": 1,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _confidence(value: Any) -> float:
    return max(0.0, min(100.0, _number(value)))


def _provenance_origin(event: dict[str, Any]) -> str | None:
    provenance = event.get("provenance") if isinstance(event.get("provenance"), dict) else {}
    for value in (
        event.get("provenance_id"),
        event.get("origin_id"),
        event.get("publisher_id"),
        provenance.get("origin_id"),
        provenance.get("upstream_id"),
        provenance.get("publisher_id"),
        provenance.get("canonical_source"),
    ):
        normalized = str(value or "").strip().lower()
        if normalized:
            return normalized
    try:
        hostname = (urlparse(str(event.get("url") or "")).hostname or "").lower()
    except ValueError:
        hostname = ""
    return hostname.removeprefix("www.") or None


def assess_hypothesis_evidence(
    hypothesis: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Assess attached evidence without silently inventing corroboration."""
    del now  # Reserved for explicit recency policy; never use implicit wall time.
    requested_ids = [str(item) for item in hypothesis.get("evidence_ids") or []]
    event_by_id = {str(event.get("id")): event for event in events if event.get("id") is not None}
    attached = [event_by_id[item] for item in requested_ids if item in event_by_id]
    missing = [item for item in requested_ids if item not in event_by_id]
    sources = sorted({str(event.get("source") or "UNKNOWN") for event in attached})
    origins = sorted({origin for event in attached if (origin := _provenance_origin(event))})
    confidences = [_confidence(event.get("confidence_score")) for event in attached]
    evidence = [
        {
            "id": str(event.get("id")),
            "source": str(event.get("source") or "UNKNOWN"),
            "type": str(event.get("type") or "UNKNOWN"),
            "description": str(event.get("desc") or event.get("description") or "")[:320],
            "timestamp": event.get("timestamp"),
            "url": event.get("url") or None,
            "confidence_score": max(0, min(100, round(_number(event.get("confidence_score"))))),
            "provenance_origin": _provenance_origin(event),
        }
        for event in attached
    ]
    average_quality = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

    gaps: list[str] = []
    if not requested_ids:
        gaps.append("NO_EVIDENCE_ATTACHED")
    if missing:
        gaps.append("MISSING_EVIDENCE")
    if attached and len(origins) < 2:
        gaps.append("INDEPENDENT_CORROBORATION_REQUIRED")
    if attached and len(origins) < len(attached):
        gaps.append("UNATTRIBUTED_PROVENANCE")

    if not attached:
        posture = "INSUFFICIENT"
        recommended = min(25, round(_confidence(hypothesis.get("confidence"))))
    elif len(origins) >= 2 and average_quality >= 70:
        posture = "CORROBORATED"
        recommended = max(75, min(95, round(average_quality)))
    else:
        posture = "SINGLE_ORIGIN" if len(origins) <= 1 else "CONTESTED"
        recommended = max(0, min(65, round(average_quality)))

    return {
        "hypothesis_id": hypothesis.get("id"),
        "posture": posture,
        "recommended_confidence": recommended,
        "analyst_confidence": round(_confidence(hypothesis.get("confidence"))),
        "source_diversity": len(origins),
        "sources": sources,
        "provenance_origins": origins,
        "evidence_count": len(attached),
        "evidence_ids": [str(event.get("id")) for event in attached],
        "evidence": evidence,
        "missing_evidence_ids": missing,
        "collection_gaps": gaps,
        "average_evidence_confidence": average_quality,
        "method": "normalized_provenance_origin_count_and_mean_event_confidence_v2",
    }


def _service_ready(service: Any) -> bool:
    if not isinstance(service, dict):
        return bool(service)
    for key in ("connected", "available", "healthy", "ready"):
        if key in service:
            return bool(service[key])
    status = str(service.get("status", "")).upper()
    return status in {"OK", "UP", "READY", "HEALTHY", "CONNECTED", "AVAILABLE"}


def _priority_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("type") or "ACTIVITY").upper()
    confidence = max(0.0, min(100.0, _number(event.get("confidence_score"))))
    score = _THREAT_WEIGHT.get(event_type, 2) * 100 + confidence
    return {
        **event,
        "priority_score": round(score, 1),
        "ranked_because": {
            "threat_weight": _THREAT_WEIGHT.get(event_type, 2),
            "confidence_score": confidence,
        },
    }


def build_command_snapshot(
    *,
    events: list[dict[str, Any]] | None,
    hypotheses: list[dict[str, Any]] | None,
    system: dict[str, Any] | None,
    sitrep: dict[str, Any] | None,
    escalation: dict[str, Any] | None,
    collection_errors: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build one auditable, human-in-the-loop operational snapshot."""
    generated_at = (now or _utc_now()).astimezone(timezone.utc)
    safe_events = [event for event in (events or []) if isinstance(event, dict)]
    safe_hypotheses = [item for item in (hypotheses or []) if isinstance(item, dict)]
    safe_system = system if isinstance(system, dict) else {}
    safe_errors = [str(error) for error in (collection_errors or [])]
    missing_inputs = [
        name
        for name, value in (("events", events), ("hypotheses", hypotheses), ("system", system), ("sitrep", sitrep), ("escalation", escalation))
        if value is None
    ]

    priority_events = sorted(
        (_priority_event(event) for event in safe_events),
        key=lambda event: (-event["priority_score"], str(event.get("id", ""))),
    )[:12]
    assessments = [
        {**hypothesis, "evidence_assessment": assess_hypothesis_evidence(hypothesis, safe_events, now=generated_at)}
        for hypothesis in safe_hypotheses
    ]
    degraded = sorted(name for name, value in safe_system.items() if not _service_ready(value))
    service_count = len(safe_system)
    readiness_score = round(100 * (service_count - len(degraded)) / service_count) if service_count else 0

    decisions: list[dict[str, Any]] = []
    for service in degraded:
        decisions.append({
            "id": f"system:{service}",
            "type": "SYSTEM_DEGRADED",
            "priority": "HIGH",
            "title": f"Review degraded {service} service",
            "recommended_action": "Confirm impact and choose whether analysis may proceed.",
            "provenance": {"source": "system_status", "service": service},
            "requires_human": True,
        })
    for item in assessments:
        evidence = item["evidence_assessment"]
        if evidence["collection_gaps"]:
            decisions.append({
                "id": f"hypothesis:{item.get('id')}",
                "type": "EVIDENCE_GAP",
                "priority": "HIGH" if evidence["posture"] == "INSUFFICIENT" else "MEDIUM",
                "title": f"Resolve evidence gaps: {item.get('title') or item.get('id')}",
                "recommended_action": "Task collection or revise the analyst confidence before disposition.",
                "provenance": {
                    "source": "hypothesis_evidence_assessment",
                    "hypothesis_id": item.get("id"),
                    "gaps": evidence["collection_gaps"],
                },
                "requires_human": True,
            })

    evidence_complete = all(
        item["evidence_assessment"]["evidence_count"] > 0
        and not item["evidence_assessment"]["missing_evidence_ids"]
        for item in assessments
    )
    complete = not safe_errors and not missing_inputs

    return {
        "generated_at": generated_at.isoformat(),
        "readiness": {
            "score": readiness_score,
            "status": "READY" if not degraded and service_count else "DEGRADED",
            "degraded_services": degraded,
            "services": safe_system,
        },
        "priority_events": priority_events,
        "hypotheses": assessments,
        "sitrep": sitrep if isinstance(sitrep, dict) else {},
        "escalation": escalation if isinstance(escalation, dict) else {},
        "decision_queue": decisions,
        "integrity": {
            "evidence_backed": bool(safe_events) and complete and evidence_complete,
            "event_count": len(safe_events),
            "hypothesis_count": len(safe_hypotheses),
            "missing_inputs": missing_inputs,
            "collection_errors": safe_errors,
            "complete": complete,
            "method_version": "nexus-command-v2",
        },
    }
