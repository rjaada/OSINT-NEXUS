/**
 * CoverageSection — Anduril-style conflict zone cards.
 *
 * Fetches active zones from /api/v2/conflict-zones.
 * Falls back to 4 hardcoded defaults if backend is unavailable or returns nothing.
 * Each card shows: zone number, status, name, region, description,
 * a real geographic map (ConflictZoneMap), and coordinates.
 */
"use client";
import { useEffect, useState } from "react";
import { ConflictZoneMap, ZONE_MAP_CONFIGS } from "./ConflictZoneMap";
import type { ZoneMapConfig } from "./ConflictZoneMap";

interface Zone {
  num: string;
  name: string;           // e.g. "UKRAINE"
  region: string;         // e.g. "Eastern Europe"
  status: "ACTIVE" | "MONITORING" | "WATCH";
  description: string;
  coords: string;
  mapConfig: ZoneMapConfig;
  eventCount?: number;
}

/** Hardcoded fallback — shown when backend is unreachable */
const FALLBACK_ZONES: Zone[] = [
  {
    num: "01",
    name: "GAZA STRIP",
    region: "Palestine · Israel",
    status: "ACTIVE",
    description:
      "ONGOING CONFLICT MONITORED VIA TELEGRAM CHANNELS, RED ALERT SYSTEM AND SATELLITE IMAGERY ANALYSIS. PRIMARY INTELLIGENCE FOCUS ZONE.",
    coords: "[31.3547 · 34.3088]",
    mapConfig: ZONE_MAP_CONFIGS["GAZA STRIP"],
  },
  {
    num: "02",
    name: "ISRAEL",
    region: "Middle East",
    status: "ACTIVE",
    description:
      "DIRECT MILITARY EXCHANGES WITH IRAN. MULTI-FRONT MONITORING: NORTHERN BORDER, WEST BANK, RED SEA. STRIKE EVENTS CORRELATED ACROSS TELEGRAM AND FLIGHT FEEDS.",
    coords: "[31.0461 · 34.8516]",
    mapConfig: ZONE_MAP_CONFIGS["ISRAEL"],
  },
  {
    num: "03",
    name: "IRAN",
    region: "Middle East",
    status: "ACTIVE",
    description:
      "BALLISTIC MISSILE AND DRONE LAUNCH MONITORING. CROSS-REFERENCED WITH US CENTCOM ACTIVITY, STRAIT OF HORMUZ VESSEL TRACKING AND GOLD MARKET INDICATORS.",
    coords: "[32.4279 · 53.6880]",
    mapConfig: ZONE_MAP_CONFIGS["IRAN"],
  },
  {
    num: "04",
    name: "LEBANON",
    region: "Middle East",
    status: "MONITORING",
    description:
      "HEZBOLLAH POSTURE MONITORING POST-CEASEFIRE. SOUTHERN LEBANON BUFFER ZONE ACTIVITY. CROSS-REFERENCED WITH IDF MOVEMENT AND DIPLOMATIC SIGNAL FEEDS.",
    coords: "[33.8547 · 35.8623]",
    mapConfig: ZONE_MAP_CONFIGS["LEBANON"],
  },
];

/** Try to map a backend zone label to a ZoneMapConfig */
function resolveMapConfig(label: string): ZoneMapConfig | null {
  const upper = label.toUpperCase().trim();
  // Direct match
  if (ZONE_MAP_CONFIGS[upper]) return ZONE_MAP_CONFIGS[upper];
  // Partial match
  for (const key of Object.keys(ZONE_MAP_CONFIGS)) {
    if (upper.includes(key) || key.includes(upper)) return ZONE_MAP_CONFIGS[key];
  }
  return null;
}

interface BackendZone {
  id?: number;
  label: string;
  color?: string;
  severity?: string;
  bbox?: number[];
}

export function CoverageSection() {
  const [zones, setZones] = useState<Zone[]>(FALLBACK_ZONES);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchZones() {
      try {
        // Fetch backend conflict zones
        const [zonesRes, eventsRes] = await Promise.allSettled([
          fetch("/api/v2/conflict-zones", { credentials: "include" }),
          fetch("/api/v2/events?limit=500", { credentials: "include" }),
        ]);

        let backendZones: BackendZone[] = [];
        if (zonesRes.status === "fulfilled" && zonesRes.value.ok) {
          const raw = await zonesRes.value.json();
          // Backend returns either [] or { zones: [] }
          backendZones = Array.isArray(raw) ? raw : Array.isArray(raw?.zones) ? raw.zones : [];
        }

        // Count recent events per zone keyword for "live" activity signal
        const eventCounts: Record<string, number> = {};
        if (eventsRes.status === "fulfilled" && eventsRes.value.ok) {
          const eventsData = await eventsRes.value.json();
          const events: Array<{ title?: string; description?: string }> =
            Array.isArray(eventsData) ? eventsData :
            Array.isArray(eventsData?.events) ? eventsData.events : [];
          for (const evt of events) {
            const text = `${evt.title ?? ""} ${evt.description ?? ""}`.toUpperCase();
            for (const key of ["ISRAEL", "IRAN", "LEBANON", "GAZA", "UKRAINE", "SUDAN", "SYRIA", "IRAQ"]) {
              if (text.includes(key)) eventCounts[key] = (eventCounts[key] ?? 0) + 1;
            }
          }
        }

        // Build zone list from backend if we got valid zones
        if (backendZones.length > 0) {
          const mapped: Zone[] = backendZones
            .reduce<Zone[]>((acc, bz, i) => {
              const mapConfig = resolveMapConfig(bz.label);
              if (!mapConfig) return acc;
              const nameKey = bz.label.toUpperCase().trim();
              const countKey = Object.keys(eventCounts).find((k) =>
                nameKey.includes(k)
              );
              const count = countKey ? eventCounts[countKey] : 0;
              const status: Zone["status"] =
                bz.severity === "critical" || count > 20
                  ? "ACTIVE"
                  : bz.severity === "high" || count > 5
                  ? "MONITORING"
                  : "WATCH";

              acc.push({
                num: String(i + 1).padStart(2, "0"),
                name: bz.label.toUpperCase(),
                region: "",
                status,
                description: `ACTIVE INTELLIGENCE COLLECTION. ${count} EVENTS DETECTED IN LAST COLLECTION CYCLE. SOURCE FUSION: TELEGRAM, RSS, FLIGHT AND MARITIME FEEDS.`,
                coords: bz.bbox
                  ? `[${bz.bbox[1]?.toFixed(2)} · ${bz.bbox[0]?.toFixed(2)}]`
                  : "",
                mapConfig,
                eventCount: count,
              });
              return acc;
            }, []);

          if (mapped.length > 0) {
            setZones(mapped);
            setLoading(false);
            return;
          }
        }

        // Augment fallback zones with event counts from live data
        if (Object.keys(eventCounts).length > 0) {
          setZones(
            FALLBACK_ZONES.map((z) => {
              const key = Object.keys(eventCounts).find((k) =>
                z.name.includes(k)
              );
              return { ...z, eventCount: key ? eventCounts[key] : 0 };
            })
          );
        }
      } catch {
        // Network error — keep fallback
      } finally {
        setLoading(false);
      }
    }

    fetchZones();
  }, []);

  return (
    <section
      className="w-full bg-[#F5F4EF] text-black"
      id="coverage"
      style={{ padding: "80px 0 0 0" }}
    >
      {/* Section header */}
      <div
        className="flex items-start justify-between reveal-card"
        style={{ padding: "0 64px 64px 64px" }}
      >
        <div className="flex flex-col gap-1">
          <span className="text-[10px] tracking-[0.35em] text-black/40 uppercase font-mono">
            COVERAGE AREAS
          </span>
          <span className="font-mono text-[10px] tracking-[0.2em] text-black/30">
            | OSINT NEXUS |
          </span>
        </div>
        <div className="flex items-center gap-8">
          <span className="text-[10px] tracking-[0.35em] text-black/40 uppercase font-mono">
            {zones.length} LOCATIONS
          </span>
          <span className="font-mono text-[10px] tracking-[0.2em] text-black/30">
            | 2026 |
          </span>
        </div>
      </div>

      {/* "WHERE THE WAR IS" heading */}
      <h2
        className="reveal-heading font-extrabold uppercase leading-[0.92] tracking-[-0.02em]"
        style={{
          fontSize: "clamp(64px, 10vw, 140px)",
          padding: "0 64px 80px 64px",
        }}
      >
        WHERE THE
        <br />
        WAR IS
      </h2>

      {/* Thin rule */}
      <div
        className="reveal-line"
        style={{
          width: "100%",
          height: "1px",
          background: "rgba(0,0,0,0.12)",
          marginBottom: "0",
        }}
      />

      {/* 4-column Anduril-style grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${zones.length}, 1fr)`,
          borderLeft: "1px solid rgba(0,0,0,0.1)",
        }}
        className="coverage-grid"
      >
        {zones.map((zone, i) => (
          <div
            key={zone.num}
            className="reveal-card coverage-col group"
            style={{
              padding: "32px 40px 40px 40px",
              borderRight: "1px solid rgba(0,0,0,0.1)",
              display: "flex",
              flexDirection: "column",
              // @ts-ignore
              "--delay": `${i * 100}ms`,
            }}
          >
            {/* Top row: number + status */}
            <div className="flex items-center justify-between mb-5">
              <span className="font-mono text-[11px] tracking-[0.2em] text-black/30">
                [{zone.num}]
              </span>
              <span
                className="font-mono text-[9px] tracking-[0.25em] uppercase transition-all duration-200"
                style={{
                  color:
                    zone.status === "ACTIVE"
                      ? "#000"
                      : zone.status === "MONITORING"
                      ? "rgba(0,0,0,0.5)"
                      : "rgba(0,0,0,0.35)",
                  border: "1px solid rgba(0,0,0,0.4)",
                  padding: "3px 8px",
                }}
              >
                {zone.status}
              </span>
            </div>

            {/* Zone name */}
            <h3
              className="font-extrabold uppercase leading-[1.05] tracking-[-0.01em]"
              style={{ fontSize: "clamp(20px, 2vw, 30px)", marginBottom: "6px" }}
            >
              {zone.name}
            </h3>

            {/* Region */}
            {zone.region && (
              <span
                className="font-mono text-[11px] tracking-[0.1em] text-black/40 uppercase"
                style={{ marginBottom: "20px" }}
              >
                {zone.region}
              </span>
            )}

            {/* Description */}
            <p
              className="font-mono text-[11px] leading-[1.9] text-black/55 tracking-[0.03em] uppercase"
              style={{ marginTop: zone.region ? "0" : "20px", flex: "1" }}
            >
              {zone.description}
            </p>

            {/* Event count badge */}
            {zone.eventCount !== undefined && zone.eventCount > 0 && (
              <div
                className="flex items-center gap-2 mt-4"
                style={{ marginBottom: "4px" }}
              >
                <span
                  className="w-[5px] h-[5px] rounded-full inline-block"
                  style={{ background: "#000", animation: "blink 2s ease-in-out infinite" }}
                />
                <span className="font-mono text-[9px] tracking-[0.15em] text-black/40">
                  {zone.eventCount} EVENTS DETECTED
                </span>
              </div>
            )}

            {/* Real geographic map */}
            <div style={{ marginTop: "28px", marginBottom: "20px" }}>
              <ConflictZoneMap config={zone.mapConfig} />
            </div>

            {/* Coordinates */}
            <span className="font-mono text-[10px] tracking-[0.1em] text-black/30">
              {zone.coords}
            </span>
          </div>
        ))}
      </div>

      {/* Bottom bar */}
      <div
        className="flex flex-col md:flex-row items-start md:items-center justify-between reveal-card"
        style={{
          padding: "28px 64px",
          borderTop: "1px solid rgba(0,0,0,0.12)",
          marginTop: "0",
        }}
      >
        <div className="font-mono text-[11px] text-black/40 tracking-[0.05em] leading-[1.8]">
          CONFLICT ZONES MONITORED IN REAL-TIME.
          <br />
          DATA FUSED FROM OPEN SOURCES, SATELLITE, TELEGRAM AND FLIGHT TRACKING.
        </div>
        <div className="font-mono text-[11px] text-black/40 tracking-[0.05em] leading-[1.8] text-right mt-4 md:mt-0">
          {loading ? "LOADING LIVE DATA..." : `${zones.length} ACTIVE ZONES · LIVE`}
        </div>
      </div>
    </section>
  );
}
