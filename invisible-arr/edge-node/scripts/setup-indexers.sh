#!/usr/bin/env bash
# setup-indexers.sh — Add all available public torrent indexers to Prowlarr
# Usage: ./scripts/setup-indexers.sh
# Idempotent: skips indexers that already exist.

set -euo pipefail

PROWLARR_URL="${PROWLARR_URL:-http://localhost:9696}"

# Try to read API key from config file first, then env
if [ -z "${PROWLARR_API_KEY:-}" ]; then
    CONFIG_FILE="${CONFIG_PATH:-./config}/prowlarr/config.xml"
    if [ -f "$CONFIG_FILE" ]; then
        PROWLARR_API_KEY=$(grep -oP '(?<=<ApiKey>)[^<]+' "$CONFIG_FILE" 2>/dev/null || true)
    fi
fi

if [ -z "${PROWLARR_API_KEY:-}" ]; then
    echo "ERROR: PROWLARR_API_KEY not set and could not read from config.xml"
    exit 1
fi

HEADERS=(-H "X-Api-Key: $PROWLARR_API_KEY" -H "Content-Type: application/json")

echo "=== Prowlarr Indexer Setup ==="
echo "URL: $PROWLARR_URL"
echo ""

# Step 1: Get existing indexers
echo "Checking existing indexers..."
EXISTING=$(curl -sf "$PROWLARR_URL/api/v1/indexer" "${HEADERS[@]}")
EXISTING_NAMES=$(echo "$EXISTING" | python3 -c "
import sys, json
for idx in json.load(sys.stdin):
    print(idx.get('definitionName', '').lower())
" 2>/dev/null || true)
EXISTING_COUNT=$(echo "$EXISTING_NAMES" | grep -c . 2>/dev/null || echo 0)
echo "Found $EXISTING_COUNT existing indexers"
echo ""

# Step 2: Get available schemas
echo "Fetching available indexer schemas..."
SCHEMAS=$(curl -sf "$PROWLARR_URL/api/v1/indexer/schema" "${HEADERS[@]}")

PUBLIC_INDEXERS=$(echo "$SCHEMAS" | python3 -c "
import sys, json
schemas = json.load(sys.stdin)
seen = set()
for s in schemas:
    proto = s.get('protocol', '')
    privacy = s.get('privacy', '')
    defn = s.get('definitionName', '')
    if proto == 'torrent' and privacy == 'public' and defn and defn not in seen:
        seen.add(defn)
        impl = s.get('implementation', '')
        contract = s.get('configContract', '')
        print(f'{defn}|{impl}|{contract}')
" 2>/dev/null | sort)

TOTAL=$(echo "$PUBLIC_INDEXERS" | grep -c . 2>/dev/null || echo 0)
echo "Found $TOTAL public torrent indexer definitions"
echo ""

# Step 3: Add missing indexers
ADDED=0
SKIPPED=0
FAILED=0

while IFS='|' read -r DEF_NAME IMPL CONTRACT; do
    [ -z "$DEF_NAME" ] && continue

    if echo "$EXISTING_NAMES" | grep -qi "^${DEF_NAME}$"; then
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    echo -n "  Adding: $DEF_NAME ... "

    PAYLOAD=$(DEF_NAME="$DEF_NAME" IMPL="$IMPL" CONTRACT="$CONTRACT" python3 -c "
import os, json
print(json.dumps({
    'name': os.environ['DEF_NAME'],
    'definitionName': os.environ['DEF_NAME'],
    'implementation': os.environ['IMPL'],
    'configContract': os.environ['CONTRACT'],
    'enable': True,
    'appProfileId': 1,
    'protocol': 'torrent',
    'privacy': 'public',
    'fields': [],
    'tags': []
}))
")

    RESULT=$(curl -sf -w "%{http_code}" -o /tmp/prowlarr_add.json \
        -X POST "$PROWLARR_URL/api/v1/indexer" \
        "${HEADERS[@]}" \
        -d "$PAYLOAD" 2>/dev/null || echo "000")

    if [ "$RESULT" = "201" ] || [ "$RESULT" = "200" ]; then
        echo "OK"
        ADDED=$((ADDED + 1))
    else
        MSG=$(cat /tmp/prowlarr_add.json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('message', d.get('errorMessage', str(d)))[:80])
except:
    print('unknown error')
" 2>/dev/null || echo "HTTP $RESULT")
        echo "FAILED ($MSG)"
        FAILED=$((FAILED + 1))
    fi
done <<< "$PUBLIC_INDEXERS"

echo ""
echo "=== Results ==="
echo "  Added:   $ADDED"
echo "  Skipped: $SKIPPED (already exist)"
echo "  Failed:  $FAILED"
echo ""

# Step 4: Configure FlareSolverr proxy
echo "Checking FlareSolverr proxy..."
PROXIES=$(curl -sf "$PROWLARR_URL/api/v1/indexerProxy" "${HEADERS[@]}" 2>/dev/null || echo "[]")
HAS_FLARE=$(echo "$PROXIES" | python3 -c "
import sys, json
proxies = json.load(sys.stdin)
print('yes' if any(p.get('implementation') == 'FlareSolverr' for p in proxies) else 'no')
" 2>/dev/null || echo "no")

if [ "$HAS_FLARE" = "no" ]; then
    echo "  Adding FlareSolverr proxy..."
    curl -sf -X POST "$PROWLARR_URL/api/v1/indexerProxy" \
        "${HEADERS[@]}" \
        -d '{
            "name": "FlareSolverr",
            "implementation": "FlareSolverr",
            "configContract": "FlareSolverrSettings",
            "fields": [
                {"name": "host", "value": "http://flaresolverr:8191"},
                {"name": "requestTimeout", "value": 60}
            ],
            "tags": []
        }' > /dev/null 2>&1 && echo "  FlareSolverr proxy added" || echo "  Failed to add FlareSolverr proxy"
else
    echo "  FlareSolverr proxy already configured"
fi
echo ""

# Step 5: Sync to Sonarr/Radarr
echo "Syncing indexers to Sonarr/Radarr..."
curl -sf -X POST "$PROWLARR_URL/api/v1/indexer/action/SyncAll" \
    "${HEADERS[@]}" > /dev/null 2>&1 && echo "  Sync triggered" || echo "  Sync failed (may not be connected)"
echo ""

# Step 6: Test search
echo "Running test search for 'The Matrix'..."
RESULTS=$(curl -sf "$PROWLARR_URL/api/v1/search?query=The+Matrix&type=search" \
    "${HEADERS[@]}" 2>/dev/null || echo "[]")
echo "$RESULTS" | python3 -c "
import sys, json
results = json.load(sys.stdin)
print(f'  Total results: {len(results)}')
by_indexer = {}
for r in results:
    idx = r.get('indexer', 'unknown')
    by_indexer[idx] = by_indexer.get(idx, 0) + 1
for idx, count in sorted(by_indexer.items(), key=lambda x: -x[1])[:15]:
    print(f'    {idx:30s} {count:5d} results')
" 2>/dev/null || echo "  Could not parse search results"

echo ""
echo "=== Done ==="
