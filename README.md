# OSINT Nexus

**Autonomous all-source intelligence platform for real-time conflict monitoring.**

OSINT Nexus ingests live data from news feeds, Telegram channels, flight tracking, maritime AIS, and civil defense alerts — fuses them through a Neo4j temporal knowledge graph — and runs LLM-powered reasoning to produce structured intelligence products: SITREPs, causal chains, contradiction detection, and ranked priority actions.

> Built as a production system, not a demo. Running live data. 2,300+ events ingested.

---

## What It Does

Most dashboards show you data. OSINT Nexus **reasons** about it.

| Layer | Capability | Status |
|-------|-----------|--------|
| **Ingestion** | RSS/news, Telegram channels, ADSB flights, AIS maritime, Red Alert civil defense | Live |
| **Fusion** | Neo4j temporal knowledge graph — actors, events, locations, corroboration edges | Live |
| **Reasoning** | LLM causal chain analysis, contradiction detection, SITREP generation | Live |
| **Verification** | Multi-source corroboration scoring, disinformation signature detection | Live |
| **Action** | Priority Action Panel, Telegram digest, ETA-scored alerts | Live |

---

## Intelligence Products

### Priority Action Panel
Always-visible top-3 ranked events scored by `confidence × corroboration × freshness × type_weight`. Zero clicks. One-click suppress. Every card shows: "Ranked #1 because: X." Designed to **NATO Meaningful Human Control (MHC)** standards — the system explains its ranking, the analyst decides.

### Intel Trace
Click any event → full causal chain from Neo4j + LLM analysis. Preceded by, followed by, actors involved, contradiction flags, confidence calibration. Powered by DeepSeek-R1 via Groq (Ollama local fallback on rate limit).

### SITREP
Auto-generated situation reports every 60 minutes: what happened, why it happened, what to watch next (3 specific watch items with timeframes), confidence level with reasoning. Stored in PostgreSQL, queryable via API.

### Disinformation Detector
Sliding 45-minute window across all sources. Flags when the same claim appears on 3+ channels simultaneously — the coordinated emergence signature documented in Flashpoint's Ukraine OSINT deployment.

### Press Brief Analyzer
Paste any press conference transcript → structured intelligence extraction: headline, key claims, threats and warnings, military signals, observed facts vs. inference, follow-up recommendations.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Data Sources                          │
│   RSS/News · Telegram · ADSB flights · AIS · Red Alert       │
└─────────────────────────┬────────────────────────────────────┘
                          │  async pollers
┌─────────────────────────▼────────────────────────────────────┐
│                   Backend  (FastAPI)                          │
│  geocoding · classification · confidence scoring · ACLED     │
│  taxonomy · MGRS coords · source reliability weights         │
└──────┬──────────────────┬──────────────────┬─────────────────┘
       │                  │                  │
┌──────▼──────┐   ┌───────▼──────┐   ┌───────▼──────┐
│ PostgreSQL  │   │    Neo4j     │   │    Redis     │
│ events_v2   │   │ Temporal KG  │   │  WebSocket   │
│ ACLED cols  │   │ 760+ nodes   │   │  pub/sub     │
│ AI reports  │   │ causal graph │   │  live feed   │
└─────────────┘   └──────────────┘   └─────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────┐
│                   Reasoning Engine                            │
│   Groq LLM (primary) → Ollama local (auto-fallback on 429)  │
│   SITREP · Intel Trace · Contradiction detection             │
│   Disinformation clustering · Causal chain analysis          │
└─────────────────────────┬────────────────────────────────────┘
                          │  REST + WebSocket
┌─────────────────────────▼────────────────────────────────────┐
│                  Frontend  (Next.js 15)                       │
│  Intel Feed · Live Map · Alerts · SITREP · Graph Explorer    │
│  Priority Panel · Press Brief · Admin · AR/RTL interface     │
└──────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

**Backend**
- Python 3.11 · FastAPI · psycopg3
- Neo4j — temporal knowledge graph (760+ nodes, 6 relationship types)
- PostgreSQL + PostGIS
- Redis — WebSocket pub/sub
- Groq API (LLaMA 3 / DeepSeek-R1) with Ollama local LLM fallback

**Frontend**
- Next.js 15 App Router · TypeScript · Tailwind CSS
- MapLibre GL — conflict zone overlays, event markers, MGRS grid
- Radix UI · WebSocket real-time feed

**Infrastructure**
- Docker Compose (9 services)
- Caddy — reverse proxy + automatic HTTPS
- WebAuthn / Passkey authentication
- Role-based access control: viewer / analyst / admin
- CI/CD via GitHub Actions

---

## Getting Started

### Prerequisites
- Docker + Docker Compose
- Groq API key ([free tier](https://console.groq.com))

### Setup

```bash
git clone https://github.com/rjaada/OSINT-NEXUS.git
cd OSINT-NEXUS
cp .env.example .env
# Add your GROQ_API_KEY and credentials to .env
docker compose up -d
```

App available at `http://localhost:3000`.

### Key Environment Variables

```env
# Required
GROQ_API_KEY=your_key
AUTH_SECRET=your_secret_key
AUTH_DEFAULT_ADMIN_USER=admin
AUTH_DEFAULT_ADMIN_PASSWORD=your_password

# Optional — live flight / maritime / alert ingestion
ENABLE_ADSBLOL=1
ENABLE_AISSTREAM=1
AISSTREAM_API_KEY=your_key
ENABLE_FIRMS=1
FIRMS_MAP_KEY=your_key

# Optional — Telegram digest (sends SITREP daily at 06:00 UTC)
TG_DIGEST_TOKEN=your_bot_token
TG_DIGEST_CHAT_ID=your_chat_id

# Database (auto-configured in Docker)
DATABASE_URL=postgresql://osint:osint@postgres:5432/osint
NEO4J_URI=bolt://neo4j:7687
REDIS_URL=redis://redis:6379
```

Full variable reference: see `.env.example`.

---

## Pages

| Route | What It Is |
|-------|-----------|
| `/v2` | Intel Feed — live events, Priority Action Panel, corroboration badges |
| `/v2/alerts` | Confidence & ETA board — scored alerts with chain status |
| `/v2/sitrep` | AI situation reports — causal chain, contradictions, watch items, prediction accuracy |
| `/v2/briefs` | Operational intelligence briefs with MGRS coordinates and threat assessment |
| `/v2/sources` | Source reliability desk — lag, quality scores, per-source OPS metrics |
| `/v2/health` | System health — PostgreSQL, Redis, watchdog, queue stats |
| `/v2/admin` | User management + dynamic conflict zone editor |
| `/v2/graph` | Neo4j knowledge graph explorer — filter by relationship type and time range |
| `/v2/card` | Operator credential card |
| `/v2/ar/...` | Full Arabic RTL interface mirroring all v2 pages |

---

## Security

- **WebAuthn / Passkey** — hardware key enrollment for admin accounts
- **CSRF protection** on all state-changing endpoints
- `httponly` + `SameSite=Strict` session cookies
- **Role-based route protection** — 34 API endpoints gated
- **Audit log** on all admin actions
- SHA-256 event IDs
- Startup validation — backend refuses to start with weak `AUTH_SECRET` or default admin password
- TOTP (time-based OTP) support for analyst and admin roles

---

## Data Sources

| Source | Type | Reliability Weight |
|--------|------|--------------------|
| BBC News · Reuters · AFP · Al Jazeera | RSS | 90–95 |
| Jerusalem Post · Haaretz · Times of Israel | RSS | 75–85 |
| AJ Mubasher · Roaa War Studies (TG) | Telegram | 55–70 |
| ADSB.lol | Flight tracking (sensor) | 95 |
| AISStream | Maritime AIS (sensor) | 95 |
| Red Alert (Tzeva Adom) | Civil defense (official) | 95 |
| NASA FIRMS | Active fire (sensor) | 90 |

Source weights are dynamic — analyst ratings on Intel Trace feed back into per-source reliability scores automatically.

---

## Event Schema (ACLED-compatible)

Every event in `events_v2` carries:

| Field | Values | Purpose |
|-------|--------|---------|
| `time_precision` | 1–3 | 1=exact timestamp, 2=day, 3=estimated |
| `geo_precision` | 1–3 | 1=exact coords, 2=city-level, 3=region |
| `source_scale` | local / national / international / subnational | Source classification |
| `civilian_targeting` | boolean | Hospital, school, market, aid worker keywords |
| `acled_event_type` | Battles / Explosions / Strategic developments / ... | ACLED taxonomy |
| `acled_sub_event_type` | Armed clash / Air strike / Shelling / ... | ACLED sub-taxonomy |

Dataset is directly comparable to [ACLED's](https://acleddata.com) published conflict data.

---

## Key API Endpoints

```
# Events & Intelligence
GET  /api/v2/events
GET  /api/v2/alerts
GET  /api/v2/sitrep/latest
GET  /api/v2/sitrep/history?limit=10
GET  /api/v2/sitrep/accuracy
POST /api/v2/intel-trace/{event_id}
GET  /api/v2/disinfo/scan
GET  /api/v2/source-reliability
POST /api/v2/events/{event_id}/review

# System
GET  /api/v2/system
GET  /api/v2/health
GET  /api/v2/graph?limit=350
GET  /api/v2/metoc

# Conflict Zones (admin)
GET    /api/v2/conflict-zones
POST   /api/v2/conflict-zones
DELETE /api/v2/conflict-zones/{id}

# Auth
POST /api/auth/login
POST /api/auth/register
GET  /api/auth/session
POST /api/auth/passkey/register/options
POST /api/auth/passkey/register/verify

# Admin
GET    /api/admin/users
PATCH  /api/admin/users/{username}/role
DELETE /api/admin/users/{username}

# WebSocket
WS /ws/live
```

---

## Research Basis

OSINT Nexus implements techniques documented in 20+ academic and practitioner sources:

- **ACLED** — event taxonomy, three-tier review methodology, geo/time precision standards
- **NATO HFM-377** — Meaningful Human Control design for AI-assisted decisions
- **DARPA EMHAT** — explainability requirements for machine-generated threat assessments
- **Endsley (1995)** — Situation Awareness: perception → comprehension → projection
- **Flashpoint Ukraine** — disinformation detection via simultaneous emergence signatures
- **Recorded Future** — corroboration-first display, alert fatigue reduction
- **Bellingcat** — open-source verification methodology for user-generated content

Full literature review available on request.

---

## Repository Layout

```
.
├── backend/
│   ├── main.py              # FastAPI app, routes, WebSocket
│   ├── pollers.py           # RSS, Telegram, ADSB, Red Alert, SITREP pollers
│   ├── reasoning_engine.py  # SITREP generation, causal chain, contradiction detection
│   ├── disinfo_detector.py  # Coordinated info-op signature detection
│   ├── graph_store.py       # Neo4j temporal knowledge graph
│   ├── v2_store.py          # PostgreSQL persistence + ACLED field mapping
│   ├── db_ops.py            # Core DB operations
│   ├── groq_client.py       # Groq + Ollama LLM client with fallback
│   ├── prediction_tracker.py # Layer 4: scores SITREP predictions vs reality
│   ├── market_poller.py     # Gold, WTI, Brent, DXY, S&P500 via Yahoo Finance
│   └── telegram_digest.py   # Daily SITREP → Telegram (EN + AR)
├── frontend/
│   └── app/v2/              # Next.js App Router pages
├── docker-compose.yml
├── Makefile
└── README_K8s.md
```

---

## Status

Active development. Running live data.

- **2,359+ events** in PostgreSQL
- **760+ nodes** in Neo4j knowledge graph
- **11 active source connectors**
- Independent QA audit completed March 2026

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built by [Rachid Jaada](https://github.com/rjaada)*
