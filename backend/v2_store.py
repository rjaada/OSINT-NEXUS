import json
from typing import Any, Callable, List, Optional, Sequence


def postgres_status(database_url: str, psycopg_mod) -> dict:
    configured = database_url.startswith("postgres")
    if not configured:
        return {"configured": False, "connected": False, "events_count": None, "error": "DATABASE_URL not set to postgres"}
    if psycopg_mod is None:
        return {"configured": True, "connected": False, "events_count": None, "error": "psycopg unavailable"}
    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events_v2 (
                        id TEXT PRIMARY KEY,
                        type TEXT,
                        source TEXT,
                        timestamp TIMESTAMPTZ,
                        lat DOUBLE PRECISION,
                        lng DOUBLE PRECISION,
                        description TEXT,
                        payload_json JSONB
                    )
                    """
                )
                cur.execute("SELECT COUNT(*) FROM events_v2")
                count = int(cur.fetchone()[0])
                return {"configured": True, "connected": True, "events_count": count, "error": None}
    except Exception as e:
        return {"configured": True, "connected": False, "events_count": None, "error": str(e)}


def persist_event_v2_pg(
    event: dict,
    database_url: str,
    psycopg_mod,
    extract_source: Callable[[dict], str],
    now_iso: Callable[[], str],
) -> None:
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return
    try:
        payload = {
            "incident_id": event.get("incident_id"),
            "url": event.get("url"),
            "video_url": event.get("video_url"),
            "lang": event.get("lang"),
            "insufficient_evidence": bool(event.get("insufficient_evidence", False)),
            "observed_facts": event.get("observed_facts", []),
            "model_inference": event.get("model_inference", []),
            "confidence_score": int(event.get("confidence_score", 0) or 0),
            "confidence_reason": event.get("confidence_reason"),
            "video_assessment": event.get("video_assessment"),
            "video_confidence": event.get("video_confidence"),
            "video_clues": event.get("video_clues", []),
            "source": extract_source(event),
            "updated_at": now_iso(),
        }
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events_v2 (
                        id TEXT PRIMARY KEY,
                        type TEXT,
                        source TEXT,
                        timestamp TIMESTAMPTZ,
                        lat DOUBLE PRECISION,
                        lng DOUBLE PRECISION,
                        description TEXT,
                        payload_json JSONB
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO events_v2 (id, type, source, timestamp, lat, lng, description, payload_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        type = EXCLUDED.type,
                        source = EXCLUDED.source,
                        timestamp = EXCLUDED.timestamp,
                        lat = EXCLUDED.lat,
                        lng = EXCLUDED.lng,
                        description = EXCLUDED.description,
                        payload_json = EXCLUDED.payload_json
                    """,
                    (
                        str(event.get("id")),
                        str(event.get("type", "CLASH")),
                        extract_source(event),
                        str(event.get("timestamp") or now_iso()),
                        float(event.get("lat", 0.0)),
                        float(event.get("lng", 0.0)),
                        str(event.get("desc", "")),
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
    except Exception:
        return


def _decode_pg_event(row: Any, now_iso: Callable[[], str]) -> dict:
    payload = row[7] if isinstance(row[7], dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    ts = row[3]
    if ts is None:
        ts_iso = now_iso()
    else:
        ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    return {
        "id": row[0],
        "type": row[1] or "CLASH",
        "source": row[2] or payload.get("source") or "Unknown",
        "timestamp": ts_iso,
        "lat": float(row[4] or 0.0),
        "lng": float(row[5] or 0.0),
        "desc": row[6] or "",
        "incident_id": payload.get("incident_id"),
        "url": payload.get("url"),
        "video_url": payload.get("video_url"),
        "lang": payload.get("lang"),
        "insufficient_evidence": bool(payload.get("insufficient_evidence", False)),
        "observed_facts": payload.get("observed_facts", []),
        "model_inference": payload.get("model_inference", []),
        "confidence_score": int(payload.get("confidence_score", 0) or 0),
        "confidence_reason": payload.get("confidence_reason"),
        "video_assessment": payload.get("video_assessment"),
        "video_confidence": payload.get("video_confidence"),
        "video_clues": payload.get("video_clues", []),
    }


_CREATE_AI_REPORTS = """
CREATE TABLE IF NOT EXISTS ai_reports (
    id SERIAL PRIMARY KEY,
    report_type TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    event_fp TEXT NOT NULL DEFAULT '',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""
_IDX_AI_REPORTS = "CREATE INDEX IF NOT EXISTS idx_ai_reports_type_ts ON ai_reports(report_type, generated_at DESC)"


def persist_ai_report_pg(
    report_type: str,
    report: dict,
    event_fp: str,
    database_url: str,
    psycopg_mod,
) -> None:
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return
    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_AI_REPORTS)
                cur.execute(_IDX_AI_REPORTS)
                cur.execute(
                    """
                    INSERT INTO ai_reports (report_type, payload_json, event_fp, generated_at)
                    VALUES (%s, %s::jsonb, %s, NOW())
                    """,
                    (report_type, json.dumps(report, ensure_ascii=False), event_fp),
                )
    except Exception:
        return


def load_latest_ai_report_pg(
    report_type: str,
    database_url: str,
    psycopg_mod,
) -> Optional[dict]:
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return None
    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_AI_REPORTS)
                cur.execute(
                    """
                    SELECT payload_json, event_fp, generated_at
                    FROM ai_reports
                    WHERE report_type = %s
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """,
                    (report_type,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                payload = row[0] if isinstance(row[0], dict) else {}
                return {
                    "report": payload,
                    "event_fp": row[1] or "",
                    "generated_at_ts": row[2].timestamp() if hasattr(row[2], "timestamp") else 0.0,
                }
    except Exception:
        return None


def fetch_ai_report_history_pg(
    report_type: str,
    limit: int,
    database_url: str,
    psycopg_mod,
) -> List[dict]:
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return []
    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_AI_REPORTS)
                cur.execute(
                    """
                    SELECT id, payload_json, event_fp, generated_at
                    FROM ai_reports
                    WHERE report_type = %s
                    ORDER BY generated_at DESC
                    LIMIT %s
                    """,
                    (report_type, limit),
                )
                rows = cur.fetchall()
                results = []
                for r in rows:
                    payload = r[1] if isinstance(r[1], dict) else {}
                    ts = r[3]
                    results.append({
                        "id": r[0],
                        "report_type": report_type,
                        "generated_at": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                        **payload,
                    })
                return results
    except Exception:
        return []


def fetch_recent_v2_events_pg(
    database_url: str,
    psycopg_mod,
    now_iso: Callable[[], str],
    limit: int = 200,
    source_whitelist: Optional[Sequence[str]] = None,
    type_whitelist: Optional[Sequence[str]] = None,
) -> List[dict]:
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return []
    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                query = [
                    "SELECT id, type, source, timestamp, lat, lng, description, payload_json",
                    "FROM events_v2",
                    "WHERE 1=1",
                ]
                params: List[Any] = []
                if source_whitelist:
                    query.append("AND source = ANY(%s)")
                    params.append(list(source_whitelist))
                if type_whitelist:
                    query.append("AND type = ANY(%s)")
                    params.append(list(type_whitelist))
                query.append("ORDER BY timestamp DESC")
                query.append("LIMIT %s")
                params.append(limit)
                cur.execute("\n".join(query), tuple(params))
                rows = cur.fetchall()
                return [_decode_pg_event(r, now_iso=now_iso) for r in rows]
    except Exception:
        return []
