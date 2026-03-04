#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# CutDaCord.app — Edge Node Installer
# ══════════════════════════════════════════════════════════════════════
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()  { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error() { echo -e "${RED}[ERROR]${RESET} $*"; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if ! command -v docker &>/dev/null; then
    error "Docker is not installed. Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker compose version &>/dev/null; then
    error "Docker Compose v2 is required but not found."
    error "Install it via: https://docs.docker.com/compose/install/"
    exit 1
fi

COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || echo "0.0.0")
info "Docker Compose version: ${COMPOSE_VERSION}"

# ---------------------------------------------------------------------------
# .env setup
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_DIR}"

if [ ! -f .env ]; then
    if [ ! -f .env.template ]; then
        error ".env.template not found in ${PROJECT_DIR}. Aborting."
        exit 1
    fi

    info "Creating .env from template..."
    cp .env.template .env

    # Generate a random Postgres password
    PG_PASS=$(openssl rand -hex 16)
    sed -i "s/POSTGRES_PASSWORD=CHANGEME_GENERATE_THIS/POSTGRES_PASSWORD=${PG_PASS}/" .env
    info "Generated random Postgres password."

    # Generate a random Redis password
    REDIS_PASS=$(openssl rand -hex 16)
    sed -i "s/REDIS_PASSWORD=CHANGEME_GENERATE_THIS/REDIS_PASSWORD=${REDIS_PASS}/" .env
    info "Generated random Redis password."
else
    info ".env already exists, skipping generation."
fi

# Source current values so we can use defaults in prompts
set -a
# shellcheck disable=SC1091
source .env
set +a

# ---------------------------------------------------------------------------
# Detect Docker API version and write to .env
# ---------------------------------------------------------------------------

DETECTED_API_VERSION=$(docker version --format '{{.Server.APIVersion}}' 2>/dev/null || echo "1.44")
info "Detected Docker API version: ${DETECTED_API_VERSION}"
if grep -q '^DOCKER_API_VERSION=' .env; then
    sed -i "s|^DOCKER_API_VERSION=.*|DOCKER_API_VERSION=${DETECTED_API_VERSION}|" .env
else
    echo "DOCKER_API_VERSION=${DETECTED_API_VERSION}" >> .env
fi

# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

echo ""
echo -e "${BOLD}═══ CutDaCord.app Setup ═══${RESET}"
echo ""

# TMDB API Key (required)
read -rp "TMDB API Key (required, get one at https://www.themoviedb.org/settings/api): " TMDB_INPUT
if [ -z "${TMDB_INPUT}" ]; then
    error "TMDB API Key is required. Aborting."
    exit 1
fi
sed -i "s|^TMDB_API_KEY=.*|TMDB_API_KEY=${TMDB_INPUT}|" .env

# Real-Debrid token (optional)
read -rp "Real-Debrid API Token (optional, press Enter to skip): " RD_INPUT
if [ -n "${RD_INPUT}" ]; then
    sed -i "s|^RD_API_TOKEN=.*|RD_API_TOKEN=${RD_INPUT}|" .env
    sed -i "s|^RD_ENABLED=.*|RD_ENABLED=true|" .env
    info "Real-Debrid enabled."
fi

# Domain (optional)
read -rp "Domain for HTTPS (optional, e.g., media.example.com, press Enter to skip): " DOMAIN_INPUT
if [ -n "${DOMAIN_INPUT}" ]; then
    sed -i "s|^DOMAIN=.*|DOMAIN=${DOMAIN_INPUT}|" .env
    read -rp "  ACME/Let's Encrypt email: " ACME_INPUT
    if [ -n "${ACME_INPUT}" ]; then
        sed -i "s|^ACME_EMAIL=.*|ACME_EMAIL=${ACME_INPUT}|" .env
    fi
    info "Domain set to ${DOMAIN_INPUT}."
fi

# VPN (optional)
read -rp "Enable VPN? (y/N): " VPN_INPUT
VPN_ENABLED="false"
if [[ "${VPN_INPUT}" =~ ^[Yy] ]]; then
    VPN_ENABLED="true"
    sed -i "s|^VPN_ENABLED=.*|VPN_ENABLED=true|" .env
    read -rp "  VPN Provider (e.g., mullvad, nordvpn, protonvpn): " VPN_PROV
    if [ -n "${VPN_PROV}" ]; then
        sed -i "s|^VPN_PROVIDER=.*|VPN_PROVIDER=${VPN_PROV}|" .env
    fi
    info "VPN enabled with provider: ${VPN_PROV:-mullvad}."
fi

# IPTV (optional)
read -rp "Enable IPTV gateway? (y/N): " IPTV_INPUT
IPTV_ENABLED="false"
if [[ "${IPTV_INPUT}" =~ ^[Yy] ]]; then
    IPTV_ENABLED="true"
    sed -i "s|^IPTV_ENABLED=.*|IPTV_ENABLED=true|" .env
    info "IPTV gateway enabled."
fi

# ---------------------------------------------------------------------------
# Create directory structure
# ---------------------------------------------------------------------------

info "Creating directory structure..."

CONFIG_DIRS=(
    config/traefik
    config/jellyfin
    config/seerr
    config/sonarr
    config/radarr
    config/prowlarr
    config/qbittorrent
)

DATA_DIRS=(
    data/media/Movies
    data/media/TV
    data/downloads/rd
)

for dir in "${CONFIG_DIRS[@]}" "${DATA_DIRS[@]}"; do
    mkdir -p "${dir}"
done

info "Directories created."

# Traefik requires acme.json to exist with strict permissions before starting
if [ ! -f config/traefik/acme.json ]; then
    touch config/traefik/acme.json
    chmod 600 config/traefik/acme.json
    info "Created config/traefik/acme.json with permissions 600."
else
    chmod 600 config/traefik/acme.json
    info "config/traefik/acme.json already exists, ensured permissions 600."
fi

# ---------------------------------------------------------------------------
# Build COMPOSE_PROFILES and start
# ---------------------------------------------------------------------------

PROFILES=""
if [ "${VPN_ENABLED}" = "true" ]; then
    PROFILES="vpn"
fi
if [ "${IPTV_ENABLED}" = "true" ]; then
    if [ -n "${PROFILES}" ]; then
        PROFILES="${PROFILES},iptv"
    else
        PROFILES="iptv"
    fi
fi
if [ "${USENET_ENABLED:-false}" = "true" ]; then
    if [ -n "${PROFILES}" ]; then
        PROFILES="${PROFILES},usenet"
    else
        PROFILES="usenet"
    fi
fi

info "Building and starting services..."

if [ -n "${PROFILES}" ]; then
    COMPOSE_PROFILES="${PROFILES}" docker compose build
    COMPOSE_PROFILES="${PROFILES}" docker compose up -d
else
    docker compose build
    docker compose up -d
fi

# ---------------------------------------------------------------------------
# Wait for core services to be healthy
# ---------------------------------------------------------------------------

info "Waiting for core services to become healthy..."

wait_healthy() {
    local container="$1"
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "missing")
        if [ "$status" = "healthy" ]; then
            info "${container} is healthy."
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    warn "${container} did not become healthy after $((max_attempts * 2))s. Check: docker logs ${container}"
    return 1
}

wait_healthy postgres || true
wait_healthy redis || true

# ---------------------------------------------------------------------------
# Print access URLs
# ---------------------------------------------------------------------------

echo ""
echo -e "${BOLD}═══ CutDaCord.app is running! ═══${RESET}"
echo ""

DOMAIN_VAL=$(grep '^DOMAIN=' .env | cut -d'=' -f2)
if [ -n "${DOMAIN_VAL}" ]; then
    BASE="https://${DOMAIN_VAL}"
else
    BASE="http://localhost"
fi

# Re-source .env to pick up all generated values
set -a
# shellcheck disable=SC1091
source .env
set +a

JELLYFIN_PORT_VAL="${JELLYFIN_PORT:-8096}"
SEERR_PORT_VAL="${SEERR_PORT:-5055}"
API_PORT_VAL="${AGENT_API_PORT:-8880}"

info "Access URLs:"
echo "  Jellyfin:   http://localhost:${JELLYFIN_PORT_VAL}"
echo "  Seerr:      http://localhost:${SEERR_PORT_VAL}"
echo "  Agent API:  http://localhost:${API_PORT_VAL}"
echo "  Health:     http://localhost:${API_PORT_VAL}/health"

if [ -n "${DOMAIN_VAL}" ]; then
    echo ""
    echo "  With domain (after DNS propagation):"
    echo "  Jellyfin:   ${BASE}/jellyfin"
    echo "  Seerr:      ${BASE}"
    echo "  Agent API:  ${BASE}/api"
fi

if [ "${VPN_ENABLED}" = "true" ]; then
    QB_PORT="${QBITTORRENT_PORT:-8080}"
    echo "  qBittorrent: http://localhost:${QB_PORT}"
fi

if [ "${USENET_ENABLED:-false}" = "true" ]; then
    SAB_PORT="${SABNZBD_PORT:-8081}"
    echo "  SABnzbd:     http://localhost:${SAB_PORT}"
fi

if [ "${IPTV_ENABLED}" = "true" ]; then
    IPTV_PORT="${IPTV_GATEWAY_PORT:-8881}"
    echo "  IPTV Gateway: http://localhost:${IPTV_PORT}"
fi

echo ""
info "Run './scripts/smoke.sh' to verify all services are healthy."
echo ""
