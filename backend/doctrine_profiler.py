"""
doctrine_profiler.py — Behavioral Doctrine Profiling (Feature A).

Tracks per-actor behavioral baselines using EWMA and flags doctrine deviations
when observed feature values exceed historical norms by z > 2.0.

Matches baseline_monitor.py pattern: ALPHA=2/(30+1), MIN_OBSERVATIONS=90.

Features tracked per actor per theater per 1-hour bucket:
  - strike_rate              events/hour where type in (STRIKE, CRITICAL)
  - movement_rate            events/hour where type == MOVEMENT
  - civilian_targeting_rate  proportion of events with civilian_targeting=True
  - remote_violence_share    proportion where acled_event_type == Explosions/Remote violence
  - geo_dispersion_km        avg haversine distance from actor's centroid (0.0 if no coords)
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("osint.doctrine")

# ---------------------------------------------------------------------------
# Constants — match baseline_monitor.py exactly
# ---------------------------------------------------------------------------

DOCTRINE_ACTORS = {"IDF", "Hamas", "Hezbollah", "Houthis", "Russia", "Ukraine"}

EWMA_SPAN = 30
ALPHA = 2.0 / (EWMA_SPAN + 1)   # ≈ 0.0645 — same as baseline_monitor.py

Z_EARLY_WARNING = 2.0
Z_CRITICAL = 3.0

MIN_OBSERVATIONS = 90   # cold-start guard: ~3.75 days of hourly data

# ---------------------------------------------------------------------------
# Actor alias table — maps surface forms to canonical names
# ---------------------------------------------------------------------------

_ACTOR_ALIASES: Dict[str, str] = {
    # IDF
    "idf": "IDF",
    "israeli defense forces": "IDF",
    "israeli army": "IDF",
    "israel defense forces": "IDF",
    "zahal": "IDF",
    "israel air force": "IDF",
    "iaf": "IDF",
    # Hamas
    "hamas": "Hamas",
    "al-qassam": "Hamas",
    "qassam": "Hamas",
    "izz ad-din al-qassam": "Hamas",
    "hamas military wing": "Hamas",
    # Hezbollah
    "hezbollah": "Hezbollah",
    "hizbollah": "Hezbollah",
    "hizballah": "Hezbollah",
    "hizb allah": "Hezbollah",
    "islamic resistance": "Hezbollah",
    "lebanese hezbollah": "Hezbollah",
    # Houthis
    "houthis": "Houthis",
    "houthi": "Houthis",
    "ansar allah": "Houthis",
    "ansarallah": "Houthis",
    "yemen armed forces": "Houthis",
    # Russia
    "russia": "Russia",
    "russian army": "Russia",
    "russian forces": "Russia",
    "russian armed forces": "Russia",
    "vzs": "Russia",
    "vks": "Russia",
    "russian air force": "Russia",
    # Ukraine
    "ukraine": "Ukraine",
    "ukrainian army": "Ukraine",
    "ukrainian forces": "Ukraine",
    "ukrainian armed forces": "Ukraine",
    "zsu": "Ukraine",
    "afp ukraine": "Ukraine",
}


def extract_primary_actor(event: dict) -> Optional[str]:
    """
    Scan desc, observed_facts, model_inference for a known DOCTRINE_ACTORS alias.
    Returns canonical actor name or None.
    """
    text_parts: List[str] = []

    desc = event.get("desc") or event.get("description") or ""
    if desc:
        text_parts.append(str(desc).lower())

    facts = event.get("observed_facts") or []
    if isinstance(facts, list):
        text_parts.extend(str(f).lower() for f in facts)
    elif isinstance(facts, str):
        text_parts.append(facts.lower())

    inferences = event.get("model_inference") or []
    if isinstance(inferences, list):
        text_parts.extend(str(i).lower() for i in inferences)
    elif isinstance(inferences, str):
        text_parts.append(inferences.lower())

    combined = " ".join(text_parts)

    # Longest-match first to avoid "hamas" matching inside "anti-hamas"
    for alias in sorted(_ACTOR_ALIASES.keys(), key=len, reverse=True):
        if alias in combined:
            return _ACTOR_ALIASES[alias]

    return None


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

_STRIKE_TYPES = {"STRIKE", "CRITICAL"}
_REMOTE_VIOLENCE_LABEL = "Explosions/Remote violence"


def extract_doctrine_features(event: dict) -> Dict[str, float]:
    """
    Return a dict of feature_name → observation value for this single event.
    All values are in [0.0, 1.0] or raw count (strike_rate, movement_rate).
    geo_dispersion_km is always 0.0 here (per-event snapshot; aggregated in DB).
    """
    etype = str(event.get("type") or "").upper()
    acled_type = str(event.get("acled_event_type") or "")
    civilian = bool(event.get("civilian_targeting", False))

    return {
        "strike_rate": 1.0 if etype in _STRIKE_TYPES else 0.0,
        "movement_rate": 1.0 if etype == "MOVEMENT" else 0.0,
        "civilian_targeting_rate": 1.0 if civilian else 0.0,
        "remote_violence_share": 1.0 if acled_type == _REMOTE_VIOLENCE_LABEL else 0.0,
        "geo_dispersion_km": 0.0,  # populated via aggregation; 0 for single-event
    }


# ---------------------------------------------------------------------------
# Deviation scoring — pure math, no DB access
# ---------------------------------------------------------------------------

def score_doctrine_deviation(
    actor: str,
    theater: str,
    feature_name: str,
    observation_value: float,
    prior_mean: float,
    prior_var: float,
    alpha: float,
    obs_count: int,
) -> Optional[Dict[str, Any]]:
    """
    Score a single observation against the EWMA baseline.

    Guards:
      - obs_count < MIN_OBSERVATIONS → return None (cold start)
      - sigma floor: sqrt(max(variance, 0.0001)) for count features,
        0.05 floor for proportion features (0-1 range)

    Returns dict with z_score, deviation_level, next_mean, next_var,
    excluded_spike. Returns None when cold-start guard fires.
    """
    if obs_count < MIN_OBSERVATIONS:
        return None

    # Sigma floor — proportion features get higher floor to avoid false alarms
    _PROPORTION_FEATURES = {
        "civilian_targeting_rate",
        "remote_violence_share",
        "geo_dispersion_km",
    }
    min_var = 0.0025 if feature_name in _PROPORTION_FEATURES else 0.0001  # 0.05² vs 0.01²
    sigma = math.sqrt(max(prior_var, min_var))

    # z-score uses PRIOR mean/var (before update)
    z_score = (observation_value - prior_mean) / sigma

    # Spike exclusion: |z| > 3 → don't fold into EWMA
    excluded_spike = abs(z_score) > Z_CRITICAL

    if not excluded_spike:
        next_mean = alpha * observation_value + (1.0 - alpha) * prior_mean
        # Welford-style EWMA variance update
        next_var = (1.0 - alpha) * (prior_var + alpha * (observation_value - next_mean) ** 2)
    else:
        next_mean = prior_mean
        next_var = prior_var

    if abs(z_score) >= Z_CRITICAL:
        deviation_level = "CRITICAL"
    elif abs(z_score) >= Z_EARLY_WARNING:
        deviation_level = "EARLY_WARNING"
    else:
        deviation_level = "NORMAL"

    return {
        "actor": actor,
        "theater": theater,
        "feature_name": feature_name,
        "observation_value": observation_value,
        "prior_mean": prior_mean,
        "z_score": round(z_score, 4),
        "deviation_level": deviation_level,
        "next_mean": round(next_mean, 6),
        "next_var": round(next_var, 8),
        "excluded_spike": excluded_spike,
    }


# ---------------------------------------------------------------------------
# DB helpers — bucket, upsert, alert insert
# ---------------------------------------------------------------------------

def _hour_bucket() -> datetime:
    """Current UTC hour truncated to the hour."""
    now = datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0)


_CREATE_DOCTRINE_PROFILES = """
CREATE TABLE IF NOT EXISTS doctrine_profiles (
    actor TEXT NOT NULL,
    theater TEXT NOT NULL DEFAULT 'global',
    feature_name TEXT NOT NULL,
    bucket_start TIMESTAMPTZ NOT NULL,
    observation_value DOUBLE PRECISION NOT NULL,
    ewma_mean DOUBLE PRECISION NOT NULL,
    ewma_var DOUBLE PRECISION NOT NULL,
    z_score DOUBLE PRECISION,
    deviation_level TEXT NOT NULL DEFAULT 'NORMAL',
    event_count INTEGER NOT NULL DEFAULT 1,
    sample_n INTEGER NOT NULL DEFAULT 1,
    excluded_spike BOOLEAN NOT NULL DEFAULT FALSE,
    source_event_ids TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (actor, theater, feature_name, bucket_start)
);
CREATE INDEX IF NOT EXISTS idx_doctrine_profiles_actor_feature_time
    ON doctrine_profiles(actor, feature_name, bucket_start DESC);
"""

_CREATE_DOCTRINE_ALERTS = """
CREATE TABLE IF NOT EXISTS doctrine_alerts (
    id BIGSERIAL PRIMARY KEY,
    actor TEXT NOT NULL,
    theater TEXT NOT NULL DEFAULT 'global',
    event_id TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    observed_value DOUBLE PRECISION NOT NULL,
    expected_mean DOUBLE PRECISION NOT NULL,
    expected_sd DOUBLE PRECISION NOT NULL,
    z_score DOUBLE PRECISION NOT NULL,
    deviation_level TEXT NOT NULL,
    supporting_event_ids TEXT[] NOT NULL DEFAULT '{}',
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_doctrine_alerts_actor_time
    ON doctrine_alerts(actor, created_at DESC);
"""


def _ensure_schema(cur) -> None:
    for stmt in _CREATE_DOCTRINE_PROFILES.strip().split(";"):
        s = stmt.strip()
        if s:
            cur.execute(s)
    for stmt in _CREATE_DOCTRINE_ALERTS.strip().split(";"):
        s = stmt.strip()
        if s:
            cur.execute(s)


def _get_prior_row(cur, actor: str, theater: str, feature_name: str, bucket: datetime):
    """
    Fetch the most recent doctrine_profiles row for this actor/theater/feature
    BEFORE the current bucket. Returns (ewma_mean, ewma_var, sample_n) or defaults.
    """
    cur.execute(
        """
        SELECT ewma_mean, ewma_var, sample_n
        FROM doctrine_profiles
        WHERE actor = %s AND theater = %s AND feature_name = %s
          AND bucket_start < %s
        ORDER BY bucket_start DESC
        LIMIT 1
        """,
        (actor, theater, feature_name, bucket),
    )
    row = cur.fetchone()
    if row is None:
        return 0.0, 0.0001, 0
    mean = float(row[0]) if row[0] is not None else 0.0
    var = float(row[1]) if row[1] is not None else 0.0001
    n = int(row[2]) if row[2] is not None else 0
    return mean, var, n


def _upsert_profile(
    cur,
    actor: str,
    theater: str,
    feature_name: str,
    bucket: datetime,
    obs_val: float,
    next_mean: float,
    next_var: float,
    z_score: Optional[float],
    deviation_level: str,
    excluded_spike: bool,
    event_id: str,
) -> None:
    cur.execute(
        """
        INSERT INTO doctrine_profiles
            (actor, theater, feature_name, bucket_start, observation_value,
             ewma_mean, ewma_var, z_score, deviation_level, event_count,
             sample_n, excluded_spike, source_event_ids, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 1, %s, %s, NOW())
        ON CONFLICT (actor, theater, feature_name, bucket_start) DO UPDATE SET
            observation_value = EXCLUDED.observation_value,
            ewma_mean         = EXCLUDED.ewma_mean,
            ewma_var          = EXCLUDED.ewma_var,
            z_score           = EXCLUDED.z_score,
            deviation_level   = EXCLUDED.deviation_level,
            event_count       = doctrine_profiles.event_count + 1,
            sample_n          = EXCLUDED.sample_n,
            excluded_spike    = EXCLUDED.excluded_spike,
            source_event_ids  = array_append(doctrine_profiles.source_event_ids, %s),
            updated_at        = NOW()
        """,
        (
            actor, theater, feature_name, bucket, obs_val,
            next_mean, next_var, z_score, deviation_level,
            excluded_spike, [event_id],
            event_id,
        ),
    )


def _insert_alert(
    cur,
    actor: str,
    theater: str,
    event_id: str,
    feature_name: str,
    obs_val: float,
    expected_mean: float,
    expected_sd: float,
    z_score: float,
    deviation_level: str,
    payload: dict,
) -> None:
    cur.execute(
        """
        INSERT INTO doctrine_alerts
            (actor, theater, event_id, feature_name, observed_value,
             expected_mean, expected_sd, z_score, deviation_level,
             supporting_event_ids, payload_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            actor, theater, event_id, feature_name, obs_val,
            expected_mean, expected_sd, z_score, deviation_level,
            [event_id],
            json.dumps(payload, default=str),
        ),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def update_doctrine_profile_for_event(
    event: dict,
    database_url: str,
    psycopg_mod,
) -> List[Dict[str, Any]]:
    """
    Main entry point called after every successful persist_event_v2_pg.

    1. Extracts primary actor — returns [] if not a DOCTRINE_ACTORS member.
    2. Extracts 5 doctrine features from the event.
    3. For each feature, fetches prior EWMA state from DB.
    4. Scores deviation (returns None if cold-start guard fires).
    5. Upserts doctrine_profiles row.
    6. If EARLY_WARNING or CRITICAL, inserts doctrine_alert row.
    7. Returns list of alert dicts (may be empty).
    """
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return []

    actor = extract_primary_actor(event)
    if actor is None:
        return []

    theater = str(event.get("theater") or "global")
    event_id = str(event.get("id") or event.get("incident_id") or "unknown")
    bucket = _hour_bucket()
    features = extract_doctrine_features(event)

    alerts: List[Dict[str, Any]] = []

    try:
        with psycopg_mod.connect(database_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                _ensure_schema(cur)

                for feature_name, obs_val in features.items():
                    prior_mean, prior_var, sample_n = _get_prior_row(
                        cur, actor, theater, feature_name, bucket
                    )

                    result = score_doctrine_deviation(
                        actor=actor,
                        theater=theater,
                        feature_name=feature_name,
                        observation_value=obs_val,
                        prior_mean=prior_mean,
                        prior_var=prior_var,
                        alpha=ALPHA,
                        obs_count=sample_n,
                    )

                    if result is None:
                        # Cold-start: still upsert profile to accumulate sample_n
                        _upsert_profile(
                            cur, actor, theater, feature_name, bucket,
                            obs_val,
                            ALPHA * obs_val + (1.0 - ALPHA) * prior_mean,
                            prior_var,
                            None, "NORMAL", False, event_id,
                        )
                        continue

                    _upsert_profile(
                        cur, actor, theater, feature_name, bucket,
                        obs_val,
                        result["next_mean"],
                        result["next_var"],
                        result["z_score"],
                        result["deviation_level"],
                        result["excluded_spike"],
                        event_id,
                    )

                    if result["deviation_level"] in ("EARLY_WARNING", "CRITICAL"):
                        expected_sd = math.sqrt(max(prior_var, 0.0001))
                        payload = _build_alert_payload(
                            actor=actor,
                            theater=theater,
                            event_id=event_id,
                            event=event,
                            feature_name=feature_name,
                            obs_val=obs_val,
                            expected_mean=prior_mean,
                            expected_sd=expected_sd,
                            z_score=result["z_score"],
                            deviation_level=result["deviation_level"],
                        )
                        _insert_alert(
                            cur, actor, theater, event_id, feature_name,
                            obs_val, prior_mean, expected_sd,
                            result["z_score"], result["deviation_level"],
                            payload,
                        )
                        alerts.append(payload)

                conn.commit()

    except Exception as exc:
        logger.warning("[doctrine] profile update failed for actor=%s: %s", actor, exc)

    return alerts


# ---------------------------------------------------------------------------
# Alert payload builder
# ---------------------------------------------------------------------------

def _build_alert_payload(
    actor: str,
    theater: str,
    event_id: str,
    event: dict,
    feature_name: str,
    obs_val: float,
    expected_mean: float,
    expected_sd: float,
    z_score: float,
    deviation_level: str,
) -> Dict[str, Any]:
    direction = "exceeded" if z_score > 0 else "dropped below"
    return {
        "alert_type": "doctrine_deviation",
        "actor": actor,
        "theater": theater,
        "event_id": event_id,
        "event_timestamp": str(event.get("timestamp") or ""),
        "feature_name": feature_name,
        "observed_value": round(obs_val, 4),
        "expected_mean": round(expected_mean, 4),
        "expected_sd": round(expected_sd, 4),
        "z_score": round(z_score, 4),
        "deviation_level": deviation_level,
        "bucket_start": _hour_bucket().isoformat(),
        "explanation": (
            f"Observed {actor} {feature_name} {direction} 30-hour EWMA baseline "
            f"by {abs(z_score):.1f} standard deviations "
            f"(observed={obs_val:.2f}, expected={expected_mean:.2f}±{expected_sd:.2f})."
        ),
        "recommended_action": (
            "Escalate to analyst review and inject into next SITREP."
            if deviation_level == "CRITICAL"
            else "Monitor for continued deviation over next 2 hours."
        ),
    }
