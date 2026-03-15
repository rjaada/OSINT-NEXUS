"use client"

import { useState } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

interface PressBriefAnalysis {
  speaker: string
  speaker_role: string
  speaker_country: string
  statement_type: string
  date_mentioned: string | null
  headline: string
  key_claims: string[]
  threats_warnings: string[]
  military_signals: string[]
  diplomatic_signals: string[]
  actors_mentioned: string[]
  locations_mentioned: string[]
  intel_value: "HIGH" | "MEDIUM" | "LOW"
  intel_value_reason: string
  deception_indicators: string[]
  observed_facts: string[]
  speculation_flags: string[]
  recommended_follow_up: string[]
}

interface PressBriefResult {
  analysis: PressBriefAnalysis
  text_length: number
  generated_at: string
}

const INTEL_COLOR = {
  HIGH: "text-emerald-400 border-emerald-400/40 bg-emerald-400/10",
  MEDIUM: "text-amber-400 border-amber-400/40 bg-amber-400/10",
  LOW: "text-zinc-400 border-zinc-400/40 bg-zinc-400/10",
}

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono font-bold tracking-widest border ${color}`}>
      {label}
    </span>
  )
}

function Section({ title, icon, items, color = "text-zinc-300" }: {
  title: string
  icon: string
  items: string[]
  color?: string
}) {
  if (!items?.length) return null
  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4">
      <div className="text-[10px] font-mono text-zinc-500 tracking-widest mb-3">{icon} {title}</div>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className={`text-sm font-mono ${color} flex gap-2`}>
            <span className="text-zinc-600 flex-shrink-0">▸</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Tag({ label }: { label: string }) {
  return (
    <span className="inline-block px-2 py-0.5 bg-zinc-800 border border-zinc-700 rounded text-[11px] font-mono text-zinc-300">
      {label}
    </span>
  )
}

export default function PressBriefPage() {
  const [text, setText] = useState("")
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<PressBriefResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function analyze() {
    if (!text.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const resp = await fetch(`${API_BASE}/api/v2/ai/press-brief`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ text }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Unknown error" }))
        throw new Error(err.detail || `HTTP ${resp.status}`)
      }
      const data: PressBriefResult = await resp.json()
      setResult(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Analysis failed")
    } finally {
      setLoading(false)
    }
  }

  const a = result?.analysis

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <TopBar />
      <CommandNav />
      <main className="p-6 max-w-5xl mx-auto">

        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-1">
            <div className="w-1 h-8 bg-violet-400 rounded" />
            <h1 className="text-2xl font-mono font-bold tracking-widest text-zinc-100 uppercase">
              Press Brief Analyzer
            </h1>
            <Pill label="AI-POWERED" color="text-violet-400 border-violet-400/40 bg-violet-400/10" />
          </div>
          <p className="text-zinc-500 text-xs font-mono ml-4">
            Paste any speech, statement, or transcript — extract structured intelligence
          </p>
        </div>

        {/* Input */}
        <div className="mb-4">
          <div className="text-[10px] font-mono text-zinc-500 tracking-widest mb-2">
            📋 PASTE TRANSCRIPT / STATEMENT / SPEECH
          </div>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder="Paste the full text here... press conference, speech, official statement, interview transcript"
            className="w-full h-48 bg-zinc-900 border border-zinc-700 rounded-lg p-4 text-sm font-mono text-zinc-200 placeholder-zinc-600 resize-none focus:outline-none focus:border-violet-500 transition-colors"
          />
          <div className="flex items-center justify-between mt-2">
            <span className="text-[10px] font-mono text-zinc-600">{text.length.toLocaleString()} chars · max 20,000</span>
            <button
              onClick={analyze}
              disabled={loading || !text.trim()}
              className="px-5 py-2 bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white font-mono text-sm font-bold rounded-lg transition-colors flex items-center gap-2"
            >
              {loading ? (
                <>
                  <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ANALYZING...
                </>
              ) : "▶ ANALYZE"}
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 bg-red-950/40 border border-red-800/60 rounded-lg p-4 text-red-400 font-mono text-sm">
            ⚠ {error}
          </div>
        )}

        {/* Results */}
        {a && (
          <div className="space-y-4">

            {/* Top card — headline + speaker */}
            <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-0.5 bg-gradient-to-r from-violet-500 via-violet-400/50 to-transparent" />

              <div className="flex items-start justify-between gap-4 mb-4">
                <div className="flex-1">
                  <div className="text-[10px] font-mono text-zinc-500 tracking-widest mb-1">INTELLIGENCE HEADLINE</div>
                  <h2 className="text-lg font-mono font-bold text-zinc-100 leading-snug">{a.headline}</h2>
                </div>
                <div className="flex-shrink-0">
                  <Pill
                    label={`${a.intel_value} VALUE`}
                    color={INTEL_COLOR[a.intel_value] || INTEL_COLOR.MEDIUM}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                {[
                  { label: "SPEAKER", value: a.speaker },
                  { label: "ROLE", value: a.speaker_role },
                  { label: "COUNTRY", value: a.speaker_country },
                  { label: "TYPE", value: a.statement_type?.replace("_", " ").toUpperCase() },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-zinc-800/60 rounded-lg p-3">
                    <div className="text-[9px] font-mono text-zinc-500 tracking-widest mb-0.5">{label}</div>
                    <div className="text-sm font-mono text-zinc-200 truncate">{value || "—"}</div>
                  </div>
                ))}
              </div>

              <div className="text-[10px] font-mono text-zinc-500">{a.intel_value_reason}</div>
            </div>

            {/* Intel grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Section title="KEY CLAIMS" icon="📌" items={a.key_claims} color="text-zinc-200" />
              <Section title="THREATS & WARNINGS" icon="⚠️" items={a.threats_warnings} color="text-red-300" />
              <Section title="MILITARY SIGNALS" icon="🎯" items={a.military_signals} color="text-amber-300" />
              <Section title="DIPLOMATIC SIGNALS" icon="🤝" items={a.diplomatic_signals} color="text-sky-300" />
              <Section title="OBSERVED FACTS" icon="✅" items={a.observed_facts} color="text-emerald-300" />
              <Section title="SPECULATION FLAGS" icon="❓" items={a.speculation_flags} color="text-orange-300" />
              <Section title="DECEPTION INDICATORS" icon="🔍" items={a.deception_indicators} color="text-red-400" />
              <Section title="RECOMMENDED FOLLOW-UP" icon="🔭" items={a.recommended_follow_up} color="text-violet-300" />
            </div>

            {/* Entities */}
            {(a.actors_mentioned?.length > 0 || a.locations_mentioned?.length > 0) && (
              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4">
                <div className="text-[10px] font-mono text-zinc-500 tracking-widest mb-3">🗂 ENTITIES EXTRACTED</div>
                <div className="space-y-3">
                  {a.actors_mentioned?.length > 0 && (
                    <div>
                      <div className="text-[9px] font-mono text-zinc-600 mb-1.5">ACTORS / ORGANIZATIONS</div>
                      <div className="flex flex-wrap gap-1.5">
                        {a.actors_mentioned.map((actor, i) => <Tag key={i} label={actor} />)}
                      </div>
                    </div>
                  )}
                  {a.locations_mentioned?.length > 0 && (
                    <div>
                      <div className="text-[9px] font-mono text-zinc-600 mb-1.5">LOCATIONS</div>
                      <div className="flex flex-wrap gap-1.5">
                        {a.locations_mentioned.map((loc, i) => <Tag key={i} label={loc} />)}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Footer */}
            <div className="text-[10px] font-mono text-zinc-600 text-right">
              Generated {result?.generated_at?.slice(0, 16).replace("T", " ")} UTC · {result?.text_length?.toLocaleString()} chars analyzed
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
