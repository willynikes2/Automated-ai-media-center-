#!/usr/bin/env bash
# Smoke test: Radarr -> rdt-client -> Real-Debrid pipeline
# Tests each link in the chain independently, then end-to-end.
# Run from edge-node directory: ./scripts/smoke-test-rd-pipeline.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS=0
FAIL=0

pass() { echo -e "${GREEN}[PASS]${NC} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "${RED}[FAIL]${NC} $1"; FAIL=$((FAIL + 1)); }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

# Load env
if [ -f .env ]; then
  set -a; source .env; set +a
fi

RADARR_KEY="${RADARR_API_KEY:?RADARR_API_KEY not set in .env}"

radarr() {
  docker exec radarr curl -sf "http://localhost:7878$1" -H "X-Api-Key: $RADARR_KEY" "${@:2}" 2>/dev/null
}

echo "========================================="
echo " Smoke Test: RD Download Pipeline"
echo "========================================="
echo

# --- 1. Service health ---
info "1. Checking service health..."
for svc in radarr rdt-client zurg rclone; do
  if docker compose ps --format '{{.Name}} {{.Status}}' 2>/dev/null | grep -q "$svc.*Up"; then
    pass "$svc is running"
  else
    fail "$svc is NOT running"
  fi
done
echo

# --- 2. rdt-client qBittorrent auth ---
info "2. Testing rdt-client qBittorrent API auth..."
AUTH_RESULT=$(docker exec radarr curl -s "http://rdt-client:6500/api/v2/auth/login" \
  -X POST -d "username=admin&password=cutdacord2024" 2>/dev/null || echo "CONN_FAIL")
if [ "$AUTH_RESULT" = "Ok." ]; then
  pass "rdt-client qBit auth succeeds"
else
  fail "rdt-client qBit auth failed (got: $AUTH_RESULT)"
fi
echo

# --- 3. Radarr download client test ---
info "3. Testing Radarr -> rdt-client download client connection..."
CLIENT_JSON=$(radarr "/api/v3/downloadclient/3")
TEST_RESULT=$(docker exec radarr curl -s -X POST "http://localhost:7878/api/v3/downloadclient/test" \
  -H "X-Api-Key: $RADARR_KEY" -H "Content-Type: application/json" \
  -d "$CLIENT_JSON" 2>/dev/null)
if [ "$TEST_RESULT" = "{}" ] || [ -z "$TEST_RESULT" ]; then
  pass "Radarr -> rdt-client connection test passes"
else
  fail "Radarr -> rdt-client connection test failed: $TEST_RESULT"
fi
echo

# --- 4. RD API key validity ---
info "4. Checking Real-Debrid API key..."
RD_KEY=$(python3 -c "
import sqlite3
conn = sqlite3.connect('config/rdtclient/rdtclient.db')
c = conn.cursor()
c.execute(\"SELECT Value FROM Settings WHERE SettingId='Provider:ApiKey'\")
print(c.fetchone()[0])
" 2>/dev/null)
RD_USER=$(curl -s "https://api.real-debrid.com/rest/1.0/user" -H "Authorization: Bearer $RD_KEY" 2>/dev/null)
if echo "$RD_USER" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('type')=='premium'" 2>/dev/null; then
  EXPIRY=$(echo "$RD_USER" | python3 -c "import sys,json; print(json.load(sys.stdin)['expiration'][:10])" 2>/dev/null)
  pass "RD API key valid (premium, expires $EXPIRY)"
else
  fail "RD API key invalid or not premium"
fi
echo

# --- 5. Zurg + rclone mount ---
info "5. Checking Zurg + rclone mount..."
ZURG_HEALTH=$(docker exec zurg curl -s http://localhost:9999/health 2>/dev/null || echo "FAIL")
if echo "$ZURG_HEALTH" | grep -qi "ok\|healthy\|alive" 2>/dev/null || [ "$ZURG_HEALTH" != "FAIL" ]; then
  pass "Zurg health endpoint responds"
else
  fail "Zurg health check failed"
fi

if docker exec rclone ls /data/zurg/ 2>/dev/null | head -1 | grep -q .; then
  pass "rclone mount has content"
else
  info "rclone mount is empty (OK if no active RD torrents)"
fi
echo

# --- 6. qBit API torrent list (via rdt-client) ---
info "6. Testing rdt-client torrent list API..."
# First authenticate
COOKIE=$(docker exec radarr curl -sv "http://rdt-client:6500/api/v2/auth/login" \
  -X POST -d "username=admin&password=cutdacord2024" 2>&1 | grep -i "set-cookie" | head -1 | sed 's/.*set-cookie: //i; s/;.*//')
if [ -n "$COOKIE" ]; then
  TORRENTS=$(docker exec radarr curl -s "http://rdt-client:6500/api/v2/torrents/info" \
    -H "Cookie: $COOKIE" 2>/dev/null)
  if echo "$TORRENTS" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    COUNT=$(echo "$TORRENTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
    pass "qBit torrent list API works ($COUNT torrents)"
  else
    fail "qBit torrent list returned invalid JSON"
  fi
else
  fail "Could not get auth cookie from rdt-client"
fi
echo

# --- Summary ---
echo "========================================="
TOTAL=$((PASS + FAIL))
echo -e " Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC} / $TOTAL total"
echo "========================================="

if [ $FAIL -gt 0 ]; then
  exit 1
fi
