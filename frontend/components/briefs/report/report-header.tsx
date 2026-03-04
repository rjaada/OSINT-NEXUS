import { Shield } from "lucide-react"
import type { IntelligenceReportData } from "./types"

export function ReportHeader({ data }: { data: IntelligenceReportData }) {
  return (
    <div className="flex items-start justify-between px-8 py-6">
      {/* Left: Logo */}
      <div className="flex items-center gap-3">
        <Shield className="h-12 w-12 text-red-official" strokeWidth={1.5} />
        <span className="font-[var(--font-stencil)] text-2xl tracking-wider text-ink">
          OSINT NEXUS
        </span>
      </div>

      {/* Right: Report metadata */}
      <div className="text-right">
        <h1 className="font-[var(--font-stencil)] text-2xl font-bold text-red-official">{data.title}</h1>
        <p className="mt-1 font-mono text-xs tracking-wide text-ink/70">
          {data.docId}
        </p>
        <p className="mt-0.5 font-mono text-xs font-semibold tracking-wide text-ink">
          {`CLASSIFICATION: ${data.classification}`}
        </p>
        <p className="mt-0.5 font-mono text-xs tracking-wide text-ink/70">
          {`DISTRIBUTION: ${data.distribution}`}
        </p>
      </div>
    </div>
  )
}
