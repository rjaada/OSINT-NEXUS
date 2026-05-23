"""
escalation_classifier.py — Escalation Ladder Classifier (Feature B).

Classifies each conflict theater into one of 6 escalation states using
a Gaussian HMM trained on 7-day observation windows derived from events_v2.

States (ACLED-aligned thresholds):
  0 = LATENT        — no events
  1 = SPORADIC      — <3 events/week, isolated
  2 = ACTIVE        — 3-15 events/week, sustained
  3 = ESCALATING    — >15 events/week OR fatalities spike >2σ
  4 = PEAK          — >50 events/week OR mass-casualty (>25 fatalities single event)
  5 = DE_ESCALATING — rate declining >30% from prior week peak

Training uses events_v2 history — no external ACLED CSV required.
Model is disabled (returns None) until first training run succeeds.
"""

from __future__ import annotations

import json
import logging
import math
import os
import pickle
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("osint.escalation")

# ── Constants ─────────────────────────────────────────────────────────────────

STATE_NAMES = {
    0: "LATENT",
    1: "SPORADIC",
    2: "ACTIVE",
    3: "ESCALATING",
    4: "PEAK",
    5: "DE_ESCALATING",
}

N_STATES = 6
WINDOW_DAYS = 7
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")

_STRIKE_TYPES = {"STRIKE", "CRITICAL"}
_CLASH_TYPES = {"CLASH", "ACTIVITY"}


# ── Observation vector extraction ─────────────────────────────────────────────

def extract_theater_obs_vector(
    events: List[Dict[str, Any]],
    window_start: datetime,
    window_days: int = WINDOW_DAYS,
) -> Optional[np.ndarray]:
    """
    Build the 6-feature observation vector for one (theater, time_window).

    Features:
      0: events_per_day
      1: fatalities_per_day
      2: strike_fraction   (STRIKE+CRITICAL / total)
      3: clash_fraction    (CLASH+ACTIVITY / total)
      4: unique_sources_count
      5: max_single_event_fatalities

    Returns shape (6,) or None if no events in window.
    """
    window_end = window_start + timedelta(days=window_days)
    window_events = [
        e for e in events
        if _parse_ts(str(e.get("timestamp", ""))) is not None
        and window_start <= _parse_ts(str(e.get("timestamp", ""))) < window_end  # type: ignore[operator]
    ]

    n = len(window_events)
    if n == 0:
        return np.zeros(6, dtype=float)

    fatalities = [_safe_int(e.get("fatalities") or e.get("confidence_score") or 0) for e in window_events]
    types = [str(e.get("type") or "").upper() for e in window_events]
    sources = set(str(e.get("source") or "") for e in window_events if e.get("source"))

    strike_frac = sum(1 for t in types if t in _STRIKE_TYPES) / n
    clash_frac = sum(1 for t in types if t in _CLASH_TYPES) / n
    max_fatalities = max(fatalities) if fatalities else 0
    total_fatalities = sum(fatalities)

    return np.array([
        n / window_days,                   # events_per_day
        total_fatalities / window_days,    # fatalities_per_day
        strike_frac,                       # strike_fraction
        clash_frac,                        # clash_fraction
        float(len(sources)),               # unique_sources_count
        float(max_fatalities),             # max_single_event_fatalities
    ], dtype=float)


def _parse_ts(ts_str: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _safe_int(val: Any) -> int:
    try:
        return int(float(val))
    except Exception:
        return 0


# ── Label assignment ──────────────────────────────────────────────────────────

def label_window(
    obs: np.ndarray,
    prior_obs: Optional[np.ndarray] = None,
) -> int:
    """
    Assign escalation state label from ACLED-derived thresholds.

    obs shape: (6,) as returned by extract_theater_obs_vector.
    prior_obs: prior window for DE_ESCALATING detection.
    """
    events_per_day = obs[0]
    fatalities_per_day = obs[1]
    max_fatalities = obs[5]
    events_per_week = events_per_day * 7

    # PEAK: >50/week OR mass-casualty
    if events_per_week > 50 or max_fatalities > 25:
        return 4

    # Check DE_ESCALATING: current rate < 70% of prior peak
    if prior_obs is not None and prior_obs[0] > 0:
        if events_per_day < prior_obs[0] * 0.70 and prior_obs[0] * 7 >= 15:
            return 5

    # ESCALATING: >15/week
    if events_per_week > 15:
        return 3

    # ACTIVE: 3-15/week
    if events_per_week >= 3:
        return 2

    # SPORADIC: any events
    if events_per_week > 0:
        return 1

    return 0  # LATENT


# ── Model persistence ─────────────────────────────────────────────────────────

def _model_path(theater: str) -> str:
    safe = theater.replace(" ", "_").replace("/", "-")
    os.makedirs(MODEL_DIR, exist_ok=True)
    return os.path.join(MODEL_DIR, f"hmm_escalation_{safe}.pkl")


def _save_model(model: Any, theater: str) -> None:
    with open(_model_path(theater), "wb") as f:
        pickle.dump(model, f)


def _load_model(theater: str) -> Optional[Any]:
    path = _model_path(theater)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as exc:
        logger.warning("[escalation] failed to load model for %s: %s", theater, exc)
        return None


# ── Training ──────────────────────────────────────────────────────────────────

def train_escalation_model(theater: str, obs_seq: np.ndarray, label_seq: np.ndarray) -> Optional[Any]:
    """
    Train a GaussianHMM on the observation sequence.
    Returns fitted model or None if training fails.

    Guards:
    - insufficient state diversity (< 3 distinct states) → skip
    - random_state=42 for reproducible initialization
    """
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        logger.warning("[escalation] hmmlearn not available — skipping training")
        return None

    unique_states = set(label_seq)
    if len(unique_states) < 3:
        logger.warning(
            "[escalation] insufficient state diversity for %s (%d states) — skipping",
            theater, len(unique_states),
        )
        return None

    if len(obs_seq) < 10:
        logger.warning("[escalation] too few windows for %s (%d) — skipping", theater, len(obs_seq))
        return None

    try:
        model = GaussianHMM(
            n_components=N_STATES,
            covariance_type="diag",
            n_iter=100,
            random_state=42,
        )
        model.fit(obs_seq)
        _save_model(model, theater)
        logger.info("[escalation] trained model for %s (%d windows)", theater, len(obs_seq))
        return model
    except Exception as exc:
        logger.warning("[escalation] training failed for %s: %s", theater, exc)
        return None


# ── Inference ─────────────────────────────────────────────────────────────────

def predict_current_state(
    theater: str,
    recent_obs: np.ndarray,
) -> Dict[str, Any]:
    """
    Predict current escalation state using the saved HMM model.
    Falls back to rule-based label when model unavailable.

    recent_obs: shape (n_recent_windows, 6) — last N observation windows.
    """
    model = _load_model(theater)
    current_obs = recent_obs[-1] if len(recent_obs) > 0 else np.zeros(6)
    prior_obs = recent_obs[-2] if len(recent_obs) > 1 else None
    rule_state = label_window(current_obs, prior_obs)

    if model is None:
        return {
            "theater": theater,
            "state_id": rule_state,
            "state_name": STATE_NAMES[rule_state],
            "confidence": None,
            "method": "rule_based",
            "model_available": False,
        }

    try:
        state_seq = model.predict(recent_obs)
        current_state = int(state_seq[-1])
        # Confidence: posterior probability of predicted state
        log_probs = model.predict_proba(recent_obs)
        confidence = float(log_probs[-1, current_state])
        return {
            "theater": theater,
            "state_id": current_state,
            "state_name": STATE_NAMES.get(current_state, "UNKNOWN"),
            "confidence": round(confidence, 4),
            "method": "hmm",
            "model_available": True,
        }
    except Exception as exc:
        logger.warning("[escalation] prediction failed for %s: %s", theater, exc)
        return {
            "theater": theater,
            "state_id": rule_state,
            "state_name": STATE_NAMES[rule_state],
            "confidence": None,
            "method": "rule_based_fallback",
            "model_available": True,
        }


# ── DB helpers ────────────────────────────────────────────────────────────────

def _upsert_theater_state(conn, state: Dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO theater_states (theater, state_id, state_name, confidence, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (theater) DO UPDATE SET
                state_id   = EXCLUDED.state_id,
                state_name = EXCLUDED.state_name,
                confidence = EXCLUDED.confidence,
                updated_at = NOW()
            """,
            (state["theater"], state["state_id"], state["state_name"], state.get("confidence")),
        )


def _theater_bbox(theater: Dict[str, Any]) -> Tuple[float, float, float, float]:
    coords = theater["coordinates"]
    if isinstance(coords, str):
        coords = json.loads(coords)
    lngs = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return min(lats), max(lats), min(lngs), max(lngs)


def _event_in_bbox(lat: float, lng: float, bbox: Tuple[float, float, float, float]) -> bool:
    min_lat, max_lat, min_lng, max_lng = bbox
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng


# ── Main entry points ─────────────────────────────────────────────────────────

def get_all_theater_states(database_url: str, psycopg_mod) -> List[Dict[str, Any]]:
    """
    Return current escalation state for all active conflict zones.
    Uses HMM if available, falls back to rule-based classification.
    """
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return []

    try:
        with psycopg_mod.connect(database_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                # Load theaters
                cur.execute("SELECT label, coordinates FROM conflict_zones WHERE active = TRUE")
                theaters = []
                for row in cur.fetchall():
                    try:
                        coords = row[1]
                        if isinstance(coords, str):
                            coords = json.loads(coords)
                        bbox = _theater_bbox({"label": row[0], "coordinates": coords})
                        theaters.append({"label": row[0], "bbox": bbox})
                    except Exception:
                        continue

                if not theaters:
                    return []

                # Load events from last 90 days
                cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
                cur.execute(
                    """
                    SELECT lat, lng, type, timestamp, confidence_score
                    FROM events_v2
                    WHERE timestamp >= %s
                      AND lat IS NOT NULL AND lng IS NOT NULL
                    ORDER BY timestamp
                    """,
                    (cutoff,),
                )
                raw_events = cur.fetchall()

        # Parse events
        all_events: List[Dict[str, Any]] = []
        for row in raw_events:
            ts = _parse_ts(str(row[3])) if row[3] else None
            if ts is None:
                continue
            all_events.append({
                "lat": float(row[0]), "lng": float(row[1]),
                "type": str(row[2] or ""), "timestamp": ts,
                "confidence_score": row[4],
            })

        # Generate recent 13 weeks of windows (90 days / 7-day windows)
        now = datetime.now(timezone.utc)
        window_starts = [now - timedelta(days=WINDOW_DAYS * (i + 1)) for i in range(12, -1, -1)]

        results: List[Dict[str, Any]] = []
        with psycopg_mod.connect(database_url, connect_timeout=5) as conn:
            for theater in theaters:
                bbox = theater["bbox"]
                # Filter events for this theater
                theater_evts = [
                    {"type": e["type"], "timestamp": e["timestamp"].isoformat(),
                     "confidence_score": e["confidence_score"]}
                    for e in all_events
                    if _event_in_bbox(e["lat"], e["lng"], bbox)
                ]

                obs_list = []
                for ws in window_starts:
                    obs = extract_theater_obs_vector(theater_evts, ws)
                    obs_list.append(obs if obs is not None else np.zeros(6))

                obs_seq = np.array(obs_list, dtype=float)
                state = predict_current_state(theater["label"], obs_seq)
                results.append(state)

                _upsert_theater_state(conn, state)
            conn.commit()

        return results

    except Exception as exc:
        logger.warning("[escalation] get_all_theater_states failed: %s", exc)
        return []


def retrain_all_theaters(database_url: str, psycopg_mod) -> Dict[str, Any]:
    """
    Weekly retrain: build observation sequences from events_v2 history
    and retrain HMM models for all active theaters.
    """
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return {"error": "database unavailable"}

    try:
        with psycopg_mod.connect(database_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT label, coordinates FROM conflict_zones WHERE active = TRUE")
                theaters_raw = cur.fetchall()
                cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
                cur.execute(
                    """
                    SELECT lat, lng, type, timestamp, confidence_score
                    FROM events_v2
                    WHERE timestamp >= %s
                      AND lat IS NOT NULL AND lng IS NOT NULL
                    ORDER BY timestamp
                    """,
                    (cutoff,),
                )
                raw_events = cur.fetchall()

        all_events: List[Dict[str, Any]] = []
        for row in raw_events:
            ts = _parse_ts(str(row[3])) if row[3] else None
            if ts is None:
                continue
            all_events.append({
                "lat": float(row[0]), "lng": float(row[1]),
                "type": str(row[2] or ""), "timestamp": ts,
                "confidence_score": row[4],
            })

        trained = []
        skipped = []
        now = datetime.now(timezone.utc)

        for row in theaters_raw:
            label = row[0]
            try:
                coords = row[1]
                if isinstance(coords, str):
                    coords = json.loads(coords)
                bbox = _theater_bbox({"label": label, "coordinates": coords})
            except Exception:
                skipped.append(label)
                continue

            theater_evts = [
                {"type": e["type"], "timestamp": e["timestamp"].isoformat(),
                 "confidence_score": e["confidence_score"]}
                for e in all_events
                if _event_in_bbox(e["lat"], e["lng"], bbox)
            ]

            # Generate weekly windows over full history
            weeks_back = 52  # 1 year
            window_starts = [now - timedelta(days=WINDOW_DAYS * (i + 1)) for i in range(weeks_back - 1, -1, -1)]
            obs_list = []
            label_list = []
            for i, ws in enumerate(window_starts):
                obs = extract_theater_obs_vector(theater_evts, ws)
                vec = obs if obs is not None else np.zeros(6)
                obs_list.append(vec)
                prior = obs_list[i - 1] if i > 0 else None
                lbl = label_window(vec, prior)
                label_list.append(lbl)

            obs_seq = np.array(obs_list, dtype=float)
            label_seq = np.array(label_list, dtype=int)
            model = train_escalation_model(label, obs_seq, label_seq)
            if model is not None:
                trained.append(label)
            else:
                skipped.append(label)

        return {"trained": trained, "skipped": skipped, "retrained_at": now.isoformat()}

    except Exception as exc:
        logger.warning("[escalation] retrain failed: %s", exc)
        return {"error": str(exc)}
