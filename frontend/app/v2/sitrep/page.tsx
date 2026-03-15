"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"

interface WatchItem {
  item: string
  timeframe: string
  why: string
}

interface Contradiction {
  event_a: { id: string; desc: string; source: string; type: string }
  event_b: { id: string; desc: string; source: string; type: string }
  conflict_type: string
  location: { lat: number; lng: number }
}

interface Sitrep {
  headline: string
  what_happened: string
  why_it_matters: string
  causal_chain: string[]
  contradictions_summary: string
  historical_parallel: string
  watch_items: WatchItem[]
  confidence: "HIGH" | "MEDIUM" | "LOW"
  confidence_reason: string
  dominant_actors: string[]
  key_locations: string[]
}

interface SitrepReport {
  generated_at: string
  event_count: number
  cluster_count: number
  dominant_cluster_size: number
  data_quality: "rich" | "partial" | "sparse" | "no_data"
  contradictions: Contradiction[]
  historical_patterns: string[]
  sitrep: Sitrep | null
  groq_available: boolean
  neo4j_available: boolean
  watch_items: WatchItem[]
}

interface AccuracyStats {
  total: number
  correct: number
  partial: number
  incorrect: number
  pending: number
  accuracy_pct: number | null
  scored: number
  window_days: number
}

const CONFIDENCE_COLOR = {
  HIGH: "text-emerald-400 border-emerald-400/40 bg-emerald-400/10",
  MEDIUM: "text-amber-400 border-amber-400/40 bg-amber-400/10",
  LOW: "text-red-400 border-red-400/40 bg-red-400/10",
}

const QUALITY_LABEL = {
  rich: { label: "RICH DATA", color: "text-emerald-400" },
  partial: { label: "PARTIAL DATA", color: "text-amber-400" },
  sparse: { label: "SPARSE DATA", color: "text-orange-400" },
  no_data: { label: "NO DATA", color: "text-zinc-500" },
}

function formatTs(iso: string) {
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      timeZone: "UTC", timeZoneName: "short",
    })
  } catch { return iso }
}

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono font-bold tracking-widest border ${color}`}>
      {label}
    </span>
  )
}

function ScanLine() {
  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden rounded">
      <div className="w-full h-px bg-gradient-to-r from-transparent via-amber-400/20 to-transparent animate-[scan_4s_linear_infinite]" />
    </div>
  )
}

function CausalChain({ steps }: { steps: string[] }) {
  if (!steps?.length) return null
  return (
    <div className="flex flex-col gap-0">
      {steps.map((step, i) => (
        <div key={i} className="flex items-start gap-3">
          <div className="flex flex-col items-center">
            <div className="w-7 h-7 rounded-full border border-amber-400/60 bg-amber-400/10 flex items-center justify-center text-amber-400 text-xs font-bold font-mono flex-shrink-0">
              {i + 1}
            </div>
            {i < steps.length - 1 && (
              <div className="w-px flex-1 bg-amber-400/20 my-1 min-h-[20px]" />
            )}
          </div>
          <div className="pb-4 pt-1">
            <p className="text-zinc-200 text-sm leading-relaxed">{step}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function WatchCard({ item, index }: { item: WatchItem; index: number }) {
  const colors = ["border-amber-400/30", "border-blue-400/30", "border-violet-400/30"]
  const dots = ["bg-amber-400", "bg-blue-400", "bg-violet-400"]
  return (
    <div className={`rounded border ${colors[index % 3]} bg-zinc-900/60 p-4`}>
      <div className="flex items-center gap-2 mb-2">
        <div className={`w-2 h-2 rounded-full ${dots[index % 3]} animate-pulse`} />
        <span className="text-[10px] font-mono text-zinc-400 tracking-widest uppercase">
          Watch Item {index + 1}
        </span>
        <span className="ml-auto text-[10px] font-mono text-zinc-500 border border-zinc-700 px-2 py-0.5 rounded">
          {item.timeframe}
        </span>
      </div>
      <p className="text-zinc-100 text-sm font-medium mb-1">{item.item}</p>
      <p className="text-zinc-500 text-xs leading-relaxed">{item.why}</p>
    </div>
  )
}

function AccuracyBadge({ stats }: { stats: AccuracyStats }) {
  const pct = stats.accuracy_pct
  const color = pct == null ? "text-zinc-500" : pct >= 70 ? "text-emerald-400" : pct >= 50 ? "text-amber-400" : "text-red-400"
  return (
    <div className="rounded border border-zinc-700 bg-zinc-900/60 p-4">
      <div className="text-[10px] font-mono text-zinc-500 tracking-widest uppercase mb-3">Prediction Accuracy (last {stats.window_days}d)</div>
      <div className={`text-4xl font-mono font-bold ${color} mb-2`}>
        {pct != null ? `${pct}%` : "—"}
      </div>
      <div className="flex gap-3 text-xs font-mono">
        <span className="text-emerald-400">✓ {stats.correct} correct</span>
        <span className="text-amber-400">~ {stats.partial} partial</span>
        <span className="text-red-400">✗ {stats.incorrect} wrong</span>
        <span className="text-zinc-500">⏳ {stats.pending} pending</span>
      </div>
    </div>
  )
}

export default function SitrepPage() {
  const router = useRouter()
  const [report, setReport] = useState<SitrepReport | null>(null)
  const [accuracy, setAccuracy] = useState<AccuracyStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nextRefresh, setNextRefresh] = useState(3600)

  const fetchData = useCallback(async () => {
    try {
      const [sitrepRes, accRes] = await Promise.all([
        fetch("/api/v2/sitrep/latest", { credentials: "include" }),
        fetch("/api/v2/sitrep/accuracy", { credentials: "include" }),
      ])
      if (sitrepRes.status === 401 || accRes.status === 401) {
        router.push("/v2")
        return
      }
      const sitrepData = await sitrepRes.json()
      const accData = await accRes.json()
      setReport(sitrepData)
      setAccuracy(accData)
      setNextRefresh(3600)
      setError(null)
    } catch (e) {
      setError("Failed to load SITREP")
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60 * 60 * 1000)
    return () => clearInterval(interval)
  }, [fetchData])

  // Countdown timer
  useEffect(() => {
    const t = setInterval(() => setNextRefresh(p => Math.max(0, p - 1)), 1000)
    return () => clearInterval(t)
  }, [])

  const formatCountdown = (secs: number) => {
    const m = Math.floor(secs / 60).toString().padStart(2, "0")
    const s = (secs % 60).toString().padStart(2, "0")
    return `${m}:${s}`
  }

  const sitrep = report?.sitrep

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <TopBar />
      <CommandNav />
      <main className="p-6 max-w-7xl mx-auto">

          {/* Header */}
          <div className="mb-6 flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <div className="w-1 h-8 bg-amber-400 rounded" />
                <h1 className="text-2xl font-mono font-bold tracking-widest text-zinc-100 uppercase">
                  Situation Report
                </h1>
                <Pill label="AUTO-GENERATED" color="text-amber-400 border-amber-400/40 bg-amber-400/10" />
              </div>
              <p className="text-zinc-500 text-xs font-mono ml-4">
                AI-powered all-source intelligence synthesis · Updates every 60 min
              </p>
            </div>
            <div className="text-right">
              <div className="text-[10px] font-mono text-zinc-500 mb-1">NEXT REFRESH</div>
              <div className="text-amber-400 font-mono text-xl font-bold">{formatCountdown(nextRefresh)}</div>
              <button
                onClick={fetchData}
                className="mt-1 text-[10px] font-mono text-zinc-500 hover:text-amber-400 transition-colors"
              >
                FORCE REFRESH ↺
              </button>
            </div>
          </div>

          {loading && (
            <div className="flex items-center justify-center h-64">
              <div className="text-amber-400 font-mono text-sm animate-pulse">GENERATING INTELLIGENCE PICTURE...</div>
            </div>
          )}

          {error && (
            <div className="rounded border border-red-500/40 bg-red-500/10 p-4 text-red-400 font-mono text-sm">
              {error}
            </div>
          )}

          {!loading && !error && !sitrep && (
            <div className="rounded border border-zinc-700 bg-zinc-900/60 p-8 text-center">
              <div className="text-zinc-500 font-mono text-sm mb-2">NO SITREP AVAILABLE YET</div>
              <div className="text-zinc-600 text-xs font-mono">
                The reasoning engine runs 2 minutes after startup, then every 60 minutes.<br />
                Check back shortly.
              </div>
              <div className="mt-4 flex items-center justify-center gap-4 text-xs font-mono">
                <span className={report?.groq_available ? "text-emerald-400" : "text-red-400"}>
                  {report?.groq_available ? "● GROQ ONLINE" : "● GROQ OFFLINE"}
                </span>
                <span className={report?.neo4j_available ? "text-emerald-400" : "text-zinc-500"}>
                  {report?.neo4j_available ? "● NEO4J ONLINE" : "○ NEO4J OFFLINE"}
                </span>
              </div>
            </div>
          )}

          {sitrep && report && (
            <div className="space-y-4">

              {/* System status bar */}
              <div className="flex items-center gap-4 text-[10px] font-mono text-zinc-500 border border-zinc-800 rounded px-3 py-2 bg-zinc-900/40">
                <span>Generated: <span className="text-zinc-300">{formatTs(report.generated_at)}</span></span>
                <span>·</span>
                <span>Events analysed: <span className="text-zinc-300">{report.event_count}</span></span>
                <span>·</span>
                <span>Dominant cluster: <span className="text-zinc-300">{report.dominant_cluster_size} events</span></span>
                <span>·</span>
                <span className={QUALITY_LABEL[report.data_quality]?.color}>{QUALITY_LABEL[report.data_quality]?.label}</span>
                <span className="ml-auto flex gap-3">
                  <span className={report.groq_available ? "text-emerald-400" : "text-red-400"}>
                    {report.groq_available ? "● GROQ" : "○ GROQ"}
                  </span>
                  <span className={report.neo4j_available ? "text-emerald-400" : "text-zinc-500"}>
                    {report.neo4j_available ? "● NEO4J" : "○ NEO4J"}
                  </span>
                </span>
              </div>

              {/* Headline */}
              <div className="relative rounded border border-amber-400/30 bg-zinc-900/80 p-6 overflow-hidden">
                <ScanLine />
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="text-[10px] font-mono text-amber-400/60 tracking-widest uppercase mb-2">
                      ▸ HEADLINE ASSESSMENT
                    </div>
                    <h2 className="text-xl font-bold text-amber-400 leading-snug font-mono">
                      {sitrep.headline}
                    </h2>
                  </div>
                  <div className={`flex-shrink-0 px-3 py-2 rounded border text-center ${CONFIDENCE_COLOR[sitrep.confidence]}`}>
                    <div className="text-[9px] font-mono tracking-widest opacity-70 mb-1">CONFIDENCE</div>
                    <div className="text-lg font-mono font-bold">{sitrep.confidence}</div>
                  </div>
                </div>
                <div className="mt-2 text-zinc-500 text-xs font-mono">{sitrep.confidence_reason}</div>
              </div>

              {/* Two-column: what happened + why it matters */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded border border-zinc-700 bg-zinc-900/60 p-5">
                  <div className="text-[10px] font-mono text-zinc-500 tracking-widest uppercase mb-3">▸ WHAT HAPPENED</div>
                  <p className="text-zinc-200 text-sm leading-relaxed">{sitrep.what_happened}</p>
                </div>
                <div className="rounded border border-blue-400/20 bg-blue-400/5 p-5">
                  <div className="text-[10px] font-mono text-blue-400/70 tracking-widest uppercase mb-3">▸ WHY IT MATTERS</div>
                  <p className="text-zinc-200 text-sm leading-relaxed">{sitrep.why_it_matters}</p>
                </div>
              </div>

              {/* Causal chain */}
              {sitrep.causal_chain?.length > 0 && (
                <div className="rounded border border-zinc-700 bg-zinc-900/60 p-5">
                  <div className="text-[10px] font-mono text-zinc-500 tracking-widest uppercase mb-4">▸ CAUSAL CHAIN</div>
                  <CausalChain steps={sitrep.causal_chain} />
                </div>
              )}

              {/* Watch items */}
              {sitrep.watch_items?.length > 0 && (
                <div>
                  <div className="text-[10px] font-mono text-zinc-500 tracking-widest uppercase mb-3">▸ WATCH ITEMS — MONITOR THESE NEXT</div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {sitrep.watch_items.map((item, i) => (
                      <WatchCard key={i} item={item} index={i} />
                    ))}
                  </div>
                </div>
              )}

              {/* Contradictions */}
              {report.contradictions?.length > 0 && (
                <div className="rounded border border-red-500/30 bg-red-500/5 p-5">
                  <div className="text-[10px] font-mono text-red-400/70 tracking-widest uppercase mb-3">
                    ⚠ CONTRADICTIONS DETECTED ({report.contradictions.length})
                  </div>
                  <div className="space-y-2">
                    {report.contradictions.map((c, i) => (
                      <div key={i} className="flex items-start gap-3 text-xs font-mono border border-zinc-700 rounded p-3">
                        <div className="flex-1">
                          <span className="text-zinc-400">[{c.event_a.source}]</span>{" "}
                          <span className="text-zinc-200">{c.event_a.type}</span>
                          {" · "}
                          <span className="text-zinc-500">{c.event_a.desc?.slice(0, 80)}</span>
                        </div>
                        <div className="text-red-400 font-bold">vs</div>
                        <div className="flex-1">
                          <span className="text-zinc-400">[{c.event_b.source}]</span>{" "}
                          <span className="text-zinc-200">{c.event_b.type}</span>
                          {" · "}
                          <span className="text-zinc-500">{c.event_b.desc?.slice(0, 80)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Historical pattern + actors/locations row */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="md:col-span-2 rounded border border-zinc-700 bg-zinc-900/60 p-5">
                  <div className="text-[10px] font-mono text-zinc-500 tracking-widest uppercase mb-3">▸ HISTORICAL PARALLEL</div>
                  <p className="text-zinc-300 text-sm mb-3">{sitrep.historical_parallel}</p>
                  {report.historical_patterns?.length > 0 && (
                    <div className="space-y-1">
                      {report.historical_patterns.map((p, i) => (
                        <div key={i} className="text-xs font-mono text-zinc-500 border-l-2 border-zinc-700 pl-3">
                          {p}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="space-y-4">
                  {sitrep.dominant_actors?.length > 0 && (
                    <div className="rounded border border-zinc-700 bg-zinc-900/60 p-4">
                      <div className="text-[10px] font-mono text-zinc-500 tracking-widest uppercase mb-2">ACTORS</div>
                      <div className="flex flex-wrap gap-1">
                        {sitrep.dominant_actors.map((a, i) => (
                          <span key={i} className="text-xs font-mono bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded border border-zinc-700">
                            {a}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {sitrep.key_locations?.length > 0 && (
                    <div className="rounded border border-zinc-700 bg-zinc-900/60 p-4">
                      <div className="text-[10px] font-mono text-zinc-500 tracking-widest uppercase mb-2">LOCATIONS</div>
                      <div className="flex flex-wrap gap-1">
                        {sitrep.key_locations.map((l, i) => (
                          <span key={i} className="text-xs font-mono bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded border border-zinc-700">
                            {l}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Prediction accuracy */}
              {accuracy && (
                <AccuracyBadge stats={accuracy} />
              )}

            </div>
          )}
        </main>
    </div>
  )
}
