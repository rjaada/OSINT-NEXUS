"""Analyst-only investigations with immutable, owner-scoped evidence snapshots."""
import asyncio
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from investigations import analyze, query_terms, select_evidence
from routes_command import _require_analyst_or_admin

router = APIRouter()
_slots = threading.BoundedSemaphore(2)


class InvestigationInput(BaseModel):
    question: str = Field(min_length=8, max_length=600)
    days: int = Field(default=7, ge=1, le=30)


def connection():
    import main
    return main.psycopg.connect(main.DATABASE_URL, connect_timeout=5, options='-c statement_timeout=10000')


def run_investigation(body, owner):
    if not _slots.acquire(blocking=False):
        raise HTTPException(429, 'Two investigations are already running. Try again shortly.')
    try:
        import v2_store
        terms = query_terms(body.question)
        if not terms:
            raise HTTPException(422, 'Include a specific place, actor, or event in your question.')
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=body.days)
        with connection() as conn:
            rows = conn.execute('''SELECT id, type, source, timestamp, lat, lng, description, payload_json, notes
                FROM events_v2 WHERE timestamp >= %s AND timestamp <= %s
                AND description ILIKE ANY(%s) ORDER BY timestamp DESC LIMIT 1000''',
                (start.isoformat(), end.isoformat(), ['%' + t + '%' for t in terms])).fetchall()
        events = [v2_store._decode_pg_event(row, now_iso=lambda: end.isoformat()) for row in rows]
        evidence = select_evidence(events, terms)
        report = {**analyze(body.question, evidence), 'question': body.question.strip(), 'evidence': evidence,
                  'window_start': start.isoformat(), 'window_end': end.isoformat(),
                  'retrieval': {'terms': terms, 'candidate_count': len(rows), 'candidate_limit': 1000, 'evidence_limit': 24,
                                'scope': 'Keyword matches in stored event descriptions; this is not an exhaustive search of external sources.'}}
        identifier = str(uuid.uuid4())
        with connection() as conn:
            conn.execute('INSERT INTO investigations (id, owner, question, report) VALUES (%s, %s, %s, %s::jsonb)',
                         (identifier, owner, body.question.strip(), json.dumps(report)))
        return {'id': identifier, **report}
    finally:
        _slots.release()


@router.post('/api/v2/investigations')
async def create(body: InvestigationInput, request: Request, user=Depends(_require_analyst_or_admin)):
    import main
    main.enforce_csrf(request)
    try:
        return await asyncio.to_thread(run_investigation, body, user['username'])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Investigation could not be saved or retrieved. Please retry.') from None


def read_saved(owner, identifier=None):
    with connection() as conn:
        if identifier:
            row = conn.execute('SELECT report FROM investigations WHERE id = %s AND owner = %s', (str(identifier), owner)).fetchone()
            if not row:
                raise HTTPException(404, 'Investigation not found')
            return {'id': str(identifier), **row[0]}
        rows = conn.execute('SELECT id, question, created_at FROM investigations WHERE owner = %s ORDER BY created_at DESC LIMIT 50', (owner,)).fetchall()
        return [{'id': row[0], 'question': row[1], 'created_at': row[2].isoformat()} for row in rows]


@router.get('/api/v2/investigations')
async def history(user=Depends(_require_analyst_or_admin)):
    return await asyncio.to_thread(read_saved, user['username'])


@router.get('/api/v2/investigations/{identifier}')
async def detail(identifier: uuid.UUID, user=Depends(_require_analyst_or_admin)):
    return await asyncio.to_thread(read_saved, user['username'], identifier)
