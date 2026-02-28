"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { MapArea } from "./map-area"
import { TopBar } from "./top-bar"
import { AiAnalyst } from "./ai-analyst-v2"
import { ConflictTimeline } from "./conflict-timeline"

type EventType = "STRIKE" | "MOVEMENT" | "NOTAM" | "CLASH" | "CRITICAL"

export interface IntelEvent {
  id: string
  incident_id?: string
  type: EventType
  desc: string
  lat: number
  lng: number
  source: string
  timestamp?: string
  url?: string
  video_url?: string
  lang?: string
  observed_facts?: string[]
  model_inference?: string[]
  confidence_reason?: string
  video_assessment?: string
  video_confidence?: string
}

export interface Aircraft {
  id: string
  callsign: string
  country: string
  lat: number
  lng: number
  alt: number
  speed: number
  heading: number
  military: boolean
}

const TYPE_STYLES: Record<EventType, { bg: string; border: string; text: string }> = {
  CRITICAL: { bg: "#b24bff18", border: "#b24bff60", text: "#b24bff" },
  STRIKE: { bg: "#ff1a3c18", border: "#ff1a3c40", text: "#ff1a3c" },
  MOVEMENT: { bg: "#00b4d818", border: "#00b4d840", text: "#00b4d8" },
  NOTAM: { bg: "#ffa63018", border: "#ffa63040", text: "#ffa630" },
  CLASH: { bg: "#00ff8818", border: "#00ff8840", text: "#00ff88" },
}

const SOURCE_COLORS: Record<string, string> = {
  Reuters: "#ff8c00",
  "Al Jazeera": "#c8a84b",
  "BBC News": "#bb1919",
  "CBS News": "#1a73e8",
  "The Guardian": "#09803a",
  "Times of Israel": "#4a90d9",
  "Red Alert": "#ff0040",
  "AJ Mubasher (TG)": "#6a4ccc",
  "Roaa War Studies (TG)": "#00b4d8",
}

function playAlertBeep(type: "CRITICAL" | "STRIKE") {
  try {
    const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)

    if (type === "CRITICAL") {
      osc.frequency.value = 880
      gain.gain.setValueAtTime(0.15, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15)
      osc.start(ctx.currentTime)
      osc.stop(ctx.currentTime + 0.15)
      const osc2 = ctx.createOscillator()
      const gain2 = ctx.createGain()
      osc2.connect(gain2)
      gain2.connect(ctx.destination)
      osc2.frequency.value = 1100
      gain2.gain.setValueAtTime(0.15, ctx.currentTime + 0.2)
      gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4)
      osc2.start(ctx.currentTime + 0.2)
      osc2.stop(ctx.currentTime + 0.4)
    } else {
      osc.frequency.value = 660
      gain.gain.setValueAtTime(0.1, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.12)
      osc.start(ctx.currentTime)
      osc.stop(ctx.currentTime + 0.12)
    }
  } catch (_) {}
}

function SourceBadge({ source }: { source: string }) {
  const color = SOURCE_COLORS[source] ?? "#808090"
  return (
    <span
      className="text-[8px] font-bold tracking-[0.1em] px-1.5 py-0.5 rounded shrink-0"
      style={{ background: `${color}20`, color, border: `1px solid ${color}40` }}
    >
      {source.toUpperCase()}
    </span>
  )
}

function IntelCard({ event, isNew, onClick, crisisMode }: { event: IntelEvent; isNew?: boolean; onClick: () => void; crisisMode: boolean }) {
  const style = TYPE_STYLES[event.type] ?? TYPE_STYLES.CLASH
  const isCritical = event.type === "CRITICAL"
  const displayDesc = event.desc.replace(/^\[.+?\]\s*/, "")
  const sourceTag = event.desc.match(/^\[(.+?)\]/)?.[1] ?? event.source

  const videoHref = event.video_url
    ? (event.video_url.startsWith("/media/") ? `http://localhost:8000${event.video_url}` : event.video_url)
    : null

  return (
    <div
      onClick={onClick}
      className={`rounded-lg ${crisisMode ? "p-4" : "p-3"} cursor-pointer transition-all duration-200 hover:bg-white/5 ${isNew ? "animate-flash" : ""}`}
      style={{
        background: isCritical ? "rgba(178,75,255,0.08)" : "rgba(11,12,18,0.7)",
        border: `1px solid ${isCritical ? "rgba(178,75,255,0.3)" : "rgba(255,255,255,0.07)"}`,
        boxShadow: isCritical ? "0 0 12px rgba(178,75,255,0.15)" : "none",
      }}
    >
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span className="text-[9px] font-bold tracking-[0.15em] px-2 py-0.5 rounded" style={{ background: style.bg, border: `1px solid ${style.border}`, color: style.text }}>
          {isCritical ? "⚠ CRITICAL" : event.type}
        </span>
        <SourceBadge source={sourceTag} />
        {event.video_assessment ? (
          <span className="text-[8px] px-1.5 py-0.5 rounded border border-osint-green/30 text-osint-green">{event.video_assessment}</span>
        ) : null}
        <span className="text-[9px] text-muted-foreground tabular-nums ml-auto shrink-0">{event.timestamp ?? "--:--:--Z"}</span>
      </div>

      <p className={`leading-relaxed mb-2 ${crisisMode ? "text-[13px]" : "text-[11px]"} ${isCritical ? "text-[#d0b0f0] font-medium" : "text-[#b0b0c4]"}`}>
        {displayDesc}
      </p>

      {event.confidence_reason ? <p className="text-[10px] text-osint-blue mb-2">{event.confidence_reason}</p> : null}

      <div className="grid grid-cols-2 gap-2 mb-2 text-[10px]">
        <div className="rounded border border-white/10 p-1.5 bg-black/20">
          <p className="text-osint-green uppercase tracking-[0.12em] text-[9px] mb-1">Observed</p>
          <p className="text-[#b6d7bf] line-clamp-2">{(event.observed_facts && event.observed_facts[0]) || "No direct fact extracted"}</p>
        </div>
        <div className="rounded border border-white/10 p-1.5 bg-black/20">
          <p className="text-osint-amber uppercase tracking-[0.12em] text-[9px] mb-1">Inference</p>
          <p className="text-[#d6c7a8] line-clamp-2">{(event.model_inference && event.model_inference[0]) || "No model inference"}</p>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-[9px] text-muted-foreground tabular-nums">{event.lat.toFixed(3)}N {event.lng.toFixed(3)}E</span>
        <div className="flex items-center gap-2">
          {videoHref && (
            <a
              href={videoHref}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-[9px] text-osint-green hover:text-osint-green/80 underline underline-offset-2"
            >
              latest video ↗
            </a>
          )}
          {event.url && (
            <a
              href={event.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-[9px] text-osint-blue hover:text-osint-blue/80 underline underline-offset-2"
            >
              source ↗
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

export function Dashboard() {
  const [events, setEvents] = useState<IntelEvent[]>([])
  const [aircraft, setAircraft] = useState<Aircraft[]>([])
  const [headlines, setHeadlines] = useState<string[]>([])
  const [filter, setFilter] = useState<"ALL" | EventType>("ALL")
  const [wsStatus, setWsStatus] = useState<"connecting" | "live" | "offline">("connecting")
  const [newIds, setNewIds] = useState<Set<string>>(new Set())
  const [crisisMode, setCrisisMode] = useState(false)
  const seenIdsRef = useRef<Set<string>>(new Set())
  const hasInteractedRef = useRef(false)

  useEffect(() => {
    const handler = () => { hasInteractedRef.current = true }
    window.addEventListener("click", handler, { once: true })
    window.addEventListener("keydown", handler, { once: true })
    return () => {
      window.removeEventListener("click", handler)
      window.removeEventListener("keydown", handler)
    }
  }, [])

  useEffect(() => {
    try {
      setCrisisMode(localStorage.getItem("osint_crisis_mode") === "1")
    } catch (_) {}
    const onMode = (e: Event) => {
      const custom = e as CustomEvent<{ crisis: boolean }>
      setCrisisMode(Boolean(custom.detail?.crisis))
      if (custom.detail?.crisis) setFilter("CRITICAL")
      else setFilter("ALL")
    }
    window.addEventListener("osint:mode", onMode)
    return () => window.removeEventListener("osint:mode", onMode)
  }, [])

  const addEvent = useCallback((evt: IntelEvent, fromBackfill = false) => {
    if (seenIdsRef.current.has(evt.id)) return
    seenIdsRef.current.add(evt.id)
    evt.timestamp = evt.timestamp ? new Date(evt.timestamp).toISOString().slice(11, 19) + "Z" : new Date().toISOString().slice(11, 19) + "Z"

    setEvents((prev) => {
      const next = [evt, ...prev]
      return next.slice(0, crisisMode ? 280 : 200)
    })

    setHeadlines((prev) => [evt.desc, ...prev].slice(0, 40))

    if (!fromBackfill) {
      setNewIds((prev) => new Set(prev).add(evt.id))
      setTimeout(() => setNewIds((prev) => {
        const next = new Set(prev)
        next.delete(evt.id)
        return next
      }), 2000)

      if (hasInteractedRef.current && (evt.type === "CRITICAL" || evt.type === "STRIKE")) {
        playAlertBeep(evt.type as "CRITICAL" | "STRIKE")
      }
    }
  }, [crisisMode])

  useEffect(() => {
    const backfill = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/events?limit=${crisisMode ? 140 : 90}`)
        if (res.ok) {
          const data: IntelEvent[] = await res.json()
          seenIdsRef.current.clear()
          setEvents([])
          setHeadlines([])
          data.forEach((evt) => addEvent(evt, true))
        }
      } catch (_) {}
    }
    backfill()
  }, [addEvent, crisisMode])

  useEffect(() => {
    let ws: WebSocket
    let retry: ReturnType<typeof setTimeout>

    const connect = () => {
      try {
        const wsUrl = (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000") + "/ws/live"
        ws = new WebSocket(wsUrl)
        ws.onopen = () => setWsStatus("live")
        ws.onclose = () => {
          setWsStatus("offline")
          retry = setTimeout(connect, crisisMode ? 1500 : 5000)
        }
        ws.onerror = () => ws.close()
        ws.onmessage = (e) => {
          try {
            const payload = JSON.parse(e.data)
            if (payload.type === "NEW_EVENT") {
              addEvent(payload.data as IntelEvent)
            } else if (payload.type === "AIRCRAFT_UPDATE") {
              setAircraft(payload.data as Aircraft[])
            }
          } catch (_) {}
        }
      } catch (_) {
        setWsStatus("offline")
      }
    }

    connect()
    return () => {
      ws?.close()
      clearTimeout(retry)
    }
  }, [addEvent, crisisMode])

  const base = filter === "ALL" ? events : events.filter((e) => e.type === filter)
  const filtered = crisisMode ? base.filter((e) => e.type === "CRITICAL" || e.type === "STRIKE") : base

  const FILTERS: Array<"ALL" | EventType> = crisisMode
    ? ["CRITICAL", "STRIKE", "CLASH"]
    : ["ALL", "CRITICAL", "STRIKE", "CLASH", "MOVEMENT", "NOTAM"]

  const FILTER_COLORS: Record<string, string> = {
    ALL: "#ffffff",
    CRITICAL: "#b24bff",
    STRIKE: "#ff1a3c",
    CLASH: "#00ff88",
    MOVEMENT: "#00b4d8",
    NOTAM: "#ffa630",
  }

  const handleEventClick = (evt: IntelEvent) => {
    if (evt.url) {
      window.open(evt.url, "_blank", "noopener,noreferrer")
      return
    }
    window.open("https://twitter.com/spectatorindex", "_blank", "noopener,noreferrer")
  }

  return (
    <>
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex-1 min-h-0 p-2 flex flex-col">
          <MapArea events={events} onEventClick={handleEventClick} />
        </div>
        <ConflictTimeline events={events} />
      </div>

      <aside className={`flex flex-col border-l border-[rgba(255,255,255,0.06)] overflow-hidden ${crisisMode ? "w-[420px]" : "w-[340px]"}`} style={{ background: "rgba(7,8,12,0.92)", backdropFilter: "blur(16px)" }}>
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[rgba(255,255,255,0.06)]">
          <span className="relative flex h-2 w-2">
            <span className={`absolute inline-flex h-full w-full rounded-full ${wsStatus === "live" ? "bg-osint-red animate-blink" : "bg-yellow-500"}`} />
            <span className={`relative inline-flex h-2 w-2 rounded-full ${wsStatus === "live" ? "bg-osint-red" : "bg-yellow-500"}`} />
          </span>
          <h2 className="text-[10px] font-bold tracking-[0.2em] text-[#e0e0e8] uppercase">Intel Feed</h2>
          {crisisMode ? <span className="text-[8px] px-1.5 py-px rounded border border-osint-red/40 text-osint-red">CRISIS</span> : null}
          <span className="text-[8px] ml-1 px-1.5 py-px rounded" style={{
            color: wsStatus === "live" ? "#00ff88" : "#ffa630",
            background: wsStatus === "live" ? "#00ff8820" : "#ffa63020",
            border: `1px solid ${wsStatus === "live" ? "#00ff8840" : "#ffa63040"}`,
          }}>
            {wsStatus === "live" ? "LIVE" : wsStatus.toUpperCase()}
          </span>
          <span className="ml-auto text-[9px] text-muted-foreground tabular-nums">{filtered.length} items</span>
        </div>

        <div className="px-3 pt-3 pb-1">
          <AiAnalyst />
        </div>

        <div className="px-3 pb-1 text-[10px] text-muted-foreground">
          Separation rule: <span className="text-osint-green">Observed</span> vs <span className="text-osint-amber">Model Inference</span>
        </div>

        <div className="flex gap-1 px-3 py-2 border-b border-[rgba(255,255,255,0.05)] flex-wrap">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="text-[8px] font-bold tracking-widest px-2 py-1 rounded transition-all"
              style={{
                color: filter === f ? FILTER_COLORS[f] : "#50505f",
                background: filter === f ? `${FILTER_COLORS[f]}18` : "transparent",
                border: `1px solid ${filter === f ? `${FILTER_COLORS[f]}40` : "transparent"}`,
              }}
            >
              {f}
            </button>
          ))}
        </div>

        <ScrollArea className="flex-1">
          <div className="flex flex-col gap-2 p-3">
            {filtered.map((evt) => (
              <IntelCard
                key={evt.id}
                event={evt}
                isNew={newIds.has(evt.id)}
                onClick={() => handleEventClick(evt)}
                crisisMode={crisisMode}
              />
            ))}
          </div>
        </ScrollArea>
      </aside>

      <style>{`
        @keyframes flash-in {
          0% { background: rgba(255,255,255,0.12); transform: translateX(4px); }
          100% { background: transparent; transform: translateX(0); }
        }
        .animate-flash { animation: flash-in 0.6s ease-out; }
      `}</style>
    </>
  )
}

export { TopBar }
export function IntelFeed() { return null }
