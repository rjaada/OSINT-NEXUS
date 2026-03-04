import type { IntelligenceReportData } from "@/components/briefs/report/types"

function asFilenameUtc(now: Date): string {
  const y = now.getUTCFullYear()
  const m = String(now.getUTCMonth() + 1).padStart(2, "0")
  const d = String(now.getUTCDate()).padStart(2, "0")
  const hh = String(now.getUTCHours()).padStart(2, "0")
  const mm = String(now.getUTCMinutes()).padStart(2, "0")
  return `${y}-${m}-${d}-${hh}${mm}`
}

export function buildReportPdfFileName(data: IntelligenceReportData): string {
  const stamp = asFilenameUtc(new Date())
  return `OSINT-NEXUS-${stamp}-${data.reportType}.pdf`
}
