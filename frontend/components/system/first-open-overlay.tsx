"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { usePathname } from "next/navigation"
import { Shield } from "lucide-react"

// ── Real-data shape fetched before boot starts ──────────────────────────────
interface BootData {
  aircraft: number
  vessels: number
  eventsTotal: number
  postgres: "OK" | "DEGRADED" | "UNKNOWN"
  redis: "OK" | "DEGRADED" | "UNKNOWN"
  ollama: "OK" | "DEGRADED" | "UNKNOWN"
  neo4j: "OK" | "DEGRADED" | "UNKNOWN"
  latencyMs: number
  sourcesActive: number
  uptimeSeconds: number
}

const FALLBACK: BootData = {
  aircraft: 0,
  vessels: 0,
  eventsTotal: 0,
  postgres: "UNKNOWN",
  redis: "UNKNOWN",
  ollama: "UNKNOWN",
  neo4j: "UNKNOWN",
  latencyMs: 0,
  sourcesActive: 0,
  uptimeSeconds: 0,
}

async function fetchBootData(): Promise<BootData> {
  const t0 = Date.now()
  try {
    const [statsRes, healthRes] = await Promise.all([
      fetch("/api/stats", { cache: "no-store" }).catch(() => null),
      fetch("/api/health", { cache: "no-store" }).catch(() => null),
    ])
    const latencyMs = Date.now() - t0
    const stats = statsRes?.ok ? await statsRes.json().catch(() => null) : null
    const health = healthRes?.ok ? await healthRes.json().catch(() => null) : null

    const dep = (key: string): BootData["postgres"] => {
      const v = health?.checks?.[key]
      if (v === "ok") return "OK"
      if (v === "degraded" || v === "error") return "DEGRADED"
      return "UNKNOWN"
    }

    return {
      aircraft: stats?.aircraft_tracked ?? 0,
      vessels: stats?.vessels_tracked ?? 0,
      eventsTotal: stats?.events_total ?? 0,
      postgres: dep("postgres"),
      redis: dep("redis"),
      ollama: dep("ollama"),
      neo4j: dep("neo4j"),
      latencyMs,
      sourcesActive: stats?.sources_active ?? 0,
      uptimeSeconds: stats?.uptime_seconds ?? 0,
    }
  } catch {
    return { ...FALLBACK, latencyMs: Date.now() - t0 }
  }
}

// ── Build boot lines from real data ─────────────────────────────────────────
function depColor(s: BootData["postgres"]): string {
  if (s === "OK") return "#00ff88"
  if (s === "DEGRADED") return "#ff1a3c"
  return "#ffa630"
}

function makeBootLines(d: BootData) {
  const pg = depColor(d.postgres)
  const rd = depColor(d.redis)
  const ol = depColor(d.ollama)
  const n4 = depColor(d.neo4j)
  const uptimeH = d.uptimeSeconds > 0 ? `${Math.floor(d.uptimeSeconds / 3600)}h ${Math.floor((d.uptimeSeconds % 3600) / 60)}m` : "N/A"

  return [
    { text: "[SYS] BIOS POST CHECK ................ OK", color: "#6a6a7a", delay: 60 },
    { text: "[SYS] MEMORY TEST 64GB ECC ........... PASS", color: "#6a6a7a", delay: 50 },
    { text: "[SYS] SECURE BOOT VERIFIED ........... OK", color: "#6a6a7a", delay: 40 },
    { text: "", color: "", delay: 200 },
    { text: "OSINT NEXUS v4.7.2-MILSPEC", color: "#e0e0e8", delay: 80 },
    { text: "DEFENSE INTELLIGENCE SYSTEMS COMMAND", color: "#6a6a7a", delay: 60 },
    { text: "----------------------------------------", color: "#2a2a3a", delay: 30 },
    { text: "", color: "", delay: 150 },
    { text: "[CRYPTO] Initializing AES-256-GCM encryption module ...", color: "#00b4d8", delay: 70 },
    { text: "[CRYPTO] Key exchange protocol ECDH-P384 .... ACTIVE", color: "#00b4d8", delay: 60 },
    { text: "[CRYPTO] Certificate chain validated ......... OK", color: "#00ff88", delay: 50 },
    { text: "", color: "", delay: 100 },
    { text: "[NET] Establishing secure uplink .............", color: "#ffa630", delay: 90 },
    { text: "[NET] TLS 1.3 handshake complete", color: "#00ff88", delay: 50 },
    { text: `[NET] API latency ............................ ${d.latencyMs}ms`, color: "#6a6a7a", delay: 40 },
    { text: `[NET] Backend uptime ......................... ${uptimeH}`, color: "#6a6a7a", delay: 40 },
    { text: "", color: "", delay: 100 },
    { text: `[DB] PostgreSQL ............................... ${d.postgres}`, color: pg, delay: 60 },
    { text: `[DB] Redis cache .............................. ${d.redis}`, color: rd, delay: 50 },
    { text: `[DB] Neo4j graph .............................. ${d.neo4j}`, color: n4, delay: 50 },
    { text: `[AI] Ollama inference engine .................. ${d.ollama}`, color: ol, delay: 50 },
    { text: "", color: "", delay: 100 },
    { text: "[INTEL] Loading SIGINT modules ...............", color: "#00b4d8", delay: 80 },
    { text: "[INTEL] Loading IMINT modules ...............", color: "#00b4d8", delay: 70 },
    { text: "[INTEL] Loading HUMINT modules ...............", color: "#00b4d8", delay: 60 },
    { text: "[INTEL] Loading ELINT modules ...............", color: "#00b4d8", delay: 50 },
    { text: `[INTEL] Active sources ..................... ${d.sourcesActive} feeds`, color: "#00ff88", delay: 50 },
    { text: "", color: "", delay: 100 },
    { text: "[MAP] Initializing geospatial overlay ........", color: "#ffa630", delay: 70 },
    { text: "[MAP] Loading MIL-STD-2525D symbology .......", color: "#ffa630", delay: 60 },
    { text: "[MAP] Tactical data link established ........ OK", color: "#00ff88", delay: 50 },
    { text: "", color: "", delay: 100 },
    { text: `[TRACK] ADS-B feed ........................ ${d.aircraft} contacts`, color: "#00b4d8", delay: 60 },
    { text: `[TRACK] AIS maritime ...................... ${d.vessels} contacts`, color: "#00b4d8", delay: 50 },
    { text: `[TRACK] Events database ................... ${d.eventsTotal.toLocaleString()} records`, color: "#00b4d8", delay: 40 },
    { text: "", color: "", delay: 150 },
    { text: "[AUTH] Operator clearance: TOP SECRET // SCI", color: "#ff1a3c", delay: 100 },
    { text: "[AUTH] Session token generated .............. OK", color: "#00ff88", delay: 50 },
    { text: "", color: "", delay: 200 },
    { text: "========================================", color: "#ff1a3c", delay: 40 },
    { text: "  ALL SYSTEMS NOMINAL - DASHBOARD READY  ", color: "#00ff88", delay: 100 },
    { text: "========================================", color: "#ff1a3c", delay: 40 },
  ]
}

function makeSubsystems(d: BootData) {
  return [
    { name: "ENCRYPTION", status: "AES-256-GCM" },
    { name: "POSTGRES", status: d.postgres },
    { name: "REDIS", status: d.redis },
    { name: "NEO4J", status: d.neo4j },
    { name: "OLLAMA", status: d.ollama },
    { name: "ADS-B", status: d.aircraft > 0 ? `${d.aircraft} TRACKS` : "NO DATA" },
    { name: "AIS", status: d.vessels > 0 ? `${d.vessels} TRACKS` : "NO DATA" },
    { name: "EVENTS DB", status: `${d.eventsTotal.toLocaleString()} REC` },
    { name: "SOURCES", status: `${d.sourcesActive} FEEDS` },
    { name: "API LATENCY", status: `${d.latencyMs}ms` },
    { name: "CLEARANCE", status: "TS//SCI" },
  ]
}

// ── Boot sequence component ──────────────────────────────────────────────────
export function BootSequence({ onComplete, data }: { onComplete: () => void; data: BootData }) {
  const bootLines = makeBootLines(data)
  const subsystems = makeSubsystems(data)

  const [visibleLines, setVisibleLines] = useState<number>(0)
  const [typingLine, setTypingLine] = useState<string>("")
  const [typingIndex, setTypingIndex] = useState<number>(0)
  const [phase, setPhase] = useState<"boot" | "classification" | "reveal">("boot")
  const [progress, setProgress] = useState(0)
  const [subsystemCount, setSubsystemCount] = useState(0)
  const [glitchActive, setGlitchActive] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const hasInteractedRef = useRef(false)

  const playBeep = useCallback((freq: number = 800, duration: number = 30) => {
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext()
      }
      const ctx = audioContextRef.current
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.frequency.value = freq
      osc.type = "square"
      gain.gain.value = 0.02
      osc.start()
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration / 1000)
      osc.stop(ctx.currentTime + duration / 1000)
    } catch {
      // Audio not available
    }
  }, [])

  useEffect(() => {
    const handleInteraction = () => {
      if (!hasInteractedRef.current) {
        hasInteractedRef.current = true
        if (audioContextRef.current?.state === "suspended") {
          audioContextRef.current.resume()
        }
      }
    }
    window.addEventListener("click", handleInteraction, { once: true })
    window.addEventListener("keydown", handleInteraction, { once: true })
    return () => {
      window.removeEventListener("click", handleInteraction)
      window.removeEventListener("keydown", handleInteraction)
    }
  }, [])

  // Phase 1: Boot log typewriter
  useEffect(() => {
    if (phase !== "boot") return

    if (visibleLines >= bootLines.length) {
      const t = setTimeout(() => setPhase("classification"), 600)
      return () => clearTimeout(t)
    }

    const currentLine = bootLines[visibleLines]

    if (currentLine.text === "") {
      const t = setTimeout(() => {
        setVisibleLines((v) => v + 1)
        setTypingLine("")
        setTypingIndex(0)
      }, currentLine.delay)
      return () => clearTimeout(t)
    }

    if (typingIndex < currentLine.text.length) {
      const charDelay = Math.max(8, currentLine.delay / currentLine.text.length)
      const t = setTimeout(() => {
        setTypingLine(currentLine.text.slice(0, typingIndex + 1))
        setTypingIndex((i) => i + 1)
        if (currentLine.text[typingIndex] === "." || currentLine.text[typingIndex] === "[") {
          playBeep(600 + Math.random() * 400, 15)
        }
      }, charDelay)
      return () => clearTimeout(t)
    }

    const t = setTimeout(() => {
      setVisibleLines((v) => v + 1)
      setTypingLine("")
      setTypingIndex(0)
      const pct = Math.min(100, Math.round(((visibleLines + 1) / bootLines.length) * 100))
      setProgress(pct)
      if (
        currentLine.text.includes("ACTIVE") ||
        currentLine.text.includes("OK") ||
        currentLine.text.includes("LOCKED") ||
        currentLine.text.includes("ONLINE") ||
        currentLine.text.includes("contacts") ||
        currentLine.text.includes("records") ||
        currentLine.text.includes("feeds")
      ) {
        setSubsystemCount((c) => Math.min(c + 1, subsystems.length))
      }
    }, 40)
    return () => clearTimeout(t)
  }, [phase, visibleLines, typingIndex, playBeep, bootLines, subsystems.length])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [visibleLines, typingLine])

  // Phase 2: Classification splash
  useEffect(() => {
    if (phase !== "classification") return
    playBeep(1200, 80)
    const g1 = setTimeout(() => setGlitchActive(true), 200)
    const g2 = setTimeout(() => setGlitchActive(false), 350)
    const g3 = setTimeout(() => setGlitchActive(true), 500)
    const g4 = setTimeout(() => setGlitchActive(false), 580)
    const t = setTimeout(() => setPhase("reveal"), 2800)
    return () => {
      clearTimeout(g1); clearTimeout(g2); clearTimeout(g3); clearTimeout(g4); clearTimeout(t)
    }
  }, [phase, playBeep])

  // Phase 3: Reveal
  useEffect(() => {
    if (phase !== "reveal") return
    const t = setTimeout(onComplete, 1200)
    return () => clearTimeout(t)
  }, [phase, onComplete])

  if (phase === "classification") {
    return (
      <div className="fixed inset-0 z-50 bg-background flex flex-col items-center justify-center overflow-hidden">
        <div className="absolute inset-0 scanline-overlay pointer-events-none" />
        {glitchActive && (
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,26,60,0.03) 2px, rgba(255,26,60,0.03) 4px)",
              transform: `translateX(${Math.random() * 4 - 2}px)`,
            }}
          />
        )}
        <div className="relative flex flex-col items-center gap-6 animate-in fade-in zoom-in-95 duration-500">
          <div className="relative">
            <div className="absolute -inset-8 rounded-full border border-[rgba(255,26,60,0.15)] animate-spin" style={{ animationDuration: "8s" }} />
            <div className="absolute -inset-14 rounded-full border border-[rgba(255,26,60,0.08)]" />
            <div
              className="relative h-20 w-20 rounded-full border-2 border-[#ff1a3c] flex items-center justify-center"
              style={{ boxShadow: "0 0 30px rgba(255,26,60,0.3), inset 0 0 20px rgba(255,26,60,0.1)" }}
            >
              <Shield className="h-10 w-10 text-[#ff1a3c]" />
            </div>
          </div>
          <div className="flex flex-col items-center gap-2 mt-2">
            <h1 className="text-2xl font-bold tracking-[0.4em] text-[#e0e0e8]">OSINT NEXUS</h1>
            <div className="h-px w-48 bg-gradient-to-r from-transparent via-[#ff1a3c] to-transparent" />
            <p className="text-[10px] tracking-[0.3em] text-[#6a6a7a] uppercase mt-1">Defense Intelligence Systems Command</p>
          </div>
          <div
            className="mt-4 px-8 py-3 border border-[#ff1a3c]/40 rounded"
            style={{ background: "rgba(255,26,60,0.06)", boxShadow: "0 0 40px rgba(255,26,60,0.1)" }}
          >
            <p className="text-xs font-bold tracking-[0.35em] text-[#ff1a3c] text-center animate-blink">TOP SECRET // SCI // NOFORN</p>
          </div>
          <p className="text-[9px] tracking-[0.2em] text-[#4a4a5a] uppercase mt-2">Authorized Personnel Only</p>
        </div>
        <div className="absolute bottom-8 flex flex-col items-center gap-2">
          <div className="flex items-center gap-3">
            <div className="h-px w-16 bg-[rgba(255,26,60,0.2)]" />
            <span className="text-[8px] tracking-[0.3em] text-[#ff1a3c]/50 uppercase">Classified Material</span>
            <div className="h-px w-16 bg-[rgba(255,26,60,0.2)]" />
          </div>
          <span className="text-[8px] tracking-[0.2em] text-[#3a3a4a]">Unauthorized access will be prosecuted under 18 U.S.C. 1030</span>
        </div>
      </div>
    )
  }

  if (phase === "reveal") {
    return <div className="fixed inset-0 z-50 bg-background animate-out fade-out duration-1000 fill-mode-forwards pointer-events-none" />
  }

  return (
    <div className="fixed inset-0 z-50 bg-background flex overflow-hidden">
      <div className="absolute inset-0 scanline-overlay pointer-events-none" />

      {/* Left panel: terminal output */}
      <div className="flex-1 flex flex-col p-6 md:p-10 overflow-hidden">
        <div className="flex items-center gap-3 mb-4">
          <Shield className="h-5 w-5 text-[#ff1a3c]" />
          <span className="text-xs font-bold tracking-[0.25em] text-[#e0e0e8]">SYSTEM INITIALIZATION</span>
          <div className="flex-1" />
          <span className="text-[9px] tracking-[0.2em] text-[#ff1a3c]/60 uppercase animate-blink">RESTRICTED</span>
        </div>
        <div className="h-px w-full bg-gradient-to-r from-[#ff1a3c]/40 via-[rgba(255,255,255,0.06)] to-transparent mb-4" />

        <div ref={scrollRef} className="flex-1 overflow-hidden font-mono text-[11px] leading-[1.8] select-none">
          {bootLines.slice(0, visibleLines).map((line, i) => (
            <div key={i} style={{ color: line.color || "transparent" }} className="whitespace-pre">
              {line.text || "\u00a0"}
            </div>
          ))}
          {visibleLines < bootLines.length && typingLine && (
            <div style={{ color: bootLines[visibleLines]?.color || "#6a6a7a" }} className="whitespace-pre">
              {typingLine}
              <span className="inline-block w-[7px] h-[14px] bg-[#00ff88] ml-px align-middle animate-blink" />
            </div>
          )}
          {visibleLines < bootLines.length && !typingLine && (
            <div>
              <span className="inline-block w-[7px] h-[14px] bg-[#00ff88] animate-blink" />
            </div>
          )}
        </div>

        <div className="mt-4">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[9px] tracking-[0.2em] text-[#6a6a7a] uppercase">System Load</span>
            <span className="text-[9px] tracking-wider text-[#00ff88] tabular-nums">{progress}%</span>
          </div>
          <div className="h-1 w-full bg-[rgba(255,255,255,0.04)] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300 ease-out"
              style={{
                width: `${progress}%`,
                background: progress < 100 ? "linear-gradient(90deg, #00b4d8, #00ff88)" : "#00ff88",
                boxShadow: "0 0 8px rgba(0,255,136,0.4)",
              }}
            />
          </div>
        </div>
      </div>

      {/* Right panel: subsystem status */}
      <div className="hidden md:flex flex-col w-72 border-l border-[rgba(255,255,255,0.06)] p-6 bg-[rgba(0,0,0,0.3)]">
        <div className="flex items-center gap-2 mb-4">
          <div className="h-2 w-2 rounded-full bg-[#00ff88] animate-pulse" />
          <span className="text-[9px] font-bold tracking-[0.25em] text-[#6a6a7a] uppercase">Live System Status</span>
        </div>
        <div className="h-px w-full bg-[rgba(255,255,255,0.06)] mb-4" />

        <div className="flex flex-col gap-2">
          {subsystems.map((sub, i) => {
            const isOnline = i < subsystemCount
            const isDegraded = isOnline && (sub.status === "DEGRADED" || sub.status === "UNKNOWN")
            const statusColor = isDegraded ? "#ffa630" : isOnline ? "#00ff88" : "#3a3a4a"
            return (
              <div
                key={sub.name}
                className="flex items-center justify-between py-1.5 px-2 rounded transition-all duration-300"
                style={{
                  background: isOnline ? (isDegraded ? "rgba(255,166,48,0.04)" : "rgba(0,255,136,0.03)") : "transparent",
                  opacity: isOnline ? 1 : 0.3,
                }}
              >
                <span className="text-[9px] tracking-[0.15em] text-[#8a8a9a] uppercase">{sub.name}</span>
                <span className="text-[9px] font-bold tracking-wider transition-colors duration-300" style={{ color: statusColor }}>
                  {isOnline ? sub.status : "---"}
                </span>
              </div>
            )
          })}
        </div>

        <div className="mt-auto pt-4 border-t border-[rgba(255,255,255,0.04)]">
          <div className="text-[8px] text-[#2a2a3a] leading-[1.6] font-mono select-none">
            <div>{"0x4F53 494E 5420 4E45"}</div>
            <div>{"0x5855 5320 7634 2E37"}</div>
            <div>{"0x2E32 2D4D 494C 5350"}</div>
            <div>{"0x4543 0000 0000 0000"}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Outer wrapper: fetches data then shows boot ──────────────────────────────
export function FirstOpenOverlay() {
  const pathname = usePathname()
  const [visible, setVisible] = useState(false)
  const [bootData, setBootData] = useState<BootData | null>(null)

  useEffect(() => {
    if ((pathname || "").startsWith("/v2/briefs/print")) {
      setVisible(false)
      return
    }
    try {
      const seen = sessionStorage.getItem("osint_boot_seen") === "1"
      const force = sessionStorage.getItem("osint_boot_force_once") === "1"
      if (!seen || force) {
        setVisible(true)
        // Fetch real data in parallel with showing the overlay
        fetchBootData().then(setBootData)
      }
    } catch {
      setVisible(true)
      fetchBootData().then(setBootData)
    }
  }, [pathname])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "r" || e.key === "R")) {
        try {
          sessionStorage.setItem("osint_boot_force_once", "1")
        } catch {
          // Ignore
        }
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const handleComplete = () => {
    try {
      sessionStorage.setItem("osint_boot_seen", "1")
      sessionStorage.removeItem("osint_boot_force_once")
    } catch {
      // Ignore
    }
    setVisible(false)
  }

  if (!visible) return null
  // Wait until data is fetched (fast — same-origin API, <200ms typical)
  // Show a minimal cursor while waiting so there's no blank flash
  if (!bootData) {
    return (
      <div className="fixed inset-0 z-50 bg-background flex items-center justify-center">
        <div className="absolute inset-0 scanline-overlay pointer-events-none" />
        <span className="inline-block w-[7px] h-[14px] bg-[#00ff88] animate-blink" />
      </div>
    )
  }
  return <BootSequence onComplete={handleComplete} data={bootData} />
}
