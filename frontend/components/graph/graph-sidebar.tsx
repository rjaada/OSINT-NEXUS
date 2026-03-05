"use client"

import { ExternalLink } from "lucide-react"
import type { GraphNode, GraphNodeProfile, NodeType, RelationshipType } from "@/lib/graph-data"
import { NODE_COLORS } from "@/lib/graph-data"

interface GraphSidebarProps {
  activeNodeTypes: Set<NodeType>
  toggleNodeType: (type: NodeType) => void
  activeRelTypes: Set<RelationshipType>
  toggleRelType: (type: RelationshipType) => void
  selectedNode: GraphNode | null
  selectedProfile: GraphNodeProfile | null
  loadingProfile: boolean
  connectedNodes: GraphNode[]
  timeRange: number
  setTimeRange: (val: number) => void
  nodeTypeCounts: Record<string, number>
}

const NODE_TYPE_ORDER: NodeType[] = ["EVENT", "ACTOR", "LOCATION", "SOURCE", "INCIDENT", "TYPE"]

const NODE_TYPE_LABELS: Record<NodeType, string> = {
  EVENT: "EVENTS",
  ACTOR: "ACTORS",
  LOCATION: "LOCATIONS",
  SOURCE: "SOURCES",
  INCIDENT: "INCIDENTS",
  TYPE: "CLASS TYPES",
  UNKNOWN: "UNKNOWN",
}

const REL_TYPES: RelationshipType[] = [
  "PARTICIPATED_IN",
  "CORROBORATES",
  "OCCURRED_AT",
  "AFFILIATED_WITH",
  "REPORTED_BY",
  "CLASSIFIED_AS",
  "PART_OF",
]

export function GraphSidebar({
  activeNodeTypes,
  toggleNodeType,
  activeRelTypes,
  toggleRelType,
  selectedNode,
  selectedProfile,
  loadingProfile,
  connectedNodes,
  timeRange,
  setTimeRange,
  nodeTypeCounts,
}: GraphSidebarProps) {
  return (
    <aside className="glass-panel flex w-[300px] shrink-0 flex-col overflow-y-auto border-r border-[rgba(255,255,255,0.06)]">
      <div className="border-b border-[rgba(255,255,255,0.06)] p-4">
        <SectionLabel>FILTER NODES</SectionLabel>
        <div className="mt-3 flex flex-col gap-2">
          {NODE_TYPE_ORDER.filter((type) => (nodeTypeCounts[type] || 0) > 0).map((type) => {
            const active = activeNodeTypes.has(type)
            const color = NODE_COLORS[type]
            const count = nodeTypeCounts[type] || 0
            return (
              <button
                key={type}
                onClick={() => toggleNodeType(type)}
                className="flex items-center justify-between rounded px-3 py-2 font-mono text-[11px] transition-all"
                style={{
                  background: active ? "rgba(255,255,255,0.04)" : "rgba(255,255,255,0.02)",
                  border: active ? `1px solid ${color}` : "1px solid rgba(255,255,255,0.06)",
                  color: active ? "#ffffff" : "rgba(255,255,255,0.4)",
                }}
              >
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full" style={{ backgroundColor: color, opacity: active ? 1 : 0.4 }} />
                  <span>{NODE_TYPE_LABELS[type]}</span>
                </div>
                <span
                  className="rounded-sm px-1.5 py-0.5 text-[9px] font-bold"
                  style={{
                    background: `${color}15`,
                    color,
                  }}
                >
                  {count}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="border-b border-[rgba(255,255,255,0.06)] p-4">
        <SectionLabel>FILTER RELATIONSHIPS</SectionLabel>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {REL_TYPES.map((type) => {
            const active = activeRelTypes.has(type)
            return (
              <button
                key={type}
                onClick={() => toggleRelType(type)}
                className="rounded px-2 py-1 font-mono text-[9px] transition-all"
                style={{
                  background: active ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.02)",
                  border: active ? "1px solid rgba(255,255,255,0.2)" : "1px solid rgba(255,255,255,0.06)",
                  color: active ? "#ffffff" : "rgba(255,255,255,0.3)",
                }}
              >
                {type}
              </button>
            )
          })}
        </div>
      </div>

      <div className="border-b border-[rgba(255,255,255,0.06)] p-4">
        <SectionLabel>TIME RANGE</SectionLabel>
        <div className="mt-3">
          <input
            type="range"
            min={0}
            max={72}
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value))}
            className="osint-slider w-full"
            style={{
              accentColor: "#ff1a3c",
            }}
          />
          <div className="mt-1.5 flex items-center justify-between">
            <span className="font-mono text-[9px]" style={{ color: "#ffa630" }}>
              72H AGO
            </span>
            <span className="font-mono text-[9px]" style={{ color: "#ffa630" }}>
              NOW
            </span>
          </div>
        </div>
      </div>

      {selectedNode && (
        <div className="p-4">
          <SectionLabel>SELECTED NODE</SectionLabel>
          <div
            className="mt-3 rounded p-3"
            style={{
              background: "rgba(11, 12, 16, 0.9)",
              borderLeft: `3px solid ${NODE_COLORS[selectedNode.type]}`,
              border: "1px solid rgba(255,255,255,0.06)",
              borderLeftColor: NODE_COLORS[selectedNode.type],
              borderLeftWidth: "3px",
            }}
          >
            <span
              className="inline-block rounded px-1.5 py-0.5 font-mono text-[9px] font-bold"
              style={{
                background: `${NODE_COLORS[selectedNode.type]}20`,
                color: NODE_COLORS[selectedNode.type],
              }}
            >
              {selectedNode.type}
            </span>
            <h3 className="mt-2 font-serif text-sm font-medium" style={{ color: "#ffffff" }}>
              {selectedNode.label}
            </h3>
            <div className="mt-2 flex flex-col gap-1">
              <span className="font-mono text-[9px]" style={{ color: "rgba(255,255,255,0.4)" }}>
                CREATED: {new Date(selectedNode.created).toLocaleString()}
              </span>
              <span className="font-mono text-[10px] font-semibold" style={{ color: "#00b4d8" }}>
                {selectedNode.connections} CONNECTIONS
              </span>
            </div>

            {loadingProfile ? (
              <div className="mt-3 font-mono text-[10px] text-muted-foreground">Loading profile...</div>
            ) : selectedProfile ? (
              <div className="mt-3 flex flex-col gap-1 border-t border-[rgba(255,255,255,0.06)] pt-2">
                <span className="font-mono text-[8px] uppercase" style={{ color: "rgba(255,255,255,0.3)" }}>
                  PROFILE DETAILS
                </span>
                <span className="font-mono text-[9px]" style={{ color: "rgba(255,255,255,0.65)" }}>
                  Incoming: {Array.isArray(selectedProfile.incoming) ? selectedProfile.incoming.length : 0}
                </span>
                <span className="font-mono text-[9px]" style={{ color: "rgba(255,255,255,0.65)" }}>
                  Outgoing: {Array.isArray(selectedProfile.outgoing) ? selectedProfile.outgoing.length : 0}
                </span>
                {selectedProfile.properties?.incident_id && (
                  <span className="font-mono text-[9px]" style={{ color: "rgba(255,255,255,0.65)" }}>
                    Incident: {String(selectedProfile.properties.incident_id)}
                  </span>
                )}
              </div>
            ) : null}

            {connectedNodes.length > 0 && (
              <div className="mt-3 flex flex-col gap-1 border-t border-[rgba(255,255,255,0.06)] pt-2">
                <span className="font-mono text-[8px] uppercase" style={{ color: "rgba(255,255,255,0.3)" }}>
                  RECENT CONNECTIONS
                </span>
                {connectedNodes.slice(0, 4).map((cn) => (
                  <div key={cn.id} className="flex items-center gap-1.5">
                    <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: NODE_COLORS[cn.type] }} />
                    <span className="truncate font-mono text-[9px]" style={{ color: "rgba(255,255,255,0.6)" }}>
                      {cn.label}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <div
              className="mt-3 flex w-full items-center justify-center gap-1.5 rounded py-1.5 font-mono text-[10px] font-semibold"
              style={{ border: "1px solid #ff1a3c", color: "#ff1a3c" }}
            >
              FULL PROFILE LOADED
              <ExternalLink className="h-3 w-3" />
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10px] font-bold uppercase tracking-[0.15em]" style={{ color: "#ff1a3c" }}>
      {children}
    </span>
  )
}
