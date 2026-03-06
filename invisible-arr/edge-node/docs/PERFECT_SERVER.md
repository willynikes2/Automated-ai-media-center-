# CutDaCord — Perfect Server Reference

Production-ready configuration guide synthesized from TRaSH Guides, IBRACORP tutorials, and battle-tested best practices.

---

## 1. Architecture Overview

```
Internet → Traefik (TLS + security plugins) → Frontend / API / Jellyfin
                                                  ↓
                                            Agent API (FastAPI)
                                              ↓         ↓
                                         Agent Worker   Agent QC
                                           ↓    ↓
                                    Radarr/Sonarr  Download Clients
                                         ↓              ↓
                                    Prowlarr        qBit / RDT / SABnzbd
                                                         ↓
                                                    /data/media → Jellyfin
```

### Container Count: ~26
- **User-facing:** Traefik, Frontend, Jellyfin, Landing
- **Agent layer:** agent-api, agent-worker, agent-qc, agent-storage
- **Arr stack:** Radarr, Sonarr, Prowlarr, Recyclarr
- **Download:** qBittorrent, rdt-client, Zurg, Rclone, SABnzbd
- **Infra:** Postgres, Redis, FlareSolverr
- **Observability:** Prometheus, Loki, Promtail, Grafana

---

## 2. Storage Architecture (TRaSH-Compatible)

### Folder Structure
```
data/
├── media/
│   ├── users/{user_id}/
│   │   ├── Movies/
│   │   └── TV/
│   └── (shared libraries if needed)
├── torrents/
│   ├── movies/
│   ├── tv/
│   └── music/
├── usenet/
│   ├── complete/
│   └── incomplete/
└── zurg/
    └── __all__/  (Real-Debrid mount via rclone)
```

### Hardlinks
- Sonarr/Radarr mount `${DATA_PATH}:/data` (full share, not subdirectory)
- qBittorrent mounts `${DATA_PATH}/torrents:/data/torrents`
- Both see the same filesystem → hardlinks work
- Enable in Radarr/Sonarr: Settings → Media Management → Show Advanced → "Use hard links instead of copy"

### Why This Matters
Without hardlinks: file is **copied** (doubles I/O, doubles disk usage temporarily)
With hardlinks: instant, zero extra disk space, same file with two directory entries

---

## 3. Authentication

### Current Auth Methods
1. **Email/Password** — bcrypt-hashed, returns API key
2. **Jellyfin SSO** — authenticates against Jellyfin, creates/links local user
3. **Google OAuth2** — OIDC flow, creates/links user by email
4. *(Planned)* **Apple Sign-In**

### Why NOT Authentik for CutDaCord
Authentik is designed for homelab SSO across multiple self-hosted apps. CutDaCord is a SaaS product with its own user model, tiers, invite system, and API keys. Adding OAuth2 directly to FastAPI is simpler and more appropriate.

**Authentik makes sense for:** protecting admin panels (Grafana, Sonarr, Radarr) if exposed publicly.

### Google OAuth2 Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create OAuth 2.0 Client ID (Web Application type)
3. Authorized redirect URI: `https://app.cutdacord.app/auth/google/callback`
4. Add to `.env`:
   ```
   GOOGLE_CLIENT_ID=<your-client-id>
   GOOGLE_CLIENT_SECRET=<your-client-secret>
   GOOGLE_REDIRECT_URI=https://app.cutdacord.app/auth/google/callback
   ```
5. Rebuild agent-api: `docker compose build agent-api && docker compose up -d agent-api`

---

## 4. TRaSH Guides / Recyclarr

### What Recyclarr Does
Automatically syncs TRaSH Guides custom formats, quality profiles, and scoring into Radarr/Sonarr. Runs on schedule or manually.

### Current Profiles
- **Radarr:** HD Bluray + WEB (1080p focus, x265 preferred)
- **Sonarr:** WEB-1080p (streaming source preferred)

### Custom Formats Enabled
- **Required:** Golden Rule HD (x265 codec scoring)
- **Miscellaneous:** Bad Dual Groups, DV (Disk), No-RlsGroup, Obfuscated, Retags, Scene, x264, x265
- **Movie Versions (Radarr only):** Remaster, 4K Remaster, Criterion, IMAX, IMAX Enhanced, Theatrical Cut, etc.

### Running Recyclarr
```bash
docker exec recyclarr recyclarr sync
```

### Key Principle
TRaSH scoring ensures you get the **right file the first time** — correct codec, resolution, and source. This eliminates the "downloaded wrong quality" problem that CutDaCord's AI agent also monitors for.

---

## 5. Traefik Security

### Plugins Enabled
| Plugin | Purpose |
|--------|---------|
| **fail2ban** | Rate limiting, brute force protection (ban after 5 attempts for 3h) |
| **real-ip** | Extract real client IPs behind Cloudflare/CDN |

### Security Headers
All responses include:
- XSS protection
- Content-Type nosniff
- Frame deny (clickjacking protection)
- HSTS with preload (1 year)
- Strict referrer policy

### Config Location
- Static: `docker-compose.yml` traefik command args
- Dynamic: `config/traefik/dynamic/security.yml` (hot-reloaded)

---

## 6. Monitoring Stack

### Prometheus (Metrics)
- Scrapes agent-api `/metrics` endpoint
- 30-day retention, 2GB max
- CPU/memory/disk usage of all containers

### Loki + Promtail (Logs)
- Promtail ships Docker container logs to Loki
- Centralized log search via Grafana

### Grafana (Dashboards)
- URL: `https://status.cutdacord.app`
- Pre-provisioned dashboards for system + media metrics
- Alert rules for disk space, container health

---

## 7. Maintenance Runbook

### Daily (Automated)
- Recyclarr syncs TRaSH profiles
- Agent worker processes job queue
- Agent QC verifies import quality
- Promtail ships logs

### Weekly (Manual Check)
- Review Grafana dashboards for anomalies
- Check Radarr/Sonarr activity for stuck items
- Verify Zurg/rclone mount is healthy: `docker exec rclone ls zurg:`

### Monthly
- Update container images: `docker compose pull && docker compose up -d`
- Check for Recyclarr config updates (TRaSH Guides evolve)
- Review and rotate API keys/tokens if needed
- Check disk usage and clean up old media if needed

### Before Any Upgrade
1. Back up Postgres: `docker exec postgres pg_dump -U invisible_arr invisible_arr > backup.sql`
2. Back up config directory: `tar -czf config-backup.tar.gz config/`
3. Test upgrade on a non-production instance if possible

---

## 8. Common Issues

| Issue | Solution |
|-------|----------|
| Hardlinks not working | Verify Sonarr/Radarr mount to `/data` (not `/data/media`). Must be same filesystem. |
| Recyclarr sync fails | Check API keys in config match `.env`. Run `docker logs recyclarr` for details. |
| Google login not appearing | Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, rebuild agent-api. |
| Traefik plugins not loading | Plugins require Traefik restart (they're in static config). Run `docker compose restart traefik`. |
| rdt-client stuck | Check Real-Debrid account status. Clear queue via API. See `docs/ROADMAP.md` for known issues. |
| Worker jobs stuck in ACQUIRING | Reset job to PENDING in DB AND re-enqueue in Redis. DB reset alone doesn't trigger processing. |
| Jellyfin not finding new media | Run library scan. Check folder permissions (PUID/PGID). Verify mount paths. |
| Zurg mount stale | Restart rclone: `docker compose restart rclone`. Check Zurg health: `curl http://localhost:9999/dav/` |

---

## 9. Key Ports (Internal Only)

| Service | Port | Notes |
|---------|------|-------|
| Traefik | 80, 443 | Only public-facing ports |
| agent-api | 8880 | Via Traefik at api.cutdacord.app |
| Jellyfin | 8096 | Via Traefik at media.cutdacord.app |
| Frontend | 3000 | Via Traefik at app.cutdacord.app |
| Grafana | 3000 | Via Traefik at status.cutdacord.app |
| Radarr | 7878 | Internal only |
| Sonarr | 8989 | Internal only |
| Prowlarr | 9696 | Internal only |
| qBittorrent | 8080 | Internal only |
| Postgres | 5432 | Internal only |
| Redis | 6379 | Internal only |
