"use client"

import { Plus, Minus, Maximize, RefreshCw } from "lucide-react"

interface GraphControlsProps {
  zoom: number
  onZoomIn: () => void
  onZoomOut: () => void
  onFitToScreen: () => void
  onRefresh: () => void
}

export function GraphControls({
  onZoomIn,
  onZoomOut,
  onFitToScreen,
  onRefresh,
}: GraphControlsProps) {
  const buttons = [
    { icon: Plus, label: "Zoom in", onClick: onZoomIn },
    { icon: Minus, label: "Zoom out", onClick: onZoomOut },
    { icon: Maximize, label: "Fit to screen", onClick: onFitToScreen },
    { icon: RefreshCw, label: "Refresh graph", onClick: onRefresh },
  ]

  return (
    <div
      className="glass-panel absolute right-4 bottom-4 z-10 flex flex-col gap-1 rounded-lg p-1.5"
    >
      {buttons.map(({ icon: Icon, label, onClick }) => (
        <button
          key={label}
          onClick={onClick}
          title={label}
          className="flex h-8 w-8 items-center justify-center rounded transition-all hover:border-[#ff1a3c]"
          style={{
            background: "rgba(5,5,7,0.8)",
            border: "1px solid rgba(255,255,255,0.08)",
            color: "#ffffff",
          }}
          aria-label={label}
        >
          <Icon className="h-3.5 w-3.5" />
        </button>
      ))}
    </div>
  )
}

export function GraphLegend() {
  const items = [
    { shape: "circle", color: "#ff1a3c", label: "EVENTS" },
    { shape: "hexagon", color: "#ffa630", label: "ACTORS" },
    { shape: "diamond", color: "#00b4d8", label: "LOCATIONS" },
    { shape: "square", color: "#00ff88", label: "SOURCES" },
  ]

  return (
    <div
      className="glass-panel absolute bottom-4 left-4 z-10 flex flex-col gap-1.5 rounded-lg p-3"
      style={{ opacity: 0.75 }}
    >
      {items.map(({ shape, color, label }) => (
        <div key={label} className="flex items-center gap-2">
          <LegendShape shape={shape} color={color} />
          <span className="font-mono text-[9px]" style={{ color: "rgba(255,255,255,0.5)" }}>
            {label}
          </span>
        </div>
      ))}
    </div>
  )
}

function LegendShape({ shape, color }: { shape: string; color: string }) {
  const size = 8
  return (
    <svg width={size + 4} height={size + 4} viewBox={`0 0 ${size + 4} ${size + 4}`}>
      {shape === "circle" && (
        <circle cx={(size + 4) / 2} cy={(size + 4) / 2} r={size / 2} fill={color} />
      )}
      {shape === "hexagon" && (
        <polygon
          points={Array.from({ length: 6 }, (_, i) => {
            const angle = (Math.PI / 3) * i - Math.PI / 6
            return `${(size + 4) / 2 + Math.cos(angle) * (size / 2)},${(size + 4) / 2 + Math.sin(angle) * (size / 2)}`
          }).join(" ")}
          fill={color}
        />
      )}
      {shape === "diamond" && (
        <polygon
          points={`${(size + 4) / 2},1 ${size + 3},${(size + 4) / 2} ${(size + 4) / 2},${size + 3} 1,${(size + 4) / 2}`}
          fill={color}
        />
      )}
      {shape === "square" && (
        <rect x={2} y={2} width={size} height={size} fill={color} />
      )}
    </svg>
  )
}

export function GraphActionBar() {
  return (
    <div
      className="absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full px-4 py-2"
      style={{
        background: "rgba(11,12,16,0.90)",
        border: "1px solid rgba(255,255,255,0.10)",
        backdropFilter: "blur(12px)",
      }}
    >
      <button
        className="rounded-full px-4 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider transition-all hover:bg-[rgba(255,255,255,0.05)]"
        style={{
          border: "1px solid rgba(255,255,255,0.15)",
          color: "#ffffff",
        }}
      >
        EXPORT GRAPH
      </button>
      <button
        className="font-blackops rounded-full px-4 py-1.5 text-[10px] uppercase tracking-wider transition-all hover:opacity-90"
        style={{
          background: "#ff1a3c",
          color: "#ffffff",
        }}
      >
        GENERATE REPORT
      </button>
      <button
        className="rounded-full px-4 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider transition-all hover:bg-[rgba(255,255,255,0.05)]"
        style={{
          border: "1px solid rgba(255,255,255,0.15)",
          color: "#ffffff",
        }}
      >
        FULL SCREEN
      </button>
    </div>
  )
}
