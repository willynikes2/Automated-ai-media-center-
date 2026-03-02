# Architecture

## Container Map

| Tier | Container | Image | Exposed | Port |
|------|-----------|-------|---------|------|
| User-Facing | traefik | traefik:v3.3 | Yes | 80, 443 |
| User-Facing | jellyfin | jellyfin/jellyfin:latest | Yes (via Traefik) | 8096 |
| User-Facing | seerr | ghcr.io/seerr-team/seerr:latest | Yes (via Traefik) | 5055 |
| Hidden Plumbing | sonarr | lscr.io/linuxserver/sonarr:latest | No | 8989 |
| Hidden Plumbing | radarr | lscr.io/linuxserver/radarr:latest | No | 7878 |
| Hidden Plumbing | prowlarr | lscr.io/linuxserver/prowlarr:latest | No | 9696 |
| Acquisition | gluetun | qmcgaw/gluetun:latest | No | — |
| Acquisition | qbittorrent | lscr.io/linuxserver/qbittorrent:latest | No (via gluetun) | 8080 |
| Acquisition | flaresolverr | ghcr.io/flaresolverr/flaresolverr:latest | No | 8191 |
| Agent Layer | agent-api | Custom (FastAPI) | Optional (via Traefik) | 8880 |
| Agent Layer | agent-worker | Custom (FastAPI) | No | — |
| Agent Layer | agent-qc | Custom (ffprobe) | No | — |
| Agent Layer | agent-storage | Custom (FastAPI) | No | — |
| Agent Layer | iptv-gateway | Custom (FastAPI) | No | 8881 |
| Infrastructure | postgres | postgres:16-alpine | No | 5432 |
| Infrastructure | redis | redis:7-alpine | No | 6379 |

## Data Flow

```
User submits request in Seerr
       │
       ▼
Seerr triggers agent-api (webhook / direct call)
       │
       ▼
agent-worker resolves TMDB ID (canonical identity)
       │
       ▼
agent-worker searches Prowlarr for release candidates
       │
       ▼
Regex parser extracts resolution, codec, source, size, tags
       │
       ▼
Deterministic scoring engine ranks candidates by policy
       │
       ▼
Top candidate acquired: Real-Debrid first, VPN torrent fallback
       │
       ▼
Files staged in /data/downloads/rd/<job_id>/
       │
       ▼
Imported to /data/media/ with correct naming convention
       │
       ▼
agent-qc runs ffprobe validation
       │
       ▼
Jellyfin library scan picks up new media
```

## Network Topology

- **Traefik** is the sole ingress point (ports 80/443)
- All inter-service communication happens on the `internal` Docker network
- **qBittorrent** runs exclusively through Gluetun (`network_mode: service:gluetun`)
- All torrent traffic is VPN-protected when VPN is enabled
- Agent services communicate with Arr APIs over the internal network

**Hard rule:** Sonarr, Radarr, Prowlarr, and qBittorrent UIs are NEVER publicly exposed. Only Seerr, Jellyfin, and optionally agent-api are routed through Traefik.
