# Parallel Job Processing + Fast-Fail Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Process multiple jobs concurrently (up to 3) so one stuck job doesn't block others, fail instantly for unreleased content, reduce grab timeout from 600s to 120s, and show error reasons on the Activity page.

**Architecture:** Replace the sequential consumer loop in main.py with a semaphore-gated task spawner. Add Radarr/Sonarr status checks in worker.py before entering the grab poll loop. Add a `last_error` field to the job list API response and display it on the Activity page.

**Tech Stack:** Python asyncio (Semaphore, create_task), FastAPI, React/TypeScript

---

### Task 1: Parallel Job Processing — Worker Pool in main.py

**Files:**
- Modify: `services/agent-worker/main.py:30-31` (add constant)
- Modify: `services/agent-worker/main.py:64-139` (rewrite consumer loop)

**Step 1: Add MAX_CONCURRENT_JOBS constant**

In `main.py` after line 31, add:

```python
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "3"))
```

**Step 2: Rewrite the consumer loop in `_run()`**

Replace lines 86-139 (from `# Consumer loop` through shutdown cleanup) with:

```python
    # Consumer loop ----------------------------------------------------------
    logger.info("Entering job consumer loop (max_concurrent=%d)", MAX_CONCURRENT_JOBS)
    monitor_task = asyncio.create_task(monitor_downloads(_shutdown_event))
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
    active_tasks: set[asyncio.Task] = set()

    def _task_done(task: asyncio.Task) -> None:
        active_tasks.discard(task)
        if task.exception() and not task.cancelled():
            logger.exception(
                "Job task raised unhandled exception",
                exc_info=task.exception(),
            )

    async def _run_job(job_id: str) -> None:
        async with semaphore:
            try:
                await process_job(job_id)
                try:
                    job = await get_job(job_id)
                    if job.state in (JobState.DONE, JobState.FAILED):
                        logger.info("Job %s finished with state %s", job_id, job.state.value)
                    elif job.state == JobState.VERIFYING:
                        logger.info("Job %s handed off to QC (state=VERIFYING)", job_id)
                    else:
                        logger.warning("Job %s ended in unexpected state %s", job_id, job.state.value)
                except Exception:
                    logger.info("Job %s processing returned without error", job_id)
            except Exception:
                logger.exception("Unhandled exception while processing job %s", job_id)
                try:
                    await _fail_job(job_id)
                except Exception:
                    logger.exception("Could not transition job %s to FAILED", job_id)

            # Check retry regardless of outcome
            try:
                await _maybe_retry(job_id)
            except Exception:
                logger.exception("Error checking retry for job %s", job_id)

    while not _shutdown_event.is_set():
        try:
            job_id = await dequeue_job(timeout=2)
        except Exception:
            logger.exception("Error dequeueing job, retrying in 5s")
            await asyncio.sleep(5)
            continue

        if job_id is None:
            continue

        logger.info("Dequeued job %s (%d/%d slots in use)", job_id, MAX_CONCURRENT_JOBS - semaphore._value, MAX_CONCURRENT_JOBS)
        task = asyncio.create_task(_run_job(job_id), name=f"job-{job_id[:8]}")
        active_tasks.add(task)
        task.add_done_callback(_task_done)

    # Shutdown cleanup -------------------------------------------------------
    if active_tasks:
        logger.info("Waiting for %d active job(s) to finish...", len(active_tasks))
        done, pending = await asyncio.wait(active_tasks, timeout=30)
        for t in pending:
            logger.warning("Cancelling job task %s (shutdown timeout)", t.get_name())
            t.cancel()
        if pending:
            await asyncio.wait(pending, timeout=5)

    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

    logger.info("Shutting down agent-worker")
    await redis.aclose()
    engine = get_engine()
    await engine.dispose()
    logger.info("Resources released, goodbye")
```

**Step 3: Verify — rebuild and check startup log**

```bash
docker compose build agent-worker && docker compose up -d agent-worker
docker logs agent-worker --tail=10
```

Expected: `"Entering job consumer loop (max_concurrent=3)"`

**Step 4: Commit**

```bash
git add services/agent-worker/main.py
git commit -m "feat: parallel job processing with configurable concurrency"
```

---

### Task 2: Fast-Fail — Unreleased Content Detection

**Files:**
- Modify: `services/agent-worker/worker.py:48-50` (reduce grab timeout)
- Modify: `services/agent-worker/worker.py:522-582` (`_monitor_radarr_download`)
- Modify: `services/agent-worker/worker.py:585-648` (`_monitor_sonarr_download`)

**Step 1: Reduce ARR_GRAB_TIMEOUT_DOWNLOAD**

In `worker.py`, change line 50:

```python
# Before:
ARR_GRAB_TIMEOUT_DOWNLOAD = 600
# After:
ARR_GRAB_TIMEOUT_DOWNLOAD = 120
```

**Step 2: Add unreleased movie detection to `_monitor_radarr_download`**

Insert after line 535 (`logger.info("Waiting for Radarr to grab...")`), before the grab timeout calculation:

```python
        # Fast-fail: check if movie is released
        movie_info = await radarr.get_movie(movie_id)
        movie_status = movie_info.get("status", "")
        if movie_status in ("announced", "inCinemas"):
            status_label = "in cinemas only" if movie_status == "inCinemas" else "announced but not released"
            raise RuntimeError(
                f"Movie is {status_label} — no digital release available for download"
            )
```

**Step 3: Add unaired episode detection to `_monitor_sonarr_download`**

Insert after line 596 (`logger.info("Waiting for Sonarr to grab...")`), before the grab timeout calculation:

```python
        # Fast-fail: check if episode has aired
        if job.season is not None and job.episode is not None:
            episodes = await sonarr.get_episodes(series_id, job.season)
            target_ep = next(
                (e for e in episodes if e.get("episodeNumber") == job.episode),
                None,
            )
            if target_ep:
                air_date = target_ep.get("airDateUtc")
                if air_date:
                    from datetime import datetime, timezone
                    try:
                        aired = datetime.fromisoformat(air_date.replace("Z", "+00:00"))
                        if aired > datetime.now(timezone.utc):
                            raise RuntimeError(
                                f"Episode has not aired yet (airs {aired.strftime('%Y-%m-%d')})"
                            )
                    except (ValueError, TypeError):
                        pass  # Malformed date — proceed normally
```

**Step 4: Verify — rebuild and test with an unreleased movie**

```bash
docker compose build agent-worker && docker compose up -d agent-worker
```

Test by requesting a known unreleased movie. Check logs for instant failure:

```bash
docker logs agent-worker --since=30s --tail=20
```

Expected: `"Movie is announced but not released"` → FAILED within seconds, not 120s.

**Step 5: Commit**

```bash
git add services/agent-worker/worker.py
git commit -m "feat: fast-fail for unreleased movies/unaired episodes, reduce grab timeout to 120s"
```

---

### Task 3: API — Add `last_error` to Job List Response

**Files:**
- Modify: `services/shared/schemas.py:93-113` (add field to `JobListResponse`)
- Modify: `services/agent-api/routers/jobs.py:78-123` (populate field from job_events)

**Step 1: Add `last_error` field to `JobListResponse`**

In `schemas.py`, add to `JobListResponse` class after line 112 (`retry_count`):

```python
    last_error: str | None = None
```

**Step 2: Populate `last_error` from job_events in list endpoint**

In `jobs.py`, modify the list endpoint. Replace lines 87-99 with:

```python
    async with get_session_factory()() as session:
        stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)

        if status is not None:
            stmt = stmt.where(Job.state == status)

        if not (user.role == "admin" and all_users):
            stmt = stmt.where(Job.user_id == user.id)

        # Eagerly load events for FAILED jobs to extract last_error
        from sqlalchemy.orm import selectinload
        stmt = stmt.options(selectinload(Job.events))

        result = await session.execute(stmt)
        jobs: list[Job] = list(result.scalars().all())
```

Then update the response construction (lines 101-123). Replace with:

```python
    def _last_error(j: Job) -> str | None:
        if j.state != JobState.FAILED or not j.events:
            return None
        # Find the most recent FAILED event
        failed_events = [e for e in j.events if e.state == JobState.FAILED.value]
        if failed_events:
            return max(failed_events, key=lambda e: e.created_at).message
        return None

    return [
        JobListResponse(
            id=j.id,
            user_id=j.user_id,
            title=j.title,
            query=j.query,
            tmdb_id=j.tmdb_id,
            media_type=j.media_type,
            season=j.season,
            episode=j.episode,
            state=j.state,
            selected_candidate=j.selected_candidate,
            rd_torrent_id=j.rd_torrent_id,
            imported_path=j.imported_path,
            acquisition_mode=j.acquisition_mode,
            acquisition_method=j.acquisition_method,
            streaming_urls=j.streaming_urls,
            retry_count=j.retry_count,
            last_error=_last_error(j),
            created_at=j.created_at,
            updated_at=j.updated_at,
        )
        for j in jobs
    ]
```

**Step 3: Verify — rebuild API and check response**

```bash
docker compose build agent-api && docker compose up -d agent-api
```

Test with curl or browser — check that failed jobs now include `last_error` in the JSON.

**Step 4: Commit**

```bash
git add services/shared/schemas.py services/agent-api/routers/jobs.py
git commit -m "feat: include last_error in job list API response"
```

---

### Task 4: Frontend — Display Error Reason on Activity Page

**Files:**
- Modify: `services/frontend/src/api/jobs.ts:17-36` (add field to Job interface)
- Modify: `services/frontend/src/pages/ActivityPage.tsx:116-164` (display error)

**Step 1: Add `last_error` to the `Job` TypeScript interface**

In `jobs.ts`, add after line 34 (`updated_at: string;`):

```typescript
  last_error: string | null;
```

**Step 2: Add friendly error mapping and display to `CompletedRow`**

In `ActivityPage.tsx`, add a helper before the `CompletedRow` function (before line 116):

```typescript
function friendlyError(raw: string | null): string | null {
  if (!raw) return null;
  if (raw.includes('announced but not released')) return 'Not yet released';
  if (raw.includes('in cinemas only')) return 'In cinemas only';
  if (raw.includes('not aired yet')) return 'Not aired yet';
  if (raw.includes('did not grab a release')) return 'No downloads available';
  if (raw.includes('Import verification')) return 'Import failed';
  if (raw.includes('Download stalled')) return 'Download stalled';
  if (raw.includes('Download failed')) return 'Download failed';
  return raw.length > 40 ? raw.slice(0, 40) + '...' : raw;
}
```

Then in the `CompletedRow` component, replace lines 140-145 (the subtitle `<p>` tag) with:

```tsx
        <p className="text-[10px] text-text-tertiary">
          {job.media_type === 'tv' ? 'TV' : 'Movie'}
          {' · '}
          {new Date(job.updated_at).toLocaleDateString()}
          {isFailed && job.last_error && (
            <span className="text-status-failed"> · {friendlyError(job.last_error)}</span>
          )}
          {isFailed && !job.last_error && job.retry_count > 0 && ` · ${job.retry_count} retries`}
        </p>
```

**Step 3: Verify — rebuild frontend and check Activity page**

```bash
docker compose build frontend && docker compose up -d frontend
```

Navigate to Activity page. Failed jobs should show error reason (e.g. "Not yet released").

**Step 4: Commit**

```bash
git add services/frontend/src/api/jobs.ts services/frontend/src/pages/ActivityPage.tsx
git commit -m "feat: display error reason on Activity page for failed jobs"
```

---

### Task 5: Add Toast Notifications to Roadmap

**Files:**
- Modify: `docs/ROADMAP_STREAMING.md` or create `docs/ROADMAP.md`

**Step 1: Add roadmap item**

Append to roadmap doc:

```markdown
## Real-Time Toast Notifications (Future)

Status: PLANNED

Push real-time notifications to users when job state changes (especially failures).
Requires WebSocket or SSE infrastructure from agent-api to frontend.

### Use Cases
- Job fails: toast with friendly error (e.g. "Scream 7: Not yet released")
- Job completes: toast with "Movie ready to watch"
- Download progress: optional progress bar in header

### Implementation Notes
- Add WebSocket endpoint to agent-api (FastAPI WebSocket support)
- Worker publishes state changes to Redis pub/sub
- API subscribes and pushes to connected clients
- Frontend: connect on mount, show toast on message
```

**Step 5: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs: add real-time toast notifications to roadmap"
```

---

### Task 6: Integration Test — Verify Everything Works Together

**Step 1: Verify parallel processing**

Submit 3 requests simultaneously (one unreleased, two available). Confirm:
- Unreleased movie fails instantly (seconds, not minutes)
- Both available movies process in parallel (check logs for interleaved job IDs)
- Activity page shows error reason for the failed job

**Step 2: Verify no regressions**

- Check existing completed jobs still show correctly
- Check retry button still works on failed jobs
- Check job detail page still loads with events

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: parallel jobs, fast-fail, error display — integration verified"
```
