export type NodeType = "EVENT" | "ACTOR" | "LOCATION" | "SOURCE" | "INCIDENT" | "TYPE" | "UNKNOWN"

export type RelationshipType =
  | "PARTICIPATED_IN"
  | "CORROBORATES"
  | "OCCURRED_AT"
  | "AFFILIATED_WITH"
  | "REPORTED_BY"
  | "CLASSIFIED_AS"
  | "PART_OF"

export interface GraphNode {
  id: string
  type: NodeType
  label: string
  confidence?: number
  created: string
  lastSeen: string
  connections: number
  x: number
  y: number
  vx: number
  vy: number
  cluster?: string
  properties?: Record<string, unknown>
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  type: RelationshipType
  properties?: Record<string, unknown>
}

export interface GraphPayload {
  backend?: string
  nodes: Array<Record<string, unknown>>
  edges: Array<Record<string, unknown>>
  generated_at?: string
}

export interface GraphNodeProfile {
  id: string
  type: string
  label: string
  properties: Record<string, unknown>
  outgoing: Array<Record<string, unknown>>
  incoming: Array<Record<string, unknown>>
}

export const NODE_COLORS: Record<NodeType, string> = {
  EVENT: "#ff1a3c",
  ACTOR: "#ffa630",
  LOCATION: "#00b4d8",
  SOURCE: "#00ff88",
  INCIDENT: "#c77dff",
  TYPE: "#ffd166",
  UNKNOWN: "#b0b0b0",
}

export const EDGE_COLORS: Record<RelationshipType, string> = {
  CORROBORATES: "#00ff88",
  PARTICIPATED_IN: "#ffa630",
  OCCURRED_AT: "#00b4d8",
  AFFILIATED_WITH: "#ff1a3c",
  REPORTED_BY: "#ffffff",
  CLASSIFIED_AS: "#ffd166",
  PART_OF: "#c77dff",
}

export const EDGE_STYLES: Record<RelationshipType, { width: number; dashed: boolean }> = {
  CORROBORATES: { width: 2.5, dashed: false },
  PARTICIPATED_IN: { width: 1.8, dashed: false },
  OCCURRED_AT: { width: 1.2, dashed: false },
  AFFILIATED_WITH: { width: 1.2, dashed: true },
  REPORTED_BY: { width: 1, dashed: false },
  CLASSIFIED_AS: { width: 1.2, dashed: false },
  PART_OF: { width: 1.2, dashed: true },
}

function seededRandom(seed: number) {
  const x = Math.sin(seed) * 10000
  return x - Math.floor(x)
}

function hashCode(input: string): number {
  let h = 0
  for (let i = 0; i < input.length; i++) {
    h = (Math.imul(31, h) + input.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

function normalizeNodeType(raw: string): NodeType {
  const upper = String(raw || "").toUpperCase()
  if (upper === "EVENT" || upper === "ACTOR" || upper === "LOCATION" || upper === "SOURCE" || upper === "INCIDENT" || upper === "TYPE") {
    return upper
  }
  return "UNKNOWN"
}

function normalizeRelType(raw: string): RelationshipType {
  const upper = String(raw || "").toUpperCase()
  if (
    upper === "PARTICIPATED_IN" ||
    upper === "CORROBORATES" ||
    upper === "OCCURRED_AT" ||
    upper === "AFFILIATED_WITH" ||
    upper === "REPORTED_BY" ||
    upper === "CLASSIFIED_AS" ||
    upper === "PART_OF"
  ) {
    return upper
  }
  return "REPORTED_BY"
}

function parseTs(input: unknown, fallbackIso: string): string {
  const text = String(input || "").trim()
  if (!text) return fallbackIso
  const d = new Date(text)
  return Number.isNaN(d.getTime()) ? fallbackIso : d.toISOString()
}

export function normalizeGraphPayload(payload: GraphPayload): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nowIso = new Date().toISOString()
  const rawNodes = Array.isArray(payload?.nodes) ? payload.nodes : []
  const rawEdges = Array.isArray(payload?.edges) ? payload.edges : []

  const nodes: GraphNode[] = rawNodes
    .map((n, idx) => {
      const id = String(n.id || "").trim()
      if (!id) return null
      const props = (n.properties as Record<string, unknown>) || {}
      const type = normalizeNodeType(String(n.type || n.kind || props.type || "UNKNOWN"))
      const label = String(n.label || props.label || props.name || id)
      const created = parseTs(props.created_at || props.created || props.timestamp, nowIso)
      const lastSeen = parseTs(props.updated_at || props.lastSeen || props.timestamp, nowIso)
      const confidenceRaw = props.confidence_score ?? props.confidence
      const confidence = Number.isFinite(Number(confidenceRaw)) ? Number(confidenceRaw) : undefined
      const seed = hashCode(id) + idx * 17
      const x = 180 + seededRandom(seed) * 1040
      const y = 120 + seededRandom(seed + 29) * 620
      return {
        id,
        type,
        label,
        confidence,
        created,
        lastSeen,
        connections: 0,
        x,
        y,
        vx: 0,
        vy: 0,
        cluster: type.toLowerCase(),
        properties: props,
      } as GraphNode
    })
    .filter((x): x is GraphNode => Boolean(x))

  const nodeIds = new Set(nodes.map((n) => n.id))

  const edges = rawEdges
    .map((e, idx): GraphEdge | null => {
      const source = String(e.source || "").trim()
      const target = String(e.target || "").trim()
      if (!source || !target || !nodeIds.has(source) || !nodeIds.has(target)) return null
      return {
        id: String(e.id || `edge:${idx}:${source}:${target}`),
        source,
        target,
        type: normalizeRelType(String(e.type || e.relation || "REPORTED_BY")),
        properties: (e.properties as Record<string, unknown>) || {},
      }
    })
    .filter((x): x is GraphEdge => x !== null)

  const connectionMap = new Map<string, number>()
  edges.forEach((edge) => {
    connectionMap.set(edge.source, (connectionMap.get(edge.source) || 0) + 1)
    connectionMap.set(edge.target, (connectionMap.get(edge.target) || 0) + 1)
  })

  nodes.forEach((node) => {
    node.connections = connectionMap.get(node.id) || 0
  })

  return { nodes, edges }
}
