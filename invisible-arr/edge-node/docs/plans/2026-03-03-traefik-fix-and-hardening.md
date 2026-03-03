# Traefik Fix + Port Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix Traefik's Docker API version negotiation failure, harden service port bindings to localhost-only, fix Redis healthcheck auth, and make install.sh fully self-sufficient for future installs.

**Architecture:** Three-file edit — `docker-compose.yml` (runtime fixes), `.env.template` (add missing vars), `scripts/install.sh` (auto-generate secrets + pre-flight setup). No new files. No volume changes. Only Traefik and Redis are recreated; other services just get their port bindings corrected in-place.

**Tech Stack:** Docker Compose v2, Traefik v3.3, Redis 7, bash

---

## Task 1: Backup docker-compose.yml

**Files:**
- Modify: `docker-compose.yml` (backup only)

**Step 1: Create timestamped backup**

```bash
cp docker-compose.yml docker-compose.yml.bak
```

Expected: file `docker-compose.yml.bak` now exists.

**Step 2: Verify backup**

```bash
diff docker-compose.yml docker-compose.yml.bak
```

Expected: no output (files identical).

---

## Task 2: Fix docker-compose.yml — Traefik Docker API version

**Files:**
- Modify: `docker-compose.yml` lines 6-31 (traefik service)

**Problem:** Traefik's internal Docker client defaults to negotiating API v1.24, but the host Docker daemon requires ≥1.44. Setting `DOCKER_API_VERSION` in the container's env forces the client to skip the downgrade negotiation.

**Step 1: Add environment block + endpoint flag to traefik service**

Replace the traefik `command:` block and add `environment:`:

```yaml
  traefik:
    image: traefik:v3.3
    container_name: traefik
    restart: unless-stopped
    environment:
      - DOCKER_HOST=unix:///var/run/docker.sock
      - DOCKER_API_VERSION=${DOCKER_API_VERSION:-1.44}
    command:
      - "--providers.docker=true"
      - "--providers.docker.endpoint=unix:///var/run/docker.sock"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.letsencrypt.acme.email=${ACME_EMAIL:-admin@example.com}"
      - "--certificatesresolvers.letsencrypt.acme.storage=/etc/traefik/acme.json"
      - "--entrypoints.web.http.redirections.entrypoint.to=websecure"
      - "--entrypoints.web.http.redirections.entrypoint.scheme=https"
      - "--api=false"
      - "--api.dashboard=false"
      - "--log.level=WARN"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ${CONFIG_PATH:-./config}/traefik:/etc/traefik
    networks:
      - internal
```

**Step 2: Validate compose file**

```bash
docker compose config --quiet
```

Expected: no errors.

---

## Task 3: Fix docker-compose.yml — Redis healthcheck auth

**Files:**
- Modify: `docker-compose.yml` lines 212-225 (redis service)

**Problem:** Redis is started with `--requirepass`, but the healthcheck runs `redis-cli ping` without auth — causes healthcheck to fail when a password is set.

Note: Inside a compose `test:` array, `$$VAR` double-escapes the `$` so compose doesn't interpolate it (the shell inside the container sees `$VAR`).

**Step 1: Fix redis healthcheck and update command**

Replace the redis service `command` and `healthcheck`:

```yaml
  redis:
    image: redis:7-alpine
    container_name: redis
    restart: unless-stopped
    command: >
      sh -c "redis-server --requirepass $${REDIS_PASSWORD}"
    healthcheck:
      test: ["CMD", "sh", "-c", "redis-cli -a $${REDIS_PASSWORD} ping | grep PONG"]
      interval: 10s
      timeout: 5s
      retries: 5
    volumes:
      - redis_data:/data
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    networks:
      - internal
```

**Note on the `command` change:** The original `redis-server --requirepass ${REDIS_PASSWORD:-}` fails when `REDIS_PASSWORD` is empty (redis gets `--requirepass` with no value). Using `sh -c` with `$$` escaping ensures compose doesn't expand it — the container's own environment does, and if `REDIS_PASSWORD` is unset it still produces a valid (empty-string) arg.

Actually, we want to require a password always — install.sh will always generate one. Keep it simple:

```yaml
    command: redis-server --requirepass ${REDIS_PASSWORD}
    environment:
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "redis-cli -a $$REDIS_PASSWORD ping | grep PONG"]
```

**Step 2: Validate**

```bash
docker compose config --quiet
```

Expected: no errors.

---

## Task 4: Fix docker-compose.yml — Harden port bindings

**Files:**
- Modify: `docker-compose.yml` — jellyfin, seerr, gluetun port entries

**Problem:** Jellyfin (8096), Seerr (5055), and qBittorrent via gluetun (8080) are bound to `0.0.0.0`, exposing them publicly. They should only be reachable on localhost; Traefik proxies the public traffic.

**Step 1: Update jellyfin ports**

Change:
```yaml
      - "${JELLYFIN_PORT:-8096}:8096"
```
To:
```yaml
      - "127.0.0.1:${JELLYFIN_PORT:-8096}:8096"
```

**Step 2: Update seerr ports**

Change:
```yaml
      - "${SEERR_PORT:-5055}:5055"
```
To:
```yaml
      - "127.0.0.1:${SEERR_PORT:-5055}:5055"
```

**Step 3: Update gluetun ports (qBittorrent WebUI)**

Change:
```yaml
      - "${QBITTORRENT_PORT:-8080}:8080"
```
To:
```yaml
      - "127.0.0.1:${QBITTORRENT_PORT:-8080}:8080"
```

**Step 4: Validate full compose file**

```bash
docker compose config
```

Expected: full rendered YAML with no errors. Verify port bindings show `127.0.0.1` for jellyfin, seerr, gluetun.

---

## Task 5: Update .env.template — add missing variables

**Files:**
- Modify: `.env.template`

**Step 1: Add REDIS_PASSWORD and DOCKER_API_VERSION**

Add after the `REDIS_URL` line:

```
REDIS_PASSWORD=CHANGEME_GENERATE_THIS

# Set to your host Docker API version (auto-detected by install.sh)
DOCKER_API_VERSION=1.44
```

Also add port variables that compose references but aren't in the template:

```
# --- Service ports ---
JELLYFIN_PORT=8096
SEERR_PORT=5055
AGENT_API_PORT=8880
QBITTORRENT_PORT=8080
IPTV_GATEWAY_PORT=8881
```

**Step 2: Verify the template has all vars referenced in docker-compose.yml**

```bash
grep -oP '\$\{[A-Z_]+' docker-compose.yml | tr -d '${' | sort -u
```

Check each var is either in `.env.template`, has a `:-default` in compose, or is intentionally absent (like `VPN_TYPE`, `WIREGUARD_*` — user-specific).

---

## Task 6: Update install.sh — auto-generate Redis password + Docker API version + acme.json

**Files:**
- Modify: `scripts/install.sh`

**Problems to fix:**
1. No `REDIS_PASSWORD` generation (causes Redis startup crash on fresh install)
2. No `acme.json` creation (Traefik fails to start without it, or starts with wrong perms)
3. No `DOCKER_API_VERSION` detection (causes Traefik provider failure on fresh install)
4. No post-startup health verification
5. Access URL section shows localhost even when domain is configured

**Step 1: Add Redis password generation after Postgres password generation**

In the `.env setup` section, after the Postgres password generation block, add:

```bash
    # Generate a random Redis password
    REDIS_PASS=$(openssl rand -hex 16)
    sed -i "s/REDIS_PASSWORD=CHANGEME_GENERATE_THIS/REDIS_PASSWORD=${REDIS_PASS}/" .env
    info "Generated random Redis password."
```

**Step 2: Add Docker API version detection**

After the `.env` source block, add:

```bash
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
```

**Step 3: Add acme.json creation in directory structure section**

After the `mkdir -p` loop, add:

```bash
# Traefik requires acme.json to exist with strict permissions before starting
if [ ! -f config/traefik/acme.json ]; then
    touch config/traefik/acme.json
    chmod 600 config/traefik/acme.json
    info "Created config/traefik/acme.json with permissions 600."
fi
```

**Step 4: Add post-startup healthcheck wait**

After the `docker compose up -d` call, add:

```bash
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
    warn "${container} did not become healthy after $((max_attempts * 2)) seconds. Check: docker logs ${container}"
    return 1
}

wait_healthy postgres
wait_healthy redis
```

**Step 5: Fix access URL output**

The current access URL section reads port values from `.env` with `grep`, which returns empty if the var is absent. Replace with sourced vars:

```bash
# Re-source .env to pick up all generated values
set -a
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
```

---

## Task 7: Apply and verify live

**Step 1: Run docker compose config to confirm no parse errors**

```bash
docker compose config
```

**Step 2: Recreate only traefik and redis (other services just need port rebind)**

```bash
docker compose up -d --force-recreate traefik redis
```

**Step 3: Check Traefik logs**

```bash
docker logs --tail=80 traefik
```

Expected: no "client version X is too old" error. Should see provider loaded successfully and routes discovered.

**Step 4: Check all containers are up**

```bash
docker ps
```

Expected: traefik, redis, postgres, jellyfin, sonarr, radarr, prowlarr, seerr, flaresolverr all `Up`.

**Step 5: Verify port bindings are localhost-only**

```bash
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep -E "jellyfin|seerr|gluetun"
```

Expected: `127.0.0.1:8096->8096/tcp`, `127.0.0.1:5055->5055/tcp`.

**Step 6: Verify redis auth works**

```bash
source .env && docker exec redis redis-cli -a "$REDIS_PASSWORD" ping
```

Expected: `PONG`

**Step 7: Verify redis healthcheck passes**

```bash
docker inspect --format='{{.State.Health.Status}}' redis
```

Expected: `healthy`

**Step 8: Commit**

```bash
git add docker-compose.yml .env.template scripts/install.sh
git commit -m "fix: traefik docker api version, redis auth healthcheck, localhost port binding, idempotent install"
```
