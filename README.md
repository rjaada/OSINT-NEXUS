<div align="center">

<img src="opening.gif" alt="OSINT Nexus" width="100%" />

# OSINT Nexus

**Autonomous all-source intelligence analyst. Never sleeps.**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-9_services-2496ED?logo=docker)](docker-compose.yml)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](backend/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)](frontend/)
[![Research](https://img.shields.io/badge/Preprint-Zenodo-blue)](https://doi.org/10.5281/zenodo.19169143)

</div>

---

Most dashboards show you data. OSINT Nexus **reasons** about it.

It ingests live news, Telegram channels, flight tracking, maritime AIS, and civil defense alerts — fuses them through a Neo4j temporal knowledge graph — and runs LLM reasoning to produce structured intelligence products: SITREPs, causal chains, contradiction detection, and ranked priority actions.

> Running live data. 2,300+ events ingested. Built as a production system, not a demo.

---

## What It Does

| Layer | Capability | Status |
|-------|-----------|--------|
| **Ingestion** | RSS/news, Telegram, ADSB flights, AIS maritime, Red Alert civil defense | Live |
| **Fusion** | Neo4j temporal knowledge graph — actors, events, locations, corroboration edges | Live |
| **Reasoning** | LLM causal chain analysis, contradiction detection, SITREP generation | Live |
| **Verification** | Multi-source corroboration scoring, disinformation signature detection | Live |
| **Action** | Priority Action Panel, Telegram digest, ETA-scored alerts | Live |

---

## Intelligence Products

### Priority Action Panel
Always-visible top-3 ranked events scored by `confidence × corroboration × freshness × type_weight`. Zero clicks to reach. Every card explains itself: *"Ranked #1 because: X."* Designed to **NATO Meaningful Human Control (MHC)** standards — the system explains, the analyst decides.

### Intel Trace
Click any event → full causal chain from Neo4j + LLM analysis. What came before, what followed, actors involved, contradiction flags, ICD 203 confidence level. Powered by DeepSeek-R1 via Groq with Ollama local fallback.

### SITREP
Auto-generated situation reports every 60 minutes: what happened, why it happened, what to watch next (3 specific watch items with timeframes), forward projection (24h / 72h / 7d), confidence with reasoning. Stored in PostgreSQL, queryable via API.

### Disinformation Detector
Sliding 45-minute window across all sources. Flags coordinated information operations when the same claim appears on 3+ channels simultaneously — cosine similarity clustering, not keyword matching.

### Press Brief Analyzer
Paste any press conference transcript → structured extraction: headline, key claims, threats, military signals, observed facts vs. inference, follow-up recommendations.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Data Sources                          │
│   RSS/News · Telegram · ADSB flights · AIS · Red Alert       │
└─────────────────────────┬────────────────────────────────────┘
                          │  async pollers
┌─────────────────────────▼────────────────────────────────────┐
│                   Backend  (FastAPI)                         │
│  geocoding · classification · confidence scoring · ACLED     │
│  taxonomy · MGRS coords · Bayesian source reliability        │
└──────┬──────────────────┬──────────────────┬─────────────────┘
       │                  │                  │
┌──────▼──────┐   ┌───────▼──────┐   ┌───────▼──────┐
│ PostgreSQL  │   │    Neo4j     │   │    Redis     │
│ events_v2   │   │ Temporal KG  │   │  WebSocket   │
│ ACLED cols  │   │ 760+ nodes   │   │  pub/sub     │
│ AI reports  │   │ causal graph │   │  live feed   │
└─────────────┘   └──────────────┘   └──────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────┐
│                   Reasoning Engine                           │
│   Groq LLM (primary) → Ollama local (auto-fallback on 429)   │
│   SITREP · Intel Trace · Contradiction detection             │
│   Disinformation clustering · Causal chain analysis          │
└─────────────────────────┬────────────────────────────────────┘
                          │  REST + WebSocket
┌─────────────────────────▼────────────────────────────────────┐
│                  Frontend  (Next.js 15)                      │
│  Intel Feed · Live Map · Alerts · SITREP · Graph Explorer    │
│  Priority Panel · Press Brief · Admin · AR/RTL interface     │
└──────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

**Backend**
- Python 3.11 · FastAPI · psycopg3
- Neo4j — temporal knowledge graph (760+ nodes, 6 relationship types, 30-day edge decay)
- PostgreSQL + PostGIS
- Redis — WebSocket pub/sub
- Groq API (DeepSeek-R1 / LLaMA 3) with Ollama local LLM fallback

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
| `/v2/ar/...` | Full Arabic RTL interface mirroring all v2 pages |

---

## Security

- **WebAuthn / Passkey** — hardware key enrollment for admin accounts
- **CSRF protection** on all state-changing endpoints
- `httponly` + `SameSite=Strict` session cookies
- **Role-based route protection** — 34 API endpoints gated
- **Audit log** on all admin actions
- SHA-256 event IDs
- Startup validation — backend refuses to start with weak `AUTH_SECRET` or default credentials
- TOTP (time-based OTP) for analyst and admin roles
- Content-Security-Policy headers

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

Source weights are dynamic — analyst ratings on Intel Trace feed back into per-source reliability scores via Bayesian update.

---

## Analytic Standards

| Standard | Implementation |
|----------|---------------|
| **ICD 203** | 4-level confidence scale (HIGH / MODERATE / LOW / VERY LOW) on all AI products |
| **NATO 2×6** | Source reliability (A–F) + claim credibility (1–6) badge on every event card |
| **ACLED taxonomy** | Full event schema compatibility — `acled_event_type`, `acled_sub_event_type`, `civilian_targeting`, `geo_precision`, `time_precision` |
| **NATO MHC** | Every ranked recommendation shows its reasoning. Analyst suppresses, not the system. |

---

## Research

Built on techniques from 20+ academic and practitioner sources. Peer-reviewed preprint available on Zenodo:

> **OSINT Nexus: A Production-Deployed Multi-Source Intelligence Fusion System with LLM Reasoning and Adaptive Confidence Calibration**
> Rachid Jaada, 2026 — [https://doi.org/10.5281/zenodo.19169143](https://doi.org/10.5281/zenodo.19169143)

Key references: ACLED methodology · NATO HFM-377 · DARPA EMHAT · Endsley (1995) · Flashpoint Ukraine · Recorded Future · Bellingcat

---

## Repository Layout

```
.
├── backend/
│   ├── main.py               # FastAPI app, routes, WebSocket
│   ├── ingestion.py          # Geocoding, classification, event normalization
│   ├── pollers.py            # RSS, Telegram, ADSB, Red Alert, SITREP pollers
│   ├── reasoning_engine.py   # SITREP, causal chain, contradiction detection
│   ├── disinfo_detector.py   # Coordinated info-op signature detection
│   ├── graph_store.py        # Neo4j temporal knowledge graph
│   ├── v2_store.py           # PostgreSQL persistence + ACLED field mapping
│   ├── groq_client.py        # Groq + Ollama LLM client with fallback
│   ├── baseline_monitor.py   # EWMA behavioral anomaly detection per source
│   ├── prediction_tracker.py # Scores SITREP predictions vs reality
│   └── market_poller.py      # Gold, WTI, Brent, DXY, S&P500
├── frontend/
│   └── app/v2/               # Next.js App Router pages
├── k8s/                      # Kubernetes manifests
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
- Research preprint published March 2026

---

## License

[AGPL v3](LICENSE) — free for open use. Commercial deployments require a separate license.

---

<div align="center">

Built by [Rachid Jaada](https://github.com/rjaada)

</div>
