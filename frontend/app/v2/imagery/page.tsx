"use client"

import { useEffect, useState, useCallback } from "react"
import { useSearchParams } from "next/navigation"
import { Suspense } from "react"
import { TopBar } from "@/components/dashboard/top-bar"
import { CommandNav } from "@/components/dashboard/command-nav"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

interface Scene {
  id: string
  datetime: string
  cloud_cover: number
  platform: string
  thumbnail: string | null
  bbox: number[] | null
}

interface ImageryResult {
  lat: number
  lon: number
  event_time: string
  before: Scene | null
  after: Scene | null
  before_scenes_found: number
  after_scenes_found: number
  change_score: number
  flags: string[]
  coverage_km: number
  analyzed_at: string
  method: string
  note: string
}

function scoreColor(s: number): string {
  if (s >= 0.6) return "#ef4444"
  if (s >= 0.35) return "#f59e0b"
  return "#22c55e"
}

function scoreLabel(s: number): string {
  if (s >= 0.6) return "SIGNIFICANT CHANGE"
  if (s >= 0.35) return "REVIEW RECOMMENDED"
  return "NO SIGNIFICANT CHANGE"
}

function fmtDt(iso: string): string {
  try { return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) }
  catch { return iso }
}

function ImageryContent() {
  const params = useSearchParams()
  const [lat, setLat] = useState(params.get("lat") ?? "")
  const [lng, setLng] = useState(params.get("lng") ?? "")
  const [ts, setTs] = useState(params.get("ts") ?? new Date().toISOString().slice(0, 16))
  const [km, setKm] = useState("3")
  const [result, setResult] = useState<ImageryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [recentFirms, setRecentFirms] = useState<Array<{ id: string; lat: number; lng: number; timestamp: string; desc: string }>>([])

  // Auto-run if URL params are set
  useEffect(() => {
    if (params.get("lat") && params.get("lng")) void run(
      params.get("lat")!, params.get("lng")!, params.get("ts") ?? new Date().toISOString(), "3"
    )
  }, [])

  // Load recent FIRMS events for quick-select
  useEffect(() => {
    fetch(`${API_BASE}/api/v2/events?limit=200`, { credentials: "include" })
      .then(r => r.ok ? r.json() : [])
      .then((evts: Array<{ id: string; source?: string; lat?: number; lng?: number; timestamp?: string; desc?: string }>) => {
        const firms = evts.filter(e => (e.source ?? "").toLowerCase().includes("firm") || (e.source ?? "").toLowerCase().includes("fire"))
        setRecentFirms(firms.slice(0, 15).map(e => ({
          id: e.id,
          lat: e.lat ?? 0,
          lng: e.lng ?? 0,
          timestamp: e.timestamp ?? new Date().toISOString(),
          desc: e.desc ?? "",
        })))
      })
      .catch(() => {})
  }, [])

  const run = useCallback(async (latV: string, lngV: string, tsV: string, kmV: string) => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const url = `${API_BASE}/api/v2/imagery/check?lat=${latV}&lng=${lngV}&timestamp=${encodeURIComponent(tsV)}&km=${kmV}`
      const r = await fetch(url, { credentials: "include" })
      if (!r.ok) throw new Error(`${r.status}`)
      setResult(await r.json())
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    void run(lat, lng, ts, km)
  }

  const selectFirms = (evt: { lat: number; lng: number; timestamp: string }) => {
    setLat(String(evt.lat))
    setLng(String(evt.lng))
    setTs(evt.timestamp.slice(0, 16))
    void run(String(evt.lat), String(evt.lng), evt.timestamp, km)
  }

  return (
    <div className="flex flex-col h-screen bg-[#05080e] text-white font-mono overflow-hidden">
      <TopBar />
      <CommandNav />

      <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 shrink-0">
        <span className="text-[9px] tracking-[0.2em] text-white/30 uppercase">Sentinel-2 Imagery Change Detection</span>
        <span className="text-[9px] text-white/20">Copernicus Data Space · No auth required · 10m resolution · 5-day revisit</span>
      </div>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left panel: form + FIRMS events */}
        <div className="w-72 border-r border-white/10 flex flex-col overflow-hidden shrink-0">
          {/* Query form */}
          <form onSubmit={handleSubmit} className="px-4 py-4 border-b border-white/10 flex flex-col gap-3">
            <div className="text-[8px] tracking-widest text-white/25 uppercase">Coordinate Query</div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[7px] text-white/25 uppercase block mb-0.5">Latitude</label>
                <input
                  type="number" step="any" value={lat} onChange={e => setLat(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-[9px] text-white focus:outline-none focus:border-white/25"
                  placeholder="31.50"
                />
              </div>
              <div>
                <label className="text-[7px] text-white/25 uppercase block mb-0.5">Longitude</label>
                <input
                  type="number" step="any" value={lng} onChange={e => setLng(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-[9px] text-white focus:outline-none focus:border-white/25"
                  placeholder="34.46"
                />
              </div>
            </div>
            <div>
              <label className="text-[7px] text-white/25 uppercase block mb-0.5">Event Time</label>
              <input
                type="datetime-local" value={ts} onChange={e => setTs(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-[9px] text-white focus:outline-none focus:border-white/25"
              />
            </div>
            <div>
              <label className="text-[7px] text-white/25 uppercase block mb-0.5">Search radius (km)</label>
              <select value={km} onChange={e => setKm(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-[9px] text-white focus:outline-none">
                <option value="1">1 km</option>
                <option value="2">2 km</option>
                <option value="3">3 km</option>
                <option value="5">5 km</option>
                <option value="10">10 km</option>
              </select>
            </div>
            <button
              type="submit" disabled={!lat || !lng || loading}
              className="py-1.5 rounded border border-blue-400/40 bg-blue-400/10 text-blue-400 text-[9px] tracking-widest uppercase hover:bg-blue-400/20 disabled:opacity-40 transition-colors"
            >
              {loading ? "QUERYING STAC..." : "RUN ANALYSIS"}
            </button>
          </form>

          {/* Recent FIRMS events */}
          <div className="flex-1 overflow-y-auto px-4 py-3">
            <div className="text-[8px] tracking-widest text-white/25 uppercase mb-2">
              Recent FIRMS Events ({recentFirms.length})
            </div>
            {recentFirms.length === 0 && (
              <div className="text-[8px] text-white/15">No fire events in recent feed</div>
            )}
            {recentFirms.map(evt => (
              <div
                key={evt.id}
                onClick={() => selectFirms(evt)}
                className="mb-2 p-2 rounded border border-white/8 bg-white/2 cursor-pointer hover:border-orange-400/30 hover:bg-orange-400/5 transition-all"
              >
                <div className="text-[8px] text-white/50 line-clamp-2 leading-snug mb-1">{evt.desc || "FIRMS fire detection"}</div>
                <div className="text-[7px] text-white/25">{evt.lat.toFixed(3)}, {evt.lng.toFixed(3)} · {fmtDt(evt.timestamp)}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Main: results */}
        <div className="flex-1 overflow-y-auto p-6">
          {!result && !loading && !error && (
            <div className="flex flex-col items-center justify-center h-full text-white/15 text-xs gap-2">
              <div className="tracking-widest uppercase">Select a FIRMS event or enter coordinates</div>
              <div className="text-[10px]">Sentinel-2 provides 10m resolution imagery every 5 days</div>
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center h-full text-white/30 text-xs tracking-widest">
              QUERYING COPERNICUS DATA SPACE STAC...
            </div>
          )}

          {error && (
            <div className="flex items-center justify-center h-full text-red-400 text-xs">
              ERROR: {error}
            </div>
          )}

          {result && (
            <div className="max-w-3xl mx-auto">
              {/* Header */}
              <div className="flex items-start justify-between mb-6">
                <div>
                  <div className="text-[9px] text-white/30 uppercase tracking-widest mb-1">Analysis Result</div>
                  <div className="text-sm font-bold">{result.lat.toFixed(4)}, {result.lon.toFixed(4)}</div>
                  <div className="text-[9px] text-white/40 mt-0.5">Event: {fmtDt(result.event_time)} · {result.coverage_km}km radius</div>
                </div>
                <div className="text-right">
                  <div
                    className="text-[10px] font-bold tracking-wider px-3 py-1.5 rounded border mb-1"
                    style={{ color: scoreColor(result.change_score), borderColor: scoreColor(result.change_score) + "40", background: scoreColor(result.change_score) + "10" }}
                  >
                    {scoreLabel(result.change_score)}
                  </div>
                  <div className="text-[9px] text-white/30">Change score: {(result.change_score * 100).toFixed(0)}%</div>
                </div>
              </div>

              {/* Change score bar */}
              <div className="mb-6">
                <div className="flex items-center gap-3 mb-1">
                  <div className="text-[8px] text-white/30 uppercase tracking-wider w-16">Change</div>
                  <div className="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${result.change_score * 100}%`, background: scoreColor(result.change_score) }}
                    />
                  </div>
                  <div className="text-[9px]" style={{ color: scoreColor(result.change_score) }}>
                    {(result.change_score * 100).toFixed(0)}%
                  </div>
                </div>
              </div>

              {/* Flags */}
              <div className="flex flex-wrap gap-2 mb-6">
                {result.flags.map(flag => (
                  <span
                    key={flag}
                    className="px-2 py-0.5 rounded border text-[8px] tracking-wider font-bold"
                    style={{
                      color: flag.includes("SIGNIFICANT") || flag.includes("SMOKE") ? "#ef4444" : flag.includes("REVIEW") ? "#f59e0b" : "#6b7280",
                      borderColor: flag.includes("SIGNIFICANT") || flag.includes("SMOKE") ? "#ef444440" : flag.includes("REVIEW") ? "#f59e0b40" : "#6b728040",
                      background: flag.includes("SIGNIFICANT") || flag.includes("SMOKE") ? "#ef444410" : flag.includes("REVIEW") ? "#f59e0b10" : "transparent",
                    }}
                  >
                    {flag.replace(/_/g, " ")}
                  </span>
                ))}
              </div>

              {/* Before / After thumbnails */}
              <div className="grid grid-cols-2 gap-4 mb-6">
                {["before", "after"].map(period => {
                  const scene = period === "before" ? result.before : result.after
                  const count = period === "before" ? result.before_scenes_found : result.after_scenes_found
                  const label = period === "before" ? "BEFORE (baseline)" : "AFTER (post-event)"
                  const borderCol = period === "after" && result.change_score >= 0.35 ? scoreColor(result.change_score) : "rgba(255,255,255,0.1)"
                  return (
                    <div key={period} className="rounded border overflow-hidden" style={{ borderColor: borderCol }}>
                      <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between">
                        <span className="text-[8px] tracking-wider text-white/40 uppercase">{label}</span>
                        <span className="text-[7px] text-white/20">{count} scene{count !== 1 ? "s" : ""} found</span>
                      </div>
                      {scene ? (
                        <>
                          {scene.thumbnail ? (
                            <div className="relative bg-black">
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={scene.thumbnail}
                                alt={`${period} scene`}
                                className="w-full object-cover"
                                style={{ maxHeight: 200 }}
                                onError={e => { (e.target as HTMLImageElement).style.display = "none" }}
                              />
                            </div>
                          ) : (
                            <div className="h-40 bg-white/3 flex items-center justify-center text-[8px] text-white/20">
                              Thumbnail not available
                            </div>
                          )}
                          <div className="px-3 py-2 bg-white/2">
                            <div className="text-[8px] text-white/40 mb-0.5">{fmtDt(scene.datetime)}</div>
                            <div className="text-[7px] text-white/25">Cloud: {scene.cloud_cover}% · {scene.platform}</div>
                            <div className="text-[7px] text-white/15 truncate mt-0.5">{scene.id}</div>
                          </div>
                        </>
                      ) : (
                        <div className="h-40 flex items-center justify-center text-[8px] text-white/20 flex-col gap-1">
                          <span>No scene available</span>
                          {period === "after" && <span className="text-[7px] text-white/10">Check back in 1–5 days</span>}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              {/* Method note */}
              <div className="text-[8px] text-white/15 leading-relaxed border-t border-white/8 pt-4">
                <span className="text-white/25 uppercase tracking-wider">Method:</span> {result.note}<br />
                Analyzed: {fmtDt(result.analyzed_at)} · Source: Copernicus Data Space STAC (ESA Sentinel-2)
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ImageryPage() {
  return (
    <Suspense fallback={
      <div className="flex flex-col h-screen bg-[#05080e]">
        <TopBar /><CommandNav />
        <div className="flex-1 flex items-center justify-center text-white/30 font-mono text-xs">LOADING...</div>
      </div>
    }>
      <ImageryContent />
    </Suspense>
  )
}
