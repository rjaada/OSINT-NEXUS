"""
theater_synchrony.py — Cross-Theater Synchrony Detection (Feature D).

Detects whether two conflict theaters show statistically correlated
activity patterns — a signal for coordinated multi-front operations.

Method: Fisher's exact test (one-sided, "greater") on 2×2 co-occurrence
tables built from 30-day / 6-hour sliding windows with 3-hour step.

Bonferroni correction applied across all (theater_pair, event_type)
combinations to control false positive rate.

Pure Python Fisher's exact — no scipy dependency.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("osint.synchrony")

# ── Constants (from blueprint) ────────────────────────────────────────────────

LOOKBACK_DAYS = 30
WINDOW_HOURS = 6
STEP_HOURS = 3
P_THRESHOLD_RAW = 0.01        # before Bonferroni
MIN_CO_OCCURRENCES = 3        # require a ≥ 3 to avoid trivially rare pairs

ACLED_TYPES = [
    "Explosions/Remote violence",
    "Battles",
    "Strategic developments",
]


# ── Fisher's exact test (pure Python, no scipy) ───────────────────────────────

def _log_comb(n: int, k: int) -> float:
    """log C(n, k) using log-gamma for numerical stability."""
    if k < 0 or k > n:
        return -math.inf
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher_exact_greater(a: int, b: int, c: int, d: int) -> Tuple[float, float]:
    """
    One-sided Fisher's exact test (alternative="greater").
    Tests H1: T1 and T2 co-occur more than expected by chance.

    Returns (odds_ratio, p_value).
    odds_ratio = (a * d) / (b * c) — returns inf if b*c == 0.
    """
    n = a + b + c + d
    row1 = a + b
    col1 = a + c

    # Odds ratio
    if b * c == 0:
        odds_ratio = float("inf") if a * d > 0 else float("nan")
    else:
        odds_ratio = (a * d) / (b * c)

    # p-value: sum P(X >= a) under hypergeometric null
    # X ~ Hypergeometric(N=n, K=col1, n=row1)
    k_min = max(0, row1 + col1 - n)
    k_max = min(row1, col1)

    # Log-normalizing constant
    log_denom = _log_comb(n, row1)

    # P(X = k) = C(col1, k) * C(n-col1, row1-k) / C(n, row1)
    p_value = 0.0
    for k in range(a, k_max + 1):
        log_p = _log_comb(col1, k) + _log_comb(n - col1, row1 - k) - log_denom
        p_value += math.exp(log_p)

    return odds_ratio, min(p_value, 1.0)


# ── Theater loading ───────────────────────────────────────────────────────────

def _load_theaters(cur) -> List[Dict[str, Any]]:
    """
    Load active conflict zones from DB and derive bounding boxes.
    coordinates stored as JSONB list of [lng, lat] pairs.
    """
    cur.execute(
        "SELECT label, coordinates FROM conflict_zones WHERE active = TRUE ORDER BY label"
    )
    rows = cur.fetchall()
    theaters: List[Dict[str, Any]] = []
    for row in rows:
        label = row[0]
        coords = row[1]
        if isinstance(coords, str):
            try:
                coords = json.loads(coords)
            except Exception:
                continue
        if not coords or not isinstance(coords, list):
            continue
        try:
            lngs = [float(c[0]) for c in coords]
            lats = [float(c[1]) for c in coords]
        except (IndexError, TypeError, ValueError):
            continue
        theaters.append({
            "label": label,
            "min_lng": min(lngs), "max_lng": max(lngs),
            "min_lat": min(lats), "max_lat": max(lats),
        })
    return theaters


def _event_in_theater(lat: Optional[float], lng: Optional[float], theater: Dict[str, Any]) -> bool:
    if lat is None or lng is None:
        return False
    return (
        theater["min_lat"] <= lat <= theater["max_lat"]
        and theater["min_lng"] <= lng <= theater["max_lng"]
    )


# ── Window generation ─────────────────────────────────────────────────────────

def _generate_windows(lookback_days: int, window_hours: int, step_hours: int) -> List[Tuple[datetime, datetime]]:
    """Generate (start, end) tuples for all time windows."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start_time = now - timedelta(days=lookback_days)
    windows = []
    t = start_time
    while t + timedelta(hours=window_hours) <= now:
        windows.append((t, t + timedelta(hours=window_hours)))
        t += timedelta(hours=step_hours)
    return windows


# ── Co-occurrence counting ────────────────────────────────────────────────────

def _count_contingency(
    windows: List[Tuple[datetime, datetime]],
    events_a: List[Tuple[datetime, str]],  # (ts, acled_type)
    events_b: List[Tuple[datetime, str]],
    acled_type: str,
) -> Tuple[int, int, int, int]:
    """
    Build 2×2 contingency table for (theater_a, theater_b, acled_type).
    Returns (a, b, c, d).
    """
    a = b = c = d = 0
    for w_start, w_end in windows:
        has_a = any(
            w_start <= ts <= w_end and etype == acled_type
            for ts, etype in events_a
        )
        has_b = any(
            w_start <= ts <= w_end and etype == acled_type
            for ts, etype in events_b
        )
        if has_a and has_b:
            a += 1
        elif has_a and not has_b:
            b += 1
        elif not has_a and has_b:
            c += 1
        else:
            d += 1
    return a, b, c, d


# ── Main scanner ──────────────────────────────────────────────────────────────

def scan_theater_synchrony(database_url: str, psycopg_mod) -> Dict[str, Any]:
    """
    Scan all (theater_pair, ACLED_type) combinations for synchrony.
    Returns structured results with Bonferroni-corrected p-values.
    """
    if not database_url.startswith("postgres") or psycopg_mod is None:
        return {"error": "database unavailable", "detections": []}

    try:
        with psycopg_mod.connect(database_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                theaters = _load_theaters(cur)

                if len(theaters) < 2:
                    return {
                        "detections": [],
                        "theaters_scanned": len(theaters),
                        "window_count": 0,
                        "note": "fewer than 2 active conflict zones",
                        "scanned_at": datetime.now(timezone.utc).isoformat(),
                    }

                # Fetch all events in lookback window with lat/lng/acled_type/timestamp
                cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).isoformat()
                cur.execute(
                    """
                    SELECT lat, lng, acled_event_type, timestamp
                    FROM events_v2
                    WHERE timestamp >= %s
                      AND lat IS NOT NULL AND lng IS NOT NULL
                      AND acled_event_type IS NOT NULL
                      AND acled_event_type != ''
                    ORDER BY timestamp
                    """,
                    (cutoff,),
                )
                raw_events = cur.fetchall()

        # Parse timestamps
        parsed_events: List[Tuple[float, float, str, datetime]] = []
        for row in raw_events:
            lat, lng, etype, ts = row[0], row[1], row[2], row[3]
            if isinstance(ts, str):
                try:
                    ts_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                except Exception:
                    continue
            elif isinstance(ts, datetime):
                ts_dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            else:
                continue
            parsed_events.append((float(lat), float(lng), str(etype), ts_dt))

        # Pre-bin events per theater
        theater_events: Dict[str, List[Tuple[datetime, str]]] = {
            t["label"]: [] for t in theaters
        }
        for lat, lng, etype, ts_dt in parsed_events:
            for t in theaters:
                if _event_in_theater(lat, lng, t):
                    theater_events[t["label"]].append((ts_dt, etype))
                    break  # assign to first matching theater

        windows = _generate_windows(LOOKBACK_DAYS, WINDOW_HOURS, STEP_HOURS)
        n_windows = len(windows)

        theater_pairs = list(combinations([t["label"] for t in theaters], 2))
        n_tests = len(theater_pairs) * len(ACLED_TYPES)
        alpha_corrected = P_THRESHOLD_RAW / max(n_tests, 1)

        detections: List[Dict[str, Any]] = []
        all_results: List[Dict[str, Any]] = []

        for ta, tb in theater_pairs:
            ev_a = theater_events.get(ta, [])
            ev_b = theater_events.get(tb, [])

            for acled_type in ACLED_TYPES:
                a, b, c, d = _count_contingency(windows, ev_a, ev_b, acled_type)
                if a < MIN_CO_OCCURRENCES:
                    continue

                odds_ratio, p_value = fisher_exact_greater(a, b, c, d)

                result: Dict[str, Any] = {
                    "theater_a": ta,
                    "theater_b": tb,
                    "event_type": acled_type,
                    "co_occurrence_count": a,
                    "window_count": n_windows,
                    "a": a, "b": b, "c": c, "d": d,
                    "odds_ratio": round(odds_ratio, 3) if math.isfinite(odds_ratio) else None,
                    "p_value": round(p_value, 6),
                    "p_corrected": round(p_value * n_tests, 6),
                    "significant": p_value < alpha_corrected,
                    "alpha_corrected": round(alpha_corrected, 6),
                }
                all_results.append(result)
                if result["significant"]:
                    detections.append(result)

        # Sort detections by p_value ascending
        detections.sort(key=lambda r: r["p_value"])

        return {
            "detections": detections,
            "all_pairs": all_results,
            "theaters_scanned": len(theaters),
            "window_count": n_windows,
            "n_tests": n_tests,
            "alpha_corrected": round(alpha_corrected, 6),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.warning("[synchrony] scan failed: %s", exc)
        return {"error": str(exc), "detections": []}


def get_synchrony_summary(database_url: str, psycopg_mod) -> Dict[str, Any]:
    """Lightweight wrapper used by the API endpoint."""
    result = scan_theater_synchrony(database_url, psycopg_mod)
    # Return only detections + top 20 all_pairs (sorted by p_value)
    all_pairs = sorted(result.get("all_pairs", []), key=lambda r: r["p_value"])[:20]
    result["all_pairs"] = all_pairs
    return result
