"use client"

import { useCallback } from "react"

interface ReplayBarProps {
  replayTime: string | null
  bounds: { earliest: string | null; latest: string | null }
  onReplayChange: (iso: string | null) => void
}

export function ReplayBar({ replayTime, bounds, onReplayChange }: ReplayBarProps) {
  const isLive = replayTime === null

  const handleSlider = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    onReplayChange(new Date(Number(e.target.value)).toISOString())
  }, [onReplayChange])

  const earliest = bounds.earliest ? new Date(bounds.earliest).getTime() : Date.now() - 86400000 * 7
  const latest = bounds.latest ? new Date(bounds.latest).getTime() : Date.now()
  const current = replayTime ? new Date(replayTime).getTime() : latest
  const pct = earliest === latest ? 100 : ((current - earliest) / (latest - earliest)) * 100

  const fmt = (iso: string) => new Date(iso).toLocaleString("en-GB", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false
  })

  return (
    <div className="flex items-center gap-3 px-3 py-1.5 border-b border-white/10 bg-[rgba(5,8,14,0.85)] text-[11px] font-mono select-none shrink-0">
      {isLive ? (
        <span className="flex items-center gap-1 px-2 py-0.5 rounded border border-green-500/50 text-green-400 font-bold tracking-widest shrink-0">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          LIVE
        </span>
      ) : (
        <span className="flex items-center gap-1 px-2 py-0.5 rounded border border-red-500/50 text-red-400 font-bold tracking-widest shrink-0">
          ◀ REPLAY
        </span>
      )}

      <div className="flex-1 flex items-center gap-2 min-w-0">
        {bounds.earliest && (
          <span className="text-white/30 shrink-0 hidden sm:block">{fmt(bounds.earliest)}</span>
        )}
        <div className="relative flex-1 h-1 bg-white/10 rounded-full">
          <div className="absolute left-0 top-0 h-1 rounded-full bg-white/30" style={{ width: `${pct}%` }} />
          <input
            type="range"
            min={earliest}
            max={latest}
            step={60000}
            value={current}
            onChange={handleSlider}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          />
        </div>
        <span className="text-white/50 shrink-0 hidden sm:block">NOW</span>
      </div>

      {!isLive && <span className="text-white/70 shrink-0">{fmt(replayTime!)}</span>}

      {!isLive && (
        <button
          onClick={() => onReplayChange(null)}
          className="px-2 py-0.5 rounded border border-green-500/40 text-green-400 hover:bg-green-500/10 transition-colors shrink-0"
        >
          Go Live
        </button>
      )}
    </div>
  )
}
