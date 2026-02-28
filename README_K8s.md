# Kubernetes Deployment Guide (Minikube)

This document covers local Kubernetes deployment for OSINT NEXUS using Minikube.

## Documentation

- Project overview, architecture, and non-Kubernetes usage: [README.md](README.md)

## Scope

Use the `osint` namespace manifests only:

- `k8s/00-namespace.yaml`
- `k8s/01-redis.yaml`
- `k8s/03-backend.yaml`
- `k8s/04-frontend.yaml`

Avoid applying all files in `k8s/` with a wildcard, because `k8s/deployment.yaml` deploys an alternate stack (`osint-nexus`) and can cause duplicate resources.

## Prerequisites

- Docker Engine
- Minikube
- kubectl
- Built images:
  - `osint-backend:latest`
  - `osint-frontend:latest`

## 1. Start Minikube

```bash
minikube start --driver=docker --gpus all --memory=8192
```

## 2. Build and Load Images

Build locally:

```bash
docker build ./backend -t osint-backend:latest
docker build ./frontend -t osint-frontend:latest
```

Load into Minikube image cache:

```bash
minikube image load osint-backend:latest
minikube image load osint-frontend:latest
```

## 3. Deploy the Kubernetes Resources

```bash
kubectl apply -f k8s/00-namespace.yaml \
  -f k8s/01-redis.yaml \
  -f k8s/03-backend.yaml \
  -f k8s/04-frontend.yaml
```

## 4. Verify Status

```bash
kubectl get pods -n osint -w
```

Expected:

- `frontend`, `backend`, `redis` in `Running`
- `ollama` is not required in this flow unless you explicitly deploy `k8s/02-ollama.yaml`

## 5. Access the Application

Recommended for local development:

```bash
kubectl port-forward -n osint svc/frontend 3000:3000
kubectl port-forward -n osint svc/backend 8000:8000
```

Open:

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`

Alternative NodePort access:

```bash
minikube ip
kubectl get svc -n osint
```

Then open `http://<MINIKUBE_IP>:30000`.

## Ollama and GPU Notes

### Current recommended local mode

Run Ollama on host Docker with GPU and let backend in Kubernetes call it via:

`OLLAMA_URL=http://host.minikube.internal:11434/api/generate`

Start host Ollama:

```bash
docker run -d --name ollama-gpu \
  --restart unless-stopped \
  --gpus all \
  -p 11434:11434 \
  -v "$(pwd)/ollama_data:/root/.ollama" \
  ollama/ollama:latest
```

Pull model:

```bash
docker exec ollama-gpu ollama pull llama3
```

### In-cluster Ollama GPU

If you deploy `k8s/02-ollama.yaml`, pod scheduling requires `nvidia.com/gpu` to be available in node allocatable resources. If missing, the pod remains `Pending`.

## Common Operations

Restart deployment after image reload:

```bash
kubectl rollout restart deployment/backend -n osint
kubectl rollout restart deployment/frontend -n osint
```

Watch rollout:

```bash
kubectl rollout status deployment/backend -n osint
kubectl rollout status deployment/frontend -n osint
```

Check logs:

```bash
kubectl logs -n osint deploy/backend --tail=200
kubectl logs -n osint deploy/frontend --tail=200
```

## Full Reset

```bash
kubectl delete namespace osint
minikube delete --all --purge
```
