#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# Invisible Arr — Edge Node Installer
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
else
    info ".env already exists, skipping generation."
fi

# Source current values so we can use defaults in prompts
set -a
# shellcheck disable=SC1091
source .env
set +a

# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

echo ""
echo -e "${BOLD}═══ Invisible Arr Setup ═══${RESET}"
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

info "Building and starting services..."

if [ -n "${PROFILES}" ]; then
    COMPOSE_PROFILES="${PROFILES}" docker compose build
    COMPOSE_PROFILES="${PROFILES}" docker compose up -d
else
    docker compose build
    docker compose up -d
fi

# ---------------------------------------------------------------------------
# Print access URLs
# ---------------------------------------------------------------------------

echo ""
echo -e "${BOLD}═══ Invisible Arr is running! ═══${RESET}"
echo ""

DOMAIN_VAL=$(grep '^DOMAIN=' .env | cut -d'=' -f2)
if [ -n "${DOMAIN_VAL}" ]; then
    BASE="https://${DOMAIN_VAL}"
else
    BASE="http://localhost"
fi

JELLYFIN_PORT_VAL=$(grep '^JELLYFIN_PORT=' .env | cut -d'=' -f2)
SEERR_PORT_VAL=$(grep '^SEERR_PORT=' .env | cut -d'=' -f2)
API_PORT_VAL=$(grep '^AGENT_API_PORT=' .env | cut -d'=' -f2)

info "Access URLs:"
echo "  Jellyfin:   http://localhost:${JELLYFIN_PORT_VAL:-8096}"
echo "  Seerr:      http://localhost:${SEERR_PORT_VAL:-5055}"
echo "  Agent API:  http://localhost:${API_PORT_VAL:-8880}"
echo "  Health:     http://localhost:${API_PORT_VAL:-8880}/health"

if [ -n "${DOMAIN_VAL}" ]; then
    echo ""
    echo "  With domain (after DNS propagation):"
    echo "  Jellyfin:   ${BASE}/jellyfin"
    echo "  Seerr:      ${BASE}"
    echo "  Agent API:  ${BASE}/api"
fi

if [ "${VPN_ENABLED}" = "true" ]; then
    QB_PORT=$(grep '^QBITTORRENT_PORT=' .env | cut -d'=' -f2)
    echo "  qBittorrent: http://localhost:${QB_PORT:-8080}"
fi

if [ "${IPTV_ENABLED}" = "true" ]; then
    IPTV_PORT=$(grep '^IPTV_GATEWAY_PORT=' .env | cut -d'=' -f2)
    echo "  IPTV Gateway: http://localhost:${IPTV_PORT:-8881}"
fi

echo ""
info "Run './scripts/smoke.sh' to verify all services are healthy."
echo ""
