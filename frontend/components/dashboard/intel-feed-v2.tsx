"use client"

import { useEffect, useState, useCallback, useRef, useMemo } from "react"
import { MapArea } from "./map-area"
import { AiAnalyst } from "./ai-analyst-v2"

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
  confidence?: "LOW" | "MEDIUM" | "HIGH"
  confidence_score?: number
  corroborating_sources?: string[]
  video_assessment?: string
  video_confidence?: string
  mgrs?: string
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

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

function isTelegramSource(src?: string): boolean {
  const s = (src || "").trim()
  return s.endsWith("(TG)") || s === "AJ Mubasher (TG)" || s === "Roaa War Studies (TG)"
}

function isFirmsSource(src?: string): boolean {
  const s = String(src || "").toUpperCase()
  return s.includes("FIRMS") || s.includes("NASA")
}

function isOperationalEventSource(src?: string): boolean {
  return isTelegramSource(src) || isFirmsSource(src)
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

export function Dashboard() {
  const [events, setEvents] = useState<IntelEvent[]>([])
  const [wsStatus, setWsStatus] = useState<"connecting" | "live" | "offline">("connecting")
  const [crisisMode, setCrisisMode] = useState(false)
  const [selectedMapEvent, setSelectedMapEvent] = useState<IntelEvent | null>(null)
  const [showWeatherOverlay, setShowWeatherOverlay] = useState(false)
  const [defcon, setDefcon] = useState<number>(5)
  const [metoc, setMetoc] = useState({ windKts: 0, visibilityKm: 0, ceilingFt: 0, condition: "Loading...", source: "open-meteo" })
  const seenIdsRef = useRef<Set<string>>(new Set())
  const hasInteractedRef = useRef(false)
  const eventsRef = useRef<IntelEvent[]>([])

  useEffect(() => {
    eventsRef.current = events
  }, [events])

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
      const lv = Number(localStorage.getItem("osint_defcon") || "5")
      setDefcon(Number.isFinite(lv) ? Math.min(5, Math.max(1, lv)) : 5)
    } catch (_) {}
    const onDefcon = (e: Event) => {
      const custom = e as CustomEvent<{ level: number }>
      const lv = Number(custom.detail?.level || 5)
      setDefcon(Math.min(5, Math.max(1, lv)))
    }
    window.addEventListener("osint:defcon", onDefcon)
    return () => window.removeEventListener("osint:defcon", onDefcon)
  }, [])

  useEffect(() => {
    const pull = async () => {
      const ref = selectedMapEvent || eventsRef.current[0]
      const qp = ref ? `?lat=${ref.lat}&lng=${ref.lng}` : ""
      try {
        const res = await fetch(`${API_BASE}/api/v2/metoc${qp}`, { cache: "no-store" })
        if (!res.ok) return
        const data = await res.json()
        const vis = Number(data?.visibility_km ?? 0)
        const wind = Number(data?.wind_speed_kts ?? 0)
        setMetoc({
          windKts: Number.isFinite(wind) ? wind : 0,
          visibilityKm: Number.isFinite(vis) ? vis : 0,
          ceilingFt: Number(data?.cloud_ceiling_ft_est ?? 0) || 0,
          condition: vis < 3 ? "Low visibility" : wind > 28 ? "High crosswind" : "Moderate conditions",
          source: String(data?.source || "open-meteo"),
        })
      } catch (_) {}
    }
    void pull()
    const t = setInterval(() => void pull(), 30000)
    return () => clearInterval(t)
  }, [selectedMapEvent])

  useEffect(() => {
    try {
      setCrisisMode(localStorage.getItem("osint_crisis_mode") === "1")
    } catch (_) {}
    const onMode = (e: Event) => {
      const custom = e as CustomEvent<{ crisis: boolean }>
      setCrisisMode(Boolean(custom.detail?.crisis))
    }
    window.addEventListener("osint:mode", onMode)
    return () => window.removeEventListener("osint:mode", onMode)
  }, [])

  const addEvent = useCallback((evt: IntelEvent, fromBackfill = false) => {
    if (!isOperationalEventSource(evt.source)) return
    if (!evt?.id || seenIdsRef.current.has(evt.id)) return
    seenIdsRef.current.add(evt.id)
    evt.timestamp = evt.timestamp ? new Date(evt.timestamp).toISOString().slice(11, 19) + "Z" : new Date().toISOString().slice(11, 19) + "Z"

    setEvents((prev) => {
      const next = [evt, ...prev]
      return next.slice(0, crisisMode ? 280 : 200)
    })

    if (!fromBackfill) {
      if (hasInteractedRef.current && (evt.type === "CRITICAL" || evt.type === "STRIKE")) {
        playAlertBeep(evt.type)
      }
    }
  }, [crisisMode])

  useEffect(() => {
    const backfill = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v2/events?limit=${crisisMode ? 160 : 110}`)
        if (res.ok) {
          const data: IntelEvent[] = await res.json()
          seenIdsRef.current.clear()
          setEvents([])
          data.filter((evt) => isOperationalEventSource(evt.source)).forEach((evt) => addEvent(evt, true))
        }
      } catch (_) {}
    }
    backfill()
  }, [addEvent, crisisMode])

  useEffect(() => {
    if (!selectedMapEvent) return
    if (!events.some((evt) => evt.id === selectedMapEvent.id)) {
      setSelectedMapEvent(null)
    }
  }, [events, selectedMapEvent])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedMapEvent(null)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  useEffect(() => {
    let ws: WebSocket
    let retry: ReturnType<typeof setTimeout>

    const connect = () => {
      try {
        const wsUrl = (process.env.NEXT_PUBLIC_WS_URL ?? (typeof window !== "undefined" ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}` : "ws://localhost:8000")) + "/ws/live/v2"
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
              const evt = payload.data as IntelEvent
              if (isOperationalEventSource(evt?.source)) addEvent(evt)
            } else if (payload.type === "NEW_EVENT_DIFF") {
              const d = payload.data || {}
              if (!isOperationalEventSource(d.source)) return
              addEvent({
                id: d.id,
                incident_id: d.incident_id,
                type: d.type || "CLASH",
                desc: `[${d.source || "Source"}] update`,
                source: d.source || "Source",
                lat: Number(d.lat || 0),
                lng: Number(d.lng || 0),
                timestamp: d.timestamp,
                observed_facts: ["Diff update from ingestion queue"],
                model_inference: [],
              })
            } else if (payload.type === "AIRCRAFT_UPDATE") {
              // Aircraft feed continues in backend but is intentionally not rendered in map UI.
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

  const handleMapEventClick = (evt: IntelEvent) => {
    setSelectedMapEvent(evt)
  }

  return (
    <>
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex-1 min-h-0 p-2 flex flex-col relative">
          <MapArea
            events={events}
            onEventClick={handleMapEventClick}
            showWeatherOverlay={showWeatherOverlay}
          />
          {selectedMapEvent && (
            <div className="absolute top-5 left-5 z-30 w-[min(420px,calc(100%-2.5rem))] rounded-xl border border-cyan-500/35 bg-[rgba(5,8,14,0.94)] shadow-[0_14px_30px_rgba(0,0,0,0.55)] backdrop-blur-md">
              <div className="flex items-start gap-2 border-b border-white/10 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[10px] font-bold tracking-[0.2em] px-2 py-0.5 rounded border border-white/20 text-white/90">
                      {selectedMapEvent.type}
                    </span>
                    <span className="text-[10px] font-bold tracking-[0.08em] px-2 py-0.5 rounded border border-osint-blue/40 text-osint-blue max-w-[170px] truncate">
                      {selectedMapEvent.source}
                    </span>
                    {selectedMapEvent.confidence ? (
                      <span className="text-[9px] px-2 py-0.5 rounded border border-osint-green/30 text-osint-green">
                        {selectedMapEvent.confidence} {typeof selectedMapEvent.confidence_score === "number" ? `(${selectedMapEvent.confidence_score})` : ""}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-2 text-[12px] leading-relaxed text-[#d7dbea]">
                    {selectedMapEvent.desc.replace(/^\[.+?\]\s*/, "")}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedMapEvent(null)}
                  className="shrink-0 rounded border border-white/15 px-2 py-1 text-[10px] text-white/75 hover:text-white hover:border-white/35"
                >
                  X
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2 p-3 text-[10px]">
                <div className="rounded border border-white/10 bg-black/20 p-2">
                  <p className="mb-1 text-[9px] uppercase tracking-[0.12em] text-osint-green">Observed</p>
                  <p className="text-[#b6d7bf] line-clamp-3">{(selectedMapEvent.observed_facts && selectedMapEvent.observed_facts[0]) || "No direct fact extracted"}</p>
                </div>
                <div className="rounded border border-white/10 bg-black/20 p-2">
                  <p className="mb-1 text-[9px] uppercase tracking-[0.12em] text-osint-amber">Inference</p>
                  <p className="text-[#d6c7a8] line-clamp-3">{(selectedMapEvent.model_inference && selectedMapEvent.model_inference[0]) || "No model inference"}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-y-2 border-t border-white/10 px-4 py-3 text-[10px] text-muted-foreground">
                <p className="truncate">time: {selectedMapEvent.timestamp ?? "--"}</p>
                <p className="text-right truncate">coords: {selectedMapEvent.lat.toFixed(3)}N {selectedMapEvent.lng.toFixed(3)}E</p>
                <p className="truncate">MGRS: {selectedMapEvent.mgrs || "N/A"}</p>
                <p className="truncate">source: {selectedMapEvent.source}</p>
                <p className="text-right truncate">corroboration: {(selectedMapEvent.corroborating_sources?.length ?? 0) > 0 ? selectedMapEvent.corroborating_sources?.length : "single-source"}</p>
                {selectedMapEvent.confidence_reason ? (
                  <p className="col-span-2 truncate text-osint-blue">confidence note: {selectedMapEvent.confidence_reason}</p>
                ) : null}
                {selectedMapEvent.video_assessment ? (
                  <p className="col-span-2 truncate text-osint-green">media: {selectedMapEvent.video_assessment}{selectedMapEvent.video_confidence ? ` (${selectedMapEvent.video_confidence})` : ""}</p>
                ) : null}
              </div>
            </div>
          )}
        </div>
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
          <span className="ml-auto text-[9px] text-muted-foreground tabular-nums">{events.length} items</span>
        </div>

        <div className="px-3 pt-2 pb-1">
          <div className="rounded-lg border border-white/10 bg-black/25 p-2 text-[10px]">
            <div className="flex items-center justify-between mb-1">
              <p className="uppercase tracking-[0.16em] text-osint-amber">Operational Tempo</p>
              <span className={`px-1.5 py-0.5 rounded border text-[9px] ${defcon <= 2 ? "border-osint-red/50 text-osint-red" : defcon <= 3 ? "border-osint-amber/50 text-osint-amber" : "border-osint-blue/40 text-osint-blue"}`}>
                DEFCON {defcon}
              </span>
            </div>
            <p className="text-muted-foreground">Battle rhythm synced to ZULU and theater clocks.</p>
          </div>
        </div>

        <div className="px-3 pt-3 pb-1">
          <AiAnalyst />
        </div>

        <div className="px-3 pb-2 space-y-2">
            <div className="rounded-lg border border-white/10 bg-black/25 p-2">
              <div className="flex items-center justify-between mb-1">
                <p className="text-[9px] uppercase tracking-[0.16em] text-osint-blue">METOC</p>
              <button
                onClick={() => setShowWeatherOverlay((v) => !v)}
                className={`text-[9px] px-1.5 py-0.5 rounded border ${showWeatherOverlay ? "border-osint-green/40 text-osint-green" : "border-white/15 text-muted-foreground"}`}
              >
                {showWeatherOverlay ? "Radar ON" : "Radar OFF"}
              </button>
            </div>
            <div className="grid grid-cols-2 gap-1 text-[10px] text-muted-foreground">
              <p>Wind: <span className="text-[#d4dbe8]">{metoc.windKts} kts</span></p>
              <p className="text-right">Visibility: <span className="text-[#d4dbe8]">{metoc.visibilityKm} km</span></p>
              <p>Ceiling: <span className="text-[#d4dbe8]">{metoc.ceilingFt} ft</span></p>
              <p className="text-right">Condition: <span className="text-[#d4dbe8]">{metoc.condition}</span></p>
              <p className="col-span-2 text-[9px] text-muted-foreground">source: {metoc.source}</p>
            </div>
          </div>

        </div>

        <div className="flex-1 min-h-0 overflow-y-auto osint-feed-scroll">
          <div className="flex flex-col gap-2 p-3">
          </div>
        </div>
      </aside>

      <style>{`
        .osint-feed-scroll {
          scrollbar-width: thin;
          scrollbar-color: rgba(0, 180, 216, 0.55) rgba(255, 255, 255, 0.06);
        }
        .osint-feed-scroll::-webkit-scrollbar {
          width: 8px;
        }
        .osint-feed-scroll::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.04);
          border-left: 1px solid rgba(255, 255, 255, 0.06);
        }
        .osint-feed-scroll::-webkit-scrollbar-thumb {
          background: linear-gradient(180deg, rgba(0, 180, 216, 0.68), rgba(178, 75, 255, 0.5));
          border: 1px solid rgba(0, 180, 216, 0.5);
          border-radius: 999px;
          box-shadow: 0 0 8px rgba(0, 180, 216, 0.35);
        }
        .osint-feed-scroll::-webkit-scrollbar-thumb:hover {
          background: linear-gradient(180deg, rgba(0, 220, 255, 0.78), rgba(178, 75, 255, 0.62));
        }
      `}</style>
    </>
  )
}

export function IntelFeed() { return null }
