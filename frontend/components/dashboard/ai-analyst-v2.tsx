"use client"

import { useEffect, useState, useRef } from "react"
import { Bot, RefreshCw, ChevronDown, ChevronUp, AlertTriangle } from "lucide-react"

interface AnalystReport {
  summary: string
  threat_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | "UNKNOWN" | string
  key_developments: string[]
  insufficient_evidence?: boolean
  generated_at: string
}

const THREAT_COLORS: Record<"LOW" | "MEDIUM" | "HIGH" | "CRITICAL", { text: string; bg: string; border: string }> = {
  LOW: { text: "#00ff88", bg: "#00ff8820", border: "#00ff8840" },
  MEDIUM: { text: "#ffa630", bg: "#ffa63020", border: "#ffa63040" },
  HIGH: { text: "#ff1a3c", bg: "#ff1a3c20", border: "#ff1a3c40" },
  CRITICAL: { text: "#b24bff", bg: "#b24bff20", border: "#b24bff40" },
}

const REFRESH_INTERVAL_MS = 5 * 60 * 1000

type ThreatLevel = keyof typeof THREAT_COLORS

function normalizeThreatLevel(level?: string): ThreatLevel {
  if (level === "LOW" || level === "MEDIUM" || level === "HIGH" || level === "CRITICAL") return level
  return "MEDIUM"
}

function timeAgo(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

export function AiAnalyst() {
  const [report, setReport] = useState<AnalystReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(true)
  const [hasKey, setHasKey] = useState(false)
  const [agoText, setAgoText] = useState("")
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchReport = async (force = false) => {
    setLoading(true)
    try {
      const res = await fetch(`http://localhost:8000/api/v2/ai/report${force ? "?force=true" : ""}`, { cache: "no-store" })
      if (res.ok) {
        const data = await res.json()
        setReport(data)
        setHasKey(true)
      }
    } catch (_) {
      // offline
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchReport()
    if (intervalRef.current) clearInterval(intervalRef.current)
    intervalRef.current = setInterval(fetchReport, REFRESH_INTERVAL_MS)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  useEffect(() => {
    const updateAgo = () => {
      if (report?.generated_at) setAgoText(timeAgo(report.generated_at))
    }
    updateAgo()
    const i = setInterval(updateAgo, 15000)
    return () => clearInterval(i)
  }, [report?.generated_at])

  const level = normalizeThreatLevel(report?.threat_level)
  const colors = THREAT_COLORS[level]
  const isCritical = level === "CRITICAL"
  const isHigh = level === "HIGH"

  return (
    <div
      className={`rounded-xl overflow-hidden transition-all ${isCritical ? "animate-pulse-border" : ""}`}
      style={{
        background: isCritical ? "rgba(178,75,255,0.05)" : "rgba(7,8,14,0.9)",
        border: `1px solid ${isCritical ? "rgba(178,75,255,0.4)" : isHigh ? "rgba(255,26,60,0.2)" : "rgba(255,255,255,0.07)"}`,
        boxShadow: isCritical ? "0 0 20px rgba(178,75,255,0.15)" : "none",
      }}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => e.key === "Enter" && setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-white/[0.02] transition-colors cursor-pointer select-none"
      >
        <Bot className="h-4 w-4 text-osint-purple shrink-0" />
        <span className="text-[10px] font-bold tracking-[0.2em] text-[#e0e0e8] uppercase flex-1 text-left">AI Crisis Analyst</span>
        {!hasKey && <span title="AI backend key missing"><AlertTriangle className="h-3 w-3 text-osint-amber" /></span>}
        <span className={`text-[8px] font-bold tracking-widest px-2 py-0.5 rounded ${isCritical ? "animate-blink" : ""}`} style={{ background: colors.bg, border: `1px solid ${colors.border}`, color: colors.text }}>
          {report?.threat_level ?? "—"}
        </span>
        <button onClick={(e) => { e.stopPropagation(); fetchReport(true) }} className={`ml-1 text-muted-foreground hover:text-white transition-all ${loading ? "animate-spin" : ""}`}>
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
        {expanded ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
      </div>

      {expanded && report && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/[0.05]">
          {report.insufficient_evidence ? (
            <div className="mt-3 rounded border border-osint-amber/40 bg-osint-amber/10 p-2 text-[10px] text-osint-amber">
              Evidence quality is limited. Treat this as model inference, not confirmed fact.
            </div>
          ) : null}

          <p className={`text-[11px] leading-relaxed pt-2 ${isCritical ? "text-[#d0b0f0]" : "text-[#a0a0c0]"}`}>
            {loading ? "Generating intelligence summary..." : report.summary}
          </p>

          {report.key_developments.length > 0 && (
            <div className="space-y-1.5">
              <span className="text-[8px] uppercase tracking-[0.2em] text-muted-foreground">Key Developments</span>
              {report.key_developments.map((dev, i) => (
                <div key={i} className="flex gap-2 items-start">
                  <span className="text-[9px] shrink-0 mt-0.5" style={{ color: colors.text }}>▸</span>
                  <span className="text-[10px] text-[#909090] leading-relaxed">{dev}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between text-[8px] text-muted-foreground pt-1">
            <span>{hasKey ? `Updated ${agoText} · Refreshes every ${REFRESH_INTERVAL_MS / 60000}m` : "Analyst unavailable"}</span>
            {level === "CRITICAL" ? <span className="text-[8px] text-osint-purple font-bold tracking-wider animate-blink">ESCALATED</span> : null}
          </div>
        </div>
      )}

      <style>{`
        @keyframes pulse-border {
          0%, 100% { box-shadow: 0 0 8px rgba(178,75,255,0.15); }
          50% { box-shadow: 0 0 24px rgba(178,75,255,0.35); }
        }
        .animate-pulse-border { animation: pulse-border 2s ease-in-out infinite; }
      `}</style>
    </div>
  )
}
