"""
OSINT NEXUS — Real-time Intelligence Engine
"""

import asyncio
import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Sequence, Tuple

import feedparser
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
try:
    import psycopg  # type: ignore
except Exception:
    psycopg = None
try:
    import mgrs  # type: ignore
except Exception:
    mgrs = None

try:
    from .analyst import generate_analyst_report  # type: ignore
    from . import auth_security as authsec  # type: ignore
    from . import auth_store as authstore  # type: ignore
except ImportError:
    from analyst import generate_analyst_report
    import auth_security as authsec
    import auth_store as authstore

app = FastAPI(title="OSINT Nexus Engine v3")

CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "llama3:latest")
OLLAMA_BASE_URL = OLLAMA_URL.rsplit("/api/", 1)[0] if "/api/" in OLLAMA_URL else "http://ollama:11434"
V2_MODEL_VERIFY = os.getenv("V2_MODEL_VERIFY", "phi4-mini")
V2_MODEL_REPORT = os.getenv("V2_MODEL_REPORT", "deepseek-r1:8b")
V2_MODEL_DEFAULT = os.getenv("V2_MODEL_DEFAULT", V2_MODEL_VERIFY)
V2_VERIFY_TIMEOUT_SEC = int(os.getenv("V2_VERIFY_TIMEOUT_SEC", "35"))
V2_REPORT_TIMEOUT_SEC = int(os.getenv("V2_REPORT_TIMEOUT_SEC", "120"))
V2_REPORT_CACHE_TTL_SEC = int(os.getenv("V2_REPORT_CACHE_TTL_SEC", "300"))
GEOCODE_URL = os.getenv("GEOCODE_URL", "https://nominatim.openstreetmap.org/search")
V2_API_KEY = os.getenv("V2_API_KEY", "")
STORAGE_BACKEND = "postgres" if os.getenv("DATABASE_URL", "").startswith("postgres") else "sqlite"
DATABASE_URL = os.getenv("DATABASE_URL", "")
AUTH_SECRET = os.getenv("AUTH_SECRET", "")
AUTH_DEFAULT_ADMIN_USER = os.getenv("AUTH_DEFAULT_ADMIN_USER", "admin")
AUTH_DEFAULT_ADMIN_PASSWORD = os.getenv("AUTH_DEFAULT_ADMIN_PASSWORD", "")
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "0").lower() in ("1", "true", "yes", "on")
AUTH_ACCESS_HOURS = int(os.getenv("AUTH_ACCESS_HOURS", "8"))
AUTH_LOGIN_MAX_ATTEMPTS = int(os.getenv("AUTH_LOGIN_MAX_ATTEMPTS", "5"))
AUTH_LOGIN_LOCK_SEC = int(os.getenv("AUTH_LOGIN_LOCK_SEC", "300"))
AUTH_RATE_WINDOW_SEC = int(os.getenv("AUTH_RATE_WINDOW_SEC", "60"))
AUTH_RATE_LOGIN_PER_IP = int(os.getenv("AUTH_RATE_LOGIN_PER_IP", "20"))
AUTH_RATE_REGISTER_PER_IP = int(os.getenv("AUTH_RATE_REGISTER_PER_IP", "8"))
ALLOW_INSECURE_DEFAULTS = os.getenv("ALLOW_INSECURE_DEFAULTS", "0").lower() in ("1", "true", "yes", "on")
OVERLAY_DIR = Path(os.getenv("OVERLAY_DIR", "/tmp/osint_overlays"))
OVERLAY_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Cache-Control"] = "no-store"
    if AUTH_COOKIE_SECURE:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


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
_ollama_http_client: Optional[httpx.AsyncClient] = None
_geocode_http_client: Optional[httpx.AsyncClient] = None
_ollama_available_models: set = set()
_media_jobs: "asyncio.Queue[dict]" = asyncio.Queue()
_media_job_state: Dict[str, dict] = {}
_rate_limit: Dict[str, List[float]] = {}
_failed_logins: Dict[str, Dict[str, Any]] = {}
_review_cache: Dict[str, dict] = {}
_analyst_state: Dict[str, Any] = {
    "last_generated_ts": 0.0,
    "last_event_fp": "",
    "report": None,
}
_v2_report_state: Dict[str, Any] = {
    "last_generated_ts": 0.0,
    "last_event_fp": "",
    "report": None,
}


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
TELEGRAM_SOURCE_SET = {str(ch.get("source", "")).strip() for ch in TELEGRAM_CHANNELS}
TELEGRAM_POLL_INTERVAL_SEC = int(os.getenv("TELEGRAM_POLL_INTERVAL_SEC", "3"))

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
    return authsec.utc_now_iso()


def hash_password(password: str, salt: Optional[bytes] = None, iterations: int = 240_000) -> str:
    return authsec.hash_password(password, salt=salt, iterations=iterations)


def verify_password(password: str, encoded: str) -> bool:
    return authsec.verify_password(password, encoded)


def mgrs_from_latlng(lat: float, lng: float) -> Optional[str]:
    if mgrs is None:
        return None
    try:
        converter = mgrs.MGRS()
        return str(converter.toMGRS(lat, lng))
    except Exception:
        return None


def parse_overlay_file(path: Path) -> Optional[dict]:
    try:
        if path.suffix.lower() != ".geojson":
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("type") not in {"FeatureCollection", "Feature"}:
            return None
        return {
            "id": path.stem,
            "name": path.stem.replace("_", " ").title(),
            "kind": "geojson",
            "source": raw,
        }
    except Exception:
        return None


def load_overlays() -> List[dict]:
    items: List[dict] = []
    if not OVERLAY_DIR.exists():
        return items
    for p in sorted(OVERLAY_DIR.glob("*.geojson")):
        parsed = parse_overlay_file(p)
        if parsed:
            items.append(parsed)
    return items


def auth_sign(username: str, role: str, expires_epoch: int) -> str:
    return authsec.auth_sign(AUTH_SECRET, username, role, expires_epoch)


def auth_verify(token: str) -> Optional[dict]:
    return authsec.auth_verify(AUTH_SECRET, token)


def auth_token_signature(token: str) -> Optional[str]:
    return authsec.auth_token_signature(AUTH_SECRET, token)


def check_password_policy(password: str) -> Optional[str]:
    return authsec.check_password_policy(password)


def _is_local_origin(origin: str) -> bool:
    return authsec.is_local_origin(origin)


def _is_local_dev_mode() -> bool:
    return authsec.is_local_dev_mode(CORS_ORIGINS)


def validate_security_config() -> None:
    authsec.validate_security_config(
        auth_secret=AUTH_SECRET,
        auth_default_admin_password=AUTH_DEFAULT_ADMIN_PASSWORD,
        auth_cookie_secure=AUTH_COOKIE_SECURE,
        cors_origins=CORS_ORIGINS,
        allow_insecure_defaults=ALLOW_INSECURE_DEFAULTS,
    )


def _client_ip(request: Request) -> str:
    return authsec.client_ip(request)


def enforce_rate_limit(bucket: str, key: str, max_events: int, window_sec: int) -> None:
    authsec.enforce_rate_limit(_rate_limit, bucket, key, max_events, window_sec)


def enforce_csrf(request: Request) -> None:
    authsec.enforce_csrf(request)


def is_token_revoked(sig: str) -> bool:
    return authsec.is_token_revoked(_db, sig)


def cleanup_revoked_tokens() -> None:
    authsec.cleanup_revoked_tokens(_db)


def auth_user_from_request(request: Request) -> dict:
    return authsec.auth_user_from_request(request, AUTH_SECRET, _db)


def auth_user_from_websocket(websocket: WebSocket) -> Optional[dict]:
    return authsec.auth_user_from_websocket(websocket, AUTH_SECRET, _db)


def build_auth_card_payload(verified: dict) -> dict:
    return authsec.build_auth_card_payload(
        verified=verified,
        auth_secret=AUTH_SECRET,
        auth_access_hours=AUTH_ACCESS_HOURS,
        auth_card_theater=os.getenv("AUTH_CARD_THEATER", "SECTOR-CENTCOM"),
    )


def require_admin(request: Request) -> dict:
    verified = authsec.auth_user_from_request(request, AUTH_SECRET, _db)
    if str(verified.get("role", "")).lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return verified


def resolve_write_identity(
    request: Request,
    x_api_key: Optional[str] = None,
    x_actor: Optional[str] = None,
    x_role: Optional[str] = None,
) -> dict:
    token = request.cookies.get("osint_auth") or ""
    if token:
        enforce_csrf(request)
        verified = auth_user_from_request(request)
        role = str(verified.get("role", "")).lower()
        if role not in {"admin", "analyst"}:
            raise HTTPException(status_code=403, detail="Role not allowed")
        return {"username": str(verified.get("username", "unknown")), "role": role, "auth": "cookie"}

    if V2_API_KEY and x_api_key == V2_API_KEY:
        role = (x_role or "viewer").strip().lower()
        if role not in {"admin", "analyst"}:
            raise HTTPException(status_code=403, detail="Role not allowed")
        actor = (x_actor or "service").strip() or "service"
        return {"username": actor, "role": role, "auth": "api_key"}

    raise HTTPException(status_code=401, detail="Authentication required")


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            incident_id TEXT,
            status TEXT NOT NULL,
            analyst TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_event ON reviews(event_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner TEXT NOT NULL,
            filters_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner TEXT NOT NULL,
            query TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pinned_incidents (
            incident_id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS handoff_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner TEXT NOT NULL,
            min_confidence INTEGER NOT NULL,
            event_types_json TEXT NOT NULL,
            channels_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_analysis (
            event_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            keyframes_json TEXT NOT NULL,
            ocr_snippets_json TEXT NOT NULL,
            stt_snippets_json TEXT NOT NULL,
            claim_alignment TEXT NOT NULL,
            credibility_note TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            truth_type TEXT,
            truth_lat REAL,
            truth_lng REAL,
            outcome TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            target_id TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            sig TEXT PRIMARY KEY,
            expires_epoch INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires ON revoked_tokens(expires_epoch)")
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


def audit_log(action: str, actor: str, role: str, payload: dict, target_id: Optional[str] = None):
    if _db is None:
        return
    _db.execute(
        """
        INSERT INTO audit_logs (actor, role, action, target_id, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            actor or "system",
            role or "viewer",
            action,
            target_id,
            json.dumps(payload, ensure_ascii=False),
            utc_now_iso(),
        ),
    )
    _db.commit()


def _model_call_json(prompt: str, model_name: str, retries: int = 2) -> Optional[dict]:
    async def _run() -> Optional[dict]:
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=25) as client:
                    resp = await client.post(
                        OLLAMA_URL,
                        json={
                            "model": model_name,
                            "prompt": prompt,
                            "stream": False,
                            "format": "json",
                            "options": {"temperature": 0.1},
                        },
                    )
                    resp.raise_for_status()
                    raw = str(resp.json().get("response", "{}")).strip()
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return data
            except Exception:
                await asyncio.sleep(0.2 * (attempt + 1))
        return None

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return None
    except Exception:
        pass
    return asyncio.run(_run())


def evaluate_claim_alignment(desc: str, ocr_lines: List[str], stt_lines: List[str]) -> Tuple[str, str]:
    text = normalize_desc(desc)
    merged = normalize_desc(" ".join(ocr_lines + stt_lines))
    if not merged:
        return "UNVERIFIED_VISUAL", "No OCR/STT evidence available from media."
    overlap = len(set(text.split()) & set(merged.split()))
    if overlap >= 6:
        return "LIKELY_RELATED", "OCR/STT cues align strongly with source text."
    if overlap >= 3:
        return "UNVERIFIED_VISUAL", "Partial OCR/STT overlap; requires analyst confirmation."
    return "MISMATCH", "Low textual overlap between media extraction and source claim."


def _safe_run(cmd: List[str], timeout_sec: int = 20) -> Tuple[bool, str]:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=timeout_sec).decode(errors="ignore")
        return True, out
    except Exception as e:
        return False, str(e)


def run_media_analysis(event: dict) -> dict:
    event_id = str(event.get("id", ""))
    video_url = event.get("video_url")
    if not event_id or not video_url:
        return {
            "status": "skipped",
            "keyframes": [],
            "ocr_snippets": [],
            "stt_snippets": [],
            "claim_alignment": "UNVERIFIED_VISUAL",
            "credibility_note": "No analyzable media for this event.",
        }

    local_file = None
    if isinstance(video_url, str) and video_url.startswith("/media/telegram/"):
        local_file = str((MEDIA_DIR / "telegram" / Path(video_url).name))

    keyframes: List[str] = []
    ocr_lines: List[str] = []
    stt_lines: List[str] = []
    status = "partial"

    if local_file and Path(local_file).exists():
        ffprobe_ok, ffprobe_out = _safe_run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", local_file],
            timeout_sec=10,
        )
        if ffprobe_ok:
            duration_txt = ffprobe_out.strip().splitlines()[-1] if ffprobe_out.strip() else "0"
            keyframes.append(f"duration_sec:{duration_txt}")
        status = "done"
    else:
        status = "partial"

    # Optional OCR/STT placeholders: capture capability status without hard dependency failure.
    ocr_ok, _ = _safe_run(["which", "tesseract"], timeout_sec=5)
    stt_ok, _ = _safe_run(["which", "whisper"], timeout_sec=5)
    if not ocr_ok:
        ocr_lines.append("tesseract_unavailable")
    if not stt_ok:
        stt_lines.append("whisper_unavailable")

    align, note = evaluate_claim_alignment(str(event.get("desc", "")), ocr_lines, stt_lines)
    return {
        "status": status,
        "keyframes": keyframes[:6],
        "ocr_snippets": ocr_lines[:6],
        "stt_snippets": stt_lines[:6],
        "claim_alignment": align,
        "credibility_note": note,
    }


def persist_media_analysis(event_id: str, data: dict):
    if _db is None:
        return
    _db.execute(
        """
        INSERT OR REPLACE INTO media_analysis (
            event_id, status, keyframes_json, ocr_snippets_json, stt_snippets_json,
            claim_alignment, credibility_note, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            data.get("status", "pending"),
            json.dumps(data.get("keyframes", []), ensure_ascii=False),
            json.dumps(data.get("ocr_snippets", []), ensure_ascii=False),
            json.dumps(data.get("stt_snippets", []), ensure_ascii=False),
            data.get("claim_alignment", "UNVERIFIED_VISUAL"),
            data.get("credibility_note", ""),
            utc_now_iso(),
        ),
    )
    _db.commit()


def get_media_analysis(event_id: str) -> dict:
    if _db is None:
        return {}
    row = _db.execute("SELECT * FROM media_analysis WHERE event_id = ?", (event_id,)).fetchone()
    if not row:
        return {}
    return {
        "status": row["status"],
        "keyframes": json.loads(row["keyframes_json"] or "[]"),
        "ocr_snippets": json.loads(row["ocr_snippets_json"] or "[]"),
        "stt_snippets": json.loads(row["stt_snippets_json"] or "[]"),
        "claim_alignment": row["claim_alignment"],
        "credibility_note": row["credibility_note"],
        "updated_at": row["updated_at"],
    }


async def media_worker():
    while True:
        job = await _media_jobs.get()
        event_id = job.get("event_id")
        _media_job_state[event_id] = {"status": "running", "updated_at": utc_now_iso()}
        result = await asyncio.to_thread(run_media_analysis, job.get("event", {}))
        persist_media_analysis(event_id, result)
        _media_job_state[event_id] = {"status": "done", "updated_at": utc_now_iso()}
        _media_jobs.task_done()


def source_ops_metrics(window_minutes: int = 120) -> dict:
    now = datetime.now(timezone.utc)
    per_source: Dict[str, dict] = {}
    errors = {
        "rss": metrics["rss_errors"],
        "telegram": metrics["telegram_errors"],
        "flights": metrics["flight_errors"],
        "red_alert": metrics["red_alert_errors"],
    }
    sample = fetch_recent_v2_events_pg(limit=2000)
    if not sample:
        sample = list(events_history)
    for e in sample:
        src = _extract_source(e)
        ts = _parse_iso(str(e.get("timestamp", utc_now_iso())))
        if (now - ts).total_seconds() > window_minutes * 60:
            continue
        bucket = per_source.setdefault(src, {"count": 0, "last_ts": None})
        bucket["count"] += 1
        bucket["last_ts"] = max(bucket["last_ts"], ts) if bucket["last_ts"] else ts

    out = {}
    for src, data in per_source.items():
        last_ts = data["last_ts"]
        lag_sec = int((now - last_ts).total_seconds()) if last_ts else None
        throughput = round(data["count"] / max(1, window_minutes), 3)
        degraded = bool(lag_sec and lag_sec > 20 * 60)
        out[src] = {
            "lag_seconds": lag_sec,
            "throughput_per_min": throughput,
            "events_window": data["count"],
            "degraded": degraded,
            "last_success": last_ts.isoformat() if last_ts else None,
        }
    return {
        "per_source": out,
        "poll_errors": errors,
        "generated_at": utc_now_iso(),
    }


def postgres_status() -> dict:
    configured = DATABASE_URL.startswith("postgres")
    if not configured:
        return {"configured": False, "connected": False, "events_count": None, "error": "DATABASE_URL not set to postgres"}
    if psycopg is None:
        return {"configured": True, "connected": False, "events_count": None, "error": "psycopg unavailable"}
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events_v2 (
                        id TEXT PRIMARY KEY,
                        type TEXT,
                        source TEXT,
                        timestamp TIMESTAMPTZ,
                        lat DOUBLE PRECISION,
                        lng DOUBLE PRECISION,
                        description TEXT,
                        payload_json JSONB
                    )
                    """
                )
                cur.execute("SELECT COUNT(*) FROM events_v2")
                count = int(cur.fetchone()[0])
                return {"configured": True, "connected": True, "events_count": count, "error": None}
    except Exception as e:
        return {"configured": True, "connected": False, "events_count": None, "error": str(e)}


def ensure_default_admin() -> None:
    authstore.ensure_default_admin(
        _db,
        default_admin_user=AUTH_DEFAULT_ADMIN_USER,
        default_admin_password=AUTH_DEFAULT_ADMIN_PASSWORD,
        hash_password=hash_password,
        now_iso=utc_now_iso,
    )


def get_user(username: str) -> Optional[sqlite3.Row]:
    return authstore.get_user(_db, username)


class AuthRegisterPayload(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class AuthLoginPayload(BaseModel):
    username: str
    password: str


class AdminSetRolePayload(BaseModel):
    role: str


class OpsBriefPayload(BaseModel):
    mode: str = "INTSUM"
    limit: int = 20


def persist_event_v2_pg(event: dict):
    if not DATABASE_URL.startswith("postgres") or psycopg is None:
        return
    try:
        payload = {
            "incident_id": event.get("incident_id"),
            "url": event.get("url"),
            "video_url": event.get("video_url"),
            "lang": event.get("lang"),
            "insufficient_evidence": bool(event.get("insufficient_evidence", False)),
            "observed_facts": event.get("observed_facts", []),
            "model_inference": event.get("model_inference", []),
            "confidence_score": int(event.get("confidence_score", 0) or 0),
            "confidence_reason": event.get("confidence_reason"),
            "video_assessment": event.get("video_assessment"),
            "video_confidence": event.get("video_confidence"),
            "video_clues": event.get("video_clues", []),
            "source": _extract_source(event),
            "updated_at": utc_now_iso(),
        }
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events_v2 (
                        id TEXT PRIMARY KEY,
                        type TEXT,
                        source TEXT,
                        timestamp TIMESTAMPTZ,
                        lat DOUBLE PRECISION,
                        lng DOUBLE PRECISION,
                        description TEXT,
                        payload_json JSONB
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO events_v2 (id, type, source, timestamp, lat, lng, description, payload_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        type = EXCLUDED.type,
                        source = EXCLUDED.source,
                        timestamp = EXCLUDED.timestamp,
                        lat = EXCLUDED.lat,
                        lng = EXCLUDED.lng,
                        description = EXCLUDED.description,
                        payload_json = EXCLUDED.payload_json
                    """,
                    (
                        str(event.get("id")),
                        str(event.get("type", "CLASH")),
                        _extract_source(event),
                        str(event.get("timestamp") or utc_now_iso()),
                        float(event.get("lat", 0.0)),
                        float(event.get("lng", 0.0)),
                        str(event.get("desc", "")),
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
    except Exception:
        # Keep ingestion non-blocking if Postgres is unavailable.
        return


def _decode_pg_event(row: Any) -> dict:
    payload = row[7] if isinstance(row[7], dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    ts = row[3]
    if ts is None:
        ts_iso = utc_now_iso()
    else:
        ts_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    return {
        "id": row[0],
        "type": row[1] or "CLASH",
        "source": row[2] or payload.get("source") or "Unknown",
        "timestamp": ts_iso,
        "lat": float(row[4] or 0.0),
        "lng": float(row[5] or 0.0),
        "desc": row[6] or "",
        "incident_id": payload.get("incident_id"),
        "url": payload.get("url"),
        "video_url": payload.get("video_url"),
        "lang": payload.get("lang"),
        "insufficient_evidence": bool(payload.get("insufficient_evidence", False)),
        "observed_facts": payload.get("observed_facts", []),
        "model_inference": payload.get("model_inference", []),
        "confidence_score": int(payload.get("confidence_score", 0) or 0),
        "confidence_reason": payload.get("confidence_reason"),
        "video_assessment": payload.get("video_assessment"),
        "video_confidence": payload.get("video_confidence"),
        "video_clues": payload.get("video_clues", []),
    }


def fetch_recent_v2_events_pg(
    limit: int = 200,
    source_whitelist: Optional[Sequence[str]] = None,
    type_whitelist: Optional[Sequence[str]] = None,
) -> List[dict]:
    if not DATABASE_URL.startswith("postgres") or psycopg is None:
        return []
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                query = [
                    "SELECT id, type, source, timestamp, lat, lng, description, payload_json",
                    "FROM events_v2",
                    "WHERE 1=1",
                ]
                params: List[Any] = []
                if source_whitelist:
                    query.append("AND source = ANY(%s)")
                    params.append(list(source_whitelist))
                if type_whitelist:
                    query.append("AND type = ANY(%s)")
                    params.append(list(type_whitelist))
                query.append("ORDER BY timestamp DESC")
                query.append("LIMIT %s")
                params.append(limit)
                cur.execute("\n".join(query), tuple(params))
                rows = cur.fetchall()
                return [_decode_pg_event(r) for r in rows]
    except Exception:
        return []


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


def assess_confidence_v2(event: dict, nearby: list, age_min: float) -> Tuple[int, str, List[str]]:
    base, reason, corroborating = assess_confidence(event, nearby, age_min)
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


def _is_telegram_source(event: dict) -> bool:
    src = _extract_source(event).strip()
    return src in TELEGRAM_SOURCE_SET or src.endswith("(TG)")


def _get_ollama_client() -> httpx.AsyncClient:
    global _ollama_http_client
    if _ollama_http_client is None:
        _ollama_http_client = httpx.AsyncClient(timeout=30)
    return _ollama_http_client


def _get_geocode_client() -> httpx.AsyncClient:
    global _geocode_http_client
    if _geocode_http_client is None:
        _geocode_http_client = httpx.AsyncClient(
            timeout=8,
            headers={"User-Agent": "OSINT-Nexus/1.0 (research dashboard)"},
        )
    return _geocode_http_client


async def sync_ollama_runtime_models() -> None:
    global OLLAMA_MODEL, OLLAMA_FALLBACK_MODEL, _ollama_available_models
    try:
        client = _get_ollama_client()
        res = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        res.raise_for_status()
        raw = res.json()
        models = raw.get("models", []) if isinstance(raw, dict) else []
        names = [str(m.get("name", "")).strip() for m in models if isinstance(m, dict)]
        available = {n for n in names if n}
        _ollama_available_models = available
        if not available:
            print("[OLLAMA] No local models available from /api/tags")
            return

        preferred = [
            OLLAMA_MODEL,
            OLLAMA_FALLBACK_MODEL,
            V2_MODEL_VERIFY,
            V2_MODEL_REPORT,
            V2_MODEL_DEFAULT,
            "qwen2.5:7b",
            "phi4-mini",
            "deepseek-r1:8b",
            "llama3",
            "llama3:latest",
        ]
        primary = next((m for m in preferred if m and m in available), None)
        if primary is None:
            primary = sorted(available)[0]
        fallback = next((m for m in preferred if m and m in available and m != primary), primary)
        OLLAMA_MODEL = primary
        OLLAMA_FALLBACK_MODEL = fallback
        print(f"[OLLAMA] Runtime model chain: primary={OLLAMA_MODEL}, fallback={OLLAMA_FALLBACK_MODEL}")
    except Exception as e:
        print(f"[OLLAMA] Model discovery failed: {e}")


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
        params = {"q": place, "format": "json", "limit": 1}
        client = _get_geocode_client()
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


async def fetch_metoc(lat: float, lng: float) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lng:.4f}",
        "current": ",".join(
            [
                "temperature_2m",
                "wind_speed_10m",
                "wind_direction_10m",
                "visibility",
                "cloud_cover",
                "pressure_msl",
            ]
        ),
        "timezone": "UTC",
    }
    try:
        client = _get_geocode_client()
        res = await client.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json().get("current", {}) if isinstance(res.json(), dict) else {}
        visibility_m = float(data.get("visibility", 0.0) or 0.0)
        cloud_cover = float(data.get("cloud_cover", 0.0) or 0.0)
        ceiling_ft = int(max(500.0, 12000.0 - (cloud_cover / 100.0) * 10000.0))
        return {
            "source": "open-meteo",
            "lat": lat,
            "lng": lng,
            "temperature_c": data.get("temperature_2m"),
            "wind_speed_kts": round(float(data.get("wind_speed_10m", 0.0) or 0.0) * 0.539957, 1),
            "wind_direction_deg": data.get("wind_direction_10m"),
            "visibility_km": round(visibility_m / 1000.0, 1) if visibility_m else None,
            "cloud_cover_pct": cloud_cover,
            "cloud_ceiling_ft_est": ceiling_ft,
            "pressure_hpa": data.get("pressure_msl"),
            "updated_at": utc_now_iso(),
        }
    except Exception as e:
        return {
            "source": "open-meteo",
            "lat": lat,
            "lng": lng,
            "error": str(e),
            "updated_at": utc_now_iso(),
        }


def _decode_ollama_json_response(raw: str) -> Optional[dict]:
    raw_text = str(raw or "{}").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json", "", 1).strip()
    try:
        parsed = json.loads(raw_text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


class V2AiScheduler:
    """Strict single-active-model scheduler for v2 routes."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._task_to_model = {
            "verify": V2_MODEL_VERIFY,
            "report": V2_MODEL_REPORT,
        }
        self._task_timeout = {
            "verify": V2_VERIFY_TIMEOUT_SEC,
            "report": V2_REPORT_TIMEOUT_SEC,
        }
        self._state: Dict[str, Any] = {
            "current_model": None,
            "active_task": None,
            "active_requests": 0,
            "total_requests": 0,
            "forced_switches": 0,
            "last_error": None,
            "last_run_at": None,
            "last_duration_ms": None,
        }

    async def _post_generate(self, payload: Dict[str, Any], timeout_sec: int) -> dict:
        client = _get_ollama_client()
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=timeout_sec)
        resp.raise_for_status()
        return resp.json()

    async def _unload_model(self, model: Optional[str]) -> None:
        if not model:
            return
        try:
            await self._post_generate(
                {
                    "model": model,
                    "prompt": ".",
                    "stream": False,
                    "options": {"temperature": 0},
                    "keep_alive": "0s",
                },
                timeout_sec=15,
            )
        except httpx.HTTPStatusError as e:
            # 404 is expected when trying to unload a model that was never loaded.
            if getattr(e.response, "status_code", None) != 404:
                self._state["last_error"] = f"unload:{model}:{e}"
        except Exception as e:
            self._state["last_error"] = f"unload:{model}:{e}"

    async def _switch_model(self, next_model: str) -> None:
        current = self._state.get("current_model")
        if current and current != next_model:
            self._state["forced_switches"] += 1
            await self._unload_model(current)
            self._state["current_model"] = None
        if self._state.get("current_model") != next_model:
            self._state["current_model"] = next_model

    async def run_json(self, task: str, prompt: str, temperature: float = 0.1) -> dict:
        if task not in self._task_to_model:
            raise HTTPException(status_code=400, detail=f"Unsupported task '{task}'")
        model = self._task_to_model[task]
        timeout_sec = int(self._task_timeout.get(task, 30))
        candidate_models = [model]
        for fallback_model in (V2_MODEL_DEFAULT, OLLAMA_MODEL):
            if fallback_model and fallback_model not in candidate_models:
                candidate_models.append(fallback_model)
        if _ollama_available_models:
            candidate_models = [m for m in candidate_models if m in _ollama_available_models]
        if not candidate_models:
            raise HTTPException(status_code=502, detail=f"v2 ai '{task}' failed: no available ollama models")

        async with self._lock:
            started = time.time()
            self._state["active_requests"] += 1
            self._state["active_task"] = task
            self._state["total_requests"] += 1
            self._state["last_error"] = None
            try:
                for model_name in candidate_models:
                    try:
                        await self._switch_model(model_name)
                        response = await self._post_generate(
                            {
                                "model": model_name,
                                "prompt": prompt,
                                "stream": False,
                                "format": "json",
                                "options": {"temperature": temperature},
                                "keep_alive": "30s" if model_name == V2_MODEL_DEFAULT else "10s",
                            },
                            timeout_sec=timeout_sec,
                        )
                        data = _decode_ollama_json_response(str(response.get("response", "{}")))
                        if data is None:
                            raise ValueError("invalid JSON response")
                        return data
                    except httpx.HTTPStatusError as e:
                        if getattr(e.response, "status_code", None) == 404:
                            _ollama_available_models.discard(model_name)
                        self._state["last_error"] = f"{model_name}: {e}"
                        continue
                    except Exception as e:
                        self._state["last_error"] = f"{model_name}: {e}"
                        continue
                raise HTTPException(status_code=502, detail=f"v2 ai '{task}' failed across model chain")
            except HTTPException:
                raise
            except Exception as e:
                self._state["last_error"] = str(e)
                raise HTTPException(status_code=502, detail=f"v2 ai '{task}' failed: {e}")
            finally:
                current = self._state.get("current_model")
                if current and current != V2_MODEL_DEFAULT:
                    await self._unload_model(current)
                    self._state["current_model"] = None
                self._state["active_requests"] = max(0, int(self._state["active_requests"]) - 1)
                if self._state["active_requests"] == 0:
                    self._state["active_task"] = None
                self._state["last_run_at"] = utc_now_iso()
                self._state["last_duration_ms"] = int((time.time() - started) * 1000)

    def status(self) -> Dict[str, Any]:
        return {
            "policy": {
                "single_active_model": True,
                "max_concurrency": 1,
                "default_model": V2_MODEL_DEFAULT,
                "task_models": self._task_to_model,
                "timeouts_sec": self._task_timeout,
            },
            "runtime": dict(self._state),
        }


_v2_ai_scheduler = V2AiScheduler()


async def call_ollama_json(prompt: str, retries: int = 2) -> Optional[dict]:
    model_chain = [OLLAMA_MODEL]
    if OLLAMA_FALLBACK_MODEL and OLLAMA_FALLBACK_MODEL not in model_chain:
        model_chain.append(OLLAMA_FALLBACK_MODEL)
    if _ollama_available_models:
        model_chain = [m for m in model_chain if m in _ollama_available_models]
    if not model_chain:
        return None
    for model_name in model_chain:
        for attempt in range(retries + 1):
            try:
                client = _get_ollama_client()
                resp = await client.post(
                    OLLAMA_URL,
                    json={
                        "model": model_name,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.1},
                    },
                    timeout=20,
                )
                resp.raise_for_status()
                raw = str(resp.json().get("response", "{}")).strip()
                if raw.startswith("```"):
                    raw = raw.strip("`")
                    raw = raw.replace("json", "", 1).strip()
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except httpx.HTTPStatusError as e:
                # 404 usually means missing model; stop retrying that model to reduce log spam.
                if getattr(e.response, "status_code", None) == 404:
                    _ollama_available_models.discard(model_name)
                    print(f"[OLLAMA] Missing model '{model_name}', removed from runtime chain")
                    break
                if attempt == retries:
                    print(f"[OLLAMA] JSON call failed ({model_name}): {e}")
                await asyncio.sleep(0.35 * (attempt + 1))
            except Exception as e:
                if attempt == retries:
                    print(f"[OLLAMA] JSON call failed ({model_name}): {e}")
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
                persist_event_v2_pg(existing)
            return

        incident_id = build_incident_id(event)
        event["incident_id"] = incident_id
        incident_index[incident_id] = event

    events_history.append(event)
    if len(events_history) > 1200:
        events_history[:] = events_history[-1200:]

    persist_event(event)
    persist_event_v2_pg(event)
    if event.get("video_url"):
        event_id = str(event.get("id", ""))
        if event_id and event_id not in _media_job_state:
            _media_job_state[event_id] = {"status": "queued", "updated_at": utc_now_iso()}
            await _media_jobs.put({"event_id": event_id, "event": event})
    push_event_buffer(event)
    await manager.broadcast({"type": "NEW_EVENT", "data": event})
    await manager.broadcast(
        {
            "type": "NEW_EVENT_DIFF",
            "data": {
                "id": event.get("id"),
                "incident_id": event.get("incident_id"),
                "type": event.get("type"),
                "source": _extract_source(event),
                "lat": event.get("lat"),
                "lng": event.get("lng"),
                "timestamp": event.get("timestamp"),
            },
        }
    )


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
                        geo = await geolocate_event(f"[{cfg['source']}] Telegram Update", text, pid, allow_ai=True)
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
            await asyncio.sleep(max(1, TELEGRAM_POLL_INTERVAL_SEC))


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


def build_ops_alerts() -> List[dict]:
    alerts: List[dict] = []
    warnings = _watchdog_check()
    for w in warnings:
        severity = "critical" if "no successful poll yet" in w else "warning"
        alerts.append({"rule": "watchdog_stale_source", "severity": severity, "message": w})

    if _media_jobs.qsize() > 25:
        alerts.append(
            {
                "rule": "media_queue_backlog",
                "severity": "warning",
                "message": f"media_jobs_pending={_media_jobs.qsize()} exceeds threshold 25",
            }
        )
    if metrics.get("rss_errors", 0) >= 3 or metrics.get("telegram_errors", 0) >= 3:
        alerts.append(
            {
                "rule": "ingestion_error_rate",
                "severity": "warning",
                "message": f"rss_errors={metrics.get('rss_errors', 0)}, telegram_errors={metrics.get('telegram_errors', 0)}",
            }
        )
    pg = postgres_status()
    if pg.get("configured") and not pg.get("connected"):
        alerts.append({"rule": "postgres_connectivity", "severity": "critical", "message": str(pg.get("error", "postgres offline"))})
    return alerts


def render_prometheus_metrics() -> str:
    lines = [
        "# HELP osint_events_history_total Number of events in runtime history",
        "# TYPE osint_events_history_total gauge",
        f"osint_events_history_total {len(events_history)}",
        "# HELP osint_events_buffer_total Number of events in short-term buffer",
        "# TYPE osint_events_buffer_total gauge",
        f"osint_events_buffer_total {len(events_buffer)}",
        "# HELP osint_media_jobs_pending Number of pending media jobs",
        "# TYPE osint_media_jobs_pending gauge",
        f"osint_media_jobs_pending {_media_jobs.qsize()}",
        "# HELP osint_watchdog_warnings Number of watchdog warnings",
        "# TYPE osint_watchdog_warnings gauge",
        f"osint_watchdog_warnings {metrics.get('watchdog_warnings', 0)}",
        "# HELP osint_rss_polls_total Total RSS polling cycles",
        "# TYPE osint_rss_polls_total counter",
        f"osint_rss_polls_total {metrics.get('rss_polls', 0)}",
        "# HELP osint_telegram_polls_total Total Telegram polling cycles",
        "# TYPE osint_telegram_polls_total counter",
        f"osint_telegram_polls_total {metrics.get('telegram_polls', 0)}",
        "# HELP osint_flight_polls_total Total flight polling cycles",
        "# TYPE osint_flight_polls_total counter",
        f"osint_flight_polls_total {metrics.get('flight_polls', 0)}",
        "# HELP osint_red_alert_polls_total Total red alert polling cycles",
        "# TYPE osint_red_alert_polls_total counter",
        f"osint_red_alert_polls_total {metrics.get('red_alert_polls', 0)}",
        "# HELP osint_rss_errors_total Total RSS polling errors",
        "# TYPE osint_rss_errors_total counter",
        f"osint_rss_errors_total {metrics.get('rss_errors', 0)}",
        "# HELP osint_telegram_errors_total Total Telegram polling errors",
        "# TYPE osint_telegram_errors_total counter",
        f"osint_telegram_errors_total {metrics.get('telegram_errors', 0)}",
        "# HELP osint_flight_errors_total Total flight polling errors",
        "# TYPE osint_flight_errors_total counter",
        f"osint_flight_errors_total {metrics.get('flight_errors', 0)}",
        "# HELP osint_red_alert_errors_total Total red alert polling errors",
        "# TYPE osint_red_alert_errors_total counter",
        f"osint_red_alert_errors_total {metrics.get('red_alert_errors', 0)}",
    ]
    pg = postgres_status()
    lines.extend(
        [
            "# HELP osint_postgres_connected Postgres connectivity status (1 connected, 0 disconnected)",
            "# TYPE osint_postgres_connected gauge",
            f"osint_postgres_connected {1 if pg.get('connected') else 0}",
            "# HELP osint_postgres_events_v2_total Count of events in Postgres events_v2",
            "# TYPE osint_postgres_events_v2_total gauge",
            f"osint_postgres_events_v2_total {int(pg.get('events_count') or 0)}",
        ]
    )
    return "\n".join(lines) + "\n"


@app.on_event("startup")
async def startup_event():
    global _start_time, _db, _ollama_http_client, _geocode_http_client
    _start_time = time.time()
    validate_security_config()
    _db = init_db()
    _ollama_http_client = httpx.AsyncClient(timeout=30)
    _geocode_http_client = httpx.AsyncClient(
        timeout=8,
        headers={"User-Agent": "OSINT-Nexus/1.0 (research dashboard)"},
    )
    cleanup_revoked_tokens()
    await sync_ollama_runtime_models()
    ensure_default_admin()
    load_recent_events()

    asyncio.create_task(poll_flights())
    asyncio.create_task(poll_rss())
    asyncio.create_task(poll_telegram())
    asyncio.create_task(poll_red_alert())
    asyncio.create_task(media_worker())
    print("[OSINT] Engine started — pollers + DB persistence active")


@app.on_event("shutdown")
async def shutdown_event():
    global _ollama_http_client, _geocode_http_client
    if _ollama_http_client is not None:
        await _ollama_http_client.aclose()
        _ollama_http_client = None
    if _geocode_http_client is not None:
        await _geocode_http_client.aclose()
        _geocode_http_client = None


@app.get("/")
async def root():
    return {"status": "OSINT Engine v3 Running", "clients": len(manager.connections), "events": len(events_history)}


@app.post("/api/auth/register")
async def auth_register(payload: AuthRegisterPayload, request: Request):
    if _db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    enforce_rate_limit("register_ip", _client_ip(request), AUTH_RATE_REGISTER_PER_IP, AUTH_RATE_WINDOW_SEC)
    username = payload.username.strip().lower()
    password = payload.password
    role = (payload.role or "viewer").strip().lower()
    if not re.match(r"^[a-z0-9_.-]{3,32}$", username):
        raise HTTPException(status_code=400, detail="Username must be 3-32 chars [a-z0-9_.-]")
    password_error = check_password_policy(password)
    if password_error:
        raise HTTPException(status_code=400, detail=password_error)
    if role not in {"viewer", "analyst", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    if get_user(username):
        raise HTTPException(status_code=409, detail="Username already exists")
    now = utc_now_iso()
    authstore.create_user(
        _db,
        username=username,
        password_hash=hash_password(password),
        role=role,
        now_iso=utc_now_iso,
    )
    return {"ok": True, "username": username, "role": role, "created_at": now}


@app.post("/api/auth/login")
async def auth_login(payload: AuthLoginPayload, request: Request, response: Response):
    if _db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    cleanup_revoked_tokens()
    ip = _client_ip(request)
    enforce_rate_limit("login_ip", ip, AUTH_RATE_LOGIN_PER_IP, AUTH_RATE_WINDOW_SEC)
    username = payload.username.strip().lower()
    lock_key = f"{username}|{ip}"
    lock_state = _failed_logins.get(lock_key) or {}
    lock_until = float(lock_state.get("lock_until", 0))
    if lock_until > time.time():
        wait_sec = max(1, int(lock_until - time.time()))
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Retry in {wait_sec}s")
    user = get_user(username)
    if not user:
        state = _failed_logins.get(lock_key, {"count": 0, "lock_until": 0.0})
        state["count"] = int(state.get("count", 0)) + 1
        if state["count"] >= AUTH_LOGIN_MAX_ATTEMPTS:
            state["lock_until"] = time.time() + AUTH_LOGIN_LOCK_SEC
            state["count"] = 0
        _failed_logins[lock_key] = state
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, str(user["password_hash"])):
        state = _failed_logins.get(lock_key, {"count": 0, "lock_until": 0.0})
        state["count"] = int(state.get("count", 0)) + 1
        if state["count"] >= AUTH_LOGIN_MAX_ATTEMPTS:
            state["lock_until"] = time.time() + AUTH_LOGIN_LOCK_SEC
            state["count"] = 0
        _failed_logins[lock_key] = state
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _failed_logins.pop(lock_key, None)
    role = str(user["role"])
    expiry_dt = datetime.now(timezone.utc) + timedelta(hours=AUTH_ACCESS_HOURS)
    expires_epoch = int(expiry_dt.timestamp())
    token = auth_sign(username, role, expires_epoch)
    csrf_token = secrets.token_urlsafe(24)
    cookie_expires = expiry_dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
    for key, value in [
        ("osint_session", "1"),
        ("osint_role", role),
        ("osint_user", username),
        ("osint_auth", token),
        ("osint_csrf", csrf_token),
    ]:
        response.set_cookie(
            key=key,
            value=value,
            path="/",
            expires=cookie_expires,
            httponly=(key == "osint_auth"),
            samesite="lax",
            secure=AUTH_COOKIE_SECURE,
        )
    return {"ok": True, "username": username, "role": role, "expires_at": expiry_dt.isoformat(), "csrf": csrf_token}


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    enforce_csrf(request)
    token = request.cookies.get("osint_auth") or ""
    verified = auth_verify(token) if token else None
    if verified:
        authstore.revoke_token(
            _db,
            sig=str(verified.get("sig", "")),
            expires_epoch=int(verified.get("expires", 0)),
            now_iso=utc_now_iso,
        )
    for key in ["osint_session", "osint_role", "osint_user", "osint_auth", "osint_csrf"]:
        response.delete_cookie(key=key, path="/", samesite="lax", secure=AUTH_COOKIE_SECURE)
    return {"ok": True}


@app.get("/api/auth/session")
async def auth_session(request: Request):
    token = request.cookies.get("osint_auth") or ""
    if not token:
        return {"authenticated": False}
    verified = auth_verify(token)
    if not verified:
        return {"authenticated": False}
    if is_token_revoked(str(verified.get("sig", ""))):
        return {"authenticated": False}
    return {
        "authenticated": True,
        "username": str(verified.get("username", "")),
        "role": str(verified.get("role", "")),
        "expires": int(verified.get("expires", 0)),
        "csrf": request.cookies.get("osint_csrf", ""),
    }


@app.get("/api/auth/card")
async def auth_card(request: Request):
    verified = auth_user_from_request(request)
    return {"card": build_auth_card_payload(verified)}


@app.get("/api/admin/users")
async def admin_list_users(request: Request):
    actor = require_admin(request)
    try:
        items = authstore.list_users(_db)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {
        "items": items,
        "actor": str(actor.get("username", "")),
        "generated_at": utc_now_iso(),
    }


@app.patch("/api/admin/users/{username}/role")
async def admin_set_user_role(username: str, payload: AdminSetRolePayload, request: Request):
    enforce_csrf(request)
    actor = require_admin(request)
    if _db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    target = username.strip().lower()
    if not re.match(r"^[a-z0-9_.-]{3,32}$", target):
        raise HTTPException(status_code=400, detail="Invalid username")
    next_role = str(payload.role or "").strip().lower()
    if next_role not in {"viewer", "analyst", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    try:
        result = authstore.set_user_role(_db, username=target, next_role=next_role, now_iso=utc_now_iso)
    except LookupError:
        raise HTTPException(status_code=404, detail="User not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit_log(
        "admin.role.set",
        str(actor.get("username", "")),
        str(actor.get("role", "admin")),
        {"username": result["username"], "from": result["from"], "to": result["to"]},
        target_id=target,
    )
    return {
        "ok": True,
        "username": result["username"],
        "role": result["to"],
        "updated_at": result["updated_at"],
        "updated_by": str(actor.get("username", "")),
    }


@app.delete("/api/admin/users/{username}")
async def admin_delete_user(username: str, request: Request):
    enforce_csrf(request)
    actor = require_admin(request)
    if _db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    target = username.strip().lower()
    if not re.match(r"^[a-z0-9_.-]{3,32}$", target):
        raise HTTPException(status_code=400, detail="Invalid username")

    actor_username = str(actor.get("username", "")).strip().lower()
    try:
        result = authstore.delete_user(
            _db,
            username=target,
            actor_username=actor_username,
            now_iso=utc_now_iso,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="User not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit_log(
        "admin.user.delete",
        str(actor.get("username", "")),
        str(actor.get("role", "admin")),
        {"username": result["username"], "role": result["role"]},
        target_id=target,
    )
    return {
        "ok": True,
        "username": result["username"],
        "deleted_at": result["deleted_at"],
        "deleted_by": str(actor.get("username", "")),
    }


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
async def analyst_endpoint(force: bool = False):
    # Always analyze from latest persisted events so restarts do not blank analyst context.
    latest = events_history[-120:]
    latest_slice = [
        {
            "id": e.get("id"),
            "type": e.get("type"),
            "desc": e.get("desc"),
            "source": _extract_source(e),
            "timestamp": e.get("timestamp"),
        }
        for e in latest
    ]
    fingerprint_seed = "|".join([f"{x.get('id')}@{x.get('timestamp')}" for x in latest_slice[-40:]])
    event_fp = hashlib.md5(fingerprint_seed.encode()).hexdigest() if fingerprint_seed else "empty"

    now_ts = time.time()
    ttl_seconds = 5 * 60
    age_ok = (now_ts - float(_analyst_state.get("last_generated_ts", 0.0))) < ttl_seconds
    same_events = _analyst_state.get("last_event_fp") == event_fp
    if (not force) and age_ok and same_events and _analyst_state.get("report"):
        return _analyst_state["report"]

    report = await generate_analyst_report(latest_slice)
    _analyst_state["report"] = report
    _analyst_state["last_event_fp"] = event_fp
    _analyst_state["last_generated_ts"] = now_ts
    return report


def _v2_events_for_ai(limit: int = 160) -> List[dict]:
    rows = fetch_recent_v2_events_pg(limit=limit, source_whitelist=sorted(TELEGRAM_SOURCE_SET))
    if rows:
        return rows
    return [e for e in events_history[-limit:] if _is_telegram_source(e)]


def _normalize_threat_level(level: str) -> str:
    normalized = str(level or "").upper().strip()
    return normalized if normalized in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else "MEDIUM"


def _safe_v2_report(message: str) -> Dict[str, Any]:
    return {
        "summary": message,
        "threat_level": "MEDIUM",
        "key_developments": ["Insufficient verified evidence"],
        "insufficient_evidence": True,
        "generated_at": utc_now_iso(),
        "model": V2_MODEL_REPORT,
    }


@app.get("/api/v2/ai/policy")
async def v2_ai_policy():
    return _v2_ai_scheduler.status()


@app.get("/api/v2/ai/report")
async def v2_ai_report(force: bool = False):
    latest = _v2_events_for_ai(limit=160)
    latest_slice = [
        {
            "id": e.get("id"),
            "type": e.get("type"),
            "desc": e.get("description") or e.get("desc"),
            "source": _extract_source(e),
            "timestamp": e.get("timestamp"),
            "confidence": e.get("confidence_score"),
            "insufficient_evidence": bool(e.get("insufficient_evidence", False)),
        }
        for e in latest[-120:]
    ]
    fingerprint_seed = "|".join([f"{x.get('id')}@{x.get('timestamp')}" for x in latest_slice[-50:]])
    event_fp = hashlib.md5(fingerprint_seed.encode()).hexdigest() if fingerprint_seed else "empty"

    now_ts = time.time()
    age_ok = (now_ts - float(_v2_report_state.get("last_generated_ts", 0.0))) < V2_REPORT_CACHE_TTL_SEC
    same_events = _v2_report_state.get("last_event_fp") == event_fp
    if (not force) and age_ok and same_events and _v2_report_state.get("report"):
        return _v2_report_state["report"]
    if not latest_slice:
        return _safe_v2_report("No recent events available for v2 report generation.")

    evidence_lines = "\n".join(
        [
            f"- [{e.get('type', 'UNKNOWN')}] {e.get('desc', '')} "
            f"(source={e.get('source', '')}, confidence={e.get('confidence')}, insufficient={e.get('insufficient_evidence')})"
            for e in latest_slice[-45:]
        ]
    )
    prompt = f"""You are an OSINT report reasoning engine.
Return ONLY strict JSON:
{{
  "summary": "2-3 sentence report",
  "threat_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "key_developments": ["item1","item2","item3"],
  "insufficient_evidence": true|false
}}
Rules:
- Use only the evidence provided.
- If evidence is weak/contradictory: insufficient_evidence=true.
- If insufficient_evidence=true, threat_level cannot exceed MEDIUM.
- No markdown and no extra keys.

EVIDENCE:
{evidence_lines}
"""
    try:
        data = await _v2_ai_scheduler.run_json("report", prompt=prompt, temperature=0.05)
    except HTTPException:
        return _safe_v2_report("Report model unavailable or timed out.")

    key_developments = data.get("key_developments") if isinstance(data.get("key_developments"), list) else []
    key_developments = [str(x)[:220] for x in key_developments[:5]] or ["Insufficient verified evidence"]
    insufficient = bool(data.get("insufficient_evidence", False))
    threat = _normalize_threat_level(str(data.get("threat_level", "MEDIUM")))
    if insufficient and threat in {"HIGH", "CRITICAL"}:
        threat = "MEDIUM"
    summary = str(data.get("summary", "")).strip() or "Insufficient evidence to produce a stable v2 report."

    report = {
        "summary": summary,
        "threat_level": threat,
        "key_developments": key_developments,
        "insufficient_evidence": insufficient,
        "generated_at": utc_now_iso(),
        "model": V2_MODEL_REPORT,
    }
    _v2_report_state["report"] = report
    _v2_report_state["last_event_fp"] = event_fp
    _v2_report_state["last_generated_ts"] = now_ts
    return report


@app.post("/api/v2/ai/verify")
async def v2_ai_verify(payload: Dict[str, Any]):
    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip()
    source = str(payload.get("source", "")).strip()
    published_at = str(payload.get("published_at", "")).strip()
    if not (title or body):
        raise HTTPException(status_code=400, detail="title or body is required")

    prompt = f"""You are an OSINT verification classifier.
Return ONLY strict JSON:
{{
  "classification": "verified|likely|uncertain|disputed",
  "confidence_0_to_100": 0,
  "reasoning": ["reason1","reason2","reason3"],
  "required_follow_up": ["step1","step2"],
  "insufficient_evidence": true|false
}}
Rules:
- Prefer uncertain when evidence is limited.
- Keep each reason under 140 characters.
- No markdown and no extra keys.

SOURCE: {source or "unknown"}
PUBLISHED_AT: {published_at or "unknown"}
TITLE: {title}
BODY: {body}
"""
    data = await _v2_ai_scheduler.run_json("verify", prompt=prompt, temperature=0.0)
    classification = str(data.get("classification", "uncertain")).lower().strip()
    if classification not in {"verified", "likely", "uncertain", "disputed"}:
        classification = "uncertain"
    confidence = int(data.get("confidence_0_to_100", 40))
    reasons = data.get("reasoning") if isinstance(data.get("reasoning"), list) else []
    follow_up = data.get("required_follow_up") if isinstance(data.get("required_follow_up"), list) else []
    return {
        "classification": classification,
        "confidence_0_to_100": max(0, min(100, confidence)),
        "reasoning": [str(x)[:160] for x in reasons[:4]],
        "required_follow_up": [str(x)[:160] for x in follow_up[:4]],
        "insufficient_evidence": bool(data.get("insufficient_evidence", classification in {"uncertain", "disputed"})),
        "model": V2_MODEL_VERIFY,
        "generated_at": utc_now_iso(),
    }


@app.post("/api/media/consume")
async def media_consume(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    event_id = str(payload.get("event_id", "")).strip()
    video_url = str(payload.get("video_url", "")).strip()
    if not video_url.startswith("/media/telegram/"):
        raise HTTPException(status_code=400, detail="Only local telegram media can be consumed")

    filename = Path(video_url).name
    media_path = (TELEGRAM_MEDIA_DIR / filename).resolve()
    telegram_root = TELEGRAM_MEDIA_DIR.resolve()
    if telegram_root not in media_path.parents:
        raise HTTPException(status_code=400, detail="Invalid media path")

    removed = False
    if media_path.exists() and media_path.is_file():
        media_path.unlink(missing_ok=True)
        removed = True

    # Clear stale video_url from runtime + DB.
    if event_id:
        for e in events_history:
            if str(e.get("id")) == event_id:
                e["video_url"] = None
                persist_event(e)
                break
    else:
        for e in events_history:
            if str(e.get("video_url", "")) == video_url:
                e["video_url"] = None
                persist_event(e)

    return {"ok": True, "removed": removed, "video_url": video_url}


@app.get("/api/v2/system")
async def v2_system():
    pg = postgres_status()
    ai_status = _v2_ai_scheduler.status()
    return {
        "version": "v2-beta",
        "storage_backend": STORAGE_BACKEND,
        "ollama_model_primary": OLLAMA_MODEL,
        "ollama_model_fallback": OLLAMA_FALLBACK_MODEL,
        "ollama_models_available": sorted(_ollama_available_models),
        "v2_ai_models": {
            "default": V2_MODEL_DEFAULT,
            "verify": V2_MODEL_VERIFY,
            "report": V2_MODEL_REPORT,
        },
        "postgres": pg,
        "queue": {
            "media_jobs_pending": _media_jobs.qsize(),
            "media_jobs_tracked": len(_media_job_state),
        },
        "ai_policy": ai_status.get("policy"),
        "ai_runtime": ai_status.get("runtime"),
        "generated_at": utc_now_iso(),
    }


@app.get("/api/v2/overlays")
async def v2_overlays():
    return {
        "items": load_overlays(),
        "generated_at": utc_now_iso(),
    }


@app.get("/api/v2/metoc")
async def v2_metoc(lat: Optional[float] = None, lng: Optional[float] = None):
    if lat is None or lng is None:
        sample = fetch_recent_v2_events_pg(limit=120, source_whitelist=sorted(TELEGRAM_SOURCE_SET))
        if not sample:
            sample = list(events_history[-120:])
        if sample:
            lat = sum(float(e.get("lat", 0.0)) for e in sample) / len(sample)
            lng = sum(float(e.get("lng", 0.0)) for e in sample) / len(sample)
        else:
            lat, lng = 31.7683, 35.2137
    metoc = await fetch_metoc(float(lat), float(lng))
    return metoc


@app.post("/api/v2/ai/ops-brief")
async def v2_ai_ops_brief(payload: OpsBriefPayload):
    mode = str(payload.mode or "INTSUM").upper()
    limit = min(max(int(payload.limit or 20), 5), 40)
    recent = fetch_recent_v2_events_pg(
        limit=500,
        source_whitelist=sorted(TELEGRAM_SOURCE_SET),
        type_whitelist=["STRIKE", "CRITICAL", "CLASH", "MOVEMENT", "NOTAM"],
    )
    if not recent:
        recent = [e for e in events_history[-1200:] if _is_telegram_source(e)]
    recent_sorted = sorted(recent, key=lambda x: _parse_iso(str(x.get("timestamp", utc_now_iso()))), reverse=True)
    sample = recent_sorted[:limit]
    if not sample:
        return {"mode": mode, "summary": "No events available.", "verify": [], "report": None, "generated_at": utc_now_iso()}

    verify_cards = []
    for e in sample[: min(5, len(sample))]:
        try:
            verify_prompt = f"""You verify intelligence claims.
Return strict JSON:
{{
  "classification": "credible|uncertain|unlikely",
  "confidence_0_to_100": 0,
  "reasoning": ["..."],
  "required_follow_up": ["..."],
  "insufficient_evidence": false
}}
Title: {str(e.get('desc','')).replace('[','(').replace(']',')')[:180]}
Body: {str(e.get('desc',''))[:400]}
Source: {str(e.get('source',''))}
Timestamp: {str(e.get('timestamp',''))}
"""
            vr = await _v2_ai_scheduler.run_json("verify", verify_prompt, temperature=0.0)
            verify_cards.append(
                {
                    "event_id": e.get("id"),
                    "desc": str(e.get("desc", "")).replace("[", "(").replace("]", ")")[:200],
                    "source": e.get("source"),
                    "timestamp": e.get("timestamp"),
                    "result": vr,
                }
            )
        except Exception:
            continue

    context_lines = []
    for e in sample[:25]:
        mgrs_code = mgrs_from_latlng(float(e.get("lat", 0.0)), float(e.get("lng", 0.0))) or "N/A"
        context_lines.append(
            f"- [{e.get('type')}] {str(e.get('timestamp',''))} {str(e.get('source',''))} MGRS:{mgrs_code} :: {str(e.get('desc',''))[:180]}"
        )
    for v in verify_cards:
        res = v.get("result", {})
        context_lines.append(
            f"- VERIFY {v.get('event_id')} => {res.get('classification')} ({res.get('confidence_0_to_100')})"
        )

    report_prompt = f"""You are an operational intelligence reporting assistant.
Mode: {mode}
Return strict JSON:
{{
  "title": "string",
  "summary": "string",
  "paragraphs": ["..."],
  "priority_actions": ["..."],
  "risk_level": "low|medium|high|critical"
}}
Context:
{chr(10).join(context_lines)}
"""
    report_json = await _v2_ai_scheduler.run_json("report", report_prompt, temperature=0.1)
    priority_actions = report_json.get("priority_actions") if isinstance(report_json.get("priority_actions"), list) else []
    commander_chat = {
        "one_line_risk": str(report_json.get("summary", "")).strip()[:240],
        "next_actions": [str(x)[:180] for x in priority_actions[:5]],
    }
    return {
        "mode": mode,
        "verify": verify_cards,
        "report": report_json,
        "commander_chat": commander_chat,
        "model_policy": _v2_ai_scheduler.status().get("policy"),
        "generated_at": utc_now_iso(),
    }


@app.get("/api/v2/events")
async def v2_events(limit: int = 120, clustered: bool = False):
    limit = min(max(limit, 1), 400)
    rows = fetch_recent_v2_events_pg(limit=limit, source_whitelist=sorted(TELEGRAM_SOURCE_SET))
    if not rows:
        rows = [e for e in events_history[-1200:][::-1] if _is_telegram_source(e)][:limit]
    now = datetime.now(timezone.utc)
    by_bucket = defaultdict(list)
    for e in rows:
        key = (round(float(e.get("lat", 0.0)), 1), round(float(e.get("lng", 0.0)), 1))
        by_bucket[key].append(e)
    enriched = []
    for e in rows:
        x = dict(e)
        ts = _parse_iso(str(e.get("timestamp", utc_now_iso())))
        age_min = max(0.0, (now - ts).total_seconds() / 60.0)
        nearby = by_bucket[(round(float(e.get("lat", 0.0)), 1), round(float(e.get("lng", 0.0)), 1))]
        score, reason, corroborating = assess_confidence_v2(e, nearby, age_min)
        x["media"] = get_media_analysis(str(e.get("id", "")))
        x["review"] = _review_cache.get(str(e.get("id", "")))
        x["confidence_score"] = score
        x["confidence"] = "HIGH" if score >= 78 else ("MEDIUM" if score >= 55 else "LOW")
        x["confidence_reason"] = reason
        x["corroborating_sources"] = corroborating
        x["fact_vs_inference"] = {
            "facts": x.get("observed_facts", []),
            "inference": x.get("model_inference", []),
        }
        x["mgrs"] = mgrs_from_latlng(float(x.get("lat", 0.0)), float(x.get("lng", 0.0)))
        enriched.append(x)
    if clustered:
        return {"clusters": cluster_events_for_map(enriched), "items": enriched}
    return enriched


@app.get("/api/v2/alerts")
async def v2_alerts(limit: int = 60):
    limit = min(max(limit, 1), 120)
    now = datetime.now(timezone.utc)
    recent = fetch_recent_v2_events_pg(
        limit=700,
        source_whitelist=sorted(TELEGRAM_SOURCE_SET),
        type_whitelist=["STRIKE", "CRITICAL", "CLASH"],
    )
    if not recent:
        recent = [e for e in events_history[-1000:] if _is_telegram_source(e) and e.get("type") in {"STRIKE", "CRITICAL", "CLASH"}]
    by_bucket = defaultdict(list)
    for e in recent:
        by_bucket[(round(float(e.get("lat", 0.0)), 1), round(float(e.get("lng", 0.0)), 1))].append(e)

    cards = []
    alert_candidates = [x for x in recent if x.get("type") in ("STRIKE", "CRITICAL", "CLASH")]
    alert_candidates.sort(key=lambda x: _parse_iso(str(x.get("timestamp", utc_now_iso()))), reverse=True)
    for e in alert_candidates:
        ts = _parse_iso(str(e.get("timestamp", utc_now_iso())))
        age_min = max(0.0, (now - ts).total_seconds() / 60.0)
        nearby = by_bucket[(round(float(e.get("lat", 0.0)), 1), round(float(e.get("lng", 0.0)), 1))]
        score, reason, corroborating = assess_confidence_v2(e, nearby, age_min)
        confidence = "HIGH" if score >= 78 else ("MEDIUM" if score >= 55 else "LOW")
        cards.append(
            {
                "id": e.get("id"),
                "incident_id": e.get("incident_id"),
                "type": e.get("type"),
                "desc": e.get("desc"),
                "timestamp": e.get("timestamp"),
                "lat": e.get("lat"),
                "lng": e.get("lng"),
                "source": _extract_source(e),
                "confidence_score": score,
                "confidence": confidence,
                "confidence_reason": reason,
                "corroborating_sources": corroborating,
                "eta_band": eta_band(e),
                "age_minutes": round(age_min, 1),
                "observed_facts": e.get("observed_facts", []),
                "model_inference": e.get("model_inference", []),
                "insufficient_evidence": bool(e.get("insufficient_evidence", False)),
                "video_url": e.get("video_url"),
                "video_assessment": e.get("video_assessment"),
                "video_confidence": e.get("video_confidence"),
                "mgrs": mgrs_from_latlng(float(e.get("lat", 0.0)), float(e.get("lng", 0.0))),
                "media": get_media_analysis(str(e.get("id", ""))),
                "review": _review_cache.get(str(e.get("id", ""))),
            }
        )
    return cards[:limit]


@app.get("/api/v2/sources")
async def v2_sources(limit: int = 200):
    limit = min(max(limit, 1), 400)
    rows = fetch_recent_v2_events_pg(limit=limit, source_whitelist=sorted(TELEGRAM_SOURCE_SET))
    if not rows:
        rows = [r for r in events_history[-1200:][::-1] if _is_telegram_source(r)][:limit]
    grouped = defaultdict(int)
    for r in rows:
        grouped[_extract_source(r)] += 1
    ops = source_ops_metrics(window_minutes=120)
    degraded = [k for k, v in ops["per_source"].items() if v.get("degraded")]
    return {
        "items": rows,
        "counts_by_source": dict(sorted(grouped.items(), key=lambda x: x[1], reverse=True)),
        "reliability_profile": SOURCE_RELIABILITY,
        "ops": ops,
        "degraded_sources": degraded,
        "generated_at": utc_now_iso(),
    }


@app.post("/api/v2/reviews")
async def v2_reviews(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    event_id = str(payload.get("event_id", "")).strip()
    status = str(payload.get("status", "")).strip().lower()
    note = str(payload.get("note", "")).strip()[:500]
    if status not in {"confirm", "reject", "needs_review"}:
        raise HTTPException(status_code=400, detail="invalid status")
    if not event_id:
        raise HTTPException(status_code=400, detail="missing event_id")
    incident_id = next((e.get("incident_id") for e in events_history if e.get("id") == event_id), None)
    if _db is not None:
        _db.execute(
            """
            INSERT INTO reviews (event_id, incident_id, status, analyst, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, incident_id, status, actor, note, utc_now_iso()),
        )
        _db.commit()
    _review_cache[event_id] = {"status": status, "analyst": actor, "note": note, "updated_at": utc_now_iso()}
    audit_log("review.set", actor, role, payload, target_id=event_id)
    return {"ok": True, "event_id": event_id, "status": status}


@app.get("/api/v2/reviews")
async def v2_reviews_list(limit: int = 200):
    limit = min(max(limit, 1), 500)
    if _db is None:
        return []
    rows = _db.execute(
        """
        SELECT id, event_id, incident_id, status, analyst, note, created_at
        FROM reviews ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/v2/saved-views")
async def v2_saved_views_create(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    name = str(payload.get("name", "")).strip()[:120]
    filters = payload.get("filters", {})
    if not name:
        raise HTTPException(status_code=400, detail="missing name")
    if _db is not None:
        _db.execute(
            "INSERT INTO saved_views (name, owner, filters_json, created_at) VALUES (?, ?, ?, ?)",
            (name, actor, json.dumps(filters, ensure_ascii=False), utc_now_iso()),
        )
        _db.commit()
    audit_log("saved_view.create", actor, role, payload, target_id=name)
    return {"ok": True}


@app.get("/api/v2/saved-views")
async def v2_saved_views(request: Request, owner: str = "anon", x_api_key: Optional[str] = Header(default=None, alias="x-api-key")):
    if x_api_key != V2_API_KEY:
        owner = auth_user_from_request(request).get("username", "anon")
    if _db is None:
        return []
    rows = _db.execute(
        "SELECT id, name, owner, filters_json, created_at FROM saved_views WHERE owner = ? ORDER BY id DESC",
        (owner,),
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "owner": r["owner"],
                "filters": json.loads(r["filters_json"] or "{}"),
                "created_at": r["created_at"],
            }
        )
    return out


@app.post("/api/v2/watchlists")
async def v2_watchlist_create(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    name = str(payload.get("name", "")).strip()[:120]
    query = str(payload.get("query", "")).strip()[:220]
    tags = payload.get("tags", [])
    if not name or not query:
        raise HTTPException(status_code=400, detail="missing name/query")
    if _db is not None:
        _db.execute(
            "INSERT INTO watchlists (name, owner, query, tags_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, actor, query, json.dumps(tags, ensure_ascii=False), utc_now_iso()),
        )
        _db.commit()
    audit_log("watchlist.create", actor, role, payload, target_id=name)
    return {"ok": True}


@app.get("/api/v2/watchlists")
async def v2_watchlists(request: Request, owner: str = "anon", x_api_key: Optional[str] = Header(default=None, alias="x-api-key")):
    if x_api_key != V2_API_KEY:
        owner = auth_user_from_request(request).get("username", "anon")
    if _db is None:
        return []
    rows = _db.execute(
        "SELECT id, name, owner, query, tags_json, created_at FROM watchlists WHERE owner = ? ORDER BY id DESC",
        (owner,),
    ).fetchall()
    out = []
    for r in rows:
        query = str(r["query"])
        matched = [
            e for e in events_history[-300:]
            if query.lower() in str(e.get("desc", "")).lower() or query.lower() in str(_extract_source(e)).lower()
        ]
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "owner": r["owner"],
                "query": query,
                "tags": json.loads(r["tags_json"] or "[]"),
                "hits": len(matched),
                "created_at": r["created_at"],
            }
        )
    return out


@app.post("/api/v2/pins")
async def v2_pin_incident(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    incident_id = str(payload.get("incident_id", "")).strip()
    note = str(payload.get("note", "")).strip()[:400]
    if not incident_id:
        raise HTTPException(status_code=400, detail="missing incident_id")
    if _db is not None:
        _db.execute(
            """
            INSERT OR REPLACE INTO pinned_incidents (incident_id, owner, note, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (incident_id, actor, note, utc_now_iso()),
        )
        _db.commit()
    audit_log("pin.set", actor, role, payload, target_id=incident_id)
    return {"ok": True}


@app.get("/api/v2/pins")
async def v2_pins(request: Request, owner: str = "anon", x_api_key: Optional[str] = Header(default=None, alias="x-api-key")):
    if x_api_key != V2_API_KEY:
        owner = auth_user_from_request(request).get("username", "anon")
    if _db is None:
        return []
    rows = _db.execute(
        "SELECT incident_id, owner, note, created_at FROM pinned_incidents WHERE owner = ? ORDER BY created_at DESC",
        (owner,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/v2/handoff")
async def v2_handoff_add(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    incident_id = str(payload.get("incident_id", "")).strip()
    note = str(payload.get("note", "")).strip()[:1000]
    if not incident_id or not note:
        raise HTTPException(status_code=400, detail="missing incident_id/note")
    if _db is not None:
        _db.execute(
            "INSERT INTO handoff_notes (incident_id, owner, note, created_at) VALUES (?, ?, ?, ?)",
            (incident_id, actor, note, utc_now_iso()),
        )
        _db.commit()
    audit_log("handoff.add", actor, role, payload, target_id=incident_id)
    return {"ok": True}


@app.get("/api/v2/handoff")
async def v2_handoff(incident_id: str):
    if _db is None:
        return []
    rows = _db.execute(
        "SELECT id, incident_id, owner, note, created_at FROM handoff_notes WHERE incident_id = ? ORDER BY id DESC",
        (incident_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/v2/notifications")
async def v2_notifications_create(
    payload: Dict[str, Any],
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    x_role: str = Header(default="viewer", alias="x-role"),
    x_actor: str = Header(default="anon", alias="x-actor"),
):
    identity = resolve_write_identity(request, x_api_key=x_api_key, x_actor=x_actor, x_role=x_role)
    actor = identity["username"]
    role = identity["role"]
    min_confidence = int(payload.get("min_confidence", 75))
    event_types = payload.get("event_types", ["CRITICAL"])
    channels = payload.get("channels", ["in_app"])
    enabled = 1 if payload.get("enabled", True) else 0
    if _db is not None:
        _db.execute(
            """
            INSERT INTO notification_rules (owner, min_confidence, event_types_json, channels_json, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (actor, min_confidence, json.dumps(event_types), json.dumps(channels), enabled, utc_now_iso()),
        )
        _db.commit()
    audit_log("notifications.create", actor, role, payload)
    return {"ok": True}


@app.get("/api/v2/notifications")
async def v2_notifications(request: Request, owner: str = "anon", x_api_key: Optional[str] = Header(default=None, alias="x-api-key")):
    if x_api_key != V2_API_KEY:
        owner = auth_user_from_request(request).get("username", "anon")
    if _db is None:
        return []
    rows = _db.execute(
        """
        SELECT id, owner, min_confidence, event_types_json, channels_json, enabled, created_at
        FROM notification_rules WHERE owner = ? ORDER BY id DESC
        """,
        (owner,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "owner": r["owner"],
            "min_confidence": r["min_confidence"],
            "event_types": json.loads(r["event_types_json"] or "[]"),
            "channels": json.loads(r["channels_json"] or "[]"),
            "enabled": bool(r["enabled"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@app.get("/api/v2/evaluation/scorecard")
async def v2_eval_scorecard():
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    reviews = []
    if _db is not None:
        reviews = _db.execute(
            "SELECT event_id, status, created_at FROM reviews WHERE created_at >= ?",
            (week_ago,),
        ).fetchall()
    total = len(reviews)
    confirmed = sum(1 for r in reviews if r["status"] == "confirm")
    rejected = sum(1 for r in reviews if r["status"] == "reject")
    needs_review = sum(1 for r in reviews if r["status"] == "needs_review")
    false_positive_rate = round((rejected / total) * 100.0, 2) if total else 0.0
    geo_with_evidence = [e for e in events_history[-600:] if not e.get("insufficient_evidence")]
    geo_accuracy_proxy = round((len(geo_with_evidence) / max(1, len(events_history[-600:]))) * 100.0, 2)
    return {
        "window_days": 7,
        "reviewed_total": total,
        "confirmed": confirmed,
        "rejected": rejected,
        "needs_review": needs_review,
        "false_positive_rate_pct": false_positive_rate,
        "geo_accuracy_proxy_pct": geo_accuracy_proxy,
        "generated_at": utc_now_iso(),
    }


@app.get("/api/v2/onboarding")
async def v2_onboarding():
    return {
        "title": "How to read confidence",
        "steps": [
            "Observed Facts are extracted signal data.",
            "Model Inference is machine-generated interpretation and can be wrong.",
            "High confidence requires source reliability plus corroboration.",
            "Always validate critical alerts with official civil-defense channels.",
        ],
        "disclaimer": "This dashboard is advisory and not an official warning system.",
    }


@app.get("/api/v2/ops/dashboard")
async def v2_ops_dashboard():
    warnings = _watchdog_check()
    pg = postgres_status()
    return {
        "status": "nominal" if not warnings else "degraded",
        "uptime_seconds": int(time.time() - _start_time),
        "watchdog_warnings": warnings,
        "metrics": metrics,
        "queues": {
            "events_history": len(events_history),
            "events_buffer": len(events_buffer),
            "media_jobs_pending": _media_jobs.qsize(),
            "media_jobs_tracked": len(_media_job_state),
            "seen_articles": len(seen_articles),
            "seen_telegram_posts": len(seen_telegram_posts),
        },
        "postgres": pg,
        "generated_at": utc_now_iso(),
    }


@app.get("/api/v2/ops/alerts")
async def v2_ops_alerts():
    alerts = build_ops_alerts()
    return {
        "alerts": alerts,
        "total": len(alerts),
        "critical": sum(1 for a in alerts if a.get("severity") == "critical"),
        "warning": sum(1 for a in alerts if a.get("severity") == "warning"),
        "generated_at": utc_now_iso(),
    }


@app.get("/metrics")
async def metrics_endpoint():
    payload = render_prometheus_metrics()
    return Response(content=payload, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.websocket("/ws/live/v2")
async def ws_endpoint_v2(websocket: WebSocket):
    if not auth_user_from_websocket(websocket):
        await websocket.close(code=1008, reason="Authentication required")
        return
    await manager.connect(websocket)
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "SYSTEM",
                    "message": "Connected to OSINT Nexus v2 stream (diff + compact updates).",
                }
            )
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws/live")
async def ws_endpoint(websocket: WebSocket):
    if not auth_user_from_websocket(websocket):
        await websocket.close(code=1008, reason="Authentication required")
        return
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
