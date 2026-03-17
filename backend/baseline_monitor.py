"""
EWMA Behavioral Baseline Monitor — anomaly detection for per-source event velocity.

Uses exponentially-weighted moving average (EWMA, span=30 hourly observations) to model
normal ingestion rate per source. Flags z-score anomalies as EARLY_WARNING or CRITICAL.

Design decisions (from Shewhart process control + CUSUM practice):
  - span=30: 30-hour rolling window at hourly granularity — responsive but not noisy
  - z > 2.0 → EARLY_WARNING: monitor closely, may be legitimate escalation
  - z > 3.0 → CRITICAL: possible info op, pipeline failure, or mass-narrative event
  - Spike exclusion: z > 3 observations are excluded from EWMA update to prevent
    crisis periods from contaminating the "normal" baseline
  - 90-observation minimum: ~3.75 days of hourly data before showing any anomaly status.
    Below this, cold-start noise produces false alarms.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger("osint.baseline")

EWMA_SPAN = 30
ALPHA = 2.0 / (EWMA_SPAN + 1)  # ≈ 0.0645

Z_EARLY_WARNING = 2.0
Z_CRITICAL = 3.0

MIN_OBSERVATIONS = 90  # 90 hourly obs ≈ 3.75 days

_CREATE_BASELINE = """
CREATE TABLE IF NOT EXISTS source_baseline (
    source TEXT NOT NULL,
    hour_bucket TIMESTAMPTZ NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source, hour_bucket)
)
"""


def _now_bucket() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0)


def record_event_baseline(source: str, database_url: str, psycopg_mod) -> None:
    """Increment event count for the current hour bucket for this source."""
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return
    bucket = _now_bucket()
    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_BASELINE)
                cur.execute(
                    """
                    INSERT INTO source_baseline (source, hour_bucket, event_count)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (source, hour_bucket) DO UPDATE
                    SET event_count = source_baseline.event_count + 1
                    """,
                    (source, bucket),
                )
    except Exception:
        return


def compute_source_anomaly(
    source: str,
    database_url: str,
    psycopg_mod,
    lookback_days: int = 90,
) -> Dict[str, Any]:
    """
    Compute EWMA baseline and z-score for a source.
    Returns anomaly status dict with status, z_score, ewma, current_count.
    """
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return {"status": "UNAVAILABLE", "source": source}

    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_BASELINE)
                cur.execute(
                    """
                    SELECT hour_bucket, event_count
                    FROM source_baseline
                    WHERE source = %s
                      AND hour_bucket >= NOW() - make_interval(days => %s)
                    ORDER BY hour_bucket ASC
                    """,
                    (source, lookback_days),
                )
                rows = cur.fetchall()
    except Exception:
        return {"status": "ERROR", "source": source}

    if len(rows) < MIN_OBSERVATIONS:
        return {
            "status": "INSUFFICIENT_BASELINE",
            "source": source,
            "observations": len(rows),
            "required": MIN_OBSERVATIONS,
        }

    counts = [float(r[1]) for r in rows]

    # Compute EWMA and variance with spike exclusion
    ewma = counts[0]
    ewma_var = 0.0
    excluded = 0

    for count in counts[1:]:
        # Exclude spikes from baseline update (prevents crisis contamination)
        if ewma_var > 0:
            sd = math.sqrt(ewma_var)
            z = abs(count - ewma) / sd if sd > 0 else 0.0
            if z > Z_CRITICAL:
                excluded += 1
                continue
        ewma = ALPHA * count + (1 - ALPHA) * ewma
        # Welford-style variance update for EWMA
        ewma_var = (1 - ALPHA) * (ewma_var + ALPHA * (count - ewma) ** 2)

    # Find current hour count
    current_bucket = _now_bucket()
    current_count = 0
    for r in rows:
        rb = r[0]
        rb_norm = rb.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc) if hasattr(rb, "replace") else rb
        if rb_norm == current_bucket:
            current_count = int(r[1])
            break

    sd = math.sqrt(ewma_var) if ewma_var > 0 else 1.0
    z_score = (current_count - ewma) / sd if sd > 0 else 0.0

    if z_score >= Z_CRITICAL:
        status = "CRITICAL"
    elif z_score >= Z_EARLY_WARNING:
        status = "EARLY_WARNING"
    else:
        status = "NORMAL"

    return {
        "status": status,
        "source": source,
        "current_count": current_count,
        "ewma": round(ewma, 2),
        "z_score": round(z_score, 2),
        "observations": len(rows),
        "excluded_spikes": excluded,
    }


def get_all_source_anomalies(database_url: str, psycopg_mod) -> List[Dict[str, Any]]:
    """Get anomaly status for all sources with sufficient baseline data."""
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return []
    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_BASELINE)
                cur.execute("SELECT DISTINCT source FROM source_baseline")
                sources = [r[0] for r in cur.fetchall()]
    except Exception:
        return []

    results = []
    for source in sources:
        anomaly = compute_source_anomaly(source, database_url, psycopg_mod)
        if anomaly.get("status") not in ("INSUFFICIENT_BASELINE", "UNAVAILABLE", "ERROR"):
            results.append(anomaly)

    results.sort(key=lambda x: abs(x.get("z_score", 0)), reverse=True)
    return results
