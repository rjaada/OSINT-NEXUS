"use client"

import Link from "next/link"
import { useEffect, useMemo, useRef, useState } from "react"
import { Shield, Radio, Lock, Search, X } from "lucide-react"

type SearchItem = {
  id: string
  label: string
  hint?: string
  section: "Navigation" | "Intel Events" | "Tracked Assets"
  href?: string
}

const INACTIVITY_LIMIT_MS = 15 * 60 * 1000
const WARNING_WINDOW_MS = 3 * 60 * 1000

function dtg(now: Date) {
  const day = String(now.getUTCDate()).padStart(2, "0")
  const hh = String(now.getUTCHours()).padStart(2, "0")
  const mm = String(now.getUTCMinutes()).padStart(2, "0")
  const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
  return `${day}${hh}${mm}Z${months[now.getUTCMonth()]}${now.getUTCFullYear()}`
}

function fmtTime(now: Date, timeZone?: string) {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone,
  }).format(now)
}

function formatCountdown(ms: number) {
  const totalSec = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
}

export function TopBar({ headlines }: { headlines?: string[] }) {
  const [utcTime, setUtcTime] = useState("")
  const [localTime, setLocalTime] = useState("")
  const [theaterTime, setTheaterTime] = useState("")
  const [dtgText, setDtgText] = useState("")
  const [commandOpen, setCommandOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [eventItems, setEventItems] = useState<SearchItem[]>([])
  const [assetItems, setAssetItems] = useState<SearchItem[]>([
    { id: "asset-1", label: "UAV-7792", hint: "aircraft 35.45N 36.83E", section: "Tracked Assets" },
    { id: "asset-2", label: "CVN-78", hint: "vessel 33.93N 35.36E", section: "Tracked Assets" },
    { id: "asset-3", label: "DDG-112", hint: "vessel 34.06N 35.36E", section: "Tracked Assets" },
  ])
  const [warnActive, setWarnActive] = useState(false)
  const [countdownText, setCountdownText] = useState("03:00")
  const [terminalLocked, setTerminalLocked] = useState(false)
  const lastActivityRef = useRef<number>(Date.now())
  const searchInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const update = () => {
      const now = new Date()
      setUtcTime(now.toISOString().replace("T", " ").slice(0, 19) + " UTC")
      setLocalTime(fmtTime(now))
      setTheaterTime(fmtTime(now, "Asia/Jerusalem"))
      setDtgText(dtg(now))
    }
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const NAV_ITEMS: SearchItem[] = [
      { id: "nav-ops", label: "Operations", hint: "Live map and intel feed", section: "Navigation", href: "/operations" },
      { id: "nav-alerts", label: "Alerts", hint: "Confidence and ETA board", section: "Navigation", href: "/alerts" },
      { id: "nav-sources", label: "Sources", hint: "Reliability and source health", section: "Navigation", href: "/sources" },
      { id: "nav-v2-ops", label: "V2 Operations", hint: "Phase-2 operations", section: "Navigation", href: "/v2/operations" },
      { id: "nav-v2-alerts", label: "V2 Alerts", hint: "Phase-2 alert board", section: "Navigation", href: "/v2/alerts" },
      { id: "nav-v2-sources", label: "V2 Sources", hint: "Phase-2 sources", section: "Navigation", href: "/v2/sources" },
      { id: "nav-v2-health", label: "V2 Health", hint: "System reliability", section: "Navigation", href: "/v2/health" },
    ]

    const load = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/v2/events?limit=18", { cache: "no-store" })
        if (!res.ok) return
        const data = await res.json()
        const parsed: SearchItem[] = (data || []).map((evt: { id: string; desc?: string; source?: string; timestamp?: string }, idx: number) => ({
          id: evt.id || `evt-${idx}`,
          label: (evt.desc || "intel event").replace(/^\[.+?\]\s*/, "").slice(0, 72),
          hint: `${evt.source || "Source"} • ${evt.timestamp || "live"}`,
          section: "Intel Events",
        }))
        setEventItems(parsed)
      } catch (_) {
        // Keep static fallback
      }
    }

    try {
      const ac = localStorage.getItem("osint_asset_cache")
      if (ac) {
        const cached = JSON.parse(ac)
        if (Array.isArray(cached) && cached.length > 0) {
          setAssetItems(cached.slice(0, 8))
        }
      }
    } catch (_) {
      // Ignore cache parse errors
    }

    void load()
    const poll = setInterval(load, 20000)
    return () => clearInterval(poll)
  }, [])

  useEffect(() => {
    const onActivity = () => {
      lastActivityRef.current = Date.now()
      if (terminalLocked) return
      setWarnActive(false)
    }
    const events: Array<keyof WindowEventMap> = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"]
    events.forEach((ev) => window.addEventListener(ev, onActivity, { passive: true }))

    const timer = setInterval(() => {
      if (terminalLocked) return
      const idle = Date.now() - lastActivityRef.current
      if (idle >= INACTIVITY_LIMIT_MS) {
        setTerminalLocked(true)
        setWarnActive(false)
        return
      }
      if (idle >= INACTIVITY_LIMIT_MS - WARNING_WINDOW_MS) {
        setWarnActive(true)
        setCountdownText(formatCountdown(INACTIVITY_LIMIT_MS - idle))
      } else {
        setWarnActive(false)
      }
    }, 1000)

    return () => {
      clearInterval(timer)
      events.forEach((ev) => window.removeEventListener(ev, onActivity))
    }
  }, [terminalLocked])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setCommandOpen((v) => !v)
      }
      if (e.key === "Escape") setCommandOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  useEffect(() => {
    if (commandOpen) {
      setTimeout(() => searchInputRef.current?.focus(), 0)
    } else {
      setQuery("")
    }
  }, [commandOpen])

  const baseItems = useMemo(() => {
    const nav: SearchItem[] = [
      { id: "nav-ops", label: "Operations", hint: "Live map and intel feed", section: "Navigation", href: "/operations" },
      { id: "nav-alerts", label: "Alerts", hint: "Confidence and ETA board", section: "Navigation", href: "/alerts" },
      { id: "nav-sources", label: "Sources", hint: "Reliability and source health", section: "Navigation", href: "/sources" },
      { id: "nav-v2-ops", label: "V2 Operations", hint: "Phase-2 operations", section: "Navigation", href: "/v2/operations" },
      { id: "nav-v2-alerts", label: "V2 Alerts", hint: "Phase-2 alert board", section: "Navigation", href: "/v2/alerts" },
      { id: "nav-v2-health", label: "V2 Health", hint: "System reliability", section: "Navigation", href: "/v2/health" },
    ]
    return [...nav, ...assetItems, ...eventItems]
  }, [assetItems, eventItems])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return baseItems
    return baseItems.filter((x) => `${x.label} ${x.hint || ""} ${x.section}`.toLowerCase().includes(q))
  }, [baseItems, query])

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

  const unlockTerminal = () => {
    lastActivityRef.current = Date.now()
    setTerminalLocked(false)
    setWarnActive(false)
    setCountdownText("03:00")
  }

  return (
    <>
      <header className="flex flex-col glass-panel border-b border-[rgba(255,255,255,0.06)]">
        <div className="h-5 border-b border-[#ff1a3c]/30 bg-[#24070c] px-4 flex items-center justify-between text-[9px] tracking-[0.18em] uppercase">
          <span className="text-[#ff6f7f]">SECRET // NOFORN // REL TO FVEY</span>
          <span className="text-[#8f96ab]">Training Simulation Marking</span>
        </div>

        <div className="flex items-center justify-between px-4 py-2">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-osint-red" />
              <span className="text-sm font-bold tracking-[0.2em] text-[#e0e0e8]">OSINT NEXUS</span>
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-osint-red opacity-75 animate-blink" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-osint-red" />
              </span>
            </div>

            <div className="hidden sm:flex items-center gap-4 ml-6">
              <div className="flex items-center gap-1.5 text-[10px] text-osint-green uppercase tracking-widest">
                <Lock className="h-3 w-3" />
                <span>Secure Connection</span>
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-osint-blue uppercase tracking-widest">
                <Radio className="h-3 w-3" />
                <span>Signal Locked</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setCommandOpen(true)}
              className="hidden md:flex items-center gap-2 rounded-lg border border-white/10 bg-black/35 px-3 py-1.5 text-[11px] text-muted-foreground hover:border-osint-blue/30 hover:text-[#d8e7ff]"
            >
              <Search className="h-3.5 w-3.5" />
              <span className="max-w-[160px] truncate">Search...</span>
              <span className="rounded border border-white/10 px-1.5 py-px text-[9px] tracking-wider">Ctrl+K</span>
            </button>

            <div className="hidden xl:flex items-center gap-3 text-[9px] text-muted-foreground font-mono">
              <span className="text-osint-blue">ZULU {dtgText}</span>
              <span>LOCAL {localTime}</span>
              <span>THEATER {theaterTime}</span>
            </div>

            <div className="hidden md:flex items-center gap-2 text-[10px] text-muted-foreground uppercase tracking-wider">
              <span className="h-1.5 w-1.5 rounded-full bg-osint-green" />
              <span>SYS NOMINAL</span>
            </div>
            <time className="text-xs text-osint-amber font-mono tabular-nums tracking-wider">{utcTime}</time>
          </div>
        </div>

        {warnActive && (
          <div className="h-6 border-t border-osint-red/25 bg-osint-red/12 px-4 flex items-center justify-between text-[10px]">
            <span className="text-osint-red tracking-[0.14em] uppercase animate-blink">
              Session Expires In {countdownText} - Re-authenticate Or Terminal Locks
            </span>
            <span className="text-[#ff9aa8]">Activity required</span>
          </div>
        )}

        <div className="flex items-center bg-osint-red/10 border-t border-osint-red/20 overflow-hidden h-6">
          <div className="shrink-0 bg-osint-red px-2 h-full flex items-center">
            <span className="text-[9px] font-bold tracking-[0.15em] text-white whitespace-nowrap">● BREAKING</span>
          </div>
          <div className="flex-1 overflow-hidden relative">
            <div className="flex whitespace-nowrap text-[10px] text-[#c0c0d0] tracking-wide" style={{ animation: "ticker 60s linear infinite", willChange: "transform" }}>
              <span className="px-8">{tickerText}</span>
              <span className="px-8" aria-hidden>{tickerText}</span>
            </div>
          </div>
        </div>
      </header>

      {commandOpen && (
        <div className="fixed inset-0 z-[180] bg-black/70 backdrop-blur-sm">
          <div className="mx-auto mt-20 w-[min(920px,92vw)] rounded-xl border border-white/15 bg-[rgba(8,10,18,0.96)] shadow-2xl">
            <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
              <Search className="h-4 w-4 text-osint-blue" />
              <input
                ref={searchInputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search assets, events, comms, regions..."
                className="w-full bg-transparent text-sm text-[#d8deef] outline-none placeholder:text-[#6b7288]"
              />
              <button type="button" onClick={() => setCommandOpen(false)} className="rounded border border-white/15 px-2 py-1 text-[10px] text-muted-foreground hover:text-white">
                ESC
              </button>
              <button type="button" onClick={() => setCommandOpen(false)} className="text-muted-foreground hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-[66vh] overflow-y-auto osint-feed-scroll p-4">
              {["Navigation", "Tracked Assets", "Intel Events"].map((section) => {
                const rows = filtered.filter((x) => x.section === section)
                if (rows.length === 0) return null
                return (
                  <div key={section} className="mb-4">
                    <p className="mb-2 text-[10px] tracking-[0.2em] uppercase text-[#7f86a0]">{section}</p>
                    <div className="space-y-1.5">
                      {rows.map((item) => (
                        item.href ? (
                          <Link
                            key={item.id}
                            href={item.href}
                            onClick={() => setCommandOpen(false)}
                            className="block rounded-md border border-transparent bg-white/[0.02] px-3 py-2 hover:border-osint-blue/30 hover:bg-white/[0.05]"
                          >
                            <p className="text-[13px] text-[#dbe4ff]">{item.label}</p>
                            {item.hint ? <p className="text-[10px] text-muted-foreground">{item.hint}</p> : null}
                          </Link>
                        ) : (
                          <div key={item.id} className="rounded-md bg-white/[0.02] px-3 py-2">
                            <p className="text-[13px] text-[#dbe4ff]">{item.label}</p>
                            {item.hint ? <p className="text-[10px] text-muted-foreground">{item.hint}</p> : null}
                          </div>
                        )
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
            <div className="flex items-center justify-between border-t border-white/10 px-4 py-2 text-[10px] text-muted-foreground">
              <span>CTRL+K to toggle</span>
              <span>OSINT NEXUS SEARCH v1.0</span>
            </div>
          </div>
        </div>
      )}

      {terminalLocked && (
        <div className="fixed inset-0 z-[190] bg-black/85 backdrop-blur-md flex items-center justify-center">
          <div className="w-[min(520px,92vw)] rounded-xl border border-osint-red/40 bg-[rgba(15,5,8,0.95)] p-6 text-center">
            <p className="text-[10px] uppercase tracking-[0.3em] text-osint-red mb-2">Terminal Locked</p>
            <h2 className="text-2xl font-semibold text-[#f3d7dd] mb-3">Session Timed Out</h2>
            <p className="text-sm text-[#caa6af] mb-6">Re-authenticate to resume operations console access.</p>
            <button
              type="button"
              onClick={unlockTerminal}
              className="rounded border border-osint-red/50 bg-osint-red/15 px-4 py-2 text-sm text-osint-red hover:bg-osint-red/25"
            >
              Re-authenticate
            </button>
          </div>
        </div>
      )}

      <style>{`
        @keyframes ticker {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
    </>
  )
}
