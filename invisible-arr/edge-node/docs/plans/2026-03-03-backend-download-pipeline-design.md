# Backend Download Pipeline — Indexers, Usenet, Reliability

**Date:** 2026-03-03
**Status:** Approved

## Summary

Upgrade the download pipeline from RD-only to a multi-method acquisition system with automatic candidate fallback, streaming link support, Usenet scaffolding, and VPN torrent fallback.

## 1. Prowlarr Indexer Setup Script

Reusable `scripts/setup-indexers.sh`:
- Reads API key from `config/prowlarr/config.xml`
- Fetches available indexer schemas, filters public torrent indexers
- Adds each missing indexer (idempotent)
- Configures FlareSolverr as indexer proxy
- Syncs to Sonarr/Radarr
- Runs test search and reports counts

## 2. Download Reliability

### Candidate Fallback
When acquisition fails on a candidate, try the next-best (up to top 3 by score). Currently a single failure = FAILED job.

### Error Diagnostics
`diagnose_failure()` maps raw errors to actionable messages stored as job events.

### Download Progress
Track bytes during RD download, store percentage in Redis (`job:{id}:progress`). Add `GET /v1/jobs/{id}/progress` endpoint.

## 3. Streaming Link Mode

When `acquisition_mode="stream"` (RD only):
- Add magnet, select files, unrestrict links
- Store URLs in `job.streaming_urls`
- Skip download/import/QC, transition to DONE

## 4. Usenet Scaffolding

- SABnzbd in docker-compose (profile: `usenet`, disabled by default)
- Config vars in `config.py` and `.env.template`
- `sabnzbd_client.py` — SABnzbd API client
- `acquire_via_usenet()` in worker

## 5. VPN Torrent Fallback

- `qbt_client.py` — qBittorrent Web API client
- `acquire_via_torrent()` — checks Gluetun health, adds magnet, polls completion
- Config vars: `qbt_url`, `qbt_password`

## Acquisition Order

```
acquire_with_fallback(job, candidates, prefs)
  For each candidate (top 3):
    1. RD (if enabled)
    2. Usenet (if enabled, NZB results only)
    3. VPN Torrent (if enabled, VPN health check first)
    On failure: log diagnostic, try next candidate
  All failed → FAILED with diagnostics
```

## Files

| File | Action |
|------|--------|
| `scripts/setup-indexers.sh` | Create |
| `services/agent-worker/worker.py` | Modify — candidate fallback, streaming, multi-method |
| `services/shared/config.py` | Modify — Usenet + qBit config |
| `services/shared/qbt_client.py` | Create |
| `services/shared/sabnzbd_client.py` | Create |
| `services/shared/rd_client.py` | Modify — progress callback |
| `services/shared/schemas.py` | Modify — progress schema |
| `services/agent-api/routers/jobs.py` | Modify — progress endpoint |
| `docker-compose.yml` | Modify — SABnzbd service |
| `.env.template` | Modify — new vars |
| `services/migrations/versions/003_add_acquisition_fields.py` | Create |
