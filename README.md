# OSINT NEXUS

OSINT NEXUS is a real-time OSINT monitoring platform for conflict-driven situational awareness. It ingests open feeds, geolocates events, computes confidence, and presents a live operations interface with separate mission pages.

## What This Project Does

- Aggregates live signals from:
  - Telegram channels (currently `AJ Mubasher (TG)` and `Roaa War Studies (TG)`)
  - RSS sources (Reuters, Al Jazeera, BBC, CBS, The Guardian, Times of Israel)
  - FlightRadar24 military-relevant aircraft feed
  - Red Alert feed (when reachable)
- Generates event confidence using source reliability + cross-source corroboration
- Performs geolocation with fallback logic (place match, geocoder, AI/fallback)
- Downloads Telegram video media when available and links it to events
- Streams data to frontend over WebSocket for live operations

## Current UI Structure

The frontend now supports versioned workspaces:

- `v1` (stable, default): `http://localhost:3000/`
- `v2` (beta): `http://localhost:3000/v2`

Both include mission pages:

- Hub
- Operations
- Alerts
- Sources

A version switch button is available in navigation:

- `Switch to V2 Beta` from v1
- `Switch to V1 Stable` from v2

## Architecture

- `frontend/`: Next.js app router UI
- `backend/`: FastAPI ingestion and analytics engine
- `k8s/`: Kubernetes manifests for local Minikube deployment
- `docker-compose.yml`: local Compose stack

## Key Backend Capabilities

- Persistent event storage in SQLite (`/tmp/osint_nexus.db` by default)
- Incident deduplication and incident threading
- Confidence scoring with explainable reason text
- Guardrailed analyst output with insufficient-evidence mode
- Source health, watchdog warnings, and operations metrics APIs

## Main API Endpoints

- `GET /api/health`
- `GET /api/ops/health`
- `GET /api/stats`
- `GET /api/events`
- `GET /api/alerts/assessment`
- `GET /api/sources/recent`
- `GET /api/analyst`
- `WS /ws/live`

## Prerequisites

- Docker Engine
- Docker Compose
- Node.js 20+ (for direct frontend dev)
- Python 3.11+ (for direct backend dev)
- Minikube + kubectl (for Kubernetes mode)
- Optional NVIDIA GPU + NVIDIA Container Toolkit for Ollama acceleration

## Environment Variables (Backend)

Core variables:

- `OLLAMA_URL` (default: `http://ollama:11434/api/generate`)
- `OLLAMA_MODEL` (default: `llama3`)
- `OSINT_DB_PATH` (default: `/tmp/osint_nexus.db`)
- `MEDIA_DIR` (default: `/tmp/osint_nexus_media`)

Telegram/video tuning:

- `DOWNLOAD_TELEGRAM_MEDIA` (default: `true`)
- `TELEGRAM_LOOKBACK_POSTS` (default: `20`)
- `TELEGRAM_MAX_NEW_PER_POLL` (default: `8`)

## Local Run (Docker Compose)

Start:

```bash
docker compose up --build
```

Or use the `Makefile` shortcuts:

```bash
make up
make up-ai
make health
```

Open:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

Stop:

```bash
docker compose down
```

Useful operational targets:

- `make ps`
- `make logs`
- `make logs-backend`
- `make analyst`
- `make down`

## Kubernetes Run (Minikube)

For Kubernetes setup and operations, see:

- [README_K8s.md](README_K8s.md)

## Ollama (GPU on Host)

Recommended local mode with Kubernetes backend:

1. Run Ollama on host Docker with GPU.
2. Point backend to `http://host.minikube.internal:11434/api/generate`.

Example:

```bash
docker run -d --name ollama-gpu \
  --restart unless-stopped \
  --gpus all \
  -p 11434:11434 \
  -v "$(pwd)/ollama_data:/root/.ollama" \
  ollama/ollama:latest

docker exec ollama-gpu ollama pull llama3
```

## Security and Usage Notes

- This system is an OSINT aid, not an authoritative command system.
- Treat model inference as advisory.
- Always validate critical claims with official sources.
- Do not commit secrets, private keys, or credentials.

## Repository Layout

```text
.
├── backend/
├── frontend/
├── k8s/
├── docker-compose.yml
├── README.md
└── README_K8s.md
```
