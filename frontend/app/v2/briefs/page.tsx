"use client"

import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { CommandNav } from "@/components/dashboard/command-nav"
import { TopBar } from "@/components/dashboard/top-bar"
import { CinematicSequence } from "@/components/briefs/cinematic/cinematic-sequence"
import type {
  DevelopmentItem,
  IntelligenceReportData,
  ThreatData,
  ThreatLevel,
  ReportType,
} from "@/components/briefs/report/types"
import { readCookie } from "@/lib/security"
import { useReportNotifications } from "@/hooks/use-report-notifications"

type Role = "viewer" | "analyst" | "admin"

interface OpsBriefResponse {
  mode?: string
  document_control?: string
  report?: {
    title?: string
    summary?: string
    paragraphs?: string[]
    priority_actions?: string[]
    risk_level?: string
  }
  verify?: Array<{
    source?: string
    result?: {
      classification?: string
      confidence_0_to_100?: number
    }
  }>
  generated_at?: string
}

interface EventItem {
  source?: string
}

interface AlertItem {
  type?: string
  confidence_score?: number
}

const CACHE_KEY = "osint_v2_brief_cache"
const API_BASE = "http://localhost:8000"

function isoToUtcText(input: string): string {
  const parsed = new Date(input)
  if (Number.isNaN(parsed.getTime())) return "N/A UTC"
  const y = parsed.getUTCFullYear()
  const m = String(parsed.getUTCMonth() + 1).padStart(2, "0")
  const d = String(parsed.getUTCDate()).padStart(2, "0")
  const hh = String(parsed.getUTCHours()).padStart(2, "0")
  const mm = String(parsed.getUTCMinutes()).padStart(2, "0")
  return `${y}-${m}-${d} ${hh}:${mm} UTC`
}

function toThreatLevel(value: string | undefined): ThreatLevel {
  const raw = String(value || "").trim().toUpperCase()
  if (raw === "LOW" || raw === "MEDIUM" || raw === "HIGH" || raw === "CRITICAL") return raw
  return "MEDIUM"
}

function threatScoreFromLevel(level: ThreatLevel): number {
  if (level === "LOW") return 28
  if (level === "MEDIUM") return 52
  if (level === "HIGH") return 76
  return 92
}

function deriveThreatFromAlerts(alerts: AlertItem[]): ThreatData {
  if (!alerts.length) return { level: "MEDIUM", score: 52 }
  const top = alerts.slice(0, 20)
  let score = 35
  for (const alert of top) {
    const kind = String(alert.type || "").toUpperCase()
    const confidence = Number(alert.confidence_score || 0)
    if (kind === "CRITICAL") score = Math.max(score, 78)
    if (kind === "STRIKE") score = Math.max(score, 70)
    if (kind === "CLASH") score = Math.max(score, 60)
    score = Math.max(score, Math.min(95, Math.round(confidence)))
  }
  const level: ThreatLevel = score >= 85 ? "CRITICAL" : score >= 70 ? "HIGH" : score >= 45 ? "MEDIUM" : "LOW"
  return { level, score }
}

function buildDevelopments(ops: OpsBriefResponse, sourceSet: Set<string>): DevelopmentItem[] {
  const fromActions = Array.isArray(ops.report?.priority_actions) ? ops.report?.priority_actions || [] : []
  const fromVerify = Array.isArray(ops.verify) ? ops.verify : []
  const items: DevelopmentItem[] = []

  for (const action of fromActions.slice(0, 4)) {
    items.push({
      priority: toThreatLevel(ops.report?.risk_level),
      text: String(action),
      sources: [...sourceSet].slice(0, 3),
    })
  }

  for (const v of fromVerify.slice(0, 3)) {
    const classification = String(v.result?.classification || "uncertain").toLowerCase()
    const confidence = Number(v.result?.confidence_0_to_100 || 0)
    let priority: ThreatLevel = "MEDIUM"
    if (classification === "credible" && confidence >= 75) priority = "HIGH"
    if (classification === "unlikely") priority = "LOW"
    items.push({
      priority,
      text: `Verification from ${String(v.source || "unknown source")}: ${classification.toUpperCase()} (${confidence}%)`,
      sources: [String(v.source || "OSINT")],
    })
  }

  if (!items.length) {
    items.push({
      priority: "MEDIUM",
      text: "No priority action output from AI analyst. Continue source monitoring and corroboration.",
      sources: [...sourceSet].slice(0, 2),
    })
  }
  return items.slice(0, 5)
}

function defaultBriefData(): IntelligenceReportData {
  return {
    reportType: "INTSUM",
    title: "INTELLIGENCE SUMMARY",
    docId: "OSINT-NEXUS-INTSUM-DRAFT",
    classification: "UNCLASSIFIED // FOUO",
    distribution: "LIMITED",
    metadata: {
      generatedAt: "N/A UTC",
      analyst: "AI-NEXUS-01",
      sourcesActive: 0,
      confidence: "MEDIUM",
      reportId: "DRAFT",
    },
    executiveSummary: ["No report generated yet."],
    keyDevelopments: [
      {
        priority: "MEDIUM",
        text: "Awaiting backend report generation.",
        sources: ["OSINT"],
      },
    ],
    threat: { level: "MEDIUM", score: 52 },
    analystNotes: ["AI analyst output unavailable. Retry generation or inspect source feeds directly."],
  }
}

export default function V2BriefsPage() {
  const router = useRouter()
  const [role, setRole] = useState<Role>("viewer")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [offlineFallback, setOfflineFallback] = useState(false)
  const [briefData, setBriefData] = useState<IntelligenceReportData>(defaultBriefData())

  const allowed = role === "analyst" || role === "admin"
  const { requestPermissionOnce, notifyReportGenerated } = useReportNotifications(() => {
    router.push("/v2/briefs")
  })

  useEffect(() => {
    const raw = readCookie("osint_role").toLowerCase()
    if (raw === "analyst" || raw === "admin" || raw === "viewer") setRole(raw)
  }, [])

  useEffect(() => {
    if (!allowed) {
      setLoading(false)
      return
    }

    let isMounted = true
    const load = async () => {
      setLoading(true)
      setError("")
      setOfflineFallback(false)
      try {
        const [opsRes, eventsRes, alertsRes] = await Promise.all([
          fetch(`${API_BASE}/api/v2/ai/ops-brief`, {
            method: "POST",
            credentials: "include",
            cache: "no-store",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: "INTSUM", limit: 20 }),
          }),
          fetch(`${API_BASE}/api/v2/events?limit=200`, { credentials: "include", cache: "no-store" }),
          fetch(`${API_BASE}/api/v2/alerts?limit=80`, { credentials: "include", cache: "no-store" }),
        ])

        if (!opsRes.ok) throw new Error("AI analyst offline")
        const ops = (await opsRes.json()) as OpsBriefResponse
        const events = eventsRes.ok ? ((await eventsRes.json()) as EventItem[]) : []
        const alerts = alertsRes.ok ? ((await alertsRes.json()) as AlertItem[]) : []

        const sourceSet = new Set(
          (Array.isArray(events) ? events : [])
            .map((e) => String(e.source || "").trim())
            .filter((x) => x.length > 0),
        )
        const risk = toThreatLevel(ops.report?.risk_level)
        const derivedThreat = deriveThreatFromAlerts(Array.isArray(alerts) ? alerts : [])
        const threat: ThreatData = ops.report?.risk_level
          ? { level: risk, score: threatScoreFromLevel(risk) }
          : derivedThreat

        const generatedAtIso = String(ops.generated_at || new Date().toISOString())
        const modeRaw = String(ops.mode || "INTSUM").toUpperCase()
        const reportType: ReportType = modeRaw === "SITREP"
          ? "SITREP"
          : modeRaw === "FLASH"
          ? "FLASH"
          : modeRaw === "OSINT BRIEF" || modeRaw === "OSINT-BRIEF"
          ? "OSINT-BRIEF"
          : "INTSUM"
        const reportId = generatedAtIso.replace(/[-:TZ.]/g, "").slice(0, 12) || "INTSUM"
        const confidenceFromVerify = Math.round(
          ((ops.verify || [])
            .map((v) => Number(v.result?.confidence_0_to_100 || 0))
            .filter((n) => Number.isFinite(n))
            .reduce((a, b) => a + b, 0) / Math.max(1, (ops.verify || []).length)) || 0,
        )
        const confidence: "LOW" | "MEDIUM" | "HIGH" =
          confidenceFromVerify >= 78 ? "HIGH" : confidenceFromVerify >= 55 ? "MEDIUM" : "LOW"
        const summary = String(ops.report?.summary || "").trim()
        const paragraphs = Array.isArray(ops.report?.paragraphs)
          ? ops.report?.paragraphs.filter((x) => String(x).trim().length > 0).map((x) => String(x))
          : []
        const executiveSummary =
          paragraphs.length > 0 ? paragraphs.slice(0, 3) : summary ? [summary] : ["No summary returned from AI analyst."]

        const nextData: IntelligenceReportData = {
          reportType,
          title: String(ops.report?.title || "INTELLIGENCE SUMMARY").toUpperCase(),
          docId: String(ops.document_control || `OSINT-NEXUS-${generatedAtIso.slice(0, 10).replace(/-/g, "")}-${reportId}-${reportType}`),
          classification: "UNCLASSIFIED // FOUO",
          distribution: "LIMITED",
          metadata: {
            generatedAt: isoToUtcText(generatedAtIso),
            analyst: "AI-NEXUS-01",
            sourcesActive: sourceSet.size,
            confidence,
            reportId,
          },
          executiveSummary,
          keyDevelopments: buildDevelopments(ops, sourceSet),
          threat,
          analystNotes: [
            summary || "No one-line AI summary returned.",
            ...(paragraphs.length > 0 ? [paragraphs[0]] : []),
          ],
        }

        if (!isMounted) return
        setBriefData(nextData)
        localStorage.setItem(CACHE_KEY, JSON.stringify(nextData))
      } catch (err) {
        const fallbackRaw = localStorage.getItem(CACHE_KEY)
        if (fallbackRaw) {
          try {
            const fallback = JSON.parse(fallbackRaw) as IntelligenceReportData
            if (isMounted) {
              setBriefData(fallback)
              setOfflineFallback(true)
              setError(err instanceof Error ? err.message : "AI analyst offline")
            }
            return
          } catch {
            // continue to hard error state
          }
        }
        if (isMounted) {
          setError(err instanceof Error ? err.message : "AI analyst offline")
        }
      } finally {
        if (isMounted) setLoading(false)
      }
    }

    void load()
    return () => {
      isMounted = false
    }
  }, [allowed])

  useEffect(() => {
    if (!allowed) return
    void requestPermissionOnce()
  }, [allowed, requestPermissionOnce])

  useEffect(() => {
    if (!allowed) return
    let ws: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | null = null
    const connect = () => {
      try {
        const wsUrl = (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000") + "/ws/live/v2"
        ws = new WebSocket(wsUrl)
        ws.onmessage = (evt) => {
          try {
            const payload = JSON.parse(evt.data)
            if (payload?.type !== "report_generated") return
            const data = payload?.data || {}
            notifyReportGenerated({
              report_type: String(data.report_type || "INTSUM"),
              document_control: String(data.document_control || "OSINT-NEXUS-UNKNOWN"),
              generated_at: String(data.generated_at || new Date().toISOString()),
            })
          } catch {
            // ignore malformed payloads
          }
        }
        ws.onclose = () => {
          retry = setTimeout(connect, 3500)
        }
        ws.onerror = () => ws?.close()
      } catch {
        retry = setTimeout(connect, 3500)
      }
    }
    connect()
    return () => {
      if (retry) clearTimeout(retry)
      ws?.close()
    }
  }, [allowed, notifyReportGenerated])

  const deniedView = useMemo(
    () => (
      <main className="px-4 py-6 md:px-6">
        <div className="mx-auto max-w-4xl rounded-lg border border-osint-red/40 bg-osint-red/10 p-4 text-sm text-osint-red">
          Analyst or Admin role required for intelligence briefs.
        </div>
      </main>
    ),
    [],
  )

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar />
      <CommandNav />
      {allowed ? (
        <CinematicSequence data={briefData} loading={loading} error={error} offlineFallback={offlineFallback} />
      ) : (
        deniedView
      )}
    </div>
  )
}
