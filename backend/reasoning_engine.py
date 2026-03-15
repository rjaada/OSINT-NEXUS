"""
Reasoning Engine — Layer 3 intelligence.

Takes recent events, finds correlations, builds causal chains,
detects contradictions, matches historical patterns, and generates
a SITREP (Situation Report) via Groq.

Honesty rule: every claim is grounded in actual events from the DB.
Groq narrates — it does not invent.
"""

import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("osint.reasoning")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(ts_str: str) -> datetime:
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _haversine_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Approximate distance in degrees (cheap, good enough for clustering)."""
    return math.sqrt((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2)


def _event_tokens(event: dict) -> set:
    """Extract a set of meaningful tokens from an event for overlap scoring."""
    tokens: set = set()
    desc = str(event.get("desc") or "").lower()
    for word in desc.split():
        if len(word) > 4:
            tokens.add(word)
    for actor in event.get("observed_facts") or []:
        tokens.add(str(actor).lower())
    for inf in event.get("model_inference") or []:
        tokens.add(str(inf).lower())
    tokens.add(str(event.get("type") or "").lower())
    return tokens


# ---------------------------------------------------------------------------
# Event correlation
# ---------------------------------------------------------------------------

def correlate_events(
    events: List[dict],
    window_hours: float = 72.0,
    proximity_deg: float = 2.0,
    min_cluster_size: int = 2,
) -> List[List[dict]]:
    """
    Group events into clusters where members share:
    - spatial proximity (within proximity_deg) OR
    - token overlap (same actors/keywords) OR
    - same event type within the window

    Returns clusters sorted by size descending.
    """
    if not events:
        return []

    # Sort by timestamp
    sorted_evts = sorted(events, key=lambda e: _parse_ts(str(e.get("timestamp", ""))))

    # Build adjacency: two events are "related" if any criterion matches
    n = len(sorted_evts)
    related: Dict[int, set] = defaultdict(set)

    for i in range(n):
        ei = sorted_evts[i]
        ti = _parse_ts(str(ei.get("timestamp", "")))
        toks_i = _event_tokens(ei)
        lat_i = float(ei.get("lat") or 0.0)
        lng_i = float(ei.get("lng") or 0.0)

        for j in range(i + 1, n):
            ej = sorted_evts[j]
            tj = _parse_ts(str(ej.get("timestamp", "")))

            # Time window check
            if abs((tj - ti).total_seconds()) > window_hours * 3600:
                break  # events are sorted, no need to look further

            lat_j = float(ej.get("lat") or 0.0)
            lng_j = float(ej.get("lng") or 0.0)
            toks_j = _event_tokens(ej)

            spatial = _haversine_deg(lat_i, lng_i, lat_j, lng_j) <= proximity_deg
            same_type = ei.get("type") == ej.get("type") and ei.get("type") not in (None, "", "CLASH")
            token_overlap = len(toks_i & toks_j) >= 2

            if spatial or same_type or token_overlap:
                related[i].add(j)
                related[j].add(i)

    # Union-find to build clusters
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for i, neighbors in related.items():
        for j in neighbors:
            union(i, j)

    cluster_map: Dict[int, List[dict]] = defaultdict(list)
    for i, evt in enumerate(sorted_evts):
        cluster_map[find(i)].append(evt)

    clusters = [c for c in cluster_map.values() if len(c) >= min_cluster_size]
    clusters.sort(key=len, reverse=True)
    return clusters


# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------

def detect_contradictions(events: List[dict]) -> List[Dict[str, Any]]:
    """
    Find pairs of events from DIFFERENT sources that cover the same
    location/time but with conflicting types or descriptions.
    Returns list of contradiction dicts.
    """
    contradictions = []
    checked = set()

    for i, ei in enumerate(events):
        for j, ej in enumerate(events):
            if j <= i:
                continue
            pair = (i, j)
            if pair in checked:
                continue
            checked.add(pair)

            # Same source = not a contradiction
            if ei.get("source") == ej.get("source"):
                continue

            lat_i, lng_i = float(ei.get("lat") or 0), float(ei.get("lng") or 0)
            lat_j, lng_j = float(ej.get("lat") or 0), float(ej.get("lng") or 0)
            if _haversine_deg(lat_i, lng_i, lat_j, lng_j) > 1.5:
                continue

            ti = _parse_ts(str(ei.get("timestamp", "")))
            tj = _parse_ts(str(ej.get("timestamp", "")))
            if abs((ti - tj).total_seconds()) > 6 * 3600:
                continue

            # Type contradiction (one says STRIKE, other says MOVEMENT nearby)
            type_conflict = (
                ei.get("type") in ("STRIKE", "CRITICAL") and ej.get("type") == "MOVEMENT"
            ) or (
                ej.get("type") in ("STRIKE", "CRITICAL") and ei.get("type") == "MOVEMENT"
            )

            if type_conflict:
                contradictions.append({
                    "event_a": {"id": ei.get("id"), "desc": ei.get("desc"), "source": ei.get("source"), "type": ei.get("type")},
                    "event_b": {"id": ej.get("id"), "desc": ej.get("desc"), "source": ej.get("source"), "type": ej.get("type")},
                    "conflict_type": "type_mismatch",
                    "location": {"lat": (lat_i + lat_j) / 2, "lng": (lng_i + lng_j) / 2},
                })

    return contradictions[:5]  # cap at 5


# ---------------------------------------------------------------------------
# Historical pattern matching via Neo4j
# ---------------------------------------------------------------------------

def match_historical_patterns(
    graph_store: Any,
    cluster: List[dict],
) -> List[str]:
    """
    Query Neo4j for PRECEDED_BY chains that match the current cluster's
    event types and locations. Returns plain-text pattern descriptions.
    """
    if graph_store is None or not graph_store.status().get("connected"):
        return []

    patterns = []
    types_in_cluster = list({e.get("type") for e in cluster if e.get("type")})

    try:
        with graph_store._driver.session() as session:
            result = session.run(
                """
                MATCH (a:Event)-[r:PRECEDED_BY]->(b:Event)
                WHERE a.type IN $types AND b.type IN $types
                  AND a.timestamp < b.timestamp
                RETURN a.type AS from_type, b.type AS to_type,
                       a.description AS from_desc, b.description AS to_desc,
                       duration.between(datetime(a.timestamp), datetime(b.timestamp)).hours AS hours_gap
                ORDER BY b.timestamp DESC
                LIMIT 6
                """,
                {"types": types_in_cluster},
            )
            rows = result.data()
            for row in rows:
                gap = row.get("hours_gap") or "?"
                patterns.append(
                    f"{row.get('from_type')} → {row.get('to_type')} "
                    f"(gap: {gap}h) | '{str(row.get('from_desc',''))[:60]}'"
                )
    except Exception as exc:
        logger.warning("[RE] historical pattern query failed: %s", exc)

    return patterns


# ---------------------------------------------------------------------------
# Groq SITREP generation
# ---------------------------------------------------------------------------

_SITREP_SYSTEM = """You are a senior intelligence analyst generating a classified Situation Report (SITREP).
You will receive a cluster of correlated security events, contradiction flags, and historical patterns.
Produce a structured JSON SITREP with these exact keys:
{
  "headline": "One-sentence summary of the situation (max 120 chars)",
  "what_happened": "2-3 sentences: factual summary of the correlated events",
  "why_it_matters": "2-3 sentences: strategic significance, who benefits, what it signals",
  "causal_chain": ["step 1", "step 2", "step 3"],
  "contradictions_summary": "One sentence about any conflicting reports, or 'No contradictions detected'",
  "historical_parallel": "One sentence matching this to a past pattern, or 'No clear historical match'",
  "watch_items": [
    {"item": "what to watch", "timeframe": "within X hours/days", "why": "one sentence"},
    {"item": "...", "timeframe": "...", "why": "..."},
    {"item": "...", "timeframe": "...", "why": "..."}
  ],
  "confidence": "HIGH|MEDIUM|LOW",
  "confidence_reason": "One sentence explaining confidence level",
  "dominant_actors": ["actor1", "actor2"],
  "key_locations": ["location1", "location2"]
}
Base EVERYTHING on the provided events. Do not invent facts.
IMPORTANT: "dominant_actors" must be real political/military actors (countries, factions, militaries) — NOT data sources like "NASA FIRMS", "BBC News", "AISStream".
If the data is weak, say so in confidence_reason. Return ONLY valid JSON."""


def _call_groq_sitrep(
    groq_client: Any,
    cluster: List[dict],
    contradictions: List[dict],
    patterns: List[str],
) -> Optional[Dict[str, Any]]:
    """Send the cluster to Groq and get a structured SITREP back."""
    if groq_client is None or not groq_client.groq_available():
        return None

    # Build compact event summaries
    event_summaries = []
    for e in cluster[:20]:  # cap at 20 events
        event_summaries.append({
            "id": e.get("id"),
            "type": e.get("type"),
            "source": e.get("source"),
            "timestamp": str(e.get("timestamp", ""))[:19],
            "desc": str(e.get("desc") or "")[:200],
            "confidence_score": e.get("confidence_score"),
            "lat": e.get("lat"),
            "lng": e.get("lng"),
        })

    payload = {
        "event_count": len(cluster),
        "events": event_summaries,
        "contradictions": contradictions,
        "historical_patterns": patterns,
        "honesty_note": (
            f"This SITREP covers {len(cluster)} correlated events from "
            f"{len({e.get('source') for e in cluster})} sources. "
            "Do NOT invent facts. If data is sparse, say so."
        ),
    }

    messages = [
        {"role": "system", "content": _SITREP_SYSTEM},
        {"role": "user", "content": json.dumps(payload, default=str)[:5000]},
    ]

    raw = groq_client.chat(messages, max_tokens=1200, temperature=0.15)
    if not raw:
        return None

    try:
        cleaned = raw
        if "<think>" in cleaned:
            end = cleaned.rfind("</think>")
            cleaned = cleaned[end + 8:].strip() if end != -1 else cleaned
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if "```" in cleaned:
                cleaned = cleaned[: cleaned.rfind("```")]
            cleaned = cleaned.strip()
        return json.loads(cleaned)
    except Exception:
        return {"headline": "SITREP parse error", "raw": raw[:500]}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_sitrep(
    graph_store: Any,
    groq_client: Any,
    recent_events: List[dict],
    window_hours: float = 72.0,
) -> Dict[str, Any]:
    """
    Full pipeline:
    1. Correlate events into clusters
    2. Pick dominant cluster
    3. Detect contradictions
    4. Match historical patterns
    5. Call Groq for structured SITREP
    6. Return result with metadata
    """
    base: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "event_count": len(recent_events),
        "cluster_count": 0,
        "dominant_cluster_size": 0,
        "contradictions": [],
        "historical_patterns": [],
        "sitrep": None,
        "groq_available": groq_client.groq_available() if groq_client else False,
        "neo4j_available": graph_store is not None and graph_store.status().get("connected", False),
        "data_quality": "no_data",
    }

    if not recent_events:
        return base

    clusters = correlate_events(recent_events, window_hours=window_hours)
    base["cluster_count"] = len(clusters)

    # Pick the biggest cluster with highest-confidence events
    # Priority event types — operational intelligence over sensor noise
    _HIGH_VALUE_TYPES = {"STRIKE", "CRITICAL", "CLASH", "MOVEMENT", "NOTAM"}
    _LOW_VALUE_SOURCES = {"NASA FIRMS", "ADSB.lol", "AISStream", "FR24-MIL", "Market Data"}

    def _cluster_score(c: List[dict]) -> float:
        """Score a cluster: penalize sensor-only clusters, reward operational events."""
        high_value = sum(1 for e in c if e.get("type") in _HIGH_VALUE_TYPES)
        diverse_sources = len({e.get("source") for e in c if e.get("source") not in _LOW_VALUE_SOURCES})
        avg_conf = sum((e.get("confidence_score") or 0) for e in c) / max(len(c), 1)
        # Heavy weight on operational events + source diversity
        return high_value * 10 + diverse_sources * 5 + avg_conf * 0.1 + len(c) * 0.5

    dominant: List[dict] = []
    if clusters:
        # Pick cluster with best operational score, not just biggest
        dominant = max(clusters, key=_cluster_score)

    base["dominant_cluster_size"] = len(dominant)

    if len(dominant) == 0:
        base["data_quality"] = "no_data"
        return base
    elif len(dominant) < 3:
        base["data_quality"] = "sparse"
    elif len(dominant) < 8:
        base["data_quality"] = "partial"
    else:
        base["data_quality"] = "rich"

    contradictions = detect_contradictions(dominant)
    patterns = match_historical_patterns(graph_store, dominant)

    base["contradictions"] = contradictions
    base["historical_patterns"] = patterns

    sitrep = _call_groq_sitrep(groq_client, dominant, contradictions, patterns)
    base["sitrep"] = sitrep

    # Extract watch items for Layer 4
    watch_items: List[Dict[str, str]] = []
    if sitrep and isinstance(sitrep.get("watch_items"), list):
        watch_items = sitrep["watch_items"]
    base["watch_items"] = watch_items

    return base
