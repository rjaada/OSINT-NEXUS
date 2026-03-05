"use client"

import { useRef, useEffect, useCallback, useState } from "react"
import type { GraphNode, GraphEdge, NodeType, RelationshipType } from "@/lib/graph-data"
import { NODE_COLORS, EDGE_COLORS, EDGE_STYLES } from "@/lib/graph-data"

interface GraphCanvasProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  activeNodeTypes: Set<NodeType>
  activeRelTypes: Set<RelationshipType>
  selectedNodeId: string | null
  hoveredNodeId: string | null
  onSelectNode: (id: string | null) => void
  onHoverNode: (id: string | null) => void
  zoom: number
  setZoom: (z: number) => void
}

// Draw node shapes based on type
function drawNode(
  ctx: CanvasRenderingContext2D,
  node: GraphNode,
  size: number,
  isSelected: boolean,
  isHovered: boolean,
  isConnectedToHovered: boolean,
  time: number
) {
  const color = NODE_COLORS[node.type]
  const nodeSeed = Array.from(node.id).reduce((acc, ch) => acc + ch.charCodeAt(0), 0)
  const pulseScale = 1 + Math.sin(time * 0.002 + nodeSeed * 0.5) * 0.04

  ctx.save()
  ctx.translate(node.x, node.y)
  ctx.scale(pulseScale, pulseScale)

  // Outer glow
  const glowAlpha = isSelected || isHovered ? 0.5 : isConnectedToHovered ? 0.3 : 0.15
  ctx.shadowColor = color
  ctx.shadowBlur = isSelected ? 20 : isHovered ? 16 : 8
  ctx.globalAlpha = glowAlpha

  ctx.fillStyle = color
  const s = size

  switch (node.type) {
    case "EVENT": // Circle
      ctx.beginPath()
      ctx.arc(0, 0, s, 0, Math.PI * 2)
      ctx.fill()
      break
    case "ACTOR": // Hexagon
      ctx.beginPath()
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 6
        const px = Math.cos(angle) * s
        const py = Math.sin(angle) * s
        if (i === 0) ctx.moveTo(px, py)
        else ctx.lineTo(px, py)
      }
      ctx.closePath()
      ctx.fill()
      break
    case "LOCATION": // Diamond
      ctx.beginPath()
      ctx.moveTo(0, -s * 1.2)
      ctx.lineTo(s, 0)
      ctx.lineTo(0, s * 1.2)
      ctx.lineTo(-s, 0)
      ctx.closePath()
      ctx.fill()
      break
    case "SOURCE": // Square
      ctx.fillRect(-s * 0.7, -s * 0.7, s * 1.4, s * 1.4)
      break
    case "INCIDENT": // Triangle
      ctx.beginPath()
      ctx.moveTo(0, -s * 1.2)
      ctx.lineTo(s * 1.1, s * 0.9)
      ctx.lineTo(-s * 1.1, s * 0.9)
      ctx.closePath()
      ctx.fill()
      break
    default:
      ctx.beginPath()
      ctx.arc(0, 0, s, 0, Math.PI * 2)
      ctx.fill()
      break
  }

  // Reset and draw solid fill
  ctx.shadowBlur = 0
  ctx.globalAlpha = 1
  ctx.fillStyle = color

  switch (node.type) {
    case "EVENT":
      ctx.beginPath()
      ctx.arc(0, 0, s * 0.7, 0, Math.PI * 2)
      ctx.fill()
      break
    case "ACTOR":
      ctx.beginPath()
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 6
        const px = Math.cos(angle) * s * 0.7
        const py = Math.sin(angle) * s * 0.7
        if (i === 0) ctx.moveTo(px, py)
        else ctx.lineTo(px, py)
      }
      ctx.closePath()
      ctx.fill()
      break
    case "LOCATION":
      ctx.beginPath()
      ctx.moveTo(0, -s * 0.85)
      ctx.lineTo(s * 0.7, 0)
      ctx.lineTo(0, s * 0.85)
      ctx.lineTo(-s * 0.7, 0)
      ctx.closePath()
      ctx.fill()
      break
    case "SOURCE":
      ctx.fillRect(-s * 0.5, -s * 0.5, s, s)
      break
    case "INCIDENT":
      ctx.beginPath()
      ctx.moveTo(0, -s * 0.85)
      ctx.lineTo(s * 0.8, s * 0.65)
      ctx.lineTo(-s * 0.8, s * 0.65)
      ctx.closePath()
      ctx.fill()
      break
    default:
      ctx.beginPath()
      ctx.arc(0, 0, s * 0.7, 0, Math.PI * 2)
      ctx.fill()
      break
  }

  // Selected ring
  if (isSelected) {
    ctx.strokeStyle = "#ffffff"
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.arc(0, 0, s + 4, 0, Math.PI * 2)
    ctx.stroke()
  }

  // Hovered ring
  if (isHovered && !isSelected) {
    ctx.strokeStyle = "rgba(255,255,255,0.6)"
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.arc(0, 0, s + 3, 0, Math.PI * 2)
    ctx.stroke()
  }

  ctx.restore()

  // Node label
  ctx.save()
  ctx.font = "9px 'JetBrains Mono', monospace"
  ctx.fillStyle =
    isSelected || isHovered ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.45)"
  ctx.textAlign = "center"
  const label =
    node.label.length > 20 ? node.label.slice(0, 20) + "..." : node.label
  ctx.fillText(label, node.x, node.y + s + 14)
  ctx.restore()
}

export function GraphCanvas({
  nodes,
  edges,
  activeNodeTypes,
  activeRelTypes,
  selectedNodeId,
  hoveredNodeId,
  onSelectNode,
  onHoverNode,
  zoom,
  setZoom,
}: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animFrameRef = useRef<number>(0)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const isPanningRef = useRef(false)
  const lastMouseRef = useRef({ x: 0, y: 0 })
  const nodesRef = useRef(nodes)
  nodesRef.current = nodes

  // Filter visible nodes and edges
  const visibleNodes = nodes.filter((n) => activeNodeTypes.has(n.type))
  const visibleNodeIds = new Set(visibleNodes.map((n) => n.id))
  const visibleEdges = edges.filter(
    (e) =>
      visibleNodeIds.has(e.source) &&
      visibleNodeIds.has(e.target) &&
      (activeRelTypes.size === 0 || activeRelTypes.has(e.type))
  )

  // Find connected nodes for hover highlighting
  const connectedToHovered = new Set<string>()
  if (hoveredNodeId) {
    edges.forEach((e) => {
      if (e.source === hoveredNodeId) connectedToHovered.add(e.target)
      if (e.target === hoveredNodeId) connectedToHovered.add(e.source)
    })
  }

  const getNodeSize = useCallback((node: GraphNode) => {
    if (node.type === "EVENT") {
      return 5 + ((node.confidence || 50) / 100) * 8
    }
    if (node.type === "SOURCE") return 5
    if (node.type === "ACTOR") return 8
    return 7
  }, [])

  const findNodeAtPosition = useCallback(
    (mx: number, my: number) => {
      const canvas = canvasRef.current
      if (!canvas) return null

      // Transform mouse coords to graph space
      const gx = (mx - pan.x) / zoom
      const gy = (my - pan.y) / zoom

      for (let i = visibleNodes.length - 1; i >= 0; i--) {
        const node = visibleNodes[i]
        const size = getNodeSize(node) + 4
        const dx = gx - node.x
        const dy = gy - node.y
        if (dx * dx + dy * dy < size * size) {
          return node
        }
      }
      return null
    },
    [pan, zoom, visibleNodes, getNodeSize]
  )

  // Render loop
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const resize = () => {
      const rect = container.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      canvas.style.width = `${rect.width}px`
      canvas.style.height = `${rect.height}px`
      ctx.scale(dpr, dpr)
    }
    resize()
    window.addEventListener("resize", resize)

    const render = (time: number) => {
      const rect = container.getBoundingClientRect()
      ctx.clearRect(0, 0, rect.width, rect.height)

      ctx.save()
      ctx.translate(pan.x, pan.y)
      ctx.scale(zoom, zoom)

      // Draw edges
      visibleEdges.forEach((edge) => {
        const source = nodesRef.current.find((n) => n.id === edge.source)
        const target = nodesRef.current.find((n) => n.id === edge.target)
        if (!source || !target) return

        const style = EDGE_STYLES[edge.type]
        const color = EDGE_COLORS[edge.type]

        const isHighlighted =
          hoveredNodeId === edge.source ||
          hoveredNodeId === edge.target ||
          selectedNodeId === edge.source ||
          selectedNodeId === edge.target

        ctx.save()
        ctx.strokeStyle = color
        ctx.lineWidth = style.width * (isHighlighted ? 1.5 : 1)
        ctx.globalAlpha = isHighlighted
          ? 0.8
          : 0.25 + Math.sin(time * 0.001 + Array.from(edge.id).reduce((acc, ch) => acc + ch.charCodeAt(0), 0)) * 0.08

        if (style.dashed) {
          ctx.setLineDash([6, 4])
        }

        ctx.beginPath()
        ctx.moveTo(source.x, source.y)
        ctx.lineTo(target.x, target.y)
        ctx.stroke()
        ctx.restore()
      })

      // Draw nodes
      visibleNodes.forEach((node) => {
        const size = getNodeSize(node)
        const isSelected = selectedNodeId === node.id
        const isHovered = hoveredNodeId === node.id
        const isConnected = connectedToHovered.has(node.id)
        drawNode(ctx, node, size, isSelected, isHovered, isConnected, time)
      })

      ctx.restore()
      animFrameRef.current = requestAnimationFrame(render)
    }

    animFrameRef.current = requestAnimationFrame(render)

    return () => {
      window.removeEventListener("resize", resize)
      cancelAnimationFrame(animFrameRef.current)
    }
  }, [
    visibleNodes,
    visibleEdges,
    selectedNodeId,
    hoveredNodeId,
    zoom,
    pan,
    getNodeSize,
    connectedToHovered,
  ])

  // Mouse handlers
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const rect = canvasRef.current?.getBoundingClientRect()
      if (!rect) return
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top

      const node = findNodeAtPosition(mx, my)
      if (node) {
        onSelectNode(node.id === selectedNodeId ? null : node.id)
      } else {
        isPanningRef.current = true
        lastMouseRef.current = { x: e.clientX, y: e.clientY }
        onSelectNode(null)
      }
    },
    [findNodeAtPosition, onSelectNode, selectedNodeId]
  )

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (isPanningRef.current) {
        const dx = e.clientX - lastMouseRef.current.x
        const dy = e.clientY - lastMouseRef.current.y
        setPan((p) => ({ x: p.x + dx, y: p.y + dy }))
        lastMouseRef.current = { x: e.clientX, y: e.clientY }
        return
      }

      const rect = canvasRef.current?.getBoundingClientRect()
      if (!rect) return
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      const node = findNodeAtPosition(mx, my)
      onHoverNode(node ? node.id : null)

      if (canvasRef.current) {
        canvasRef.current.style.cursor = node ? "pointer" : "grab"
      }
    },
    [findNodeAtPosition, onHoverNode]
  )

  const handleMouseUp = useCallback(() => {
    isPanningRef.current = false
  }, [])

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault()
      const delta = e.deltaY > 0 ? 0.92 : 1.08
      const newZoom = Math.max(0.3, Math.min(3, zoom * delta))
      setZoom(newZoom)
    },
    [zoom, setZoom]
  )

  // Tooltip
  const hoveredNode = hoveredNodeId
    ? nodes.find((n) => n.id === hoveredNodeId)
    : null
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })

  const handleMouseMoveGlobal = useCallback(
    (e: React.MouseEvent) => {
      setMousePos({ x: e.clientX, y: e.clientY })
      handleMouseMove(e)
    },
    [handleMouseMove]
  )

  return (
    <div
      ref={containerRef}
      className="osint-grid osint-scanlines relative h-full w-full overflow-hidden"
      style={{ background: "#050507" }}
    >
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMoveGlobal}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => {
          isPanningRef.current = false
          onHoverNode(null)
        }}
        onWheel={handleWheel}
        className="h-full w-full"
        style={{ cursor: "grab" }}
      />

      {/* Hover tooltip */}
      {hoveredNode && (
        <div
          className="pointer-events-none fixed z-50 rounded"
          style={{
            left: mousePos.x + 16,
            top: mousePos.y - 10,
            background: "rgba(11,12,16,0.95)",
            backdropFilter: "blur(12px)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderLeft: `3px solid ${NODE_COLORS[hoveredNode.type]}`,
            padding: "10px 14px",
            maxWidth: "240px",
          }}
        >
          <div className="flex items-center gap-2">
            <span
              className="rounded px-1.5 py-0.5 font-mono text-[8px] font-bold"
              style={{
                background: `${NODE_COLORS[hoveredNode.type]}20`,
                color: NODE_COLORS[hoveredNode.type],
              }}
            >
              {hoveredNode.type}
            </span>
            <span className="font-serif text-[11px] font-medium" style={{ color: "#ffffff" }}>
              {hoveredNode.label}
            </span>
          </div>
          {hoveredNode.type === "EVENT" && hoveredNode.confidence !== undefined && (
            <div className="mt-1 font-mono text-[9px]" style={{ color: "rgba(255,255,255,0.5)" }}>
              CONFIDENCE: <span style={{ color: "#00ff88" }}>{hoveredNode.confidence}%</span>
            </div>
          )}
          <div className="mt-1 font-mono text-[9px]" style={{ color: "rgba(255,255,255,0.4)" }}>
            {hoveredNode.connections} connections
          </div>
          <div className="mt-0.5 font-mono text-[8px]" style={{ color: "rgba(255,255,255,0.3)" }}>
            Last seen: {new Date(hoveredNode.lastSeen).toLocaleString()}
          </div>
        </div>
      )}
    </div>
  )
}
