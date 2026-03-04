import { ClassificationBanner } from "./classification-banner"
import { ReportHeader } from "./report-header"
import { MetadataBar } from "./metadata-bar"
import { ExecutiveSummary } from "./executive-summary"
import { KeyDevelopments } from "./key-developments"
import { ThreatAssessment } from "./threat-assessment"
import { GeographicFocus } from "./geographic-focus"
import { AnalystNotes } from "./analyst-notes"
import { ReportFooter } from "./report-footer"
import { ClassifiedWatermark } from "./classified-watermark"
import type { IntelligenceReportData } from "./types"

export function IntelligenceReport({ data }: { data: IntelligenceReportData }) {
  return (
    <div
      id="intelligence-report"
      className="relative mx-auto w-full max-w-[900px] overflow-hidden bg-paper shadow-[0_0_60px_rgba(0,0,0,0.15)]"
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg width='100' height='100' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E\")",
      }}
    >
      {/* Classified watermark */}
      <ClassifiedWatermark />

      {/* Top banner */}
      <ClassificationBanner />
      <div className="h-[2px] bg-red-official" />

      {/* Header */}
      <ReportHeader data={data} />

      {/* Metadata bar */}
      <MetadataBar data={data} />

      {/* Sections */}
      <div className="mt-6">
        <ExecutiveSummary data={data} />
        <KeyDevelopments data={data} />
        <ThreatAssessment data={data} />
        <GeographicFocus />
        <AnalystNotes data={data} />
      </div>

      {/* Footer */}
      <ReportFooter />
    </div>
  )
}
