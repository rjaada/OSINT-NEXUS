"""
Source Network Mapping — information ecosystem terrain analysis.

Builds a weighted co-occurrence graph from disinfo cluster membership:
sources that repeatedly appear in the same claim clusters are structurally
linked in the information environment — whether as amplifiers, coordinators,
or independent reporters covering the same beat.

Community detection (greedy modularity) groups sources into suspected
information networks without requiring Neo4j GDS or external graph libraries.

Output is D3-compatible: nodes + edges + communities.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Channel type classification (mirrors disinfo_detector._channel_type)
# ---------------------------------------------------------------------------

_CHANNEL_TYPES: Dict[str, Set[str]] = {
    "telegram": {"AJ Mubasher (TG)", "Roaa War Studies (TG)", "OSINTdefender (TG)",
                 "Intel_Slava (TG)", "WarMonitor (TG)", "MilWarMap (TG)"},
    "rss": {"BBC News", "Reuters", "Al Jazeera", "DW News", "Jerusalem Post",
            "France24", "Haaretz", "Times of Israel", "AP", "AFP",
            "Sky News", "NPR", "CNN", "Al Arabiya"},
    "sensor": {"NASA FIRMS", "ADSB.lol", "AISStream", "FR24-MIL"},
    "market": {"Market Data"},
}

# Affiliation labels intentionally omitted from API output — editorial judgments
# belong in analyst notes, not automated pipeline responses.


def _channel_type(source: str) -> str:
    for ctype, sources in _CHANNEL_TYPES.items():
        if source in sources:
            return ctype
    if "(TG)" in source or "telegram" in source.lower():
        return "telegram"
    return "other"


def _parse_ts(ts_str: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Co-occurrence matrix from disinfo clusters
# ---------------------------------------------------------------------------

def build_cooccurrence(clusters: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Build weighted co-occurrence matrix from disinfo cluster events.
    Each pair of sources that appear in the same cluster gets an edge
    with weight += 1 and avg_delay_min tracking.
    """
    edges: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for cluster in clusters:
        events = sorted(cluster.get("events", []), key=lambda e: e.get("timestamp", ""))
        sources = [e.get("source") for e in events if e.get("source")]
        if len(sources) < 2:
            continue

        # All pairs in this cluster
        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                s1, s2 = sources[i], sources[j]
                if s1 == s2:
                    continue
                key = (min(s1, s2), max(s1, s2))

                if key not in edges:
                    edges[key] = {"weight": 0, "total_delay_min": 0.0, "clusters": []}

                edges[key]["weight"] += 1
                edges[key]["clusters"].append(cluster.get("cluster_id", ""))

                # Delay between the two sources in this cluster
                ti = _parse_ts(str(events[i].get("timestamp", "")))
                tj = _parse_ts(str(events[j].get("timestamp", "")))
                if ti and tj:
                    delay = abs((tj - ti).total_seconds()) / 60
                    edges[key]["total_delay_min"] += delay

    # Finalize avg_delay
    for key, data in edges.items():
        data["avg_delay_min"] = round(data["total_delay_min"] / max(data["weight"], 1), 1)
        del data["total_delay_min"]

    return edges


# ---------------------------------------------------------------------------
# Community detection — greedy modularity (pure Python)
# ---------------------------------------------------------------------------

def detect_communities(
    sources: List[str],
    edges: Dict[Tuple[str, str], Dict[str, Any]],
) -> Dict[str, int]:
    """
    Simple greedy community detection.
    Each source starts in its own community.
    Iteratively merge pairs with highest edge weight until no improvement.
    Returns source → community_id mapping.
    """
    # Initialize: each source in its own community
    community: Dict[str, int] = {s: i for i, s in enumerate(sources)}
    total_weight = sum(e["weight"] for e in edges.values()) or 1

    improved = True
    while improved:
        improved = False
        # Find the highest-weight edge that crosses community boundaries
        best_gain = 0.0
        best_pair: Optional[Tuple[str, str]] = None

        for (s1, s2), data in edges.items():
            if community.get(s1) == community.get(s2):
                continue
            # Modularity gain: weight between communities vs expected by degree product
            ki = sum(e["weight"] for (a, b), e in edges.items() if a == s1 or b == s1)
            kj = sum(e["weight"] for (a, b), e in edges.items() if a == s2 or b == s2)
            gain = data["weight"] / total_weight - (ki * kj) / (2 * total_weight ** 2)
            if gain > best_gain:
                best_gain = gain
                best_pair = (s1, s2)

        # Merge only when Newman-Girvan gain is positive
        if best_pair and best_gain > 0.0:
            s1, s2 = best_pair
            old_id = community[s2]
            new_id = community[s1]
            for s, cid in community.items():
                if cid == old_id:
                    community[s] = new_id
            improved = True

    # Normalize community IDs to sequential integers
    id_map: Dict[int, int] = {}
    next_id = 0
    result: Dict[str, int] = {}
    for s, cid in community.items():
        if cid not in id_map:
            id_map[cid] = next_id
            next_id += 1
        result[s] = id_map[cid]

    return result


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_source_network(
    recent_events: List[dict],
    clusters: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build complete source network from recent events and (optional) disinfo clusters.

    If clusters not provided, derives co-occurrence from events that share
    the same corroborating_sources field (simpler but less precise).
    """
    # Count events per source
    source_counts: Dict[str, int] = defaultdict(int)
    for evt in recent_events:
        src = evt.get("source")
        if src:
            source_counts[str(src)] += 1

    if not source_counts:
        return {"nodes": [], "edges": [], "communities": 0, "scanned_at": datetime.now(timezone.utc).isoformat()}

    # Build co-occurrence edges
    if clusters:
        cooc = build_cooccurrence(clusters)
    else:
        # Fallback: derive from corroborating_sources field
        cooc = _cooccurrence_from_events(recent_events)

    all_sources = list(source_counts.keys())

    # Detect communities
    community_map = detect_communities(all_sources, cooc)
    num_communities = len(set(community_map.values()))

    # Degree centrality per source
    degree: Dict[str, int] = defaultdict(int)
    for s1, s2 in cooc.keys():
        degree[s1] += 1
        degree[s2] += 1
    max_degree = max(degree.values(), default=1)

    # Build nodes
    nodes = []
    for src in all_sources:
        nodes.append({
            "id": src,
            "channel_type": _channel_type(src),
            "event_count": source_counts[src],
            "community": community_map.get(src, 0),
            "centrality": round(degree.get(src, 0) / max_degree, 3),
        })

    # Build edges
    edges = []
    for (s1, s2), data in cooc.items():
        edges.append({
            "source": s1,
            "target": s2,
            "weight": data["weight"],
            "avg_delay_min": data["avg_delay_min"],
            "same_community": community_map.get(s1) == community_map.get(s2),
        })

    # Sort edges by weight descending
    edges.sort(key=lambda e: e["weight"], reverse=True)

    return {
        "nodes": nodes,
        "edges": edges[:100],  # cap at 100 edges
        "communities": num_communities,
        "sources_tracked": len(nodes),
        "edges_detected": len(edges),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


def _cooccurrence_from_events(events: List[dict]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Fallback: build co-occurrence from corroborating_sources fields."""
    edges: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for evt in events:
        primary = evt.get("source")
        corr = evt.get("corroborating_sources") or []
        all_srcs = ([primary] if primary else []) + list(corr)
        all_srcs = list(dict.fromkeys(s for s in all_srcs if s))
        for i in range(len(all_srcs)):
            for j in range(i + 1, len(all_srcs)):
                s1, s2 = all_srcs[i], all_srcs[j]
                key = (min(s1, s2), max(s1, s2))
                if key not in edges:
                    edges[key] = {"weight": 0, "avg_delay_min": 0.0, "clusters": []}
                edges[key]["weight"] += 1
    return edges
