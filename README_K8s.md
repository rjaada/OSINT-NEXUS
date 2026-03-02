# OSINT NEXUS Kubernetes Guide

This guide covers local Kubernetes deployment and operations for OSINT NEXUS on Minikube.

## What Runs in K8s

In Kubernetes mode, OSINT NEXUS runs as:

- `frontend` (Next.js V2 UI),
- `backend` (FastAPI ingestion + API + auth + AI orchestration),
- `redis` (queue/cache support),
- optional `ollama` deployment (or host Ollama via bridge URL).

## Scope and Manifests

Primary namespace stack is under `k8s/`:

- `k8s/00-namespace.yaml`
- `k8s/01-redis.yaml`
- `k8s/03-backend.yaml`
- `k8s/04-frontend.yaml`

Optional in-cluster Ollama manifest:

- `k8s/02-ollama.yaml`

Alternate/legacy deployment file (do not combine blindly):

- `k8s/deployment.yaml`

Use explicit `-f` lists instead of `kubectl apply -f k8s/` to avoid duplicate resources.

## Prerequisites

- Docker Engine
- Minikube
- kubectl
- Images built into Minikube docker:
  - `osint-backend:latest`
  - `osint-frontend:latest`

Optional AI acceleration:

- NVIDIA GPU + NVIDIA container toolkit

## 1) Start Minikube

```bash
minikube start --driver=docker --memory=8192
```

Fast-path (about 10 minutes after images are built):

1. `make k8s-build`
2. `make k8s-deploy`
3. `make k8s-pf`
4. Open `http://127.0.0.1:3000/login`

## 2) Build Images into Minikube Docker

```bash
eval $(minikube docker-env)
docker build -t osint-backend:latest ./backend
docker build -t osint-frontend:latest ./frontend
```

Or via Make:

```bash
make k8s-build
```

## 3) Deploy Base Stack

```bash
kubectl apply -f k8s/00-namespace.yaml \
  -f k8s/01-redis.yaml \
  -f k8s/03-backend.yaml \
  -f k8s/04-frontend.yaml
```

Or via Make:

```bash
make k8s-deploy
```

## 4) (Optional) Deploy Ollama In-Cluster

```bash
kubectl apply -f k8s/02-ollama.yaml
```

`02-ollama.yaml` requests `nvidia.com/gpu: 1`. If your Minikube node does not expose GPU resources, keep Ollama on host instead (recommended for most local setups).

## 5) Verify

```bash
kubectl get pods,svc -n osint
kubectl rollout status deployment/backend -n osint
kubectl rollout status deployment/frontend -n osint
kubectl rollout status deployment/redis -n osint
```

If using in-cluster Ollama:

```bash
kubectl rollout status deployment/ollama -n osint
```

## 6) Access Services

Use port-forward in separate terminals:

```bash
kubectl -n osint port-forward svc/frontend 3000:3000
kubectl -n osint port-forward svc/backend 8000:8000
```

Or via Make (single command wrapper):

```bash
make k8s-pf
```

Then open:

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`

## Ollama Wiring Options

### Option A: Host Ollama (recommended)

Keep backend config pointed to host bridge:

- `OLLAMA_URL=http://host.minikube.internal:11434/api/generate`

This is already configured in `k8s/03-backend.yaml`.

Start host Ollama:

```bash
docker run -d --name ollama-gpu \
  --restart unless-stopped \
  --gpus all \
  -p 11434:11434 \
  -v "$(pwd)/ollama_data:/root/.ollama" \
  ollama/ollama:latest
```

Pull required models:

```bash
docker exec ollama-gpu ollama pull deepseek-r1:8b
docker exec ollama-gpu ollama pull phi4-mini
docker exec ollama-gpu ollama pull qwen2.5:7b
```

### Option B: In-cluster Ollama service

If you deploy `02-ollama.yaml`, update backend env to use:

- `OLLAMA_URL=http://ollama:11434/api/generate`

and rollout restart backend.

## Current V2 AI Policy (in this project)

V2 scheduler currently uses:

- `verify`: `phi4-mini`
- `report`: `deepseek-r1:8b`

Chat task has been removed from v2 operations.

Runtime behavior:

- model discovery through `/api/tags`
- available model chain selection
- missing models dropped from runtime chain to reduce repeated 404 errors

## Auth and Admin in K8s

Auth endpoints are active in-cluster as in local compose:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/session`

Admin role management endpoints:

- `GET /api/admin/users`
- `PATCH /api/admin/users/{username}/role`
- `DELETE /api/admin/users/{username}`

Frontend admin pages:

- `/v2/admin`
- `/v2/ar/admin`

Access policy:

- V2 is primary (`/` -> `/v2`).
- Any authenticated role can access V2 pages.
- Admin pages remain admin-only.

## Persistence Notes

- Backend auth/local SQLite is persisted via:
  - `OSINT_DB_PATH=/data/osint_nexus.db`
  - `backend-data-pvc` mounted to `/data`
- Backend runs as `replicas: 1` in `k8s/03-backend.yaml` to avoid split auth state when using local SQLite.
- If you scale backend replicas, move auth/local state to a shared datastore (recommended: Postgres for auth tables).

## Operations and Troubleshooting

Logs:

```bash
kubectl logs -n osint deploy/backend --tail=200
kubectl logs -n osint deploy/frontend --tail=200
```

Health checks:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/ops/health
curl http://127.0.0.1:8000/api/v2/ai/policy
```

Common issue: local ports busy (`3000`, `8000`)

- Stop local compose stack before `make k8s-pf`
- Or use alternative local ports in manual port-forward commands

## Rebuild and Rollout After Code Changes

Backend:

```bash
eval $(minikube docker-env)
docker build -t osint-backend:latest ./backend
kubectl rollout restart deployment/backend -n osint
kubectl rollout status deployment/backend -n osint
```

Frontend:

```bash
eval $(minikube docker-env)
docker build -t osint-frontend:latest ./frontend
kubectl rollout restart deployment/frontend -n osint
kubectl rollout status deployment/frontend -n osint
```

## Full Shutdown / Cleanup

Stop port-forwards:

```bash
pkill -f "kubectl -n osint port-forward" || true
```

Delete namespace:

```bash
kubectl delete namespace osint
```

Stop Minikube:

```bash
minikube stop
```

Full reset:

```bash
minikube delete --all --purge
```
