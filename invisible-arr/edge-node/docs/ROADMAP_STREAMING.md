# Streaming Mode (Zurg/STRM) — Future Roadmap

Status: DISABLED (2026-03-05)
Reason: RDT-Client `FinishedAction: RemoveAllTorrents` deletes torrents from RD after download, leaving Zurg mount empty. Streaming requires torrents to persist in RD cloud.

## What it did
- User clicks "Stream" instead of "Download" in request modal
- Worker creates .strm file pointing to Zurg-mounted RD content
- Jellyfin plays via HTTP stream from Real-Debrid servers
- No local disk usage for the media file

## Why it was disabled
1. rdt-client removes all torrents from RD after download completes
2. Zurg mount is empty because no torrents persist in RD
3. `_pick_zurg_source()` can never find files → fails after 5 retries
4. RD "storage" is really a CDN cache — not guaranteed persistent
5. Radarr/Sonarr don't understand .strm files for quality upgrades

## Files involved
- Frontend: `services/frontend/src/components/media/RequestButton.tsx` (lines 209-230)
- Worker: `services/agent-worker/worker.py` (lines 285-329, 835-957)
- Config: `services/shared/config.py` (lines 94-96: zurg_enabled, zurg_mount_path, zurg_base_url)
- Docker: `docker-compose.yml` (zurg + zurg-mounter services, lines 228-266)
- DB columns: `jobs.acquisition_mode`, `jobs.streaming_urls` (kept, not removed)

## To re-enable in future
1. Solve torrent persistence: either bypass rdt-client for stream jobs (add torrent directly to RD API) or change rdt-client FinishedAction per-torrent
2. RD has ~2000 active torrent limit for premium users — need cleanup strategy
3. Consider: is local disk + smart quality management a better solution than streaming?
4. If re-enabling, set `ZURG_ENABLED=true` in .env and restore the Stream button in RequestButton.tsx

## Smart Storage alternative (preferred direction)
Instead of streaming to avoid disk limits, dynamically adjust quality profiles based on available storage. When disk is getting full, prefer smaller files. When plenty of space, allow higher quality. This keeps the proven download flow intact.
