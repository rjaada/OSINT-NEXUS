SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose
MODEL ?= llama3
NS ?= osint

.PHONY: help
help:
	@echo "OSINT NEXUS Make targets"
	@echo ""
	@echo "Docker Compose"
	@echo "  make build           Build backend/frontend images"
	@echo "  make up              Start redis+backend+frontend"
	@echo "  make up-ai           Start ollama + pull model (MODEL=$(MODEL))"
	@echo "  make start           Start existing containers"
	@echo "  make stop            Stop containers"
	@echo "  make down            Stop and remove compose stack"
	@echo "  make restart         Restart compose stack"
	@echo "  make ps              Show compose status"
	@echo "  make logs            Tail all logs"
	@echo "  make logs-backend    Tail backend logs"
	@echo "  make logs-frontend   Tail frontend logs"
	@echo "  make logs-ollama     Tail ollama logs"
	@echo "  make health          Check key HTTP endpoints"
	@echo "  make analyst         Query /api/analyst once"
	@echo ""
	@echo "Kubernetes (Minikube)"
	@echo "  make k8s-start       Start minikube"
	@echo "  make k8s-build       Build images into minikube docker"
	@echo "  make k8s-deploy      Apply k8s manifests"
	@echo "  make k8s-status      Get pods/services in namespace"
	@echo "  make k8s-pf          Port-forward frontend+backend"
	@echo "  make k8s-stop        Stop minikube"
	@echo ""
	@echo "Cleanup"
	@echo "  make clean           Remove local build artifacts (.next, node_modules, pycache)"
	@echo "  make clean-docker    Remove compose stack + project containers/images"

.PHONY: build up up-ai pull-model start stop down restart ps logs logs-backend logs-frontend logs-ollama health analyst
build:
	$(COMPOSE) build backend frontend

up:
	$(COMPOSE) up -d --build redis backend frontend

up-ai:
	$(COMPOSE) up -d ollama
	$(COMPOSE) exec -T ollama ollama pull $(MODEL)

pull-model:
	$(COMPOSE) exec -T ollama ollama pull $(MODEL)

start:
	$(COMPOSE) start

stop:
	$(COMPOSE) stop

down:
	$(COMPOSE) down

restart: down up

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=120

logs-backend:
	$(COMPOSE) logs -f --tail=120 backend

logs-frontend:
	$(COMPOSE) logs -f --tail=120 frontend

logs-ollama:
	$(COMPOSE) logs -f --tail=120 ollama

health:
	@echo "[backend] /api/health"
	@curl -fsS http://127.0.0.1:8000/api/health || true
	@echo "\n[backend] /api/ops/health"
	@curl -fsS http://127.0.0.1:8000/api/ops/health || true
	@echo "\n[frontend] /"
	@curl -fsSI http://127.0.0.1:3000 | head -n 1 || true

analyst:
	@curl -fsS http://127.0.0.1:8000/api/analyst || true
	@echo ""

.PHONY: k8s-start k8s-build k8s-deploy k8s-status k8s-pf k8s-stop
k8s-start:
	minikube start --driver=docker --memory=8192

k8s-build:
	eval $$(minikube docker-env) && docker build -t osint-backend:latest ./backend
	eval $$(minikube docker-env) && docker build -t osint-frontend:latest ./frontend

k8s-deploy:
	kubectl apply -f k8s/00-namespace.yaml \
		-f k8s/01-redis.yaml \
		-f k8s/03-backend.yaml \
		-f k8s/04-frontend.yaml

k8s-status:
	kubectl get pods,svc -n $(NS)

k8s-pf:
	@echo "Starting port-forwards (Ctrl+C to stop)"
	kubectl -n $(NS) port-forward svc/frontend 3000:3000 & \
	kubectl -n $(NS) port-forward svc/backend 8000:8000 & \
	wait

k8s-stop:
	minikube stop

.PHONY: clean clean-docker
clean:
	rm -rf frontend/.next frontend/node_modules
	find backend frontend -type d -name '__pycache__' -prune -exec rm -rf {} +
	find backend frontend -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

clean-docker:
	$(COMPOSE) down --remove-orphans || true
	docker rm -f $$(docker ps -aq --filter name='osint-') >/dev/null 2>&1 || true
	docker rmi -f $$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^osint-(backend|frontend):') >/dev/null 2>&1 || true
