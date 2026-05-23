"use client"

import { useEffect, useState } from "react"
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

const COMMUNITY_COLORS = [
  "#60a5fa", "#f472b6", "#34d399", "#fbbf24",
  "#a78bfa", "#fb923c", "#22d3ee", "#e879f9",
]

interface NetNode {
  id: string
  channel_type: string
  event_count: number
  community: number
  centrality: number
  affiliation: string
}

interface NetEdge {
  source: string
  target: string
  weight: number
  avg_delay_min: number
  same_community: boolean
}

interface NetworkData {
  nodes: NetNode[]
  edges: NetEdge[]
  communities: number
  sources_tracked: number
  edges_detected: number
  scanned_at: string
}

function shortName(id: string): string {
  return id.replace(" (TG)", "").replace(" News", "").replace("NASA ", "").slice(0, 12)
}

export default function NetworkPage() {
  const [data, setData] = useState<NetworkData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hovered, setHovered] = useState<{ row: string; col: string } | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/v2/source-network`, { credentials: "include" })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex flex-col h-screen bg-[#05080e]">
      <TopBar /><CommandNav />
      <div className="flex-1 flex items-center justify-center text-white/30 font-mono text-xs tracking-widest">
        MAPPING SOURCE NETWORK...
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
        <div className="tracking-widest">NO SOURCE DATA AVAILABLE</div>
      </div>
    </div>
  )

  // Sort nodes by community then event_count
  const sorted = [...data.nodes].sort((a, b) =>
    a.community !== b.community ? a.community - b.community : b.event_count - a.event_count
  )

  // Build weight lookup
  const weightMap = new Map<string, number>()
  const delayMap = new Map<string, number>()
  for (const e of data.edges) {
    const key = `${e.source}|||${e.target}`
    const key2 = `${e.target}|||${e.source}`
    weightMap.set(key, e.weight)
    weightMap.set(key2, e.weight)
    delayMap.set(key, e.avg_delay_min)
    delayMap.set(key2, e.avg_delay_min)
  }
  const maxWeight = Math.max(...Array.from(weightMap.values()), 1)

  const getWeight = (a: string, b: string) => weightMap.get(`${a}|||${b}`) ?? 0
  const getDelay = (a: string, b: string) => delayMap.get(`${a}|||${b}`) ?? 0

  // Group nodes by community
  const communityGroups: Map<number, NetNode[]> = new Map()
  for (const n of sorted) {
    if (!communityGroups.has(n.community)) communityGroups.set(n.community, [])
    communityGroups.get(n.community)!.push(n)
  }

  const selectedNode = selected ? data.nodes.find(n => n.id === selected) : null
  const selectedLinks = selected
    ? data.edges.filter(e => e.source === selected || e.target === selected)
        .sort((a, b) => b.weight - a.weight)
    : []

  const CELL = 28
  const LABEL_W = 90
  const hoveredWeight = hovered ? getWeight(hovered.row, hovered.col) : 0
  const hoveredDelay = hovered ? getDelay(hovered.row, hovered.col) : 0

  return (
    <div className="flex flex-col h-screen bg-[#05080e] text-white font-mono overflow-hidden">
      <TopBar />
      <CommandNav />

      {/* Sub-header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-[9px] tracking-[0.2em] text-white/30 uppercase">Source Network — Co-occurrence Matrix</span>
          <span className="text-[9px] text-white/20">·</span>
          <span className="text-[9px] text-white/40">
            {data.sources_tracked} sources · {data.edges_detected} links · {data.communities} networks detected
          </span>
        </div>
        <div className="flex items-center gap-3 text-[9px] text-white/25">
          <span>Cell intensity = shared claim frequency</span>
          <span className="text-white/10">|</span>
          {Object.entries(CHANNEL_COLORS).map(([t, c]) => (
            <span key={t} className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: c }} />
              <span className="uppercase">{t}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Matrix */}
        <div className="flex-1 overflow-auto p-4">
          {/* Community legend */}
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            {Array.from(communityGroups.entries()).map(([cid, members]) => (
              <div key={cid} className="flex items-center gap-1.5 px-2 py-1 rounded border border-white/10">
                <span className="w-2 h-2 rounded-full" style={{ background: COMMUNITY_COLORS[cid % COMMUNITY_COLORS.length] }} />
                <span className="text-[8px] text-white/40 uppercase">Network {cid}</span>
                <span className="text-[8px] text-white/20">({members.length})</span>
              </div>
            ))}
          </div>

          {/* Matrix grid */}
          <div className="overflow-x-auto">
            <div style={{ display: "inline-block" }}>
              {/* Column headers */}
              <div className="flex" style={{ marginLeft: LABEL_W }}>
                {sorted.map(col => (
                  <div
                    key={col.id}
                    style={{ width: CELL, height: LABEL_W, flexShrink: 0 }}
                    className="flex items-end justify-center pb-1 relative"
                  >
                    <span
                      className="text-[7px] whitespace-nowrap"
                      style={{
                        transform: "rotate(-55deg) translateX(4px)",
                        transformOrigin: "bottom center",
                        color: hovered?.col === col.id || selected === col.id
                          ? (CHANNEL_COLORS[col.channel_type] || "#94a3b8")
                          : "rgba(255,255,255,0.35)",
                      }}
                    >
                      {shortName(col.id)}
                    </span>
                    {/* Community color bar at top */}
                    <div
                      className="absolute top-0 left-1 right-1 h-0.5 rounded"
                      style={{ background: COMMUNITY_COLORS[col.community % COMMUNITY_COLORS.length], opacity: 0.5 }}
                    />
                  </div>
                ))}
              </div>

              {/* Rows */}
              {sorted.map(row => (
                <div key={row.id} className="flex items-center" style={{ height: CELL }}>
                  {/* Row label */}
                  <div
                    style={{ width: LABEL_W, flexShrink: 0 }}
                    className="flex items-center gap-1.5 pr-2 cursor-pointer"
                    onClick={() => setSelected(selected === row.id ? null : row.id)}
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ background: COMMUNITY_COLORS[row.community % COMMUNITY_COLORS.length] }}
                    />
                    <span
                      className="text-[8px] truncate"
                      style={{
                        color: selected === row.id
                          ? (CHANNEL_COLORS[row.channel_type] || "#94a3b8")
                          : hovered?.row === row.id
                          ? "rgba(255,255,255,0.7)"
                          : "rgba(255,255,255,0.35)",
                      }}
                    >
                      {shortName(row.id)}
                    </span>
                  </div>

                  {/* Cells */}
                  {sorted.map(col => {
                    const w = getWeight(row.id, col.id)
                    const isSelf = row.id === col.id
                    const isHighlighted = hovered?.row === row.id && hovered?.col === col.id
                    const isRowHighlighted = hovered?.row === row.id || hovered?.col === row.id
                    const isColHighlighted = hovered?.col === col.id || hovered?.row === col.id
                    const isSelectedRow = selected === row.id || selected === col.id
                    const sameCommunity = row.community === col.community

                    let bg = "rgba(255,255,255,0)"
                    if (isSelf) {
                      bg = `rgba(255,255,255,0.06)`
                    } else if (w > 0) {
                      const intensity = w / maxWeight
                      if (sameCommunity) {
                        // Blue for same-community co-occurrence
                        bg = `rgba(96,165,250,${0.1 + intensity * 0.7})`
                      } else {
                        // Purple for cross-community
                        bg = `rgba(167,139,250,${0.1 + intensity * 0.5})`
                      }
                    }

                    return (
                      <div
                        key={col.id}
                        style={{
                          width: CELL,
                          height: CELL,
                          flexShrink: 0,
                          background: bg,
                          border: isHighlighted
                            ? "1px solid rgba(255,255,255,0.4)"
                            : isRowHighlighted || isColHighlighted || isSelectedRow
                            ? "1px solid rgba(255,255,255,0.1)"
                            : "1px solid rgba(255,255,255,0.03)",
                          cursor: w > 0 && !isSelf ? "pointer" : "default",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                        onMouseEnter={() => !isSelf && setHovered({ row: row.id, col: col.id })}
                        onMouseLeave={() => setHovered(null)}
                        onClick={() => { if (!isSelf && w > 0) setSelected(selected === row.id ? null : row.id) }}
                        title={w > 0 && !isSelf ? `${row.id} ↔ ${col.id}: ${w}× · avg ${getDelay(row.id, col.id)}m apart` : ""}
                      >
                        {w > 0 && !isSelf && (
                          <span className="text-[7px] font-bold" style={{ color: isHighlighted ? "white" : "rgba(255,255,255,0.5)" }}>
                            {w}
                          </span>
                        )}
                        {isSelf && (
                          <span
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ background: CHANNEL_COLORS[row.channel_type] || "#94a3b8" }}
                          />
                        )}
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>
          </div>

          {/* Hover tooltip */}
          {hovered && hoveredWeight > 0 && (
            <div className="mt-4 flex items-center gap-4 text-[9px] text-white/50 font-mono">
              <span className="text-white/70">{hovered.row}</span>
              <span>↔</span>
              <span className="text-white/70">{hovered.col}</span>
              <span className="text-white/30">·</span>
              <span>{hoveredWeight}× shared claims</span>
              <span className="text-white/30">·</span>
              <span>avg {hoveredDelay}m apart</span>
            </div>
          )}

          <div className="mt-6 text-[8px] text-white/15 leading-relaxed">
            Blue cell = same network cluster · Purple cell = cross-cluster link · Number = co-occurrence count<br />
            Correlation signal from shared claim clusters. Not proof of coordination — analyst verification required.
          </div>
        </div>

        {/* Source detail sidebar */}
        {selectedNode && (
          <div className="w-60 border-l border-white/10 flex flex-col overflow-hidden shrink-0">
            <div className="px-4 pt-4 pb-3 border-b border-white/10">
              <div className="text-[8px] tracking-widest text-white/25 uppercase mb-1">Source Detail</div>
              <div className="text-[11px] font-bold" style={{ color: CHANNEL_COLORS[selectedNode.channel_type] || "#94a3b8" }}>
                {selectedNode.id}
              </div>
              <div className="text-[9px] text-white/30 mt-0.5 uppercase">
                {selectedNode.channel_type} · {selectedNode.event_count} events
              </div>
              <div className="flex items-center gap-1.5 mt-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: COMMUNITY_COLORS[selectedNode.community % COMMUNITY_COLORS.length] }} />
                <span className="text-[9px]" style={{ color: COMMUNITY_COLORS[selectedNode.community % COMMUNITY_COLORS.length] }}>
                  Network {selectedNode.community}
                </span>
              </div>
              {selectedNode.affiliation !== "unknown" && (
                <div className="text-[8px] text-white/25 mt-0.5">{selectedNode.affiliation}</div>
              )}
              <div className="text-[8px] text-white/20 mt-0.5">
                centrality: {(selectedNode.centrality * 100).toFixed(0)}%
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-3">
              <div className="text-[8px] tracking-widest text-white/25 uppercase mb-2">
                Top Co-reporters
              </div>
              {selectedLinks.length === 0 ? (
                <div className="text-[9px] text-white/20">No shared claim clusters</div>
              ) : selectedLinks.slice(0, 10).map((e, i) => {
                const other = e.source === selected ? e.target : e.source
                const otherNode = data.nodes.find(n => n.id === other)
                return (
                  <div key={i} className="mb-2.5 pb-2.5 border-b border-white/5 last:border-0">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ background: CHANNEL_COLORS[otherNode?.channel_type || "other"] || "#94a3b8" }}
                      />
                      <span className="text-[9px] text-white/60 truncate">{other}</span>
                    </div>
                    <div className="text-[8px] text-white/30">
                      {e.weight}× · avg {e.avg_delay_min}m
                      {e.same_community && <span className="ml-1 text-blue-400">· same network</span>}
                    </div>
                  </div>
                )
              })}
            </div>

            <button
              onClick={() => setSelected(null)}
              className="mx-4 mb-4 py-1.5 text-[9px] tracking-widest uppercase text-white/25 border border-white/10 rounded hover:text-white/50 transition-colors"
            >
              Clear
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
