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

interface RawNode {
  id: string
  channel_type: string
  event_count: number
  clusters: string[]
}

interface SimNode extends RawNode {
  x: number
  y: number
  vx: number
  vy: number
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

const W = 820
const H = 580

export default function NarrativePage() {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [, forceRender] = useState(0)

  const nodesRef = useRef<SimNode[]>([])
  const rafRef = useRef<number>()
  const frameRef = useRef(0)

  useEffect(() => {
    fetch(`${API_BASE}/api/v2/narrative/graph`, { credentials: "include" })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d: GraphData) => {
        setData(d)
        const cx = W / 2
        const cy = H / 2
        nodesRef.current = d.nodes.map((n, i) => ({
          ...n,
          x: cx + Math.cos((i / Math.max(d.nodes.length, 1)) * Math.PI * 2) * 160 + (Math.random() - 0.5) * 30,
          y: cy + Math.sin((i / Math.max(d.nodes.length, 1)) * Math.PI * 2) * 140 + (Math.random() - 0.5) * 30,
          vx: 0,
          vy: 0,
        }))
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!data || nodesRef.current.length === 0) return

    const adjSet: Map<string, Set<string>> = new Map()
    for (const e of data.edges) {
      if (!adjSet.has(e.source)) adjSet.set(e.source, new Set())
      if (!adjSet.has(e.target)) adjSet.set(e.target, new Set())
      adjSet.get(e.source)!.add(e.target)
      adjSet.get(e.target)!.add(e.source)
    }

    const REPULSION = 5000
    const SPRING_K = 0.035
    const SPRING_L = 190
    const GRAVITY = 0.006
    const DAMP = 0.82
    let alive = true
    frameRef.current = 0

    const tick = () => {
      if (!alive) return
      const nodes = nodesRef.current
      const nodeById = new Map(nodes.map(n => [n.id, n]))
      const n = nodes.length

      for (let i = 0; i < n; i++) {
        const ni = nodes[i]
        let fx = 0, fy = 0

        for (let j = 0; j < n; j++) {
          if (i === j) continue
          const nj = nodes[j]
          const dx = ni.x - nj.x
          const dy = ni.y - nj.y
          const d2 = dx * dx + dy * dy || 1
          const dist = Math.sqrt(d2)
          const f = REPULSION / d2
          fx += (dx / dist) * f
          fy += (dy / dist) * f
        }

        for (const nbId of adjSet.get(ni.id) ?? []) {
          const nj = nodeById.get(nbId)
          if (!nj) continue
          const dx = nj.x - ni.x
          const dy = nj.y - ni.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const ext = dist - SPRING_L
          const f = SPRING_K * ext
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
  }, [data])

  const nodeMap = new Map(nodesRef.current.map(n => [n.id, n]))

  if (loading) return (
    <div className="flex flex-col h-screen bg-[#05080e]">
      <TopBar /><CommandNav />
      <div className="flex-1 flex items-center justify-center text-white/30 font-mono text-xs tracking-widest">
        SCANNING NARRATIVE PROPAGATION...
      </div>
    </div>
  )

  if (error) return (
    <div className="flex flex-col h-screen bg-[#05080e]">
      <TopBar /><CommandNav />
      <div className="flex-1 flex items-center justify-center text-red-400 font-mono text-xs">
        FETCH ERROR — {error}
      </div>
    </div>
  )

  if (!data || data.nodes.length === 0) return (
    <div className="flex flex-col h-screen bg-[#05080e]">
      <TopBar /><CommandNav />
      <div className="flex-1 flex items-center justify-center flex-col gap-2 text-white/20 font-mono text-xs">
        <div className="tracking-widest">NO COORDINATED CLUSTERS DETECTED</div>
        <div className="text-white/10">{data?.events_scanned ?? 0} events scanned — threshold not reached</div>
      </div>
    </div>
  )

  const selectedEdges = selected
    ? data.edges.filter(e => e.source === selected || e.target === selected)
    : []

  return (
    <div className="flex flex-col h-screen bg-[#05080e] text-white font-mono overflow-hidden">
      <TopBar />
      <CommandNav />

      {/* Sub-header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-[9px] tracking-[0.2em] text-white/30 uppercase">Narrative Cartography</span>
          <span className="text-[9px] text-white/20">·</span>
          <span className="text-[9px] text-white/40">{data.nodes.length} sources · {data.edges.length} links · {data.clusters_detected} clusters</span>
        </div>
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
      </div>

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        {/* Graph */}
        <div className="flex-1 flex items-center justify-center relative overflow-hidden">
          <svg
            width={W}
            height={H}
            viewBox={`0 0 ${W} ${H}`}
            className="max-w-full max-h-full"
          >
            <defs>
              {Object.entries(SUSPICION_COLORS).map(([level, color]) => (
                <marker
                  key={level}
                  id={`arr-${level}`}
                  viewBox="0 0 10 10"
                  refX="22"
                  refY="5"
                  markerWidth="5"
                  markerHeight="5"
                  orient="auto"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
                </marker>
              ))}
            </defs>

            {/* Edges */}
            {data.edges.map((edge, i) => {
              const s = nodeMap.get(edge.source)
              const t = nodeMap.get(edge.target)
              if (!s || !t) return null
              const color = SUSPICION_COLORS[edge.suspicion_level] || "#6b7280"
              const highlighted = selected === edge.source || selected === edge.target
              const mx = (s.x + t.x) / 2
              const my = (s.y + t.y) / 2
              return (
                <g key={i}>
                  <line
                    x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                    stroke={color}
                    strokeWidth={highlighted ? 1.8 : 0.8}
                    strokeOpacity={highlighted ? 0.85 : 0.25}
                    markerEnd={`url(#arr-${edge.suspicion_level})`}
                  />
                  {highlighted && edge.delay_minutes > 0 && (
                    <text x={mx} y={my - 5} fill={color} fontSize={8} textAnchor="middle" opacity={0.8}>
                      +{edge.delay_minutes}m
                    </text>
                  )}
                </g>
              )
            })}

            {/* Nodes */}
            {nodesRef.current.map(node => {
              const color = CHANNEL_COLORS[node.channel_type] || "#94a3b8"
              const isSelected = selected === node.id
              const r = 8 + Math.min(node.event_count * 2, 18)
              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x.toFixed(1)},${node.y.toFixed(1)})`}
                  onClick={() => setSelected(isSelected ? null : node.id)}
                  style={{ cursor: "pointer" }}
                >
                  {isSelected && <circle r={r + 8} fill={color} opacity={0.12} />}
                  <circle
                    r={r}
                    fill={color}
                    fillOpacity={isSelected ? 0.3 : 0.15}
                    stroke={color}
                    strokeWidth={isSelected ? 1.8 : 1}
                    strokeOpacity={0.85}
                  />
                  <text
                    fill={color}
                    fontSize={8}
                    textAnchor="middle"
                    dy={3}
                    style={{ pointerEvents: "none", userSelect: "none", fontWeight: "bold" }}
                  >
                    {node.event_count}
                  </text>
                  <text
                    y={r + 14}
                    fill="rgba(255,255,255,0.55)"
                    fontSize={8}
                    textAnchor="middle"
                    style={{ pointerEvents: "none", userSelect: "none" }}
                  >
                    {node.id.length > 20 ? node.id.slice(0, 20) + "…" : node.id}
                  </text>
                </g>
              )
            })}
          </svg>

          <div className="absolute bottom-3 left-4 text-[8px] text-white/15 leading-relaxed">
            Node size = event count · Edge = propagation direction · Click node to inspect<br />
            Suspicion flag only — analyst verification required before action
          </div>
        </div>

        {/* Sidebar */}
        {selected && (
          <div className="w-64 border-l border-white/10 flex flex-col overflow-hidden shrink-0">
            <div className="px-4 pt-4 pb-3 border-b border-white/10">
              <div className="text-[8px] tracking-widest text-white/25 uppercase mb-1">Source</div>
              {(() => {
                const node = nodesRef.current.find(n => n.id === selected)
                if (!node) return null
                const color = CHANNEL_COLORS[node.channel_type] || "#94a3b8"
                return (
                  <>
                    <div className="text-[11px] font-bold leading-snug" style={{ color }}>{node.id}</div>
                    <div className="text-[9px] text-white/30 mt-0.5 uppercase">{node.channel_type} · {node.event_count} events in clusters</div>
                  </>
                )
              })()}
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-3">
              <div className="text-[8px] tracking-widest text-white/25 uppercase mb-2">Propagation Links</div>
              {selectedEdges.length === 0 ? (
                <div className="text-[9px] text-white/20">No directed links</div>
              ) : selectedEdges.map((e, i) => {
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
                      <span className="text-[8px] px-1 py-0.5 rounded border text-[9px]"
                        style={{ color: slColor, borderColor: slColor + "44" }}>
                        {e.suspicion_level}
                      </span>
                    </div>
                    {e.common_tokens.length > 0 && (
                      <div className="text-[8px] text-white/20 mt-1">{e.common_tokens.join(" · ")}</div>
                    )}
                  </div>
                )
              })}
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
