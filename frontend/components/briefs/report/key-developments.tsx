import { SectionHeader } from "./section-header"
import type { IntelligenceReportData, ThreatLevel } from "./types"

const priorityColors: Record<ThreatLevel, string> = {
  CRITICAL: "bg-red-critical",
  HIGH: "bg-amber",
  MEDIUM: "bg-yellow-med",
  LOW: "bg-green-low",
}

const priorityTextColors: Record<ThreatLevel, string> = {
  CRITICAL: "text-red-critical",
  HIGH: "text-amber",
  MEDIUM: "text-yellow-med",
  LOW: "text-green-low",
}

export function KeyDevelopments({ data }: { data: IntelligenceReportData }) {
  return (
    <section className="px-8 py-4">
      <SectionHeader number={2} title="KEY DEVELOPMENTS" />
      <div className="space-y-3 pl-5">
        {data.keyDevelopments.map((dev, i) => (
          <div key={i} className="flex items-start gap-3">
            <div className="flex flex-shrink-0 items-center gap-2 pt-0.5">
              <span className={`inline-block h-2.5 w-2.5 rounded-full ${priorityColors[dev.priority]}`} />
              <span className={`font-mono text-[10px] font-bold ${priorityTextColors[dev.priority]}`}>
                {dev.priority}
              </span>
            </div>
            <div className="flex-1">
              <p className="font-mono text-xs leading-relaxed text-ink/85">
                <span className="font-bold text-ink">{i + 1}.</span> {dev.text}
              </p>
              <div className="mt-1 flex gap-1.5">
                {dev.sources.map((src) => (
                  <span
                    key={src}
                    className="bg-ink/[0.07] px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wider text-ink/60"
                  >
                    [{src}]
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
