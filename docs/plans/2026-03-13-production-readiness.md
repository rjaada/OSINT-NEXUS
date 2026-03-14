# Production Readiness Plan — OSINT Nexus

> **Status:** Draft — 2026-03-13
> **Goal:** Take OSINT Nexus from "runs on my server" to a deployable, observable, resilient production system.
> **Rule:** Work in priority order. Don't start Phase 2 until Phase 1 is done.

---

## Phase 1 — Critical Blockers (must fix before any real traffic)

These will cause outages, data loss, or security incidents in production.

---

### 1.1 TLS / Reverse Proxy

**Problem:** FastAPI runs bare on port 8000. No HTTPS. Credentials, tokens, and WebSocket data travel in plaintext.

**What to do:**
- Add a reverse proxy (Caddy is the simplest — auto-provisions Let's Encrypt certs).
- Caddy sits in front of FastAPI (port 8000) and Next.js (port 3000).
- WebSocket proxying must be explicitly configured (`reverse_proxy` with `upgrade`).
- Set `AUTH_COOKIE_SECURE=1` in `.env` once HTTPS is live.
- Add security headers: `Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, `Content-Security-Policy`.
- Update `docker-compose.yml` to include the Caddy container and remove direct port exposure of backend/frontend.

**Done when:** `https://yourdomain.com` loads, cookies have `Secure` flag, WebSocket connects over `wss://`.

---

### 1.2 Fix Neo4j Auth Mismatch

**Problem:** `NEO4J_PASSWORD` in `.env` does not match what Neo4j was initialized with. Graph store silently fails at startup every time.

**What to do:**
- Decide on one canonical password.
- Either wipe the Neo4j volume and restart with the correct password, or use `neo4j-admin` to change the password on the existing volume.
- Add a startup check: if Neo4j is unreachable, log a clear fatal error and exit — don't silently continue with a broken graph store.
- Document the bootstrap procedure in the runbook (Phase 4).

**Done when:** Graph store connects cleanly on startup, no auth errors in logs.

---

### 1.3 Consolidate to One Database (SQLite → PostgreSQL)

**Problem:** SQLite is used alongside PostgreSQL. Across container restarts and replicas this creates split state. SQLite is not suited for concurrent writes at scale.

**What to do:**
- Audit every SQLite table: events, deduplication state, sessions, report cache.
- Migrate each to PostgreSQL tables (schema already partially defined in `db_sqlite.py`).
- Use the existing `migrate_sqlite_to_postgres.py` script as the starting point, extend it to cover all tables.
- Remove SQLite dependency from `requirements.txt` and `db_sqlite.py` after migration.
- Keep SQLite only for local dev if needed, but it must not run in the production Docker image.

**Done when:** No `sqlite3` imports remain in production code paths. All state lives in Postgres.

---

### 1.4 Redis-Backed Rate Limiting

**Problem:** Rate limiting is tracked in a Python dict (`_rate_limit` in `state.py`). Resets on every restart. Across multiple containers it is completely ineffective.

**What to do:**
- Add Redis to `docker-compose.yml` (use the official `redis:7-alpine` image).
- Replace the in-memory `_rate_limit` dict with Redis `INCR` + `EXPIRE` calls.
- Apply rate limiting at the auth endpoints minimum: `/api/auth/login`, `/api/auth/register`, all passkey endpoints.
- Apply a global per-IP rate limit for all API routes.
- Failed login tracking (`_failed_logins`) should also move to Redis.

**Done when:** Restarting the backend container does not reset rate limit counters. Rate limits work across two backend instances.

---

### 1.5 Secrets Management

**Problem:** All secrets live in `.env`. Anyone with filesystem access has every credential. Secrets are not rotated, not audited, and not scoped.

**What to do (minimal viable for now):**
- Ensure `.env` is in `.gitignore` and never committed (it already is — verify this holds).
- Add Docker secrets support: move `AUTH_SECRET`, `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, API keys to Docker secrets instead of environment variables.
- Update `config.py` to read from `/run/secrets/<name>` when the env var is absent.
- Rotate `AUTH_SECRET` — any existing sessions will be invalidated (acceptable for a launch reset).
- Document which secrets exist and who can access them.

**Long-term (after launch):** Move to HashiCorp Vault or AWS Secrets Manager.

**Done when:** No plaintext secrets in any Docker environment variable. Secrets mounted as files.

---

## Phase 2 — Reliability (prevents incidents)

These won't block launch but will cause pain within weeks of real usage.

---

### 2.1 CI/CD Pipeline

**Problem:** Deploys are manual `docker compose build && docker compose up`. No automated test gate. One bad push goes straight to production.

**What to do:**
- Set up GitHub Actions (or GitLab CI if self-hosted).
- Pipeline stages:
  1. `pytest` — run all 17 existing tests, fail pipeline on any failure.
  2. `docker compose build` — verify image builds clean.
  3. On merge to `main` only: deploy to production server via SSH + `docker compose up -d`.
- Add a `.github/workflows/ci.yml` (or equivalent).
- Add a branch protection rule: merges to `main` require CI to pass.
- Store deploy SSH key and all secrets in GitHub Actions secrets (not in the repo).

**Done when:** Every PR runs tests automatically. Merging broken code to main is impossible.

---

### 2.2 Automated Backups

**Problem:** No backup strategy for Postgres, Neo4j, or persistent volumes. One disk failure or accidental `docker volume rm` and everything is gone.

**What to do:**
- **Postgres:** Daily `pg_dump` via a cron container or systemd timer. Compress and ship to S3 / Backblaze B2 / any offsite storage. Keep 30 days.
- **Neo4j:** Use `neo4j-admin database dump` on a schedule. Same offsite shipping.
- **Test restores:** At least monthly, restore a backup to a throwaway container and verify data integrity. A backup you've never tested is not a backup.
- Document the restore procedure in the runbook.

**Done when:** Backups run daily, are stored offsite, and at least one restore has been tested successfully.

---

### 2.3 Real Health Checks

**Problem:** `/api/health` likely returns 200 even when Postgres, Neo4j, or Ollama are down. This means load balancers and uptime monitors see false positives.

**What to do:**
- Extend the health endpoint to actively probe each dependency:
  - Postgres: run `SELECT 1`.
  - Neo4j: run a lightweight Cypher query.
  - Ollama: hit `/api/tags` and verify response.
  - Redis (once added): `PING`.
- Return `200` only if all critical dependencies are healthy.
- Return `503` with a JSON body listing which dependency failed.
- Add Docker `HEALTHCHECK` directives to `docker-compose.yml` for backend and frontend containers.

**Done when:** Taking down Postgres causes the health endpoint to return 503 within 10 seconds.

---

### 2.4 Structured Logging + Log Aggregation

**Problem:** Mix of `print()` and `logging` module calls. No central place to query logs. When something breaks in production there is nothing to search.

**What to do:**
- Replace all `print()` calls with `logging` calls at the appropriate level.
- Configure `logging` to emit JSON-formatted lines (use `python-json-logger` library).
- Add context to every log line: `request_id`, `user_id` (hashed), `route`, `duration_ms`.
- Add Loki + Grafana to `docker-compose.yml` for log aggregation (Loki is lightweight).
- Configure the Docker logging driver to ship container stdout to Loki.
- Set log retention policy (30 days of raw logs, summarized forever).

**Done when:** You can open Grafana, type a query, and find any log line from the last 24 hours in under 10 seconds.

---

### 2.5 Data Retention + Pruning

**Problem:** Events, articles, and deduplication sets accumulate indefinitely. The deque caps in memory (`maxlen=30_000`) but the database has no pruning. Disk fills over weeks/months.

**What to do:**
- Define retention policy: e.g. raw events 90 days, processed reports 1 year, deduplication hashes 30 days.
- Add a scheduled pruning job (already have a scheduler in the backend — add a daily task).
- Pruning targets: `events` table, `seen_articles` persistent store (if any), old media files in `TELEGRAM_MEDIA_DIR`.
- Add a disk usage metric to the health endpoint: warn when Postgres volume is >80% full.

**Done when:** Disk usage is flat week-over-week under normal load.

---

### 2.6 Graceful Shutdown

**Problem:** On SIGTERM (container stop), in-flight HTTP requests, open WebSocket connections, and background polling tasks may be abruptly terminated. Users see connection drops.

**What to do:**
- FastAPI supports lifespan context managers — use one to register a shutdown handler.
- On shutdown: stop accepting new connections, wait for in-flight requests to complete (max 10s timeout), drain the media job queue, cancel background tasks cleanly.
- Test by running `docker compose stop backend` while a client is connected via WebSocket — verify the client gets a clean close frame, not a TCP reset.

**Done when:** `docker compose stop` causes zero error logs and all clients disconnect cleanly.

---

## Phase 3 — Observability (know when things go wrong before users tell you)

---

### 3.1 Metrics + Alerting

**Problem:** Prometheus metrics endpoint exists but nothing consumes it. No alerting. You find out about outages from users.

**What to do:**
- Add Prometheus + Grafana to `docker-compose.yml`.
- Create dashboards for:
  - Request rate and error rate by route.
  - WebSocket connection count.
  - Background task success/failure rates (RSS polls, flight polls, etc.).
  - Ollama inference latency and error rate.
  - Postgres connection pool usage.
  - Memory and CPU per container.
- Set up Alertmanager with at minimum these alerts:
  - Error rate > 5% for 5 minutes → page.
  - Health check failing → page immediately.
  - Disk > 80% → warn.
  - Ollama error rate > 20% → warn.
- Route alerts to email or a Slack/Discord webhook (not PagerDuty unless you want to pay).

**Done when:** You know about an outage within 2 minutes of it starting, without a user telling you.

---

### 3.2 Distributed Tracing (Optional but Valuable)

**Problem:** When a slow request comes in, you can't tell which part (Postgres, Neo4j, Ollama, network) was slow.

**What to do:**
- Add OpenTelemetry instrumentation to FastAPI (one middleware, automatic for most routes).
- Use Jaeger or Tempo (Grafana's trace backend) for storage.
- Instrument the Ollama call, database queries, and graph store calls with trace spans.

**Done when:** You can click on a slow request trace and see exactly which database call took 800ms.

---

## Phase 4 — Operations (the human side)

---

### 4.1 Runbook

**Problem:** No documentation on how to operate this system. If you step away for a month and something breaks, you start from zero.

**What to write (`docs/runbook.md`):**
- How to deploy (first-time and upgrades).
- How to roll back a bad deploy.
- What to do when each health check fails (Postgres down, Neo4j down, Ollama down).
- How to restore from backup.
- What the Red Alert 403 means and why it's harmless.
- How to add a new user / reset a password.
- How to check current DEFCON level and recent events via API.
- Emergency contacts / escalation path.

**Done when:** Someone who has never seen this project can bring it back from a full failure in under 30 minutes using the runbook alone.

---

### 4.2 CORS + Security Headers Audit

**Problem:** CORS policy is not explicitly configured. Default FastAPI CORS is wide open or too restrictive depending on version. Security headers are not set.

**What to do:**
- Explicitly set `CORSMiddleware` with allowed origins (your domain only, not `*`).
- Add security headers via Caddy or a FastAPI middleware: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`.
- Set `Content-Security-Policy` for the frontend (restricts what scripts/frames can load).

**Done when:** `https://securityheaders.com` gives the frontend an A rating.

---

### 4.3 OSINT Data Source License Audit

**Problem:** ADS-B (adsb.lol), AIS (AISStream), FIRMS (NASA), Red Alert (OREF), Telegram — each has terms of use. High-traffic or commercial use may violate them.

**What to do:**
- Read the terms of service for each data source.
- Document what's allowed (personal use, commercial use, redistribution).
- If any source prohibits your intended use, either remove it or contact them for a commercial license.
- Add this to the runbook so it's reviewed annually.

---

## Phase 5 — Scalability (only needed if you actually get users)

Do not start this phase until you have real traffic that justifies it.

---

### 5.1 Horizontal Scaling

**Problem:** WebSocket state is in-memory. Adding a second backend container breaks real-time for half the clients (their messages go to a different instance).

**What to do:**
- Move WebSocket pub/sub to Redis (Redis Pub/Sub or Redis Streams).
- All backend instances subscribe to the same Redis channel.
- When one instance broadcasts an event, all instances relay it to their connected clients.
- Once this is done, you can run multiple backend replicas behind a load balancer.

---

### 5.2 Ollama Scaling

**Problem:** Ollama is a single GPU/CPU process. Slow model inference (15–22s) blocks concurrent requests. Under load, the queue backs up.

**What to do:**
- Add a proper job queue for AI inference requests (Redis Queue / Celery / ARQ).
- Background workers pull jobs from the queue and call Ollama independently.
- HTTP endpoints return immediately with a job ID; clients poll or receive a WebSocket notification when done.
- Consider running Ollama on a dedicated machine if inference volume grows.

---

### 5.3 CDN for Frontend

**Problem:** Next.js serves static assets directly. Under real load, a CDN would dramatically reduce server load and latency for international users.

**What to do:**
- Put Cloudflare (free tier) in front of the domain.
- Configure caching rules: cache static assets (`_next/static/*`) aggressively, never cache API routes.
- Enable Cloudflare's DDoS protection and bot management.

---

## Summary Checklist

| Phase | Item | Priority |
|-------|------|----------|
| 1 | TLS / Caddy reverse proxy | 🔴 Critical |
| 1 | Fix Neo4j auth mismatch | 🔴 Critical |
| 1 | Consolidate SQLite → PostgreSQL | 🔴 Critical |
| 1 | Redis-backed rate limiting | 🔴 Critical |
| 1 | Secrets management (Docker secrets) | 🔴 Critical |
| 2 | CI/CD pipeline (GitHub Actions) | 🟠 High |
| 2 | Automated backups + tested restores | 🟠 High |
| 2 | Real health checks (probe dependencies) | 🟠 High |
| 2 | Structured logging + Loki | 🟠 High |
| 2 | Data retention + pruning job | 🟠 High |
| 2 | Graceful shutdown | 🟠 High |
| 3 | Prometheus + Grafana + alerting | 🟡 Medium |
| 3 | Distributed tracing (OpenTelemetry) | 🟡 Medium |
| 4 | Runbook documentation | 🟡 Medium |
| 4 | CORS + security headers audit | 🟡 Medium |
| 4 | Data source license audit | 🟡 Medium |
| 5 | Redis pub/sub for WebSocket scale-out | 🟢 When needed |
| 5 | Ollama job queue | 🟢 When needed |
| 5 | CDN (Cloudflare) | 🟢 When needed |

---

*Written 2026-03-13. Revisit after completing each phase.*
