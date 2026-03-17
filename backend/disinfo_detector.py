"""
Disinformation Signature Detector — Layer 2 verification.

Detects coordinated information operations by flagging claims that appear
simultaneously (within a configurable window) across 3+ distinct source
channels. Legitimate news spreads gradually; coordinated ops emerge at once.

Key signatures detected:
  1. Simultaneous emergence — same claim from 3+ sources within WINDOW_MINUTES
  2. Cross-channel coordination — sources from different channel types (RSS, Telegram, etc.)
  3. High token overlap — events share 4+ meaningful tokens

Honesty rule: flags are suspicion signals, NOT conclusions.
The analyst must verify. Flags are surfaced, never acted on automatically.
"""

import logging
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("osint.disinfo")

# Minimum distinct sources to flag a cluster
MIN_SOURCES = 3

# Time window in minutes — events within this window are "simultaneous"
WINDOW_MINUTES = 45

# Cosine similarity threshold for same-claim detection.
# Research (Stanford IO, EU DisinfoLab) uses >0.85 for full documents.
# Conflict event descriptions are short (10-40 tokens), so binary cosine
# produces lower values — 0.40 is roughly equivalent to 3-token overlap
# on a 6-token set but normalizes for event length.
COSINE_THRESHOLD = 0.40

# Source channel types — used to check cross-channel diversity
_CHANNEL_TYPES = {
    "telegram": {"AJ Mubasher (TG)", "Roaa War Studies (TG)", "OSINTdefender (TG)",
                 "Intel_Slava (TG)", "WarMonitor (TG)", "MilWarMap (TG)"},
    "rss": {"BBC News", "Reuters", "Al Jazeera", "DW News", "Jerusalem Post",
            "France24", "Haaretz", "Times of Israel", "AP", "AFP"},
    "sensor": {"NASA FIRMS", "ADSB.lol", "AISStream", "FR24-MIL"},
    "market": {"Market Data"},
}


def _channel_type(source: str) -> str:
    for ctype, sources in _CHANNEL_TYPES.items():
        if source in sources:
            return ctype
    # Partial match for Telegram channels not in whitelist
    if "(TG)" in source or "Telegram" in source.lower():
        return "telegram"
    return "other"


def _parse_ts(ts_str: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
    except Exception:
        return None


def _event_tokens(event: dict) -> set:
    """Extract meaningful tokens from event for overlap scoring."""
    tokens: set = set()
    for field in ("desc", "description"):
        text = str(event.get(field) or "").lower()
        for word in re.findall(r"\b[a-z]{4,}\b", text):
            tokens.add(word)
    for actor in event.get("observed_facts") or []:
        tokens.update(str(actor).lower().split())
    tokens.add(str(event.get("type") or "").lower())
    return tokens


def _cosine_sim(toks_a: set, toks_b: set) -> float:
    """Binary cosine similarity between two token sets (no sklearn dependency)."""
    if not toks_a or not toks_b:
        return 0.0
    intersection = len(toks_a & toks_b)
    return intersection / math.sqrt(len(toks_a) * len(toks_b))


def _events_are_same_claim(ei: dict, ej: dict) -> bool:
    """True if two events are plausibly the same claim (cosine similarity >= threshold).
    Normalizes for event length — short events aren't penalized vs long ones."""
    toks_i = _event_tokens(ei)
    toks_j = _event_tokens(ej)
    return _cosine_sim(toks_i, toks_j) >= COSINE_THRESHOLD


def detect_coordinated_clusters(
    events: List[dict],
    window_minutes: float = WINDOW_MINUTES,
    min_sources: int = MIN_SOURCES,
) -> List[Dict[str, Any]]:
    """
    Scan recent events for coordinated information operation signatures.

    Returns a list of flagged clusters, each with:
      - events: the matching events
      - sources: distinct source names
      - channel_types: distinct channel types
      - window_minutes: actual spread of the cluster in minutes
      - token_overlap: most common shared tokens
      - flag_reason: human-readable explanation
      - suspicion_level: HIGH / MEDIUM / LOW
    """
    if not events:
        return []

    # Sort by timestamp
    sorted_evts = sorted(
        [e for e in events if _parse_ts(str(e.get("timestamp", "")))],
        key=lambda e: _parse_ts(str(e.get("timestamp", ""))),
    )

    clusters: List[Dict[str, Any]] = []
    window_sec = window_minutes * 60

    # Sliding window: for each event, look forward within window
    n = len(sorted_evts)
    used_indices = set()

    for i in range(n):
        if i in used_indices:
            continue

        ei = sorted_evts[i]
        ti = _parse_ts(str(ei.get("timestamp", "")))
        if ti is None:
            continue

        # Collect all events within window that share this claim
        cluster_indices = [i]

        for j in range(i + 1, n):
            ej = sorted_evts[j]
            tj = _parse_ts(str(ej.get("timestamp", "")))
            if tj is None:
                continue
            if (tj - ti).total_seconds() > window_sec:
                break
            if _events_are_same_claim(ei, ej):
                cluster_indices.append(j)

        cluster_events = [sorted_evts[k] for k in cluster_indices]
        distinct_sources = list({e.get("source") for e in cluster_events if e.get("source")})
        distinct_channels = list({_channel_type(e.get("source") or "") for e in cluster_events})

        if len(distinct_sources) < min_sources:
            continue

        # Mark used so we don't double-count
        used_indices.update(cluster_indices)

        # Compute actual time spread
        timestamps = [_parse_ts(str(e.get("timestamp", ""))) for e in cluster_events]
        timestamps = [t for t in timestamps if t]
        time_spread_min = (max(timestamps) - min(timestamps)).total_seconds() / 60 if len(timestamps) > 1 else 0

        # Find most common shared tokens
        all_tokens: Dict[str, int] = defaultdict(int)
        for e in cluster_events:
            for tok in _event_tokens(e):
                all_tokens[tok] += 1
        top_tokens = sorted(all_tokens.items(), key=lambda x: x[1], reverse=True)
        common_tokens = [t for t, c in top_tokens if c >= len(cluster_events) * 0.6][:8]

        # Suspicion scoring
        score = 0
        # More sources = more suspicious
        score += min(len(distinct_sources) - min_sources, 5) * 20
        # Cross-channel (telegram + rss) = more suspicious than same channel
        if len(distinct_channels) >= 2 and "telegram" in distinct_channels:
            score += 30
        # Very tight time window = more suspicious
        if time_spread_min < 10:
            score += 30
        elif time_spread_min < 20:
            score += 15
        # Sensor sources corroborating = less suspicious (real events leave sensor signatures)
        sensor_count = sum(1 for e in cluster_events if _channel_type(e.get("source") or "") == "sensor")
        if sensor_count > 0:
            score -= 25

        suspicion_level = "HIGH" if score >= 50 else "MEDIUM" if score >= 25 else "LOW"

        # Build reason string
        reasons = []
        reasons.append(f"{len(distinct_sources)} distinct sources within {time_spread_min:.0f} min")
        if len(distinct_channels) >= 2:
            reasons.append(f"cross-channel ({', '.join(distinct_channels[:3])})")
        if time_spread_min < 15:
            reasons.append("simultaneous emergence (<15 min)")
        if sensor_count == 0:
            reasons.append("no sensor corroboration")

        clusters.append({
            "cluster_id": f"disinfo_{int(datetime.now(timezone.utc).timestamp())}_{i}",
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "suspicion_level": suspicion_level,
            "event_count": len(cluster_events),
            "sources": distinct_sources,
            "channel_types": distinct_channels,
            "time_spread_minutes": round(time_spread_min, 1),
            "common_tokens": common_tokens,
            "flag_reason": "; ".join(reasons),
            "events": [
                {
                    "id": e.get("id"),
                    "source": e.get("source"),
                    "type": e.get("type"),
                    "timestamp": str(e.get("timestamp", "")),
                    "desc": str(e.get("desc") or e.get("description") or "")[:120],
                }
                for e in cluster_events[:10]
            ],
            "analyst_note": (
                "This is a suspicion flag, not a conclusion. "
                "Verify independently before acting on this intelligence."
            ),
        })

    clusters.sort(key=lambda c: {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(c["suspicion_level"], 0), reverse=True)
    return clusters[:10]  # cap at 10 clusters per scan


def scan_for_disinfo(recent_events: List[dict]) -> Dict[str, Any]:
    """
    Full scan pipeline. Returns summary + clusters.
    Called from background task or on-demand endpoint.
    """
    clusters = detect_coordinated_clusters(recent_events)

    high = sum(1 for c in clusters if c["suspicion_level"] == "HIGH")
    medium = sum(1 for c in clusters if c["suspicion_level"] == "MEDIUM")

    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "events_scanned": len(recent_events),
        "clusters_detected": len(clusters),
        "high_suspicion": high,
        "medium_suspicion": medium,
        "clusters": clusters,
    }
