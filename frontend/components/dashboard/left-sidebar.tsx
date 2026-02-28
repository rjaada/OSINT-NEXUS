"use client"

import { useState } from "react"
import { Plane, Ship, CloudOff, Crosshair, Newspaper } from "lucide-react"

const layers = [
  { icon: Plane, label: "Military Flights", color: "text-osint-blue", dotColor: "bg-osint-blue" },
  { icon: Ship, label: "Naval Vessels", color: "text-osint-green", dotColor: "bg-osint-green" },
  { icon: CloudOff, label: "Airspace (NOTAMs)", color: "text-osint-amber", dotColor: "bg-osint-amber" },
  { icon: Crosshair, label: "Conflict Events", color: "text-osint-red", dotColor: "bg-osint-red" },
  { icon: Newspaper, label: "News Feed", color: "text-osint-purple", dotColor: "bg-osint-purple" },
]

export function LeftSidebar() {
  const [active, setActive] = useState<Set<number>>(new Set([0, 1, 2, 3, 4]))

  const toggle = (index: number) => {
    setActive((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  return (
    <aside className="glass-panel flex flex-col items-center gap-1 py-3 px-1.5 border-r border-[rgba(255,255,255,0.06)]">
      <span className="text-[8px] uppercase tracking-widest text-muted-foreground mb-2">
        Layers
      </span>
      {layers.map((layer, i) => {
        const Icon = layer.icon
        const isActive = active.has(i)
        return (
          <button
            key={layer.label}
            onClick={() => toggle(i)}
            className={`relative flex flex-col items-center justify-center w-10 h-10 rounded-lg transition-all duration-200 group ${
              isActive
                ? "bg-[rgba(255,255,255,0.05)]"
                : "opacity-40 hover:opacity-70"
            }`}
            title={layer.label}
            aria-label={`Toggle ${layer.label}`}
            aria-pressed={isActive}
          >
            <Icon className={`h-4 w-4 ${isActive ? layer.color : "text-muted-foreground"}`} />
            <span
              className={`absolute top-1 right-1 h-1.5 w-1.5 rounded-full transition-all ${
                isActive ? layer.dotColor : "bg-muted-foreground/30"
              }`}
            />
          </button>
        )
      })}
    </aside>
  )
}
