"use client"

import { useEffect, useState } from "react"
import { Activity, AlertTriangle, Plane, Radio, Shield, Clock } from "lucide-react"

interface Stats {
  events_total: number
  aircraft_tracked: number
  military_aircraft: number
  active_threats: number
  sources_active: number
  clients: number
  uptime_seconds: number
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
}

export function BottomBar() {
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/stats")
        if (res.ok) setStats(await res.json())
      } catch (_) {}
    }
    fetchStats()
    const interval = setInterval(fetchStats, 5000)
    return () => clearInterval(interval)
  }, [])

  const items = [
    { label: "Events Monitored", value: stats?.events_total ?? 0, icon: Activity, color: "#00ff88" },
    { label: "Active Threats", value: stats?.active_threats ?? 0, icon: AlertTriangle, color: "#ff1a3c" },
    { label: "Aircraft Tracked", value: stats?.aircraft_tracked ?? 0, icon: Plane, color: "#00b4d8" },
    { label: "Military AC", value: stats?.military_aircraft ?? 0, icon: Shield, color: "#ffa630" },
    { label: "Sources", value: stats?.sources_active ?? 0, icon: Radio, color: "#b24bff" },
  ]

  return (
    <footer className="glass-panel flex items-center justify-between px-4 py-2 border-t border-[rgba(255,255,255,0.06)]">
      <div className="flex items-center gap-6 md:gap-10">
        {items.map((stat) => {
          const Icon = stat.icon
          return (
            <div key={stat.label} className="flex items-center gap-2">
              <Icon className="h-3.5 w-3.5 hidden sm:block" style={{ color: stat.color }} />
              <div className="flex flex-col">
                <span className="text-[8px] uppercase tracking-[0.15em] text-muted-foreground leading-none mb-0.5">
                  {stat.label}
                </span>
                <span
                  className="text-sm font-bold tabular-nums leading-none"
                  style={{ color: stat.color }}
                >
                  {stat.value.toLocaleString()}
                </span>
              </div>
            </div>
          )
        })}
      </div>
      <div className="hidden lg:flex items-center gap-4">
        <div className="flex items-center gap-2 text-[9px] text-muted-foreground tracking-wider font-mono">
          <Clock className="h-3 w-3" />
          <span>UPTIME {stats ? formatUptime(stats.uptime_seconds) : "--:--:--"}</span>
        </div>
        <div className="flex items-center gap-2 text-[9px] text-muted-foreground tracking-wider">
          <span className="h-1.5 w-1.5 rounded-full bg-osint-green animate-pulse" />
          UPLINK ACTIVE / 128-BIT AES
        </div>
      </div>
    </footer>
  )
}
