import { SectionHeader } from "./section-header"
import type { IntelligenceReportData } from "./types"

export function ExecutiveSummary({ data }: { data: IntelligenceReportData }) {
  return (
    <section className="px-8 py-4">
      <SectionHeader number={1} title="EXECUTIVE SUMMARY" />
      <div className="pl-5 font-serif text-sm leading-relaxed text-ink/90">
        {data.executiveSummary.map((paragraph, idx) => (
          <p key={`${idx}-${paragraph.slice(0, 24)}`} className={idx > 0 ? "mt-3" : ""}>
            {paragraph}
          </p>
        ))}
      </div>
    </section>
  )
}
