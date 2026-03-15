"""
Prediction Tracker — Layer 4 self-learning.

Stores watch items from each SITREP, checks if they materialized,
scores predictions, and exposes accuracy stats for confidence calibration.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

logger = logging.getLogger("osint.prediction_tracker")

_CREATE_PREDICTIONS = """
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id SERIAL PRIMARY KEY,
    sitrep_id TEXT NOT NULL,
    watch_item TEXT NOT NULL,
    timeframe_hours INTEGER NOT NULL DEFAULT 48,
    expected_by TIMESTAMPTZ NOT NULL,
    outcome TEXT NOT NULL DEFAULT 'pending',
    matched_event_id TEXT,
    scored_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""
_IDX_PREDICTIONS = "CREATE INDEX IF NOT EXISTS idx_pred_expected ON prediction_outcomes(expected_by, outcome)"


def _parse_timeframe_hours(timeframe_str: str) -> int:
    """Convert 'within 24 hours', 'within 3 days' etc. to hours."""
    s = str(timeframe_str).lower()
    try:
        if "hour" in s:
            for token in s.split():
                if token.isdigit():
                    return int(token)
        if "day" in s:
            for token in s.split():
                if token.isdigit():
                    return int(token) * 24
    except Exception:
        pass
    return 48  # default


def store_watch_items(
    sitrep_id: str,
    watch_items: List[dict],
    database_url: str,
    psycopg_mod: Any,
) -> None:
    """Persist watch items from a newly generated SITREP."""
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return
    if not watch_items:
        return
    try:
        now = datetime.now(timezone.utc)
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_PREDICTIONS)
                cur.execute(_IDX_PREDICTIONS)
                for item in watch_items:
                    hours = _parse_timeframe_hours(item.get("timeframe", "48 hours"))
                    expected_by = now + timedelta(hours=hours)
                    cur.execute(
                        """
                        INSERT INTO prediction_outcomes
                          (sitrep_id, watch_item, timeframe_hours, expected_by, outcome, created_at)
                        VALUES (%s, %s, %s, %s, 'pending', NOW())
                        """,
                        (sitrep_id, str(item.get("item", ""))[:400], hours, expected_by),
                    )
    except Exception as exc:
        logger.warning("[PT] store_watch_items failed: %s", exc)


def score_pending_predictions(
    recent_events: List[dict],
    database_url: str,
    psycopg_mod: Any,
) -> int:
    """
    For each pending prediction whose expected_by has passed,
    check if any recent event matches the watch item keywords.
    Mark as 'correct', 'partial', or 'incorrect'.
    Returns number of predictions scored.
    """
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return 0

    scored = 0
    now = datetime.now(timezone.utc)

    # Build a searchable blob from recent events
    event_text = " ".join(
        str(e.get("desc") or "") + " " + str(e.get("type") or "")
        for e in recent_events
    ).lower()

    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_PREDICTIONS)
                # Fetch pending predictions past their expected_by
                cur.execute(
                    """
                    SELECT id, watch_item, timeframe_hours
                    FROM prediction_outcomes
                    WHERE outcome = 'pending' AND expected_by <= %s
                    LIMIT 50
                    """,
                    (now,),
                )
                rows = cur.fetchall()

                for row in rows:
                    pred_id, watch_item, _ = row
                    # Score: how many key words from the watch item appear in recent events?
                    keywords = [w for w in watch_item.lower().split() if len(w) > 4]
                    if not keywords:
                        outcome = "incorrect"
                    else:
                        matches = sum(1 for kw in keywords if kw in event_text)
                        ratio = matches / len(keywords)
                        if ratio >= 0.6:
                            outcome = "correct"
                        elif ratio >= 0.3:
                            outcome = "partial"
                        else:
                            outcome = "incorrect"

                    cur.execute(
                        """
                        UPDATE prediction_outcomes
                        SET outcome = %s, scored_at = NOW()
                        WHERE id = %s
                        """,
                        (outcome, pred_id),
                    )
                    scored += 1

    except Exception as exc:
        logger.warning("[PT] score_pending_predictions failed: %s", exc)

    return scored


def fetch_accuracy_stats(
    database_url: str,
    psycopg_mod: Any,
    limit_days: int = 30,
) -> dict:
    """Return accuracy stats for the last N days."""
    empty = {"total": 0, "correct": 0, "partial": 0, "incorrect": 0, "pending": 0, "accuracy_pct": None}
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return empty
    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_PREDICTIONS)
                cur.execute(
                    """
                    SELECT outcome, COUNT(*) FROM prediction_outcomes
                    WHERE created_at >= NOW() - INTERVAL '%s days'
                    GROUP BY outcome
                    """,
                    (limit_days,),
                )
                rows = cur.fetchall()
                counts = {r[0]: int(r[1]) for r in rows}
                total = sum(counts.values())
                correct = counts.get("correct", 0)
                partial = counts.get("partial", 0)
                incorrect = counts.get("incorrect", 0)
                pending = counts.get("pending", 0)
                scored = correct + partial + incorrect
                accuracy = round((correct + 0.5 * partial) / scored * 100, 1) if scored > 0 else None
                return {
                    "total": total,
                    "correct": correct,
                    "partial": partial,
                    "incorrect": incorrect,
                    "pending": pending,
                    "accuracy_pct": accuracy,
                    "scored": scored,
                    "window_days": limit_days,
                }
    except Exception as exc:
        logger.warning("[PT] fetch_accuracy_stats failed: %s", exc)
        return empty
