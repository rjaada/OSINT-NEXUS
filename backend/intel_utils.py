import hashlib
import math
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


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
    # Normalize Arabic alef forms (أ إ آ ٱ) → bare alef (ا)
    s = re.sub(r"[\u0623\u0625\u0622\u0671]", "\u0627", s)
    # Remove Arabic diacritics/harakat (U+064B–U+065F)
    s = re.sub(r"[\u064B-\u065F]", "", s)
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


def cluster_events_for_map(items: List[dict], zoom_bucket: int = 4) -> List[dict]:
    clusters: Dict[Tuple[int, int, str], dict] = {}
    for e in items:
        lat = float(e.get("lat", 0.0))
        lng = float(e.get("lng", 0.0))
        t = str(e.get("type", "CLASH"))
        lat_bucket = int(lat * zoom_bucket)
        lon_scale = max(1.0, 1.0 / max(0.1, math.cos(math.radians(abs(lat)))))
        lng_bucket = int(lng * zoom_bucket * lon_scale)
        k = (lat_bucket, lng_bucket, t)
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


def event_confidence_value(event: Dict[str, Any], source_reliability: Dict[str, int]) -> int:
    raw = event.get("confidence_score")
    if isinstance(raw, (int, float)):
        return int(max(0, min(100, raw)))
    src = extract_source(event)
    return int(max(0, min(100, source_reliability.get(src, 45))))


def event_theater_bucket(event: Dict[str, Any]) -> str:
    lat = float(event.get("lat", 0.0))
    lng = float(event.get("lng", 0.0))
    if 29 <= lat <= 35 and 33 <= lng <= 37:
        return "Levant"
    if 23 <= lat <= 33 and 44 <= lng <= 56:
        return "Gulf"
    if 11 <= lat <= 22 and 37 <= lng <= 45:
        return "RedSea"
    if 32 <= lat <= 38 and 36 <= lng <= 43:
        return "Syria-Iraq"
    return "Other"


def assess_confidence(
    event: dict,
    nearby: list,
    age_min: float,
    source_reliability: Dict[str, int],
) -> Tuple[int, str, List[str]]:
    src = extract_source(event)
    base = source_reliability.get(src, 50)

    corroborating = sorted({extract_source(x) for x in nearby if extract_source(x) != src})
    corroboration_bonus = min(24, len(corroborating) * 8)

    freshness = 8 if age_min <= 5 else (4 if age_min <= 15 else 0)
    critical_bonus = 5 if event.get("type") == "CRITICAL" else 0
    evidence_bonus = 6 if not event.get("insufficient_evidence") else -8

    score = max(0, min(100, base + corroboration_bonus + freshness + critical_bonus + evidence_bonus - 30))

    reasons = [f"source reliability {base}/100"]
    if corroborating:
        reasons.append(f"corroborated by {len(corroborating)} source(s)")
    if age_min <= 5:
        reasons.append("fresh update")
    if event.get("insufficient_evidence"):
        reasons.append("limited geolocation evidence")

    return score, "; ".join(reasons), corroborating


def eta_band(event: dict) -> str:
    source = extract_source(event)
    if source.lower() == "red alert":
        return "<2m"
    lat = float(event.get("lat", 31.77))
    lng = float(event.get("lng", 35.21))
    dist = haversine_km(lat, lng, 31.77, 35.21)
    if dist <= 120:
        return "2-5m"
    if dist <= 350:
        return "5-10m"
    if dist <= 900:
        return "10-20m"
    return ">20m"


def geolocate_alert(city: str, israel_city_coords: Dict[str, tuple]) -> tuple:
    lower = city.lower().strip()
    for name, coords in israel_city_coords.items():
        if name in lower or lower in name:
            return coords
    return (31.77 + (hash(city) % 10) * 0.05, 35.0 + (hash(city) % 5) * 0.05)


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


def evaluate_claim_alignment(desc: str, ocr_lines: List[str], stt_lines: List[str]) -> Tuple[str, str]:
    text = normalize_desc(desc)
    merged = normalize_desc(" ".join(ocr_lines + stt_lines))
    if not merged:
        return "UNVERIFIED_VISUAL", "No OCR/STT evidence available from media."
    overlap = len({t for t in set(text.split()) & set(merged.split()) if len(t) > 2})
    if overlap >= 6:
        return "LIKELY_RELATED", "OCR/STT cues align strongly with source text."
    if overlap >= 3:
        return "UNVERIFIED_VISUAL", "Partial OCR/STT overlap; requires analyst confirmation."
    return "MISMATCH", "Low textual overlap between media extraction and source claim."


def safe_run(cmd: List[str], timeout_sec: int = 20) -> Tuple[bool, str]:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=timeout_sec).decode(errors="ignore")
        return True, out
    except Exception as e:
        return False, str(e)
