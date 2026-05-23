"""
calibration_engine.py — Analyst Calibration Engine (Feature E).

Records falsifiable analyst judgments and resolves them against ground truth,
producing Brier scores that measure how well-calibrated each analyst is.

Valid judgment types (falsifiable):
  source_rating     — star rating ≥4 on an event; implied claim "this source is accurate"
  hypothesis_status — CONFIRMED/REFUTED status change on a hypothesis

Resolution windows: 24h and 7d.

Ground truth hierarchy (strongest first):
  1. Sensor corroboration: NASA FIRMS / ADS-B / Red Alert event within 50km + same type in window
  2. Cross-source corroboration: corroborating_sources count ≥2 in events_v2
  3. No match: outcome = 0.0 (prediction failed)
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("osint.calibration")

# Sensor sources treated as ground truth
_SENSOR_SOURCES = {"NASA FIRMS", "ADS-B Exchange", "ADSB.lol", "Red Alert", "AISStream", "FR24-MIL"}

# Probability mapping for star ratings
_RATING_PROB = {4: 0.75, 5: 0.90}

# Probability mapping for hypothesis status changes
_HYPOTHESIS_PROB = {"CONFIRMED": 0.90, "REFUTED": 0.10}

# Brier score baseline: always predict 0.5
_BRIER_BASELINE = 0.25


# ---------------------------------------------------------------------------
# Core math — no DB access
# ---------------------------------------------------------------------------

def brier_score(stated_prob: float, outcome: float) -> float:
    return (stated_prob - outcome) ** 2


def compute_brier_stats(judgments: List[Dict[str, Any]], outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute aggregate Brier score stats from judgment + outcome dicts.
    Both lists must have matching judgment_id keys.
    Returns mean_brier, skill_score, by_judgment_type breakdown.
    """
    outcome_map: Dict[int, float] = {o["judgment_id"]: o["outcome_prob"] for o in outcomes}
    by_type: Dict[str, List[float]] = {}
    scores: List[float] = []

    for j in judgments:
        jid = j["id"]
        if jid not in outcome_map:
            continue
        bs = brier_score(j["stated_prob"], outcome_map[jid])
        scores.append(bs)
        jtype = j.get("judgment_type", "unknown")
        by_type.setdefault(jtype, []).append(bs)

    n = len(scores)
    if n == 0:
        return {"total_scored": 0, "mean_brier": None, "skill_score": None, "by_judgment_type": {}}

    mean_bs = sum(scores) / n
    skill = 1.0 - (mean_bs / _BRIER_BASELINE)

    by_type_summary = {
        t: {"n": len(blist), "mean_brier": round(sum(blist) / len(blist), 4)}
        for t, blist in by_type.items()
    }

    return {
        "total_scored": n,
        "mean_brier": round(mean_bs, 4),
        "skill_score": round(skill, 4),
        "by_judgment_type": by_type_summary,
    }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def record_judgment(
    analyst_id: str,
    judgment_type: str,
    stated_prob: float,
    judgment_text: str,
    database_url: str,
    psycopg_mod,
    event_id: Optional[str] = None,
    hypothesis_id: Optional[str] = None,
) -> Optional[int]:
    """
    Insert a new analyst judgment row. Returns the new row id, or None on failure.
    resolve_at_24h and resolve_at_7d are set automatically.
    """
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return None
    now = datetime.now(timezone.utc)
    resolve_24h = now + timedelta(hours=24)
    resolve_7d = now + timedelta(days=7)
    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analyst_judgments
                        (analyst_id, judgment_type, event_id, hypothesis_id,
                         stated_prob, judgment_text, created_at, resolve_at_24h, resolve_at_7d)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        analyst_id, judgment_type,
                        event_id, hypothesis_id,
                        round(float(stated_prob), 4),
                        judgment_text[:500],
                        now, resolve_24h, resolve_7d,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return row[0] if row else None
    except Exception as exc:
        logger.warning("[calibration] record_judgment failed: %s", exc)
        return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _resolve_single(judgment: dict, cur) -> Optional[Dict[str, Any]]:
    """
    Attempt ground truth resolution for one judgment.
    Returns outcome dict or None if no ground truth available yet.
    """
    jid = judgment["id"]
    event_id = judgment.get("event_id")
    stated_prob = float(judgment["stated_prob"])
    window = judgment["_window"]  # '24h' or '7d'
    created_at = judgment["created_at"]
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    resolve_at = created_at + timedelta(hours=24) if window == "24h" else created_at + timedelta(days=7)

    outcome: Optional[float] = None
    ground_truth_source = "no_matching_event"

    if event_id:
        # Fetch the original event's lat/lng and type
        cur.execute(
            "SELECT lat, lng, type FROM events_v2 WHERE id = %s LIMIT 1",
            (event_id,)
        )
        orig = cur.fetchone()
        if orig:
            orig_lat = orig[0]
            orig_lng = orig[1]

            # Check sensor corroboration within window + 50km
            if orig_lat is not None and orig_lng is not None:
                window_end = resolve_at
                window_start = created_at
                cur.execute(
                    """
                    SELECT source, lat, lng FROM events_v2
                    WHERE source = ANY(%s)
                      AND timestamp >= %s AND timestamp <= %s
                    LIMIT 200
                    """,
                    (list(_SENSOR_SOURCES), window_start.isoformat(), window_end.isoformat()),
                )
                sensor_events = cur.fetchall()
                for se in sensor_events:
                    s_lat, s_lng = se[1], se[2]
                    if s_lat is not None and s_lng is not None:
                        if _haversine_km(orig_lat, orig_lng, float(s_lat), float(s_lng)) <= 50.0:
                            outcome = 1.0
                            ground_truth_source = "sensor_corroboration"
                            break

            # Fallback: cross-source corroboration count in original event
            if outcome is None:
                cur.execute(
                    "SELECT payload_json FROM events_v2 WHERE id = %s LIMIT 1",
                    (event_id,)
                )
                payload_row = cur.fetchone()
                if payload_row and payload_row[0]:
                    import json
                    try:
                        payload = json.loads(payload_row[0]) if isinstance(payload_row[0], str) else payload_row[0]
                        corr = payload.get("corroborating_sources") or []
                        if len(corr) >= 2:
                            outcome = 0.5
                            ground_truth_source = "cross_source_corroboration"
                    except Exception:
                        pass

    if outcome is None:
        # No ground truth found — treat as failed prediction only after window closed
        now = datetime.now(timezone.utc)
        if now < resolve_at:
            return None  # window not yet closed
        outcome = 0.0
        ground_truth_source = "no_matching_event"

    bs = brier_score(stated_prob, outcome)
    return {
        "judgment_id": jid,
        "resolution_window": window,
        "outcome_prob": outcome,
        "brier_score": round(bs, 6),
        "ground_truth_source": ground_truth_source,
    }


def resolve_judgments(window: str, database_url: str, psycopg_mod) -> int:
    """
    Resolve pending analyst judgments for the given window ('24h' or '7d').
    Returns count of newly resolved judgments.
    """
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return 0
    if window not in ("24h", "7d"):
        return 0

    resolved_col = "resolve_at_24h" if window == "24h" else "resolve_at_7d"
    resolved_count = 0

    try:
        with psycopg_mod.connect(database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT j.id, j.analyst_id, j.judgment_type, j.event_id,
                           j.stated_prob, j.judgment_text, j.created_at
                    FROM analyst_judgments j
                    WHERE j.{resolved_col} <= NOW()
                      AND j.id NOT IN (
                          SELECT judgment_id FROM judgment_outcomes
                          WHERE resolution_window = %s
                      )
                    LIMIT 200
                    """,
                    (window,),
                )
                rows = cur.fetchall()

                for row in rows:
                    judgment = {
                        "id": row[0], "analyst_id": row[1], "judgment_type": row[2],
                        "event_id": row[3], "stated_prob": row[4], "judgment_text": row[5],
                        "created_at": row[6], "_window": window,
                    }
                    result = _resolve_single(judgment, cur)
                    if result is None:
                        continue

                    cur.execute(
                        """
                        INSERT INTO judgment_outcomes
                            (judgment_id, resolution_window, outcome_prob, brier_score,
                             ground_truth_source)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            result["judgment_id"], result["resolution_window"],
                            result["outcome_prob"], result["brier_score"],
                            result["ground_truth_source"],
                        ),
                    )
                    resolved_count += 1

            conn.commit()
    except Exception as exc:
        logger.warning("[calibration] resolve_judgments(%s) failed: %s", window, exc)

    return resolved_count


# ---------------------------------------------------------------------------
# Stats query
# ---------------------------------------------------------------------------

def get_calibration_stats(
    analyst_id: Optional[str],
    database_url: str,
    psycopg_mod,
) -> Dict[str, Any]:
    """
    Returns calibration stats for an analyst (or all analysts if analyst_id is None).
    """
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return {"error": "database unavailable"}

    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                where = "WHERE j.analyst_id = %s" if analyst_id else ""
                params = (analyst_id,) if analyst_id else ()

                cur.execute(
                    f"""
                    SELECT
                        j.analyst_id,
                        COUNT(DISTINCT j.id) AS total_judgments,
                        COUNT(DISTINCT CASE WHEN jo.resolution_window = '24h' THEN jo.id END) AS resolved_24h,
                        COUNT(DISTINCT CASE WHEN jo.resolution_window = '7d' THEN jo.id END) AS resolved_7d,
                        AVG(CASE WHEN jo.resolution_window = '24h' THEN jo.brier_score END) AS mean_brier_24h,
                        AVG(CASE WHEN jo.resolution_window = '7d' THEN jo.brier_score END) AS mean_brier_7d
                    FROM analyst_judgments j
                    LEFT JOIN judgment_outcomes jo ON jo.judgment_id = j.id
                    {where}
                    GROUP BY j.analyst_id
                    ORDER BY j.analyst_id
                    """,
                    params,
                )
                rows = cur.fetchall()

                # Per-type breakdown
                cur.execute(
                    f"""
                    SELECT j.judgment_type,
                           COUNT(jo.id) AS n,
                           AVG(jo.brier_score) AS mean_brier
                    FROM analyst_judgments j
                    JOIN judgment_outcomes jo ON jo.judgment_id = j.id
                    {where}
                    GROUP BY j.judgment_type
                    """,
                    params,
                )
                type_rows = cur.fetchall()

                # Calibration curve buckets
                cur.execute(
                    f"""
                    SELECT
                        ROUND(j.stated_prob::numeric, 1) AS prob_bucket,
                        AVG(jo.outcome_prob) AS actual_rate,
                        COUNT(*) AS n
                    FROM analyst_judgments j
                    JOIN judgment_outcomes jo ON jo.judgment_id = j.id
                    {where}
                    GROUP BY ROUND(j.stated_prob::numeric, 1)
                    ORDER BY prob_bucket
                    """,
                    params,
                )
                curve_rows = cur.fetchall()

        def _skill(mean_bs):
            if mean_bs is None:
                return None
            return round(1.0 - (float(mean_bs) / _BRIER_BASELINE), 4)

        if not rows:
            return {
                "analyst_id": analyst_id,
                "total_judgments": 0,
                "resolved_24h": 0,
                "resolved_7d": 0,
                "mean_brier_24h": None,
                "mean_brier_7d": None,
                "skill_score_24h": None,
                "skill_score_7d": None,
                "by_judgment_type": {},
                "calibration_curve": [],
            }

        # If no analyst_id filter, aggregate across all analysts
        if analyst_id is None:
            total_j = sum(r[1] for r in rows)
            total_24h = sum(r[2] for r in rows)
            total_7d = sum(r[3] for r in rows)
            briers_24h = [float(r[4]) for r in rows if r[4] is not None]
            briers_7d = [float(r[5]) for r in rows if r[5] is not None]
            mean_24h = sum(briers_24h) / len(briers_24h) if briers_24h else None
            mean_7d = sum(briers_7d) / len(briers_7d) if briers_7d else None
            row_out = {"analyst_id": "all", "total_judgments": total_j,
                       "resolved_24h": total_24h, "resolved_7d": total_7d,
                       "mean_brier_24h": round(mean_24h, 4) if mean_24h else None,
                       "mean_brier_7d": round(mean_7d, 4) if mean_7d else None}
        else:
            r = rows[0]
            row_out = {
                "analyst_id": r[0],
                "total_judgments": r[1],
                "resolved_24h": r[2],
                "resolved_7d": r[3],
                "mean_brier_24h": round(float(r[4]), 4) if r[4] is not None else None,
                "mean_brier_7d": round(float(r[5]), 4) if r[5] is not None else None,
            }

        row_out["skill_score_24h"] = _skill(row_out["mean_brier_24h"])
        row_out["skill_score_7d"] = _skill(row_out["mean_brier_7d"])
        row_out["by_judgment_type"] = {
            tr[0]: {"n": tr[1], "mean_brier": round(float(tr[2]), 4) if tr[2] else None}
            for tr in type_rows
        }
        row_out["calibration_curve"] = [
            {"stated_prob_bucket": float(cr[0]), "actual_outcome_rate": round(float(cr[1]), 4), "n": cr[2]}
            for cr in curve_rows
        ]

        return row_out

    except Exception as exc:
        logger.warning("[calibration] get_calibration_stats failed: %s", exc)
        return {"error": str(exc)}
