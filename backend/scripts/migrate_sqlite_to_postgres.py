#!/usr/bin/env python3
"""One-shot migration helper: copy events from SQLite to PostgreSQL events_v2."""

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List

import httpx

try:
    import psycopg  # type: ignore
except Exception as e:
    raise SystemExit(f"psycopg missing: {e}")

SQLITE_PATH = os.getenv("OSINT_DB_PATH", "/tmp/osint_nexus.db")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://osint:osint@localhost:5432/osint")
BACKEND_EVENTS_URL = os.getenv("BACKEND_EVENTS_URL", "http://localhost:8000/api/events?limit=1200")


def has_events_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'events' LIMIT 1"
    ).fetchone()
    return bool(row)


def load_from_sqlite(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, type, source, timestamp, lat, lng, desc, observed_facts, model_inference, confidence_score FROM events"
    ).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "type": r["type"],
                "source": r["source"],
                "timestamp": r["timestamp"],
                "lat": r["lat"],
                "lng": r["lng"],
                "desc": r["desc"],
                "observed_facts": json.loads(r["observed_facts"] or "[]"),
                "model_inference": json.loads(r["model_inference"] or "[]"),
                "confidence_score": int(r["confidence_score"] or 0),
            }
        )
    return out


def load_from_api() -> List[Dict[str, Any]]:
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(BACKEND_EVENTS_URL)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                return []
            out: List[Dict[str, Any]] = []
            for e in data:
                if not isinstance(e, dict):
                    continue
                out.append(
                    {
                        "id": e.get("id"),
                        "type": e.get("type"),
                        "source": e.get("source"),
                        "timestamp": e.get("timestamp"),
                        "lat": e.get("lat"),
                        "lng": e.get("lng"),
                        "desc": e.get("desc"),
                        "observed_facts": e.get("observed_facts") if isinstance(e.get("observed_facts"), list) else [],
                        "model_inference": e.get("model_inference") if isinstance(e.get("model_inference"), list) else [],
                        "confidence_score": int(e.get("confidence_score", 0) or 0),
                    }
                )
            return out
    except Exception:
        return []


def main() -> int:
    sq = sqlite3.connect(SQLITE_PATH)
    sq.row_factory = sqlite3.Row
    if has_events_table(sq):
        records = load_from_sqlite(sq)
        source_label = f"sqlite:{SQLITE_PATH}"
    else:
        records = load_from_api()
        source_label = f"api:{BACKEND_EVENTS_URL}"
    if not records:
        print("no rows found to migrate (events table missing/empty and API fallback empty)")
        return 0

    with psycopg.connect(DATABASE_URL) as pg:
        with pg.cursor() as cur:
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

            inserted = 0
            for r in records:
                payload = {
                    "observed_facts": r["observed_facts"],
                    "model_inference": r["model_inference"],
                    "confidence_score": int(r["confidence_score"] or 0),
                    "migrated_at": datetime.utcnow().isoformat(),
                }
                cur.execute(
                    """
                    INSERT INTO events_v2 (id, type, source, timestamp, lat, lng, description, payload_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        r["id"],
                        r["type"],
                        r["source"],
                        r["timestamp"],
                        r["lat"],
                        r["lng"],
                        r["desc"],
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
                inserted += 1

    print(f"migration source: {source_label}")
    print(f"migrated rows attempted: {len(records)}, inserted/checked: {inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
