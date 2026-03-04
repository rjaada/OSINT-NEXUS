import { SectionHeader } from "./section-header"
import type { IntelligenceReportData } from "./types"

export function ThreatAssessment({ data }: { data: IntelligenceReportData }) {
  const markerPosition = Math.min(100, Math.max(0, data.threat.score))

  return (
    <section className="px-8 py-4">
      <SectionHeader number={3} title="THREAT ASSESSMENT" />
      <div className="pl-5">
        <div className="border border-ink/10 bg-ink/[0.02] p-5">
          {/* Labels */}
          <div className="mb-2 flex items-center justify-between">
            <span className="font-mono text-[10px] font-bold tracking-wider text-green-low">
              MINIMAL
            </span>
            <span className="font-mono text-[10px] font-bold tracking-wider text-red-critical">
              CRITICAL
            </span>
          </div>

          {/* Threat bar */}
          <div className="relative">
            <div
              className="h-5 w-full"
              style={{
                background:
                  "linear-gradient(to right, #2d7a2d 0%, #6aab2d 20%, #c9a800 40%, #e85d00 60%, #cc0000 80%, #8b0000 100%)",
              }}
            />
            {/* Marker */}
            <div
              className="absolute top-0 flex h-full flex-col items-center"
              style={{ left: `${markerPosition}%`, transform: "translateX(-50%)" }}
            >
              <div className="h-5 w-0.5 bg-ink" />
            </div>
            <div
              className="absolute flex flex-col items-center"
              style={{
                left: `${markerPosition}%`,
                transform: "translateX(-50%)",
                top: "calc(100% + 2px)",
              }}
            >
              <div className="h-0 w-0 border-x-[5px] border-b-0 border-t-[6px] border-x-transparent border-t-ink" />
              <span className="mt-0.5 font-mono text-[10px] font-bold tracking-wider text-ink">
                {data.threat.level}
              </span>
            </div>
          </div>

          {/* Scale labels */}
          <div className="mt-6 flex justify-between">
            {["MINIMAL", "LOW", "GUARDED", "ELEVATED", "HIGH", "CRITICAL"].map(
              (label) => (
                <span
                  key={label}
                  className={`font-mono text-[8px] tracking-wider ${
                    label === data.threat.level ? "font-bold text-ink" : "text-ink/40"
                  }`}
                >
                  {label}
                </span>
              )
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
