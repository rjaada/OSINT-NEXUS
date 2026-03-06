"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
type AssessState = { loading: boolean; text: string; offline: boolean }

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

const CLUSTER_META: Record<string, { label: string }> = {
  lebanon: { label: "Lebanon Theater" },
  gaza: { label: "Gaza Strip" },
  iran_nuclear: { label: "Iran Nuclear" },
  red_sea_hormuz: { label: "Red Sea / Strait of Hormuz" },
  iraq_pmf: { label: "Iraq PMF" },
  syria_conflict: { label: "Syria Conflict" },
  source_hub: { label: "Source Hub" },
  general: { label: "General Theater" },
}

function slugSource(input: string): string {
  return input.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "unknown"
}

function sourceReliability(name: string): number {
  const key = name.toLowerCase()
  if (key.includes("reuters")) return 82
  if (key.includes("bbc")) return 81
  if (key.includes("guardian")) return 78
  if (key.includes("al jazeera")) return 74
  if (key.includes("times of israel")) return 70
  if (key.includes("aj mubasher")) return 58
  if (key.includes("roaa")) return 56
  if (key.includes("firms") || key.includes("nasa")) return 86
  return 60
}

function toIso(value: unknown): string {
  const date = new Date(String(value || ""))
  return Number.isNaN(date.getTime()) ? new Date().toISOString() : date.toISOString()
}

function dtg(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "UNKNOWN"
  const day = String(d.getUTCDate()).padStart(2, "0")
  const hh = String(d.getUTCHours()).padStart(2, "0")
  const mm = String(d.getUTCMinutes()).padStart(2, "0")
  const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
  return `${day}${hh}${mm}Z${months[d.getUTCMonth()]}${d.getUTCFullYear()}`
}

function inferCluster(node: GraphNode): string {
  const payload = `${node.label} ${JSON.stringify(node.properties || {})}`.toLowerCase()
  if (payload.includes("lebanon") || payload.includes("hezb")) return "lebanon"
  if (payload.includes("gaza") || payload.includes("rafah") || payload.includes("hamas")) return "gaza"
  if (payload.includes("iran") || payload.includes("tehran") || payload.includes("nuclear")) return "iran_nuclear"
  if (payload.includes("red sea") || payload.includes("hormuz") || payload.includes("houthi") || payload.includes("yemen")) return "red_sea_hormuz"
  if (payload.includes("iraq") || payload.includes("pmf") || payload.includes("baghdad")) return "iraq_pmf"
  if (payload.includes("syria") || payload.includes("aleppo") || payload.includes("idlib")) return "syria_conflict"
  if (node.type === "SOURCE") return "source_hub"
  return "general"
}

function hexToRgb(hex: string) {
  const text = hex.replace("#", "")
  const value = text.length === 3 ? text.split("").map((x) => x + x).join("") : text
  const num = parseInt(value, 16)
  return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 }
}

function rgbToHex(r: number, g: number, b: number) {
  return `#${[r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("")}`
}

function blendClusterColor(nodes: GraphNode[]) {
  if (nodes.length === 0) return "#8f9ab6"
  let r = 0
  let g = 0
  let b = 0
  for (const node of nodes) {
    const rgb = hexToRgb(
      node.type === "EVENT"
        ? "#ff1a3c"
        : node.type === "ACTOR"
          ? "#ffa630"
          : node.type === "LOCATION"
            ? "#00b4d8"
            : node.type === "SOURCE"
              ? "#00ff88"
              : node.type === "INCIDENT"
                ? "#c77dff"
                : "#ffd166",
    )
    r += rgb.r
    g += rgb.g
    b += rgb.b
  }
  return rgbToHex(r / nodes.length, g / nodes.length, b / nodes.length)
}

function dominantNodeType(nodes: GraphNode[]): NodeType {
  const count: Record<string, number> = {}
  nodes.forEach((n) => {
    count[n.type] = (count[n.type] || 0) + 1
  })
  return (Object.entries(count).sort((a, b) => b[1] - a[1])[0]?.[0] as NodeType) || "UNKNOWN"
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
        timestamp: String(event.timestamp || now),
        incident_id: String(event.incident_id || ""),
        type: String(event.type || "EVENT"),
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
      properties: { source, reliability: sourceReliability(source) },
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
  const edgesRef = useRef<GraphEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [offline, setOffline] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [centerNodeId, setCenterNodeId] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [timeRange, setTimeRange] = useState(72)
  const [activeNodeTypes, setActiveNodeTypes] = useState<Set<NodeType>>(new Set(["EVENT", "ACTOR", "LOCATION", "SOURCE", "INCIDENT", "TYPE"]))
  const [activeRelTypes, setActiveRelTypes] = useState<Set<RelationshipType>>(new Set())
  const [selectedProfile, setSelectedProfile] = useState<GraphNodeProfile | null>(null)
  const [loadingProfile, setLoadingProfile] = useState(false)
  const [backendTag, setBackendTag] = useState("")
  const [search, setSearch] = useState("")
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set())
  const [aiAssess, setAiAssess] = useState<AssessState>({ loading: false, text: "", offline: false })
  const wsBase = useMemo(() => {
    const fromEnv = process.env.NEXT_PUBLIC_WS_URL
    if (fromEnv) return fromEnv
    if (typeof window === "undefined") return "ws://localhost:8000"
    const proto = window.location.protocol === "https:" ? "wss" : "ws"
    return `${proto}://${window.location.host}`
  }, [])

  const allowed = role === "analyst" || role === "admin"

  useEffect(() => {
    edgesRef.current = edges
  }, [edges])

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
    const ws = new WebSocket(`${wsBase}/ws/live/v2`)
    let ping: ReturnType<typeof setInterval> | null = null

    ws.onopen = () => {
      ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping")
      }, 18000)
    }
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data) as { type?: string; data?: Record<string, unknown> }
        if ((msg.type === "NEW_EVENT" || msg.type === "NEW_EVENT_DIFF") && msg.data) {
          setNodes((prevNodes) => {
            const result = addLiveEvent(prevNodes, edgesRef.current, msg.data as Record<string, unknown>)
            edgesRef.current = result.edges
            setEdges(result.edges)
            return result.nodes
          })
        }
      } catch {
        // no-op
      }
    }
    ws.onclose = () => {
      if (ping) clearInterval(ping)
    }

    return () => {
      if (ping) clearInterval(ping)
      ws.close()
    }
  }, [allowed, wsBase])

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

  const baseNodeSet = useMemo(() => new Set(timeFilteredNodes.map((n) => n.id)), [timeFilteredNodes])

  const timeFilteredEdges = useMemo(
    () => edges.filter((edge) => baseNodeSet.has(edge.source) && baseNodeSet.has(edge.target)),
    [edges, baseNodeSet],
  )

  const clustered = useMemo(() => {
    const groups = new Map<string, GraphNode[]>()
    timeFilteredNodes.forEach((node) => {
      const key = inferCluster(node)
      const arr = groups.get(key) || []
      arr.push(node)
      groups.set(key, arr)
    })

    const displayNodes: GraphNode[] = []
    const nodeMap = new Map<string, string>()
    const clusterIds = new Set<string>()

    for (const [clusterKey, clusterNodes] of groups.entries()) {
      const expanded = expandedClusters.has(clusterKey)
      if (expanded || clusterNodes.length <= 1) {
        clusterNodes.forEach((node) => {
          displayNodes.push(node)
          nodeMap.set(node.id, node.id)
        })
        continue
      }

      const clusterNodeId = `cluster:${clusterKey}`
      clusterIds.add(clusterNodeId)
      clusterNodes.forEach((node) => nodeMap.set(node.id, clusterNodeId))

      const avgX = clusterNodes.reduce((sum, n) => sum + n.x, 0) / clusterNodes.length
      const avgY = clusterNodes.reduce((sum, n) => sum + n.y, 0) / clusterNodes.length
      const dominant = dominantNodeType(clusterNodes)
      const created = clusterNodes.map((n) => toIso(n.created)).sort()[0] || new Date().toISOString()
      const lastSeen = clusterNodes.map((n) => toIso(n.lastSeen)).sort().reverse()[0] || new Date().toISOString()

      displayNodes.push({
        id: clusterNodeId,
        type: dominant,
        label: CLUSTER_META[clusterKey]?.label || "Cluster",
        created,
        lastSeen,
        confidence: Math.round(
          clusterNodes.reduce((sum, n) => sum + Number(n.confidence || 0), 0) / Math.max(1, clusterNodes.length),
        ),
        connections: 0,
        x: avgX,
        y: avgY,
        vx: 0,
        vy: 0,
        cluster: clusterKey,
        properties: {
          is_cluster: true,
          cluster_id: clusterKey,
          cluster_count: clusterNodes.length,
          cluster_color: blendClusterColor(clusterNodes),
          cluster_types: Array.from(new Set(clusterNodes.map((n) => n.type))),
        },
      })
    }

    const seenEdges = new Set<string>()
    const displayEdges: GraphEdge[] = []
    for (const edge of timeFilteredEdges) {
      const src = nodeMap.get(edge.source) || edge.source
      const dst = nodeMap.get(edge.target) || edge.target
      if (src === dst) continue
      const key = `${src}|${edge.type}|${dst}`
      if (seenEdges.has(key)) continue
      seenEdges.add(key)
      displayEdges.push({ ...edge, id: `agg:${key}`, source: src, target: dst })
    }

    const conn = new Map<string, number>()
    displayEdges.forEach((e) => {
      conn.set(e.source, (conn.get(e.source) || 0) + 1)
      conn.set(e.target, (conn.get(e.target) || 0) + 1)
    })
    displayNodes.forEach((n) => {
      n.connections = conn.get(n.id) || 0
    })

    return { nodes: displayNodes, edges: displayEdges, clusterIds }
  }, [timeFilteredNodes, timeFilteredEdges, expandedClusters])

  const selectedNode = useMemo(
    () => (selectedNodeId ? clustered.nodes.find((node) => node.id === selectedNodeId) || null : null),
    [selectedNodeId, clustered.nodes],
  )

  const connectedNodes = useMemo(() => {
    if (!selectedNodeId) return []
    const connectedIds = new Set<string>()
    clustered.edges.forEach((edge) => {
      if (edge.source === selectedNodeId) connectedIds.add(edge.target)
      if (edge.target === selectedNodeId) connectedIds.add(edge.source)
    })
    return clustered.nodes.filter((node) => connectedIds.has(node.id))
  }, [selectedNodeId, clustered.edges, clustered.nodes])

  const highlightedNodeIds = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return new Set<string>()
    return new Set(
      clustered.nodes
        .filter((node) => `${node.label} ${JSON.stringify(node.properties || {})}`.toLowerCase().includes(q))
        .map((node) => node.id),
    )
  }, [search, clustered.nodes])

  const edgeCountByType = useMemo(() => {
    const counts: Record<string, number> = {}
    clustered.edges.forEach((edge) => {
      counts[edge.type] = (counts[edge.type] || 0) + 1
    })
    return counts
  }, [clustered.edges])

  const handleNodeSelect = useCallback((id: string | null) => {
    if (id && id.startsWith("cluster:")) {
      const key = id.replace("cluster:", "")
      setExpandedClusters((prev) => {
        const next = new Set(prev)
        if (next.has(key)) next.delete(key)
        else next.add(key)
        return next
      })
      return
    }
    setSelectedNodeId(id)
    setCenterNodeId(id)
  }, [])

  useEffect(() => {
    if (!selectedNodeId || selectedNodeId.startsWith("cluster:") || !allowed) {
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
        if (mounted) setSelectedProfile(data)
      } catch {
        if (mounted) setSelectedProfile(null)
      } finally {
        if (mounted) setLoadingProfile(false)
      }
    }
    void loadProfile()
    return () => {
      mounted = false
    }
  }, [selectedNodeId, allowed])

  useEffect(() => {
    if (!selectedNode || selectedNode.id.startsWith("cluster:")) {
      setAiAssess({ loading: false, text: "", offline: false })
      return
    }
    let mounted = true
    const loadAssessment = async () => {
      setAiAssess({ loading: true, text: "", offline: false })
      try {
        const res = await fetch(`${API_BASE}/api/v2/graph/node/assess`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            node_id: selectedNode.id,
            node_type: selectedNode.type,
            node_data: {
              label: selectedNode.label,
              ...selectedNode.properties,
              connections: selectedNode.connections,
              source: selectedNode.properties?.source || selectedNode.label,
              reliability: selectedNode.type === "SOURCE" ? sourceReliability(selectedNode.label) : undefined,
            },
          }),
        })
        if (!res.ok) {
          if (mounted) setAiAssess({ loading: false, text: "AI ANALYST OFFLINE", offline: true })
          return
        }
        const data = await res.json()
        if (!mounted) return
        setAiAssess({
          loading: false,
          text: String(data?.assessment || "AI ANALYST OFFLINE"),
          offline: Boolean(data?.offline),
        })
      } catch {
        if (!mounted) return
        setAiAssess({ loading: false, text: "AI ANALYST OFFLINE", offline: true })
      }
    }
    void loadAssessment()
    return () => {
      mounted = false
    }
  }, [selectedNode])

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
            selectedNode={null}
            selectedProfile={null}
            loadingProfile={false}
            connectedNodes={[]}
            timeRange={timeRange}
            setTimeRange={setTimeRange}
            nodeTypeCounts={nodeTypeCounts}
          />

          <div className="relative flex-1">
            <div className="absolute left-4 top-4 z-20 flex items-center gap-2 rounded-lg border border-white/10 bg-[rgba(11,12,16,0.88)] px-3 py-2 backdrop-blur-md">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setSearch("")
                    return
                  }
                  if (e.key === "Enter") {
                    const first = Array.from(highlightedNodeIds)[0]
                    if (first) {
                      handleNodeSelect(first)
                      setCenterNodeId(first)
                    }
                  }
                }}
                placeholder="Search nodes..."
                className="w-56 bg-transparent font-mono text-[11px] text-[#dbe4ff] outline-none placeholder:text-[#73809d]"
                style={{ borderColor: "rgba(255,26,60,0.4)" }}
              />
              <button
                onClick={() => setSearch("")}
                className="rounded border border-white/15 px-2 py-0.5 font-mono text-[9px] text-muted-foreground hover:text-white"
              >
                ESC
              </button>
            </div>

            <div className="absolute right-4 top-4 z-20 flex items-center gap-2">
              <button
                onClick={() => setExpandedClusters(new Set(Object.keys(CLUSTER_META)))}
                className="rounded border border-white/15 bg-[rgba(11,12,16,0.88)] px-3 py-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-white"
              >
                Expand All
              </button>
              <button
                onClick={() => setExpandedClusters(new Set())}
                className="rounded border border-white/15 bg-[rgba(11,12,16,0.88)] px-3 py-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-white"
              >
                Collapse All
              </button>
            </div>

            <GraphCanvas
              nodes={clustered.nodes}
              edges={clustered.edges}
              activeNodeTypes={activeNodeTypes}
              activeRelTypes={activeRelTypes}
              selectedNodeId={selectedNodeId}
              hoveredNodeId={hoveredNodeId}
              onSelectNode={handleNodeSelect}
              onHoverNode={setHoveredNodeId}
              zoom={zoom}
              setZoom={setZoom}
              focusNodeId={selectedNodeId}
              highlightedNodeIds={highlightedNodeIds}
              centerOnNodeId={centerNodeId}
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

            <aside
              className={`absolute right-0 top-0 z-30 h-full w-[320px] border-l border-white/10 bg-[rgba(11,12,16,0.9)] p-4 backdrop-blur-md transition-transform duration-200 ${
                selectedNode ? "translate-x-0" : "translate-x-full"
              }`}
            >
              {selectedNode ? (
                <>
                  <div className="mb-3 flex items-center justify-between">
                    <span className="rounded border border-osint-red/50 px-2 py-0.5 font-mono text-[10px] uppercase text-osint-red">
                      {selectedNode.type}
                    </span>
                    <button
                      onClick={() => setSelectedNodeId(null)}
                      className="rounded border border-white/20 px-2 py-1 font-mono text-[9px] text-muted-foreground hover:text-white"
                    >
                      CLOSE
                    </button>
                  </div>

                  <p className="font-mono text-[10px] text-[#9fabc8]">ID: {selectedNode.id}</p>
                  <p className="mt-1 text-lg font-semibold text-white">{selectedNode.label}</p>
                  <div className="mt-3 rounded border border-white/10 bg-black/20 p-3">
                    {selectedNode.type === "EVENT" ? (
                      <div className="space-y-1 font-mono text-[11px] text-[#cfd7ea]">
                        <p>CLASS: {String(selectedNode.properties?.type || selectedNode.label).toUpperCase()}</p>
                        <p>CONFIDENCE: {Math.round(Number(selectedNode.confidence || selectedNode.properties?.confidence_score || 0))}</p>
                        <p>SOURCE: {String(selectedNode.properties?.source || "Unknown")}</p>
                        <p>DTG: {dtg(String(selectedNode.properties?.timestamp || selectedNode.lastSeen))}</p>
                        <p>LOCATION: {String(selectedNode.properties?.lat ?? "N/A")}, {String(selectedNode.properties?.lng ?? "N/A")}</p>
                        <p className="pt-1 text-[10px] text-[#b2bed7]">{String(selectedNode.properties?.description || "No description")}</p>
                      </div>
                    ) : selectedNode.type === "SOURCE" ? (
                      <div className="space-y-1 font-mono text-[11px] text-[#cfd7ea]">
                        <p>TYPE: {String(selectedNode.properties?.source_type || "Telegram/RSS/Satellite")}</p>
                        <p>RELIABILITY: {sourceReliability(selectedNode.label)}</p>
                        <p>TOTAL EVENTS: {selectedNode.connections}</p>
                        <p>LAST ACTIVE: {dtg(selectedNode.lastSeen)}</p>
                      </div>
                    ) : selectedNode.type === "INCIDENT" ? (
                      <div className="space-y-1 font-mono text-[11px] text-[#cfd7ea]">
                        <p>EVENT COUNT: {selectedNode.connections}</p>
                        <p>AREA: {String(selectedNode.properties?.theater || selectedNode.cluster || "Mixed Theater")}</p>
                        <p>TIME SPAN: {dtg(selectedNode.created)} → {dtg(selectedNode.lastSeen)}</p>
                        <p>CONFIDENCE: {Math.round(Number(selectedNode.confidence || 0))}</p>
                      </div>
                    ) : selectedNode.type === "TYPE" ? (
                      <div className="space-y-1 font-mono text-[11px] text-[#cfd7ea]">
                        <p>CLASS TYPE: {selectedNode.label}</p>
                        <p>EVENT COUNT: {selectedNode.connections}</p>
                        <p>TREND: {String(selectedNode.properties?.trend || "Live ingestion")}</p>
                      </div>
                    ) : (
                      <div className="space-y-1 font-mono text-[11px] text-[#cfd7ea]">
                        <p>CONNECTED: {selectedNode.connections}</p>
                        <p>LAST SEEN: {dtg(selectedNode.lastSeen)}</p>
                      </div>
                    )}
                  </div>

                  <div className="mt-3">
                    <p className="font-mono text-[9px] uppercase tracking-[0.15em] text-osint-blue">Connected Nodes</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {connectedNodes.slice(0, 16).map((node) => (
                        <button
                          key={node.id}
                          onClick={() => {
                            handleNodeSelect(node.id)
                            setCenterNodeId(node.id)
                          }}
                          className="rounded border border-white/15 px-2 py-1 font-mono text-[9px] text-[#dbe4ff] hover:border-osint-blue/50"
                        >
                          {node.label.length > 24 ? `${node.label.slice(0, 24)}...` : node.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="mt-4 rounded border border-osint-red/30 bg-black/25 p-3">
                    <p className="font-mono text-[9px] uppercase tracking-[0.15em] text-osint-red">AI ANALYST // ADVISORY</p>
                    {aiAssess.loading ? (
                      <p className="mt-2 font-mono text-[11px] text-muted-foreground">Generating assessment...</p>
                    ) : (
                      <p className={`mt-2 text-[12px] leading-relaxed ${aiAssess.offline ? "font-mono text-osint-amber" : "text-[#d4ddf5]"}`}>
                        {aiAssess.text || "AI ANALYST OFFLINE"}
                      </p>
                    )}
                  </div>

                  {loadingProfile ? (
                    <p className="mt-3 font-mono text-[10px] text-muted-foreground">Loading node profile...</p>
                  ) : selectedProfile ? (
                    <p className="mt-3 font-mono text-[10px] text-[#9eb0cd]">
                      Incoming: {selectedProfile.incoming.length} · Outgoing: {selectedProfile.outgoing.length}
                    </p>
                  ) : null}
                </>
              ) : null}
            </aside>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-black/55">
          <p className="font-mono text-[12px] uppercase tracking-[0.2em] text-osint-blue">{offline ? "GRAPH OFFLINE" : "Loading graph..."}</p>
        </div>
      ) : null}
    </div>
  )
}
