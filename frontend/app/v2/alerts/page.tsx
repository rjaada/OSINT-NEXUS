"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"
import { VideoModal } from "@/components/system/video-modal"
import { csrfHeaders, readCookie } from "@/lib/security"

type Confidence = "LOW" | "MEDIUM" | "HIGH"
type ReviewState = "confirm" | "reject" | "needs_review"

interface MediaCred {
  claim_alignment?: string
  credibility_note?: string
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

interface VerifyResult {
  classification: string
  confidence_0_to_100: number
  reasoning: string[]
  required_follow_up: string[]
  insufficient_evidence: boolean
  model: string
  generated_at: string
}

const CONF_STYLE: Record<Confidence, { text: string; bg: string; border: string }> = {
  LOW: { text: "#ffa630", bg: "#ffa63020", border: "#ffa63040" },
  MEDIUM: { text: "#00b4d8", bg: "#00b4d820", border: "#00b4d840" },
  HIGH: { text: "#00ff88", bg: "#00ff8820", border: "#00ff8840" },
}
const ALERTS_REFRESH_MS = 15000

function requestHeaders() {
  let apiKey = ""
  try {
    apiKey = localStorage.getItem("osint_v2_api_key") || ""
  } catch (_) {}
  return csrfHeaders({
    "Content-Type": "application/json",
    "x-api-key": apiKey,
  })
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertAssessment[]>([])
  const [loading, setLoading] = useState(true)
  const [lastSync, setLastSync] = useState("")
  const [crisisMode, setCrisisMode] = useState(false)
  const [activeVideo, setActiveVideo] = useState<{ eventId: string; videoUrl: string; title: string } | null>(null)
  const [role, setRole] = useState("viewer")
  const [verifyingId, setVerifyingId] = useState<string | null>(null)
  const [verifyById, setVerifyById] = useState<Record<string, VerifyResult>>({})
  const [briefBusy, setBriefBusy] = useState<"" | "SITREP" | "INTSUM">("")
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
  const strikeCount = useMemo(() => alerts.filter((a) => a.type === "STRIKE").length, [alerts])
  const canReview = role === "analyst" || role === "admin"

  const exportReport = async (mode: "SITREP" | "INTSUM") => {
    setBriefBusy(mode)
    try {
      const res = await fetch("http://localhost:8000/api/v2/ai/ops-brief", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, limit: 22 }),
      })
      if (res.ok) {
        const data = await res.json()
        const now = new Date()
        const lines: string[] = []
        lines.push("SECRET // NOFORN // REL TO FVEY")
        lines.push(`${mode} // OSINT NEXUS AI OPS BRIEF`)
        lines.push(`GENERATED_AT: ${data.generated_at || now.toISOString()}`)
        lines.push(`MODELS: verify=${data?.model_policy?.task_models?.verify || "-"} report=${data?.model_policy?.task_models?.report || "-"}`)
        lines.push("")
        lines.push(`TITLE: ${data?.report?.title || mode}`)
        lines.push(`SUMMARY: ${data?.report?.summary || ""}`)
        lines.push("")
        lines.push("PARAGRAPHS:")
        for (const p of (data?.report?.paragraphs || [])) lines.push(`- ${p}`)
        lines.push("")
        lines.push("PRIORITY ACTIONS:")
        for (const a of (data?.report?.priority_actions || [])) lines.push(`- ${a}`)
        lines.push("")
        lines.push("COMMANDER NOTE:")
        lines.push(`- ${data?.commander_chat?.one_line_risk || ""}`)
        for (const a of (data?.commander_chat?.next_actions || [])) lines.push(`- ${a}`)
        lines.push("")
        lines.push("TOP VERIFY RESULTS:")
        for (const v of (data?.verify || [])) {
          lines.push(`- ${v?.event_id}: ${v?.result?.classification || "unknown"} (${v?.result?.confidence_0_to_100 || "-"})`)
        }
        lines.push("")
        lines.push("SECRET // NOFORN // REL TO FVEY")
        const text = lines.join("\n")
        const blob = new Blob([text], { type: "text/plain;charset=utf-8" })
        const url = URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = url
        a.download = `${mode.toLowerCase()}_${now.toISOString().replace(/[:.]/g, "-")}.txt`
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
        return
      }
    } catch (_) {
      // fall back to local report render below
    }

    const now = new Date()
    const day = String(now.getUTCDate()).padStart(2, "0")
    const hh = String(now.getUTCHours()).padStart(2, "0")
    const mm = String(now.getUTCMinutes()).padStart(2, "0")
    const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    const dtg = `${day}${hh}${mm}Z${months[now.getUTCMonth()]}${now.getUTCFullYear()}`

    const lines: string[] = []
    lines.push("SECRET // NOFORN // REL TO FVEY")
    lines.push(`${mode} // OSINT NEXUS`)
    lines.push(`DTG: ${dtg}`)
    lines.push(`ROLE: ${role.toUpperCase()}`)
    lines.push(`TOTAL ALERTS: ${alerts.length} | CRITICAL: ${criticalCount} | STRIKE: ${strikeCount}`)
    lines.push("")
    lines.push("1. SITUATION OVERVIEW")
    lines.push(`- Last sync: ${lastSync || "--:--:--Z"}`)
    lines.push(`- Operational mode: ${crisisMode ? "CRISIS" : "NORMAL"}`)
    lines.push("")
    lines.push("2. KEY INCIDENTS")
    alerts.slice(0, 20).forEach((a, i) => {
      lines.push(`${i + 1}. [${a.type}] ${a.desc.replace(/^\[.+?\]\s*/, "").slice(0, 180)}`)
      lines.push(`   DTG: ${a.timestamp} | SOURCE: ${a.source} | CONFIDENCE: ${a.confidence} (${a.confidence_score})`)
      lines.push(`   GRID/COORD: ${Number(a.lat).toFixed(3)}N ${Number(a.lng).toFixed(3)}E | ETA: ${a.eta_band}`)
      lines.push(`   PROVENANCE: source=${a.source}; corroboration=${a.corroborating_sources.length > 0 ? a.corroborating_sources.join(",") : "single-source"}; reviewed=${a.review?.status || "unreviewed"}`)
      if (a.observed_facts && a.observed_facts.length > 0) lines.push(`   OBSERVED: ${a.observed_facts.slice(0, 2).join(" | ")}`)
      if (a.model_inference && a.model_inference.length > 0) lines.push(`   INFERENCE: ${a.model_inference.slice(0, 2).join(" | ")}`)
      lines.push("")
    })
    lines.push("3. DISPOSITION")
    lines.push("- Advisory use only. Validate through official channels before action.")
    lines.push("")
    lines.push("SECRET // NOFORN // REL TO FVEY")

    const text = lines.join("\n")
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${mode.toLowerCase()}_${now.toISOString().replace(/[:.]/g, "-")}.txt`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    setBriefBusy("")
  }

  useEffect(() => {
    if (!briefBusy) return
    const t = setTimeout(() => setBriefBusy(""), 400)
    return () => clearTimeout(t)
  }, [briefBusy])

  const setReview = async (eventId: string, status: ReviewState) => {
    if (!canReview) return
    try {
      await fetch("http://localhost:8000/api/v2/reviews", {
        method: "POST",
        headers: requestHeaders(),
        credentials: "include",
        body: JSON.stringify({ event_id: eventId, status, note: "set from v2 alert board" }),
      })
      await loadMain()
    } catch (_) {}
  }

  const runVerify = async (a: AlertAssessment) => {
    setVerifyingId(a.id)
    try {
      const bodyPayload = [
        a.desc.replace(/^\[.+?\]\s*/, ""),
        (a.observed_facts || []).slice(0, 3).join("; "),
        (a.model_inference || []).slice(0, 3).join("; "),
      ].filter(Boolean).join(" | ")
      const res = await fetch("http://localhost:8000/api/v2/ai/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: a.desc.replace(/^\[.+?\]\s*/, "").slice(0, 220),
          body: bodyPayload.slice(0, 1200),
          source: a.source,
          published_at: a.timestamp,
        }),
      })
      if (!res.ok) return
      const data: VerifyResult = await res.json()
      setVerifyById((prev) => ({ ...prev, [a.id]: data }))
    } catch (_) {
      // keep page usable if verify endpoint is unavailable
    } finally {
      setVerifyingId(null)
    }
  }

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
              <div className="mt-2 flex items-center justify-end gap-2">
                <button className="text-[10px] px-2 py-1 rounded border border-osint-blue/40 text-osint-blue" onClick={() => exportReport("SITREP")}>
                  {briefBusy === "SITREP" ? "Generating..." : "Generate SITREP"}
                </button>
                <button className="text-[10px] px-2 py-1 rounded border border-osint-purple/40 text-osint-purple" onClick={() => exportReport("INTSUM")}>
                  {briefBusy === "INTSUM" ? "Generating..." : "Generate INTSUM"}
                </button>
              </div>
            </div>
          </header>

          <section className="grid gap-3">
            {alerts.map((a) => {
              const c = CONF_STYLE[a.confidence]
              const videoHref = a.video_url ? (a.video_url.startsWith("/media/") ? `http://localhost:8000${a.video_url}` : a.video_url) : null
              const review = a.review?.status || "unreviewed"
              const verify = verifyById[a.id]
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
                    {videoHref ? (
                      <button
                        onClick={() => setActiveVideo({ eventId: a.id, videoUrl: a.video_url || "", title: a.desc.replace(/^\[.+?\]\s*/, "") })}
                        className="text-osint-green underline"
                      >
                        Latest Video
                      </button>
                    ) : null}

                    {canReview ? (
                      <>
                        <button
                          className="ml-auto text-[10px] px-2 py-1 rounded border border-osint-blue/40 text-osint-blue"
                          onClick={() => runVerify(a)}
                          disabled={verifyingId === a.id}
                        >
                          {verifyingId === a.id ? "Verifying..." : "AI Verify"}
                        </button>
                        <button className="ml-auto text-[10px] px-2 py-1 rounded border border-osint-green/40 text-osint-green" onClick={() => setReview(a.id, "confirm")}>Confirm</button>
                        <button className="text-[10px] px-2 py-1 rounded border border-osint-red/40 text-osint-red" onClick={() => setReview(a.id, "reject")}>Reject</button>
                        <button className="text-[10px] px-2 py-1 rounded border border-osint-amber/40 text-osint-amber" onClick={() => setReview(a.id, "needs_review")}>Needs Review</button>
                      </>
                    ) : (
                      <button
                        className="ml-auto text-[10px] px-2 py-1 rounded border border-osint-blue/40 text-osint-blue"
                        onClick={() => runVerify(a)}
                        disabled={verifyingId === a.id}
                      >
                        {verifyingId === a.id ? "Verifying..." : "AI Verify"}
                      </button>
                    )}
                  </div>

                  {verify ? (
                    <div className="mt-3 rounded-md border border-osint-blue/30 bg-osint-blue/10 p-2 text-[10px]">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="uppercase tracking-[0.14em] text-osint-blue">verify</span>
                        <span className="text-[#d0d6e8]">{verify.classification}</span>
                        <span className="text-[#d0d6e8]">({verify.confidence_0_to_100})</span>
                        <span className="text-muted-foreground">{verify.model}</span>
                      </div>
                      {(verify.reasoning || []).length > 0 ? (
                        <p className="text-[#c4cad9]">Reason: {verify.reasoning.slice(0, 2).join(" | ")}</p>
                      ) : null}
                      {(verify.required_follow_up || []).length > 0 ? (
                        <p className="text-osint-amber">Follow-up: {verify.required_follow_up.slice(0, 2).join(" | ")}</p>
                      ) : null}
                    </div>
                  ) : null}
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
