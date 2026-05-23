"""
claim_lineage.py — Claim Lineage Fingerprinting (Feature C).

Builds a time-ordered propagation tree for a seed event: which other events
are plausibly reporting the same claim, in what order, and how far each has
mutated from the original.

Algorithm: greedy closest-ancestor (time-ordering constraint).
  For each event ordered by timestamp, attach to the already-processed node
  with minimum weight. O(n²), fine for n < 200.

Weight: 0.3 * norm_time_delta + 0.7 * (1 - cosine_sim)
  — text similarity matters more than timing.

Parallel-origin detection: if cosine_sim > 0.85 AND delay < 5 min,
  the two events likely originated independently (same primary source),
  not through propagation.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Reuse token / cosine helpers from disinfo_detector — no duplication
try:
    from disinfo_detector import _event_tokens, _cosine_sim, _parse_ts
except ImportError:
    # Fallback definitions if import not available
    def _parse_ts(ts_str: str) -> Optional[datetime]:  # type: ignore[misc]
        try:
            return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        except Exception:
            return None

    def _event_tokens(event: dict) -> set:  # type: ignore[misc]
        tokens: set = set()
        for field in ("desc", "description"):
            text = str(event.get(field) or "").lower()
            for word in re.findall(r"\b[a-z]{4,}\b", text):
                tokens.add(word)
        tokens.add(str(event.get("type") or "").lower())
        return tokens

    def _cosine_sim(toks_a: set, toks_b: set) -> float:  # type: ignore[misc]
        if not toks_a or not toks_b:
            return 0.0
        return len(toks_a & toks_b) / math.sqrt(len(toks_a) * len(toks_b))


# Similarity threshold: events below this are unrelated claims
LINEAGE_COSINE_MIN = 0.20
# Weight split: time vs. text
ALPHA_TIME = 0.3
# Parallel-origin detection thresholds
PARALLEL_COSINE = 0.85
PARALLEL_DELAY_MIN = 5.0


def _norm_time_delta(dt_seconds: float, max_seconds: float) -> float:
    """Normalize time difference to [0, 1] using max observed window."""
    if max_seconds <= 0:
        return 0.0
    return min(dt_seconds / max_seconds, 1.0)


def _edge_weight(
    parent: dict,
    child: dict,
    parent_tokens: set,
    child_tokens: set,
    max_delta_sec: float,
) -> float:
    pt = _parse_ts(str(parent.get("timestamp", "")))
    ct = _parse_ts(str(child.get("timestamp", "")))
    if pt and ct:
        dt_sec = abs((ct - pt).total_seconds())
    else:
        dt_sec = max_delta_sec  # treat unknown as max distance

    cosine = _cosine_sim(parent_tokens, child_tokens)
    time_component = ALPHA_TIME * _norm_time_delta(dt_sec, max_delta_sec)
    text_component = (1.0 - ALPHA_TIME) * (1.0 - cosine)
    return time_component + text_component


def build_lineage_tree(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a claim propagation tree from a list of related events.

    Input: list of event dicts, each with at minimum:
      id, timestamp, source, desc (or description)

    Returns: lineage tree JSON matching the blueprint schema.
    """
    if not events:
        return {"nodes": [], "edges": [], "total_nodes": 0, "max_mutation": 0.0,
                "generated_at": datetime.now(timezone.utc).isoformat()}

    # Sort by timestamp ascending — root = earliest
    def _ts_key(e: dict) -> datetime:
        ts = _parse_ts(str(e.get("timestamp", "")))
        return ts if ts else datetime.max.replace(tzinfo=timezone.utc)

    sorted_events = sorted(events, key=_ts_key)

    # Pre-compute token sets
    token_sets: List[set] = [_event_tokens(e) for e in sorted_events]

    # Time window for normalization: span from first to last event
    ts_first = _parse_ts(str(sorted_events[0].get("timestamp", "")))
    ts_last = _parse_ts(str(sorted_events[-1].get("timestamp", "")))
    if ts_first and ts_last:
        max_delta_sec = max(abs((ts_last - ts_first).total_seconds()), 1.0)
    else:
        max_delta_sec = 3600.0

    root_tokens = token_sets[0]
    root_event = sorted_events[0]

    # Build tree: greedy closest-ancestor
    edges: List[Dict[str, Any]] = []
    parent_idx: Dict[int, int] = {}  # child_idx → parent_idx
    depths: Dict[int, int] = {0: 0}

    for idx in range(1, len(sorted_events)):
        child = sorted_events[idx]
        child_tokens = token_sets[idx]
        best_w = float("inf")
        best_parent = 0

        for pidx in range(idx):  # only earlier events as candidates
            parent = sorted_events[pidx]
            parent_tokens = token_sets[pidx]
            w = _edge_weight(parent, child, parent_tokens, child_tokens, max_delta_sec)
            if w < best_w:
                best_w = w
                best_parent = pidx

        parent_idx[idx] = best_parent

        # Edge metadata
        p = sorted_events[best_parent]
        pt = _parse_ts(str(p.get("timestamp", "")))
        ct = _parse_ts(str(child.get("timestamp", "")))
        delay_min = 0.0
        if pt and ct:
            delay_min = round(abs((ct - pt).total_seconds()) / 60, 1)

        sim = _cosine_sim(token_sets[best_parent], child_tokens)
        parallel = sim >= PARALLEL_COSINE and delay_min < PARALLEL_DELAY_MIN

        edges.append({
            "source": str(p.get("id", "")),
            "target": str(child.get("id", "")),
            "similarity": round(sim, 3),
            "delay_minutes": delay_min,
            "parallel_origin": parallel,
        })

        # Depth = parent depth + 1
        depths[idx] = depths.get(best_parent, 0) + 1

    # Build node list
    nodes: List[Dict[str, Any]] = []
    for idx, evt in enumerate(sorted_events):
        mutation = round(1.0 - _cosine_sim(root_tokens, token_sets[idx]), 3)
        nodes.append({
            "id": str(evt.get("id", "")),
            "source": str(evt.get("source", "")),
            "timestamp": str(evt.get("timestamp", "")),
            "description": str(evt.get("desc") or evt.get("description") or ""),
            "depth": depths.get(idx, 0),
            "mutation_score": mutation,
        })

    max_mutation = max((n["mutation_score"] for n in nodes), default=0.0)

    # Summarize the claim from root event description
    root_desc = str(root_event.get("desc") or root_event.get("description") or "")
    claim_summary = (root_desc[:80] + "…") if len(root_desc) > 80 else root_desc
    if len(nodes) > 1:
        claim_summary = f"{claim_summary} — reported by {len(nodes)} sources"

    return {
        "root_id": str(root_event.get("id", "")),
        "claim_summary": claim_summary,
        "nodes": nodes,
        "edges": edges,
        "total_nodes": len(nodes),
        "max_mutation": round(max_mutation, 3),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def find_related_events(
    seed_event: Dict[str, Any],
    candidate_events: List[Dict[str, Any]],
    window_hours: float = 24.0,
    min_cosine: float = LINEAGE_COSINE_MIN,
    max_events: int = 50,
) -> List[Dict[str, Any]]:
    """
    Filter candidate events to those plausibly reporting the same claim as seed_event.
    Returns seed + related events, capped at max_events.
    """
    seed_ts = _parse_ts(str(seed_event.get("timestamp", "")))
    seed_tokens = _event_tokens(seed_event)
    seed_id = seed_event.get("id")

    related = [seed_event]
    for evt in candidate_events:
        if str(evt.get("id")) == str(seed_id):
            continue  # skip self
        evt_ts = _parse_ts(str(evt.get("timestamp", "")))
        if seed_ts and evt_ts:
            delta_hours = abs((evt_ts - seed_ts).total_seconds()) / 3600
            if delta_hours > window_hours:
                continue
        sim = _cosine_sim(seed_tokens, _event_tokens(evt))
        if sim >= min_cosine:
            related.append(evt)
        if len(related) >= max_events:
            break

    return related
