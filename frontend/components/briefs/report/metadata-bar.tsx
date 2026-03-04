import type { IntelligenceReportData } from "./types"

export function MetadataBar({ data }: { data: IntelligenceReportData }) {
  const items = [
    { label: "GENERATED", value: data.metadata.generatedAt },
    { label: "ANALYST", value: data.metadata.analyst },
    { label: "SOURCES", value: `${data.metadata.sourcesActive} ACTIVE` },
    { label: "CONFIDENCE", value: data.metadata.confidence },
    { label: "REPORT", value: data.metadata.reportId },
  ]

  return (
    <div className="mx-6 flex flex-wrap items-center justify-between gap-y-1 bg-metadata-bg px-5 py-2.5">
      {items.map((item, i) => (
        <span key={i} className="font-mono text-[11px] tracking-wide text-metadata-text">
          <span className="text-metadata-text/60">{item.label}:</span>{" "}
          <span className="font-semibold text-metadata-text">{item.value}</span>
        </span>
      ))}
    </div>
  )
}
