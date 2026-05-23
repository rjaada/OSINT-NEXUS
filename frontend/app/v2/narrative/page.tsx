"use client"

import { useEffect, useRef, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

const CHANNEL_COLORS: Record<string, string> = {
  rss: "#22c55e",
  telegram: "#f59e0b",
  sensor: "#3b82f6",
  market: "#a855f7",
  other: "#94a3b8",
}

const SUSPICION_COLORS: Record<string, string> = {
  HIGH: "#ef4444",
  MEDIUM: "#f59e0b",
  LOW: "#6b7280",
}

// ── Network mode types ────────────────────────────────────────────────────────

interface RawNode {
  id: string
  channel_type: string
  event_count: number
  clusters: string[]
}

interface GraphEdge {
  source: string
  target: string
  delay_minutes: number
  cluster_id: string
  suspicion_level: string
  common_tokens: string[]
}

interface GraphData {
  nodes: RawNode[]
  edges: GraphEdge[]
  clusters_detected: number
  scanned_at: string
  events_scanned: number
}

// ── Lineage mode types ────────────────────────────────────────────────────────

interface LineageNode {
  id: string
  source: string
  timestamp: string
  description: string
  depth: number
  mutation_score: number
}

interface LineageEdge {
  source: string
  target: string
  similarity: number
  delay_minutes: number
  parallel_origin: boolean
}

interface LineageTree {
  root_id: string
  claim_summary: string
  nodes: LineageNode[]
  edges: LineageEdge[]
  total_nodes: number
  max_mutation: number
  generated_at: string
}

// ── Shared sim node ───────────────────────────────────────────────────────────

interface SimNode {
  id: string
  x: number
  y: number
  vx: number
  vy: number
  // network fields
  channel_type?: string
  event_count?: number
  // lineage fields
  mutation_score?: number
  depth?: number
  source?: string
  description?: string
  timestamp?: string
}

const W = 820
const H = 580

// Delay → edge color in lineage mode (fast = red, slow = gray)
function lineageEdgeColor(delay_min: number): string {
  if (delay_min < 5) return "#ef4444"
  if (delay_min < 30) return "#f59e0b"
  if (delay_min < 120) return "#6b7280"
  return "#374151"
}

export default function NarrativePage() {
  const [mode, setMode] = useState<"network" | "lineage">("network")

  // Network mode state
  const [data, setData] = useState<GraphData | null>(null)
  const [netLoading, setNetLoading] = useState(true)
  const [netError, setNetError] = useState<string | null>(null)

  // Lineage mode state
  const [lineageEventId, setLineageEventId] = useState("")
  const [lineage, setLineage] = useState<LineageTree | null>(null)
  const [linLoading, setLinLoading] = useState(false)
  const [linError, setLinError] = useState<string | null>(null)

  const [selected, setSelected] = useState<string | null>(null)
  const [, forceRender] = useState(0)

  const nodesRef = useRef<SimNode[]>([])
  const rafRef = useRef<number>()
  const frameRef = useRef(0)

  // ── Network data fetch ──────────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${API_BASE}/api/v2/narrative/graph`, { credentials: "include" })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d: GraphData) => {
        setData(d)
        const cx = W / 2, cy = H / 2
        nodesRef.current = d.nodes.map((n, i) => ({
          id: n.id,
          channel_type: n.channel_type,
          event_count: n.event_count,
          x: cx + Math.cos((i / Math.max(d.nodes.length, 1)) * Math.PI * 2) * 160 + (Math.random() - 0.5) * 30,
          y: cy + Math.sin((i / Math.max(d.nodes.length, 1)) * Math.PI * 2) * 140 + (Math.random() - 0.5) * 30,
          vx: 0, vy: 0,
        }))
      })
      .catch(e => setNetError(String(e)))
      .finally(() => setNetLoading(false))
  }, [])

  // ── Lineage fetch ───────────────────────────────────────────────────────────
  function fetchLineage() {
    const id = lineageEventId.trim()
    if (!id) return
    setLinLoading(true)
    setLinError(null)
    setLineage(null)
    fetch(`${API_BASE}/api/v2/claims/${encodeURIComponent(id)}/lineage`, { credentials: "include" })
      .then(r => (r.ok ? r.json() : r.json().then((e: { detail?: string }) => Promise.reject(e.detail || r.status))))
      .then((tree: LineageTree) => {
        setLineage(tree)
        const cx = W / 2, cy = H / 2
        // Pin root to left, spread others radially
        nodesRef.current = tree.nodes.map((n, i) => {
          const isRoot = n.id === tree.root_id
          return {
            id: n.id,
            source: n.source,
            description: n.description,
            timestamp: n.timestamp,
            mutation_score: n.mutation_score,
            depth: n.depth,
            x: isRoot ? 120 : cx + Math.cos((i / Math.max(tree.nodes.length, 1)) * Math.PI * 2) * 180 + (Math.random() - 0.5) * 40,
            y: isRoot ? cy : cy + Math.sin((i / Math.max(tree.nodes.length, 1)) * Math.PI * 2) * 150 + (Math.random() - 0.5) * 40,
            vx: 0, vy: 0,
          }
        })
        frameRef.current = 0
      })
      .catch(e => setLinError(String(e)))
      .finally(() => setLinLoading(false))
  }

  // ── Physics simulation ──────────────────────────────────────────────────────
  const activeEdges = mode === "lineage" && lineage
    ? lineage.edges.map(e => ({ source: e.source, target: e.target }))
    : data?.edges.map(e => ({ source: e.source, target: e.target })) ?? []

  useEffect(() => {
    const nodes = nodesRef.current
    if (nodes.length === 0) return

    const adjSet: Map<string, Set<string>> = new Map()
    for (const e of activeEdges) {
      if (!adjSet.has(e.source)) adjSet.set(e.source, new Set())
      if (!adjSet.has(e.target)) adjSet.set(e.target, new Set())
      adjSet.get(e.source)!.add(e.target)
      adjSet.get(e.target)!.add(e.source)
    }

    const REPULSION = 5000, SPRING_K = 0.035, SPRING_L = 190, GRAVITY = 0.006, DAMP = 0.82
    let alive = true
    frameRef.current = 0

    const tick = () => {
      if (!alive) return
      const ns = nodesRef.current
      const nodeById = new Map(ns.map(n => [n.id, n]))
      const n = ns.length

      for (let i = 0; i < n; i++) {
        const ni = ns[i]
        // Pin root node in lineage mode
        if (mode === "lineage" && lineage && ni.id === lineage.root_id) continue
        let fx = 0, fy = 0

        for (let j = 0; j < n; j++) {
          if (i === j) continue
          const nj = ns[j]
          const dx = ni.x - nj.x, dy = ni.y - nj.y
          const d2 = dx * dx + dy * dy || 1
          const dist = Math.sqrt(d2)
          const f = REPULSION / d2
          fx += (dx / dist) * f
          fy += (dy / dist) * f
        }

        for (const nbId of adjSet.get(ni.id) ?? []) {
          const nj = nodeById.get(nbId)
          if (!nj) continue
          const dx = nj.x - ni.x, dy = nj.y - ni.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const f = SPRING_K * (dist - SPRING_L)
          fx += (dx / dist) * f
          fy += (dy / dist) * f
        }

        fx += (W / 2 - ni.x) * GRAVITY
        fy += (H / 2 - ni.y) * GRAVITY
        ni.vx = (ni.vx + fx) * DAMP
        ni.vy = (ni.vy + fy) * DAMP
        ni.x = Math.max(64, Math.min(W - 64, ni.x + ni.vx))
        ni.y = Math.max(44, Math.min(H - 44, ni.y + ni.vy))
      }

      frameRef.current++
      if (frameRef.current % 2 === 0) forceRender(f => f + 1)
      if (frameRef.current < 320) rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      alive = false
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, lineage, mode])

  const nodeMap = new Map(nodesRef.current.map(n => [n.id, n]))

  // ── Layout ──────────────────────────────────────────────────────────────────
  const loading = mode === "network" ? netLoading : linLoading
  const error = mode === "network" ? netError : linError

  return (
    <div className="flex flex-col h-screen bg-[#05080e] text-white font-mono overflow-hidden">
      <TopBar />
      <CommandNav />

      {/* Sub-header with mode toggle */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 shrink-0">
        <div className="flex items-center gap-3">
          {/* Mode toggle */}
          <div className="flex gap-1">
            {(["network", "lineage"] as const).map(m => (
              <button
                key={m}
                onClick={() => { setMode(m); setSelected(null) }}
                className={`text-[9px] tracking-[0.15em] uppercase px-2 py-0.5 rounded border transition-colors ${
                  mode === m
                    ? "border-white/40 text-white/80 bg-white/5"
                    : "border-white/10 text-white/25 hover:text-white/50"
                }`}
              >
                {m === "network" ? "Source Network" : "Claim Lineage"}
              </button>
            ))}
          </div>
          <span className="text-[9px] text-white/20">·</span>
          {mode === "network" && data && (
            <span className="text-[9px] text-white/40">
              {data.nodes.length} sources · {data.edges.length} links · {data.clusters_detected} clusters
            </span>
          )}
          {mode === "lineage" && lineage && (
            <span className="text-[9px] text-white/40">
              {lineage.total_nodes} sources · max mutation {(lineage.max_mutation * 100).toFixed(0)}%
            </span>
          )}
        </div>

        {mode === "network" && (
          <div className="flex items-center gap-4 text-[9px] text-white/25">
            {Object.entries(CHANNEL_COLORS).map(([t, c]) => (
              <span key={t} className="flex items-center gap-1 uppercase">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: c }} />
                {t}
              </span>
            ))}
            <span className="text-white/10 mx-1">|</span>
            {Object.entries(SUSPICION_COLORS).map(([l, c]) => (
              <span key={l} className="text-[9px]" style={{ color: c }}>{l}</span>
            ))}
          </div>
        )}

        {mode === "lineage" && (
          <div className="flex items-center gap-2">
            <input
              className="bg-transparent border border-white/15 rounded px-2 py-0.5 text-[10px] text-white/70 placeholder-white/20 w-52 focus:outline-none focus:border-white/30"
              placeholder="Event ID…"
              value={lineageEventId}
              onChange={e => setLineageEventId(e.target.value)}
              onKeyDown={e => e.key === "Enter" && fetchLineage()}
            />
            <button
              onClick={fetchLineage}
              disabled={linLoading}
              className="text-[9px] uppercase tracking-widest px-2 py-0.5 border border-white/15 rounded text-white/40 hover:text-white/70 hover:border-white/30 transition-colors disabled:opacity-40"
            >
              {linLoading ? "…" : "Trace"}
            </button>
          </div>
        )}
      </div>

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        {/* Graph area */}
        <div className="flex-1 flex items-center justify-center relative overflow-hidden">

          {/* Lineage mode empty state */}
          {mode === "lineage" && !lineage && !linLoading && !linError && (
            <div className="flex flex-col items-center gap-2 text-white/20 font-mono text-xs">
              <div className="tracking-widest">ENTER AN EVENT ID TO TRACE ITS CLAIM</div>
              <div className="text-white/10 text-[9px]">Paste any event ID from the operations feed</div>
            </div>
          )}

          {/* Loading spinner */}
          {loading && (
            <div className="text-white/30 text-xs tracking-widest">
              {mode === "network" ? "SCANNING NARRATIVE PROPAGATION…" : "TRACING CLAIM LINEAGE…"}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="text-red-400 text-xs">FETCH ERROR — {error}</div>
          )}

          {/* Network empty state */}
          {mode === "network" && !netLoading && !netError && data && data.nodes.length === 0 && (
            <div className="flex flex-col items-center gap-2 text-white/20 text-xs">
              <div className="tracking-widest">NO COORDINATED CLUSTERS DETECTED</div>
              <div className="text-white/10">{data.events_scanned ?? 0} events scanned</div>
            </div>
          )}

          {/* Graph SVG — shown when nodes are available */}
          {nodesRef.current.length > 0 && !loading && !error && (
            <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="max-w-full max-h-full">
              <defs>
                {mode === "network" && Object.entries(SUSPICION_COLORS).map(([level, color]) => (
                  <marker key={level} id={`arr-${level}`} viewBox="0 0 10 10" refX="22" refY="5"
                    markerWidth="5" markerHeight="5" orient="auto">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
                  </marker>
                ))}
                {mode === "lineage" && (
                  <marker id="arr-lineage" viewBox="0 0 10 10" refX="22" refY="5"
                    markerWidth="5" markerHeight="5" orient="auto">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#6b7280" />
                  </marker>
                )}
              </defs>

              {/* ── Network edges ── */}
              {mode === "network" && data?.edges.map((edge, i) => {
                const s = nodeMap.get(edge.source), t = nodeMap.get(edge.target)
                if (!s || !t) return null
                const color = SUSPICION_COLORS[edge.suspicion_level] || "#6b7280"
                const highlighted = selected === edge.source || selected === edge.target
                const mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2
                return (
                  <g key={i}>
                    <line x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                      stroke={color} strokeWidth={highlighted ? 1.8 : 0.8}
                      strokeOpacity={highlighted ? 0.85 : 0.25}
                      markerEnd={`url(#arr-${edge.suspicion_level})`} />
                    {highlighted && edge.delay_minutes > 0 && (
                      <text x={mx} y={my - 5} fill={color} fontSize={8} textAnchor="middle" opacity={0.8}>
                        +{edge.delay_minutes}m
                      </text>
                    )}
                  </g>
                )
              })}

              {/* ── Lineage edges ── */}
              {mode === "lineage" && lineage?.edges.map((edge, i) => {
                const s = nodeMap.get(edge.source), t = nodeMap.get(edge.target)
                if (!s || !t) return null
                const color = lineageEdgeColor(edge.delay_minutes)
                const highlighted = selected === edge.source || selected === edge.target
                const mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2
                return (
                  <g key={i}>
                    <line x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                      stroke={color} strokeWidth={highlighted ? 2 : 0.9}
                      strokeOpacity={highlighted ? 0.9 : edge.parallel_origin ? 0.15 : 0.35}
                      strokeDasharray={edge.parallel_origin ? "4 3" : undefined}
                      markerEnd="url(#arr-lineage)" />
                    {highlighted && (
                      <text x={mx} y={my - 5} fill={color} fontSize={8} textAnchor="middle" opacity={0.85}>
                        +{edge.delay_minutes}m {edge.parallel_origin ? "⟂" : ""}
                      </text>
                    )}
                  </g>
                )
              })}

              {/* ── Network nodes ── */}
              {mode === "network" && nodesRef.current.map(node => {
                const color = CHANNEL_COLORS[node.channel_type || "other"] || "#94a3b8"
                const isSelected = selected === node.id
                const r = 8 + Math.min((node.event_count ?? 0) * 2, 18)
                return (
                  <g key={node.id}
                    transform={`translate(${node.x.toFixed(1)},${node.y.toFixed(1)})`}
                    onClick={() => setSelected(isSelected ? null : node.id)}
                    style={{ cursor: "pointer" }}>
                    {isSelected && <circle r={r + 8} fill={color} opacity={0.12} />}
                    <circle r={r} fill={color} fillOpacity={isSelected ? 0.3 : 0.15}
                      stroke={color} strokeWidth={isSelected ? 1.8 : 1} strokeOpacity={0.85} />
                    <text fill={color} fontSize={8} textAnchor="middle" dy={3}
                      style={{ pointerEvents: "none", userSelect: "none", fontWeight: "bold" }}>
                      {node.event_count}
                    </text>
                    <text y={r + 14} fill="rgba(255,255,255,0.55)" fontSize={8} textAnchor="middle"
                      style={{ pointerEvents: "none", userSelect: "none" }}>
                      {node.id.length > 20 ? node.id.slice(0, 20) + "…" : node.id}
                    </text>
                  </g>
                )
              })}

              {/* ── Lineage nodes ── */}
              {mode === "lineage" && nodesRef.current.map(node => {
                const isRoot = lineage?.root_id === node.id
                const mutation = node.mutation_score ?? 0
                const r = isRoot ? 14 : 8 + Math.round(mutation * 22)
                const color = isRoot ? "#facc15" : mutation > 0.6 ? "#ef4444" : mutation > 0.3 ? "#f59e0b" : "#22c55e"
                const isSelected = selected === node.id
                return (
                  <g key={node.id}
                    transform={`translate(${node.x.toFixed(1)},${node.y.toFixed(1)})`}
                    onClick={() => setSelected(isSelected ? null : node.id)}
                    style={{ cursor: "pointer" }}>
                    {isRoot && <circle r={r + 10} fill="#facc15" opacity={0.08} />}
                    {isSelected && <circle r={r + 7} fill={color} opacity={0.12} />}
                    <circle r={r} fill={color} fillOpacity={isSelected ? 0.35 : 0.18}
                      stroke={color} strokeWidth={isRoot ? 2 : isSelected ? 1.8 : 1} strokeOpacity={0.9} />
                    <text fill={color} fontSize={7} textAnchor="middle" dy={3}
                      style={{ pointerEvents: "none", userSelect: "none", fontWeight: "bold" }}>
                      {isRoot ? "ROOT" : `${(mutation * 100).toFixed(0)}%`}
                    </text>
                    <text y={r + 13} fill="rgba(255,255,255,0.5)" fontSize={7.5} textAnchor="middle"
                      style={{ pointerEvents: "none", userSelect: "none" }}>
                      {(node.source || node.id).slice(0, 18)}
                    </text>
                  </g>
                )
              })}
            </svg>
          )}

          <div className="absolute bottom-3 left-4 text-[8px] text-white/15 leading-relaxed">
            {mode === "network"
              ? "Node size = event count · Edge = propagation direction · Click node to inspect"
              : "Node size = claim mutation · Yellow = origin · Red edge = fast spread · Dashed = parallel origin"}
            <br />
            Suspicion flag only — analyst verification required before action
          </div>
        </div>

        {/* Sidebar */}
        {selected && (
          <div className="w-64 border-l border-white/10 flex flex-col overflow-hidden shrink-0">
            <div className="px-4 pt-4 pb-3 border-b border-white/10">
              <div className="text-[8px] tracking-widest text-white/25 uppercase mb-1">
                {mode === "network" ? "Source" : "Event"}
              </div>
              {(() => {
                const node = nodesRef.current.find(n => n.id === selected)
                if (!node) return null
                if (mode === "network") {
                  const color = CHANNEL_COLORS[node.channel_type || "other"] || "#94a3b8"
                  return (
                    <>
                      <div className="text-[11px] font-bold leading-snug" style={{ color }}>{node.id}</div>
                      <div className="text-[9px] text-white/30 mt-0.5 uppercase">
                        {node.channel_type} · {node.event_count} events in clusters
                      </div>
                    </>
                  )
                }
                const isRoot = lineage?.root_id === node.id
                const mutation = node.mutation_score ?? 0
                const color = isRoot ? "#facc15" : mutation > 0.6 ? "#ef4444" : mutation > 0.3 ? "#f59e0b" : "#22c55e"
                return (
                  <>
                    <div className="text-[11px] font-bold leading-snug" style={{ color }}>
                      {node.source || node.id}
                    </div>
                    <div className="text-[9px] text-white/30 mt-0.5">
                      {isRoot ? "ORIGIN · " : ""}Depth {node.depth ?? 0} · {(mutation * 100).toFixed(0)}% mutated
                    </div>
                    {node.description && (
                      <div className="text-[9px] text-white/40 mt-1 leading-snug line-clamp-3">
                        {node.description}
                      </div>
                    )}
                    {node.timestamp && (
                      <div className="text-[8px] text-white/20 mt-1">{node.timestamp.slice(0, 19).replace("T", " ")} UTC</div>
                    )}
                  </>
                )
              })()}
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-3">
              <div className="text-[8px] tracking-widest text-white/25 uppercase mb-2">
                {mode === "network" ? "Propagation Links" : "Claim Links"}
              </div>

              {mode === "network" && (() => {
                const selectedEdges = data
                  ? data.edges.filter(e => e.source === selected || e.target === selected)
                  : []
                if (selectedEdges.length === 0) return (
                  <div className="text-[9px] text-white/20">No directed links</div>
                )
                return selectedEdges.map((e, i) => {
                  const isSource = e.source === selected
                  const other = isSource ? e.target : e.source
                  const slColor = SUSPICION_COLORS[e.suspicion_level] || "#6b7280"
                  return (
                    <div key={i} className="mb-3 pb-3 border-b border-white/5 last:border-0">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span style={{ color: slColor }} className="text-[10px]">{isSource ? "→" : "←"}</span>
                        <span className="text-[10px] text-white/65 leading-snug">{other}</span>
                      </div>
                      <div className="text-[8px] text-white/30 mb-0.5">
                        {isSource ? "propagated to" : "received from"} ·{" "}
                        {e.delay_minutes > 0 ? `+${e.delay_minutes}m` : "simultaneously"}
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="text-[8px] px-1 py-0.5 rounded border"
                          style={{ color: slColor, borderColor: slColor + "44" }}>
                          {e.suspicion_level}
                        </span>
                      </div>
                      {e.common_tokens.length > 0 && (
                        <div className="text-[8px] text-white/20 mt-1">{e.common_tokens.join(" · ")}</div>
                      )}
                    </div>
                  )
                })
              })()}

              {mode === "lineage" && (() => {
                const linEdges = lineage
                  ? lineage.edges.filter(e => e.source === selected || e.target === selected)
                  : []
                if (linEdges.length === 0) return (
                  <div className="text-[9px] text-white/20">No lineage links</div>
                )
                return linEdges.map((e, i) => {
                  const isSource = e.source === selected
                  const other = isSource ? e.target : e.source
                  const color = lineageEdgeColor(e.delay_minutes)
                  return (
                    <div key={i} className="mb-3 pb-3 border-b border-white/5 last:border-0">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span style={{ color }} className="text-[10px]">{isSource ? "→" : "←"}</span>
                        <span className="text-[10px] text-white/65 leading-snug">{other.slice(0, 22)}</span>
                      </div>
                      <div className="text-[8px] text-white/30 mb-1">
                        {isSource ? "claim spread to" : "received claim from"} ·{" "}
                        {e.delay_minutes > 0 ? `+${e.delay_minutes}m` : "simultaneously"}
                        {e.parallel_origin && " · parallel origin"}
                      </div>
                      <div className="text-[8px] text-white/25">
                        similarity {(e.similarity * 100).toFixed(0)}%
                      </div>
                    </div>
                  )
                })
              })()}
            </div>

            <button
              onClick={() => setSelected(null)}
              className="mx-4 mb-4 py-1.5 text-[9px] tracking-widest uppercase text-white/25 border border-white/10 rounded hover:text-white/50 hover:border-white/20 transition-colors"
            >
              Clear Selection
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
