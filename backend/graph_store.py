import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover - optional dependency at runtime
    GraphDatabase = None  # type: ignore

logger = logging.getLogger("osint.graph")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


class GraphStore:
    def __init__(self, uri: str, user: str, password: str):
        self.uri = (uri or "").strip()
        self.user = (user or "").strip()
        self.password = (password or "").strip()
        self._driver = None
        self._enabled = bool(self.uri and self.user and self.password and GraphDatabase is not None)
        self._last_error: Optional[str] = None

        if not self._enabled:
            if GraphDatabase is None:
                self._last_error = "neo4j driver unavailable"
            else:
                self._last_error = "neo4j not configured"
            return

        try:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            with self._driver.session() as session:
                session.run("RETURN 1").single()
        except Exception as exc:
            self._last_error = str(exc)
            self._enabled = False
            self._driver = None
            logger.warning("[GRAPH] Neo4j init failed: %s", exc)

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "connected": self._driver is not None,
            "uri": self.uri if self.uri else None,
            "error": self._last_error,
        }

    def _run(self, query: str, params: Dict[str, Any]) -> None:
        if self._driver is None:
            return
        with self._driver.session() as session:
            session.run(query, params)

    def _query(self, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self._driver is None:
            return []
        with self._driver.session() as session:
            result = session.run(query, params)
            return [dict(record) for record in result]

    def upsert_source_node(self, source_id: str, name: str, props: Optional[Dict[str, Any]] = None) -> None:
        if not source_id:
            return
        payload = {
            "source_id": source_id,
            "name": name or source_id,
            "props": props or {},
            "updated_at": _utc_iso(),
        }
        self._run(
            """
            MERGE (s:SOURCE {id: $source_id})
            ON CREATE SET s.created_at = $updated_at
            SET s.name = $name,
                s.label = $name,
                s.updated_at = $updated_at,
                s += $props
            """,
            payload,
        )

    def upsert_location_node(self, location_id: str, lat: Optional[float], lng: Optional[float], props: Optional[Dict[str, Any]] = None) -> None:
        if not location_id:
            return
        payload = {
            "location_id": location_id,
            "lat": lat,
            "lng": lng,
            "label": f"{lat:.4f},{lng:.4f}" if lat is not None and lng is not None else location_id,
            "props": props or {},
            "updated_at": _utc_iso(),
        }
        self._run(
            """
            MERGE (l:LOCATION {id: $location_id})
            ON CREATE SET l.created_at = $updated_at
            SET l.lat = $lat,
                l.lng = $lng,
                l.label = $label,
                l.updated_at = $updated_at,
                l += $props
            """,
            payload,
        )

    def upsert_event_node(self, event: Dict[str, Any]) -> None:
        event_id = str(event.get("id") or "").strip()
        if not event_id:
            return

        source = str(event.get("source") or event.get("source_name") or "Unknown").strip() or "Unknown"
        source_id = f"source:{source.lower().replace(' ', '_')}"
        lat = _safe_float(event.get("lat"))
        lng = _safe_float(event.get("lng"))
        location_id = ""
        if lat is not None and lng is not None:
            location_id = f"loc:{round(lat, 4)}:{round(lng, 4)}"

        payload = {
            "event_id": event_id,
            "event_type": str(event.get("type") or "UNKNOWN"),
            "description": str(event.get("description") or event.get("desc") or "").strip(),
            "incident_id": str(event.get("incident_id") or "").strip() or None,
            "timestamp": str(event.get("timestamp") or _utc_iso()),
            "confidence_score": int(event.get("confidence_score") or 0),
            "lat": lat,
            "lng": lng,
            "source": source,
            "source_id": source_id,
            "location_id": location_id,
            "updated_at": _utc_iso(),
        }

        self._run(
            """
            MERGE (e:EVENT {id: $event_id})
            ON CREATE SET e.created_at = $updated_at
            SET e.type = $event_type,
                e.label = CASE
                    WHEN $description = '' THEN $event_type
                    ELSE substring($description, 0, 110)
                END,
                e.description = $description,
                e.incident_id = $incident_id,
                e.timestamp = $timestamp,
                e.confidence_score = $confidence_score,
                e.lat = $lat,
                e.lng = $lng,
                e.updated_at = $updated_at
            """,
            payload,
        )
        self.upsert_source_node(source_id=source_id, name=source)
        if location_id:
            self.upsert_location_node(location_id=location_id, lat=lat, lng=lng)

        self.create_relationship("EVENT", event_id, "SOURCE", source_id, "REPORTED_BY", {"updated_at": payload["updated_at"]})
        if location_id:
            self.create_relationship("EVENT", event_id, "LOCATION", location_id, "OCCURRED_AT", {"updated_at": payload["updated_at"]})

        incident_id = str(event.get("incident_id") or "").strip()
        if incident_id:
            related = self._query(
                """
                MATCH (other:EVENT {incident_id: $incident_id})
                WHERE other.id <> $event_id
                RETURN other.id AS id
                ORDER BY other.timestamp DESC
                LIMIT 6
                """,
                {"incident_id": incident_id, "event_id": event_id},
            )
            for row in related:
                other_id = str(row.get("id") or "").strip()
                if other_id:
                    self.create_relationship("EVENT", event_id, "EVENT", other_id, "CORROBORATES", {"via": "incident_id", "updated_at": payload["updated_at"]})

    def create_relationship(
        self,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        rel_type: str,
        props: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not from_id or not to_id or not rel_type:
            return
        query = f"""
        MATCH (a:{from_label} {{id: $from_id}})
        MATCH (b:{to_label} {{id: $to_id}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += $props
        """
        self._run(query, {"from_id": from_id, "to_id": to_id, "props": props or {}})

    def create_temporal_relationship(
        self,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        rel_type: str,
        since: str,
        weight: float = 1.0,
        props: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Like create_relationship but always stamps since (ISO) and weight on the edge."""
        if not from_id or not to_id or not rel_type:
            return
        merged = dict(props or {})
        merged["since"] = since
        merged["weight"] = weight
        query = f"""
        MATCH (a:{from_label} {{id: $from_id}})
        MATCH (b:{to_label} {{id: $to_id}})
        MERGE (a)-[r:{rel_type}]->(b)
        ON CREATE SET r.since = $since
        SET r.weight = $weight, r += $props
        """
        self._run(query, {"from_id": from_id, "to_id": to_id, "since": since, "weight": weight, "props": merged})

    def link_temporal_predecessor(
        self,
        event_id: str,
        event_timestamp: str,
        lat: Optional[float],
        lng: Optional[float],
    ) -> None:
        """Find the most recent prior event near this location and create a PRECEDED_BY edge."""
        if self._driver is None or lat is None or lng is None:
            return
        rows = self._query(
            """
            MATCH (e:EVENT)
            WHERE e.id <> $event_id
              AND e.timestamp < $ts
              AND e.lat IS NOT NULL AND e.lng IS NOT NULL
              AND abs(e.lat - $lat) < 1.0
              AND abs(e.lng - $lng) < 1.0
            WITH e
            WHERE duration.between(datetime(e.timestamp), datetime($ts)).hours < 72
            RETURN e.id AS id, e.timestamp AS ts
            ORDER BY e.timestamp DESC
            LIMIT 1
            """,
            {"event_id": event_id, "ts": event_timestamp, "lat": lat, "lng": lng},
        )
        if rows:
            pred_id = str(rows[0].get("id") or "")
            if pred_id:
                self.create_temporal_relationship(
                    "EVENT", pred_id, "EVENT", event_id, "PRECEDED_BY",
                    since=event_timestamp, weight=0.7,
                    props={"method": "temporal_proximity", "updated_at": _utc_iso()},
                )

    def get_temporal_anomaly_score(self, event_id: str) -> float:
        """
        Score how anomalous this event is vs 30-day baseline.
        Returns 0.0 (routine) to 1.0 (highly anomalous).
        """
        if self._driver is None:
            return 0.0
        rows = self._query(
            """
            MATCH (e:EVENT {id: $event_id})-[:INVOLVED_ACTOR]->(a:ACTOR)
            MATCH (e)-[:OCCURRED_AT]->(l:LOCATION)
            WITH a, l
            MATCH (other:EVENT)-[:INVOLVED_ACTOR]->(a)
            MATCH (other)-[:OCCURRED_AT]->(l2:LOCATION)
            WHERE abs(l.lat - l2.lat) < 0.5 AND abs(l.lng - l2.lng) < 0.5
              AND other.id <> $event_id
            WITH count(other) AS baseline_count
            RETURN baseline_count
            """,
            {"event_id": event_id},
        )
        if not rows:
            return 0.5
        count = int(rows[0].get("baseline_count") or 0)
        if count == 0:
            return 0.85
        elif count < 3:
            return 0.6
        elif count < 10:
            return 0.35
        else:
            return 0.1

    def get_source_trust_network(self, event_id: str) -> dict:
        """Return source corroboration stats for an event."""
        if self._driver is None:
            return {"source_count": 0, "avg_trust": 0.0, "sources": []}
        rows = self._query(
            """
            MATCH (e:EVENT {id: $id})-[:REPORTED_BY]->(s:SOURCE)
            RETURN s.name AS name, s.trust AS trust
            """,
            {"id": event_id},
        )
        sources = [{"name": r.get("name"), "trust": r.get("trust")} for r in rows]
        trusts = [float(s["trust"]) for s in sources if s.get("trust") is not None]
        return {
            "source_count": len(sources),
            "avg_trust": round(sum(trusts) / len(trusts), 3) if trusts else 0.0,
            "sources": sources,
        }

    def get_graph_data(self, limit: int = 400) -> Dict[str, Any]:
        if self._driver is None:
            return {"nodes": [], "edges": []}

        rows = self._query(
            """
            MATCH (e:EVENT)
            WITH e ORDER BY e.timestamp DESC LIMIT $limit
            OPTIONAL MATCH (e)-[r:REPORTED_BY|OCCURRED_AT|CORROBORATES]->(n)
            WITH collect(DISTINCT e) + collect(DISTINCT n) AS ns,
                 collect(DISTINCT r) AS rs
            RETURN ns, rs
            """,
            {"limit": max(10, min(int(limit), 2000))},
        )
        if not rows:
            return {"nodes": [], "edges": []}

        record = rows[0]
        raw_nodes = record.get("ns") or []
        raw_edges = record.get("rs") or []

        nodes: List[Dict[str, Any]] = []
        seen_nodes = set()
        for node in raw_nodes:
            if node is None:
                continue
            data = dict(node)
            node_id = str(data.get("id") or "").strip()
            if not node_id or node_id in seen_nodes:
                continue
            labels = list(getattr(node, "labels", []))
            node_type = labels[0] if labels else "UNKNOWN"
            nodes.append(
                {
                    "id": node_id,
                    "type": node_type,
                    "label": str(data.get("label") or data.get("name") or node_id),
                    "properties": data,
                }
            )
            seen_nodes.add(node_id)

        edges: List[Dict[str, Any]] = []
        seen_edges = set()
        for rel in raw_edges:
            if rel is None:
                continue
            src = str(rel.start_node.get("id") or "").strip()  # type: ignore[attr-defined]
            dst = str(rel.end_node.get("id") or "").strip()  # type: ignore[attr-defined]
            rel_id = str(getattr(rel, "element_id", ""))
            rel_type = str(getattr(rel, "type", ""))
            if not src or not dst or not rel_type:
                continue
            dedup_key = f"{src}|{rel_type}|{dst}"
            if dedup_key in seen_edges:
                continue
            edges.append(
                {
                    "id": rel_id or dedup_key,
                    "source": src,
                    "target": dst,
                    "type": rel_type,
                    "properties": dict(rel),
                }
            )
            seen_edges.add(dedup_key)

        return {"nodes": nodes, "edges": edges}

    def upsert_actor_node(self, actor_id: str, name: str, props: Optional[Dict[str, Any]] = None) -> None:
        if not actor_id:
            return
        payload = {
            "actor_id": actor_id,
            "name": name or actor_id,
            "props": props or {},
            "updated_at": _utc_iso(),
        }
        self._run(
            """
            MERGE (a:ACTOR {id: $actor_id})
            ON CREATE SET a.created_at = $updated_at
            SET a.name = $name,
                a.label = $name,
                a.updated_at = $updated_at,
                a += $props
            """,
            payload,
        )

    def upsert_weapon_node(self, weapon_id: str, name: str, props: Optional[Dict[str, Any]] = None) -> None:
        if not weapon_id:
            return
        payload = {
            "weapon_id": weapon_id,
            "name": name or weapon_id,
            "props": props or {},
            "updated_at": _utc_iso(),
        }
        self._run(
            """
            MERGE (w:WEAPON {id: $weapon_id})
            ON CREATE SET w.created_at = $updated_at
            SET w.name = $name,
                w.label = $name,
                w.updated_at = $updated_at,
                w += $props
            """,
            payload,
        )

    def link_event_actors(self, event_id: str, actors: List[str]) -> None:
        """Link an EVENT to ACTOR nodes, creating actors if needed."""
        for name in actors:
            name = (name or "").strip()
            if not name:
                continue
            actor_id = f"actor:{name.lower().replace(' ', '_')}"
            self.upsert_actor_node(actor_id=actor_id, name=name)
            self.create_relationship("EVENT", event_id, "ACTOR", actor_id, "INVOLVED_ACTOR", {"updated_at": _utc_iso()})

    def link_event_weapons(self, event_id: str, weapons: List[str]) -> None:
        """Link an EVENT to WEAPON nodes, creating weapons if needed."""
        for name in weapons:
            name = (name or "").strip()
            if not name:
                continue
            weapon_id = f"weapon:{name.lower().replace(' ', '_')}"
            self.upsert_weapon_node(weapon_id=weapon_id, name=name)
            self.create_relationship("EVENT", event_id, "WEAPON", weapon_id, "WEAPON_TYPE", {"updated_at": _utc_iso()})

    def get_event_subgraph(self, event_id: str, hops: int = 2) -> Dict[str, Any]:
        """
        Return a rich subgraph around an event for intelligence tracing.
        Includes the event, its directly related nodes, and 1 hop of
        related events (CORROBORATES, PRECEDED_BY, FOLLOWED_BY).
        """
        if self._driver is None:
            return {"event": None, "related_events": [], "sources": [], "actors": [], "weapons": [], "locations": []}

        event_rows = self._query(
            "MATCH (e:EVENT {id: $id}) RETURN e LIMIT 1",
            {"id": event_id},
        )
        if not event_rows or not event_rows[0].get("e"):
            return {"event": None, "related_events": [], "sources": [], "actors": [], "weapons": [], "locations": []}

        event_node = dict(event_rows[0]["e"])

        # Sources
        source_rows = self._query(
            """
            MATCH (e:EVENT {id: $id})-[:REPORTED_BY]->(s:SOURCE)
            RETURN s.name AS name, s.id AS id, s.trust AS trust
            """,
            {"id": event_id},
        )
        sources = [{"name": r.get("name"), "id": r.get("id"), "trust": r.get("trust")} for r in source_rows]

        # Actors
        actor_rows = self._query(
            """
            MATCH (e:EVENT {id: $id})-[:INVOLVED_ACTOR]->(a:ACTOR)
            RETURN a.name AS name, a.id AS id
            """,
            {"id": event_id},
        )
        actors = [{"name": r.get("name"), "id": r.get("id")} for r in actor_rows]

        # Weapons
        weapon_rows = self._query(
            """
            MATCH (e:EVENT {id: $id})-[:WEAPON_TYPE]->(w:WEAPON)
            RETURN w.name AS name, w.id AS id
            """,
            {"id": event_id},
        )
        weapons = [{"name": r.get("name"), "id": r.get("id")} for r in weapon_rows]

        # Locations
        loc_rows = self._query(
            """
            MATCH (e:EVENT {id: $id})-[:OCCURRED_AT]->(l:LOCATION)
            RETURN l.label AS label, l.lat AS lat, l.lng AS lng
            """,
            {"id": event_id},
        )
        locations = [{"label": r.get("label"), "lat": r.get("lat"), "lng": r.get("lng")} for r in loc_rows]

        # Related events (corroborating, temporal)
        related_rows = self._query(
            """
            MATCH (e:EVENT {id: $id})-[r:CORROBORATES|PRECEDED_BY|FOLLOWED_BY]-(other:EVENT)
            RETURN other.id AS id,
                   other.type AS type,
                   other.description AS description,
                   other.timestamp AS timestamp,
                   other.confidence_score AS confidence_score,
                   type(r) AS rel_type
            ORDER BY other.timestamp DESC
            LIMIT 10
            """,
            {"id": event_id},
        )
        related_events = [
            {
                "id": r.get("id"),
                "type": r.get("type"),
                "description": r.get("description"),
                "timestamp": r.get("timestamp"),
                "confidence_score": r.get("confidence_score"),
                "rel_type": r.get("rel_type"),
            }
            for r in related_rows
        ]

        return {
            "event": event_node,
            "related_events": related_events,
            "sources": sources,
            "actors": actors,
            "weapons": weapons,
            "locations": locations,
        }

    def get_node_profile(self, node_id: str) -> Optional[Dict[str, Any]]:
        if self._driver is None:
            return None
        target = (node_id or "").strip()
        if not target:
            return None

        rows = self._query(
            """
            MATCH (n {id: $node_id})
            OPTIONAL MATCH (n)-[r1]->(out)
            OPTIONAL MATCH (inc)-[r2]->(n)
            RETURN n,
                   collect(DISTINCT {type: type(r1), target: out.id, label: out.label, properties: properties(r1)}) AS outgoing,
                   collect(DISTINCT {type: type(r2), source: inc.id, label: inc.label, properties: properties(r2)}) AS incoming
            LIMIT 1
            """,
            {"node_id": target},
        )
        if not rows:
            return None

        record = rows[0]
        node = record.get("n")
        if node is None:
            return None

        props = dict(node)
        labels = list(getattr(node, "labels", []))
        return {
            "id": props.get("id"),
            "type": labels[0] if labels else "UNKNOWN",
            "label": props.get("label") or props.get("name") or props.get("id"),
            "properties": props,
            "outgoing": [x for x in (record.get("outgoing") or []) if x and x.get("type")],
            "incoming": [x for x in (record.get("incoming") or []) if x and x.get("type")],
        }
