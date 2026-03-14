# Split main.py Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break the 3851-line `backend/main.py` into focused modules with no circular imports, without changing any observable behaviour.

**Architecture:** Introduce a `state.py` singleton for all shared mutable globals → move business logic to `ingest.py` and `ai.py` → extract routes into `APIRouter` files → thin `main.py` wires everything. Dependency direction: `state` ← `ingest/ai` ← `routes_*` ← `main`.

**Tech Stack:** FastAPI `APIRouter`, Python modules, pytest, Docker Compose

---

## Dependency DAG (must not be violated)

```
config.py        ← nothing
db_sqlite.py     ← config
intel_utils.py   ← config
state.py         ← config, db_sqlite (shared globals only)
ingest.py        ← state, intel_utils, config
ai.py            ← state, intel_utils, config
routes_auth.py   ← state, config (+ existing auth_* modules)
routes_admin.py  ← state
routes_v2.py     ← state, ingest, ai
routes_ops.py    ← state, ingest, ai
main.py          ← ALL of the above  (app, startup, pollers)
```

---

## File Map

| File | Status | Responsibility |
|------|--------|----------------|
| `backend/state.py` | **CREATE** | All shared mutable globals: `manager`, `metrics`, `_db`, rate-limit dicts, deques, caches, locks |
| `backend/ingest.py` | **CREATE** | Event ingestion pipeline: `ingest_event`, `persist_event`, `push_event_buffer`, `should_merge_with_existing`, `build_incident_id`, `is_relevant`, `classify_event` |
| `backend/ai.py` | **CREATE** | Ollama + geocoding: `call_ollama_json`, `geolocate_with_ai`, `geolocate_event`, `geocode_place`, `fetch_metoc`, `sync_ollama_runtime_models`, `_get_ollama_client`, `_get_geocode_client` |
| `backend/routes_auth.py` | **CREATE** | `APIRouter` for all `/api/auth/*` endpoints (lines 2315–2636) |
| `backend/routes_admin.py` | **CREATE** | `APIRouter` for all `/api/admin/*` endpoints (lines 2636–2680) |
| `backend/routes_ops.py` | **CREATE** | `APIRouter` for `/api/health`, `/api/ops/*`, `/api/stats`, `/api/events`, `/api/sources/*`, `/api/alerts/*`, `/api/analyst`, `/metrics` (lines 2680–2891) |
| `backend/routes_v2.py` | **CREATE** | `APIRouter` for all `/api/v2/*` and `/api/media/*` and WebSocket endpoints (lines 2891–3851) |
| `backend/main.py` | **SHRINK** | App creation, middleware, `include_router` calls, startup/shutdown, pollers (`poll_flights`, `poll_rss`, `poll_telegram`, `poll_red_alert`) |

---

## Safety Rules

1. **Run `pytest backend/tests/ -q` after every task** — all 17 tests must stay green.
2. **Never delete from main.py before the replacement is confirmed working.**
3. Move functions **one module at a time** in dependency order (state → ingest/ai → routes → main cleanup).
4. After each task, do a quick smoke-test: `docker compose up -d backend && sleep 5 && curl -s http://localhost:8000/api/health`.

---

## Chunk 1: Shared State Module

### Task 1: Create `backend/state.py`

**Files:**
- Create: `backend/state.py`

Extract every shared mutable global from `main.py` into `state.py`. These are variables that multiple route files will need to read/write.

- [ ] **Step 1: Create `backend/state.py`** with the following content:

```python
"""
state.py — Shared mutable globals for OSINT Nexus.
Import from here instead of from main.py to avoid circular imports.
All values are module-level singletons; main.py sets _db at startup.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Dict, List, Optional, Set

import sqlite3

from config import (
    MEDIA_JOB_STATE_TTL_SEC,
    MEDIA_JOB_STATE_MAX,
    FAILED_LOGIN_MAX_TRACKED,
)


# ── WebSocket manager (imported from main to avoid re-declaring ConnectionManager) ──
# Set by main.py at module load time after ConnectionManager is defined.
manager: Any = None  # type: ignore[assignment]


# ── Database connection ──
_db: Optional[sqlite3.Connection] = None


# ── Metrics ──
metrics: Dict[str, Any] = {
    "rss_polls": 0,
    "rss_errors": 0,
    "telegram_polls": 0,
    "telegram_errors": 0,
    "flight_polls": 0,
    "flight_errors": 0,
    "red_alert_polls": 0,
    "red_alert_errors": 0,
    "adsblol_polls": 0,
    "adsblol_errors": 0,
    "ais_polls": 0,
    "ais_errors": 0,
    "firms_polls": 0,
    "firms_errors": 0,
    "events_ingested": 0,
    "last_success": {},
}

# ── Rate limiting ──
_rate_limit: Dict[str, list] = {}
_failed_logins: Dict[str, dict] = {}

# ── Media job state ──
_media_job_state: Dict[str, dict] = {}

# ── Auth ──
_passkey_challenges: Dict[str, dict] = {}
_revoked_tokens: Set[str] = set()

# ── Deduplication deques ──
_seen_article_order: deque = deque(maxlen=2000)
_seen_alert_order: deque = deque(maxlen=500)
_seen_telegram_order: deque = deque(maxlen=3000)
_seen_article_ids: Set[str] = set()
_seen_alert_ids: Set[str] = set()
_seen_telegram_ids: Set[str] = set()

# ── Report / AI state ──
_analyst_state: Dict[str, Any] = {
    "report": "",
    "last_event_fp": "",
    "last_generated_ts": 0.0,
}
_v2_report_state: Dict[str, Any] = {
    "report": "",
    "last_event_fp": "",
    "last_generated_ts": 0.0,
}
_defcon_state: Dict[str, Any] = {}

# ── Live aircraft / vessel data ──
last_aircraft: List[dict] = []
last_vessels: List[dict] = []

# ── Ollama runtime ──
_ollama_available_models: Set[str] = set()
_ollama_http_client: Any = None
_geocode_http_client: Any = None

# ── Red Alert throttle ──
_red_alert_403_last_logged: float = 0.0

# ── Incident dedup ──
incident_lock = asyncio.Lock()

# ── Process start time ──
_start_time: float = time.time()
```

- [ ] **Step 2: Verify state.py is importable**

```bash
cd /home/rjaada/projects/me/OSINT/backend && python3 -c "import state; print('state.py OK')"
```
Expected: `state.py OK` with no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/state.py
git commit -m "feat: add state.py — shared mutable globals singleton"
```

---

## Chunk 2: Business Logic Modules

### Task 2: Create `backend/ingest.py`

**Files:**
- Create: `backend/ingest.py`
- Modify: `backend/main.py` (add thin wrappers importing from ingest.py)

Functions to move from main.py: `is_relevant` (line 1641), `build_incident_id` (1650), `should_merge_with_existing` (1660), `push_event_buffer` (1678), `ingest_event` (1688).

- [ ] **Step 1: Create `backend/ingest.py`**

Copy those 5 functions from main.py into ingest.py. Header:

```python
"""
ingest.py — Event ingestion pipeline.
Receives raw events, deduplicates, merges incidents, persists.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any, Dict, List, Optional

from config import (
    ALERT_RELEVANCE_KEYWORDS,
    ALERT_MERGE_RADIUS_KM,
    ALERT_MERGE_AGE_SEC,
)
import state
# intel_utils functions will be imported as needed inside functions
```

Then paste the 5 function bodies, replacing every reference to `metrics`, `incident_lock`, `last_aircraft`, etc. with `state.metrics`, `state.incident_lock`, etc.

- [ ] **Step 2: Add thin wrappers to main.py** (keep old names working):

```python
# Thin delegation — keep existing call sites working during migration.
from ingest import (
    is_relevant,
    build_incident_id,
    should_merge_with_existing,
    push_event_buffer,
    ingest_event,
)
```

Add these imports near the top of main.py (after existing imports). Do NOT delete the original function bodies yet.

- [ ] **Step 3: Run tests**

```bash
cd /home/rjaada/projects/me/OSINT && python3 -m pytest backend/tests/ -q
```
Expected: 17 passed.

- [ ] **Step 4: Delete original function bodies from main.py**

Remove lines 1641–1738 (the 5 original functions). The thin wrapper imports added in Step 2 now cover them.

- [ ] **Step 5: Run tests again**

```bash
python3 -m pytest backend/tests/ -q
```
Expected: 17 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/ingest.py backend/main.py
git commit -m "refactor: extract event ingestion pipeline to ingest.py"
```

---

### Task 3: Create `backend/ai.py`

**Files:**
- Create: `backend/ai.py`
- Modify: `backend/main.py`

Functions to move: `_get_ollama_client` (1075), `_get_geocode_client` (1082), `sync_ollama_runtime_models` (1092), `_haversine_km` (1130), `geocode_place` (1150), `fetch_metoc` (1170), `_decode_ollama_json_response` (1218), `call_ollama_json` (1377), `geolocate_with_ai` (1424), `geolocate_event` (1461).

- [ ] **Step 1: Create `backend/ai.py`**

```python
"""
ai.py — Ollama LLM integration and geocoding helpers.
All network calls to Ollama and geocoding APIs live here.
"""
from __future__ import annotations

import asyncio
import json
import math
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config import (
    OLLAMA_URL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_FALLBACK_MODEL,
    OLLAMA_TIMEOUT,
    PLACE_COORDS,
    ISRAEL_CITY_COORDS,
)
import state
```

Copy the 10 functions, replacing `_ollama_available_models` with `state._ollama_available_models`, `_ollama_http_client` with `state._ollama_http_client`, etc.

- [ ] **Step 2: Add thin wrapper imports to main.py**

```python
from ai import (
    _get_ollama_client,
    _get_geocode_client,
    sync_ollama_runtime_models,
    geocode_place,
    fetch_metoc,
    call_ollama_json,
    geolocate_with_ai,
    geolocate_event,
)
```

- [ ] **Step 3: Run tests**

```bash
python3 -m pytest backend/tests/ -q
```
Expected: 17 passed.

- [ ] **Step 4: Delete original function bodies from main.py** (lines ~1075–1523 covering those 10 functions).

- [ ] **Step 5: Run tests**

Expected: 17 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/ai.py backend/main.py
git commit -m "refactor: extract Ollama/geocoding to ai.py"
```

---

## Chunk 3: Route Extraction

For each route file:
1. Create the file with `router = APIRouter()`
2. Copy routes from main.py (change `@app.` → `@router.`)
3. Add `app.include_router(router)` to main.py
4. Run tests
5. Delete original routes from main.py
6. Run tests again
7. Commit

### Task 4: Create `backend/routes_auth.py`

**Files:**
- Create: `backend/routes_auth.py`
- Modify: `backend/main.py`

Lines 2315–2636 in current main.py (all `/api/auth/*` routes + `/api/auth/passkey/*`).

- [ ] **Step 1: Create `backend/routes_auth.py`**

```python
"""
routes_auth.py — Authentication endpoints.
Covers: register, login, logout, session, card, MFA TOTP, passkeys.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

import state
from config import (
    AUTH_LOGIN_LOCK_SEC,
    AUTH_LOGIN_MAX_FAILURES,
    AUTH_ADMIN_REQUIRE_PASSKEY,
    AUTH_BREAK_GLASS_CODE,
    AUTH_COOKIE_SECURE,
    AUTH_COOKIE_MAX_AGE,
)

router = APIRouter()
```

Then copy all `/api/auth/*` route functions (change `@app.post` → `@router.post`, `@app.get` → `@router.get`).

All helper functions these routes call (`auth_user_from_request`, `require_admin`, `enforce_csrf`, `enforce_rate_limit`, `hash_password`, `verify_password`, `_set_auth_cookies`, `mfa_verify_user_code`, etc.) remain in main.py for now — import them at the top of routes_auth.py:

```python
# Business logic still in main during migration — will be moved in a follow-up.
from main import (
    auth_user_from_request,
    enforce_csrf,
    enforce_rate_limit,
    _client_ip,
    hash_password,
    verify_password,
    _set_auth_cookies,
    get_user,
    audit_log,
    mfa_verify_user_code,
    mfa_enabled_for_user,
    mfa_required_for_role,
    passkey_count_for_user,
    admin_password_block_reason,
    _prune_failed_logins,
    check_password_policy,
    build_auth_card_payload,
    auth_sign,
    auth_verify,
    is_token_revoked,
    auth_token_signature,
    cleanup_revoked_tokens,
)
```

**Note:** Importing from main.py in route files is allowed during migration — these functions will be moved to `deps.py` in a follow-up task. The key constraint is main.py must NOT import from routes_*.py.

- [ ] **Step 2: Register router in main.py**

After the app is created (around line 145), add:
```python
from routes_auth import router as auth_router
app.include_router(auth_router)
```

Keep original route definitions in main.py for now (don't delete yet).

- [ ] **Step 3: Verify no duplicate route errors**

Start app and check: `python3 -c "import main"` — should not raise `ValueError: Duplicate operation`.
If duplicates: comment out the original routes in main.py temporarily.

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest backend/tests/ -q
```
Expected: 17 passed.

- [ ] **Step 5: Delete original `/api/auth/*` routes from main.py**

Remove lines 2315–2636 from main.py.

- [ ] **Step 6: Run tests**

Expected: 17 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/routes_auth.py backend/main.py
git commit -m "refactor: extract /api/auth/* routes to routes_auth.py"
```

---

### Task 5: Create `backend/routes_admin.py`

**Files:**
- Create: `backend/routes_admin.py`
- Modify: `backend/main.py`

Lines covering `/api/admin/users` (GET), `/api/admin/users/{username}/role` (PATCH), `/api/admin/users/{username}` (DELETE).

- [ ] **Step 1: Create `backend/routes_admin.py`**

```python
"""
routes_admin.py — Admin user management endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

import state
from main import (
    require_admin,
    enforce_csrf,
    get_user,
    audit_log,
    check_password_policy,
    hash_password,
)

router = APIRouter()
```

Copy the 3 admin routes (change `@app.` → `@router.`).

- [ ] **Step 2: Register in main.py**

```python
from routes_admin import router as admin_router
app.include_router(admin_router)
```

- [ ] **Step 3: Run tests → delete originals → run tests → commit**

```bash
python3 -m pytest backend/tests/ -q  # before
# delete original admin routes from main.py
python3 -m pytest backend/tests/ -q  # after
git add backend/routes_admin.py backend/main.py
git commit -m "refactor: extract /api/admin/* routes to routes_admin.py"
```

---

### Task 6: Create `backend/routes_ops.py`

**Files:**
- Create: `backend/routes_ops.py`
- Modify: `backend/main.py`

Routes: `/api/health`, `/api/ops/health`, `/api/stats`, `/api/events`, `/api/sources/recent`, `/api/alerts/assessment`, `/api/analyst`, `/metrics`.

- [ ] **Step 1: Create `backend/routes_ops.py`**

```python
"""
routes_ops.py — Operational health, stats, and legacy event endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

import state
from main import (
    auth_user_from_request,
    require_analyst_or_admin,
    _watchdog_check,
    build_ops_alerts,
    render_prometheus_metrics,
    source_ops_metrics,
    postgres_status,
    fetch_recent_v2_events_pg,
    cluster_events_for_map,
    assess_confidence_v2,
    _parse_iso,
    _extract_source,
    _is_telegram_source,
    utc_now_iso,
)
import ai  # for fetch_metoc

router = APIRouter()
```

Copy the 8 ops routes.

- [ ] **Step 2–5: Same pattern** — register, run tests, delete originals, run tests, commit.

```bash
git commit -m "refactor: extract ops/health/stats routes to routes_ops.py"
```

---

### Task 7: Create `backend/routes_v2.py`

**Files:**
- Create: `backend/routes_v2.py`
- Modify: `backend/main.py`

All `/api/v2/*`, `/api/media/*`, and both WebSocket endpoints (lines ~2891–3851).

- [ ] **Step 1: Create `backend/routes_v2.py`**

```python
"""
routes_v2.py — V2 AI analysis, data, ops, and WebSocket endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response

import state
from main import (
    auth_user_from_request,
    require_analyst_or_admin,
    require_admin,
    enforce_csrf,
    auth_user_from_websocket,
    resolve_write_identity,
    utc_now_iso,
    # v2 business logic functions
    fetch_recent_v2_events_pg,
    persist_ai_report,
    load_latest_ai_report,
    fetch_ai_report_history,
    cluster_events_for_map,
    assess_confidence_v2,
    calculate_defcon,
    build_ops_alerts,
    _watchdog_check,
    _parse_iso,
    _extract_source,
    _is_telegram_source,
    run_media_analysis,
    persist_media_analysis,
    get_media_analysis,
    load_overlays,
    parse_overlay_file,
    mgrs_from_latlng,
    infer_video_metadata,
    is_playable_video_url,
    download_telegram_video,
    audit_log,
    persist_event,
)
from ingest import ingest_event
import ai as ai_module

router = APIRouter()
```

Copy all v2 + WebSocket routes.

- [ ] **Step 2–5: Register, run tests, delete originals, run tests, commit.**

```bash
git commit -m "refactor: extract /api/v2/* and WebSocket routes to routes_v2.py"
```

---

## Chunk 4: Main Cleanup & Root Route

### Task 8: Slim down `backend/main.py`

After all routes are extracted, main.py should contain only:
- Imports
- Global constants (AUTH_*, config vars)
- Class definitions (`ConnectionManager`, `V2AiScheduler`, Pydantic payload models)
- Utility/helper functions that routes still import from main (these will be moved to `deps.py` in future)
- Startup/shutdown event handlers
- Pollers (`poll_flights`, `poll_rss`, `poll_telegram`, `poll_red_alert`)
- `app.include_router(...)` calls
- Static file mount

Target: **< 1500 lines** (down from 3851).

- [ ] **Step 1: Audit remaining lines**

```bash
wc -l backend/main.py
```

- [ ] **Step 2: Remove any dead code** — unused imports, commented-out blocks identified during migration.

- [ ] **Step 3: Run full test suite**

```bash
python3 -m pytest backend/tests/ -q
```
Expected: 17 passed.

- [ ] **Step 4: Rebuild Docker and smoke test**

```bash
docker compose build backend && docker compose up -d backend
sleep 8
curl -s http://localhost:8000/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('health OK' if d else 'EMPTY')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/main.py
git commit -m "refactor: slim main.py to wiring + pollers only (~1500 lines)"
```

---

### Task 9: Create `backend/deps.py` (future-proof)

Move the dependency injection helpers out of main.py so routes no longer need to `from main import ...`.

**Files:**
- Create: `backend/deps.py`
- Modify: All route files (change `from main import X` → `from deps import X`)

Functions to move to deps.py:
- `auth_user_from_request`
- `auth_user_from_websocket`
- `require_admin`
- `require_analyst_or_admin`
- `enforce_csrf`
- `enforce_rate_limit`
- `_client_ip`

- [ ] **Step 1: Create `backend/deps.py`** with those 7 functions (they only depend on `state.py` and auth modules, no circular imports).

- [ ] **Step 2: Update all route files** to `from deps import ...` instead of `from main import ...` for those 7 functions.

- [ ] **Step 3: Run tests**

Expected: 17 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/deps.py backend/routes_*.py backend/main.py
git commit -m "refactor: extract dependency injection helpers to deps.py, eliminate routes→main imports"
```

---

## Verification Checklist

After all tasks complete:

- [ ] `python3 -m pytest backend/tests/ -q` → 17 passed
- [ ] `wc -l backend/main.py` → < 1500
- [ ] `docker compose build backend && docker compose up -d backend` → no build errors
- [ ] `curl -s http://localhost:8000/api/health` → 200 OK
- [ ] `curl -s http://localhost:8000/api/auth/session` → 200 OK
- [ ] No circular import errors on `python3 -c "import main"`
- [ ] `grep -n "from main import" backend/routes_*.py` → empty (after Task 9)

## Final Module Count

| Module | Lines (est.) |
|--------|-------------|
| state.py | ~90 |
| ingest.py | ~120 |
| ai.py | ~280 |
| routes_auth.py | ~340 |
| routes_admin.py | ~60 |
| routes_ops.py | ~230 |
| routes_v2.py | ~950 |
| deps.py | ~80 |
| main.py | ~1200 |
| **Total** | **~3350** |

Existing modules unchanged: `config.py`, `db_sqlite.py`, `intel_utils.py`, `osint_layers.py`, `auth_security.py`, `auth_handlers.py`, `auth_passkey.py`, `auth_store.py`, `mfa_totp.py`, `graph_store.py`, `v2_store.py`, `analyst.py`.
