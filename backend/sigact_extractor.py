"""
SIGACT (Significant Activity) Pattern Extraction — Layer 2 enrichment.

Military and paramilitary Telegram channels use semi-structured reporting
conventions: grid references, call signs, BDA formats, ZULU timestamps.
General-purpose NLP misses these. This module catches them.

When 2+ structured fields are extracted (sigact_score >= 2), the event is
flagged as a SIGACT report and checked for sensor corroboration (FIRMS + ADS-B).
Three-source match (Telegram + FIRMS fire + ADS-B loiter) = tier-1 product.
"""

import math
import re
from typing import Any, Dict, List, Optional

# MGRS grid references (2-letter zone + 6 or 8 digit coordinate)
_MGRS_RE = re.compile(r"\b[A-Z]{2}\s?\d{6,8}\b", re.IGNORECASE)

# Raw 6/8-digit numeric grids (common in Russian/Iranian reporting)
_NUMERIC_GRID_RE = re.compile(r"\b\d{8}\b|\b\d{6}\b")

# Military unit call signs
_CALLSIGN_RE = re.compile(
    r"\b(battalion|bn|brigade|bde|company|coy|platoon|plt|regiment|rgt"
    r"|division|div|squadron|sqn|unit|group|gp|corps|force)\s*[-#]?\s*\d+\b",
    re.IGNORECASE,
)

# BDA: action + numeric count
_BDA_RE = re.compile(
    r"(destroyed?|neutrali[sz]ed?|eliminated?|killed?|kia|wounded?|wia"
    r"|captured?|damaged?|burned?|hit)\s*[:\-–]?\s*(\d+)",
    re.IGNORECASE,
)

# Time-on-target: HHMM followed by Z/L/ZULU/LOCAL/UTC
_TOT_RE = re.compile(r"\b(\d{4})\s*(Z|L|ZULU|LOCAL|UTC)\b", re.IGNORECASE)

# Weapon systems (conflict-zone relevant)
_WEAPON_RE = re.compile(
    r"\b(ATGM|RPG|UAV|UAS|MLRS|HIMARS|Grad|Smerch|Uragan|Kornet|Javelin"
    r"|Stinger|Shahed|Lancet|Hermes|Spike|Brimstone|JDAM|GBU|Hellfire"
    r"|AGM|Kh-\d+|Iskander|Kinzhal|Kalibr|S-300|S-400|Patriot|Iron Dome"
    r"|drone|FPV|loitering munition|IED|VBIED|SVBIED|mortar|howitzer"
    r"|tank|APC|IFV|artillery|rocket|missile|bomb|shell|barrage)\b",
    re.IGNORECASE,
)

# Direction + distance: "5km north of", "2.5km NW of"
_BEARING_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*km\s+"
    r"(north(?:east|west)?|south(?:east|west)?|east|west|NE|NW|SE|SW|N|S|E|W)"
    r"\s+of\b",
    re.IGNORECASE,
)

# Casualty counts (broader coverage than BDA alone)
_CASUALTY_RE = re.compile(
    r"(\d+)\s+(killed?|dead|kia|wounded?|wia|injur|casualt|martyr)",
    re.IGNORECASE,
)

# Priority report indicators
_FLASH_RE = re.compile(
    r"\b(FLASH|URGENT|BREAKING|CONFIRMED|DEVELOPING|UNCONFIRMED|RUMINT)\b",
    re.IGNORECASE,
)


def extract_sigact(text: str) -> Dict[str, Any]:
    """
    Extract structured SIGACT fields from conflict reporting text.
    Returns enrichment dict — empty fields are omitted.
    sigact_score = number of distinct field types found.
    is_sigact = True when score >= 2 (two or more structured military fields).
    """
    result: Dict[str, Any] = {}

    # Grid references
    mgrs = _MGRS_RE.findall(text)
    numeric = _NUMERIC_GRID_RE.findall(text)
    grids = list({g.strip().upper() for g in mgrs + numeric})
    if grids:
        result["grid_refs"] = grids[:4]

    # Call signs
    callsign_matches = _CALLSIGN_RE.findall(text)
    if callsign_matches:
        result["call_signs"] = list({cs[0].upper() for cs in callsign_matches})[:4]

    # BDA
    bda_matches = _BDA_RE.findall(text)
    if bda_matches:
        bda_list = [{"action": m[0].lower(), "count": int(m[1])} for m in bda_matches[:6]]
        result["bda"] = bda_list
        kia = sum(
            b["count"] for b in bda_list
            if any(kw in b["action"] for kw in ("kill", "kia", "dead", "elim", "neutral"))
        )
        if kia > 0:
            result["bda_kia"] = kia

    # Time on target
    tot_matches = _TOT_RE.findall(text)
    if tot_matches:
        result["time_on_target"] = [f"{m[0]}{m[1].upper()}" for m in tot_matches[:2]]

    # Weapons
    weapons = list({w for w in _WEAPON_RE.findall(text)})
    if weapons:
        result["weapons"] = weapons[:8]

    # Bearing / distance
    bearing_matches = _BEARING_RE.findall(text)
    if bearing_matches:
        result["bearing_distance"] = [
            {"km": float(b[0]), "direction": b[1].upper()}
            for b in bearing_matches[:3]
        ]

    # Casualties
    casualty_matches = _CASUALTY_RE.findall(text)
    if casualty_matches:
        result["casualties"] = [
            {"count": int(c[0]), "type": c[1].lower()}
            for c in casualty_matches[:6]
        ]

    # Priority indicators
    flash_matches = _FLASH_RE.findall(text)
    if flash_matches:
        result["priority_indicators"] = list({f.upper() for f in flash_matches})

    # Scoring
    scored_fields = {"grid_refs", "call_signs", "bda", "time_on_target", "weapons", "bearing_distance", "casualties"}
    result["sigact_score"] = sum(1 for f in scored_fields if f in result)
    result["is_sigact"] = result["sigact_score"] >= 2

    return result


def correlate_with_sensors(
    event: dict,
    recent_events: List[dict],
    radius_km: float = 0.5,
    window_minutes: int = 30,
) -> Dict[str, Any]:
    """
    Check if a SIGACT-flagged event has sensor corroboration.

    Scans recent events for FIRMS fire detections and ADS-B loiter patterns
    within radius_km and window_minutes. Returns corroboration details and
    a confidence_boost value.

    Three-source (Telegram + FIRMS + ADS-B) = tier-1 strike confirmation.
    """
    from datetime import datetime

    lat = event.get("lat")
    lng = event.get("lng")
    if not lat or not lng:
        return {"corroborated": False, "confidence_boost": 0}

    try:
        ts = datetime.fromisoformat(str(event.get("timestamp", "")).replace("Z", "+00:00"))
    except Exception:
        return {"corroborated": False, "confidence_boost": 0}

    firms_hits: List[dict] = []
    adsb_hits: List[dict] = []

    for evt in recent_events:
        if evt.get("id") == event.get("id"):
            continue
        try:
            et = datetime.fromisoformat(str(evt.get("timestamp", "")).replace("Z", "+00:00"))
            dt_min = abs((et - ts).total_seconds()) / 60
            if dt_min > window_minutes:
                continue
        except Exception:
            continue

        elat = evt.get("lat")
        elng = evt.get("lng")
        if not elat or not elng:
            continue

        dist = _haversine_km(float(lat), float(lng), float(elat), float(elng))
        if dist > radius_km:
            continue

        src = str(evt.get("source") or "").lower()
        hit = {"source": evt.get("source"), "dist_km": round(dist, 3), "dt_min": round(dt_min, 1)}
        if "firms" in src or "fire" in src:
            firms_hits.append(hit)
        elif "adsb" in src or "fr24" in src or "flight" in src or "ais" in src:
            adsb_hits.append(hit)

    three_source = len(firms_hits) > 0 and len(adsb_hits) > 0
    corroborated = len(firms_hits) > 0 or len(adsb_hits) > 0
    sources = (["FIRMS"] if firms_hits else []) + (["ADS-B"] if adsb_hits else [])

    return {
        "corroborated": corroborated,
        "three_source": three_source,
        "firms_hits": firms_hits[:3],
        "adsb_hits": adsb_hits[:3],
        "corroboration_sources": sources,
        "confidence_boost": 30 if three_source else 15 if corroborated else 0,
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))
