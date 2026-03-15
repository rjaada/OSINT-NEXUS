"""
OSINT NEXUS — Real-time Intelligence Engine
"""

import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Sequence, Tuple
import logging
from pythonjsonlogger import jsonlogger

import feedparser
import httpx
from bs4 import BeautifulSoup
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
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
    from . import auth_passkey as authpasskey  # type: ignore
    from . import auth_handlers as authhandlers  # type: ignore
    from . import mfa_totp  # type: ignore
    from . import media_hooks  # type: ignore
    from . import osint_layers  # type: ignore
    from . import intel_utils as iutils  # type: ignore
    from . import v2_store  # type: ignore
    from . import graph_store as gstore  # type: ignore
    from . import groq_client  # type: ignore
    from . import db_sqlite  # type: ignore  # kept for legacy/test compat
    from . import db_postgres  # type: ignore
    from .config import *  # type: ignore
    from .config import (  # type: ignore
        ADSBLOL_API_URL, ADSBLOL_POLL_INTERVAL_SEC, AISSTREAM_API_KEY,
        AISSTREAM_BBOX, AISSTREAM_WS_URL, ALLOW_INSECURE_DEFAULTS,
        AUTH_ACCESS_HOURS, AUTH_ADMIN_REQUIRE_PASSKEY, AUTH_BREAK_GLASS_CODE,
        AUTH_COOKIE_SECURE, AUTH_DEFAULT_ADMIN_PASSWORD, AUTH_DEFAULT_ADMIN_USER,
        AUTH_ENABLE_TOTP, AUTH_LOGIN_LOCK_SEC, AUTH_LOGIN_MAX_ATTEMPTS,
        AUTH_RATE_LOGIN_PER_IP, AUTH_RATE_REGISTER_PER_IP, AUTH_RATE_WINDOW_SEC,
        AUTH_SECRET, AUTH_TOTP_REQUIRED_ROLES, BBOX, CONFLICT_KEYWORDS,
        CORS_ORIGINS, DATABASE_URL, DB_PATH, DEEPFAKE_HOOK_URL,
        DEFCON_MANUAL_OVERRIDE, DOWNLOAD_TELEGRAM_MEDIA, ENABLE_ADSBLOL,
        ENABLE_AISSTREAM, ENABLE_FIRMS, EVENT_TYPE_KEYWORDS_AR, FIRMS_BBOX,
        FIRMS_DAYS, FIRMS_MAP_KEY, FIRMS_POLL_INTERVAL_SEC, FIRMS_SOURCE,
        FR24_URL, GEOCODE_URL, MEDIA_DIR, MEDIA_HOOK_TIMEOUT_SEC,
        MILITARY_PREFIXES, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER,
        OLLAMA_BASE_URL, OLLAMA_FALLBACK_MODEL, OLLAMA_MODEL, OLLAMA_URL,
        OVERLAY_DIR, PASSKEY_CHALLENGE_TTL_SEC, PASSKEY_ORIGINS, PASSKEY_RP_ID,
        PASSKEY_RP_NAME, RSS_FEEDS_EN, SOURCE_RELIABILITY, STORAGE_BACKEND,
        TELEGRAM_CHANNELS, TELEGRAM_LOOKBACK_POSTS, TELEGRAM_MAX_MEDIA_MB,
        TELEGRAM_MAX_NEW_PER_POLL, TELEGRAM_MEDIA_DIR, TELEGRAM_POLL_INTERVAL_SEC,
        TELEGRAM_SOURCE_SET, V2_API_KEY, V2_MODEL_DEFAULT, V2_MODEL_REPORT,
        V2_MODEL_VERIFY, V2_REPORT_CACHE_TTL_SEC, V2_REPORT_TIMEOUT_SEC,
        V2_VERIFY_TIMEOUT_SEC, WHISPER_HOOK_URL,
        ISRAEL_CITY_COORDS, PLACE_COORDS,
        MEDIA_JOB_STATE_TTL_SEC, MEDIA_JOB_STATE_MAX, FAILED_LOGIN_MAX_TRACKED,
    )
except ImportError:
    from analyst import generate_analyst_report
    import auth_security as authsec
    import auth_store as authstore
    import auth_passkey as authpasskey
    import auth_handlers as authhandlers
    import mfa_totp
    import media_hooks
    import osint_layers
    import intel_utils as iutils
    import v2_store
    import graph_store as gstore
    import groq_client
    import db_sqlite  # kept for legacy/test compat
    import db_postgres
    from config import *
    from config import (
        ADSBLOL_API_URL, ADSBLOL_POLL_INTERVAL_SEC, AISSTREAM_API_KEY,
        AISSTREAM_BBOX, AISSTREAM_WS_URL, ALLOW_INSECURE_DEFAULTS,
        AUTH_ACCESS_HOURS, AUTH_ADMIN_REQUIRE_PASSKEY, AUTH_BREAK_GLASS_CODE,
        AUTH_COOKIE_SECURE, AUTH_DEFAULT_ADMIN_PASSWORD, AUTH_DEFAULT_ADMIN_USER,
        AUTH_ENABLE_TOTP, AUTH_LOGIN_LOCK_SEC, AUTH_LOGIN_MAX_ATTEMPTS,
        AUTH_RATE_LOGIN_PER_IP, AUTH_RATE_REGISTER_PER_IP, AUTH_RATE_WINDOW_SEC,
        AUTH_SECRET, AUTH_TOTP_REQUIRED_ROLES, BBOX, CONFLICT_KEYWORDS,
        CORS_ORIGINS, DATABASE_URL, DB_PATH, DEEPFAKE_HOOK_URL,
        DEFCON_MANUAL_OVERRIDE, DOWNLOAD_TELEGRAM_MEDIA, ENABLE_ADSBLOL,
        ENABLE_AISSTREAM, ENABLE_FIRMS, EVENT_TYPE_KEYWORDS_AR, FIRMS_BBOX,
        FIRMS_DAYS, FIRMS_MAP_KEY, FIRMS_POLL_INTERVAL_SEC, FIRMS_SOURCE,
        FR24_URL, GEOCODE_URL, MEDIA_DIR, MEDIA_HOOK_TIMEOUT_SEC,
        MILITARY_PREFIXES, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER,
        OLLAMA_BASE_URL, OLLAMA_FALLBACK_MODEL, OLLAMA_MODEL, OLLAMA_URL,
        OVERLAY_DIR, PASSKEY_CHALLENGE_TTL_SEC, PASSKEY_ORIGINS, PASSKEY_RP_ID,
        PASSKEY_RP_NAME, RSS_FEEDS_EN, SOURCE_RELIABILITY, STORAGE_BACKEND,
        TELEGRAM_CHANNELS, TELEGRAM_LOOKBACK_POSTS, TELEGRAM_MAX_MEDIA_MB,
        TELEGRAM_MAX_NEW_PER_POLL, TELEGRAM_MEDIA_DIR, TELEGRAM_POLL_INTERVAL_SEC,
        TELEGRAM_SOURCE_SET, V2_API_KEY, V2_MODEL_DEFAULT, V2_MODEL_REPORT,
        V2_MODEL_VERIFY, V2_REPORT_CACHE_TTL_SEC, V2_REPORT_TIMEOUT_SEC,
        V2_VERIFY_TIMEOUT_SEC, WHISPER_HOOK_URL,
        ISRAEL_CITY_COORDS, PLACE_COORDS,
        MEDIA_JOB_STATE_TTL_SEC, MEDIA_JOB_STATE_MAX, FAILED_LOGIN_MAX_TRACKED,
    )

_json_handler = logging.StreamHandler()
_json_handler.setFormatter(jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
))
logging.root.addHandler(_json_handler)
logging.root.setLevel(logging.INFO)
logger = logging.getLogger("osint")

# ── DB operations (extracted to db_ops.py) ───────────────────────────────────
from db_ops import (  # noqa: E402
    init_db,
    load_recent_events,
    persist_event,
    audit_log,
    persist_media_analysis,
    get_media_analysis,
    postgres_status,
)

app = FastAPI(title="OSINT Nexus Engine v3")

try:
    from webauthn import (
        generate_authentication_options,
        generate_registration_options,
        verify_authentication_response,
        verify_registration_response,
    )
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json
    from webauthn.helpers.structs import (
        PublicKeyCredentialDescriptor,
        PublicKeyCredentialType,
        UserVerificationRequirement,
    )
    WEBAUTHN_AVAILABLE = True
except Exception:
    WEBAUTHN_AVAILABLE = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


_WS_MAX_TOTAL = 200   # global connection ceiling
_WS_MAX_PER_IP = 10   # per-IP ceiling (prevents one client monopolising the bus)


class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []
        self._per_ip: Dict[str, int] = {}

    async def connect(self, ws: WebSocket) -> bool:
        """Accept the WebSocket and track it. Returns False and closes if limits are exceeded."""
        ip = (ws.client.host if ws.client else "unknown") or "unknown"
        if len(self.connections) >= _WS_MAX_TOTAL:
            await ws.close(code=1008, reason="Server connection limit reached")
            return False
        if self._per_ip.get(ip, 0) >= _WS_MAX_PER_IP:
            await ws.close(code=1008, reason="Per-IP connection limit reached")
            return False
        await ws.accept()
        self.connections.append(ws)
        self._per_ip[ip] = self._per_ip.get(ip, 0) + 1
        return True

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)
            ip = (ws.client.host if ws.client else "unknown") or "unknown"
            self._per_ip[ip] = max(0, self._per_ip.get(ip, 1) - 1)
            if self._per_ip[ip] == 0:
                self._per_ip.pop(ip, None)

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
_seen_articles_order = deque(maxlen=30_000)
seen_telegram_posts: set = set()
_seen_telegram_order = deque(maxlen=10_000)
seen_alerts: set = set()
_seen_alerts_order = deque(maxlen=20_000)

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
    "adsblol_polls": 0,
    "ais_polls": 0,
    "firms_polls": 0,
    "rss_errors": 0,
    "telegram_errors": 0,
    "flight_errors": 0,
    "red_alert_errors": 0,
    "adsblol_errors": 0,
    "ais_errors": 0,
    "firms_errors": 0,
    "db_writes": 0,
    "dedup_dropped": 0,
    "watchdog_warnings": 0,
    "last_success": {
        "rss": None,
        "telegram": None,
        "flights": None,
        "red_alert": None,
        "adsblol": None,
        "ais": None,
        "firms": None,
    },
}

_start_time = time.time()
_db: Optional[Any] = None  # psycopg3 Connection, set at startup
_ollama_http_client: Optional[httpx.AsyncClient] = None
_geocode_http_client: Optional[httpx.AsyncClient] = None
_graph_store: Optional[gstore.GraphStore] = None
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
graph_logger = logging.getLogger("osint.graph")
_passkey_reg_challenges: Dict[str, Dict[str, Any]] = {}
_passkey_auth_challenges: Dict[str, Dict[str, Any]] = {}

_MEDIA_JOB_STATE_TTL_SEC = MEDIA_JOB_STATE_TTL_SEC
_MEDIA_JOB_STATE_MAX = MEDIA_JOB_STATE_MAX
_FAILED_LOGIN_MAX_TRACKED = FAILED_LOGIN_MAX_TRACKED
_defcon_state: Dict[str, Any] = {
    "level": 5,
    "reason": "Baseline monitoring state",
    "updated_at": None,
    "event_count": 0,
    "confidence_avg": 0,
    "capped_from_1": False,
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


def require_analyst_or_admin(request: Request) -> dict:
    verified = auth_user_from_request(request)
    role = str(verified.get("role", "")).lower()
    if role not in {"admin", "analyst"}:
        raise HTTPException(status_code=403, detail="Analyst or admin role required")
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


def _graph_source_id(source: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", source.lower()).strip("_")
    if not normalized:
        normalized = "unknown"
    return f"source:{normalized}"


async def _sync_event_to_graph_async(event: dict) -> None:
    if _graph_store is None or not _graph_store.status().get("connected"):
        return
    try:
        payload = dict(event)
        payload["source_name"] = _extract_source(event)
        payload["source"] = payload["source_name"]
        await asyncio.to_thread(_graph_store.upsert_event_node, payload)

        # Entity extraction via Groq — Telegram + high-trust RSS sources (trust >= 0.80)
        # High-trust RSS: BBC News, DW News, France 24, NPR
        _HIGH_TRUST_RSS = {"BBC News", "DW News", "France 24", "NPR"}
        src_name = payload["source_name"]
        _run_extraction = _is_telegram_source(event) or src_name in _HIGH_TRUST_RSS
        if groq_client.groq_available() and _run_extraction:
            desc = str(event.get("description") or event.get("desc") or event.get("title") or "")
            if desc:
                event_id = str(event.get("id") or "")
                entities = await asyncio.to_thread(groq_client.extract_entities, desc)
                if entities.get("actors"):
                    await asyncio.to_thread(_graph_store.link_event_actors, event_id, entities["actors"])
                if entities.get("weapons"):
                    await asyncio.to_thread(_graph_store.link_event_weapons, event_id, entities["weapons"])

        # Temporal enrichment — predecessor linking + anomaly scoring
        import temporal_kg
        event_id = str(event.get("id") or "")
        ts = str(event.get("timestamp") or "")
        lat = event.get("lat")
        lng = event.get("lng")
        if event_id and ts and lat is not None and lng is not None:
            await asyncio.to_thread(
                temporal_kg.enrich_event_with_temporal_context,
                _graph_store, event_id, ts, float(lat), float(lng),
            )
    except Exception as exc:
        graph_logger.warning("[GRAPH] failed to sync event %s: %s", str(event.get("id", "")), exc)


# init_db, load_recent_events → moved to db_ops.py


# persist_event → moved to db_ops.py


# audit_log → moved to db_ops.py


def evaluate_claim_alignment(desc: str, ocr_lines: List[str], stt_lines: List[str]) -> Tuple[str, str]:
    return iutils.evaluate_claim_alignment(desc, ocr_lines, stt_lines)


def _safe_run(cmd: List[str], timeout_sec: int = 20) -> Tuple[bool, str]:
    return iutils.safe_run(cmd, timeout_sec)


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
        candidate = (MEDIA_DIR / "telegram" / Path(video_url).name).resolve()
        # Ensure the resolved path stays within TELEGRAM_MEDIA_DIR (defense-in-depth).
        if str(candidate).startswith(str(TELEGRAM_MEDIA_DIR.resolve())):
            local_file = str(candidate)

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

    hook_data: Dict[str, Any] = {}
    hook_data.update(
        media_hooks.whisper_transcribe(
            whisper_url=WHISPER_HOOK_URL,
            media_local_path=local_file,
            media_remote_url=str(video_url),
            timeout_sec=MEDIA_HOOK_TIMEOUT_SEC,
        )
    )
    hook_data.update(
        media_hooks.deepfake_analyze(
            deepfake_url=DEEPFAKE_HOOK_URL,
            media_local_path=local_file,
            media_remote_url=str(video_url),
            timeout_sec=MEDIA_HOOK_TIMEOUT_SEC,
        )
    )
    transcript = str(hook_data.get("transcript_text", "")).strip()
    if transcript:
        stt_lines.insert(0, transcript[:180])

    align, note = evaluate_claim_alignment(str(event.get("desc", "")), ocr_lines, stt_lines)
    return {
        "status": status,
        "keyframes": keyframes[:6],
        "ocr_snippets": ocr_lines[:6],
        "stt_snippets": stt_lines[:6],
        "claim_alignment": align,
        "credibility_note": note,
        "transcript_text": str(hook_data.get("transcript_text", "")),
        "transcript_language": str(hook_data.get("transcript_language", "")),
        "transcript_error": str(hook_data.get("transcript_error", "")),
        "deepfake_score": str(hook_data.get("deepfake_score", "")),
        "deepfake_label": str(hook_data.get("deepfake_label", "")),
        "deepfake_error": str(hook_data.get("deepfake_error", "")),
    }


# persist_media_analysis, get_media_analysis → moved to db_ops.py


async def media_worker():
    while True:
        job = await _media_jobs.get()
        event_id = str(job.get("event_id", "")).strip() or "unknown"
        try:
            _media_job_state[event_id] = {"status": "running", "updated_at": utc_now_iso()}
            result = await asyncio.to_thread(run_media_analysis, job.get("event", {}))
            persist_media_analysis(event_id, result)
            _media_job_state[event_id] = {"status": "done", "updated_at": utc_now_iso()}
        except Exception as e:
            _media_job_state[event_id] = {"status": "error", "updated_at": utc_now_iso(), "error": str(e)[:240]}
            logger.warning(f"[MEDIA] worker job failed for {event_id}: {e}")
        finally:
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


# postgres_status → moved to db_ops.py


def ensure_default_admin() -> None:
    authstore.ensure_default_admin(
        _db,
        default_admin_user=AUTH_DEFAULT_ADMIN_USER,
        default_admin_password=AUTH_DEFAULT_ADMIN_PASSWORD,
        hash_password=hash_password,
        now_iso=utc_now_iso,
    )


def get_user(username: str) -> Optional[Dict[str, Any]]:
    return authstore.get_user(_db, username)


def mfa_required_for_role(role: str) -> bool:
    if not AUTH_ENABLE_TOTP:
        return False
    return str(role or "").strip().lower() in AUTH_TOTP_REQUIRED_ROLES


def mfa_enabled_for_user(username: str) -> bool:
    if not AUTH_ENABLE_TOTP:
        return False
    return mfa_totp.is_enabled(_db, username.strip().lower())


def mfa_verify_user_code(username: str, code: str) -> bool:
    if not AUTH_ENABLE_TOTP:
        return True
    uname = username.strip().lower()
    secret = mfa_totp.get_secret(_db, uname)
    if not secret:
        return False
    return mfa_totp.verify_and_consume(_db, uname, secret, code)


def passkey_count_for_user(username: str) -> int:
    return authpasskey.count_for_user(_db, username.strip().lower())


def admin_password_block_reason(username: str, role: str, break_glass_code: str) -> Optional[str]:
    if str(role).strip().lower() != "admin":
        return None
    if not AUTH_ADMIN_REQUIRE_PASSKEY:
        return None
    if AUTH_BREAK_GLASS_CODE and break_glass_code and hmac.compare_digest(AUTH_BREAK_GLASS_CODE, break_glass_code):
        return None
    if passkey_count_for_user(username) <= 0:
        return "Admin passkey is required. Enroll passkey first or use break-glass."
    return "Admin password login is disabled. Use passkey authentication."


def _prune_passkey_challenges() -> None:
    now = time.time()
    for bag in (_passkey_reg_challenges, _passkey_auth_challenges):
        stale = [k for k, v in bag.items() if float(v.get("expires_at", 0)) < now]
        for k in stale:
            bag.pop(k, None)


def _track_seen_article(article_id: str) -> bool:
    if article_id in seen_articles:
        return False
    if len(_seen_articles_order) == _seen_articles_order.maxlen:
        oldest = _seen_articles_order.popleft()
        seen_articles.discard(oldest)
    _seen_articles_order.append(article_id)
    seen_articles.add(article_id)
    return True


def _track_seen_alert(alert_id: str) -> bool:
    if alert_id in seen_alerts:
        return False
    if len(_seen_alerts_order) == _seen_alerts_order.maxlen:
        oldest = _seen_alerts_order.popleft()
        seen_alerts.discard(oldest)
    _seen_alerts_order.append(alert_id)
    seen_alerts.add(alert_id)
    return True


def _track_seen_telegram(post_id: str) -> bool:
    if post_id in seen_telegram_posts:
        return False
    if len(_seen_telegram_order) == _seen_telegram_order.maxlen:
        oldest = _seen_telegram_order.popleft()
        seen_telegram_posts.discard(oldest)
    _seen_telegram_order.append(post_id)
    seen_telegram_posts.add(post_id)
    return True


def _prune_failed_logins() -> None:
    now = time.time()
    stale = [k for k, v in _failed_logins.items() if float(v.get("lock_until", 0)) + AUTH_LOGIN_LOCK_SEC < now]
    for k in stale:
        _failed_logins.pop(k, None)
    if len(_failed_logins) > _FAILED_LOGIN_MAX_TRACKED:
        # Drop oldest by lock_until first.
        overflow = len(_failed_logins) - _FAILED_LOGIN_MAX_TRACKED
        keys = sorted(_failed_logins.keys(), key=lambda k: float(_failed_logins[k].get("lock_until", 0)))
        for k in keys[:overflow]:
            _failed_logins.pop(k, None)


def _prune_media_job_state() -> None:
    now = datetime.now(timezone.utc)
    stale_keys: List[str] = []
    for event_id, state in _media_job_state.items():
        status = str(state.get("status", "")).lower()
        updated_at = str(state.get("updated_at", "")).strip()
        if status not in {"done", "error"}:
            continue
        ts = _parse_iso(updated_at) if updated_at else now
        if (now - ts).total_seconds() > _MEDIA_JOB_STATE_TTL_SEC:
            stale_keys.append(event_id)
    for event_id in stale_keys:
        _media_job_state.pop(event_id, None)

    if len(_media_job_state) > _MEDIA_JOB_STATE_MAX:
        # Keep latest updated entries.
        ordered = sorted(
            _media_job_state.items(),
            key=lambda kv: _parse_iso(str(kv[1].get("updated_at", utc_now_iso()))),
            reverse=True,
        )
        keep = dict(ordered[:_MEDIA_JOB_STATE_MAX])
        _media_job_state.clear()
        _media_job_state.update(keep)


def _prune_runtime_state() -> None:
    _prune_passkey_challenges()
    authsec.prune_rate_limit_store(_rate_limit, window_sec=AUTH_RATE_WINDOW_SEC)
    _prune_failed_logins()
    _prune_media_job_state()
    # Prune incident_index — keep only entries from the last 4 hours
    _incident_cutoff = utc_now_iso()
    try:
        _now_ts = time.time()
        stale_incidents = [
            k for k, v in list(incident_index.items())
            if (_now_ts - _parse_iso(str(v.get("timestamp", _incident_cutoff))).timestamp()) > 14400
        ]
        for k in stale_incidents:
            incident_index.pop(k, None)
    except Exception:
        pass
    # Cap _review_cache at 500 entries (drop oldest by insertion order)
    if len(_review_cache) > 500:
        excess = len(_review_cache) - 500
        for k in list(_review_cache.keys())[:excess]:
            _review_cache.pop(k, None)


def _set_auth_cookies(response: Response, username: str, role: str) -> dict:
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
            httponly=(key in ("osint_auth", "osint_role", "osint_session")),
            samesite="lax",
            secure=AUTH_COOKIE_SECURE,
        )
    return {"ok": True, "username": username, "role": role, "expires_at": expiry_dt.isoformat(), "csrf": csrf_token}


class AuthRegisterPayload(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class AuthLoginPayload(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = None
    break_glass_code: Optional[str] = None


class AuthTotpCodePayload(BaseModel):
    code: str


class PasskeyUserPayload(BaseModel):
    username: str


class PasskeyRegisterVerifyPayload(BaseModel):
    credential: Dict[str, Any]
    label: Optional[str] = None


class PasskeyLoginVerifyPayload(BaseModel):
    username: str
    credential: Dict[str, Any]


class AdminSetRolePayload(BaseModel):
    role: str


class OpsBriefPayload(BaseModel):
    mode: str = "INTSUM"
    limit: int = 20


def persist_event_v2_pg(event: dict):
    v2_store.persist_event_v2_pg(
        event,
        database_url=DATABASE_URL,
        psycopg_mod=psycopg,
        extract_source=_extract_source,
        now_iso=utc_now_iso,
    )


def fetch_recent_v2_events_pg(
    limit: int = 200,
    source_whitelist: Optional[Sequence[str]] = None,
    type_whitelist: Optional[Sequence[str]] = None,
) -> List[dict]:
    return v2_store.fetch_recent_v2_events_pg(
        database_url=DATABASE_URL,
        psycopg_mod=psycopg,
        now_iso=utc_now_iso,
        limit=limit,
        source_whitelist=source_whitelist,
        type_whitelist=type_whitelist,
    )


def persist_ai_report(report_type: str, report: dict, event_fp: str) -> None:
    v2_store.persist_ai_report_pg(
        report_type=report_type,
        report=report,
        event_fp=event_fp,
        database_url=DATABASE_URL,
        psycopg_mod=psycopg,
    )


def load_latest_ai_report(report_type: str) -> Optional[dict]:
    return v2_store.load_latest_ai_report_pg(
        report_type=report_type,
        database_url=DATABASE_URL,
        psycopg_mod=psycopg,
    )


def fetch_ai_report_history(report_type: str, limit: int = 50) -> List[dict]:
    return v2_store.fetch_ai_report_history_pg(
        report_type=report_type,
        limit=limit,
        database_url=DATABASE_URL,
        psycopg_mod=psycopg,
    )


def cluster_events_for_map(items: List[dict], zoom_bucket: int = 2) -> List[dict]:
    return iutils.cluster_events_for_map(items, zoom_bucket=zoom_bucket)


# ---------------------------------------------------------------------------
# SITREP + prediction tracker accessors (Layer 3 + 4)
# ---------------------------------------------------------------------------
import reasoning_engine as _reasoning_engine
import prediction_tracker as _prediction_tracker


def fetch_sitrep_accuracy() -> dict:
    return _prediction_tracker.fetch_accuracy_stats(
        database_url=DATABASE_URL,
        psycopg_mod=psycopg,
    )


def store_sitrep_watch_items(sitrep_id: str, watch_items: list) -> None:
    _prediction_tracker.store_watch_items(
        sitrep_id=sitrep_id,
        watch_items=watch_items,
        database_url=DATABASE_URL,
        psycopg_mod=psycopg,
    )


def score_sitrep_predictions(recent_events: list) -> int:
    return _prediction_tracker.score_pending_predictions(
        recent_events=recent_events,
        database_url=DATABASE_URL,
        psycopg_mod=psycopg,
    )


def assess_confidence_v2(event: dict, nearby: list, age_min: float) -> Tuple[int, str, List[str]]:
    return iutils.assess_confidence_v2(event, nearby, age_min, assess_confidence_fn=assess_confidence)


def is_military(callsign: str, icao24: str) -> bool:
    return iutils.is_military(callsign, icao24, MILITARY_PREFIXES)


def _parse_iso(ts: str) -> datetime:
    return iutils.parse_iso(ts, now_iso=utc_now_iso)


def _extract_source(event: dict) -> str:
    return iutils.extract_source(event)


def _is_telegram_source(event: dict) -> bool:
    return iutils.is_telegram_source(event, TELEGRAM_SOURCE_SET)


def _get_ollama_client() -> httpx.AsyncClient:
    global _ollama_http_client
    if _ollama_http_client is None:
        _ollama_http_client = httpx.AsyncClient(timeout=60)
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
            logger.warning("[OLLAMA] No local models available from /api/tags")
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
        logger.info(f"[OLLAMA] Runtime model chain: primary={OLLAMA_MODEL}, fallback={OLLAMA_FALLBACK_MODEL}")
    except Exception as e:
        logger.warning(f"[OLLAMA] Model discovery failed: {e}")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return iutils.haversine_km(lat1, lon1, lat2, lon2)


def normalize_desc(desc: str) -> str:
    return iutils.normalize_desc(desc)


def article_id(entry) -> str:
    return iutils.article_id(entry)


def classify_event(title: str, summary: str) -> str:
    return iutils.classify_event(title, summary, EVENT_TYPE_KEYWORDS_AR)


def extract_place_candidates(text: str) -> List[str]:
    return iutils.extract_place_candidates(text, PLACE_COORDS)


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
        # Keep strict model separation by task:
        # verify -> verify chain, report -> report chain.
        if task == "verify":
            for fallback_model in (V2_MODEL_DEFAULT,):
                if fallback_model and fallback_model not in candidate_models:
                    candidate_models.append(fallback_model)
        elif task == "report":
            for fallback_model in (OLLAMA_MODEL,):
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
                    timeout=45,
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
                    logger.warning(f"[OLLAMA] Missing model '{model_name}', removed from runtime chain")
                    break
                if attempt == retries:
                    logger.warning(f"[OLLAMA] JSON call failed ({model_name}): {e}")
                await asyncio.sleep(0.35 * (attempt + 1))
            except Exception as e:
                if attempt == retries:
                    logger.warning(f"[OLLAMA] JSON call failed ({model_name}): {e}")
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


async def geolocate_event(title: str, summary: str, fallback_seed: str, allow_ai: bool = True, use_geocoder: bool = True) -> dict:
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

    for place in (candidates[:2] if use_geocoder else []):
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
        video_src = None
        if video_node:
            # Telegram lazy-loads via data-src; fall back to <source> children
            video_src = (
                video_node.get("src")
                or video_node.get("data-src")
                or (video_node.select_one("source") and video_node.select_one("source").get("src"))
                or None
            )
            # Strip empty strings
            if video_src and not video_src.strip():
                video_src = None
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
            "--max-filesize", f"{TELEGRAM_MAX_MEDIA_MB}M",
            "--restrict-filenames",
            "-f", "mp4/best[ext=mp4]/best",
            "-o", out_tpl,
            post_url,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        for ext in ("mp4", "webm", "mkv", "mov"):
            candidate = TELEGRAM_MEDIA_DIR / f"{event_id}.{ext}"
            if candidate.exists():
                size_mb = candidate.stat().st_size / (1024 * 1024)
                if size_mb > TELEGRAM_MAX_MEDIA_MB:
                    candidate.unlink(missing_ok=True)
                    return None
                return f"/media/telegram/{candidate.name}"
    except Exception:
        return None
    return None


def download_video_direct(cdn_url: str, event_id: str) -> Optional[str]:
    """Download a Telegram CDN video URL directly with httpx, bypassing yt-dlp."""
    if not cdn_url or not DOWNLOAD_TELEGRAM_MEDIA:
        return None
    try:
        import httpx as _httpx
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://t.me/"}
        max_bytes = TELEGRAM_MAX_MEDIA_MB * 1024 * 1024
        with _httpx.stream("GET", cdn_url, headers=headers, follow_redirects=True, timeout=30) as r:
            if r.status_code != 200:
                return None
            ct = r.headers.get("content-type", "")
            if "video" not in ct and "octet" not in ct:
                return None
            ext = "mp4"
            if "webm" in ct:
                ext = "webm"
            dest = TELEGRAM_MEDIA_DIR / f"{event_id}.{ext}"
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        dest.unlink(missing_ok=True)
                        return None
                    f.write(chunk)
        return f"/media/telegram/{dest.name}"
    except Exception:
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


def is_playable_video_url(url: str) -> bool:
    if not url:
        return False
    if url.startswith("/media/telegram/"):
        local_path = TELEGRAM_MEDIA_DIR / Path(url).name
        return local_path.exists() and local_path.is_file()
    lower = url.lower()
    # Accept direct CDN URLs from Telegram even without file extension
    if "cdn.telegram.org" in lower or "cdn1.telegram.org" in lower or "cdn2.telegram.org" in lower:
        return True
    return bool(re.search(r"\.(mp4|webm|mov|m4v)(\?|$)", lower))


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
    return "inc_" + hashlib.sha256(key.encode()).hexdigest()[:14]


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
    asyncio.create_task(_sync_event_to_graph_async(event))
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
    return iutils.assess_confidence(event, nearby, age_min, SOURCE_RELIABILITY)


def eta_band(event: dict) -> str:
    return iutils.eta_band(event)


def geolocate_alert(city: str) -> tuple:
    return iutils.geolocate_alert(city, ISRAEL_CITY_COORDS)


async def poll_flights():
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        while True:
            await asyncio.sleep(30)
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
                logger.warning(f"[FR24] Error: {e}")


async def poll_rss():
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        while True:
            metrics["rss_polls"] += 1
            for feed_cfg in RSS_FEEDS_EN:
                try:
                    resp = await client.get(feed_cfg["url"])
                    if resp.status_code != 200:
                        continue
                    feed_text = resp.text
                    parsed = await asyncio.to_thread(feedparser.parse, feed_text)
                    for entry in parsed.entries[:25]:
                        aid = article_id(entry)
                        if not _track_seen_article(aid):
                            continue
                        if not is_relevant(entry):
                            # Keep non-relevant article ids out of dedupe registry.
                            seen_articles.discard(aid)
                            try:
                                _seen_articles_order.remove(aid)
                            except ValueError:
                                pass
                            continue

                        title = getattr(entry, "title", "No title")
                        summary = getattr(entry, "summary", getattr(entry, "description", ""))
                        summary = re.sub(r"<[^>]+>", "", summary)[:300]

                        geo = await geolocate_event(title, summary, aid, allow_ai=False, use_geocoder=False)
                        _trust = SOURCE_RELIABILITY.get(feed_cfg["source"], 65)
                        _confidence = "HIGH" if _trust >= 75 else "MEDIUM" if _trust >= 60 else "LOW"
                        event = {
                            "id": f"rss_{aid[:10]}",
                            "type": geo["type"],
                            "desc": f"[{feed_cfg['source']}] {title}",
                            "lat": geo["lat"],
                            "lng": geo["lng"],
                            "source": feed_cfg["source"],
                            "url": getattr(entry, "link", None) or getattr(entry, "id", None) or "",
                            "timestamp": utc_now_iso(),
                            "insufficient_evidence": geo["insufficient_evidence"],
                            "observed_facts": geo["observed_facts"],
                            "model_inference": geo["model_inference"],
                            "confidence_score": _trust,
                            "confidence": _confidence,
                            "confidence_reason": f"{feed_cfg['source']} — source trust {_trust}/100",
                        }
                        await ingest_event(event)
                        await asyncio.sleep(0.2)
                    metrics["last_success"]["rss"] = utc_now_iso()
                except Exception as e:
                    metrics["rss_errors"] += 1
                    logger.warning(f"[RSS] Error: {e}")
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
                        _track_seen_telegram(pid)

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
                            remote_video_src = str(p.get("video_src") or "").strip()
                            local_video = None
                            # Try direct CDN download first (yt-dlp telegram extractor is unreliable)
                            if remote_video_src:
                                local_video = await asyncio.to_thread(download_video_direct, remote_video_src, pid)
                            # Fall back to yt-dlp if direct download failed
                            if not local_video:
                                local_video = await asyncio.to_thread(download_telegram_video, p["url"], pid)
                            if local_video:
                                event["video_url"] = local_video
                            elif is_playable_video_url(remote_video_src):
                                event["video_url"] = remote_video_src
                            event["has_video"] = True

                        video_meta = infer_video_metadata(event.get("desc", ""), bool(event.get("has_video")), geo.get("geo_method", "fallback"))
                        event.update(video_meta)

                        await ingest_event(event)

                    if len(seen_telegram_posts) > 6000:
                        seen_telegram_posts.clear()
                    metrics["last_success"]["telegram"] = utc_now_iso()
                except Exception as e:
                    metrics["telegram_errors"] += 1
                    logger.warning(f"[TELEGRAM] Error {cfg['slug']}: {e}")
            await asyncio.sleep(max(1, TELEGRAM_POLL_INTERVAL_SEC))


RED_ALERT_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
_red_alert_403_last_logged: float = 0.0


async def poll_sitrep(interval_sec: int = 3600):
    """Layer 3+4: generate SITREP every hour, score past predictions."""
    await asyncio.sleep(120)  # wait for pollers to fill data first
    while True:
        try:
            recent = v2_store.fetch_recent_v2_events_pg(
                database_url=DATABASE_URL,
                psycopg_mod=psycopg,
                now_iso=utc_now_iso,
                limit=300,
            )
            if not recent:
                recent = list(reversed(events_history[-300:]))

            # Score pending predictions before generating new ones
            scored = score_sitrep_predictions(recent)
            if scored:
                logger.info("[SITREP] Scored %d pending predictions", scored)

            result = await asyncio.to_thread(
                _reasoning_engine.generate_sitrep,
                _graph_store, groq_client, recent,
            )

            if result.get("sitrep"):
                sitrep_id = f"sitrep_{utc_now_iso()}"
                persist_ai_report("sitrep", result, event_fp="")
                watch_items = result.get("watch_items") or []
                if watch_items:
                    store_sitrep_watch_items(sitrep_id, watch_items)
                logger.info(
                    "[SITREP] Generated: quality=%s cluster=%d contradictions=%d watches=%d",
                    result.get("data_quality"), result.get("dominant_cluster_size", 0),
                    len(result.get("contradictions") or []), len(watch_items),
                )
        except Exception as exc:
            logger.error("[SITREP] poll_sitrep failed: %s", exc)
        await asyncio.sleep(interval_sec)


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
                if resp.status_code != 200:
                    metrics["red_alert_errors"] += 1
                    if resp.status_code == 403:
                        global _red_alert_403_last_logged
                        _now = asyncio.get_event_loop().time()
                        if _now - _red_alert_403_last_logged > 600:
                            logger.warning("[RED ALERT] 403 Forbidden — OREF geo-blocking this IP (logged once per 10m)")
                            _red_alert_403_last_logged = _now
                    continue
                if not resp.text.strip():
                    continue
                try:
                    data = resp.json()
                except Exception:
                    continue
                if not data:
                    continue

                alert_id = data.get("id", "")
                if not _track_seen_alert(alert_id):
                    continue

                alert_title = data.get("title", "Red Alert")
                cities = data.get("data", [])
                ts_now = utc_now_iso()

                for city in cities:
                    lat, lng = geolocate_alert(city)
                    eid = hashlib.sha256(f"{alert_id}_{city}".encode()).hexdigest()[:10]
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
                logger.warning(f"[RED ALERT] Error: {e}")


def _watchdog_check() -> list:
    warnings = []
    now = datetime.now(timezone.utc)
    feeds = ["rss", "telegram", "flights", "red_alert"]
    if ENABLE_ADSBLOL:
        feeds.append("adsblol")
    if ENABLE_AISSTREAM:
        feeds.append("ais")
    if ENABLE_FIRMS and FIRMS_MAP_KEY and FIRMS_BBOX:
        feeds.append("firms")
    for feed in feeds:
        ts = metrics["last_success"].get(feed)
        if not ts:
            warnings.append(f"{feed}: no successful poll yet")
            continue
        age = (now - _parse_iso(ts)).total_seconds()
        threshold = 240 if feed in {"rss", "telegram"} else 90
        if feed == "firms":
            threshold = max(300, FIRMS_POLL_INTERVAL_SEC * 3)
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
        "# HELP osint_adsblol_polls_total Total ADSB.lol polling cycles",
        "# TYPE osint_adsblol_polls_total counter",
        f"osint_adsblol_polls_total {metrics.get('adsblol_polls', 0)}",
        "# HELP osint_ais_polls_total Total AIS stream message cycles",
        "# TYPE osint_ais_polls_total counter",
        f"osint_ais_polls_total {metrics.get('ais_polls', 0)}",
        "# HELP osint_firms_polls_total Total FIRMS polling cycles",
        "# TYPE osint_firms_polls_total counter",
        f"osint_firms_polls_total {metrics.get('firms_polls', 0)}",
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
        "# HELP osint_adsblol_errors_total Total ADSB.lol polling errors",
        "# TYPE osint_adsblol_errors_total counter",
        f"osint_adsblol_errors_total {metrics.get('adsblol_errors', 0)}",
        "# HELP osint_ais_errors_total Total AIS polling errors",
        "# TYPE osint_ais_errors_total counter",
        f"osint_ais_errors_total {metrics.get('ais_errors', 0)}",
        "# HELP osint_firms_errors_total Total FIRMS polling errors",
        "# TYPE osint_firms_errors_total counter",
        f"osint_firms_errors_total {metrics.get('firms_errors', 0)}",
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


def _event_confidence_value(event: Dict[str, Any]) -> int:
    return iutils.event_confidence_value(event, SOURCE_RELIABILITY)


def _event_theater_bucket(event: Dict[str, Any]) -> str:
    return iutils.event_theater_bucket(event)


def calculate_defcon() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if DEFCON_MANUAL_OVERRIDE in {1, 2, 3, 4, 5}:
        return {
            "level": DEFCON_MANUAL_OVERRIDE,
            "reason": f"Manual DEFCON override active ({DEFCON_MANUAL_OVERRIDE})",
            "event_count": 0,
            "confidence_avg": 0,
            "capped_from_1": False,
        }

    recent = [e for e in events_history[-1800:] if _parse_iso(str(e.get("timestamp", utc_now_iso()))) >= now - timedelta(minutes=60)]
    prev = [
        e
        for e in events_history[-2400:]
        if now - timedelta(minutes=120) <= _parse_iso(str(e.get("timestamp", utc_now_iso()))) < now - timedelta(minutes=60)
    ]
    recent_count = len(recent)
    prev_count = len(prev)
    strikes = [e for e in recent if str(e.get("type", "")).upper() in {"STRIKE", "CRITICAL"}]
    strikes_high = [e for e in strikes if _event_confidence_value(e) >= 65]
    critical_high = [e for e in recent if str(e.get("type", "")).upper() == "CRITICAL" and _event_confidence_value(e) >= 75]
    avg_conf = int(sum(_event_confidence_value(e) for e in strikes_high) / max(1, len(strikes_high)))

    incident_sources: Dict[str, set] = defaultdict(set)
    strike_clusters: Dict[str, int] = defaultdict(int)
    theaters: set = set()
    for e in strikes:
        inc_id = str(e.get("incident_id", "")).strip()
        if inc_id:
            incident_sources[inc_id].add(_extract_source(e))
        key = f"{round(float(e.get('lat', 0.0)), 1)}:{round(float(e.get('lng', 0.0)), 1)}"
        strike_clusters[key] += 1
        theaters.add(_event_theater_bucket(e))

    corroborated_2 = sum(1 for s in incident_sources.values() if len(s) >= 2)
    corroborated_3 = sum(1 for s in incident_sources.values() if len(s) >= 3)
    active_clusters = sum(1 for c in strike_clusters.values() if c >= 2)

    level = 5
    reason = "Low event tempo and no significant corroborated strikes"
    capped_from_1 = False

    elevated = len(strikes_high) >= 4 or (recent_count >= 10 and recent_count >= int(prev_count * 1.6))
    high_tempo = corroborated_2 >= 2 or len(critical_high) >= 1 or len(theaters) >= 3 or len(strikes_high) >= 8
    severe = corroborated_3 >= 1 and len(critical_high) >= 1 and active_clusters >= 2 and recent_count >= 18

    if elevated:
        level = 4
        reason = f"Elevated strike tempo: {len(strikes_high)} high-confidence strikes in last 60 minutes"
    if high_tempo:
        level = 3
        reason = (
            f"High tempo: {corroborated_2} corroborated incidents, "
            f"{len(critical_high)} critical events, {len(theaters)} active theaters"
        )
    if severe:
        level = 2
        reason = (
            f"Severe tempo: {corroborated_3} incidents with 3+ sources, "
            f"{active_clusters} strike clusters, event rate {recent_count}/h"
        )

    if level <= 1:
        level = 2
        capped_from_1 = True
        reason = f"{reason}; DEFCON 1 requires manual override"

    return {
        "level": level,
        "reason": reason,
        "event_count": recent_count,
        "confidence_avg": avg_conf,
        "capped_from_1": capped_from_1,
    }


async def refresh_defcon_state() -> None:
    global _defcon_state
    snapshot = calculate_defcon()
    previous = int(_defcon_state.get("level", 5))
    current = int(snapshot["level"])
    updated_at = utc_now_iso()
    _defcon_state = {
        **snapshot,
        "updated_at": updated_at,
    }
    if previous != current:
        await manager.broadcast(
            {
                "type": "defcon_change",
                "data": {
                    "previous": previous,
                    "current": current,
                    "reason": snapshot["reason"],
                    "timestamp": updated_at,
                    "event_count": snapshot["event_count"],
                    "confidence_avg": snapshot["confidence_avg"],
                },
            }
        )


async def runtime_housekeeping():
    while True:
        try:
            _prune_runtime_state()
            cleanup_revoked_tokens()
            await refresh_defcon_state()
        except Exception as e:
            logger.warning(f"[HOUSEKEEPING] Error: {e}")
        await asyncio.sleep(60)


def _check_rate_limit(ip: str, limit: int, window_sec: int) -> bool:
    """Returns True if request is allowed, False if rate limited."""
    try:
        import redis as redis_lib
        from config import REDIS_URL
        r = redis_lib.from_url(REDIS_URL, socket_timeout=0.5)
        key = f"rl:{ip}:{window_sec}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, window_sec)
        return count <= limit
    except Exception:
        # Redis unavailable: fall back to allowing the request
        return True


def _track_failed_login(ip: str) -> int:
    try:
        import redis as redis_lib
        from config import REDIS_URL
        r = redis_lib.from_url(REDIS_URL, socket_timeout=0.5)
        key = f"fl:{ip}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 900)  # 15 min window
        return count
    except Exception:
        return 0


def _clear_failed_login(ip: str):
    try:
        import redis as redis_lib
        from config import REDIS_URL
        r = redis_lib.from_url(REDIS_URL, socket_timeout=0.5)
        r.delete(f"fl:{ip}")
    except Exception:
        pass


async def prune_old_data():
    """Daily pruning: delete events older than 90 days from events_v2."""
    while True:
        await asyncio.sleep(24 * 3600)  # run once per day
        try:
            from config import DATABASE_URL
            import psycopg
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
            with psycopg.connect(DATABASE_URL, connect_timeout=5) as conn:
                result = conn.execute(
                    "DELETE FROM events_v2 WHERE timestamp < %s", (cutoff,)
                )
                conn.commit()
                deleted = result.rowcount
            logger.info(f"[PRUNE] Deleted {deleted} events older than 90 days")

            # Prune old media files older than 90 days
            from config import TELEGRAM_MEDIA_DIR
            import time as _time
            cutoff_ts = _time.time() - (90 * 24 * 3600)
            pruned_files = 0
            for f in TELEGRAM_MEDIA_DIR.glob("**/*"):
                if f.is_file() and f.stat().st_mtime < cutoff_ts:
                    f.unlink()
                    pruned_files += 1
            if pruned_files:
                logger.info(f"[PRUNE] Deleted {pruned_files} old media files")
        except Exception as e:
            logger.warning(f"[PRUNE] Error during pruning: {e}")


_bg_tasks: list = []

# ── APIRouter registrations ────────────────────────────────────────────────────
from routes_auth import router as auth_router
app.include_router(auth_router)
from routes_admin import router as admin_router
app.include_router(admin_router)
from routes_ops import router as ops_router
app.include_router(ops_router)
from routes_v2 import router as v2_router
app.include_router(v2_router)

@app.on_event("startup")
async def startup_event():
    global _start_time, _db, _ollama_http_client, _geocode_http_client, _graph_store
    _start_time = time.time()
    validate_security_config()
    _db = db_postgres.get_pg_conn()
    db_postgres.init_pg_schema(_db)
    _ollama_http_client = httpx.AsyncClient(timeout=60)
    _geocode_http_client = httpx.AsyncClient(
        timeout=8,
        headers={"User-Agent": "OSINT-Nexus/1.0 (research dashboard)"},
    )
    import state as _state_mod
    _state_mod._db = _db
    _state_mod._ollama_http_client = _ollama_http_client
    _state_mod._geocode_http_client = _geocode_http_client
    _state_mod._v2_ai_scheduler = _v2_ai_scheduler
    cleanup_revoked_tokens()
    await sync_ollama_runtime_models()
    _graph_store = gstore.GraphStore(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
    graph_status = _graph_store.status()
    if graph_status.get("connected"):
        logger.info(f"[GRAPH] Neo4j connected ({graph_status.get('uri')})")
    else:
        logger.warning(f"[GRAPH] Neo4j disabled/offline: {graph_status.get('error')}")
    ensure_default_admin()
    load_recent_events()
    await refresh_defcon_state()

    for _rtype, _state in (("analyst", _analyst_state), ("v2", _v2_report_state)):
        _saved = load_latest_ai_report(_rtype)
        if _saved and _saved.get("report"):
            _state["report"] = _saved["report"]
            _state["last_event_fp"] = _saved.get("event_fp", "")
            _state["last_generated_ts"] = float(_saved.get("generated_at_ts", 0.0))
            logger.info(f"[REPORTS] Restored {_rtype} report from Postgres")

    _bg_tasks.append(asyncio.create_task(poll_flights()))
    _bg_tasks.append(asyncio.create_task(poll_rss()))
    _bg_tasks.append(asyncio.create_task(poll_telegram()))
    _bg_tasks.append(asyncio.create_task(poll_red_alert()))
    _bg_tasks.append(asyncio.create_task(poll_sitrep()))
    import market_poller as _market_poller
    _bg_tasks.append(asyncio.create_task(
        _market_poller.poll_markets(
            ingest_fn=ingest_event,
            now_iso_fn=utc_now_iso,
        )
    ))
    import telegram_digest as _tg_digest
    _bg_tasks.append(asyncio.create_task(
        _tg_digest.poll_daily_digest(
            token=TG_DIGEST_TOKEN,
            chat_id=TG_DIGEST_CHAT_ID,
            load_latest_fn=load_latest_ai_report,
            send_hour_utc=TG_DIGEST_HOUR_UTC,
        )
    ))
    _bg_tasks.append(asyncio.create_task(
        osint_layers.poll_adsblol(
            enabled=ENABLE_ADSBLOL,
            api_url=ADSBLOL_API_URL,
            interval_sec=ADSBLOL_POLL_INTERVAL_SEC,
            metrics=metrics,
            last_aircraft=last_aircraft,
            military_prefixes=MILITARY_PREFIXES,
            now_iso=utc_now_iso,
            broadcast=manager.broadcast,
        )
    ))
    _bg_tasks.append(asyncio.create_task(
        osint_layers.poll_aisstream(
            enabled=ENABLE_AISSTREAM,
            ws_url=AISSTREAM_WS_URL,
            api_key=AISSTREAM_API_KEY,
            bbox=AISSTREAM_BBOX,
            metrics=metrics,
            now_iso=utc_now_iso,
            broadcast=manager.broadcast,
        )
    ))
    _bg_tasks.append(asyncio.create_task(
        osint_layers.poll_firms(
            enabled=ENABLE_FIRMS,
            map_key=FIRMS_MAP_KEY,
            source=FIRMS_SOURCE,
            bbox=FIRMS_BBOX,
            days=FIRMS_DAYS,
            interval_sec=FIRMS_POLL_INTERVAL_SEC,
            metrics=metrics,
            now_iso=utc_now_iso,
            ingest_event=ingest_event,
        )
    ))
    _bg_tasks.append(asyncio.create_task(media_worker()))
    _bg_tasks.append(asyncio.create_task(runtime_housekeeping()))
    _bg_tasks.append(asyncio.create_task(prune_old_data()))
    logger.info("[OSINT] Engine started — pollers + DB persistence active")


@app.on_event("shutdown")
async def shutdown_event():
    global _ollama_http_client, _geocode_http_client, _graph_store
    # Cancel all background tasks
    for task in _bg_tasks:
        task.cancel()
    if _bg_tasks:
        await asyncio.gather(*_bg_tasks, return_exceptions=True)
    logger.info("Background tasks cancelled cleanly")
    if _ollama_http_client is not None:
        await _ollama_http_client.aclose()
        _ollama_http_client = None
    if _geocode_http_client is not None:
        await _geocode_http_client.aclose()
        _geocode_http_client = None
    if _graph_store is not None:
        _graph_store.close()
        _graph_store = None


@app.get("/")
async def root():
    return {"status": "OSINT Engine v3 Running", "clients": len(manager.connections), "events": len(events_history)}


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


def build_event_graph(items: List[dict]) -> dict:
    nodes: Dict[str, dict] = {}
    edges: Dict[str, dict] = {}

    def _node(node_id: str, label: str, kind: str) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "label": label, "kind": kind}

    for e in items:
        event_id = str(e.get("id") or "")
        if not event_id:
            continue
        incident_id = str(e.get("incident_id") or "")
        source = _extract_source(e)
        etype = str(e.get("type") or "UNKNOWN")
        _node(f"event:{event_id}", event_id, "event")
        _node(f"type:{etype}", etype, "type")
        _node(f"source:{source}", source, "source")
        if incident_id:
            _node(f"incident:{incident_id}", incident_id, "incident")

        links = [
            (f"event:{event_id}", f"type:{etype}", "classified_as"),
            (f"event:{event_id}", f"source:{source}", "reported_by"),
        ]
        if incident_id:
            links.append((f"event:{event_id}", f"incident:{incident_id}", "part_of"))

        for src, dst, rel in links:
            key = f"{src}|{rel}|{dst}"
            if key not in edges:
                edges[key] = {"source": src, "target": dst, "relation": rel, "weight": 1}
            else:
                edges[key]["weight"] += 1

    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


# ---------------------------------------------------------------------------
# Intel Trace endpoint — Neo4j subgraph + Groq causal analysis
# ---------------------------------------------------------------------------

@app.get("/api/v2/intel/trace/{event_id}")
async def intel_trace(event_id: str, request: Request):
    """
    Return a full temporal intelligence trace for a given event.
    Pulls Neo4j subgraph (actors, weapons, locations, predecessors, sources),
    computes anomaly score, then asks Groq to narrate — only from graph data.
    Requires analyst or admin role.
    """
    user = auth_user_from_request(request)
    if user.get("role") not in ("analyst", "admin"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Analyst or admin required")

    eid = (event_id or "").strip()
    if not eid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="event_id required")

    import temporal_kg
    result = await asyncio.to_thread(
        temporal_kg.build_intelligence_trace,
        _graph_store,
        groq_client,
        eid,
    )

    # If Neo4j has no record, fall back to local history for basic info
    if not result.get("subgraph", {}).get("event"):
        ev = next((e for e in events_history if str(e.get("id") or "") == eid), None)
        if ev:
            result["subgraph"] = {
                "event": ev,
                "related_events": [],
                "sources": [{"name": ev.get("source", "Unknown")}],
                "actors": [],
                "weapons": [],
                "locations": [],
            }
            result["data_quality"] = "local_fallback"
        else:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Event not found")

    return result


_landing_dir = Path(__file__).parent / "landing"
if _landing_dir.exists():
    app.mount("/", StaticFiles(directory=str(_landing_dir), html=True), name="landing")
