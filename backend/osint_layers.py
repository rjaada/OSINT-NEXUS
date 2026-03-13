import asyncio
import csv
import io
import json
from typing import Any, Callable, Dict, List, Optional, Sequence

import httpx
import websockets


_seen_firms_ids: set = set()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, str) and value.strip().lower() in {"ground", "gnd", "nan", "none", ""}:
            return default
        return float(value)
    except Exception:
        return default


def _is_military(callsign: str, prefixes: Sequence[str]) -> bool:
    if not callsign:
        return False
    up = callsign.strip().upper()
    return any(up.startswith(p) for p in prefixes)


async def poll_adsblol(
    *,
    enabled: bool,
    api_url: str,
    interval_sec: int,
    metrics: Dict[str, Any],
    last_aircraft: List[dict],
    military_prefixes: Sequence[str],
    now_iso: Callable[[], str],
    broadcast: Callable[[dict], Any],
) -> None:
    if not enabled or not api_url:
        return
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "OSINT-Nexus/1.0"}) as client:
        while True:
            await asyncio.sleep(max(3, interval_sec))
            metrics["adsblol_polls"] = int(metrics.get("adsblol_polls", 0)) + 1
            try:
                r = await client.get(api_url)
                if r.status_code != 200:
                    continue
                data = r.json()
                rows = data.get("ac") or data.get("aircraft") or []
                if not isinstance(rows, list):
                    continue
                parsed: List[dict] = []
                for a in rows[:250]:
                    if not isinstance(a, dict):
                        continue
                    lat = a.get("lat")
                    lon = a.get("lon")
                    if lat is None or lon is None:
                        continue
                    callsign = str(a.get("flight") or a.get("callsign") or a.get("hex") or "").strip()
                    parsed.append(
                        {
                            "id": str(a.get("hex") or a.get("icao24") or callsign),
                            "callsign": callsign.upper(),
                            "country": str(a.get("r") or "Unknown"),
                            "lat": _to_float(lat),
                            "lng": _to_float(lon),
                            "alt": int(_to_float(a.get("alt_baro") or a.get("alt_geom") or 0) * 0.3048),
                            "speed": int(_to_float(a.get("gs") or 0) * 0.51444),
                            "heading": _to_float(a.get("track") or 0),
                            "military": _is_military(callsign, military_prefixes),
                        }
                    )
                if parsed:
                    last_aircraft[:] = parsed[:150]
                    metrics["last_success"]["adsblol"] = now_iso()
                    await broadcast({"type": "AIRCRAFT_UPDATE", "data": last_aircraft, "ts": asyncio.get_event_loop().time()})
            except Exception as e:
                metrics["adsblol_errors"] = int(metrics.get("adsblol_errors", 0)) + 1
                print(f"[ADSBLOL] Error: {e}")


async def poll_aisstream(
    *,
    enabled: bool,
    ws_url: str,
    api_key: str,
    bbox: str,
    metrics: Dict[str, Any],
    now_iso: Callable[[], str],
    broadcast: Callable[[dict], Any],
) -> None:
    if not enabled or not ws_url:
        return
    if not api_key:
        print("[AIS] API key is empty; stream may reject subscription")
    bounds = [[[12.0, 30.0], [40.0, 63.0]]]
    try:
        if bbox:
            parts = [float(x.strip()) for x in bbox.split(",")]
            if len(parts) == 4:
                # west,south,east,north -> [[south,west],[north,east]]
                bounds = [[[parts[1], parts[0]], [parts[3], parts[2]]]]
    except Exception:
        pass

    while True:
        try:
            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=20,
                open_timeout=20,
                close_timeout=10,
                max_size=2_000_000,
            ) as ws:
                sub = {
                    "BoundingBoxes": bounds,
                }
                if api_key:
                    sub["APIKey"] = api_key
                await ws.send(json.dumps(sub))
                print(f"[AIS] Connected and subscribed to {ws_url} with bbox={bounds}")
                while True:
                    metrics["ais_polls"] = int(metrics.get("ais_polls", 0)) + 1
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    except asyncio.TimeoutError:
                        # No message in window — connection is alive, keep waiting.
                        continue
                    payload = json.loads(raw)
                    if isinstance(payload, dict) and payload.get("error"):
                        print(f"[AIS] Subscription/server error: {payload.get('error')}")
                        continue
                    m = payload.get("Message") or {}
                    msg_type = str(payload.get("MessageType") or "")
                    pos = (
                        m.get("PositionReport")
                        or m.get("StandardClassBPositionReport")
                        or m.get(msg_type)
                        or {}
                    )
                    meta = payload.get("Metadata") or m.get("MetaData") or {}
                    lat = pos.get("Latitude")
                    lon = pos.get("Longitude")
                    if lat is None or lon is None:
                        lat = meta.get("Latitude")
                        lon = meta.get("Longitude")
                    if lat is None or lon is None:
                        continue
                    vessel = {
                        "id": str(meta.get("MMSI") or pos.get("UserID") or "unknown"),
                        "mmsi": str(meta.get("MMSI") or pos.get("UserID") or "unknown"),
                        "name": str(meta.get("ShipName") or "Unknown"),
                        "lat": _to_float(lat),
                        "lng": _to_float(lon),
                        "speed": _to_float(pos.get("Sog") or 0),
                        "heading": _to_float(pos.get("Cog") or 0),
                        "ship_type": str(meta.get("ShipType") or m.get("ShipType") or "Unknown"),
                        "timestamp": str(meta.get("time_utc") or now_iso()),
                    }
                    metrics["last_success"]["ais"] = now_iso()
                    await broadcast({"type": "VESSEL_UPDATE", "data": [vessel], "ts": asyncio.get_event_loop().time()})
        except Exception as e:
            metrics["ais_errors"] = int(metrics.get("ais_errors", 0)) + 1
            print(f"[AIS] Error ({type(e).__name__}): {repr(e)}")
            await asyncio.sleep(5)


async def poll_firms(
    *,
    enabled: bool,
    map_key: str,
    source: str,
    bbox: str,
    days: int,
    interval_sec: int,
    metrics: Dict[str, Any],
    now_iso: Callable[[], str],
    ingest_event: Callable[[dict], Any],
) -> None:
    if not enabled or not map_key or not bbox:
        return
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source}/{bbox}/{max(1, days)}"
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "OSINT-Nexus/1.0"}) as client:
        while True:
            metrics["firms_polls"] = int(metrics.get("firms_polls", 0)) + 1
            try:
                r = await client.get(url)
                if r.status_code != 200 or not r.text.strip():
                    print(f"[FIRMS] Empty/non-200 response status={r.status_code}")
                    await asyncio.sleep(max(60, interval_sec))
                    continue
                reader = csv.DictReader(io.StringIO(r.text))
                for row in reader:
                    try:
                        lat = float(row.get("latitude") or row.get("lat") or 0.0)
                        lng = float(row.get("longitude") or row.get("lon") or 0.0)
                        acq_date = str(row.get("acq_date") or "")
                        acq_time = str(row.get("acq_time") or "")
                        bright = row.get("bright_ti4") or row.get("brightness") or ""
                        confidence = str(row.get("confidence") or "")
                        firms_id = f"firms_{lat:.4f}_{lng:.4f}_{acq_date}_{acq_time}"
                        if firms_id in _seen_firms_ids:
                            continue
                        _seen_firms_ids.add(firms_id)
                        desc = f"[NASA FIRMS] Thermal anomaly at {lat:.4f},{lng:.4f} (brightness={bright}, confidence={confidence})"
                        event = {
                            "id": firms_id,
                            "type": "STRIKE",
                            "desc": desc,
                            "lat": lat,
                            "lng": lng,
                            "source": "NASA FIRMS",
                            "timestamp": now_iso(),
                            "insufficient_evidence": False,
                            "observed_facts": ["Satellite thermal anomaly detected (FIRMS)"],
                            "model_inference": ["Potential fire/explosion/heat source; requires corroboration"],
                        }
                        await ingest_event(event)
                    except Exception:
                        continue
                metrics["last_success"]["firms"] = now_iso()
                if len(_seen_firms_ids) > 50000:
                    _seen_firms_ids.clear()
            except Exception as e:
                metrics["firms_errors"] = int(metrics.get("firms_errors", 0)) + 1
                print(f"[FIRMS] Error: {e}")
            await asyncio.sleep(max(60, interval_sec))
