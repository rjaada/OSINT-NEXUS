"use client"

import { useEffect, useMemo, useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"

interface SourceItem {
  id: string
  type: string
  desc: string
  source: string
  timestamp: string
  lat: number
  lng: number
  url?: string
  observed_facts?: string[]
  model_inference?: string[]
}

interface SourceOps {
  per_source: Record<string, {
    lag_seconds: number | null
    throughput_per_min: number
    events_window: number
    degraded: boolean
    last_success: string | null
  }>
  poll_errors: Record<string, number>
}

interface SourceResponse {
  items: SourceItem[]
  counts_by_source: Record<string, number>
  reliability_profile: Record<string, number>
  ops: SourceOps
  degraded_sources: string[]
  generated_at: string
}

interface EvalScorecard {
  reviewed_total: number
  confirmed: number
  rejected: number
  needs_review: number
  false_positive_rate_pct: number
  geo_accuracy_proxy_pct: number
}

interface SystemInfo {
  storage_backend: string
  ollama_model_primary: string
  ollama_model_fallback: string
  v2_ai_models?: { default?: string; chat?: string; verify?: string; report?: string }
  queue: { media_jobs_pending: number; media_jobs_tracked: number }
}

interface AiReport {
  summary: string
  threat_level: string
  key_developments: string[]
  insufficient_evidence?: boolean
  generated_at: string
  model: string
}

export default function SourcesPage() {
  const [data, setData] = useState<SourceResponse | null>(null)
  const [scorecard, setScorecard] = useState<EvalScorecard | null>(null)
  const [system, setSystem] = useState<SystemInfo | null>(null)
  const [report, setReport] = useState<AiReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)

  const sourceVolumes = useMemo(() => {
    const counts = data?.counts_by_source ?? {}
    return Object.entries(counts).sort((a, b) => Number(b[1]) - Number(a[1]))
  }, [data])

  useEffect(() => {
    const load = async () => {
      try {
        const [r1, r2, r3] = await Promise.all([
          fetch("http://localhost:8000/api/v2/sources?limit=220"),
          fetch("http://localhost:8000/api/v2/evaluation/scorecard"),
          fetch("http://localhost:8000/api/v2/system"),
        ])
        if (r1.ok) setData(await r1.json())
        if (r2.ok) setScorecard(await r2.json())
        if (r3.ok) setSystem(await r3.json())
      } catch (_) {}
    }
    load()
    const i = setInterval(load, 10000)
    return () => clearInterval(i)
  }, [])

  const loadReport = async (force = false) => {
    setReportLoading(true)
    try {
      const res = await fetch(`http://localhost:8000/api/v2/ai/report${force ? "?force=true" : ""}`, { cache: "no-store" })
      if (!res.ok) return
      const data: AiReport = await res.json()
      setReport(data)
    } catch (_) {
      // keep dashboard usable if report endpoint is unavailable
    } finally {
      setReportLoading(false)
    }
  }

  useEffect(() => {
    void loadReport(false)
    const i = setInterval(() => void loadReport(false), 30000)
    return () => clearInterval(i)
  }, [])

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />

      <main className="px-4 md:px-6 py-5">
        <div className="max-w-7xl mx-auto">
          <header className="mb-5">
            <p className="text-[10px] tracking-[0.18em] uppercase text-osint-blue mb-1">Source Desk v2</p>
            <h1 className="text-2xl md:text-3xl font-semibold">Sources, Reliability, and Pipeline Health</h1>
            <p className="text-xs text-muted-foreground mt-2">
              Facts are observed source records. Inference is model-derived interpretation and can be wrong.
            </p>
          </header>

          <section className="grid md:grid-cols-4 gap-3 mb-4">
            <article className="rounded-lg p-3 border border-white/10 bg-black/30 md:col-span-2">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-green mb-2">Source Volumes</p>
              <div className="flex flex-wrap gap-2 text-[11px]">
                {sourceVolumes.slice(0, 14).map(([k, v]) => (
                  <span key={k} className="px-2 py-1 rounded border border-white/10 text-[#c5c5d5]">
                    {k}: {v}
                  </span>
                ))}
              </div>
            </article>

            <article className="rounded-lg p-3 border border-white/10 bg-black/30">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-amber mb-2">Degraded Sources</p>
              <div className="text-[11px] text-muted-foreground space-y-1">
                {(data?.degraded_sources ?? []).length === 0
                  ? <p>None detected.</p>
                  : (data?.degraded_sources ?? []).map((x) => <p key={x}>• {x}</p>)}
              </div>
            </article>

            <article className="rounded-lg p-3 border border-white/10 bg-black/30">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-purple mb-2">Model + Queue</p>
              <div className="text-[11px] text-muted-foreground space-y-1">
                <p>Storage: {system?.storage_backend ?? "--"}</p>
                <p>Primary: {system?.ollama_model_primary ?? "--"}</p>
                <p>Fallback: {system?.ollama_model_fallback ?? "--"}</p>
                <p>Chat: {system?.v2_ai_models?.chat ?? "--"}</p>
                <p>Verify: {system?.v2_ai_models?.verify ?? "--"}</p>
                <p>Report: {system?.v2_ai_models?.report ?? "--"}</p>
                <p>Media queue: {system?.queue.media_jobs_pending ?? 0}</p>
              </div>
            </article>
          </section>

          <section className="rounded-lg border border-white/10 bg-black/30 p-3 mb-4">
            <div className="flex items-center gap-2 mb-2">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-purple">AI Report (v2)</p>
              <span className="text-[10px] text-muted-foreground">{report?.model ?? "model --"}</span>
              <button
                onClick={() => void loadReport(true)}
                className="ml-auto text-[10px] px-2 py-1 rounded border border-osint-purple/40 text-osint-purple"
                disabled={reportLoading}
              >
                {reportLoading ? "Refreshing..." : "Force Refresh"}
              </button>
            </div>
            <p className="text-[11px] text-[#d2d2de] mb-2">{report?.summary ?? "No report available."}</p>
            <div className="flex items-center gap-2 flex-wrap text-[10px]">
              <span className="px-2 py-0.5 rounded border border-white/10 text-[#d0d0df]">Threat: {report?.threat_level ?? "--"}</span>
              {report?.insufficient_evidence ? <span className="px-2 py-0.5 rounded border border-osint-amber/40 text-osint-amber">limited evidence</span> : null}
              <span className="text-muted-foreground">{report?.generated_at ?? ""}</span>
            </div>
            {(report?.key_developments || []).length > 0 ? (
              <p className="mt-2 text-[10px] text-muted-foreground">
                {report?.key_developments?.slice(0, 3).join(" | ")}
              </p>
            ) : null}
          </section>

          <section className="grid md:grid-cols-2 gap-3 mb-4">
            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-amber mb-2">Reliability Weights</p>
              <div className="grid sm:grid-cols-2 gap-2 text-[11px]">
                {Object.entries(data?.reliability_profile ?? {}).sort((a, b) => b[1] - a[1]).map(([name, weight]) => (
                  <div key={name} className="rounded border border-white/10 px-2 py-1 flex justify-between">
                    <span className="text-[#d0d0df]">{name}</span>
                    <span className="text-osint-blue">{weight}</span>
                  </div>
                ))}
              </div>
            </article>

            <article className="rounded-lg border border-white/10 bg-black/30 p-3">
              <p className="text-[10px] uppercase tracking-[0.14em] text-osint-green mb-2">Weekly Quality Scorecard</p>
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="rounded border border-white/10 p-2"><p className="text-muted-foreground">Reviewed</p><p className="text-[#d0d0df]">{scorecard?.reviewed_total ?? 0}</p></div>
                <div className="rounded border border-white/10 p-2"><p className="text-muted-foreground">Confirmed</p><p className="text-[#d0d0df]">{scorecard?.confirmed ?? 0}</p></div>
                <div className="rounded border border-white/10 p-2"><p className="text-muted-foreground">False positives</p><p className="text-[#d0d0df]">{scorecard?.false_positive_rate_pct ?? 0}%</p></div>
                <div className="rounded border border-white/10 p-2"><p className="text-muted-foreground">Geo accuracy proxy</p><p className="text-[#d0d0df]">{scorecard?.geo_accuracy_proxy_pct ?? 0}%</p></div>
              </div>
            </article>
          </section>

          <section className="rounded-lg border border-white/10 bg-black/30 p-3 mb-4">
            <p className="text-[10px] uppercase tracking-[0.14em] text-osint-blue mb-3">Per-Source Ops</p>
            <div className="grid gap-2">
              {Object.entries(data?.ops?.per_source ?? {}).sort((a, b) => (b[1].events_window - a[1].events_window)).map(([name, op]) => (
                <article key={name} className="rounded-md border border-white/10 p-2 text-[11px] grid md:grid-cols-5 gap-2">
                  <p className="text-[#d0d0df]">{name}</p>
                  <p className="text-muted-foreground">Lag: {op.lag_seconds ?? "--"}s</p>
                  <p className="text-muted-foreground">Rate: {op.throughput_per_min}/min</p>
                  <p className="text-muted-foreground">Window: {op.events_window}</p>
                  <p className={op.degraded ? "text-osint-red" : "text-osint-green"}>{op.degraded ? "DEGRADED" : "OK"}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-white/10 bg-black/30 p-3">
            <p className="text-[10px] uppercase tracking-[0.14em] text-osint-blue mb-3">Raw Feed (Latest)</p>
            <div className="grid gap-2">
              {(data?.items ?? []).slice(0, 80).map((item) => (
                <article key={item.id} className="rounded-md border border-white/10 p-2 text-[12px]">
                  <div className="flex flex-wrap gap-2 mb-1 text-[10px]">
                    <span className="px-1.5 py-0.5 border border-white/10 rounded">{item.type}</span>
                    <span className="px-1.5 py-0.5 border border-white/10 rounded text-muted-foreground">{item.source}</span>
                    <span className="ml-auto text-muted-foreground">{item.timestamp}</span>
                  </div>
                  <p className="text-[#d0d0df]">{item.desc.replace(/^\[.+?\]\s*/, "")}</p>
                  <div className="grid md:grid-cols-2 gap-2 mt-1 text-[10px]">
                    <p className="text-muted-foreground">{Number(item.lat).toFixed(3)}N {Number(item.lng).toFixed(3)}E</p>
                    <p className="text-muted-foreground text-right">{item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer" className="underline text-osint-blue">source</a> : ""}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}
