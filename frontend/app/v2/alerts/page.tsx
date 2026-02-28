"use client"

import { useEffect, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"

type Confidence = "LOW" | "MEDIUM" | "HIGH"

interface AlertAssessment {
  id: string
  incident_id?: string
  type: "STRIKE" | "CRITICAL"
  desc: string
  timestamp: string
  lat: number
  lng: number
  source: string
  confidence: Confidence
  confidence_score: number
  confidence_reason?: string
  eta_band: string
  age_minutes: number
  corroborating_sources: string[]
  observed_facts?: string[]
  model_inference?: string[]
  insufficient_evidence?: boolean
  video_url?: string
  video_assessment?: string
  video_confidence?: string
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
  const [crisisMode, setCrisisMode] = useState(false)

  useEffect(() => {
    try {
      setCrisisMode(localStorage.getItem("osint_crisis_mode") === "1")
    } catch (_) {}

    const onMode = (e: Event) => {
      const custom = e as CustomEvent<{ crisis: boolean }>
      setCrisisMode(Boolean(custom.detail?.crisis))
    }
    window.addEventListener("osint:mode", onMode)
    return () => window.removeEventListener("osint:mode", onMode)
  }, [])

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/alerts/assessment?limit=${crisisMode ? 60 : 40}`)
        if (!res.ok) return
        const data: AlertAssessment[] = await res.json()
        const normalized = crisisMode
          ? data.filter((a) => a.type === "CRITICAL" || a.type === "STRIKE")
          : data
        setAlerts(normalized)
        setLastSync(new Date().toISOString().slice(11, 19) + "Z")
      } finally {
        setLoading(false)
      }
    }

    load()
    const interval = setInterval(load, crisisMode ? 7000 : 15000)
    return () => clearInterval(interval)
  }, [crisisMode])

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
                Advisory only. ETA is estimated. Follow official civil-defense instructions for safety decisions.
              </p>
            </div>
            <div className="text-[11px] text-muted-foreground">
              {loading ? "Syncing..." : `Last sync: ${lastSync || "--:--:--Z"}`}
            </div>
          </header>

          <section className="grid gap-3">
            {alerts.map((a) => {
              const c = CONF_STYLE[a.confidence]
              const cardPad = crisisMode ? "p-5" : "p-4"
              return (
                <article
                  key={a.id}
                  className={`rounded-xl ${cardPad}`}
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
                    {a.insufficient_evidence ? (
                      <span className="text-[9px] px-2 py-0.5 rounded tracking-[0.14em] uppercase border border-osint-amber/40 text-osint-amber">
                        Limited Evidence
                      </span>
                    ) : null}
                    <span className="ml-auto text-[10px] text-muted-foreground">{a.age_minutes}m ago</span>
                  </div>

                  <p className={`leading-relaxed mb-2 ${crisisMode ? "text-base" : "text-sm"} text-[#c9c9db]`}>
                    {a.desc.replace(/^\[.+?\]\s*/, "")}
                  </p>

                  <p className="text-[11px] text-osint-blue mb-3">Why this confidence: {a.confidence_reason || "insufficient data"}</p>

                  <div className="grid md:grid-cols-2 gap-3 text-[11px] mb-3">
                    <div className="rounded-md border border-white/10 p-2 bg-black/20">
                      <p className="text-[10px] uppercase tracking-[0.12em] text-osint-green mb-1">Observed Facts</p>
                      {(a.observed_facts && a.observed_facts.length > 0) ? (
                        <ul className="text-[#b7d7c1] list-disc pl-4 space-y-1">
                          {a.observed_facts.slice(0, 3).map((x, i) => <li key={i}>{x}</li>)}
                        </ul>
                      ) : <p className="text-muted-foreground">No direct extracted facts.</p>}
                    </div>

                    <div className="rounded-md border border-white/10 p-2 bg-black/20">
                      <p className="text-[10px] uppercase tracking-[0.12em] text-osint-amber mb-1">Model Inference</p>
                      {(a.model_inference && a.model_inference.length > 0) ? (
                        <ul className="text-[#d7c6a8] list-disc pl-4 space-y-1">
                          {a.model_inference.slice(0, 3).map((x, i) => <li key={i}>{x}</li>)}
                        </ul>
                      ) : <p className="text-muted-foreground">No model inference attached.</p>}
                    </div>
                  </div>

                  <div className="flex items-center gap-4 text-[11px] text-muted-foreground flex-wrap">
                    <span>{Number(a.lat).toFixed(3)}N {Number(a.lng).toFixed(3)}E</span>
                    <span>{a.timestamp}</span>
                    <span>
                      Corroboration: {a.corroborating_sources.length > 0 ? a.corroborating_sources.join(", ") : "single-source"}
                    </span>
                    {a.video_assessment ? (
                      <span>Video: {a.video_assessment} ({a.video_confidence || "LOW"})</span>
                    ) : null}
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
