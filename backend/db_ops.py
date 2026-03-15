"""
db_ops.py — Pure database operations for OSINT Nexus.

Extracted from main.py to reduce file size.
Uses lazy `import main as _m` inside function bodies to avoid circular imports.
Dependency chain: config → db_postgres → db_ops → (main loads these)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("osint.db_ops")


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── DB init ────────────────────────────────────────────────────────────────────

def init_db():
    """Open a PostgreSQL connection and initialise the schema."""
    import db_postgres
    conn = db_postgres.get_pg_conn()
    db_postgres.init_pg_schema(conn)
    return conn


# ── Event persistence ──────────────────────────────────────────────────────────

def load_recent_events(limit: int = 400):
    import main as _m
    _db = _m._db
    if _db is None:
        return
    with _db.cursor() as _cur:
        _cur.execute(
            """
            SELECT * FROM events
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = _cur.fetchall()
    _m.events_history.clear()
    _m.incident_index.clear()
    for row in reversed(rows):
        e = {
            "id": row["id"],
            "incident_id": row["incident_id"],
            "type": row["type"],
            "desc": row["desc"],
            "lat": row["lat"],
            "lng": row["lng"],
            "source": row["source"],
            "timestamp": row["timestamp"],
            "url": row["url"],
            "video_url": row["video_url"],
            "lang": row["lang"],
            "confidence_score": row["confidence_score"],
            "confidence_reason": row["confidence_reason"],
            "observed_facts": json.loads(row["observed_facts"] or "[]"),
            "model_inference": json.loads(row["model_inference"] or "[]"),
            "video_assessment": row["video_assessment"],
            "video_confidence": row["video_confidence"],
            "video_clues": json.loads(row["video_clues"] or "[]"),
        }
        _m.events_history.append(e)
        incident_id = e.get("incident_id")
        if incident_id:
            _m.incident_index[incident_id] = e


def persist_event(event: dict):
    import main as _m
    _db = _m._db
    if _db is None:
        return
    with _db.cursor() as _cur:
        _cur.execute(
            """
            INSERT INTO events (
                id, incident_id, type, "desc", lat, lng, source, timestamp, url, video_url,
                lang, confidence_score, confidence_reason, observed_facts, model_inference,
                video_assessment, video_confidence, video_clues, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                incident_id = EXCLUDED.incident_id,
                type = EXCLUDED.type,
                "desc" = EXCLUDED."desc",
                lat = EXCLUDED.lat,
                lng = EXCLUDED.lng,
                source = EXCLUDED.source,
                timestamp = EXCLUDED.timestamp,
                url = EXCLUDED.url,
                video_url = EXCLUDED.video_url,
                lang = EXCLUDED.lang,
                confidence_score = EXCLUDED.confidence_score,
                confidence_reason = EXCLUDED.confidence_reason,
                observed_facts = EXCLUDED.observed_facts,
                model_inference = EXCLUDED.model_inference,
                video_assessment = EXCLUDED.video_assessment,
                video_confidence = EXCLUDED.video_confidence,
                video_clues = EXCLUDED.video_clues
            """,
            (
                event.get("id"),
                event.get("incident_id"),
                event.get("type"),
                event.get("desc"),
                event.get("lat"),
                event.get("lng"),
                event.get("source"),
                event.get("timestamp"),
                event.get("url"),
                event.get("video_url"),
                event.get("lang"),
                int(event.get("confidence_score", 0)),
                event.get("confidence_reason"),
                json.dumps(event.get("observed_facts", []), ensure_ascii=False),
                json.dumps(event.get("model_inference", []), ensure_ascii=False),
                event.get("video_assessment"),
                event.get("video_confidence"),
                json.dumps(event.get("video_clues", []), ensure_ascii=False),
                utc_now_iso(),
            ),
        )
    _db.commit()
    _m.metrics["db_writes"] += 1


# ── Audit log ──────────────────────────────────────────────────────────────────

def audit_log(action: str, actor: str, role: str, payload: dict, target_id: Optional[str] = None):
    import main as _m
    _db = _m._db
    if _db is None:
        return
    with _db.cursor() as _cur:
        _cur.execute(
            """
            INSERT INTO audit_logs (actor, role, action, target_id, payload_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                actor or "system",
                role or "viewer",
                action,
                target_id,
                json.dumps(payload, ensure_ascii=False),
                utc_now_iso(),
            ),
        )
    _db.commit()


# ── Media analysis persistence ────────────────────────────────────────────────

def persist_media_analysis(event_id: str, data: dict):
    import main as _m
    _db = _m._db
    if _db is None:
        return
    with _db.cursor() as _cur:
        _cur.execute(
            """
            INSERT INTO media_analysis (
                event_id, status, keyframes_json, ocr_snippets_json, stt_snippets_json,
                claim_alignment, credibility_note, transcript_text, transcript_language,
                transcript_error, deepfake_score, deepfake_label, deepfake_error, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO UPDATE SET
                status = EXCLUDED.status,
                keyframes_json = EXCLUDED.keyframes_json,
                ocr_snippets_json = EXCLUDED.ocr_snippets_json,
                stt_snippets_json = EXCLUDED.stt_snippets_json,
                claim_alignment = EXCLUDED.claim_alignment,
                credibility_note = EXCLUDED.credibility_note,
                transcript_text = EXCLUDED.transcript_text,
                transcript_language = EXCLUDED.transcript_language,
                transcript_error = EXCLUDED.transcript_error,
                deepfake_score = EXCLUDED.deepfake_score,
                deepfake_label = EXCLUDED.deepfake_label,
                deepfake_error = EXCLUDED.deepfake_error,
                updated_at = EXCLUDED.updated_at
            """,
            (
                event_id,
                data.get("status", "pending"),
                json.dumps(data.get("keyframes", []), ensure_ascii=False),
                json.dumps(data.get("ocr_snippets", []), ensure_ascii=False),
                json.dumps(data.get("stt_snippets", []), ensure_ascii=False),
                data.get("claim_alignment", "UNVERIFIED_VISUAL"),
                data.get("credibility_note", ""),
                str(data.get("transcript_text", "")),
                str(data.get("transcript_language", "")),
                str(data.get("transcript_error", "")),
                str(data.get("deepfake_score", "")),
                str(data.get("deepfake_label", "")),
                str(data.get("deepfake_error", "")),
                utc_now_iso(),
            ),
        )
    _db.commit()


def get_media_analysis(event_id: str) -> dict:
    import main as _m
    _db = _m._db
    if _db is None:
        return {}
    with _db.cursor() as _cur:
        _cur.execute("SELECT * FROM media_analysis WHERE event_id = %s", (event_id,))
        row = _cur.fetchone()
    if not row:
        return {}
    return {
        "status": row["status"],
        "keyframes": json.loads(row["keyframes_json"] or "[]"),
        "ocr_snippets": json.loads(row["ocr_snippets_json"] or "[]"),
        "stt_snippets": json.loads(row["stt_snippets_json"] or "[]"),
        "claim_alignment": row["claim_alignment"],
        "credibility_note": row["credibility_note"],
        "transcript_text": str(row["transcript_text"] or ""),
        "transcript_language": str(row["transcript_language"] or ""),
        "transcript_error": str(row["transcript_error"] or ""),
        "deepfake_score": str(row["deepfake_score"] or ""),
        "deepfake_label": str(row["deepfake_label"] or ""),
        "deepfake_error": str(row["deepfake_error"] or ""),
        "updated_at": row["updated_at"],
    }


# ── System status ──────────────────────────────────────────────────────────────

def postgres_status() -> dict:
    import v2_store
    try:
        import psycopg  # type: ignore
    except ImportError:
        psycopg = None
    try:
        from config import DATABASE_URL
    except ImportError:
        DATABASE_URL = ""
    return v2_store.postgres_status(DATABASE_URL, psycopg)
