"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"
import { VideoModal } from "@/components/system/video-modal"
import { readCookie } from "@/lib/security"

type Confidence = "LOW" | "MEDIUM" | "HIGH"

interface MediaCred {
  claim_alignment?: string
  credibility_note?: string
  transcript_text?: string
  transcript_language?: string
  transcript_error?: string
  deepfake_score?: string
  deepfake_label?: string
  deepfake_error?: string
}

interface AlertAssessment {
  id: string
  incident_id?: string
  type: "STRIKE" | "CRITICAL" | "CLASH"
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
  media?: MediaCred
  review?: { status?: string; analyst?: string; note?: string }
}

const CONF_STYLE: Record<Confidence, { text: string; bg: string; border: string }> = {
  LOW: { text: "#ffa630", bg: "#ffa63020", border: "#ffa63040" },
  MEDIUM: { text: "#00b4d8", bg: "#00b4d820", border: "#00b4d840" },
  HIGH: { text: "#00ff88", bg: "#00ff8820", border: "#00ff8840" },
}
const ALERTS_REFRESH_MS = 15000

function isPlayableVideoUrl(url?: string | null): boolean {
  if (!url) return false
  if (url.startsWith("/media/telegram/")) return true
  return /\.(mp4|webm|mov|m4v)(\?|$)/i.test(url)
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertAssessment[]>([])
  const [loading, setLoading] = useState(true)
  const [lastSync, setLastSync] = useState("")
  const [crisisMode, setCrisisMode] = useState(false)
  const [activeVideo, setActiveVideo] = useState<{ eventId: string; videoUrl: string; title: string } | null>(null)
  const [role, setRole] = useState("viewer")
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastRefreshTsRef = useRef(0)

  useEffect(() => {
    try {
      setCrisisMode(localStorage.getItem("osint_crisis_mode") === "1")
    } catch (_) {}
    setRole(readCookie("osint_role") || "viewer")

    const onMode = (e: Event) => {
      const custom = e as CustomEvent<{ crisis: boolean }>
      setCrisisMode(Boolean(custom.detail?.crisis))
    }
    window.addEventListener("osint:mode", onMode)
    return () => window.removeEventListener("osint:mode", onMode)
  }, [])

  const loadMain = useCallback(async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/v2/alerts?limit=${crisisMode ? 80 : 60}`, { cache: "no-store" })
      if (!res.ok) return
      const data: AlertAssessment[] = await res.json()
      const normalized = crisisMode ? data.filter((a) => a.type === "CRITICAL" || a.type === "STRIKE") : data
      setAlerts(normalized)
      setLastSync(new Date().toISOString().slice(11, 19) + "Z")
      lastRefreshTsRef.current = Date.now()
    } finally {
      setLoading(false)
    }
  }, [crisisMode])

  useEffect(() => {
    void loadMain()
    const interval = setInterval(loadMain, ALERTS_REFRESH_MS)
    return () => clearInterval(interval)
  }, [loadMain])

  useEffect(() => {
    let ws: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | null = null

    const scheduleRefresh = () => {
      const now = Date.now()
      const elapsed = now - lastRefreshTsRef.current
      if (elapsed >= 1500) {
        void loadMain()
        return
      }
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
      refreshTimerRef.current = setTimeout(() => void loadMain(), 1200)
    }

    const connect = () => {
      try {
        const wsUrl = (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000") + "/ws/live/v2"
        ws = new WebSocket(wsUrl)
        ws.onclose = () => {
          retry = setTimeout(connect, 3500)
        }
        ws.onerror = () => ws?.close()
        ws.onmessage = (evt) => {
          try {
            const payload = JSON.parse(evt.data)
            if (payload?.type !== "NEW_EVENT") return
            const data = payload?.data || {}
            const source = String(data.source || "")
            const typ = String(data.type || "")
            if (!source.endsWith("(TG)")) return
            if (!["STRIKE", "CRITICAL", "CLASH"].includes(typ)) return
            scheduleRefresh()
          } catch (_) {}
        }
      } catch (_) {
        retry = setTimeout(connect, 3500)
      }
    }

    connect()
    return () => {
      if (retry) clearTimeout(retry)
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
      ws?.close()
    }
  }, [loadMain])

  const criticalCount = useMemo(() => alerts.filter((a) => a.type === "CRITICAL").length, [alerts])
  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />

      <main className="px-4 md:px-6 py-5">
        <div className="max-w-7xl mx-auto">
          <header className="mb-5 flex items-end justify-between gap-3 flex-wrap">
            <div>
              <p className="text-[10px] tracking-[0.18em] uppercase text-osint-amber mb-1">Alert Intel v2</p>
              <h1 className="text-2xl md:text-3xl font-semibold">Confidence and ETA Board</h1>
              <p className="text-xs text-muted-foreground mt-2">
                Advisory only. Treat ETA as estimate and always prioritize official civil-defense instructions.
              </p>
            </div>
            <div className="text-[11px] text-muted-foreground text-right">
              <div>Role: {role}</div>
              <div>{loading ? "Syncing..." : `Last sync: ${lastSync || "--:--:--Z"}`}</div>
              <div>Critical cards: {criticalCount}</div>
            </div>
          </header>

          <section className="grid gap-3">
            {alerts.map((a) => {
              const c = CONF_STYLE[a.confidence]
              const videoHref = a.video_url ? (a.video_url.startsWith("/media/") ? `http://localhost:8000${a.video_url}` : a.video_url) : null
              const canInlineVideo = isPlayableVideoUrl(a.video_url)
              const review = a.review?.status || "unreviewed"
              return (
                <article
                  key={a.id}
                  className={`rounded-xl ${crisisMode ? "p-5" : "p-4"}`}
                  style={{ background: "rgba(7,8,12,0.92)", border: "1px solid rgba(255,255,255,0.08)" }}
                >
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <span className="text-[9px] px-2 py-0.5 rounded border border-white/10 tracking-[0.14em] uppercase">{a.type}</span>
                    <span className="text-[9px] px-2 py-0.5 rounded border border-white/10 tracking-[0.14em] uppercase text-muted-foreground">{a.source}</span>
                    <span className="text-[9px] px-2 py-0.5 rounded tracking-[0.14em] uppercase" style={{ color: c.text, background: c.bg, border: `1px solid ${c.border}` }}>
                      Confidence {a.confidence} ({a.confidence_score})
                    </span>
                    <span className="text-[9px] px-2 py-0.5 rounded tracking-[0.14em] uppercase border border-osint-red/30 text-osint-red">ETA {a.eta_band}</span>
                    <span className="text-[9px] px-2 py-0.5 rounded tracking-[0.14em] uppercase border border-osint-blue/30 text-osint-blue">{review}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground">{a.age_minutes}m ago</span>
                  </div>

                  <p className={`leading-relaxed mb-2 ${crisisMode ? "text-base" : "text-sm"} text-[#c9c9db]`}>
                    {a.desc.replace(/^\[.+?\]\s*/, "")}
                  </p>

                  <div className="flex items-center gap-2 flex-wrap mb-2 text-[10px]">
                    <span className="px-2 py-0.5 rounded border border-osint-blue/30 text-osint-blue">{a.confidence_reason || "no reason"}</span>
                    {a.insufficient_evidence ? <span className="px-2 py-0.5 rounded border border-osint-amber/40 text-osint-amber">limited evidence</span> : null}
                    {a.video_assessment ? <span className="px-2 py-0.5 rounded border border-osint-green/30 text-osint-green">video {a.video_assessment}</span> : null}
                    {a.media?.claim_alignment ? (
                      <span className="px-2 py-0.5 rounded border border-osint-purple/40 text-osint-purple">media {a.media.claim_alignment}</span>
                    ) : null}
                  </div>

                  <div className="grid md:grid-cols-3 gap-3 text-[11px] mb-3">
                    <div className="rounded-md border border-white/10 p-2 bg-black/20">
                      <p className="text-[10px] uppercase tracking-[0.12em] text-osint-green mb-1">Observed Facts</p>
                      {(a.observed_facts && a.observed_facts.length > 0) ? (
                        <ul className="text-[#b7d7c1] list-disc pl-4 space-y-1">
                          {a.observed_facts.slice(0, 3).map((x, i) => <li key={i}>{x}</li>)}
                        </ul>
                      ) : <p className="text-muted-foreground">No direct facts extracted.</p>}
                    </div>

                    <div className="rounded-md border border-white/10 p-2 bg-black/20">
                      <p className="text-[10px] uppercase tracking-[0.12em] text-osint-amber mb-1">Model Inference</p>
                      {(a.model_inference && a.model_inference.length > 0) ? (
                        <ul className="text-[#d7c6a8] list-disc pl-4 space-y-1">
                          {a.model_inference.slice(0, 3).map((x, i) => <li key={i}>{x}</li>)}
                        </ul>
                      ) : <p className="text-muted-foreground">No model inference.</p>}
                    </div>

                    <div className="rounded-md border border-white/10 p-2 bg-black/20">
                      <p className="text-[10px] uppercase tracking-[0.12em] text-osint-purple mb-1">Media Credibility</p>
                      <p className="text-[#c7b9dd] line-clamp-3">{a.media?.credibility_note || "Pending media analysis."}</p>
                      {a.media?.deepfake_label || a.media?.deepfake_score ? (
                        <p className="text-[10px] text-osint-amber mt-2">
                          Deepfake: {a.media?.deepfake_label || "unknown"} {a.media?.deepfake_score ? `(${a.media.deepfake_score})` : ""}
                        </p>
                      ) : null}
                      {a.media?.deepfake_error ? (
                        <p className="text-[10px] text-osint-red mt-1">Deepfake hook: {a.media.deepfake_error}</p>
                      ) : null}
                      {a.media?.transcript_text ? (
                        <p className="text-[10px] text-[#a6d2c9] mt-2 line-clamp-3">
                          Transcript{a.media?.transcript_language ? ` (${a.media.transcript_language})` : ""}: {a.media.transcript_text}
                        </p>
                      ) : null}
                      {a.media?.transcript_error ? (
                        <p className="text-[10px] text-osint-red mt-1">Transcription hook: {a.media.transcript_error}</p>
                      ) : null}
                    </div>
                  </div>

                  <div className="rounded-md border border-white/10 p-2 bg-black/20 mb-3 text-[10px]">
                    <p className="text-[10px] uppercase tracking-[0.12em] text-osint-blue mb-1">Data Provenance</p>
                    <div className="grid md:grid-cols-2 gap-1 text-muted-foreground">
                      <p>Sensor/source: {a.source}</p>
                      <p className="md:text-right">Chain status: {a.review?.status || "unreviewed"}</p>
                      <p>Corroborated by: {a.corroborating_sources.length > 0 ? a.corroborating_sources.join(", ") : "single-source"}</p>
                      <p className="md:text-right">Last corroborated: {a.timestamp}</p>
                      <p>Analyst: {a.review?.analyst || "n/a"}</p>
                      <p className="md:text-right">Confidence lineage: {a.confidence} ({a.confidence_score})</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap text-[11px] text-muted-foreground">
                    <span>{Number(a.lat).toFixed(3)}N {Number(a.lng).toFixed(3)}E</span>
                    <span>{a.timestamp}</span>
                    <span>Corroboration: {a.corroborating_sources.length > 0 ? a.corroborating_sources.join(", ") : "single-source"}</span>
                    {videoHref && canInlineVideo ? (
                      <button
                        onClick={() => setActiveVideo({ eventId: a.id, videoUrl: a.video_url || "", title: a.desc.replace(/^\[.+?\]\s*/, "") })}
                        className="text-osint-green underline"
                      >
                        Latest Video
                      </button>
                    ) : null}

                  </div>
                </article>
              )
            })}
          </section>
        </div>
      </main>

      <VideoModal
        open={Boolean(activeVideo)}
        eventId={activeVideo?.eventId}
        videoUrl={activeVideo?.videoUrl}
        title={activeVideo?.title}
        onClose={() => setActiveVideo(null)}
        onConsumed={() => loadMain()}
      />
    </div>
  )
}
