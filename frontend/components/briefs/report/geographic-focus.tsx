import { SectionHeader } from "./section-header"

interface LocationEntry {
  name: string
  mgrs: string
  status: string
}

const locations: LocationEntry[] = [
  { name: "ALPHA SECTOR - EASTERN MEDITERRANEAN", mgrs: "36SYC 4520 3870", status: "ACTIVE MONITORING" },
  { name: "BRAVO SECTOR - PERSIAN GULF CORRIDOR", mgrs: "39RYH 7840 2150", status: "ELEVATED WATCH" },
  { name: "CHARLIE SECTOR - STRAIT OF HORMUZ", mgrs: "40RCN 3210 6480", status: "CRITICAL INTEREST" },
  { name: "DELTA SECTOR - RED SEA APPROACH", mgrs: "37PFT 5670 9230", status: "ACTIVE MONITORING" },
]

export function GeographicFocus() {
  return (
    <section className="px-8 py-4">
      <SectionHeader number={4} title="GEOGRAPHIC FOCUS" />
      <div className="pl-5">
        <div className="border-2 border-ink/20 bg-ink/[0.02]">
          {/* AOI Header */}
          <div className="border-b border-ink/15 bg-ink/[0.05] px-5 py-2.5">
            <span className="font-mono text-xs font-bold tracking-wider text-red-official">
              AREA OF INTEREST: MIDDLE EAST THEATER
            </span>
          </div>

          {/* Location grid */}
          <div className="divide-y divide-ink/10">
            {locations.map((loc, i) => (
              <div key={i} className="flex items-center gap-4 px-5 py-2.5">
                <span className="w-2 h-2 bg-red-official/80 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-[11px] font-semibold tracking-wide text-ink">
                    {loc.name}
                  </p>
                  <p className="font-mono text-[10px] text-ink/50">
                    MGRS: {loc.mgrs}
                  </p>
                </div>
                <span className="font-mono text-[9px] font-bold tracking-wider text-ink/60 flex-shrink-0 bg-ink/[0.05] px-2 py-1">
                  {loc.status}
                </span>
              </div>
            ))}
          </div>

          <div className="border-t border-ink/15 px-5 py-3">
            <p className="font-mono text-[10px] tracking-wide text-ink/55">
              Theater focus is derived from live event density and corroborated-source clustering.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
