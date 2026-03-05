"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { CommandNav } from "@/components/dashboard/command-nav"
import { TopBar } from "@/components/dashboard/top-bar"
import { GraphCanvas } from "@/components/graph/graph-canvas"
import { GraphControls, GraphLegend } from "@/components/graph/graph-controls"
import { GraphSidebar } from "@/components/graph/graph-sidebar"
import {
  EDGE_COLORS,
  type GraphEdge,
  type GraphNode,
  type GraphNodeProfile,
  type NodeType,
  type RelationshipType,
  normalizeGraphPayload,
} from "@/lib/graph-data"
import { readCookie } from "@/lib/security"

type Role = "viewer" | "analyst" | "admin"

const API_BASE = "http://localhost:8000"

function slugSource(input: string): string {
  return input.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "unknown"
}

function addLiveEvent(
  nodes: GraphNode[],
  edges: GraphEdge[],
  event: Record<string, unknown>,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const eventId = String(event.id || "").trim()
  if (!eventId) return { nodes, edges }

  const now = new Date().toISOString()
  const source = String(event.source || "Unknown")
  const sourceId = `source:${slugSource(source)}`
  const lat = Number(event.lat || 0)
  const lng = Number(event.lng || 0)
  const locationId = Number.isFinite(lat) && Number.isFinite(lng) ? `loc:${lat.toFixed(4)}:${lng.toFixed(4)}` : ""

  const nextNodes = [...nodes]
  const nextEdges = [...edges]
  const byId = new Set(nextNodes.map((n) => n.id))
  const edgeKey = new Set(nextEdges.map((e) => `${e.source}|${e.type}|${e.target}`))

  if (!byId.has(eventId)) {
    nextNodes.push({
      id: eventId,
      type: "EVENT",
      label: String(event.type || "EVENT"),
      created: String(event.timestamp || now),
      lastSeen: now,
      confidence: Number(event.confidence_score || 0),
      connections: 0,
      x: 220 + Math.random() * 980,
      y: 160 + Math.random() * 560,
      vx: 0,
      vy: 0,
      cluster: "event",
      properties: {
        description: String(event.desc || ""),
        source,
        lat,
        lng,
      },
    })
    byId.add(eventId)
  }

  if (!byId.has(sourceId)) {
    nextNodes.push({
      id: sourceId,
      type: "SOURCE",
      label: source,
      created: now,
      lastSeen: now,
      connections: 0,
      x: 110 + Math.random() * 260,
      y: 140 + Math.random() * 560,
      vx: 0,
      vy: 0,
      cluster: "source",
      properties: {},
    })
    byId.add(sourceId)
  }

  if (locationId && !byId.has(locationId)) {
    nextNodes.push({
      id: locationId,
      type: "LOCATION",
      label: `${lat.toFixed(3)},${lng.toFixed(3)}`,
      created: now,
      lastSeen: now,
      connections: 0,
      x: 860 + Math.random() * 320,
      y: 140 + Math.random() * 560,
      vx: 0,
      vy: 0,
      cluster: "location",
      properties: { lat, lng },
    })
    byId.add(locationId)
  }

  const relA = `${eventId}|REPORTED_BY|${sourceId}`
  if (!edgeKey.has(relA)) {
    nextEdges.push({ id: `edge:${relA}`, source: eventId, target: sourceId, type: "REPORTED_BY" })
    edgeKey.add(relA)
  }
  if (locationId) {
    const relB = `${eventId}|OCCURRED_AT|${locationId}`
    if (!edgeKey.has(relB)) {
      nextEdges.push({ id: `edge:${relB}`, source: eventId, target: locationId, type: "OCCURRED_AT" })
      edgeKey.add(relB)
    }
  }

  const map = new Map<string, number>()
  nextEdges.forEach((edge) => {
    map.set(edge.source, (map.get(edge.source) || 0) + 1)
    map.set(edge.target, (map.get(edge.target) || 0) + 1)
  })
  nextNodes.forEach((node) => {
    node.connections = map.get(node.id) || 0
  })

  return { nodes: nextNodes, edges: nextEdges }
}

export default function V2GraphPage() {
  const [role, setRole] = useState<Role>("viewer")
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [edges, setEdges] = useState<GraphEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [offline, setOffline] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [timeRange, setTimeRange] = useState(24)
  const [activeNodeTypes, setActiveNodeTypes] = useState<Set<NodeType>>(new Set(["EVENT", "ACTOR", "LOCATION", "SOURCE", "INCIDENT", "TYPE"]))
  const [activeRelTypes, setActiveRelTypes] = useState<Set<RelationshipType>>(new Set())
  const [selectedProfile, setSelectedProfile] = useState<GraphNodeProfile | null>(null)
  const [loadingProfile, setLoadingProfile] = useState(false)
  const [backendTag, setBackendTag] = useState("")

  const allowed = role === "analyst" || role === "admin"

  useEffect(() => {
    const raw = readCookie("osint_role").toLowerCase()
    if (raw === "analyst" || raw === "admin" || raw === "viewer") setRole(raw)
  }, [])

  const loadGraph = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const res = await fetch(`${API_BASE}/api/v2/graph?limit=700`, {
        credentials: "include",
        cache: "no-store",
      })
      if (!res.ok) {
        if (res.status === 503) {
          setOffline(true)
          setError("GRAPH OFFLINE")
          return
        }
        throw new Error(`graph request failed (${res.status})`)
      }
      const data = (await res.json()) as {
        backend?: string
        nodes: Array<Record<string, unknown>>
        edges: Array<Record<string, unknown>>
      }
      const normalized = normalizeGraphPayload(data)
      setNodes(normalized.nodes)
      setEdges(normalized.edges)
      setOffline(false)
      setBackendTag(String(data.backend || "graph"))
    } catch (err) {
      setOffline(true)
      setError(err instanceof Error ? err.message : "GRAPH OFFLINE")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!allowed) {
      setLoading(false)
      return
    }
    void loadGraph()
  }, [allowed, loadGraph])

  useEffect(() => {
    if (!allowed) return
    const ws = new WebSocket("ws://localhost:8000/ws/live/v2")
    let ping: ReturnType<typeof setInterval> | null = null

    ws.onopen = () => {
      ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping")
      }, 18000)
    }
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data) as { type?: string; data?: Record<string, unknown> }
        if (msg.type === "NEW_EVENT" && msg.data) {
          setNodes((prevNodes) => {
            const result = addLiveEvent(prevNodes, edges, msg.data as Record<string, unknown>)
            setEdges(result.edges)
            return result.nodes
          })
        }
        if (msg.type === "NEW_EVENT_DIFF" && msg.data) {
          setNodes((prevNodes) => {
            const result = addLiveEvent(prevNodes, edges, msg.data as Record<string, unknown>)
            setEdges(result.edges)
            return result.nodes
          })
        }
      } catch {
        // no-op
      }
    }
    ws.onerror = () => {
      // keep page alive even if stream is down
    }
    ws.onclose = () => {
      if (ping) clearInterval(ping)
    }

    return () => {
      if (ping) clearInterval(ping)
      ws.close()
    }
  }, [allowed, edges])

  useEffect(() => {
    if (!selectedNodeId || !allowed) {
      setSelectedProfile(null)
      return
    }
    let mounted = true
    const loadProfile = async () => {
      setLoadingProfile(true)
      try {
        const res = await fetch(`${API_BASE}/api/v2/graph/node/${encodeURIComponent(selectedNodeId)}`, {
          credentials: "include",
          cache: "no-store",
        })
        if (!res.ok) {
          setSelectedProfile(null)
          return
        }
        const data = (await res.json()) as GraphNodeProfile
        if (!mounted) return
        setSelectedProfile(data)
      } catch {
        if (!mounted) return
        setSelectedProfile(null)
      } finally {
        if (mounted) setLoadingProfile(false)
      }
    }
    void loadProfile()
    return () => {
      mounted = false
    }
  }, [selectedNodeId, allowed])

  const toggleNodeType = useCallback((type: NodeType) => {
    setActiveNodeTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }, [])

  const toggleRelType = useCallback((type: RelationshipType) => {
    setActiveRelTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }, [])

  const nodeTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const node of nodes) counts[node.type] = (counts[node.type] || 0) + 1
    return counts
  }, [nodes])

  const timeFilteredNodes = useMemo(() => {
    if (!Number.isFinite(timeRange) || timeRange >= 72) return nodes
    const now = Date.now()
    const minTs = now - timeRange * 60 * 60 * 1000
    return nodes.filter((node) => {
      const ts = new Date(node.lastSeen).getTime()
      if (Number.isNaN(ts)) return true
      return ts >= minTs
    })
  }, [nodes, timeRange])

  const nodeSet = useMemo(() => new Set(timeFilteredNodes.map((n) => n.id)), [timeFilteredNodes])

  const timeFilteredEdges = useMemo(
    () => edges.filter((edge) => nodeSet.has(edge.source) && nodeSet.has(edge.target)),
    [edges, nodeSet],
  )

  const selectedNode = useMemo(
    () => (selectedNodeId ? timeFilteredNodes.find((node) => node.id === selectedNodeId) || null : null),
    [selectedNodeId, timeFilteredNodes],
  )

  const connectedNodes = useMemo(() => {
    if (!selectedNodeId) return []
    const connectedIds = new Set<string>()
    timeFilteredEdges.forEach((edge) => {
      if (edge.source === selectedNodeId) connectedIds.add(edge.target)
      if (edge.target === selectedNodeId) connectedIds.add(edge.source)
    })
    return timeFilteredNodes.filter((node) => connectedIds.has(node.id))
  }, [selectedNodeId, timeFilteredEdges, timeFilteredNodes])

  const edgeCountByType = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const edge of timeFilteredEdges) {
      counts[edge.type] = (counts[edge.type] || 0) + 1
    }
    return counts
  }, [timeFilteredEdges])

  if (!allowed) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <TopBar />
        <CommandNav />
        <main className="mx-auto max-w-4xl px-4 py-6">
          <div className="rounded-lg border border-osint-red/40 bg-osint-red/10 p-4 text-sm text-osint-red">
            Analyst or admin role required.
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />
      <div className="flex h-[calc(100vh-132px)] w-full flex-col overflow-hidden" style={{ background: "#050507" }}>

        {error ? (
          <div className="border-b border-osint-red/30 bg-osint-red/10 px-4 py-2 font-mono text-[11px] text-osint-red">{error}</div>
        ) : null}

        <div className="flex flex-1 overflow-hidden">
          <GraphSidebar
            activeNodeTypes={activeNodeTypes}
            toggleNodeType={toggleNodeType}
            activeRelTypes={activeRelTypes}
            toggleRelType={toggleRelType}
            selectedNode={selectedNode}
            selectedProfile={selectedProfile}
            loadingProfile={loadingProfile}
            connectedNodes={connectedNodes}
            timeRange={timeRange}
            setTimeRange={setTimeRange}
            nodeTypeCounts={nodeTypeCounts}
          />

          <div className="relative flex-1">
            <GraphCanvas
              nodes={timeFilteredNodes}
              edges={timeFilteredEdges}
              activeNodeTypes={activeNodeTypes}
              activeRelTypes={activeRelTypes}
              selectedNodeId={selectedNodeId}
              hoveredNodeId={hoveredNodeId}
              onSelectNode={setSelectedNodeId}
              onHoverNode={setHoveredNodeId}
              zoom={zoom}
              setZoom={setZoom}
            />
            <GraphControls
              zoom={zoom}
              onZoomIn={() => setZoom((z) => Math.min(3, z * 1.2))}
              onZoomOut={() => setZoom((z) => Math.max(0.3, z * 0.8))}
              onFitToScreen={() => setZoom(1)}
              onRefresh={() => {
                setSelectedNodeId(null)
                setHoveredNodeId(null)
                void loadGraph()
              }}
            />
            <GraphLegend />

            <div
              className="absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full px-4 py-2"
              style={{
                background: "rgba(11,12,16,0.90)",
                border: "1px solid rgba(255,255,255,0.10)",
                backdropFilter: "blur(12px)",
              }}
            >
              {Object.keys(EDGE_COLORS)
                .filter((k) => (edgeCountByType[k] || 0) > 0)
                .slice(0, 4)
                .map((k) => (
                  <span key={k} className="font-mono text-[10px]" style={{ color: EDGE_COLORS[k as RelationshipType] }}>
                    {k}:{edgeCountByType[k]}
                  </span>
                ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
