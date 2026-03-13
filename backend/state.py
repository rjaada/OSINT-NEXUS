"""
state.py — Shared mutable globals for OSINT Nexus.

Import from here to access shared runtime state without circular imports.
Dependency chain: config → state → (ingest, ai, deps) → routes_* → main
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections import deque
from typing import Any, Dict, List, Optional, Set

import httpx

from config import (
    MEDIA_JOB_STATE_TTL_SEC,
    MEDIA_JOB_STATE_MAX,
    FAILED_LOGIN_MAX_TRACKED,
)
from ws_manager import ConnectionManager

# ── WebSocket manager ──────────────────────────────────────────────────────────
manager: ConnectionManager = ConnectionManager()

# ── Database ───────────────────────────────────────────────────────────────────
_db: Optional[sqlite3.Connection] = None
_graph_store: Any = None  # gstore.GraphStore set at startup

# ── Event runtime buffers ──────────────────────────────────────────────────────
events_buffer: list = []
events_history: list = []
last_aircraft: list = []
incident_index: Dict[str, dict] = {}
incident_lock = asyncio.Lock()

# ── Deduplication ──────────────────────────────────────────────────────────────
seen_articles: Set[str] = set()
_seen_articles_order: deque = deque(maxlen=30_000)
seen_telegram_posts: Set[str] = set()
_seen_telegram_order: deque = deque(maxlen=10_000)
seen_alerts: Set[str] = set()
_seen_alerts_order: deque = deque(maxlen=20_000)

# ── Ops metrics ────────────────────────────────────────────────────────────────
metrics: Dict[str, Any] = {
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

# ── Auth / rate-limit ──────────────────────────────────────────────────────────
_rate_limit: Dict[str, List[float]] = {}
_failed_logins: Dict[str, Dict[str, Any]] = {}
_passkey_reg_challenges: Dict[str, Dict[str, Any]] = {}
_passkey_auth_challenges: Dict[str, Dict[str, Any]] = {}
_review_cache: Dict[str, dict] = {}

# ── Media job tracking ─────────────────────────────────────────────────────────
_media_jobs: "asyncio.Queue[dict]" = asyncio.Queue()
_media_job_state: Dict[str, dict] = {}

# ── AI report / DEFCON state ───────────────────────────────────────────────────
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
_defcon_state: Dict[str, Any] = {
    "level": 5,
    "reason": "Baseline monitoring state",
    "updated_at": None,
    "event_count": 0,
    "confidence_avg": 0,
    "capped_from_1": False,
}

# ── Ollama runtime ─────────────────────────────────────────────────────────────
_ollama_available_models: Set[str] = set()
_ollama_http_client: Optional[httpx.AsyncClient] = None
_geocode_http_client: Optional[httpx.AsyncClient] = None

# ── Geocode cache ──────────────────────────────────────────────────────────────
geocode_cache: Dict[str, tuple] = {}

# ── Red Alert throttle ─────────────────────────────────────────────────────────
_red_alert_403_last_logged: float = 0.0

# ── V2 AI scheduler placeholder (set by main.py after class definition) ────────
_v2_ai_scheduler: Any = None

# ── Process start time ─────────────────────────────────────────────────────────
_start_time: float = time.time()

# ── Logging ────────────────────────────────────────────────────────────────────
graph_logger = logging.getLogger("osint.graph")

# ── Config aliases (for consumers that imported from main) ────────────────────
_MEDIA_JOB_STATE_TTL_SEC = MEDIA_JOB_STATE_TTL_SEC
_MEDIA_JOB_STATE_MAX = MEDIA_JOB_STATE_MAX
_FAILED_LOGIN_MAX_TRACKED = FAILED_LOGIN_MAX_TRACKED
