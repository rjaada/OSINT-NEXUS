"use client"

import { useState, useEffect } from "react"
import { Shield } from "lucide-react"

interface GraphHeaderProps {
  nodeCount: number
  edgeCount: number
  subtitle?: string
}

export function GraphHeader({ nodeCount, edgeCount, subtitle }: GraphHeaderProps) {
  const [timestamp, setTimestamp] = useState("--:--:--")

  useEffect(() => {
    const update = () => {
      const now = new Date()
      setTimestamp(now.toISOString().replace("T", " ").slice(0, 19) + "Z")
    }
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [])

  return (
    <header className="glass-panel flex items-center justify-between px-5 py-3 border-b border-[rgba(255,255,255,0.06)]">
      {/* Left section */}
      <div className="flex items-center gap-3">
        <Shield className="h-5 w-5" style={{ color: "#ff1a3c" }} />
        <span className="font-blackops text-base tracking-wide" style={{ color: "#ffffff" }}>
          OSINT NEXUS
        </span>
        <div className="flex items-center gap-1.5 ml-2">
          <div
            className="live-dot h-2 w-2 rounded-full"
            style={{ backgroundColor: "#00ff88" }}
          />
          <span className="font-mono text-[10px] font-semibold" style={{ color: "#00ff88" }}>
            {subtitle || "LIVE"}
          </span>
        </div>
      </div>

      {/* Center section */}
      <div className="flex flex-col items-center">
        <h1 className="font-serif text-lg font-semibold tracking-wide" style={{ color: "#ffffff" }}>
          INTELLIGENCE GRAPH
        </h1>
        <span
          className="font-mono text-[9px] uppercase tracking-[0.2em]"
          style={{ color: "rgba(255,255,255,0.4)" }}
        >
          ENTITY RELATIONSHIP EXPLORER
        </span>
      </div>

      {/* Right section */}
      <div className="flex items-center gap-5">
        <div className="flex flex-col items-end">
          <span className="font-mono text-[11px] font-semibold" style={{ color: "rgba(255,255,255,0.6)" }}>
            <span style={{ color: "#ff1a3c" }}>{nodeCount}</span> NODES
          </span>
          <span className="font-mono text-[11px] font-semibold" style={{ color: "rgba(255,255,255,0.6)" }}>
            <span style={{ color: "#00b4d8" }}>{edgeCount}</span> EDGES
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="font-mono text-[9px] uppercase" style={{ color: "rgba(255,255,255,0.3)" }}>
            LAST UPDATED
          </span>
          <span className="font-mono text-[10px]" style={{ color: "#ffa630" }}>
            {timestamp}
          </span>
        </div>
        <div className="flex items-center gap-1.5 rounded px-2 py-1" style={{ background: "rgba(0,255,136,0.08)", border: "1px solid rgba(0,255,136,0.2)" }}>
          <span className="font-mono text-[9px] font-bold" style={{ color: "#00ff88" }}>
            DEFCON 5
          </span>
        </div>
      </div>
    </header>
  )
}
