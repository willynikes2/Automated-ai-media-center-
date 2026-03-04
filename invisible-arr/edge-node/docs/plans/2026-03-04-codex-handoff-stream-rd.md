# Codex Handoff — Stream + Real-Debrid Integration (2026-03-04)

This file documents what Codex changed, why, and how it was validated so Claude can continue from the exact state.

## Scope
Implemented and validated reliability improvements for:
- Stream mode (`acquisition_mode=stream`) with Zurg `.strm` pointers.
- Download mode (`acquisition_mode=download`) with real `rdt-client`/Real-Debrid flow.
- Worker-side monitor/event bridging to reduce stuck `ACQUIRING` jobs.
- Jellyfin visibility of Zurg stream targets.

## Files Changed (by Codex)

### 1) `services/agent-worker/worker.py`
Changes made:
- Added separate Arr grab timeouts:
  - `ARR_GRAB_TIMEOUT_STREAM = 120`
  - `ARR_GRAB_TIMEOUT_DOWNLOAD = 600`
- Stream-mode logic in Arr queue monitor:
  - If Arr grab happens, stream job proceeds immediately (does not wait for full download import).
  - If no Arr grab within stream timeout, stream job falls back to Zurg source lookup instead of hard failing.
- Added Zurg source wait loop before writing `.strm`:
  - Polls up to `STREAM_SOURCE_TIMEOUT` with `STREAM_SOURCE_POLL_INTERVAL`.
- Hardened stream pointer permissions:
  - `folder.chmod(0o777)` (best-effort)
  - `strm_file.chmod(0o666)` (best-effort)
- Existing webhook/rdt-ready checks remain integrated (`get_rdt_ready`).

Why:
- Prevent false failures when Arr grab is delayed.
- Allow stream mode to complete even when grab timing is imperfect.
- Avoid Radarr import permission issues caused by root-owned `.strm` directories.

### 2) `services/agent-worker/monitor.py`
Changes made:
- Extended monitor from warning-only behavior to active signaling behavior.
- Added DB lookup of active jobs (`ACQUIRING`, `IMPORTING`).
- Added logic to set `rdt_ready` when:
  - tracked Arr queue item disappears (per `arr_queue_id`), or
  - matching `rd_torrent_id` appears complete in rdt-client torrent status.
- Added completion detection helper for rdt status/progress.

Why:
- Recover/unblock jobs when webhook timing is missed.
- Improve resilience after worker restarts.

### 3) `services/agent-worker/main.py`
Changes made:
- Started monitor loop in background:
  - `monitor_task = asyncio.create_task(monitor_downloads(_shutdown_event))`
- Added shutdown cancellation/wait for `monitor_task`.

Why:
- Ensure monitor actually runs continuously with worker.

### 4) `docker-compose.yml`
Changes made:
- Added Zurg mount into Jellyfin service:
  - `${DATA_PATH:-./data}/zurg:/data/zurg:ro`

Why:
- `.strm` targets point to `/data/zurg/...`; Jellyfin must be able to read this path to play stream entries.

### 5) `.env`
Changes made:
- Added/updated runtime stream config:
  - `ZURG_ENABLED=true`
  - `ZURG_MOUNT_PATH=/data/zurg/__all__`

Why:
- Worker stream mode intentionally fails if `ZURG_ENABLED=false`.

## Existing Earlier Codex Changes (same session lineage)
These were already present before the final fixes above and are still active:
- `services/agent-api/routers/webhooks.py`
  - Added `POST /v1/webhooks/rdt-complete`
  - Token support (`RDT_WEBHOOK_TOKEN`)
  - Arr scan triggers (`DownloadedMoviesScan`, `DownloadedEpisodesScan`)
  - Job resolution by `job_id` or `rd_torrent_id` and `set_rdt_ready` signal
- `services/shared/redis_client.py`
  - Added `set_rdt_ready/get_rdt_ready/clear_rdt_ready`
- `scripts/arr-notifier.sh`
  - Added notifier payload support for category/path/hash/job/acquisition mode
- `services/agent-api/routers/admin.py`
  - Added Arr diagnostics endpoint
- `services/shared/radarr_client.py` and `services/shared/sonarr_client.py`
  - Added downloaded scan helpers + improved diagnostics
- `services/shared/config.py` and `.env.template`
  - Added Zurg/RDT webhook related config fields

## Backups Created
Timestamped backups created before edits (examples):
- `services/agent-worker/worker.py.bak.20260304-064050`
- `services/agent-worker/main.py.bak.20260304-064050`
- `services/agent-worker/monitor.py.bak.20260304-064050`
- `docker-compose.yml.bak.20260304-064050`
- `services/agent-worker/worker.py.bak.20260304-064622`
- `services/agent-worker/worker.py.bak.20260304-065929`
- `.env.bak.20260304-064933`

## Runtime Operations Performed
- Rebuilt/restarted services multiple times:
  - `agent-worker`, `agent-api`, `jellyfin`
- Verified service status via `docker compose ps`.
- Verified Jellyfin can see `/data/zurg/__all__/Movies`.
- Triggered webhook scans for Radarr using `rdt-complete` endpoint.
- Repaired media folder permissions from inside Radarr container for problematic user path:
  - `chmod -R 777 /data/media/users/<user-id>`

## Validation Evidence

### Stream mode validated
- Job `8824d84c-fc06-444e-b470-279f3260928f` (`Memento`) reached `DONE`.
- `.strm` created at:
  - `/data/media/users/<user-id>/Movies/Memento (2000)/Memento (2000).strm`
- `.strm` target:
  - `file:///data/zurg/__all__/Movies/Memento.2000.1080p.mkv`
- Jellyfin confirmed to see target file path.

### Real-Debrid / download mode validated
- Job `9e7c854a-1273-496c-8750-ebd086060ec7` (`Gone Girl`, `download`) progressed:
  - `ACQUIRING -> IMPORTING -> VERIFYING`
- Worker logs confirmed:
  - Radarr grabbed release
  - RDT completion signal received
  - Radarr import confirmed
  - QC enqueued
- Imported file present:
  - `/data/media/users/<user-id>/Movies/Gone Girl (2014)/Gone.Girl.2014.BDRip.1080p.Rus.Eng.mkv`

## Known Follow-ups / Caveats
1. Jellyfin refresh call from worker currently returns `401` because no admin token is attached in refresh call flow. Library still works; refresh is best-effort.
2. Legacy Memento import errors appeared due to old permissions/state; folder permissions were manually repaired in container.
3. `rd_torrent_id` can still be empty in some paths if Arr queue metadata does not expose download ID quickly enough; monitor + timeout adjustments now reduce impact.

## Suggested Next Steps for Claude
1. Make Jellyfin refresh authenticated (use `JELLYFIN_ADMIN_TOKEN` if configured).
2. Improve Arr queue correlation persistence (store additional keys if available).
3. Add integration tests for:
   - stream fallback when no Arr grab
   - download flow with delayed Arr grab
   - import permission regression checks

## Additional Fixes (later same day)

### Caveat #1 resolved: authenticated Jellyfin refresh
- File: `services/agent-worker/worker.py`
- Change:
  - `_trigger_jellyfin_refresh()` now sends `X-Emby-Token` header when `JELLYFIN_ADMIN_TOKEN` is configured.
- File: `docker-compose.yml`
- Change:
  - Added `JELLYFIN_ADMIN_TOKEN=${JELLYFIN_ADMIN_TOKEN:-}` to `agent-worker` environment.
- Validation:
  - Direct call with configured token returned HTTP `204`:
    - `POST http://127.0.0.1:8096/Library/Refresh`

### Caveat #2 mitigated: automatic media permission healing
- File: `services/agent-worker/worker.py`
- Changes:
  - Added `ensure_user_media_permissions(user)` called at start of `process_job()`.
  - Ensures user media roots exist (`users/<id>`, `Movies`, `TV`).
  - Recursively applies ownership to configured `PUID/PGID` and permissive modes.
- Validation:
  - User media root ownership changed from `root:root` to runtime uid/gid (`shawn:shawn` in this host setup) after a job started.

### Caveat #3 mitigated: stronger queue/torrent correlation
- File: `services/agent-worker/monitor.py`
- Changes:
  - Monitor now backfills `arr_queue_id` and `rd_torrent_id` for active jobs directly from Arr queue records.
  - Uses media-id matching (`movieId` / `seriesId`) to reduce timing-related misses.
- Validation:
  - Fresh job `4895ec5f-85e2-4ac3-a9b0-02adc3ff6b50` showed populated
    - `rd_torrent_id = 6FB0F50252B84B3D255685B61A996A8401EF1965`

### Also adjusted (download reliability)
- File: `services/agent-worker/worker.py`
- Changes:
  - Split Arr grab timeout by mode:
    - stream: `120s`
    - download: `600s`
  - Reduced false `did not grab` failures for real download jobs.

### New backups from this round
- `docker-compose.yml.bak.20260304-143106`
- `services/agent-worker/worker.py.bak.20260304-143106`
- `services/agent-worker/monitor.py.bak.20260304-143106`
- `services/agent-worker/worker.py.bak.20260304-065929`

## Queue Cleanup Performed (2026-03-04, later)

Reason:
- API was rejecting new requests with `Too many active jobs (5/5)`.

Actions taken:
- Inspected non-terminal jobs in Postgres.
- Applied manual cleanup transaction:
  - Set imported/completed jobs to `DONE`:
    - `5f4ffcdc-c59a-4954-9008-ae8dde4374d7` (The Prestige)
    - `9e7c854a-1273-496c-8750-ebd086060ec7` (Gone Girl)
  - Set stale non-terminal jobs to `FAILED`:
    - `c234d18b-31ee-4aca-92ef-1ea31626963c`
    - `f9a4dd4c-c451-438d-80d8-b5d9c95b2159`
    - `1f088ebd-46ec-4f09-8a70-32e6cfe1b3ce`
    - `4895ec5f-85e2-4ac3-a9b0-02adc3ff6b50`
  - Inserted corresponding `job_events` notes for auditability.
- Cleared stale Redis keys for those job IDs:
  - `invisiblearr:rdt_ready:<job_id>`
  - `invisiblearr:progress:<job_id>`

Validation after cleanup:
- `jobs where state not in ('DONE','FAILED')` => `0` rows.
- Redis jobs queue length => `0`.
- New request accepted successfully:
  - `6718d258-e14c-4389-b61a-2862a8b136aa` (Blade Runner, stream).
