# OSINT Nexus — Full Project Documentation

> Written in my own voice, for future me (or anyone else who touches this).
> Last updated: 2026-03-14

---

## What Is This?

OSINT Nexus is a real-time intelligence aggregation and analysis platform I built from scratch. The short version: it watches multiple data sources simultaneously (military aircraft, ships, fires, news, Telegram channels, rocket sirens), fuses everything into a unified event stream, runs AI analysis on it, and presents it through a dashboard that looks like something out of a SCIF.

The longer version: it's essentially a lightweight open-source version of what Palantir Gotham does — multi-source intelligence fusion, geospatial tracking, AI-assisted analysis, graph-based entity relationships, and structured intelligence reports — all running on a single server for free.

The primary focus is the Middle East conflict zone (Israel/Gaza/Lebanon/Syria theater), though the bounding boxes and data sources are configurable for any region.

---

## Tech Stack

### Backend
- **Python 3.11** with **FastAPI** (async, WebSocket support built-in)
- **PostgreSQL 16 with PostGIS** — main database for all events, users, reports
- **Neo4j 5** — graph database for entity relationships (who did what, where, to whom)
- **Redis** — rate limiting, session state, pub/sub
- **Ollama** — local AI inference (phi4-mini for fast tasks, llama3.1:8b for reports)
- **psycopg3** — async-compatible PostgreSQL driver

### Frontend
- **Next.js 14** with TypeScript
- **Tailwind CSS v4**
- **WebSocket** for real-time event streaming

### Infrastructure
- **Docker Compose** — all services containerized
- **Caddy** — reverse proxy with automatic HTTPS via Let's Encrypt (prod profile)
- **Prometheus + Grafana + Loki** — metrics, dashboards, log aggregation (prod profile)
- **Alertmanager** — alert routing to Slack/Discord webhooks (prod profile)

### Media Processing (optional)
- **Whisper** (via faster-whisper) — speech-to-text for video/audio clips
- **Deepfake detection** — confidence scoring for video authenticity

---

## Project Structure

```
OSINT/
├── backend/
│   ├── main.py                  # FastAPI app, startup, WebSocket manager, bg tasks
│   ├── config.py                # All env vars + constants in one place
│   ├── db_postgres.py           # PostgreSQL schema + connection helper
│   ├── db_sqlite.py             # Legacy SQLite schema (kept for test compat)
│   ├── state.py                 # Shared mutable state (event buffers, indexes)
│   ├── intel_utils.py           # Pure functions: geo, confidence, claim alignment
│   ├── routes_v2.py             # All /api/v2/* endpoints + WebSocket
│   ├── routes_auth.py           # Auth endpoints (login, passkey, TOTP, session)
│   ├── routes_ops.py            # Health, stats, alerts, metrics endpoints
│   ├── auth_store.py            # User CRUD (psycopg3, %s placeholders)
│   ├── auth_security.py         # Token revocation, rate limiting, passkey auth
│   ├── auth_passkey.py          # WebAuthn/FIDO2 credential management
│   ├── mfa_totp.py              # TOTP secret storage + verification
│   ├── scripts/
│   │   ├── migrate_data.py      # One-shot SQLite → Postgres data copier
│   │   └── migrate_sqlite_to_postgres.py  # Earlier partial migration script
│   ├── hooks_local/             # Whisper + deepfake webhook service
│   ├── tests/                   # pytest test suite
│   └── requirements.txt
├── frontend/
│   ├── app/                     # Next.js App Router pages
│   │   ├── layout.tsx           # Root layout, boot overlay, theme
│   │   ├── page.tsx             # Redirects to /v2
│   │   ├── v2/                  # Main dashboard pages
│   │   │   ├── alerts/          # Alert timeline
│   │   │   ├── operations/      # Map view
│   │   │   ├── briefs/          # Intelligence reports
│   │   │   ├── graph/           # Neo4j visualization
│   │   │   ├── health/          # System status
│   │   │   └── admin/           # Admin panel
│   │   └── login/
│   └── components/
│       ├── system/
│       │   └── first-open-overlay.tsx  # Boot sequence animation (real data)
│       ├── briefs/              # Report components (cinematic, classification)
│       └── ...
├── docker-compose.yml
├── Caddyfile                    # TLS reverse proxy config
├── prometheus.yml               # Metrics scrape config
├── alerts.yml                   # Alert rules (6 rules)
├── alertmanager.yml             # Alert routing to webhooks
├── scripts/
│   └── backup.sh                # Daily pg_dump + 30-day retention
├── .github/
│   └── workflows/ci.yml         # GitHub Actions: test → build → deploy
├── docs/
│   ├── runbook.md               # Ops procedures (deploy, rollback, restore)
│   └── plans/                   # Architecture planning docs
└── .env                         # Secrets (gitignored)
```

---

## Docker Architecture

All services run in Docker Compose. There are two profiles:
- **Default** (no profile flag): dev/home server stack — backend, frontend, postgres, neo4j, redis, ollama, media-hooks
- **`prod` profile**: adds Caddy (HTTPS), Loki, Grafana, Prometheus, Alertmanager, backup cron

```
┌─────────────────────────────────────────────────────────┐
│                    caddy:80/443 (prod)                  │
│              ↙ frontend:3000    ↘ backend:8000          │
└─────────────────────────────────────────────────────────┘
                         │
         ┌───────────────┼────────────────┐
         ▼               ▼                ▼
    postgres:5432    neo4j:7687       redis:6379
    (PostGIS)        (Graph DB)       (Cache/RL)
         │
         └──────────────────────────────────┐
                                            ▼
                                       ollama:11434
                                  (phi4-mini / llama3.1:8b)

Monitoring (prod only):
prometheus:9090 → alertmanager:9093 → webhooks
grafana:3001 ← prometheus + loki:3100
```

### Memory Limits
| Service | Limit |
|---------|-------|
| backend | 1 GB |
| frontend | 512 MB |
| postgres | 512 MB |
| neo4j | 1.5 GB |
| redis | 256 MB |
| prometheus | 256 MB |
| grafana | 256 MB |
| loki | 256 MB |
| alertmanager | 128 MB |

---

## Data Sources

| Source | What it gives you | Poll interval | Enable flag |
|--------|------------------|---------------|-------------|
| **ADS-B (adsb.lol)** | Military aircraft positions (callsign, altitude, speed, heading) | 12s | `ENABLE_ADSBLOL=1` |
| **AIS (AISStream)** | Maritime vessel positions (MMSI, vessel type, destination) | 30s (WebSocket) | `ENABLE_AISSTREAM=1` |
| **FIRMS (NASA)** | Wildfire/fire hotspot detection (VIIRS/MODIS satellite) | 180s | `ENABLE_FIRMS=1` |
| **Red Alert (OREF)** | Israeli rocket siren alerts with affected cities | 3s | Always on |
| **RSS Feeds** | English/Arabic news from conflict-zone outlets | 180s | Always on |
| **Telegram Channels** | Direct channel messages, photos, videos | 60s | `ENABLE_TELEGRAM` |

### Bounding Boxes
All geo-filtered sources use configurable bounding boxes in `.env`:
```
AISSTREAM_BBOX=30,12,63,40   # format: lat_south,lng_west,lat_north,lng_east
FIRMS_BBOX=30,12,63,40
```

### Deduplication
- **Articles**: SHA256(title + link), tracked in a capped set (10K max)
- **Aircraft**: ICAO code state tracking within a 12s window
- **Alerts**: Alert ID + 1-hour timestamp bucketing (prevents duplicate sirens)
- **Telegram**: Post ID set (auto-clears at 6000 entries to prevent memory bloat)

---

## Event Pipeline

Every event, regardless of source, goes through the same pipeline:

```
Data source (poll/websocket/webhook)
  ↓
Create event dict {id, type, source, desc, lat, lng, timestamp, ...}
  ↓
Dedup check → skip if seen
  ↓
Geolocation (reverse geocode if lat/lng available)
  ↓
Confidence scoring (source reliability × geo certainty)
  ↓
DEFCON level assessment (1–5 based on event type/confidence)
  ↓
INSERT INTO events + events_v2 (PostgreSQL)
  ↓
Append to events_history deque (maxlen=30,000, in-memory)
  ↓
WebSocket broadcast to all connected clients
```

### Event Types
```
STRIKE       — weapons impact
CRITICAL     — immediate threat
ACTIVITY     — troop/equipment movement
UPDATE       — intelligence update
ALERT        — civil defense (rocket sirens)
FLIGHT       — aircraft telemetry
MARITIME     — AIS vessel data
FIRE         — FIRMS satellite detection
MEDIA        — social media content
```

---

## API Endpoints

### Health & Stats
```
GET  /api/health         → {status: "ok", checks: {postgres, redis, ollama}}
GET  /api/stats          → {events_total, aircraft_tracked, vessels_tracked, uptime_seconds, ...}
GET  /api/metrics        → Prometheus text format
```

### Events
```
GET  /api/events?limit=80               → latest events (in-memory)
GET  /api/v2/events?limit=100&source=X  → paginated events from Postgres
GET  /api/sources/recent?limit=150      → events grouped by source
GET  /api/v2/alerts?limit=60            → recent alerts with severity
```

### AI Analysis
```
POST /api/v2/ai/ops-brief               → generate INTSUM/SITREP/THREAT_ASSESSMENT
POST /api/v2/ai/verify-claim            → credibility check {classification, confidence_0_100}
GET  /api/v2/system                     → AI runtime status, model info, DEFCON level
```

### Intelligence Reports (Briefs)
```
POST /api/v2/brief/generate             → generate structured intelligence report
GET  /api/v2/brief/print-ready          → export-ready HTML brief
GET  /api/v2/briefs                     → list saved briefs
```

### Graph Intelligence
```
GET  /api/v2/graph/entities             → Neo4j node exploration
GET  /api/v2/graph/relationships        → entity relationship queries
```

### Auth
```
POST /api/auth/login                    → password auth
POST /api/auth/logout                   → session invalidation
GET  /api/auth/session                  → current user
POST /api/auth/passkey/register/begin   → WebAuthn registration
POST /api/auth/passkey/register/verify
POST /api/auth/passkey/authenticate/begin
POST /api/auth/passkey/authenticate/verify
```

### WebSocket
```
WS   /ws                               → real-time event stream (heartbeat every 30s)
```

---

## Authentication

Three auth modes, can be mixed:

### 1. Password (legacy/dev)
Standard username + password. JWT stored in HttpOnly cookie. Rate-limited via Redis (`_check_rate_limit` using INCR + EXPIRE). Failed logins tracked separately.

### 2. WebAuthn / Passkey (recommended for prod)
FIDO2/WebAuthn. Browser creates a hardware-backed credential (TouchID, Windows Hello, YubiKey). Zero passwords stored. The credential is tied to `PASSKEY_RP_ID` (must be your domain).

Set `AUTH_ADMIN_REQUIRE_PASSKEY=1` to force passkey for admin accounts.

### 3. TOTP MFA
Time-based one-time passwords. Optional, per-user opt-in. Secrets stored in `user_mfa_totp` table in Postgres.

### Roles
- `admin` — full access, user management
- `analyst` — read events, generate briefs, verify claims
- `viewer` — read-only

### Emergency Access
`AUTH_BREAK_GLASS_CODE` in `.env` — emergency bypass code if you're locked out. Use sparingly. Logged in audit trail.

---

## Database Schema

All 14 tables live in PostgreSQL (PostGIS 16-3.4). SQLite was fully removed.

```sql
-- Core tables
events           -- primary event log (all sources)
events_v2        -- extended metadata (confidence, DEFCON, theater)
reviews          -- analyst review decisions per event
saved_views      -- saved filter configurations per user
watchlists       -- saved search queries with live hit counts
pinned_incidents -- incidents marked for follow-up
handoff_notes    -- shift handoff notes per incident
notification_rules -- alert notification rules per user
media_analysis   -- Whisper/deepfake results per event
eval_samples     -- accuracy evaluation ground truth
audit_logs       -- security audit trail

-- Auth tables
users            -- usernames, password hashes, roles
revoked_tokens   -- invalidated session token signatures
user_mfa_totp    -- TOTP secrets + used code tracking
user_passkeys    -- WebAuthn credential storage
```

Key note on the `events` table: `desc` is a reserved word in PostgreSQL, so it's quoted as `"desc"` in all SQL queries. If you add new queries touching this table, remember to quote it.

---

## AI / Intelligence Analysis

Everything runs locally via Ollama. No API keys, no data leaving your server.

### Models
- **phi4-mini** — fast, used for claim verification and quick summaries (default)
- **llama3.1:8b** — used for full intelligence reports (slower, more thorough)

Configure in `.env`:
```
V2_MODEL_DEFAULT=phi4-mini
V2_MODEL_VERIFY=phi4-mini
V2_MODEL_REPORT=llama3.1:8b
```

### What the AI does

**Claim Verification** (`/api/v2/ai/verify-claim`):
Takes an event title + body, returns:
```json
{
  "classification": "credible | uncertain | unlikely",
  "confidence_0_to_100": 72,
  "reasoning": ["Source is a known verified channel", "..."],
  "required_follow_up": ["Confirm with secondary source", "..."],
  "insufficient_evidence": false
}
```

**Ops Brief** (`/api/v2/ai/ops-brief`):
Pulls the last N Telegram/RSS events, generates a structured INTSUM, SITREP, or THREAT_ASSESSMENT in military format. Also runs verification cards on a 5-event sample.

**Confidence Scoring**:
Each event gets a confidence score (0–100) based on:
- Source reliability weight (configurable per source type)
- Geographic certainty (how precise the coordinates are)
- Event type severity

---

## The Boot Sequence (First Open Animation)

When you first open the site, there's a military-style boot sequence animation. It's not fake — it fetches real data:

- **`/api/stats`** → actual aircraft count, vessel count, total events, uptime
- **`/api/health`** → real Postgres/Redis/Ollama status (green or orange)

The right panel shows "Live System Status" with real per-dependency colors. The API latency line shows actual measured round-trip time. This all happens before the animation starts, so there's no mid-sequence jarring update.

Force-replay: open DevTools → Application → Clear Site Data → reload. Or `sessionStorage.removeItem('osint_boot_seen')` in the console.

---

## Monitoring & Alerting

### Prometheus (prod profile)
Scrapes `/api/metrics` every 15s. Stores 30 days of data.

### Alert Rules (`alerts.yml`)
| Alert | Condition | Severity |
|-------|-----------|----------|
| `BackendDown` | Prometheus can't reach backend for >1m | Critical |
| `HighErrorRate` | HTTP 5xx rate >5% for >5m | Critical |
| `EventIngestionSpike` | >500 events/min for >5m | Warning |
| `EventBufferNearFull` | In-memory buffer >90% full (27K/30K) | Warning |
| `OllamaHighErrorRate` | Polling errors accumulating for >10m | Warning |
| `ContainerMemoryHigh` | Container using >90% of memory limit | Warning |

### Alertmanager (`alertmanager.yml`)
Routes alerts to a webhook (Slack, Discord, PagerDuty, anything).
- Critical alerts: repeat every 1 hour until resolved
- Warnings: repeat every 4 hours

Set `ALERT_WEBHOOK_URL` in `.env` to your webhook endpoint.

### Grafana (prod profile)
Available at port 3001. Default password in `GRAFANA_PASSWORD` env var.
Add Prometheus as a data source (`http://prometheus:9090`) and Loki (`http://loki:3100`).

---

## Security

Things that were explicitly hardened:

1. **Rate limiting** — Redis-backed (INCR + EXPIRE), survives restarts. Auth endpoints rate-limited separately. In-memory fallback if Redis unavailable.

2. **CORS** — `CORSMiddleware` with explicit `CORS_ORIGINS` list (never `*`).

3. **Secrets** — `config.py` has a `_secret()` helper that reads from `/run/secrets/<name>` first, falls back to env var. Docker Compose mounts secrets for: `auth_secret`, `postgres_password`, `neo4j_password`, `aisstream_api_key`, `firms_map_key`.

4. **HTTPS** — Caddy handles TLS termination with automatic Let's Encrypt certs (prod profile). Set `AUTH_COOKIE_SECURE=1` when live.

5. **Security headers** — Caddyfile sets: `Strict-Transport-Security`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.

6. **Token revocation** — Revoked JWT signatures stored in Postgres `revoked_tokens` table with expiry-based cleanup.

7. **Audit logging** — Every write operation (user create, config change, etc.) logged to `audit_logs` table with actor, role, action, and payload.

---

## How to Run

### First Time

```bash
git clone <repo>
cd OSINT

# Set up environment
cp .env.example .env
# Edit .env — required fields:
# POSTGRES_PASSWORD, NEO4J_PASSWORD, AUTH_SECRET (min 32 chars),
# AUTH_DEFAULT_ADMIN_PASSWORD, AISSTREAM_API_KEY, FIRMS_MAP_KEY

# Build and start
docker compose build
docker compose up -d

# Watch startup
docker compose logs -f backend
```

Backend is healthy when you see `GET /api/health HTTP/1.1 200 OK` in the logs.

Frontend: http://localhost:3000
Backend: http://localhost:8000
API docs: http://localhost:8000/docs

### Production (with HTTPS + monitoring)

```bash
# Edit Caddyfile — replace yourdomain.com with your actual domain
# Edit .env — set AUTH_COOKIE_SECURE=1, PASSKEY_RP_ID=yourdomain.com

docker compose --profile prod up -d
```

Prometheus: http://localhost:9090
Grafana: http://localhost:3001

### Upgrade

```bash
git pull origin main
docker compose build backend frontend
docker compose up -d backend frontend
```

### Rollback

```bash
git log --oneline -10
git checkout <commit-hash>
docker compose build backend
docker compose up -d backend
```

---

## Backup & Restore

### Manual Backup

```bash
docker compose exec postgres pg_dump -U osint -d osint | gzip > backup.sql.gz
```

### Restore Test (done 2026-03-14, passed)

```bash
# Spin up throwaway postgres
docker run --rm -d --name test-restore \
  -e POSTGRES_DB=osint -e POSTGRES_USER=osint -e POSTGRES_PASSWORD=testpass \
  postgis/postgis:16-3.4

sleep 8

# Restore
gunzip -c backup.sql.gz | docker exec -i test-restore psql -U osint -d osint

# Verify
docker exec test-restore psql -U osint -d osint \
  -c "SELECT COUNT(*) FROM events_v2;"

# Cleanup
docker stop test-restore
```

The backup service (prod profile) runs this automatically daily and keeps 30 days.

---

## CI/CD

`.github/workflows/ci.yml` runs on every push:

1. **Test** — `pytest backend/tests/ -v` (17 tests)
2. **Build** — `docker compose build backend`
3. **Deploy** — SSH into server + `docker compose up -d` (main branch only)

Store deploy SSH key and all secrets in GitHub Actions secrets, not in the repo.

---

## Known Quirks & Technical Decisions

### `desc` is a reserved word in PostgreSQL
The original SQLite schema had a column called `desc`. SQLite doesn't care, PostgreSQL does. Fixed by quoting it as `"desc"` in all CREATE TABLE statements and queries. If you add SQL touching the `events` table, remember to quote it.

### DATABASE_URL with `@` in the password
If your Postgres password contains `@`, standard URL encoding doesn't work because Docker Compose decodes `%40` back to `@` when injecting env vars. The fix: pass `POSTGRES_PASSWORD` as a raw env var and build the URL in `config.py` using `urllib.parse.quote(password, safe="")`. This is already handled — don't put a full `DATABASE_URL` in `.env`.

### `_GraphStoreProxy` is never None
The Neo4j graph store uses a proxy object pattern. The proxy itself is always non-None, so checking `if _graph_store is not None` is always True and useless. The real check is `if _state._graph_store is not None`. If you work with the graph store, always check the underlying state object, not the proxy.

### SQLite → PostgreSQL migration
Completed 2026-03-14. All 14 tables are in PostgreSQL now. `db_sqlite.py` still exists for test compatibility (tests use in-memory SQLite). Production code has zero `sqlite3` imports. Migration script at `backend/scripts/migrate_data.py` if you need to copy data from an old SQLite file.

### WebSocket state is in-memory
The WebSocket connection manager (`manager.connections`) lives in memory. If you run multiple backend containers, clients connected to different instances won't see each other's events. Fix: Redis pub/sub (Phase 5, not needed until horizontal scaling).

### Ollama is sequential
Only one model runs at a time (`max_concurrency: 1`). Concurrent AI requests queue up. Fast enough for single-user use. Fix: proper job queue with background workers (Phase 5).

---

## What's Next (Optional)

From the production readiness plan — everything critical is done. What's left is genuinely optional:

1. **Set `ALERT_WEBHOOK_URL`** in `.env` — one env var and Alertmanager starts routing real alerts.
2. **OpenTelemetry tracing** — per-request spans to identify slow DB calls. Add `opentelemetry-instrumentation-fastapi` + Jaeger.
3. **Data source license audit** — read ToS for adsb.lol, AISStream, NASA FIRMS, OREF before going public.
4. **Redis pub/sub** — only needed if running multiple backend replicas.
5. **Ollama job queue** — only needed under real concurrent load.

---

## Final Note

This project does real things. It tracks real aircraft, real ships, real fires, real alerts. The AI analysis is basic but functional. The authentication is genuinely secure (WebAuthn, not just passwords). The infrastructure is production-grade — TLS, backups, monitoring, alerting, CI/CD.

Is it Palantir? No. But it's yours, it runs for free, and you understand every line of it.

---

*Generated 2026-03-14 by the project author with Claude.*
