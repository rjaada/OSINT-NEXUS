"use client"

import { useEffect, useRef, useState } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import type { IntelEvent } from "./intel-feed"

const DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"

const SATELLITE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    "esri-satellite": {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 18,
    },
  },
  layers: [{ id: "esri-satellite-layer", type: "raster", source: "esri-satellite" }],
}

const TYPE_COLORS: Record<string, string> = {
  CRITICAL: "#b24bff",
  STRIKE:   "#ff1a3c",
  MOVEMENT: "#00b4d8",
  NOTAM:    "#ffa630",
  CLASH:    "#00ff88",
}

// ── Active conflict zones with polygon coordinates ─────────────────────────────
const CONFLICT_ZONES: Array<{
  id: string
  label: string
  color: string
  severity: "critical" | "high" | "medium"
  coordinates: [number, number][]
}> = [
  {
    id: "gaza",
    label: "Gaza Strip",
    color: "#ff1a3c",
    severity: "critical",
    coordinates: [
      [34.187, 31.596], [34.230, 31.592], [34.265, 31.547],
      [34.262, 31.483], [34.245, 31.216], [34.220, 31.215],
      [34.206, 31.308], [34.185, 31.430], [34.187, 31.596],
    ],
  },
  {
    id: "west-bank",
    label: "West Bank",
    color: "#ff1a3c",
    severity: "high",
    coordinates: [
      [35.545, 32.573], [35.565, 32.468], [35.544, 32.391],
      [35.528, 32.223], [35.457, 32.030], [35.402, 31.865],
      [35.354, 31.487], [35.289, 31.487], [35.228, 31.554],
      [35.185, 31.725], [35.165, 31.900], [35.188, 32.012],
      [35.236, 32.197], [35.290, 32.344], [35.369, 32.449],
      [35.434, 32.527], [35.545, 32.573],
    ],
  },
  {
    id: "south-lebanon",
    label: "South Lebanon",
    color: "#ff6b00",
    severity: "high",
    coordinates: [
      [35.100, 33.070], [35.200, 33.090], [35.520, 33.075],
      [35.680, 33.242], [35.780, 33.424], [35.880, 33.490],
      [36.050, 33.490], [36.100, 33.380], [35.900, 33.220],
      [35.750, 33.070], [35.500, 32.950], [35.380, 32.920],
      [35.200, 32.980], [35.100, 33.070],
    ],
  },
  {
    id: "syria-north",
    label: "N. Syria Conflict",
    color: "#ffa630",
    severity: "high",
    coordinates: [
      [36.200, 36.900], [36.800, 37.100], [37.500, 37.050],
      [38.200, 37.000], [38.800, 36.700], [38.500, 36.300],
      [37.800, 36.400], [37.000, 36.500], [36.300, 36.600],
      [36.200, 36.900],
    ],
  },
  {
    id: "syria-east",
    label: "E. Syria / ISIS",
    color: "#b24bff",
    severity: "medium",
    coordinates: [
      [38.800, 36.700], [40.200, 37.200], [41.500, 37.000],
      [41.200, 36.300], [40.500, 36.100], [39.500, 35.800],
      [38.800, 35.900], [38.800, 36.700],
    ],
  },
  {
    id: "yemen",
    label: "Yemen (Houthi)",
    color: "#ff1a3c",
    severity: "critical",
    coordinates: [
      [42.600, 16.400], [43.500, 16.350], [44.300, 15.100],
      [45.400, 14.800], [46.500, 14.500], [48.700, 14.100],
      [49.800, 14.100], [50.500, 15.000], [51.000, 15.800],
      [50.500, 16.500], [49.000, 17.500], [47.000, 18.000],
      [45.500, 18.000], [44.000, 17.500], [43.000, 17.000],
      [42.600, 16.400],
    ],
  },
  {
    id: "iraq-pmf",
    label: "Iraq (PMF Activity)",
    color: "#ffa630",
    severity: "medium",
    coordinates: [
      [42.000, 34.500], [44.000, 35.500], [46.000, 35.000],
      [48.000, 34.000], [48.500, 31.500], [46.500, 30.000],
      [44.000, 29.500], [42.000, 31.000], [42.000, 34.500],
    ],
  },
  {
    id: "red-sea",
    label: "Red Sea (Houthi Strikes)",
    color: "#00b4d8",
    severity: "high",
    coordinates: [
      [37.000, 22.000], [39.000, 21.500], [42.500, 19.000],
      [43.500, 15.000], [42.000, 12.500], [40.000, 13.000],
      [38.000, 15.000], [37.000, 18.000], [37.000, 22.000],
    ],
  },
  {
    id: "bahrain",
    label: "Bahrain (Targeted)",
    color: "#ff1a3c",
    severity: "critical",
    coordinates: [
      [50.350, 26.320], [50.680, 26.320], [50.680, 26.060],
      [50.350, 26.060], [50.350, 26.320],
    ],
  },
  {
    id: "qatar",
    label: "Qatar (Targeted)",
    color: "#ff6b00",
    severity: "high",
    coordinates: [
      [50.750, 26.150], [51.700, 26.150], [51.700, 24.550],
      [50.750, 24.550], [50.750, 26.150],
    ],
  },
  {
    id: "uae-bases",
    label: "UAE (US Bases)",
    color: "#ffa630",
    severity: "medium",
    coordinates: [
      [53.800, 24.800], [56.400, 24.800], [56.400, 22.600],
      [55.200, 22.600], [54.000, 23.200], [53.800, 24.800],
    ],
  },
  {
    id: "saudi-aramco",
    label: "Saudi Arabia (Oil Infrastructure)",
    color: "#ffa630",
    severity: "medium",
    coordinates: [
      [48.500, 27.500], [50.200, 27.500], [50.200, 25.500],
      [49.000, 24.800], [47.500, 25.500], [48.500, 27.500],
    ],
  },
]

function projectPoint(lat: number, lng: number, headingDeg: number, distKm: number) {
  const R = 6371, d = distKm / R, h = (headingDeg * Math.PI) / 180
  const lat1 = (lat * Math.PI) / 180, lng1 = (lng * Math.PI) / 180
  const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(h))
  const lng2 = lng1 + Math.atan2(Math.sin(h) * Math.sin(d) * Math.cos(lat1), Math.cos(d) - Math.sin(lat1) * Math.sin(lat2))
  return [(lng2 * 180) / Math.PI, (lat2 * 180) / Math.PI]
}

function createCircle(lng: number, lat: number, radiusKm: number, points = 48): [number, number][] {
  const coords: [number, number][] = []
  for (let i = 0; i <= points; i++) {
    const pt = projectPoint(lat, lng, (i / points) * 360, radiusKm)
    coords.push([pt[0], pt[1]])
  }
  return coords
}

export function MapArea({ events, onEventClick, showWeatherOverlay = false }: {
  events?: IntelEvent[]
  onEventClick?: (evt: IntelEvent) => void
  showWeatherOverlay?: boolean
}) {
  const containerRef    = useRef<HTMLDivElement>(null)
  const mapRef          = useRef<maplibregl.Map | null>(null)
  const mapReadyRef     = useRef(false)
  const eventMarkersRef = useRef<Record<string, maplibregl.Marker>>({})
  const hoverPopupRef   = useRef<maplibregl.Popup | null>(null)
  const zoneLabelsRef   = useRef<maplibregl.Marker[]>([])
  const overlayIdsRef   = useRef<string[]>([])
  const [isSatellite, setIsSatellite] = useState(false)
  const [mapError, setMapError] = useState<string | null>(null)

  const addCustomLayers = (map: maplibregl.Map) => {
    // ── Conflict zone fills ──────────────────────────────────────────────────
    if (!map.getSource("conflict-zones")) {
      const features = CONFLICT_ZONES.map((z) => ({
        type: "Feature" as const,
        properties: { id: z.id, color: z.color, label: z.label },
        geometry: { type: "Polygon" as const, coordinates: [z.coordinates] },
      }))
      map.addSource("conflict-zones", {
        type: "geojson",
        data: { type: "FeatureCollection", features },
      })
      map.addLayer({
        id: "conflict-zones-fill",
        type: "fill",
        source: "conflict-zones",
        paint: { "fill-color": ["get", "color"], "fill-opacity": 0.12 },
      })
      map.addLayer({
        id: "conflict-zones-stroke",
        type: "line",
        source: "conflict-zones",
        paint: {
          "line-color": ["get", "color"],
          "line-width": 1.5,
          "line-opacity": 0.5,
          "line-dasharray": [4, 3],
        },
      })
    }

    // ── Threat radius for STRIKE/CRITICAL events ────────────────────────────
    if (!map.getSource("threat-radius")) {
      map.addSource("threat-radius", { type: "geojson", data: { type: "FeatureCollection", features: [] } })
      map.addLayer({
        id: "threat-radius-fill", type: "fill", source: "threat-radius",
        paint: { "fill-color": ["get", "color"], "fill-opacity": 0.08 },
      })
      map.addLayer({
        id: "threat-radius-stroke", type: "line", source: "threat-radius",
        paint: { "line-color": ["get", "color"], "line-width": 1.5, "line-opacity": 0.35, "line-dasharray": [6, 4] },
      })
    }

    // ── Heat map (event density) ─────────────────────────────────────────────
    if (!map.getSource("event-heat")) {
      map.addSource("event-heat", { type: "geojson", data: { type: "FeatureCollection", features: [] } })
      map.addLayer({
        id: "event-heat-layer", type: "heatmap", source: "event-heat",
        paint: {
          "heatmap-weight": ["get", "weight"],
          "heatmap-intensity": 0.7,
          "heatmap-radius": 30,
          "heatmap-opacity": 0.45,
          "heatmap-color": [
            "interpolate", ["linear"], ["heatmap-density"],
            0, "rgba(0,0,0,0)", 0.2, "rgba(0,180,216,0.3)", 0.4, "rgba(255,166,48,0.4)",
            0.6, "rgba(255,26,60,0.5)", 0.8, "rgba(178,75,255,0.6)", 1.0, "rgba(255,255,255,0.8)",
          ],
        },
      })
    }

    // ── METOC weather overlay (simulated radar cells) ───────────────────────
    if (!map.getSource("weather-overlay")) {
      const weatherCells = [
        { lng: 35.20, lat: 31.85, intensity: 0.68 },
        { lng: 36.12, lat: 33.10, intensity: 0.54 },
        { lng: 39.30, lat: 34.55, intensity: 0.74 },
        { lng: 44.20, lat: 33.70, intensity: 0.60 },
        { lng: 51.45, lat: 25.35, intensity: 0.49 },
      ].map((x) => ({
        type: "Feature" as const,
        properties: x,
        geometry: { type: "Point" as const, coordinates: [x.lng, x.lat] },
      }))
      map.addSource("weather-overlay", {
        type: "geojson",
        data: { type: "FeatureCollection", features: weatherCells },
      })
      map.addLayer({
        id: "weather-overlay-layer",
        type: "circle",
        source: "weather-overlay",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "intensity"], 0.3, 18, 0.9, 44],
          "circle-color": [
            "interpolate",
            ["linear"],
            ["get", "intensity"],
            0.3, "rgba(0,180,216,0.12)",
            0.6, "rgba(0,180,216,0.22)",
            0.8, "rgba(255,166,48,0.28)",
            0.9, "rgba(255,26,60,0.32)",
          ],
          "circle-stroke-width": 1,
          "circle-stroke-color": "rgba(0,180,216,0.28)",
          "circle-opacity": 0.9,
        },
        layout: { visibility: "none" },
      })
    }

    // ── Zone label markers ───────────────────────────────────────────────────
    zoneLabelsRef.current.forEach((m) => m.remove())
    zoneLabelsRef.current = []
    CONFLICT_ZONES.forEach((zone) => {
      // Centroid of polygon
      const coords = zone.coordinates
      const cx = coords.reduce((s, c) => s + c[0], 0) / coords.length
      const cy = coords.reduce((s, c) => s + c[1], 0) / coords.length

      const el = document.createElement("div")
      el.style.cssText = `
        font-family: monospace;
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 0.12em;
        color: ${zone.color};
        text-shadow: 0 0 8px ${zone.color}, 0 1px 2px rgba(0,0,0,0.9);
        pointer-events: none;
        white-space: nowrap;
        text-transform: uppercase;
      `
      el.textContent = zone.label
      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([cx, cy])
        .addTo(map)
      zoneLabelsRef.current.push(marker)
    })
  }

  const loadOverlayFiles = async (map: maplibregl.Map) => {
    try {
      overlayIdsRef.current.forEach((id) => {
        if (map.getLayer(`${id}-line`)) map.removeLayer(`${id}-line`)
        if (map.getLayer(`${id}-fill`)) map.removeLayer(`${id}-fill`)
        if (map.getSource(id)) map.removeSource(id)
      })
      overlayIdsRef.current = []
      const res = await fetch("http://localhost:8000/api/v2/overlays", { cache: "no-store" })
      if (!res.ok) return
      const data = await res.json()
      const items = Array.isArray(data?.items) ? data.items : []
      items.forEach((ov: { id?: string; source?: unknown }) => {
        const id = String(ov?.id || "").trim()
        if (!id || !ov?.source) return
        if (map.getSource(id)) return
        map.addSource(id, { type: "geojson", data: ov.source as any })
        map.addLayer({
          id: `${id}-fill`,
          type: "fill",
          source: id,
          paint: {
            "fill-color": "rgba(255,166,48,0.12)",
            "fill-outline-color": "rgba(255,166,48,0.48)",
          },
        })
        map.addLayer({
          id: `${id}-line`,
          type: "line",
          source: id,
          paint: {
            "line-color": "rgba(255,166,48,0.62)",
            "line-width": 1.8,
            "line-dasharray": [5, 3],
          },
        })
        overlayIdsRef.current.push(id)
      })
    } catch (_) {
      // Overlay files are optional
    }
  }

  // ── Init map ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return
    try {
      const map = new maplibregl.Map({
        container: containerRef.current,
        style: DARK_STYLE,
        center: [40.0, 29.0],
        zoom: 4.2,
        pitch: 0,
        attributionControl: false,
      })
      map.on("load", () => {
        mapReadyRef.current = true
        setMapError(null)
        addCustomLayers(map)
        void loadOverlayFiles(map)
      })
      map.on("error", (evt) => {
        const msg = String(evt?.error ?? "")
        if (msg.toLowerCase().includes("webgl")) {
          setMapError("Map unavailable: WebGL is not supported in this browser/session.")
        }
      })
      mapRef.current = map
    } catch (err) {
      setMapError(`Map initialization failed: ${err instanceof Error ? err.message : String(err)}`)
      mapReadyRef.current = false
      mapRef.current = null
    }
    return () => {
      mapReadyRef.current = false
      mapRef.current?.remove()
      mapRef.current = null
    }
  }, [])

  // ── Satellite toggle ──────────────────────────────────────────────────────
  const toggleSatellite = () => {
    const map = mapRef.current
    if (!map) return

    Object.values(eventMarkersRef.current).forEach((m) => m.remove())
    eventMarkersRef.current = {}
    hoverPopupRef.current?.remove()
    hoverPopupRef.current = null
    zoneLabelsRef.current.forEach((m) => m.remove())
    zoneLabelsRef.current = []

    const next = !isSatellite
    setIsSatellite(next)
    map.setStyle(next ? SATELLITE_STYLE : DARK_STYLE)
    map.once("style.load", () => {
      addCustomLayers(map)
      void loadOverlayFiles(map)
    })
  }

  // ── Event markers + heat + threat radius ─────────────────────────────────
  useEffect(() => {
    if (!mapReadyRef.current || !mapRef.current || !events) return
    const map = mapRef.current

    const heatFeatures = events.map((evt) => ({
      type: "Feature" as const,
      properties: { weight: evt.type === "CRITICAL" ? 3 : evt.type === "STRIKE" ? 2 : 1 },
      geometry: { type: "Point" as const, coordinates: [evt.lng, evt.lat] },
    }))
    const heatSrc = map.getSource("event-heat") as maplibregl.GeoJSONSource | undefined
    heatSrc?.setData({ type: "FeatureCollection", features: heatFeatures })

    const threatFeatures = events
      .filter((e) => e.type === "CRITICAL" || e.type === "STRIKE")
      .map((evt) => ({
        type: "Feature" as const,
        properties: { color: TYPE_COLORS[evt.type] ?? "#ff1a3c" },
        geometry: { type: "Polygon" as const, coordinates: [createCircle(evt.lng, evt.lat, evt.type === "CRITICAL" ? 60 : 30)] },
      }))
    const threatSrc = map.getSource("threat-radius") as maplibregl.GeoJSONSource | undefined
    threatSrc?.setData({ type: "FeatureCollection", features: threatFeatures })

    // Event dot markers 
    const currentEventIds = new Set(events.map(e => e.id))
    hoverPopupRef.current?.remove()
    hoverPopupRef.current = null

    // 1. Remove markers that are no longer in our events array (i.e. we switched languages)
    Object.keys(eventMarkersRef.current).forEach(id => {
      if (!currentEventIds.has(id)) {
        eventMarkersRef.current[id].remove()
        delete eventMarkersRef.current[id]
      }
    })

    // 2. Add new markers
    events.forEach((evt) => {
      if (eventMarkersRef.current[evt.id]) return
      const color = TYPE_COLORS[evt.type] ?? "#b24bff"
      const isCritical = evt.type === "CRITICAL"
      const size = isCritical ? 13 : 8
      const el = document.createElement("div")
      const symbolKind = evt.type === "STRIKE" || evt.type === "CRITICAL" ? "hostile" : evt.type === "MOVEMENT" ? "friendly" : "unknown"
      el.style.cssText = `
        width:${size}px;height:${size}px;cursor:${onEventClick ? "pointer" : "default"};
        box-shadow:0 0 ${isCritical ? 14 : 7}px ${isCritical ? 3 : 2}px ${color}99;
        border: 1px solid ${color};
        background:${color};
      `
      if (symbolKind === "hostile") {
        el.style.transform = "rotate(45deg)"
        el.style.borderRadius = "2px"
      } else if (symbolKind === "friendly") {
        el.style.borderRadius = "2px"
        el.style.width = `${Math.max(8, size + 2)}px`
        el.style.height = `${Math.max(6, size - 1)}px`
        el.style.background = "rgba(0,180,216,0.85)"
        el.style.border = "1px solid rgba(0,180,216,1)"
      } else {
        el.style.borderRadius = "999px"
      }
      if (!document.getElementById("osint-kf")) {
        const s = document.createElement("style"); s.id = "osint-kf"
        s.textContent = `
          @keyframes osintPulse { 0%,100%{opacity:1} 50%{opacity:0.6} }
          .maplibregl-popup.osint-hover-popup .maplibregl-popup-content {
            background: transparent;
            border: 0;
            box-shadow: none;
            padding: 0;
          }
          .maplibregl-popup.osint-hover-popup .maplibregl-popup-tip {
            border-top-color: rgba(5, 10, 18, 0.96);
            border-bottom-color: rgba(5, 10, 18, 0.96);
          }
        `
        document.head.appendChild(s)
      }
      el.style.animation = "osintPulse 2s ease-in-out infinite"

      const source = evt.desc.match(/^\[(.+?)\]/)?.[1] ?? evt.source
      const ts = evt.timestamp
        ? evt.timestamp.replace("T", " ").replace("+00:00", "Z").slice(0, 19)
        : "live"
      const popup = new maplibregl.Popup({
        offset: 14,
        closeButton: false,
        closeOnClick: false,
        maxWidth: "320px",
        className: "osint-hover-popup",
      })
        .setHTML(`
          <div style="
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace;
            width: 296px;
            color:#dbe5ff;
            background: linear-gradient(180deg, rgba(8,12,20,0.96), rgba(4,7,12,0.98));
            border:1px solid rgba(0,180,216,0.32);
            border-radius:12px;
            padding:10px 11px;
            box-shadow: 0 10px 24px rgba(0,0,0,0.55), inset 0 0 0 1px rgba(255,255,255,0.03);
            backdrop-filter: blur(6px);
          ">
            <div style="display:flex;gap:6px;align-items:center;margin-bottom:8px">
              <span style="
                display:inline-block;
                color:${color};
                border:1px solid ${color}66;
                background:${color}1A;
                border-radius:999px;
                font-size:9px;
                font-weight:700;
                letter-spacing:.14em;
                text-transform:uppercase;
                padding:2px 7px;
              ">${evt.type}</span>
              <span style="
                display:inline-block;
                color:#7ee7ff;
                border:1px solid rgba(0,180,216,0.42);
                background:rgba(0,180,216,0.10);
                border-radius:999px;
                font-size:9px;
                font-weight:700;
                letter-spacing:.08em;
                padding:2px 7px;
                max-width:176px;
                white-space:nowrap;
                overflow:hidden;
                text-overflow:ellipsis;
              ">${source}</span>
            </div>
            <div style="
              color:#e6ebff;
              line-height:1.5;
              font-size:11px;
              margin-bottom:8px;
              max-height:72px;
              overflow:hidden;
            ">${evt.desc.replace(/^\[.+?\]\s*/, "").slice(0, 220)}</div>
            <div style="
              display:flex;
              justify-content:space-between;
              align-items:center;
              border-top:1px solid rgba(255,255,255,0.08);
              padding-top:7px;
              font-size:9px;
              letter-spacing:.06em;
              color:#8aa0bd;
            ">
              <span>${evt.lat.toFixed(3)}°, ${evt.lng.toFixed(3)}°</span>
              <span>${ts}</span>
            </div>
          </div>
        `)

      el.addEventListener("mouseenter", () => {
        hoverPopupRef.current?.remove()
        popup.setLngLat([evt.lng, evt.lat]).addTo(map)
        hoverPopupRef.current = popup
      })

      el.addEventListener("mouseleave", () => {
        if (hoverPopupRef.current === popup) {
          popup.remove()
          hoverPopupRef.current = null
        }
      })

      el.addEventListener("click", (event) => {
        event.preventDefault()
        event.stopPropagation()
        onEventClick?.(evt)
      })

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([evt.lng, evt.lat])
        .addTo(map)
      eventMarkersRef.current[evt.id] = marker
    })
  }, [events, isSatellite, onEventClick])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReadyRef.current) return
    if (map.getLayer("weather-overlay-layer")) {
      map.setLayoutProperty("weather-overlay-layer", "visibility", showWeatherOverlay ? "visible" : "none")
    }
  }, [showWeatherOverlay, isSatellite])

  const evtCount  = events?.length ?? 0
  const strikeCnt = events?.filter((e) => e.type === "STRIKE" || e.type === "CRITICAL").length ?? 0

  return (
    <div className="relative flex-1 overflow-hidden" style={{ minHeight: 0 }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      {mapError && (
        <div
          className="absolute inset-0 z-30 flex items-center justify-center px-6 text-center"
          style={{ background: "rgba(5,5,10,0.92)", color: "#ffa630" }}
        >
          <div className="max-w-lg">
            <div className="text-[11px] uppercase tracking-[0.18em] mb-2 text-[#e0e0e8]">Map Error</div>
            <div className="text-sm leading-relaxed">{mapError}</div>
          </div>
        </div>
      )}

      {/* Scanline (dark mode only) */}
      {!isSatellite && (
        <div className="absolute inset-0 pointer-events-none" style={{
          background: "repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.03) 2px,rgba(0,0,0,0.03) 4px)", zIndex: 2,
        }} />
      )}

      {/* Satellite toggle */}
      <button
        onClick={toggleSatellite}
        className="absolute top-2 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-3 py-1.5 rounded-lg text-[9px] font-bold tracking-widest uppercase transition-all hover:scale-105"
        style={{
          background: "rgba(5,5,10,0.92)",
          border: `1px solid ${isSatellite ? "rgba(0,180,216,0.5)" : "rgba(255,255,255,0.1)"}`,
          color: isSatellite ? "#00b4d8" : "#707080",
          backdropFilter: "blur(12px)",
        }}
      >
        <span>{isSatellite ? "🛰" : "🗺"}</span>
        <span>{isSatellite ? "SATELLITE" : "DARK MAP"}</span>
      </button>

      {/* HUD top-right */}
      <div className="absolute top-2 right-2 text-[9px] tracking-wider pointer-events-none z-10 font-mono text-right leading-relaxed">
        <div className={isSatellite ? "text-white/70" : "text-green-400/60"}>{evtCount} EVENTS TRACKED</div>
        {strikeCnt > 0 && <div className="text-[#ff1a3c] font-bold" style={{ animation: "osintPulse 1.5s infinite" }}>⚠ {strikeCnt} ACTIVE STRIKE/CRITICAL</div>}
      </div>

      {/* Legend bottom-left */}
      <div
        className="absolute z-10 rounded-lg px-3 py-2 flex flex-col gap-1.5 pointer-events-none"
        style={{ background: "rgba(5,5,10,0.88)", border: "1px solid rgba(255,255,255,0.08)", bottom: "28px", left: "10px" }}
      >
        <div className="text-[7px] text-muted-foreground/50 uppercase tracking-widest mb-0.5">Conflict Zones</div>
        {CONFLICT_ZONES.slice(0, 6).map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2">
            <div className="w-2.5 h-1 rounded-sm shrink-0 opacity-80" style={{ background: color }} />
            <span className="text-[8px] text-muted-foreground tracking-wider">{label}</span>
          </div>
        ))}
        <div className="text-[7px] text-muted-foreground/40 mt-1 border-t border-white/5 pt-1">
          ● Events · ◌ Strike radius
        </div>
        <div className="text-[7px] text-muted-foreground/40">
          {showWeatherOverlay ? "◉ Weather radar overlay enabled" : "◉ Weather radar overlay disabled"}
        </div>
      </div>

      {/* Bottom-right label */}
      <div className="absolute bottom-2 right-2 text-[9px] text-green-400/30 tracking-wider pointer-events-none z-10 font-mono">
        {isSatellite ? "ESRI WORLD IMAGERY" : "CONFLICT ZONES OVERLAID"}
      </div>
    </div>
  )
}
