"use client"

import { useEffect, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"

type Confidence = "LOW" | "MEDIUM" | "HIGH"

interface AlertAssessment {
  id: string
  type: "STRIKE" | "CRITICAL"
  desc: string
  timestamp: string
  lat: number
  lng: number
  source: string
  confidence: Confidence
  confidence_score: number
  eta_band: string
  age_minutes: number
  corroborating_sources: string[]
  video_url?: string
}

const CONF_STYLE: Record<Confidence, { text: string; bg: string; border: string }> = {
  LOW: { text: "#ffa630", bg: "#ffa63020", border: "#ffa63040" },
  MEDIUM: { text: "#00b4d8", bg: "#00b4d820", border: "#00b4d840" },
  HIGH: { text: "#00ff88", bg: "#00ff8820", border: "#00ff8840" },
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertAssessment[]>([])
  const [loading, setLoading] = useState(true)
  const [lastSync, setLastSync] = useState("")

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/alerts/assessment?limit=40")
        if (!res.ok) return
        const data: AlertAssessment[] = await res.json()
        setAlerts(data)
        setLastSync(new Date().toISOString().slice(11, 19) + "Z")
      } finally {
        setLoading(false)
      }
    }

    load()
    const interval = setInterval(load, 15000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />

      <main className="px-4 md:px-6 py-5">
        <div className="max-w-7xl mx-auto">
          <header className="mb-5 flex items-end justify-between gap-3 flex-wrap">
            <div>
              <p className="text-[10px] tracking-[0.18em] uppercase text-osint-amber mb-1">Alert Intel</p>
              <h1 className="text-2xl md:text-3xl font-semibold">Confidence and ETA Board</h1>
              <p className="text-xs text-muted-foreground mt-2">
                Advisory only. Always prioritize official civil-defense instructions.
              </p>
            </div>
            <div className="text-[11px] text-muted-foreground">
              {loading ? "Syncing..." : `Last sync: ${lastSync || "--:--:--Z"}`}
            </div>
          </header>

          <section className="grid gap-3">
            {alerts.map((a) => {
              const c = CONF_STYLE[a.confidence]
              return (
                <article
                  key={a.id}
                  className="rounded-xl p-4"
                  style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
                >
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <span className="text-[9px] px-2 py-0.5 rounded border border-white/10 tracking-[0.14em] uppercase">
                      {a.type}
                    </span>
                    <span className="text-[9px] px-2 py-0.5 rounded border border-white/10 tracking-[0.14em] uppercase text-muted-foreground">
                      {a.source}
                    </span>
                    <span
                      className="text-[9px] px-2 py-0.5 rounded tracking-[0.14em] uppercase"
                      style={{ color: c.text, background: c.bg, border: `1px solid ${c.border}` }}
                    >
                      Confidence {a.confidence} ({a.confidence_score})
                    </span>
                    <span className="text-[9px] px-2 py-0.5 rounded tracking-[0.14em] uppercase border border-osint-red/30 text-osint-red">
                      ETA {a.eta_band}
                    </span>
                    <span className="ml-auto text-[10px] text-muted-foreground">{a.age_minutes}m ago</span>
                  </div>

                  <p className="text-sm text-[#b5b5c8] leading-relaxed mb-3">{a.desc.replace(/^\[.+?\]\s*/, "")}</p>

                  <div className="flex items-center gap-4 text-[11px] text-muted-foreground flex-wrap">
                    <span>{Number(a.lat).toFixed(3)}N {Number(a.lng).toFixed(3)}E</span>
                    <span>{a.timestamp}</span>
                    <span>
                      Corroboration: {a.corroborating_sources.length > 0 ? a.corroborating_sources.join(", ") : "single-source"}
                    </span>
                    {a.video_url && (
                      <a
                        href={a.video_url.startsWith("/media/") ? `http://localhost:8000${a.video_url}` : a.video_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-osint-green underline underline-offset-2"
                      >
                        Latest Video
                      </a>
                    )}
                  </div>
                </article>
              )
            })}
          </section>
        </div>
      </main>
    </div>
  )
}
