#!/usr/bin/env bash
# Smoke test: Zurg + rclone streaming pipeline
# Verifies the full chain: RD -> Zurg WebDAV -> rclone FUSE -> Jellyfin visibility
# Run from edge-node directory: ./scripts/smoke-test-streaming.sh

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

if [ -f .env ]; then
  set -a; source .env; set +a
fi

echo "========================================="
echo " Smoke Test: Streaming Pipeline"
echo " (Zurg -> rclone -> Jellyfin)"
echo "========================================="
echo

# --- 1. Service health ---
info "1. Checking streaming services..."
for svc in zurg rclone jellyfin; do
  if docker compose ps --format '{{.Name}} {{.Status}}' 2>/dev/null | grep -q "$svc.*Up"; then
    pass "$svc is running"
  else
    fail "$svc is NOT running"
  fi
done
echo

# --- 2. Zurg WebDAV responds ---
info "2. Checking Zurg WebDAV endpoint..."
ZURG_DAV=$(docker exec zurg curl -sf http://localhost:9999/dav/ 2>/dev/null || echo "FAIL")
if echo "$ZURG_DAV" | grep -qi "movies\|shows\|__all__"; then
  pass "Zurg WebDAV lists directories"
else
  fail "Zurg WebDAV not responding or empty"
fi
echo

# --- 3. rclone FUSE mount active ---
info "3. Checking rclone FUSE mount..."
RCLONE_LS=$(docker exec rclone ls /data/ 2>/dev/null || echo "FAIL")
if echo "$RCLONE_LS" | grep -qi "movies\|shows\|__all__"; then
  pass "rclone FUSE mount has directories"
else
  fail "rclone FUSE mount empty or broken"
fi

RCLONE_MOVIES=$(docker exec rclone ls /data/movies/ 2>/dev/null | head -5)
if [ -n "$RCLONE_MOVIES" ]; then
  COUNT=$(docker exec rclone ls /data/movies/ 2>/dev/null | wc -l)
  pass "rclone movies directory has $COUNT items"
else
  info "rclone movies directory is empty (OK if no RD content)"
fi
echo

# --- 4. Mount propagation: Jellyfin sees rclone content ---
info "4. Checking mount propagation to Jellyfin (CRITICAL)..."
JF_ZURG=$(docker exec jellyfin ls /data/zurg/ 2>/dev/null || echo "FAIL")
if echo "$JF_ZURG" | grep -qi "movies\|shows\|__all__"; then
  pass "Jellyfin can see /data/zurg directories"
else
  fail "Jellyfin CANNOT see /data/zurg (mount propagation broken!)"
fi

JF_MOVIES=$(docker exec jellyfin ls /data/zurg/movies/ 2>/dev/null | head -5)
RCLONE_MOVIES_CHECK=$(docker exec rclone ls /data/movies/ 2>/dev/null | head -5)
if [ -n "$JF_MOVIES" ] && [ -n "$RCLONE_MOVIES_CHECK" ]; then
  pass "Jellyfin sees movies from rclone mount"
elif [ -z "$RCLONE_MOVIES_CHECK" ]; then
  info "No movies in RD currently (can't verify content propagation)"
else
  fail "Jellyfin can't see movies that rclone has"
fi
echo

# --- 5. Propagation type check ---
info "5. Verifying mount propagation mode..."
PROP=$(docker inspect jellyfin --format '{{range .Mounts}}{{if eq .Destination "/data/zurg"}}{{.Propagation}}{{end}}{{end}}' 2>/dev/null)
if [ "$PROP" = "slave" ] || [ "$PROP" = "shared" ] || [ "$PROP" = "rslave" ] || [ "$PROP" = "rshared" ]; then
  pass "Jellyfin /data/zurg mount propagation is '$PROP'"
else
  fail "Jellyfin /data/zurg propagation is '$PROP' (needs slave or shared)"
fi
echo

# --- 6. End-to-end: can Jellyfin read a file from RD? ---
info "6. End-to-end file read test..."
FIRST_MOVIE=$(docker exec rclone ls /data/movies/ 2>/dev/null | head -1)
if [ -n "$FIRST_MOVIE" ]; then
  FIRST_MOVIE=$(echo "$FIRST_MOVIE" | xargs)
  # Check if Jellyfin can stat the same file
  if docker exec jellyfin test -d "/data/zurg/movies/$FIRST_MOVIE" 2>/dev/null; then
    # Try to read first few bytes of the biggest file
    BIGGEST=$(docker exec jellyfin find "/data/zurg/movies/$FIRST_MOVIE" -type f -name '*.mkv' -o -name '*.mp4' 2>/dev/null | head -1)
    if [ -n "$BIGGEST" ]; then
      BYTES=$(docker exec jellyfin head -c 4 "$BIGGEST" 2>/dev/null | wc -c)
      if [ "$BYTES" -gt 0 ]; then
        pass "Jellyfin can read video file bytes from RD stream"
      else
        fail "Jellyfin found video file but can't read bytes"
      fi
    else
      info "No .mkv/.mp4 files found in first movie dir (skipping byte test)"
    fi
  else
    fail "Jellyfin can't access movie dir that rclone has"
  fi
else
  info "No movies in RD to test end-to-end (skipping)"
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
