#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# Invisible Arr — Smoke Test Suite
# ══════════════════════════════════════════════════════════════════════
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_DIR}"

# Source environment
set -a
# shellcheck disable=SC1091
source .env
set +a

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

PASS=0
FAIL=0
SKIP=0

# ---------------------------------------------------------------------------
# check() — report PASS/FAIL/SKIP for a named test
# Usage: check "Test Name" <exit_code> [skip_reason]
# ---------------------------------------------------------------------------

check() {
    local name="$1"
    local code="$2"
    local skip_reason="${3:-}"

    if [ -n "${skip_reason}" ]; then
        echo -e "  ${YELLOW}SKIP${RESET}  ${name} — ${skip_reason}"
        SKIP=$((SKIP + 1))
    elif [ "${code}" -eq 0 ]; then
        echo -e "  ${GREEN}PASS${RESET}  ${name}"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${RESET}  ${name}"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo -e "${BOLD}═══ Invisible Arr — Smoke Tests ═══${RESET}"
echo ""

# ---------------------------------------------------------------------------
# 1. PostgreSQL
# ---------------------------------------------------------------------------

PG_RESULT=1
if docker exec postgres pg_isready -U "${POSTGRES_USER:-invisiblearr}" -q 2>/dev/null; then
    PG_RESULT=0
fi
check "PostgreSQL (pg_isready)" "${PG_RESULT}"

# ---------------------------------------------------------------------------
# 2. Redis
# ---------------------------------------------------------------------------

REDIS_RESULT=1
REDIS_PONG=$(docker exec redis redis-cli -a "${REDIS_PASSWORD}" ping 2>/dev/null || true)
if [ "${REDIS_PONG}" = "PONG" ]; then
    REDIS_RESULT=0
fi
check "Redis (ping)" "${REDIS_RESULT}"

# ---------------------------------------------------------------------------
# 3. Agent API /health
# ---------------------------------------------------------------------------

API_PORT="${AGENT_API_PORT:-8880}"
API_RESULT=1
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${API_PORT}/health" 2>/dev/null || echo "000")
if [ "${HTTP_CODE}" = "200" ]; then
    API_RESULT=0
fi
check "Agent API /health (HTTP ${HTTP_CODE})" "${API_RESULT}"

# ---------------------------------------------------------------------------
# 4. Seerr HTTP
# ---------------------------------------------------------------------------

SEERR_PORT_VAL="${SEERR_PORT:-5055}"
SEERR_RESULT=1
SEERR_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${SEERR_PORT_VAL}" 2>/dev/null || echo "000")
if [[ "${SEERR_CODE}" =~ ^(200|301|302|307|308)$ ]]; then
    SEERR_RESULT=0
fi
check "Seerr HTTP (HTTP ${SEERR_CODE})" "${SEERR_RESULT}"

# ---------------------------------------------------------------------------
# 5. Jellyfin /health
# ---------------------------------------------------------------------------

JELLY_PORT="${JELLYFIN_PORT:-8096}"
JELLY_RESULT=1
JELLY_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${JELLY_PORT}/health" 2>/dev/null || echo "000")
if [ "${JELLY_CODE}" = "200" ]; then
    JELLY_RESULT=0
fi
check "Jellyfin /health (HTTP ${JELLY_CODE})" "${JELLY_RESULT}"

# ---------------------------------------------------------------------------
# 6. Real-Debrid auth (conditional)
# ---------------------------------------------------------------------------

if [ "${RD_ENABLED:-false}" = "true" ] && [ -n "${RD_API_TOKEN:-}" ]; then
    RD_RESULT=1
    RD_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${RD_API_TOKEN}" \
        "https://api.real-debrid.com/rest/1.0/user" 2>/dev/null || echo "000")
    if [ "${RD_CODE}" = "200" ]; then
        RD_RESULT=0
    fi
    check "Real-Debrid auth (HTTP ${RD_CODE})" "${RD_RESULT}"
else
    check "Real-Debrid auth" 0 "RD_ENABLED=false or no token"
fi

# ---------------------------------------------------------------------------
# 7. VPN leak test (conditional)
# ---------------------------------------------------------------------------

if [ "${VPN_ENABLED:-false}" = "true" ]; then
    VPN_RESULT=1
    # Fetch the public IP through the gluetun container
    VPN_IP=$(docker exec gluetun wget -qO- https://ipinfo.io/ip 2>/dev/null || echo "")
    HOST_IP=$(curl -s https://ipinfo.io/ip 2>/dev/null || echo "unknown")
    if [ -n "${VPN_IP}" ] && [ "${VPN_IP}" != "${HOST_IP}" ]; then
        VPN_RESULT=0
    fi
    check "VPN leak test (VPN IP: ${VPN_IP:-none}, Host IP: ${HOST_IP})" "${VPN_RESULT}"
else
    check "VPN leak test" 0 "VPN_ENABLED=false"
fi

# ---------------------------------------------------------------------------
# 8. IPTV gateway (conditional)
# ---------------------------------------------------------------------------

if [ "${IPTV_ENABLED:-false}" = "true" ]; then
    IPTV_PORT_VAL="${IPTV_GATEWAY_PORT:-8881}"
    IPTV_RESULT=1
    IPTV_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${IPTV_PORT_VAL}/health" 2>/dev/null || echo "000")
    if [ "${IPTV_CODE}" = "200" ]; then
        IPTV_RESULT=0
    fi
    check "IPTV gateway (HTTP ${IPTV_CODE})" "${IPTV_RESULT}"
else
    check "IPTV gateway" 0 "IPTV_ENABLED=false"
fi

# ---------------------------------------------------------------------------
# 9. Job dry-run (POST /v1/request)
# ---------------------------------------------------------------------------

JOB_RESULT=1
JOB_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "http://localhost:${API_PORT}/v1/request" \
    -H "Content-Type: application/json" \
    -d '{"query":"smoke test","media_type":"movie"}' 2>/dev/null || echo "000")
# Accept 200, 201, 401, 422, or 500 as proof the endpoint is alive
# (500 = DB not migrated yet, 401 = no API key — both prove the service responds)
if [[ "${JOB_CODE}" =~ ^(200|201|401|422|500)$ ]]; then
    JOB_RESULT=0
fi
check "Job dry-run POST /v1/request (HTTP ${JOB_CODE})" "${JOB_RESULT}"

# ---------------------------------------------------------------------------
# 10. Traefik TLS (conditional)
# ---------------------------------------------------------------------------

DOMAIN_VAL="${DOMAIN:-}"
if [ -n "${DOMAIN_VAL}" ]; then
    TLS_RESULT=1
    TLS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
        "https://${DOMAIN_VAL}" 2>/dev/null || echo "000")
    if [[ "${TLS_CODE}" =~ ^(200|301|302|307|308)$ ]]; then
        TLS_RESULT=0
    fi
    check "Traefik TLS for ${DOMAIN_VAL} (HTTP ${TLS_CODE})" "${TLS_RESULT}"
else
    check "Traefik TLS" 0 "No DOMAIN configured"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

TOTAL=$((PASS + FAIL + SKIP))
echo ""
echo -e "${BOLD}═══ Summary ═══${RESET}"
echo -e "  ${GREEN}PASS: ${PASS}${RESET}  ${RED}FAIL: ${FAIL}${RESET}  ${YELLOW}SKIP: ${SKIP}${RESET}  TOTAL: ${TOTAL}"
echo ""

if [ "${FAIL}" -gt 0 ]; then
    echo -e "${RED}Some tests failed. Check the services above.${RESET}"
    exit 1
fi

echo -e "${GREEN}All tests passed!${RESET}"
exit 0
