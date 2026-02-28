"use client"

import { useEffect, useState } from "react"
import { Shield, Radio, Lock } from "lucide-react"

export function TopBar({ headlines }: { headlines?: string[] }) {
  const [utcTime, setUtcTime] = useState("")

  useEffect(() => {
    const update = () => {
      const now = new Date()
      setUtcTime(now.toISOString().replace("T", " ").slice(0, 19) + " UTC")
    }
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [])

  const tickerItems = headlines && headlines.length > 0
    ? headlines
    : [
        "IDF confirms strikes on Hezbollah positions in southern Lebanon",
        "CENTCOM: US forces intercept Houthi anti-ship missile over Red Sea",
        "Iran state TV: IRGC naval exercise underway in Strait of Hormuz",
        "US deploys additional carrier strike group to Eastern Mediterranean",
        "Israeli PM: Operation ongoing until all hostages returned",
      ]

  const tickerText = tickerItems.join("   ·   ")

  return (
    <header className="flex flex-col glass-panel border-b border-[rgba(255,255,255,0.06)]">
      {/* Main bar */}
      <div className="flex items-center justify-between px-4 py-2">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-osint-red" />
            <span className="text-sm font-bold tracking-[0.2em] text-[#e0e0e8]">
              OSINT NEXUS
            </span>
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-osint-red opacity-75 animate-blink" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-osint-red" />
            </span>
          </div>

          <div className="hidden sm:flex items-center gap-4 ml-6">
            <div className="flex items-center gap-1.5 text-[10px] text-osint-green uppercase tracking-widest">
              <Lock className="h-3 w-3" />
              <span>Secure</span>
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-osint-blue uppercase tracking-widest">
              <Radio className="h-3 w-3" />
              <span>Signal Locked</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden md:flex items-center gap-2 text-[10px] text-muted-foreground uppercase tracking-wider">
            <span className="h-1.5 w-1.5 rounded-full bg-osint-green" />
            <span>SYS NOMINAL</span>
          </div>
          <time className="text-xs text-osint-amber font-mono tabular-nums tracking-wider">
            {utcTime}
          </time>
        </div>
      </div>

      {/* Breaking news ticker */}
      <div className="flex items-center bg-osint-red/10 border-t border-osint-red/20 overflow-hidden h-6">
        <div className="shrink-0 bg-osint-red px-2 h-full flex items-center">
          <span className="text-[9px] font-bold tracking-[0.15em] text-white whitespace-nowrap">
            ● BREAKING
          </span>
        </div>
        <div className="flex-1 overflow-hidden relative">
          <div
            className="flex whitespace-nowrap text-[10px] text-[#c0c0d0] tracking-wide"
            style={{
              animation: "ticker 60s linear infinite",
              willChange: "transform",
            }}
          >
            <span className="px-8">{tickerText}</span>
            <span className="px-8" aria-hidden>{tickerText}</span>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes ticker {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
    </header>
  )
}
