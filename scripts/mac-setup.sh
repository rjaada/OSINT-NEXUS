#!/usr/bin/env bash
# Bring up OSINT Nexus locally on Apple Silicon (Docker Desktop for Mac).
#
# Native Ollama (Metal/MLX accelerated) is used instead of the `ollama`
# container — Docker Desktop for Mac has no GPU passthrough, so a
# containerized Ollama would be CPU-only and much slower.
#
# Safe to re-run: every step checks current state first and skips work
# that's already done. Never overwrites an existing .env.
set -euo pipefail
cd "$(dirname "$0")/.."

log()  { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$1"; exit 1; }

[ "$(uname -s)" = "Darwin" ] || die "This script is for macOS only."
[ "$(uname -m)" = "arm64" ] || warn "Not arm64 — this script assumes Apple Silicon; continuing anyway."

# --- 1. Homebrew + Ollama -----------------------------------------------
command -v brew >/dev/null 2>&1 || die "Homebrew not found. Install it from https://brew.sh first."

if ! command -v ollama >/dev/null 2>&1; then
  log "Installing Ollama..."
  brew install ollama
else
  log "Ollama already installed ($(ollama --version 2>&1 | head -1))."
fi

if ! brew services list | grep -q "^ollama.*started"; then
  log "Starting Ollama service..."
  brew services start ollama
  sleep 2
else
  log "Ollama service already running."
fi

curl -sf http://localhost:11434/api/version >/dev/null || die "Ollama isn't responding on :11434 after start."

# --- 2. .env --------------------------------------------------------------
if [ ! -f .env ]; then
  log "No .env found — creating from .env.example with generated secrets."
  cp .env.example .env
  gen_secret() { openssl rand -base64 32 | tr -d '\n'; }
  gen_pw() { echo "$(openssl rand -hex 6)Aa1!"; }  # satisfies upper/lower/digit/symbol, 10+ chars

  sed -i '' "s#^POSTGRES_PASSWORD=.*#POSTGRES_PASSWORD=$(gen_secret)#" .env
  sed -i '' "s#^NEO4J_PASSWORD=.*#NEO4J_PASSWORD=$(gen_secret)#" .env
  sed -i '' "s#^AUTH_SECRET=.*#AUTH_SECRET=$(gen_secret)#" .env
  sed -i '' "s#^AUTH_DEFAULT_ADMIN_PASSWORD=.*#AUTH_DEFAULT_ADMIN_PASSWORD=$(gen_pw)#" .env
  sed -i '' "s#^AUTH_ADMIN_REQUIRE_PASSKEY=.*#AUTH_ADMIN_REQUIRE_PASSKEY=0#" .env

  read -rp "AISSTREAM_API_KEY (https://aisstream.io) [blank to skip]: " k
  [ -n "${k:-}" ] && sed -i '' "s#^AISSTREAM_API_KEY=.*#AISSTREAM_API_KEY=$k#" .env
  read -rp "FIRMS_MAP_KEY (https://firms.modaps.eosdis.nasa.gov/api/) [blank to skip]: " k
  [ -n "${k:-}" ] && sed -i '' "s#^FIRMS_MAP_KEY=.*#FIRMS_MAP_KEY=$k#" .env

  warn "Generated admin password is in .env under AUTH_DEFAULT_ADMIN_PASSWORD — save it."
else
  log ".env already exists — leaving it untouched."
fi

# Ensure the Ollama-related keys exist even in a pre-existing .env
# (added/renamed by this script's Ollama model choice below).
ensure_env() {
  local key="$1" val="$2"
  if grep -q "^${key}=" .env; then
    sed -i '' "s#^${key}=.*#${key}=${val}#" .env
  else
    printf '%s=%s\n' "$key" "$val" >> .env
  fi
}

# --- 3. Models --------------------------------------------------------------
# Qwen3 8B/4B: stronger structured-JSON + reasoning than Llama 3.1 8B /
# Phi-4-mini at similar VRAM cost, and MLX-accelerated on Apple Silicon.
REPORT_MODEL="${OSINT_REPORT_MODEL:-qwen3:8b}"
VERIFY_MODEL="${OSINT_VERIFY_MODEL:-qwen3:4b}"

for m in "$REPORT_MODEL" "$VERIFY_MODEL"; do
  if ollama list | awk '{print $1}' | grep -qx "$m"; then
    log "Model $m already pulled."
  else
    log "Pulling $m..."
    ollama pull "$m"
  fi
done

ensure_env OLLAMA_MODEL "$REPORT_MODEL"
ensure_env OLLAMA_FALLBACK_MODEL "$REPORT_MODEL"
ensure_env V2_MODEL_REPORT "$REPORT_MODEL"
ensure_env V2_MODEL_VERIFY "$VERIFY_MODEL"
ensure_env V2_MODEL_DEFAULT "$VERIFY_MODEL"
ensure_env OLLAMA_URL "http://host.docker.internal:11434/api/generate"

# --- 4. hooks_local build context -------------------------------------------
if [ ! -d backend/hooks_local ] || [ ! -f backend/hooks_local/Dockerfile ]; then
  if [ -d "$HOME/Downloads/hooks_local" ]; then
    log "backend/hooks_local missing — copying from ~/Downloads/hooks_local."
    cp -R "$HOME/Downloads/hooks_local" backend/hooks_local
  else
    die "backend/hooks_local is missing and ~/Downloads/hooks_local doesn't exist either. media-hooks won't build."
  fi
else
  log "backend/hooks_local present."
fi

# --- 5. docker-compose.override.yml -----------------------------------------
[ -f docker-compose.override.yml ] || die "docker-compose.override.yml missing — expected it to wire OLLAMA_URL to host.docker.internal."

# --- 6. Bring up the stack (native Ollama instead of the container, no landing site) ---
log "Building and starting: postgres redis neo4j backend frontend media-hooks"
docker compose up -d --build postgres redis neo4j backend frontend media-hooks

log "Waiting for backend health check..."
for i in $(seq 1 30); do
  status=$(docker inspect --format='{{.State.Health.Status}}' "$(docker compose ps -q backend)" 2>/dev/null || echo "starting")
  [ "$status" = "healthy" ] && break
  sleep 3
done

if [ "$status" = "healthy" ]; then
  log "Backend healthy."
else
  warn "Backend not healthy after 90s — check: docker compose logs backend"
fi

log "Stack up. Frontend: http://localhost:3000  Backend: http://localhost:8000  Neo4j: http://localhost:7474"
