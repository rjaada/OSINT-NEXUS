"""
Sentinel-2 imagery change detection via Copernicus Data Space STAC API.

Catalog search and thumbnails are fully public — no authentication required.
Full-resolution band downloads require a free CDSE account (not implemented here).

Change score is a catalog-level heuristic (cloud cover delta + scene proximity).
Real NDVI change requires band downloads. This is the tier-1 catalog approximation —
sufficient for "imagery available, review recommended" flagging.

Auto-triggered on FIRMS fire events via ingest pipeline.
On-demand via /api/v2/imagery/check endpoint.
"""

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("osint.sentinel")

STAC_SEARCH_URL = "https://catalogue.dataspace.copernicus.eu/stac/search"
STAC_COLLECTION = "sentinel-2-l2a"


def _bbox(lat: float, lon: float, km: float = 3.0) -> Tuple[float, float, float, float]:
    lat_d = km / 111.0
    lon_d = km / (111.0 * math.cos(math.radians(lat)))
    return (lon - lon_d, lat - lat_d, lon + lon_d, lat + lat_d)


async def _search_scenes(
    lat: float,
    lon: float,
    start: str,
    end: str,
    km: float = 3.0,
    max_cloud: int = 40,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed — imagery search unavailable")
        return []

    bbox = _bbox(lat, lon, km)
    params = {
        "collections": STAC_COLLECTION,
        "bbox": f"{bbox[0]:.5f},{bbox[1]:.5f},{bbox[2]:.5f},{bbox[3]:.5f}",
        "datetime": f"{start}/{end}",
        "limit": limit,
        "sortby": "-datetime",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(STAC_SEARCH_URL, params=params)
            if not resp.is_success:
                logger.warning("STAC search %s → %d", STAC_URL, resp.status_code)
                return []
            features = resp.json().get("features", [])
    except Exception as exc:
        logger.error("Sentinel STAC error: %s", exc)
        return []

    scenes: List[Dict[str, Any]] = []
    for f in features:
        props = f.get("properties", {})
        cloud = float(props.get("eo:cloud_cover", 100))
        if cloud > max_cloud:
            continue

        # Thumbnail: try links first, then assets
        thumb: Optional[str] = None
        for link in f.get("links", []):
            if link.get("rel") == "thumbnail":
                thumb = link["href"]
                break
        if not thumb:
            for asset in f.get("assets", {}).values():
                title = str(asset.get("title", "")).lower()
                atype = str(asset.get("type", "")).lower()
                if "thumbnail" in title or "thumbnail" in atype or "quicklook" in title:
                    thumb = asset.get("href")
                    break

        scenes.append({
            "id": f.get("id", ""),
            "datetime": props.get("datetime", ""),
            "cloud_cover": round(cloud, 1),
            "platform": props.get("platform", "sentinel-2"),
            "thumbnail": thumb,
            "bbox": f.get("bbox"),
        })

    return scenes


def _change_score(before: List[dict], after: List[dict]) -> float:
    """
    Catalog-level heuristic change score 0.0–1.0.
    Proxy signals: cloud/smoke delta, scene availability, time gap.
    """
    if not before and not after:
        return 0.0
    if not before:
        return 0.25  # no baseline
    if not after:
        return 0.15  # no post-event imagery yet

    bc = min(s["cloud_cover"] for s in before)
    ac = min(s["cloud_cover"] for s in after)
    cloud_delta = max(0.0, ac - bc)

    score = 0.1
    if cloud_delta > 25:
        score += 0.35
    elif cloud_delta > 12:
        score += 0.20
    elif cloud_delta > 5:
        score += 0.10

    # Post-event imagery available
    score += 0.15

    # Temporal proximity bonus
    try:
        a_dt = datetime.fromisoformat(str(after[0]["datetime"]).replace("Z", "+00:00"))
        b_dt = datetime.fromisoformat(str(before[0]["datetime"]).replace("Z", "+00:00"))
        days = (a_dt - b_dt).days
        if days <= 5:
            score += 0.20
        elif days <= 10:
            score += 0.10
    except Exception:
        pass

    return round(min(score, 1.0), 2)


def _flags(score: float, before: List[dict], after: List[dict]) -> List[str]:
    flags: List[str] = []
    if score >= 0.60:
        flags.append("SIGNIFICANT_CHANGE_DETECTED")
    elif score >= 0.35:
        flags.append("IMAGERY_REVIEW_RECOMMENDED")
    if not before:
        flags.append("NO_BASELINE_IMAGERY")
    if not after:
        flags.append("POST_EVENT_IMAGERY_PENDING")
    if before and after:
        try:
            if min(s["cloud_cover"] for s in after) - min(s["cloud_cover"] for s in before) > 20:
                flags.append("SMOKE_OR_CLOUD_SIGNATURE")
        except Exception:
            pass
    if not flags:
        flags.append("NO_SIGNIFICANT_CHANGE")
    return flags


async def analyze_change(
    lat: float,
    lon: float,
    event_time: str,
    km: float = 3.0,
) -> Dict[str, Any]:
    """
    Fetch before/after Sentinel-2 scenes for a point event.
    Returns change analysis dict with thumbnails, score, and flags.
    """
    try:
        t = datetime.fromisoformat(str(event_time).replace("Z", "+00:00"))
    except Exception:
        t = datetime.now(timezone.utc)

    fmt = "%Y-%m-%dT%H:%M:%SZ"
    before_s = (t - timedelta(days=30)).strftime(fmt)
    before_e = (t - timedelta(hours=1)).strftime(fmt)
    after_s = t.strftime(fmt)
    after_e = (t + timedelta(days=6)).strftime(fmt)

    before_scenes, after_scenes = await asyncio.gather(
        _search_scenes(lat, lon, before_s, before_e, km=km, limit=4),
        _search_scenes(lat, lon, after_s, after_e, km=km, limit=4),
    )

    score = _change_score(before_scenes, after_scenes)

    return {
        "lat": lat,
        "lon": lon,
        "event_time": event_time,
        "before": before_scenes[0] if before_scenes else None,
        "after": after_scenes[0] if after_scenes else None,
        "before_scenes_found": len(before_scenes),
        "after_scenes_found": len(after_scenes),
        "change_score": score,
        "flags": _flags(score, before_scenes, after_scenes),
        "coverage_km": km,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "method": "catalog-heuristic",
        "note": "Cloud cover delta proxy. Full NDVI requires band download (CDSE account).",
    }
