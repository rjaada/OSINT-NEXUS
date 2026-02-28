"""
OSINT NEXUS — Real-time Intelligence Engine
"""

import asyncio
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple

import feedparser
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from analyst import generate_analyst_report

app = FastAPI(title="OSINT Nexus Engine v3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/tmp/osint_nexus_media"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
TELEGRAM_MEDIA_DIR = MEDIA_DIR / "telegram"
TELEGRAM_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_TELEGRAM_MEDIA = os.getenv("DOWNLOAD_TELEGRAM_MEDIA", "true").lower() in ("1", "true", "yes", "on")
TELEGRAM_LOOKBACK_POSTS = int(os.getenv("TELEGRAM_LOOKBACK_POSTS", "20"))
TELEGRAM_MAX_NEW_PER_POLL = int(os.getenv("TELEGRAM_MAX_NEW_PER_POLL", "8"))

DB_PATH = os.getenv("OSINT_DB_PATH", "/tmp/osint_nexus.db")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
GEOCODE_URL = os.getenv("GEOCODE_URL", "https://nominatim.openstreetmap.org/search")

app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, msg: dict):
        text = json.dumps(msg)
        dead = []
        for ws in self.connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()

# In-memory runtime state
seen_articles: set = set()
seen_telegram_posts: set = set()
seen_alerts: set = set()

# Event runtime buffers
events_buffer: list = []
events_history: list = []
last_aircraft: list = []
incident_index: Dict[str, dict] = {}
incident_lock = Lock()

# Ops metrics
metrics = {
    "rss_polls": 0,
    "telegram_polls": 0,
    "flight_polls": 0,
    "red_alert_polls": 0,
    "rss_errors": 0,
    "telegram_errors": 0,
    "flight_errors": 0,
    "red_alert_errors": 0,
    "db_writes": 0,
    "dedup_dropped": 0,
    "watchdog_warnings": 0,
    "last_success": {
        "rss": None,
        "telegram": None,
        "flights": None,
        "red_alert": None,
    },
}

_start_time = time.time()
_db: Optional[sqlite3.Connection] = None


SOURCE_RELIABILITY = {
    "Red Alert": 95,
    "Reuters": 82,
    "BBC News": 80,
    "CBS News": 75,
    "The Guardian": 72,
    "Times of Israel": 72,
    "Al Jazeera": 68,
    "AJ Mubasher (TG)": 60,
    "Roaa War Studies (TG)": 55,
    "FR24-MIL": 65,
}

BBOX = "40.0,12.0,30.0,63.0"
FR24_URL = (
    "https://data-cloud.flightradar24.com/zones/fcgi/feed.js"
    f"?bounds={BBOX}&faa=1&satellite=1&mlat=1&flarm=1&adsb=1"
    "&gnd=0&air=1&vehicles=0&estimated=1&maxage=14400&gliders=0&stats=1"
)

MILITARY_PREFIXES = {
    "RCH", "REACH", "ATLAS", "JAKE", "SCOTT", "DOVER", "MCCH", "TROP",
    "FURY", "WOLF", "VIPER", "RAZOR", "SWORD", "DEMON", "RAVEN", "HAWK",
    "EAGLE", "SNAKE", "COBRA", "TIGER", "LANCE", "SABRE", "AVENGER",
    "MAGMA", "SIRIUS", "DARK", "IRON", "HUNT", "JOLLY", "PEDRO",
    "KING", "GHOST", "CHAOS", "HOBO", "SPAR", "VENUS", "SOLAR",
    "NAVY", "VMGR", "TOPGN", "GRIZZLY", "COWBOY", "TOMCAT",
    "NATO", "NATON", "LFT", "GAF", "RAF", "FAF", "MEDEVAC",
    "AUST", "CAN", "BELG", "DUTCHF", "SENTRY", "AWACS", "HOGAN",
    "SHELL", "ARCO", "TEXAC", "QUID", "JADE", "ESSO", "GULF",
    "DUSTOFF", "LANCER", "DUKE", "BEAST", "FALCN", "VAPOR",
}

CONFLICT_KEYWORDS = [
    "israel", "iran", "hamas", "hezbollah", "idf", "netanyahu", "beirut", "gaza", "lebanon", "houthi",
    "strike", "airstrike", "drone", "missile", "attack", "war", "military", "troops", "ceasefire", "sanctions",
    "nuclear", "irgc", "mossad", "centcom", "pentagon", "tehran", "tel aviv", "west bank", "jerusalem",
    "syria", "iraq", "yemen", "red sea", "hormuz", "naval", "qatar", "bahrain", "saudi", "uae", "kuwait", "oman",
    "pakistan", "afghanistan", "مسيّرة", "مسيرة", "صاروخ", "قصف", "هجوم", "استهداف", "تل أبيب", "طهران", "الضفة",
    "غزة", "إيران", "إسرائيلي", "إسرائيل", "العراق", "اليمن", "لبنان",
]

EVENT_TYPE_KEYWORDS_AR = {
    "STRIKE": ["قصف", "استهداف", "غارة", "انفجار", "ضربة", "صاروخ", "مسيرة", "مسيّرة"],
    "MOVEMENT": ["تحرك", "تحريك", "انتشار", "تعزيزات", "حشد", "قافلة", "أسطول"],
    "NOTAM": ["إغلاق المجال", "تحذير ملاحي", "إغلاق الأجواء", "تحذير جوي"],
    "CLASH": ["اشتباك", "اشتباكات", "تبادل إطلاق", "مواجهة"],
    "CRITICAL": ["حرب شاملة", "إعلان حرب", "نووي", "تصعيد غير مسبوق"],
}

RSS_FEEDS_EN = [
    {"name": "Reuters World", "url": "https://feeds.reuters.com/Reuters/worldNews", "source": "Reuters"},
    {"name": "Al Jazeera English", "url": "https://www.aljazeera.com/xml/rss/all.xml", "source": "Al Jazeera"},
    {"name": "BBC World", "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC News"},
    {"name": "CBS News World", "url": "https://www.cbsnews.com/latest/rss/world", "source": "CBS News"},
    {"name": "The Guardian World", "url": "https://www.theguardian.com/world/rss", "source": "The Guardian"},
    {"name": "Times of Israel", "url": "https://www.timesofisrael.com/feed", "source": "Times of Israel"},
]

TELEGRAM_CHANNELS = [
    {"slug": "ajMubasher", "source": "AJ Mubasher (TG)", "lang": "ar"},
    {"slug": "RoaaWarStudies", "source": "Roaa War Studies (TG)", "lang": "ar"},
]

ISRAEL_CITY_COORDS = {
    "תל אביב": (32.07, 34.78), "tel aviv": (32.07, 34.78),
    "ירושלים": (31.77, 35.21), "jerusalem": (31.77, 35.21),
    "חיפה": (32.79, 34.99), "haifa": (32.79, 34.99),
    "אשקלון": (31.66, 34.57), "ashkelon": (31.66, 34.57),
    "sderot": (31.52, 34.60),
}

PLACE_COORDS = {
    "tehran": (35.6892, 51.3890), "طهران": (35.6892, 51.3890),
    "tel aviv": (32.0853, 34.7818), "تل أبيب": (32.0853, 34.7818),
    "haifa": (32.7940, 34.9896), "حيفا": (32.7940, 34.9896),
    "jerusalem": (31.7683, 35.2137), "القدس": (31.7683, 35.2137),
    "gaza": (31.5017, 34.4668), "غزة": (31.5017, 34.4668),
    "west bank": (31.95, 35.20), "الضفة": (31.95, 35.20),
    "beirut": (33.8938, 35.5018), "بيروت": (33.8938, 35.5018),
    "damascus": (33.5138, 36.2765), "دمشق": (33.5138, 36.2765),
    "baghdad": (33.3152, 44.3661), "بغداد": (33.3152, 44.3661),
    "bahrain": (26.0667, 50.5577), "البحرين": (26.0667, 50.5577),
    "doha": (25.2854, 51.5310), "الدوحة": (25.2854, 51.5310),
    "abu dhabi": (24.4539, 54.3773), "أبوظبي": (24.4539, 54.3773),
    "dubai": (25.2048, 55.2708), "دبي": (25.2048, 55.2708),
    "muscat": (23.5880, 58.3829), "مسقط": (23.5880, 58.3829),
    "hormuz": (26.5667, 56.2500), "هرمز": (26.5667, 56.2500),
    "kuwait": (29.3759, 47.9774), "الكويت": (29.3759, 47.9774),
    "riyadh": (24.7136, 46.6753), "الرياض": (24.7136, 46.6753),
    "iran": (32.0, 53.0), "إيران": (32.0, 53.0),
    "israel": (31.0, 35.0), "إسرائيل": (31.0, 35.0),
}

geocode_cache: Dict[str, Tuple[float, float]] = {}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            incident_id TEXT,
            type TEXT,
            desc TEXT,
            lat REAL,
            lng REAL,
            source TEXT,
            timestamp TEXT,
            url TEXT,
            video_url TEXT,
            lang TEXT,
            confidence_score INTEGER,
            confidence_reason TEXT,
            observed_facts TEXT,
            model_inference TEXT,
            video_assessment TEXT,
            video_confidence TEXT,
            video_clues TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_incident ON events(incident_id)")
    conn.commit()
    return conn


def load_recent_events(limit: int = 400):
    if _db is None:
        return
    rows = _db.execute(
        """
        SELECT * FROM events
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    events_history.clear()
    incident_index.clear()
    for row in reversed(rows):
        e = {
            "id": row["id"],
            "incident_id": row["incident_id"],
            "type": row["type"],
            "desc": row["desc"],
            "lat": row["lat"],
            "lng": row["lng"],
            "source": row["source"],
            "timestamp": row["timestamp"],
            "url": row["url"],
            "video_url": row["video_url"],
            "lang": row["lang"],
            "confidence_score": row["confidence_score"],
            "confidence_reason": row["confidence_reason"],
            "observed_facts": json.loads(row["observed_facts"] or "[]"),
            "model_inference": json.loads(row["model_inference"] or "[]"),
            "video_assessment": row["video_assessment"],
            "video_confidence": row["video_confidence"],
            "video_clues": json.loads(row["video_clues"] or "[]"),
        }
        events_history.append(e)
        incident_id = e.get("incident_id")
        if incident_id:
            incident_index[incident_id] = e


def persist_event(event: dict):
    if _db is None:
        return
    _db.execute(
        """
        INSERT OR REPLACE INTO events (
            id, incident_id, type, desc, lat, lng, source, timestamp, url, video_url,
            lang, confidence_score, confidence_reason, observed_facts, model_inference,
            video_assessment, video_confidence, video_clues, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.get("id"),
            event.get("incident_id"),
            event.get("type"),
            event.get("desc"),
            event.get("lat"),
            event.get("lng"),
            event.get("source"),
            event.get("timestamp"),
            event.get("url"),
            event.get("video_url"),
            event.get("lang"),
            int(event.get("confidence_score", 0)),
            event.get("confidence_reason"),
            json.dumps(event.get("observed_facts", []), ensure_ascii=False),
            json.dumps(event.get("model_inference", []), ensure_ascii=False),
            event.get("video_assessment"),
            event.get("video_confidence"),
            json.dumps(event.get("video_clues", []), ensure_ascii=False),
            utc_now_iso(),
        ),
    )
    _db.commit()
    metrics["db_writes"] += 1


def is_military(callsign: str, icao24: str) -> bool:
    if not callsign:
        return False
    cs = callsign.strip().upper()
    return any(cs.startswith(p) for p in MILITARY_PREFIXES)


def _parse_iso(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _extract_source(event: dict) -> str:
    desc = str(event.get("desc", ""))
    m = re.match(r"^\[(.+?)\]", desc)
    if m:
        return m.group(1)
    return str(event.get("source", "Unknown"))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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
    return hashlib.md5(key.encode()).hexdigest()


def classify_event(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()

    for etype, words in EVENT_TYPE_KEYWORDS_AR.items():
        if any(w in text for w in words):
            return etype

    if any(kw in text for kw in ["war", "invasion", "declaration of war", "martial law", "all-out", "nuclear strike"]):
        return "CRITICAL"
    if any(kw in text for kw in ["airstrike", "bombed", "strike", "explosion", "blast", "missile", "drone"]):
        return "STRIKE"
    if any(kw in text for kw in ["troops", "convoy", "vessel", "fleet", "deploy", "movement", "advance"]):
        return "MOVEMENT"
    if any(kw in text for kw in ["airspace", "notam", "flight ban", "restricted", "gps jam", "naval warning"]):
        return "NOTAM"
    return "CLASH"


def extract_place_candidates(text: str) -> List[str]:
    t = (text or "").lower()
    hits = []
    for p in PLACE_COORDS:
        if p in t:
            hits.append(p)
    return hits


async def geocode_place(place: str) -> Optional[Tuple[float, float]]:
    if place in geocode_cache:
        return geocode_cache[place]
    try:
        headers = {"User-Agent": "OSINT-Nexus/1.0 (research dashboard)"}
        params = {"q": place, "format": "json", "limit": 1}
        async with httpx.AsyncClient(timeout=8, headers=headers) as client:
            r = await client.get(GEOCODE_URL, params=params)
            if r.status_code != 200:
                return None
            data = r.json()
            if not data:
                return None
            lat = float(data[0]["lat"])
            lng = float(data[0]["lon"])
            geocode_cache[place] = (lat, lng)
            return lat, lng
    except Exception:
        return None


async def call_ollama_json(prompt: str, retries: int = 2) -> Optional[dict]:
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    OLLAMA_URL,
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.1},
                    },
                )
                resp.raise_for_status()
                raw = str(resp.json().get("response", "{}")).strip()
                if raw.startswith("```"):
                    raw = raw.strip("`")
                    raw = raw.replace("json", "", 1).strip()
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            if attempt == retries:
                print(f"[OLLAMA] JSON call failed: {e}")
            await asyncio.sleep(0.35 * (attempt + 1))
    return None


async def geolocate_with_ai(title: str, summary: str) -> Optional[dict]:
    prompt = f"""You are a geolocation extraction engine.
Return ONLY strict JSON with keys:
lat (number), lng (number), severity_1_to_10 (integer), event_type (STRIKE|MOVEMENT|CLASH|NOTAM|CRITICAL),
insufficient_evidence (boolean), observed_facts (array of short strings), model_inference (array of short strings).

Title: {title}
Summary: {summary}
"""
    result = await call_ollama_json(prompt, retries=2)
    if not result:
        return None
    try:
        lat = float(result.get("lat", 0.0))
        lng = float(result.get("lng", 0.0))
        severity = int(result.get("severity_1_to_10", 3))
        event_type = str(result.get("event_type", "CLASH")).upper()
        insufficient = bool(result.get("insufficient_evidence", False))
        observed = result.get("observed_facts") if isinstance(result.get("observed_facts"), list) else []
        inferred = result.get("model_inference") if isinstance(result.get("model_inference"), list) else []
        if event_type not in {"STRIKE", "MOVEMENT", "CLASH", "NOTAM", "CRITICAL"}:
            event_type = "CLASH"
        if abs(lat) > 90 or abs(lng) > 180:
            return None
        return {
            "lat": lat,
            "lng": lng,
            "severity": max(1, min(10, severity)),
            "type": event_type,
            "insufficient_evidence": insufficient,
            "observed_facts": [str(x)[:120] for x in observed[:4]],
            "model_inference": [str(x)[:120] for x in inferred[:4]],
        }
    except Exception:
        return None


async def geolocate_event(title: str, summary: str, fallback_seed: str, allow_ai: bool = True) -> dict:
    """Geolocation chain: place dictionary -> geocoder -> AI -> deterministic fallback."""
    observed: List[str] = []
    inferred: List[str] = []

    combined = f"{title} {summary}"
    candidates = extract_place_candidates(combined)
    for place in candidates:
        if place in PLACE_COORDS:
            lat, lng = PLACE_COORDS[place]
            observed.append(f"Matched place mention: {place}")
            return {
                "lat": lat,
                "lng": lng,
                "type": classify_event(title, summary),
                "severity": 5,
                "observed_facts": observed,
                "model_inference": ["Location estimated from explicit place-name match."],
                "insufficient_evidence": False,
                "geo_method": "place-dict",
            }

    for place in candidates[:2]:
        geo = await geocode_place(place)
        if geo:
            observed.append(f"Geocoded place mention: {place}")
            return {
                "lat": geo[0],
                "lng": geo[1],
                "type": classify_event(title, summary),
                "severity": 4,
                "observed_facts": observed,
                "model_inference": ["Location estimated via geocoder for named place."],
                "insufficient_evidence": False,
                "geo_method": "geocoder",
            }

    if allow_ai:
        ai = await geolocate_with_ai(title, summary)
        if ai and not ai.get("insufficient_evidence"):
            return {
                "lat": ai["lat"],
                "lng": ai["lng"],
                "type": "CRITICAL" if ai["severity"] >= 8 else ai["type"],
                "severity": ai["severity"],
                "observed_facts": ai.get("observed_facts", []),
                "model_inference": ai.get("model_inference", []),
                "insufficient_evidence": False,
                "geo_method": "ollama",
            }

    lat = 31.5 + (hash(fallback_seed) % 14) * 0.22
    lng = 34.8 + (hash(fallback_seed[::-1]) % 14) * 0.22
    inferred.append("Insufficient location evidence; fallback coordinate used.")
    return {
        "lat": lat,
        "lng": lng,
        "type": classify_event(title, summary),
        "severity": 3,
        "observed_facts": observed,
        "model_inference": inferred,
        "insufficient_evidence": True,
        "geo_method": "fallback",
    }


def parse_telegram_posts(html_text: str, channel_slug: str) -> list:
    soup = BeautifulSoup(html_text, "html.parser")
    posts = []
    for message in soup.select("div.tgme_widget_message"):
        data_post = message.get("data-post", "")
        if not data_post.startswith(f"{channel_slug}/"):
            continue

        post_id = data_post.split("/")[-1]
        text_node = message.select_one("div.tgme_widget_message_text")
        text = text_node.get_text(" ", strip=True) if text_node else ""
        video_node = (
            message.select_one("video.tgme_widget_message_video")
            or message.select_one("video.js-message_video")
            or message.select_one("video")
        )
        video_src = video_node.get("src") if video_node else None
        has_video = bool(video_node or message.select_one(".tgme_widget_message_video_player") or message.select_one(".tgme_widget_message_video_wrap"))
        if len(text) < 15 and not has_video:
            continue

        date_node = message.select_one("a.tgme_widget_message_date")
        url = date_node.get("href", f"https://t.me/{data_post}") if date_node else f"https://t.me/{data_post}"
        time_node = message.select_one("time")
        ts = time_node.get("datetime") if time_node else utc_now_iso()

        posts.append({
            "post_id": post_id,
            "text": text,
            "url": url,
            "timestamp": ts,
            "has_video": has_video,
            "video_src": video_src,
        })

    def post_sort_key(item: dict) -> int:
        try:
            return int(item["post_id"])
        except Exception:
            return 0

    posts.sort(key=post_sort_key)
    return posts


def download_telegram_video(post_url: str, event_id: str) -> Optional[str]:
    if not DOWNLOAD_TELEGRAM_MEDIA:
        return None
    try:
        out_tpl = str(TELEGRAM_MEDIA_DIR / f"{event_id}.%(ext)s")
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--socket-timeout", "15",
            "--retries", "2",
            "-f", "mp4/best[ext=mp4]/best",
            "-o", out_tpl,
            post_url,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        for ext in ("mp4", "webm", "mkv", "mov"):
            candidate = TELEGRAM_MEDIA_DIR / f"{event_id}.{ext}"
            if candidate.exists():
                return f"/media/telegram/{candidate.name}"
    except Exception:
        return None
    return None


def infer_video_metadata(desc: str, has_video: bool, geo_method: str) -> dict:
    if not has_video:
        return {}

    clues = []
    lower = (desc or "").lower()
    for place in extract_place_candidates(lower):
        clues.append(f"place_mention:{place}")

    if geo_method in {"place-dict", "geocoder"} and clues:
        tag = "LIKELY_RELATED"
        confidence = "MEDIUM"
    elif geo_method == "ollama" and clues:
        tag = "LIKELY_RELATED"
        confidence = "HIGH"
    elif clues:
        tag = "UNVERIFIED_VISUAL"
        confidence = "LOW"
    else:
        tag = "MISMATCH"
        confidence = "LOW"

    return {
        "video_assessment": tag,
        "video_confidence": confidence,
        "video_clues": clues[:4],
    }


def is_relevant(entry) -> bool:
    text = (
        getattr(entry, "title", "") + " " +
        getattr(entry, "summary", "") + " " +
        getattr(entry, "description", "")
    ).lower()
    return any(kw in text for kw in CONFLICT_KEYWORDS)


def build_incident_id(event: dict) -> str:
    text = normalize_desc(event.get("desc", ""))
    tokens = " ".join(text.split()[:10])
    lat_b = round(float(event.get("lat", 0.0)), 1)
    lng_b = round(float(event.get("lng", 0.0)), 1)
    typ = str(event.get("type", "CLASH"))
    key = f"{typ}|{lat_b}|{lng_b}|{tokens}"
    return "inc_" + hashlib.md5(key.encode()).hexdigest()[:14]


def should_merge_with_existing(event: dict) -> Optional[str]:
    now_ts = _parse_iso(str(event.get("timestamp", utc_now_iso())))
    new_norm = normalize_desc(event.get("desc", ""))
    for incident_id, existing in list(incident_index.items()):
        if existing.get("type") != event.get("type"):
            continue
        old_ts = _parse_iso(str(existing.get("timestamp", utc_now_iso())))
        if abs((now_ts - old_ts).total_seconds()) > 12 * 60:
            continue
        if _haversine_km(float(existing.get("lat", 0.0)), float(existing.get("lng", 0.0)), float(event.get("lat", 0.0)), float(event.get("lng", 0.0))) > 90:
            continue
        old_norm = normalize_desc(existing.get("desc", ""))
        overlap = len(set(new_norm.split()) & set(old_norm.split()))
        if overlap >= 4:
            return incident_id
    return None


def push_event_buffer(event: dict):
    events_buffer.append({
        "type": event.get("type"),
        "desc": event.get("desc"),
        "source": _extract_source(event),
    })
    if len(events_buffer) > 80:
        events_buffer[:] = events_buffer[-80:]


async def ingest_event(event: dict):
    """Centralized ingest path: dedup, persistence, history, broadcast."""
    with incident_lock:
        merge_id = should_merge_with_existing(event)
        if merge_id:
            metrics["dedup_dropped"] += 1
            existing = incident_index.get(merge_id)
            if existing:
                old_sources = set(existing.get("corroborating_sources", []))
                old_sources.add(_extract_source(event))
                existing["corroborating_sources"] = sorted(old_sources)
                existing["confidence_score"] = min(100, int(existing.get("confidence_score", 45)) + 5)
                existing["confidence_reason"] = f"Merged duplicate reports ({len(old_sources)} sources)"
                persist_event(existing)
            return

        incident_id = build_incident_id(event)
        event["incident_id"] = incident_id
        incident_index[incident_id] = event

    events_history.append(event)
    if len(events_history) > 1200:
        events_history[:] = events_history[-1200:]

    persist_event(event)
    push_event_buffer(event)
    await manager.broadcast({"type": "NEW_EVENT", "data": event})


def assess_confidence(event: dict, nearby: list, age_min: float) -> Tuple[int, str, List[str]]:
    src = _extract_source(event)
    base = SOURCE_RELIABILITY.get(src, 50)

    corroborating = sorted({_extract_source(x) for x in nearby if _extract_source(x) != src})
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
    source = _extract_source(event)
    if source.lower() == "red alert":
        return "<2m"
    lat = float(event.get("lat", 31.77))
    lng = float(event.get("lng", 35.21))
    dist = _haversine_km(lat, lng, 31.77, 35.21)
    if dist <= 120:
        return "2-5m"
    if dist <= 350:
        return "5-10m"
    if dist <= 900:
        return "10-20m"
    return ">20m"


def geolocate_alert(city: str) -> tuple:
    lower = city.lower().strip()
    for name, coords in ISRAEL_CITY_COORDS.items():
        if name in lower or lower in name:
            return coords
    return (31.77 + (hash(city) % 10) * 0.05, 35.0 + (hash(city) % 5) * 0.05)


async def poll_flights():
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        while True:
            await asyncio.sleep(8)
            metrics["flight_polls"] += 1
            try:
                resp = await client.get(FR24_URL)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                aircraft_list = []
                for key, val in data.items():
                    if key in ["full_count", "version", "stats"]:
                        continue
                    if not isinstance(val, list) or len(val) < 14:
                        continue
                    icao = str(val[0])
                    lat = val[1]
                    lng = val[2]
                    heading = val[3]
                    alt_ft = val[4]
                    speed_kts = val[5]
                    ac_type = str(val[8])
                    callsign = str(val[13] or val[16] or icao).strip()
                    alt_m = round(alt_ft * 0.3048)
                    speed_m = round(speed_kts * 0.51444)
                    is_mil = is_military(callsign, icao) or is_military(ac_type, "")
                    aircraft_list.append({
                        "id": key,
                        "callsign": callsign.upper(),
                        "country": "Unknown",
                        "lat": lat,
                        "lng": lng,
                        "alt": alt_m,
                        "speed": speed_m,
                        "heading": heading,
                        "military": is_mil,
                    })
                aircraft_list = aircraft_list[:150]
                if aircraft_list:
                    last_aircraft[:] = aircraft_list
                    await manager.broadcast({"type": "AIRCRAFT_UPDATE", "data": aircraft_list, "ts": time.time()})
                    metrics["last_success"]["flights"] = utc_now_iso()
            except Exception as e:
                metrics["flight_errors"] += 1
                print(f"[FR24] Error: {e}")


async def poll_rss():
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        while True:
            metrics["rss_polls"] += 1
            for feed_cfg in RSS_FEEDS_EN:
                try:
                    resp = await client.get(feed_cfg["url"])
                    if resp.status_code != 200:
                        continue
                    parsed = feedparser.parse(resp.text)
                    for entry in parsed.entries:
                        aid = article_id(entry)
                        if aid in seen_articles:
                            continue
                        if not is_relevant(entry):
                            continue
                        seen_articles.add(aid)

                        title = getattr(entry, "title", "No title")
                        summary = getattr(entry, "summary", getattr(entry, "description", ""))
                        summary = re.sub(r"<[^>]+>", "", summary)[:300]

                        geo = await geolocate_event(title, summary, aid)
                        event = {
                            "id": f"rss_{aid[:10]}",
                            "type": geo["type"],
                            "desc": f"[{feed_cfg['source']}] {title}",
                            "lat": geo["lat"],
                            "lng": geo["lng"],
                            "source": feed_cfg["source"],
                            "timestamp": utc_now_iso(),
                            "insufficient_evidence": geo["insufficient_evidence"],
                            "observed_facts": geo["observed_facts"],
                            "model_inference": geo["model_inference"],
                        }
                        await ingest_event(event)
                        await asyncio.sleep(0.2)
                    metrics["last_success"]["rss"] = utc_now_iso()
                except Exception as e:
                    metrics["rss_errors"] += 1
                    print(f"[RSS] Error: {e}")
            await asyncio.sleep(60)


async def poll_telegram():
    headers = {"User-Agent": "Mozilla/5.0 (OSINT-Nexus/1.0)"}
    async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
        while True:
            metrics["telegram_polls"] += 1
            for cfg in TELEGRAM_CHANNELS:
                try:
                    url = f"https://t.me/s/{cfg['slug']}"
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    posts = parse_telegram_posts(resp.text, cfg["slug"])
                    if not posts:
                        continue

                    candidates = posts[-max(1, TELEGRAM_LOOKBACK_POSTS):]
                    pending = [p for p in candidates if f"tg_{cfg['slug']}_{p['post_id']}" not in seen_telegram_posts]
                    for p in pending[-max(1, TELEGRAM_MAX_NEW_PER_POLL):]:
                        pid = f"tg_{cfg['slug']}_{p['post_id']}"
                        seen_telegram_posts.add(pid)

                        text = p["text"][:500]
                        geo = await geolocate_event(f"[{cfg['source']}] Telegram Update", text, pid, allow_ai=False)
                        event = {
                            "id": pid,
                            "type": geo["type"],
                            "desc": f"[{cfg['source']}] {text[:240]}",
                            "lat": geo["lat"],
                            "lng": geo["lng"],
                            "source": cfg["source"],
                            "timestamp": p["timestamp"],
                            "url": p["url"],
                            "lang": cfg["lang"],
                            "insufficient_evidence": geo["insufficient_evidence"],
                            "observed_facts": geo["observed_facts"],
                            "model_inference": geo["model_inference"],
                        }
                        if p.get("has_video"):
                            local_video = await asyncio.to_thread(download_telegram_video, p["url"], pid)
                            event["video_url"] = local_video or p.get("video_src") or p["url"]
                            event["has_video"] = True

                        video_meta = infer_video_metadata(event.get("desc", ""), bool(event.get("has_video")), geo.get("geo_method", "fallback"))
                        event.update(video_meta)

                        await ingest_event(event)

                    if len(seen_telegram_posts) > 6000:
                        seen_telegram_posts.clear()
                    metrics["last_success"]["telegram"] = utc_now_iso()
                except Exception as e:
                    metrics["telegram_errors"] += 1
                    print(f"[TELEGRAM] Error {cfg['slug']}: {e}")
            await asyncio.sleep(8)


RED_ALERT_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"


async def poll_red_alert():
    headers = {
        "Referer": "https://www.oref.org.il/",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0",
    }
    async with httpx.AsyncClient(timeout=5, headers=headers) as client:
        while True:
            await asyncio.sleep(3)
            metrics["red_alert_polls"] += 1
            try:
                resp = await client.get(RED_ALERT_URL)
                if resp.status_code != 200 or not resp.text.strip():
                    continue
                try:
                    data = resp.json()
                except Exception:
                    continue
                if not data:
                    continue

                alert_id = data.get("id", "")
                if alert_id in seen_alerts:
                    continue
                seen_alerts.add(alert_id)

                alert_title = data.get("title", "Red Alert")
                cities = data.get("data", [])
                ts_now = utc_now_iso()

                for city in cities:
                    lat, lng = geolocate_alert(city)
                    eid = hashlib.md5(f"{alert_id}_{city}".encode()).hexdigest()[:10]
                    event = {
                        "id": f"alert_{eid}",
                        "type": "STRIKE",
                        "desc": f"[Red Alert] {alert_title}: {city}",
                        "lat": lat,
                        "lng": lng,
                        "source": "Red Alert",
                        "timestamp": ts_now,
                        "insufficient_evidence": False,
                        "observed_facts": ["Official civil-defense alert feed"],
                        "model_inference": [],
                    }
                    await ingest_event(event)
                metrics["last_success"]["red_alert"] = utc_now_iso()
            except Exception as e:
                metrics["red_alert_errors"] += 1
                print(f"[RED ALERT] Error: {e}")


def _watchdog_check() -> list:
    warnings = []
    now = datetime.now(timezone.utc)
    for feed in ["rss", "telegram", "flights", "red_alert"]:
        ts = metrics["last_success"].get(feed)
        if not ts:
            warnings.append(f"{feed}: no successful poll yet")
            continue
        age = (now - _parse_iso(ts)).total_seconds()
        threshold = 240 if feed in {"rss", "telegram"} else 90
        if age > threshold:
            warnings.append(f"{feed}: stale ({int(age)}s)")
    metrics["watchdog_warnings"] = len(warnings)
    return warnings


@app.on_event("startup")
async def startup_event():
    global _start_time, _db
    _start_time = time.time()
    _db = init_db()
    load_recent_events()

    asyncio.create_task(poll_flights())
    asyncio.create_task(poll_rss())
    asyncio.create_task(poll_telegram())
    asyncio.create_task(poll_red_alert())
    print("[OSINT] Engine started — pollers + DB persistence active")


@app.get("/")
async def root():
    return {"status": "OSINT Engine v3 Running", "clients": len(manager.connections), "events": len(events_history)}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "clients": len(manager.connections),
        "events_buffered": len(events_buffer),
        "events_persisted": len(events_history),
        "watchdog_warnings": _watchdog_check(),
    }


@app.get("/api/ops/health")
async def ops_health():
    warnings = _watchdog_check()
    return {
        "status": "nominal" if not warnings else "degraded",
        "uptime_seconds": int(time.time() - _start_time),
        "metrics": metrics,
        "warnings": warnings,
        "queues": {
            "events_history": len(events_history),
            "events_buffer": len(events_buffer),
            "seen_articles": len(seen_articles),
            "seen_telegram_posts": len(seen_telegram_posts),
        },
    }


@app.get("/api/stats")
async def stats():
    mil_count = sum(1 for a in last_aircraft if a.get("military"))
    return {
        "events_total": len(events_history),
        "aircraft_tracked": len(last_aircraft),
        "military_aircraft": mil_count,
        "sources_active": len(RSS_FEEDS_EN) + len(TELEGRAM_CHANNELS) + 1,
        "clients": len(manager.connections),
        "uptime_seconds": int(time.time() - _start_time),
        "dedup_dropped": metrics["dedup_dropped"],
    }


@app.get("/api/events")
async def get_events(limit: int = 80):
    limit = min(max(limit, 1), 300)
    return events_history[-limit:][::-1]


@app.get("/api/sources/recent")
async def sources_recent(limit: int = 150):
    limit = min(max(limit, 1), 300)
    rows = events_history[-limit:][::-1]
    grouped = defaultdict(int)
    for r in rows:
        grouped[_extract_source(r)] += 1
    return {
        "items": rows,
        "counts_by_source": dict(sorted(grouped.items(), key=lambda x: x[1], reverse=True)),
        "generated_at": utc_now_iso(),
    }


@app.get("/api/alerts/assessment")
async def alert_assessment(limit: int = 40):
    if not events_history:
        return []
    limit = min(max(limit, 1), 100)
    now = datetime.now(timezone.utc)
    recent = events_history[-500:]

    by_bucket = defaultdict(list)
    for e in recent:
        lat_b = round(float(e.get("lat", 0.0)), 1)
        lng_b = round(float(e.get("lng", 0.0)), 1)
        by_bucket[(lat_b, lng_b)].append(e)

    candidates = [e for e in recent if e.get("type") in ("STRIKE", "CRITICAL")]
    cards = []

    for event in reversed(candidates):
        ts = _parse_iso(str(event.get("timestamp", utc_now_iso())))
        age_min = max(0.0, (now - ts).total_seconds() / 60.0)
        lat_b = round(float(event.get("lat", 0.0)), 1)
        lng_b = round(float(event.get("lng", 0.0)), 1)
        nearby = by_bucket[(lat_b, lng_b)]

        score, reason, corroborating = assess_confidence(event, nearby, age_min)
        confidence = "HIGH" if score >= 80 else ("MEDIUM" if score >= 55 else "LOW")

        cards.append({
            "id": event.get("id"),
            "incident_id": event.get("incident_id"),
            "type": event.get("type"),
            "desc": event.get("desc"),
            "timestamp": event.get("timestamp"),
            "lat": event.get("lat"),
            "lng": event.get("lng"),
            "source": _extract_source(event),
            "confidence_score": score,
            "confidence": confidence,
            "confidence_reason": reason,
            "eta_band": eta_band(event),
            "age_minutes": round(age_min, 1),
            "corroborating_sources": corroborating,
            "video_url": event.get("video_url"),
            "video_assessment": event.get("video_assessment"),
            "video_confidence": event.get("video_confidence"),
            "video_clues": event.get("video_clues", []),
            "observed_facts": event.get("observed_facts", []),
            "model_inference": event.get("model_inference", []),
            "insufficient_evidence": bool(event.get("insufficient_evidence", False)),
        })

    return cards[:limit]


@app.get("/api/analyst")
async def analyst_endpoint():
    return await generate_analyst_report(events_buffer)


@app.websocket("/ws/live")
async def ws_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps({
            "type": "SYSTEM",
            "message": "Connected to OSINT Nexus — Real-time feeds active",
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
