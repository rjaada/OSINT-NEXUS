import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple


def parse_iso(ts: str, now_iso: Callable[[], str]) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.fromisoformat(now_iso().replace("Z", "+00:00"))


def extract_source(event: dict) -> str:
    desc = str(event.get("desc", ""))
    m = re.match(r"^\[(.+?)\]", desc)
    if m:
        return m.group(1)
    return str(event.get("source", "Unknown"))


def is_telegram_source(event: dict, telegram_source_set: Sequence[str]) -> bool:
    src = extract_source(event).strip()
    return src in telegram_source_set or src.endswith("(TG)")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def normalize_desc(desc: str) -> str:
    s = re.sub(r"^\[.+?\]\s*", "", (desc or "").lower())
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"[^\w\s\u0600-\u06FF]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def article_id(entry) -> str:
    key = getattr(entry, "link", "") or getattr(entry, "title", "") or str(entry)
    return hashlib.sha256(key.encode()).hexdigest()


def classify_event(title: str, summary: str, event_type_keywords_ar: Dict[str, List[str]]) -> str:
    t = f"{title} {summary}".lower()
    if any(k in t for k in ["airstrike", "missile", "strike", "explosion", "attack", "rocket", "drone strike"]):
        return "STRIKE"
    if any(k in t for k in ["troops", "deployment", "mobilization", "convoy", "forces moved", "exercise"]):
        return "MOVEMENT"
    if any(k in t for k in ["notam", "airspace closed", "shipping advisory", "航行警告"]):
        return "NOTAM"
    if any(k in t for k in ["clash", "firefight", "exchange of fire", "skirmish"]):
        return "CLASH"
    if any(k in t for k in ["war declared", "nuclear", "regional war", "all-out war"]):
        return "CRITICAL"
    for ev, kws in event_type_keywords_ar.items():
        if any(k in t for k in kws):
            return ev
    return "CLASH"


def extract_place_candidates(text: str, place_coords: Dict[str, Tuple[float, float]]) -> List[str]:
    lower = (text or "").lower()
    hits: List[str] = []
    for k in place_coords.keys():
        if len(k) < 3:
            continue
        if k in lower:
            hits.append(k)
    # prefer longer place names first
    hits = sorted(set(hits), key=lambda x: len(x), reverse=True)
    return hits[:8]


def is_military(callsign: str, icao24: str, military_prefixes: Sequence[str]) -> bool:
    if not callsign:
        return False
    cs = callsign.strip().upper()
    return any(cs.startswith(p) for p in military_prefixes)


def cluster_events_for_map(items: List[dict], zoom_bucket: int = 2) -> List[dict]:
    clusters: Dict[Tuple[int, int, str], dict] = {}
    for e in items:
        lat = float(e.get("lat", 0.0))
        lng = float(e.get("lng", 0.0))
        t = str(e.get("type", "CLASH"))
        k = (int(lat * zoom_bucket), int(lng * zoom_bucket), t)
        c = clusters.setdefault(k, {"count": 0, "lat_sum": 0.0, "lng_sum": 0.0, "type": t, "members": []})
        c["count"] += 1
        c["lat_sum"] += lat
        c["lng_sum"] += lng
        c["members"].append(e.get("id"))
    out = []
    for key, c in clusters.items():
        out.append(
            {
                "cluster_id": f"cl_{key[0]}_{key[1]}_{key[2]}",
                "count": c["count"],
                "lat": c["lat_sum"] / c["count"],
                "lng": c["lng_sum"] / c["count"],
                "type": c["type"],
                "members": c["members"][:40],
            }
        )
    return out


def assess_confidence_v2(
    event: dict,
    nearby: list,
    age_min: float,
    assess_confidence_fn: Callable[[dict, list, float], Tuple[int, str, List[str]]],
) -> Tuple[int, str, List[str]]:
    base, reason, corroborating = assess_confidence_fn(event, nearby, age_min)
    # v2 stricter rules:
    # - single-source CRITICAL events are capped
    # - weak geolocation reduces score harder
    if event.get("type") == "CRITICAL" and len(corroborating) == 0:
        base = min(base, 62)
    if event.get("insufficient_evidence"):
        base = max(0, base - 10)
    if len(corroborating) >= 2:
        base = min(100, base + 6)
    return base, reason, corroborating
