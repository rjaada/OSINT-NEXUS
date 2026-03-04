export function ReportFooter() {
  return (
    <footer className="mt-6">
      {/* Document control block + QR placeholder */}
      <div className="mx-8 mb-4 flex items-end justify-between">
        {/* Control block - bottom left */}
        <div className="border border-ink/20 bg-ink/[0.02] px-4 py-3">
          <p className="font-mono text-[9px] leading-relaxed tracking-wide text-ink/60">
            PREPARED BY: OSINT NEXUS AI ANALYST
          </p>
          <p className="font-mono text-[9px] leading-relaxed tracking-wide text-ink/60">
            REVIEWED BY: PENDING HUMAN REVIEW
          </p>
          <p className="font-mono text-[9px] leading-relaxed tracking-wide text-ink/60">
            DISSEMINATION: AUTHORIZED RECIPIENTS ONLY
          </p>
        </div>

        {/* QR Code placeholder - bottom right */}
        <div className="flex flex-col items-center">
          <div className="flex h-16 w-16 items-center justify-center border-2 border-ink/30 bg-ink/[0.03]">
            <svg className="h-10 w-10 text-ink/20" viewBox="0 0 24 24" fill="currentColor">
              <rect x="2" y="2" width="8" height="8" rx="1" />
              <rect x="14" y="2" width="8" height="8" rx="1" />
              <rect x="2" y="14" width="8" height="8" rx="1" />
              <rect x="15" y="15" width="2" height="2" />
              <rect x="19" y="15" width="2" height="2" />
              <rect x="15" y="19" width="2" height="2" />
              <rect x="19" y="19" width="2" height="2" />
              <rect x="17" y="17" width="2" height="2" />
            </svg>
          </div>
          <p className="mt-1 font-mono text-[7px] tracking-wider text-ink/40">
            SCAN FOR LIVE SOURCE DATA
          </p>
        </div>
      </div>

      {/* Footer bar */}
      <div className="mx-8 flex items-center justify-between border-t border-ink/15 py-3">
        <span className="font-mono text-[9px] tracking-wide text-ink/40">
          {"OSINT NEXUS // AI-GENERATED INTELLIGENCE BRIEF"}
        </span>
        <span className="font-mono text-[9px] font-semibold tracking-wide text-ink/50">
          PAGE 1 OF 1
        </span>
        <span className="font-mono text-[9px] tracking-wide text-ink/40">
          NOT FOR OPERATIONAL USE WITHOUT HUMAN REVIEW
        </span>
      </div>

      {/* Bottom classification banner */}
      <div className="w-full bg-banner-bg py-2">
        <p className="text-center font-mono text-sm font-bold tracking-[0.2em] text-banner-text">
          {"//UNCLASSIFIED//FOR OFFICIAL USE ONLY//"}
        </p>
      </div>
    </footer>
  )
}
