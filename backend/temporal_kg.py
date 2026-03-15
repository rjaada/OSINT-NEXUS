"""
Temporal Knowledge Graph — intelligence orchestration layer.

Connects Neo4j graph data with temporal analysis:
  - Predecessor / successor linking via time-proximity (PRECEDED_BY edges)
  - Anomaly scoring based on 30-day actor/location baseline
  - Source trust aggregation across REPORTED_BY edges
  - Causal narrative via Groq — based ONLY on what the graph contains

Honesty rule: if the graph has no data, we say so. We never invent.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("osint.temporal_kg")


def enrich_event_with_temporal_context(
    graph_store: Any,
    event_id: str,
    event_timestamp: str,
    lat: Optional[float],
    lng: Optional[float],
) -> Dict[str, Any]:
    """
    Called after a new event is written to Neo4j.
    1. Links temporal predecessor (PRECEDED_BY edge within 72h / 100km)
    2. Computes anomaly score vs 30-day baseline
    Returns enrichment summary dict.
    """
    result: Dict[str, Any] = {
        "event_id": event_id,
        "predecessor_linked": False,
        "anomaly_score": 0.0,
        "enrichment": "none",
    }

    if graph_store is None or not graph_store.status().get("connected"):
        result["enrichment"] = "neo4j_unavailable"
        return result

    try:
        graph_store.link_temporal_predecessor(event_id, event_timestamp, lat, lng)
        result["predecessor_linked"] = True
    except Exception as exc:
        logger.warning("[TKG] predecessor link failed for %s: %s", event_id, exc)

    try:
        result["anomaly_score"] = graph_store.get_temporal_anomaly_score(event_id)
    except Exception as exc:
        logger.warning("[TKG] anomaly score failed for %s: %s", event_id, exc)

    result["enrichment"] = "complete"
    return result


def build_intelligence_trace(
    graph_store: Any,
    groq_client: Any,
    event_id: str,
) -> Dict[str, Any]:
    """
    Full intelligence picture for one event:
    1. Pull subgraph from Neo4j (actors, weapons, locations, related events, sources)
    2. Pull source trust network
    3. Compute anomaly score
    4. Send everything to Groq to narrate — only narrates what the graph says
    5. Return structured result with data-quality and honesty flags

    The caller sees exactly how many nodes the AI had access to.
    If Neo4j has nothing, the trace says so.
    """
    base: Dict[str, Any] = {
        "event_id": event_id,
        "neo4j_available": False,
        "groq_available": False,
        "subgraph": {},
        "source_trust": {"source_count": 0, "avg_trust": 0.0, "sources": []},
        "anomaly_score": 0.0,
        "trace": None,
        "data_quality": "no_data",
        "node_count": 0,
    }

    if graph_store is None or not graph_store.status().get("connected"):
        return base

    base["neo4j_available"] = True
    base["groq_available"] = groq_client.groq_available() if groq_client else False

    subgraph = graph_store.get_event_subgraph(event_id)
    source_trust = graph_store.get_source_trust_network(event_id)
    anomaly_score = graph_store.get_temporal_anomaly_score(event_id)

    event_node = subgraph.get("event") or {}
    node_count = (
        len(subgraph.get("related_events") or [])
        + len(subgraph.get("actors") or [])
        + len(subgraph.get("weapons") or [])
        + len(subgraph.get("locations") or [])
        + len(subgraph.get("sources") or [])
    )

    if node_count >= 5:
        data_quality = "rich"
    elif node_count >= 2:
        data_quality = "partial"
    elif node_count >= 1:
        data_quality = "sparse"
    else:
        data_quality = "no_data"

    description = str(event_node.get("description") or event_node.get("label") or "")

    trace_result = None
    if groq_client and groq_client.groq_available() and description:
        graph_context = {
            "node_count": node_count,
            "data_quality": data_quality,
            "source_trust": source_trust,
            "anomaly_score": round(anomaly_score, 3),
            "subgraph": subgraph,
            "honesty_note": (
                f"This analysis is grounded in {node_count} connected nodes from Neo4j. "
                f"Source count: {source_trust.get('source_count', 0)}, "
                f"avg trust: {source_trust.get('avg_trust', 0.0):.2f}. "
                "Do NOT invent facts. If a relationship is not in the subgraph, say 'not in graph'."
            ),
        }
        try:
            trace_result = groq_client.trace_event(description, graph_context)
        except Exception as exc:
            logger.warning("[TKG] groq trace failed for %s: %s", event_id, exc)

    return {
        "event_id": event_id,
        "neo4j_available": True,
        "groq_available": base["groq_available"],
        "subgraph": subgraph,
        "source_trust": source_trust,
        "anomaly_score": round(anomaly_score, 3),
        "trace": trace_result,
        "data_quality": data_quality,
        "node_count": node_count,
    }
