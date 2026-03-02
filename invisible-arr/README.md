# Invisible Arr + Agent Brain

> Fully automated media acquisition. Users request in Seerr, watch in Jellyfin. Everything in between is invisible.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        EDGE NODE                                │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                  │
│  │  Traefik  │───▶│  Seerr   │    │ Jellyfin │  ◀── User       │
│  │  (ingress)│    │  (UI)    │    │ (player) │     watches      │
│  └──────────┘    └────┬─────┘    └────▲─────┘                  │
│                       │               │                         │
│                  ┌────▼─────┐    ┌────┴─────┐                  │
│                  │ agent-api│───▶│agent-qc  │                  │
│                  └────┬─────┘    └──────────┘                  │
│                       │                                         │
│                  ┌────▼──────┐                                  │
│                  │agent-worker│                                  │
│                  └──┬───┬────┘                                  │
│                     │   │                                       │
│           ┌─────────▼┐ ┌▼─────────┐                            │
│           │ Prowlarr  │ │Real-Debrid│                           │
│           │ (indexers) │ │ (cached) │                           │
│           └─────┬─────┘ └──────────┘                           │
│                 │                                               │
│           ┌─────▼──────┐  ┌──────────┐  ┌──────────┐          │
│           │FlareSolverr │  │ Gluetun  │  │qBittorrent│          │
│           │ (CF bypass) │  │  (VPN)   │──│(fallback) │          │
│           └─────────────┘  └──────────┘  └──────────┘          │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐                 │
│  │ Postgres │  │  Redis   │  │agent-storage  │                 │
│  │  (state) │  │ (queue)  │  │(disk manager) │                 │
│  └──────────┘  └──────────┘  └──────────────┘                 │
│                                                                 │
│  ┌──────────────┐                                              │
│  │ iptv-gateway  │  (optional: M3U/XMLTV merge + TZ convert)  │
│  └──────────────┘                                              │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
cd edge-node
bash scripts/install.sh
```

The installer will:
1. Check for Docker Engine 24+ and Docker Compose v2
2. Generate `.env` from template with interactive prompts
3. Create required directories
4. Build and start the entire stack

## After Install

- **Seerr** (request UI): `http://localhost:5055`
- **Jellyfin** (media player): `http://localhost:8096`
- **Agent API**: `http://localhost:8880/health`

## Verify

```bash
bash scripts/smoke.sh
```

## Documentation

- [Architecture](edge-node/docs/ARCHITECTURE.md) — container map, data flow, network topology
- [Setup Guide](edge-node/docs/SETUP.md) — prerequisites, first run, env var reference
- [FlareSolverr](edge-node/docs/FLARESOLVERR.md) — Cloudflare bypass configuration

## License

MIT
