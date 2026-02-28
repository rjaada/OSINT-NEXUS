# OSINT NEXUS

OSINT NEXUS is a real-time intelligence dashboard that aggregates open-source signals (air traffic, conflict-related news, and alert feeds), geolocates events, and produces AI-generated situational summaries.

## Documentation

- Kubernetes-specific deployment and operations: [README_K8s.md](README_K8s.md)

## Overview

The platform consists of:

- **Backend**: FastAPI service that ingests, normalizes, and streams events.
- **Frontend**: Next.js dashboard with live map visualization and analyst panel.
- **AI Layer**: Ollama-hosted local model (`llama3`) for geolocation and tactical summaries.
- **Infra**: Docker Compose and Kubernetes manifests for local deployment.

## Key Capabilities

- Real-time aircraft tracking (FlightRadar24 feed in a defined Middle East bounding box).
- RSS-based conflict event extraction from major news sources.
- Israel Home Front Command Red Alert ingestion and mapping.
- WebSocket streaming for live event updates.
- Map-based operational view (MapLibre) with:
  - Event markers
  - Threat radius overlays
  - Heatmap density
  - Conflict zone polygons
- AI analyst summaries with threat-level classification.

## Repository Structure

```text
.
├── backend/                 # FastAPI ingest + API + websocket
├── frontend/                # Next.js dashboard
├── k8s/                     # Kubernetes manifests
├── docker-compose.yml       # Compose stack
├── README.md
└── README_K8s.md
```

## Prerequisites

- Docker Engine
- Docker Compose
- Node.js 20+ (for local frontend build/dev)
- Python 3.11+ (for local backend development)
- Minikube + kubectl (for Kubernetes deployment)
- NVIDIA GPU + NVIDIA Container Toolkit (for Ollama GPU acceleration)

## Environment Variables

### Backend

- `OLLAMA_MODEL` (default: `llama3`)
- `OLLAMA_URL` (default: `http://ollama:11434/api/generate`)
- `REDIS_URL` (default: `redis://redis:6379`)
- `GROQ_API_KEY` (optional; do not hardcode in source)

### Frontend

- `NEXT_PUBLIC_WS_URL` (example: `ws://localhost:8000`)

## Local Run with Docker Compose

1. Build and start:

```bash
docker compose up --build
```

2. Open:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`

3. Stop:

```bash
docker compose down
```

## Kubernetes Deployment (Minikube)

Use the scoped `osint` manifests:

```bash
kubectl apply -f k8s/00-namespace.yaml \
  -f k8s/01-redis.yaml \
  -f k8s/03-backend.yaml \
  -f k8s/04-frontend.yaml
```

For standard access in local development:

```bash
kubectl port-forward -n osint svc/frontend 3000:3000
kubectl port-forward -n osint svc/backend 8000:8000
```

Then open:

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`

## Ollama on GPU

In environments where in-cluster GPU scheduling is unavailable, run Ollama on host Docker with GPU and point backend to host endpoint:

```bash
docker run -d --name ollama-gpu \
  --restart unless-stopped \
  --gpus all \
  -p 11434:11434 \
  -v "$(pwd)/ollama_data:/root/.ollama" \
  ollama/ollama:latest
```

Pull and verify model:

```bash
docker exec ollama-gpu ollama pull llama3
docker exec ollama-gpu ollama list
```

Current Kubernetes backend config uses:

```text
OLLAMA_URL=http://host.minikube.internal:11434/api/generate
```

## API Endpoints

- `GET /` - service status
- `GET /api/health` - health check
- `GET /api/stats` - dashboard counters
- `GET /api/events` - recent events
- `GET /api/analyst` - generated AI briefing
- `WS /ws/live` - live event and aircraft stream

## Security Notes

- Never commit real API keys, SSH private keys, or model credentials.
- Prefer environment variables and secret stores for sensitive values.
- Review `docker-compose.yml`, `.env`, and Kubernetes secrets before sharing.

## Troubleshooting

- **Frontend client-side crash**:
  - Hard refresh browser (`Ctrl+Shift+R`).
  - Confirm backend reachable on `http://127.0.0.1:8000/api/health`.
- **AI analyst shows offline**:
  - Verify Ollama container is running and reachable on port `11434`.
  - Check backend `OLLAMA_URL` and `OLLAMA_MODEL`.
- **Kubernetes image mismatch**:
  - Rebuild image, load into minikube, restart deployment:
    - `docker build ...`
    - `minikube image load ...`
    - `kubectl rollout restart deployment/<name> -n osint`

## Development Notes

- `k8s/deployment.yaml` and `k8s/00-04*.yaml` represent different deployment styles; for local iteration, use `00-04` manifests to avoid duplicate namespaces and services.
- The frontend build currently ignores type and lint failures (`frontend/next.config.mjs`). Tighten this for production CI.
