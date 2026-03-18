/**
 * InteractiveMap — dotted SVG world map with:
 * 1. CSS-animated dot flicker (scanning effect across all map dots)
 * 2. Live backend heatmap — events fetched from /api/v2/events, clustered by proximity
 * 3. Static conflict-zone hotspots with hover tooltips
 */

// @ts-ignore
import mapSvgContent from "../../../map/public/map-dark.svg?raw";
import { useState, useEffect, useRef } from "react";

interface Zone {
  id: string;
  num: string;
  name: string;
  region: string;
  status: "ACTIVE" | "MONITORING";
  description: string;
  coords: string;
  lat: number;
  lon: number;
}

interface HeatCluster {
  lat: number;
  lon: number;
  count: number;
}

interface BackendEvent {
  lat?: number | null;
  lon?: number | null;
  latitude?: number | null;
  longitude?: number | null;
}

const ZONES: Zone[] = [
  {
    id: "gaza",
    num: "01",
    name: "GAZA STRIP",
    region: "Palestine · Israel",
    status: "ACTIVE",
    description: "Ongoing conflict. Red Alert system, Telegram channels and satellite imagery. Primary intelligence focus zone.",
    coords: "31.3547° N · 34.3088° E",
    lat: 31.35,
    lon: 34.31,
  },
  {
    id: "israel",
    num: "02",
    name: "ISRAEL",
    region: "Middle East",
    status: "ACTIVE",
    description: "Direct military exchanges with Iran. Northern border, West Bank and Red Sea monitoring. Strike events correlated across feeds.",
    coords: "31.0461° N · 34.8516° E",
    lat: 31.5,
    lon: 35.2,
  },
  {
    id: "iran",
    num: "03",
    name: "IRAN",
    region: "Middle East",
    status: "ACTIVE",
    description: "Ballistic missile and drone launch monitoring. Strait of Hormuz vessel tracking. Gold and oil market signal correlation.",
    coords: "32.4279° N · 53.6880° E",
    lat: 32.43,
    lon: 53.69,
  },
  {
    id: "lebanon",
    num: "04",
    name: "LEBANON",
    region: "Middle East",
    status: "MONITORING",
    description: "Post-ceasefire posture monitoring. Southern buffer zone activity cross-referenced with IDF movement and diplomatic feeds.",
    coords: "33.8547° N · 35.8623° E",
    lat: 33.85,
    lon: 35.86,
  },
];

function toPercent(lat: number, lon: number) {
  return {
    x: ((lon + 180) / 360) * 100,
    y: ((85 - lat) / 145) * 100,
  };
}

/** Cluster events within ~3° radius */
function clusterEvents(events: BackendEvent[]): HeatCluster[] {
  const clusters: HeatCluster[] = [];
  for (const evt of events) {
    const lat = evt.lat ?? evt.latitude;
    const lon = evt.lon ?? evt.longitude;
    if (lat == null || lon == null || isNaN(lat) || isNaN(lon)) continue;
    const existing = clusters.find(
      (c) => Math.abs(c.lat - lat) < 3 && Math.abs(c.lon - lon) < 3
    );
    if (existing) {
      existing.lat = (existing.lat * existing.count + lat) / (existing.count + 1);
      existing.lon = (existing.lon * existing.count + lon) / (existing.count + 1);
      existing.count++;
    } else {
      clusters.push({ lat, lon, count: 1 });
    }
  }
  return clusters;
}

/** Color + size by event density */
function heatStyle(count: number): { color: string; size: number; opacity: number } {
  if (count >= 20) return { color: "#EF4444", size: 14, opacity: 0.85 };
  if (count >= 10) return { color: "#F97316", size: 11, opacity: 0.75 };
  if (count >= 5)  return { color: "#F59E0B", size: 9,  opacity: 0.65 };
  if (count >= 2)  return { color: "#22D3EE", size: 7,  opacity: 0.55 };
  return               { color: "#22D3EE", size: 5,  opacity: 0.4  };
}

// CSS injected into the SVG container to animate map dots
const DOT_ANIMATION_CSS = `
  #map-svg svg circle {
    transition: opacity 0.4s ease, fill 0.4s ease;
  }
  @keyframes dotPulse {
    0%, 100% { opacity: 0.18; }
    50%       { opacity: 0.85; fill: #22d3ee; }
  }
  #map-svg svg circle:nth-child(7n+1)  { animation: dotPulse 4.1s ease-in-out infinite; animation-delay: 0.0s; }
  #map-svg svg circle:nth-child(7n+2)  { animation: dotPulse 3.7s ease-in-out infinite; animation-delay: 0.6s; }
  #map-svg svg circle:nth-child(7n+3)  { animation: dotPulse 5.2s ease-in-out infinite; animation-delay: 1.1s; }
  #map-svg svg circle:nth-child(7n+4)  { animation: dotPulse 4.6s ease-in-out infinite; animation-delay: 1.8s; }
  #map-svg svg circle:nth-child(7n+5)  { animation: dotPulse 3.3s ease-in-out infinite; animation-delay: 0.4s; }
  #map-svg svg circle:nth-child(7n+6)  { animation: dotPulse 5.8s ease-in-out infinite; animation-delay: 2.2s; }
  #map-svg svg circle:nth-child(7n+0)  { animation: dotPulse 4.4s ease-in-out infinite; animation-delay: 1.5s; }
  #map-svg svg circle:nth-child(13n+3) { animation: dotPulse 2.9s ease-in-out infinite; animation-delay: 0.9s; }
  #map-svg svg circle:nth-child(13n+7) { animation: dotPulse 3.5s ease-in-out infinite; animation-delay: 1.3s; }
`;

export default function InteractiveMap() {
  const [active, setActive] = useState<string | null>(null);
  const [clusters, setClusters] = useState<HeatCluster[]>([]);
  const [eventTotal, setEventTotal] = useState(0);
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;

    fetch("/api/v2/events?limit=500", { credentials: "include" })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (!data) return;
        const events: BackendEvent[] = Array.isArray(data)
          ? data
          : Array.isArray(data?.events)
          ? data.events
          : [];
        const clustered = clusterEvents(events);
        setClusters(clustered);
        setEventTotal(events.length);
      })
      .catch(() => {});
  }, []);

  return (
    <div className="relative w-full select-none" style={{ userSelect: "none" }}>
      {/* Inject dot animation CSS */}
      <style>{DOT_ANIMATION_CSS}</style>

      {/* ── Raw SVG dot map ── */}
      {mapSvgContent ? (
        <div
          id="map-svg"
          className="w-full max-w-[1000px] mx-auto opacity-80 mix-blend-screen overflow-hidden"
          style={{ aspectRatio: "1138 / 640" }}
          dangerouslySetInnerHTML={{ __html: mapSvgContent }}
        />
      ) : (
        <div className="w-full h-[400px] border border-white/10 flex items-center justify-center text-white/30 text-[10px] tracking-[0.3em] uppercase">
          Map Module Offline
        </div>
      )}

      {/* ── Overlay (heatmap + hotspots) ── */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ maxWidth: "1000px", margin: "0 auto", left: 0, right: 0 }}
      >
        {/* Heat clusters from live events */}
        {clusters.map((c, i) => {
          const { x, y } = toPercent(c.lat, c.lon);
          const { color, size, opacity } = heatStyle(c.count);
          return (
            <div
              key={i}
              className="absolute"
              style={{
                left: `${x}%`,
                top: `${y}%`,
                transform: "translate(-50%, -50%)",
                pointerEvents: "none",
              }}
            >
              {/* Outer glow */}
              <span
                className="absolute rounded-full"
                style={{
                  width: size * 2.5,
                  height: size * 2.5,
                  top: "50%", left: "50%",
                  transform: "translate(-50%, -50%)",
                  background: `radial-gradient(circle, ${color}55 0%, transparent 70%)`,
                }}
              />
              {/* Core */}
              <span
                className="relative block rounded-full"
                style={{
                  width: size,
                  height: size,
                  background: color,
                  opacity,
                  boxShadow: `0 0 ${size * 1.2}px ${color}`,
                }}
              />
            </div>
          );
        })}

        {/* Zone hotspots */}
        {ZONES.map((zone) => {
          const { x, y } = toPercent(zone.lat, zone.lon);
          const isActive = active === zone.id;
          const color = zone.status === "ACTIVE" ? "#EF4444" : "#F59E0B";

          return (
            <div
              key={zone.id}
              className="absolute pointer-events-auto cursor-pointer"
              style={{ left: `${x}%`, top: `${y}%`, transform: "translate(-50%, -50%)" }}
              onMouseEnter={() => setActive(zone.id)}
              onMouseLeave={() => setActive(null)}
            >
              <span className="absolute rounded-full animate-ping" style={{ width: 28, height: 28, top: "50%", left: "50%", transform: "translate(-50%,-50%)", background: color, opacity: isActive ? 0.35 : 0.2, animationDuration: "1.8s" }} />
              <span className="absolute rounded-full animate-ping" style={{ width: 18, height: 18, top: "50%", left: "50%", transform: "translate(-50%,-50%)", background: color, opacity: isActive ? 0.5 : 0.3, animationDuration: "1.2s", animationDelay: "0.3s" }} />
              <span className="relative block rounded-full transition-transform duration-200" style={{ width: 8, height: 8, background: color, boxShadow: `0 0 ${isActive ? 12 : 6}px ${color}`, transform: isActive ? "scale(1.4)" : "scale(1)" }} />

              {isActive && (
                <div className="absolute z-50 pointer-events-none" style={{ bottom: "calc(100% + 14px)", left: "50%", transform: "translateX(-50%)", width: 220 }}>
                  <div className="bg-black/95 border border-white/10 p-4" style={{ boxShadow: "0 8px 32px rgba(0,0,0,0.8)" }}>
                    <div className="flex items-center justify-between mb-3">
                      <span className="font-mono text-[9px] text-white/30 tracking-[0.2em]">{zone.num}</span>
                      <span className="font-mono text-[8px] tracking-wider px-1.5 py-0.5 border" style={{ color: zone.status === "ACTIVE" ? "#EF4444" : "#F59E0B", borderColor: zone.status === "ACTIVE" ? "rgba(239,68,68,0.3)" : "rgba(245,158,11,0.3)" }}>{zone.status}</span>
                    </div>
                    <h4 className="text-white font-bold text-[13px] tracking-wide mb-0.5">{zone.name}</h4>
                    <p className="font-mono text-[8px] text-white/30 tracking-wider mb-3">{zone.region}</p>
                    <p className="font-mono text-[9px] text-white/50 leading-relaxed tracking-wide mb-3">{zone.description}</p>
                    <p className="font-mono text-[8px] text-white/25 tracking-wider">{zone.coords}</p>
                    <div className="absolute" style={{ bottom: -5, left: "50%", transform: "translateX(-50%)", width: 0, height: 0, borderLeft: "5px solid transparent", borderRight: "5px solid transparent", borderTop: "5px solid rgba(255,255,255,0.1)" }} />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Legend ── */}
      <div className="flex items-center gap-6 mt-4 justify-end max-w-[1000px] mx-auto px-2">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-red-500 inline-block" style={{ boxShadow: "0 0 6px #EF4444" }} />
          <span className="font-mono text-[9px] text-white/30 tracking-wider">ACTIVE</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" style={{ boxShadow: "0 0 6px #F59E0B" }} />
          <span className="font-mono text-[9px] text-white/30 tracking-wider">MONITORING</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full inline-block" style={{ background: "#22D3EE", boxShadow: "0 0 6px #22D3EE" }} />
          <span className="font-mono text-[9px] text-white/30 tracking-wider">
            {eventTotal > 0 ? `${eventTotal} LIVE EVENTS` : "LIVE EVENTS"}
          </span>
        </div>
        <span className="font-mono text-[9px] text-white/15 tracking-wider">HOVER TO INSPECT</span>
      </div>
    </div>
  );
}
