"use client"

import { useRef, useEffect } from "react"
import { Clock } from "lucide-react"
import type { IntelEvent } from "./intel-feed"

const TYPE_COLORS: Record<string, string> = {
  CRITICAL: "#b24bff",
  STRIKE:   "#ff1a3c",
  MOVEMENT: "#00b4d8",
  NOTAM:    "#ffa630",
  CLASH:    "#00ff88",
}

export function ConflictTimeline({ events }: { events: IntelEvent[] }) {
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to latest (leftmost)
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = 0
    }
  }, [events.length])

  // Only show events that have a timestamp
  const timeline = events
    .filter((e) => e.timestamp)
    .slice(0, 40) // limit for perf

  if (timeline.length === 0) return null

  return (
    <div
      className="w-full border-t border-[rgba(255,255,255,0.06)]"
      style={{ background: "rgba(5,5,10,0.85)" }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5">
        <Clock className="h-3 w-3 text-osint-amber" />
        <span className="text-[9px] font-bold tracking-[0.15em] text-[#a0a0b0] uppercase">
          Conflict Timeline
        </span>
        <span className="text-[8px] text-muted-foreground ml-auto tabular-nums">
          {timeline.length} events
        </span>
      </div>

      {/* Scrollable timeline */}
      <div
        ref={scrollRef}
        className="flex gap-0 overflow-x-auto px-3 pb-2 scrollbar-thin"
        style={{ scrollBehavior: "smooth" }}
      >
        {timeline.map((evt, i) => {
          const color = TYPE_COLORS[evt.type] ?? "#808090"
          const isCritical = evt.type === "CRITICAL"
          const desc = evt.desc.replace(/^\[.+?\]\s*/, "").slice(0, 60)
          const source = evt.desc.match(/^\[(.+?)\]/)?.[1] ?? ""

          return (
            <div key={evt.id} className="flex items-start shrink-0">
              {/* Node */}
              <div className="flex flex-col items-center" style={{ width: "140px" }}>
                {/* Dot */}
                <div className="flex items-center w-full">
                  {/* Line left */}
                  <div
                    className="flex-1 h-px"
                    style={{ background: i === 0 ? "transparent" : "rgba(255,255,255,0.08)" }}
                  />
                  {/* Dot */}
                  <div
                    className={`w-2.5 h-2.5 rounded-full shrink-0 ${isCritical ? "animate-blink" : ""}`}
                    style={{
                      background: color,
                      boxShadow: `0 0 ${isCritical ? 10 : 5}px ${color}`,
                    }}
                  />
                  {/* Line right */}
                  <div
                    className="flex-1 h-px"
                    style={{ background: i === timeline.length - 1 ? "transparent" : "rgba(255,255,255,0.08)" }}
                  />
                </div>

                {/* Content */}
                <div className="mt-1.5 px-1 text-center">
                  <div
                    className="text-[7px] font-bold tracking-wider mb-0.5"
                    style={{ color }}
                  >
                    {evt.type}
                  </div>
                  <div className="text-[8px] text-[#909090] leading-tight line-clamp-2">
                    {desc}
                  </div>
                  <div className="text-[7px] text-muted-foreground mt-0.5 tabular-nums">
                    {evt.timestamp} · {source}
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Scrollbar style */}
      <style>{`
        .scrollbar-thin::-webkit-scrollbar {
          height: 3px;
        }
        .scrollbar-thin::-webkit-scrollbar-track {
          background: rgba(255,255,255,0.02);
        }
        .scrollbar-thin::-webkit-scrollbar-thumb {
          background: rgba(255,255,255,0.1);
          border-radius: 2px;
        }
      `}</style>
    </div>
  )
}
