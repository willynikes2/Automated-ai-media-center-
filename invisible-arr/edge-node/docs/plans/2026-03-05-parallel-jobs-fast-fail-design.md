# Parallel Job Processing + Fast-Fail for Unavailable Content

Date: 2026-03-05
Status: Approved

## Problem

1. Unreleased/unavailable content blocks the job queue for up to 10 minutes (ARR_GRAB_TIMEOUT_DOWNLOAD = 600s)
2. Serial job processing means one stuck job blocks all others
3. Users see "Failed" on Activity page with no explanation

## Solution

### 1. Parallel Job Processing

Replace sequential `await process_job()` in the consumer loop with a concurrent worker pool.

- `MAX_CONCURRENT_JOBS` env var, default 3
- Consumer loop keeps dequeuing, spawns `asyncio.create_task()` per job
- `asyncio.Semaphore(MAX_CONCURRENT_JOBS)` gates entry to `process_job()`
- Track active tasks in a set; clean up on completion
- Graceful shutdown waits for all in-flight tasks (with timeout)

### 2. Fast-Fail for Unavailable Content

Two-layer detection:

1. **Instant fail for unreleased content**
   - Movies: after adding to Radarr, check `movie.status`. If `"announced"` or `"inCinemas"` (no digital release), fail immediately with "Movie not yet released for download"
   - TV: check if season/episode `airDateUtc` is in the future, fail with "Episode has not aired yet"

2. **Reduced grab timeout**
   - Lower `ARR_GRAB_TIMEOUT_DOWNLOAD` from 600s to 120s
   - If Radarr/Sonarr hasn't grabbed within 2 minutes, content is likely unavailable
   - Retry system still handles edge cases

### 3. Activity Page Error Display

- Surface failure reason from `job_events` table on Activity page
- Show inline on the job card (e.g. "Not yet released", "No downloads found")
- Frontend change to Activity job row component

### 4. Roadmap: Real-Time Toast Notifications (future)

- WebSocket/SSE push notifications for job state changes
- Not in scope for this change

## Files Modified

| File | Change |
|------|--------|
| `services/agent-worker/main.py` | Concurrent consumer loop with semaphore |
| `services/agent-worker/worker.py` | Radarr/Sonarr status checks, reduced grab timeout |
| `services/frontend/src/components/activity/*` | Display error reason on failed jobs |
| `services/agent-api/` | Expose error reason in job response (if not already) |

## What Won't Change

- Redis queue structure (still FIFO list)
- Retry/smart-retry system
- QC pipeline
- Download monitor task
