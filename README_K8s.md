# OSINT NEXUS Kubernetes Guide

This guide covers local Kubernetes deployment and operations for OSINT NEXUS on Minikube.

## Scope

Use the `osint` namespace manifests for the active stack:

- `k8s/00-namespace.yaml`
- `k8s/01-redis.yaml`
- `k8s/03-backend.yaml`
- `k8s/04-frontend.yaml`

Do not apply all files with `kubectl apply -f k8s/` because `k8s/deployment.yaml` is an alternate deployment style and can create duplicates.

## Prerequisites

- Docker Engine
- Minikube
- kubectl
- Built images:
  - `osint-backend:latest`
  - `osint-frontend:latest`

Optional for local AI:

- Host Ollama container (recommended)
- NVIDIA GPU + NVIDIA Container Toolkit for GPU inference

## 1. Start Minikube

```bash
minikube start --driver=docker --memory=8192
```

If you need GPU scheduling in-cluster, your Minikube/node setup must expose `nvidia.com/gpu`.

## 2. Build Images Into Minikube Docker

```bash
eval $(minikube docker-env)
docker build -t osint-backend:latest ./backend
docker build -t osint-frontend:latest ./frontend
```

## 3. Deploy

```bash
kubectl apply -f k8s/00-namespace.yaml \
  -f k8s/01-redis.yaml \
  -f k8s/03-backend.yaml \
  -f k8s/04-frontend.yaml
```

## 4. Verify

```bash
kubectl get pods,svc -n osint
kubectl rollout status deployment/backend -n osint
kubectl rollout status deployment/frontend -n osint
kubectl rollout status deployment/redis -n osint
```

## 5. Access Services (Port Forward)

```bash
kubectl -n osint port-forward svc/frontend 3000:3000
kubectl -n osint port-forward svc/backend 8000:8000
```

Then open:

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`

## Ollama Integration (Recommended)

Run Ollama on host Docker and let backend call it via host bridge.

Backend config (already set in `k8s/03-backend.yaml`):

- `OLLAMA_URL=http://host.minikube.internal:11434/api/generate`
- `OLLAMA_MODEL=llama3`

Start host Ollama:

```bash
docker run -d --name ollama-gpu \
  --restart unless-stopped \
  --gpus all \
  -p 11434:11434 \
  -v "$(pwd)/ollama_data:/root/.ollama" \
  ollama/ollama:latest

docker exec ollama-gpu ollama pull llama3
```

## Common Operations

Restart after backend/frontend code changes:

```bash
eval $(minikube docker-env)
docker build -t osint-backend:latest ./backend
kubectl rollout restart deployment/backend -n osint
kubectl rollout status deployment/backend -n osint
```

```bash
eval $(minikube docker-env)
docker build -t osint-frontend:latest ./frontend
kubectl rollout restart deployment/frontend -n osint
kubectl rollout status deployment/frontend -n osint
```

Logs:

```bash
kubectl logs -n osint deploy/backend --tail=200
kubectl logs -n osint deploy/frontend --tail=200
```

Health checks:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/ops/health
```

## Full Shutdown and Cleanup

Stop port-forwards:

```bash
pkill -f "kubectl -n osint port-forward" || true
```

Remove active namespace:

```bash
kubectl delete namespace osint
```

Stop Minikube:

```bash
minikube stop
```

If needed, fully reset Minikube:

```bash
minikube delete --all --purge
```
