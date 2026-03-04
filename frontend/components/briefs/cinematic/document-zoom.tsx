"use client"

import { useEffect, useState } from "react"

interface DocumentZoomProps {
  onComplete: () => void
}

export function DocumentZoom({ onComplete }: DocumentZoomProps) {
  const [phase, setPhase] = useState<"pickup" | "zoom" | "done">("pickup")

  useEffect(() => {
    const t1 = setTimeout(() => setPhase("zoom"), 600)
    const t2 = setTimeout(() => setPhase("done"), 1200)
    const t3 = setTimeout(() => onComplete(), 1600)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
      clearTimeout(t3)
    }
  }, [onComplete])

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ background: "#0a0a08" }}>
      {/* Desk background */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: "url(/images/desk.jpg)",
          backgroundSize: "cover",
          backgroundPosition: "center",
          opacity: phase === "pickup" ? 0.5 : 0.3,
          filter: "brightness(0.35)",
          transition: "opacity 0.5s ease",
        }}
      />

      {/* Paper zooming to fill screen */}
      <div
        className="absolute left-1/2 top-1/2 z-10"
        style={{
          transform:
            phase === "pickup"
              ? "translate(-50%, -50%) scale(0.5)"
              : phase === "zoom"
              ? "translate(-50%, -50%) scale(2)"
              : "translate(-50%, -50%) scale(4)",
          opacity: phase === "done" ? 0.8 : 1,
          transition:
            "transform 0.6s cubic-bezier(0.22,1,0.36,1), opacity 0.4s ease",
        }}
      >
        <div
          className="flex h-[400px] w-[300px] flex-col items-center justify-center"
          style={{
            background: "#f5f0e8",
            boxShadow: "0 40px 100px rgba(0,0,0,0.6)",
          }}
        >
          <div className="w-full bg-[#1a1a1a] py-2">
            <p className="text-center font-mono text-[8px] font-bold tracking-[0.15em] text-[#cc0000]">
              {"//UNCLASSIFIED//FOR OFFICIAL USE ONLY//"}
            </p>
          </div>
          <div className="flex flex-1 items-center justify-center">
            <span className="font-[var(--font-stencil)] text-lg tracking-wider text-[#1a1a1a]">
              INTELLIGENCE SUMMARY
            </span>
          </div>
        </div>
      </div>

      {/* White overlay for transition */}
      <div
        className="pointer-events-none absolute inset-0 z-20 bg-[#f5f0e8]"
        style={{
          opacity: phase === "done" ? 1 : 0,
          transition: "opacity 0.5s ease-in",
        }}
      />
    </div>
  )
}
