/**
 * ConflictZoneMap — renders a real geographic map for a conflict zone.
 * Uses world-atlas (Natural Earth 50m) + topojson-client + d3-geo.
 * Main country: filled black. Neighboring countries: thin outline context.
 */
import { useMemo } from "react";
import { geoPath, geoMercator } from "d3-geo";
import type { GeoPermissibleObjects } from "d3-geo";
import * as topojson from "topojson-client";
import type { Feature, FeatureCollection, Geometry } from "geojson";

// @ts-ignore — no TS types for world-atlas
import world50 from "world-atlas/countries-50m.json";

const W = 240;
const H = 170;

export interface ZoneMapConfig {
  countryId: number;
  neighborIds: number[];
}

export const ZONE_MAP_CONFIGS: Record<string, ZoneMapConfig> = {
  "GAZA STRIP": { countryId: 275, neighborIds: [376, 818, 400] },
  "GAZA":       { countryId: 275, neighborIds: [376, 818, 400] },
  "PALESTINE":  { countryId: 275, neighborIds: [376, 818, 400] },
  "UKRAINE":    { countryId: 804, neighborIds: [643, 112, 616, 703, 348, 642, 498] },
  "SUDAN":      { countryId: 729, neighborIds: [818, 434, 148, 140, 728, 231, 232] },
  "YEMEN":      { countryId: 887, neighborIds: [682, 512] },
  "SYRIA":      { countryId: 760, neighborIds: [422, 376, 400, 368, 792] },
  "IRAQ":       { countryId: 368, neighborIds: [364, 760, 400, 682, 414] },
  "MYANMAR":    { countryId: 104, neighborIds: [156, 356, 764, 418, 50] },
};

interface Props {
  config: ZoneMapConfig;
}

export function ConflictZoneMap({ config }: Props) {
  const { mainPath, neighborPaths, hasData } = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const topo = world50 as any;
    const collection = topojson.feature(
      topo,
      topo.objects.countries
    ) as unknown as FeatureCollection<Geometry>;

    const features: Feature<Geometry>[] = collection.features;

    const main = features.find((f) => Number(f.id) === config.countryId) ?? null;
    const neighbors = features.filter((f) =>
      config.neighborIds.includes(Number(f.id))
    );

    if (!main) return { mainPath: "", neighborPaths: [], hasData: false };

    const projection = geoMercator().fitExtent(
      [[12, 12], [W - 12, H - 12]],
      main as GeoPermissibleObjects
    );
    const pathGen = geoPath(projection);

    return {
      mainPath: pathGen(main as GeoPermissibleObjects) ?? "",
      neighborPaths: neighbors
        .map((f) => pathGen(f as GeoPermissibleObjects) ?? "")
        .filter(Boolean),
      hasData: true,
    };
  }, [config]);

  if (!hasData) {
    return (
      <div style={{ width: "100%", height: H, background: "rgba(0,0,0,0.04)" }} />
    );
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
      {neighborPaths.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="rgba(0,0,0,0.06)"
          stroke="rgba(0,0,0,0.28)"
          strokeWidth="0.6"
        />
      ))}
      <path d={mainPath} fill="#000000" />
    </svg>
  );
}
