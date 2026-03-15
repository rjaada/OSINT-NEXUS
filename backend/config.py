"""
Central configuration — all environment variables and static constants.
Import from here instead of reading os.getenv() scattered across main.py.
"""

import os
import urllib.parse
from pathlib import Path
from typing import Dict, List, Set


def _secret(name: str, env_fallback: str = "") -> str:
    """Read from /run/secrets/<name> if it exists, else fall back to env var."""
    import pathlib
    p = pathlib.Path(f"/run/secrets/{name}")
    if p.exists():
        return p.read_text().strip()
    return env_fallback

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/tmp/osint_nexus_media"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
TELEGRAM_MEDIA_DIR = MEDIA_DIR / "telegram"
TELEGRAM_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
OVERLAY_DIR = Path(os.getenv("OVERLAY_DIR", "/tmp/osint_overlays"))
OVERLAY_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = os.getenv("OSINT_DB_PATH", "/tmp/osint_nexus.db")

# ---------------------------------------------------------------------------
# Database & Storage
# ---------------------------------------------------------------------------
# Build DATABASE_URL from individual parts so special characters in the
# password (e.g. "@") are always percent-encoded and never corrupt the URL.
_pg_password = _secret("postgres_password", os.getenv("POSTGRES_PASSWORD", ""))
_pg_host = os.getenv("POSTGRES_HOST", "postgres")
_pg_user = os.getenv("POSTGRES_USER", "osint")
_pg_db = os.getenv("POSTGRES_DB", "osint")
if _pg_password:
    _encoded = urllib.parse.quote(_pg_password, safe="")
    DATABASE_URL = f"postgresql://{_pg_user}:{_encoded}@{_pg_host}:5432/{_pg_db}"
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "")
STORAGE_BACKEND = "postgres" if DATABASE_URL.startswith("postgres") else "sqlite"
NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USER = os.getenv("NEO4J_USER", "")
NEO4J_PASSWORD = _secret("neo4j_password", os.getenv("NEO4J_PASSWORD", ""))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ORIGINS: List[str] = [
    x.strip()
    for x in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if x.strip()
]

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_SECRET = _secret("auth_secret", os.getenv("AUTH_SECRET", ""))
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

AUTH_ENABLE_TOTP = os.getenv("AUTH_ENABLE_TOTP", "1").lower() in ("1", "true", "yes", "on")
AUTH_TOTP_REQUIRED_ROLES: Set[str] = {
    r.strip().lower()
    for r in os.getenv("AUTH_TOTP_REQUIRED_ROLES", "analyst,admin").split(",")
    if r.strip()
}
AUTH_ADMIN_REQUIRE_PASSKEY = os.getenv("AUTH_ADMIN_REQUIRE_PASSKEY", "1").lower() in ("1", "true", "yes", "on")
AUTH_BREAK_GLASS_CODE = os.getenv("AUTH_BREAK_GLASS_CODE", "")

# ---------------------------------------------------------------------------
# Passkey / WebAuthn
# ---------------------------------------------------------------------------
PASSKEY_RP_ID = os.getenv("PASSKEY_RP_ID", "localhost")
PASSKEY_RP_NAME = os.getenv("PASSKEY_RP_NAME", "OSINT Nexus")
PASSKEY_ORIGINS: List[str] = [
    x.strip()
    for x in os.getenv("PASSKEY_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if x.strip()
]
PASSKEY_CHALLENGE_TTL_SEC = int(os.getenv("PASSKEY_CHALLENGE_TTL_SEC", "180"))

# ---------------------------------------------------------------------------
# Ollama / AI Models
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TRACE_TIMEOUT_SEC = int(os.getenv("GROQ_TRACE_TIMEOUT_SEC", "60"))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "llama3.1:8b")
OLLAMA_BASE_URL = OLLAMA_URL.rsplit("/api/", 1)[0] if "/api/" in OLLAMA_URL else "http://ollama:11434"
V2_MODEL_VERIFY = os.getenv("V2_MODEL_VERIFY", "phi4-mini")
V2_MODEL_REPORT = os.getenv("V2_MODEL_REPORT", "llama3.1:8b")
V2_MODEL_DEFAULT = os.getenv("V2_MODEL_DEFAULT", V2_MODEL_VERIFY)
V2_VERIFY_TIMEOUT_SEC = int(os.getenv("V2_VERIFY_TIMEOUT_SEC", "35"))
V2_REPORT_TIMEOUT_SEC = int(os.getenv("V2_REPORT_TIMEOUT_SEC", "120"))
V2_REPORT_CACHE_TTL_SEC = int(os.getenv("V2_REPORT_CACHE_TTL_SEC", "300"))
V2_API_KEY = os.getenv("V2_API_KEY", "")

# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------
GEOCODE_URL = os.getenv("GEOCODE_URL", "https://nominatim.openstreetmap.org/search")

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
DOWNLOAD_TELEGRAM_MEDIA = os.getenv("DOWNLOAD_TELEGRAM_MEDIA", "true").lower() in ("1", "true", "yes", "on")
TELEGRAM_LOOKBACK_POSTS = int(os.getenv("TELEGRAM_LOOKBACK_POSTS", "20"))
TELEGRAM_MAX_NEW_PER_POLL = int(os.getenv("TELEGRAM_MAX_NEW_PER_POLL", "8"))
TELEGRAM_MAX_MEDIA_MB = int(os.getenv("TELEGRAM_MAX_MEDIA_MB", "60"))
TELEGRAM_POLL_INTERVAL_SEC = int(os.getenv("TELEGRAM_POLL_INTERVAL_SEC", "3"))

# ---------------------------------------------------------------------------
# Data source toggles
# ---------------------------------------------------------------------------
ENABLE_ADSBLOL = os.getenv("ENABLE_ADSBLOL", "0").lower() in ("1", "true", "yes", "on")
ADSBLOL_API_URL = os.getenv("ADSBLOL_API_URL", "")
ADSBLOL_POLL_INTERVAL_SEC = int(os.getenv("ADSBLOL_POLL_INTERVAL_SEC", "10"))

ENABLE_AISSTREAM = os.getenv("ENABLE_AISSTREAM", "0").lower() in ("1", "true", "yes", "on")
AISSTREAM_WS_URL = os.getenv("AISSTREAM_WS_URL", "wss://stream.aisstream.io/v0/stream")
AISSTREAM_API_KEY = _secret("aisstream_api_key", os.getenv("AISSTREAM_API_KEY", ""))
AISSTREAM_BBOX = os.getenv("AISSTREAM_BBOX", "30,12,63,40")

ENABLE_FIRMS = os.getenv("ENABLE_FIRMS", "0").lower() in ("1", "true", "yes", "on")
FIRMS_MAP_KEY = _secret("firms_map_key", os.getenv("FIRMS_MAP_KEY", ""))
FIRMS_SOURCE = os.getenv("FIRMS_SOURCE", "VIIRS_SNPP_NRT")
FIRMS_BBOX = os.getenv("FIRMS_BBOX", "30,12,63,40")
FIRMS_DAYS = int(os.getenv("FIRMS_DAYS", "1"))
FIRMS_POLL_INTERVAL_SEC = int(os.getenv("FIRMS_POLL_INTERVAL_SEC", "180"))

# ---------------------------------------------------------------------------
# Media hooks (Whisper / Deepfake)
# ---------------------------------------------------------------------------
WHISPER_HOOK_URL = os.getenv("WHISPER_HOOK_URL", "")
DEEPFAKE_HOOK_URL = os.getenv("DEEPFAKE_HOOK_URL", "")
MEDIA_HOOK_TIMEOUT_SEC = int(os.getenv("MEDIA_HOOK_TIMEOUT_SEC", "35"))

# ---------------------------------------------------------------------------
# DEFCON
# ---------------------------------------------------------------------------
DEFCON_MANUAL_OVERRIDE = int(os.getenv("DEFCON_MANUAL_OVERRIDE", "0"))

# ---------------------------------------------------------------------------
# Intelligence: source reliability scores (0–100)
# ---------------------------------------------------------------------------
SOURCE_RELIABILITY: Dict[str, int] = {
    "Red Alert": 95,
    "Market Data": 92,
    "BBC News": 88,
    "DW News": 85,
    "France 24": 83,
    "NPR": 82,
    "Sky News": 78,
    "The Guardian": 75,
    "Al Jazeera": 72,
    "Jerusalem Post": 70,
    "AJ Mubasher (TG)": 60,
    "Roaa War Studies (TG)": 55,
    "FR24-MIL": 65,
    "ADSB.lol": 68,
    "AISStream": 66,
    "NASA FIRMS": 72,
}

# ---------------------------------------------------------------------------
# Intelligence: AoR bounding box & FR24 feed URL
# ---------------------------------------------------------------------------
BBOX = "40.0,12.0,30.0,63.0"
FR24_URL = (
    "https://data-cloud.flightradar24.com/zones/fcgi/feed.js"
    f"?bounds={BBOX}&faa=1&satellite=1&mlat=1&flarm=1&adsb=1"
    "&gnd=0&air=1&vehicles=0&estimated=1&maxage=14400&gliders=0&stats=1"
)

# ---------------------------------------------------------------------------
# Military call-sign prefixes (used to filter FR24 traffic)
# ---------------------------------------------------------------------------
MILITARY_PREFIXES: Set[str] = {
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

# ---------------------------------------------------------------------------
# Conflict relevance keywords (English + Arabic)
# ---------------------------------------------------------------------------
CONFLICT_KEYWORDS: List[str] = [
    "israel", "iran", "hamas", "hezbollah", "idf", "netanyahu", "beirut", "gaza", "lebanon", "houthi",
    "strike", "airstrike", "drone", "missile", "attack", "war", "military", "troops", "ceasefire", "sanctions",
    "nuclear", "irgc", "mossad", "centcom", "pentagon", "tehran", "tel aviv", "west bank", "jerusalem",
    "syria", "iraq", "yemen", "red sea", "hormuz", "naval", "qatar", "bahrain", "saudi", "uae", "kuwait", "oman",
    "pakistan", "afghanistan", "مسيّرة", "مسيرة", "صاروخ", "قصف", "هجوم", "استهداف", "تل أبيب", "طهران", "الضفة",
    "غزة", "إيران", "إسرائيلي", "إسرائيل", "العراق", "اليمن", "لبنان",
]

EVENT_TYPE_KEYWORDS_AR: Dict[str, List[str]] = {
    "STRIKE": ["قصف", "استهداف", "غارة", "انفجار", "ضربة", "صاروخ", "مسيرة", "مسيّرة"],
    "MOVEMENT": ["تحرك", "تحريك", "انتشار", "تعزيزات", "حشد", "قافلة", "أسطول"],
    "NOTAM": ["إغلاق المجال", "تحذير ملاحي", "إغلاق الأجواء", "تحذير جوي"],
    "CLASH": ["اشتباك", "اشتباكات", "تبادل إطلاق", "مواجهة"],
    "CRITICAL": ["حرب شاملة", "إعلان حرب", "نووي", "تصعيد غير مسبوق"],
}

# ---------------------------------------------------------------------------
# RSS feeds
# ---------------------------------------------------------------------------
RSS_FEEDS_EN = [
    # Trust tier 1 — public broadcasters with strict editorial standards, no owner agenda
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC News", "trust": 0.88},
    {"name": "BBC Middle East", "url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "source": "BBC News", "trust": 0.88},
    {"name": "DW World", "url": "https://rss.dw.com/rdf/rss-en-all", "source": "DW News", "trust": 0.85},
    {"name": "France 24 World", "url": "https://www.france24.com/en/rss", "source": "France 24", "trust": 0.82},
    {"name": "France 24 Middle East", "url": "https://www.france24.com/en/middle-east/rss", "source": "France 24", "trust": 0.84},
    {"name": "NPR World", "url": "https://feeds.npr.org/1004/rss.xml", "source": "NPR", "trust": 0.82},
    {"name": "Sky News World", "url": "https://feeds.skynews.com/feeds/rss/world.xml", "source": "Sky News", "trust": 0.78},
    # Trust tier 2 — regional perspective, strong factual record on the conflict
    {"name": "Al Jazeera English", "url": "https://www.aljazeera.com/xml/rss/all.xml", "source": "Al Jazeera", "trust": 0.72},
    {"name": "The Guardian World", "url": "https://www.theguardian.com/world/rss", "source": "The Guardian", "trust": 0.75},
    {"name": "Jerusalem Post", "url": "https://www.jpost.com/rss/rssfeedsheadlines.aspx", "source": "Jerusalem Post", "trust": 0.70},
]

# ---------------------------------------------------------------------------
# Telegram channels
# ---------------------------------------------------------------------------
TELEGRAM_CHANNELS = [
    {"slug": "ajMubasher", "source": "AJ Mubasher (TG)", "lang": "ar"},
    {"slug": "RoaaWarStudies", "source": "Roaa War Studies (TG)", "lang": "ar"},
]
TELEGRAM_SOURCE_SET: Set[str] = {str(ch.get("source", "")).strip() for ch in TELEGRAM_CHANNELS}

# ---------------------------------------------------------------------------
# Geo lookup tables
# ---------------------------------------------------------------------------
ISRAEL_CITY_COORDS: Dict[str, tuple] = {
    "תל אביב": (32.07, 34.78), "tel aviv": (32.07, 34.78),
    "ירושלים": (31.77, 35.21), "jerusalem": (31.77, 35.21),
    "חיפה": (32.79, 34.99), "haifa": (32.79, 34.99),
    "אשקלון": (31.66, 34.57), "ashkelon": (31.66, 34.57),
    "sderot": (31.52, 34.60),
}

PLACE_COORDS: Dict[str, tuple] = {
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

# ---------------------------------------------------------------------------
# Media job state limits (used in main.py runtime pruning)
# ---------------------------------------------------------------------------
MEDIA_JOB_STATE_TTL_SEC: int = int(os.getenv("MEDIA_JOB_STATE_TTL_SEC", "21600"))  # 6h
MEDIA_JOB_STATE_MAX: int = int(os.getenv("MEDIA_JOB_STATE_MAX", "3000"))
FAILED_LOGIN_MAX_TRACKED: int = int(os.getenv("FAILED_LOGIN_MAX_TRACKED", "20000"))
