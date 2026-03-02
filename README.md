# OSINT NEXUS

OSINT NEXUS is a real-time OSINT monitoring platform for conflict-driven situational awareness. It ingests open sources, geolocates events, computes confidence, and serves versioned operational dashboards.

## What This Project Is

OSINT NEXUS is an operational intelligence workspace that combines:

- live OSINT ingestion (Telegram, RSS, flight feed, red-alert feed),
- map-centric incident monitoring,
- analyst review workflows,
- role-based access control,
- local AI-assisted verification/report generation via Ollama.

It is designed for decision support, not for authoritative command-and-control.

## Current Product State

- `v2` is now the primary workspace (`/` redirects to `/v2`).
- `v1` remains in the codebase but is hidden from the main navigation.

Current engineering focus (feature freeze):

- reliability and auth/session stability,
- role/access correctness,
- persistence behavior across restarts,
- test coverage for critical paths.

## 10-Minute Local Onboarding

```bash
make up-p2
make up-ai MODEL=deepseek-r1:8b
make pull-model MODEL=phi4-mini
make health
```

Open:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Login: `http://localhost:3000/login`

Run critical auth/admin tests:

```bash
make test-auth
```

UI entry points:

- Root (V2): `http://localhost:3000/`
- V2 hub: `http://localhost:3000/v2`
- V2 operations: `http://localhost:3000/v2/operations`
- V2 alerts: `http://localhost:3000/v2/alerts`
- V2 sources: `http://localhost:3000/v2/sources`
- V2 health: `http://localhost:3000/v2/health`
- V2 admin (admin only): `http://localhost:3000/v2/admin`

Arabic routes mirror v2 under `/v2/ar/...`.

## Ingestion and Data Sources

- Telegram channels:
  - `AJ Mubasher (TG)`
  - `Roaa War Studies (TG)`
- RSS feeds (Reuters, Al Jazeera, BBC, CBS, The Guardian, Times of Israel)
- FlightRadar24 military-relevant flight feed
- Red Alert feed (when reachable)

## Backend Capabilities

- FastAPI ingestion engine with WebSocket broadcast
- SQLite local persistence (default) and Postgres v2 events persistence support
- Incident deduplication and event threading
- Confidence scoring with explainable rationale and corroboration tracking
- Media job queue and Telegram media linkage
- Watchdog + ops metrics + rule alerts
- MGRS conversion for v2 events/alerts
- Real METOC pull via Open-Meteo endpoint
- Geo overlay loading from local GeoJSON files (`OVERLAY_DIR`)

## Key Features

- V2 operations map with event hover/click detail cards
- V2 alerts board with confidence/ETA and analyst review actions
- V2 source desk for reliability/throughput and pipeline status
- V2 health dashboard for watchdog/queues/system status
- Admin role-management page (list users, promote/demote, delete with safeguards)
- Real-time updates via WebSocket stream
- MGRS conversion and METOC weather integration
- GeoJSON tactical overlays support
- AI-assisted verification + report workflows (Ollama)

## AI in V2 (current policy)

V2 currently uses task models through Ollama:

- `verify` model: default `phi4-mini`
- `report` model: default `deepseek-r1:8b`

Runtime scheduler behavior:

- single active model at a time
- serialized execution
- forced model switching when task changes
- runtime model discovery from Ollama `/api/tags`
- unavailable models are dropped from runtime chain to reduce repeated 404 noise

## Authentication and Access Control

- Account creation and login are available on `/login`
- Passwords are stored with salted PBKDF2 hash
- Signed auth cookie (`osint_auth`) is used for session verification
- Role model:
  - `viewer`
  - `analyst`
  - `admin`

Route policy:

- v1: any authenticated role
- v2: any authenticated role (`viewer`, `analyst`, `admin`)
- v2 admin pages: `admin` only

Admin tooling:

- `GET /api/admin/users` (admin only)
- `PATCH /api/admin/users/{username}/role` (admin only)
- `DELETE /api/admin/users/{username}` (admin only)
- Last-admin safety: cannot demote the final admin account
- Last-admin/self-delete safety: cannot delete final admin or current admin account

## V2 Page Summary

Operations (`/v2/operations`):

- Live map + markers
- Hover and click event details on map
- METOC widget + weather overlay toggle
- BFT/ISR widgets
- AI crisis analyst panel
- **No chat panel**
- **No alert-card feed in operations sidebar**

Alerts (`/v2/alerts`):

- Confidence and ETA board
- Analyst/admin review actions
- SITREP/INTSUM export
- Multi-model ops brief integration (`verify` + `report`)

Sources (`/v2/sources`):

- Source reliability and throughput metrics
- Queue and model status
- AI report panel

Health (`/v2/health`):

- Ops health, watchdog warnings, queue state, and postgres status

Admin (`/v2/admin`):

- List users
- Promote/demote roles
- Delete users with safety checks

## Main API Endpoints

Core:

- `GET /api/health`
- `GET /api/ops/health`
- `GET /api/stats`
- `GET /api/events`
- `GET /api/alerts/assessment`
- `GET /api/sources/recent`
- `GET /api/analyst`
- `WS /ws/live`

V2:

- `GET /api/v2/events`
- `GET /api/v2/alerts`
- `GET /api/v2/sources`
- `GET /api/v2/system`
- `GET /api/v2/ops/alerts`
- `GET /api/v2/metoc`
- `GET /api/v2/overlays`
- `GET /api/v2/ai/policy`
- `GET /api/v2/ai/report`
- `POST /api/v2/ai/verify`
- `POST /api/v2/ai/ops-brief`

Auth/Admin:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/session`
- `GET /api/admin/users`
- `PATCH /api/admin/users/{username}/role`
- `DELETE /api/admin/users/{username}`

## Prerequisites

- Docker Engine
- Docker Compose
- Node.js 20+ (optional direct frontend run)
- Python 3.11+ (optional direct backend run)
- Minikube + kubectl (for Kubernetes mode)
- Optional NVIDIA GPU + NVIDIA container toolkit (for local Ollama acceleration)

## Environment Variables (Backend)

Important variables:

- `OSINT_DB_PATH` (default: `/tmp/osint_nexus.db`; compose uses `/data/osint_nexus.db` for persistence)
- `MEDIA_DIR` (default: `/tmp/osint_nexus_media`)
- `OVERLAY_DIR` (default: `/tmp/osint_overlays`)
- `DATABASE_URL` (Postgres enablement)
- `OLLAMA_URL` (default: `http://ollama:11434/api/generate`)
- `OLLAMA_MODEL`
- `OLLAMA_FALLBACK_MODEL`
- `V2_MODEL_VERIFY`
- `V2_MODEL_REPORT`
- `V2_MODEL_DEFAULT`
- `AUTH_SECRET`
- `AUTH_DEFAULT_ADMIN_USER`
- `AUTH_DEFAULT_ADMIN_PASSWORD`
- `AUTH_COOKIE_SECURE` (`1/true` in HTTPS deployments)
- `CORS_ORIGINS` (comma-separated)

Telegram/media tuning:

- `DOWNLOAD_TELEGRAM_MEDIA`
- `TELEGRAM_LOOKBACK_POSTS`
- `TELEGRAM_MAX_NEW_PER_POLL`

## Local Run (Docker Compose)

Build and start:

```bash
make up-p2
make up-ai MODEL=deepseek-r1:8b
make pull-model MODEL=phi4-mini
make pull-model MODEL=qwen2.5:7b
```

Or direct compose:

```bash
docker compose up -d --build postgres redis backend frontend ollama
```

Access:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

Persistence note:

- Docker Compose mounts backend auth/local DB storage at `/data` (`backend_data` volume).
- This keeps user accounts and local SQLite state across container restarts.

Useful commands:

```bash
make ps
make logs
make logs-backend
make health
make test-auth
make down
```

## Kubernetes

See [README_K8s.md](README_K8s.md) for Minikube deployment details.

## Security and Usage Notes

- This is an OSINT decision-support platform, not an authoritative command system.
- Model output is advisory and can be wrong.
- Validate critical claims through trusted official channels.
- Do not commit secrets or private credentials.

## Repository Layout

```text
.
├── backend/
├── frontend/
├── k8s/
├── docker-compose.yml
├── Makefile
├── README.md
└── README_K8s.md
```
