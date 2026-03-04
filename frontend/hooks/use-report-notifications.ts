"use client"

import { useCallback, useEffect, useRef } from "react"
import { toast } from "sonner"

export interface ReportGeneratedPayload {
  report_type: string
  document_control: string
  generated_at: string
}

const PROMPT_KEY = "osint_report_notify_prompted"

function toDisplayType(raw: string): string {
  const upper = String(raw || "").toUpperCase().replace(/\s+/g, "-")
  if (upper === "INTSUM") return "INTELLIGENCE SUMMARY"
  if (upper === "SITREP") return "SITUATION REPORT"
  if (upper === "FLASH") return "FLASH REPORT"
  if (upper === "OSINT-BRIEF") return "OSINT BRIEF"
  return upper || "REPORT"
}

export function useReportNotifications(onViewReport: () => void) {
  const hasPromptedRef = useRef(false)

  useEffect(() => {
    try {
      hasPromptedRef.current = localStorage.getItem(PROMPT_KEY) === "1"
    } catch {
      hasPromptedRef.current = false
    }
  }, [])

  const requestPermissionOnce = useCallback(async () => {
    if (typeof window === "undefined" || !("Notification" in window)) return
    if (Notification.permission !== "default") return
    if (hasPromptedRef.current) return
    hasPromptedRef.current = true
    try {
      localStorage.setItem(PROMPT_KEY, "1")
    } catch {
      // ignore
    }
    try {
      await Notification.requestPermission()
    } catch {
      // fallback to in-app toasts
    }
  }, [])

  const notifyReportGenerated = useCallback(
    (payload: ReportGeneratedPayload) => {
      const reportType = toDisplayType(payload.report_type)
      const isFlash = reportType.includes("FLASH")
      const generatedAt = payload.generated_at || new Date().toISOString()
      const title = `${reportType} READY`

      toast(title, {
        description: `${payload.document_control} • ${generatedAt}`,
        duration: isFlash ? Infinity : 9000,
        className: isFlash
          ? "border border-osint-red/70 bg-[#15090c] text-[#ffe8ec] font-mono"
          : "border border-osint-red/30 bg-[#0b0d14] text-[#dbe1ef] font-mono",
        action: {
          label: "VIEW REPORT",
          onClick: onViewReport,
        },
      })

      if (typeof window === "undefined" || !("Notification" in window)) return
      if (Notification.permission !== "granted") return
      try {
        const n = new Notification("OSINT NEXUS // NEW REPORT", {
          body: `${reportType} • ${payload.document_control} • ${generatedAt}`,
          tag: `osint-report-${payload.document_control}`,
          requireInteraction: isFlash,
        })
        n.onclick = () => {
          window.focus()
          onViewReport()
          n.close()
        }
      } catch {
        // no-op
      }
    },
    [onViewReport],
  )

  return {
    requestPermissionOnce,
    notifyReportGenerated,
  }
}
