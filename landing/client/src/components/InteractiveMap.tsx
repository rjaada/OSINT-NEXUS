/**
 * InteractiveMap — keeps the original dotted SVG world map unchanged,
 * overlays clickable conflict-zone hotspots at geo-accurate positions.
 *
 * SVG canvas: 1138 × 640 (equirectangular-ish, lat -60..+85, lon -180..+180)
 * Position formula:
 *   x% = (lon + 180) / 360 * 100
 *   y% = (85 - lat) / 145 * 100
 */

// @ts-ignore - Vite raw import
import mapSvgContent from "../../../map/public/map-dark.svg?raw";
import { useState } from "react";

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

const ZONES: Zone[] = [
  {
    id: "gaza",
    num: "01",
    name: "GAZA STRIP",
    region: "Palestine · Israel",
    status: "ACTIVE",
    description: "Ongoing conflict monitored via Telegram, Red Alert system and satellite imagery. Primary intelligence focus zone.",
    coords: "31.3547° N · 34.3088° E",
    lat: 31.35,
    lon: 34.31,
  },
  {
    id: "ukraine",
    num: "02",
    name: "UKRAINE",
    region: "Eastern Europe",
    status: "ACTIVE",
    description: "Russian-Ukrainian conflict. Multi-source fusion: OSINT Telegram, flight tracking, ACLED events. Frontline tracked near-real-time.",
    coords: "48.3794° N · 31.1656° E",
    lat: 48.38,
    lon: 31.17,
  },
  {
    id: "sudan",
    num: "03",
    name: "SUDAN",
    region: "North Africa",
    status: "MONITORING",
    description: "SAF vs. RSF armed conflict. Khartoum and Darfur priority zones. Cross-referenced with ACLED taxonomy.",
    coords: "12.8628° N · 30.2176° E",
    lat: 12.86,
    lon: 30.22,
  },
  {
    id: "yemen",
    num: "04",
    name: "YEMEN",
    region: "Arabian Peninsula",
    status: "ACTIVE",
    description: "Houthi operations and Red Sea maritime threat monitoring. Vessel tracking integrated with strike event correlation.",
    coords: "15.5527° N · 48.5164° E",
    lat: 15.55,
    lon: 48.52,
  },
];

/** Map geographic coord → % position on the SVG canvas */
function toPercent(lat: number, lon: number): { x: number; y: number } {
  const x = ((lon + 180) / 360) * 100;
  const y = ((85 - lat) / 145) * 100;
  return { x, y };
}

export default function InteractiveMap() {
  const [active, setActive] = useState<string | null>(null);

  const activeZone = ZONES.find((z) => z.id === active) ?? null;

  return (
    <div className="relative w-full select-none" style={{ userSelect: "none" }}>
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

      {/* ── Hotspot overlay — absolutely positioned over the SVG ── */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ maxWidth: "1000px", margin: "0 auto", left: 0, right: 0 }}
      >
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
              {/* Pulse rings */}
              <span
                className="absolute rounded-full animate-ping"
                style={{
                  width: 28,
                  height: 28,
                  top: "50%",
                  left: "50%",
                  transform: "translate(-50%, -50%)",
                  background: color,
                  opacity: isActive ? 0.35 : 0.2,
                  animationDuration: "1.8s",
                }}
              />
              <span
                className="absolute rounded-full animate-ping"
                style={{
                  width: 18,
                  height: 18,
                  top: "50%",
                  left: "50%",
                  transform: "translate(-50%, -50%)",
                  background: color,
                  opacity: isActive ? 0.5 : 0.3,
                  animationDuration: "1.2s",
                  animationDelay: "0.3s",
                }}
              />
              {/* Core dot */}
              <span
                className="relative block rounded-full transition-transform duration-200"
                style={{
                  width: 8,
                  height: 8,
                  background: color,
                  boxShadow: `0 0 ${isActive ? 12 : 6}px ${color}`,
                  transform: isActive ? "scale(1.4)" : "scale(1)",
                }}
              />

              {/* Tooltip card — appears above the dot */}
              {isActive && (
                <div
                  className="absolute z-50 pointer-events-none"
                  style={{
                    bottom: "calc(100% + 14px)",
                    left: "50%",
                    transform: "translateX(-50%)",
                    width: 220,
                  }}
                >
                  <div
                    className="bg-black/95 border border-white/10 p-4"
                    style={{ boxShadow: "0 8px 32px rgba(0,0,0,0.8)" }}
                  >
                    {/* Header */}
                    <div className="flex items-center justify-between mb-3">
                      <span className="font-mono text-[9px] text-white/30 tracking-[0.2em]">
                        {zone.num}
                      </span>
                      <span
                        className="font-mono text-[8px] tracking-wider px-1.5 py-0.5 border"
                        style={{
                          color: zone.status === "ACTIVE" ? "#EF4444" : "#F59E0B",
                          borderColor: zone.status === "ACTIVE" ? "rgba(239,68,68,0.3)" : "rgba(245,158,11,0.3)",
                        }}
                      >
                        {zone.status}
                      </span>
                    </div>

                    <h4 className="text-white font-bold text-[13px] tracking-wide mb-0.5">
                      {zone.name}
                    </h4>
                    <p className="font-mono text-[8px] text-white/30 tracking-wider mb-3">
                      {zone.region}
                    </p>

                    <p className="font-mono text-[9px] text-white/50 leading-relaxed tracking-wide mb-3">
                      {zone.description}
                    </p>

                    <p className="font-mono text-[8px] text-white/25 tracking-wider">
                      {zone.coords}
                    </p>

                    {/* Arrow */}
                    <div
                      className="absolute"
                      style={{
                        bottom: -5,
                        left: "50%",
                        transform: "translateX(-50%)",
                        width: 0,
                        height: 0,
                        borderLeft: "5px solid transparent",
                        borderRight: "5px solid transparent",
                        borderTop: "5px solid rgba(255,255,255,0.1)",
                      }}
                    />
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
        <span className="font-mono text-[9px] text-white/15 tracking-wider">HOVER TO INSPECT</span>
      </div>
    </div>
  );
}
