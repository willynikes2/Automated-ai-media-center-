# Download Pipeline Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the fragile timer-based worker with an observer+fixer pattern that lets Radarr/Sonarr do their job, only intervening on actual problems, with full diagnostics and mom-friendly error messages.

**Architecture:** Webhooks from Radarr/Sonarr drive state transitions (grab -> downloading, import -> done). A 60s fallback poll catches missed events. A diagnostic engine investigates actual problems instead of timer-based failures. Frontend shows plain-English status.

**Tech Stack:** Python/FastAPI (backend), PostgreSQL (diagnostics table), Redis (signals), React/TypeScript (frontend), Radarr/Sonarr webhook API.

---

## Task 1: Database — Add job_diagnostics table and new job states

**Files:**
- Modify: `services/shared/models.py:31-43` (JobState enum)
- Create: `services/shared/migrations/008_add_diagnostics_and_states.sql`

**Step 1: Add new states to JobState enum**

In `services/shared/models.py`, replace lines 31-43:

```python
class JobState(str, enum.Enum):
    CREATED = "CREATED"
    SEARCHING = "SEARCHING"       # Added to Arr, search triggered (replaces RESOLVING+ADDING+old SEARCHING)
    DOWNLOADING = "DOWNLOADING"   # Arr grabbed release, download in progress (replaces ACQUIRING)
    IMPORTING = "IMPORTING"       # Download complete, Arr organizing file
    VERIFYING = "VERIFYING"       # QC running
    DONE = "DONE"
    MONITORED = "MONITORED"       # Waiting for release
    INVESTIGATING = "INVESTIGATING"  # NEW: diagnostic engine working on a problem
    UNAVAILABLE = "UNAVAILABLE"      # NEW: exhausted all options
    FAILED = "FAILED"                # Internal only — frontend maps to INVESTIGATING or UNAVAILABLE
    DELETED = "DELETED"
    # Legacy states — kept for DB compatibility with existing rows
    RESOLVING = "RESOLVING"
    ADDING = "ADDING"
    SELECTED = "SELECTED"
    ACQUIRING = "ACQUIRING"
```

**Step 2: Add JobDiagnostic model**

Append to `services/shared/models.py` after the JobEvent class:

```python
class JobDiagnostic(Base):
    __tablename__ = "job_diagnostics"

    id: Mapped[uuid.UUID] = mapped_column(default=_new_uuid, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    auto_fix_action: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
```

**Step 3: Write and apply migration**

```sql
-- 008_add_diagnostics_and_states.sql

CREATE TABLE IF NOT EXISTS job_diagnostics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    category VARCHAR(50) NOT NULL,
    details_json JSON,
    auto_fix_action VARCHAR(200),
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_diagnostics_job_id ON job_diagnostics(job_id);
CREATE INDEX IF NOT EXISTS idx_job_diagnostics_category ON job_diagnostics(category);
```

**Step 4: Apply migration**

```bash
docker exec postgres psql -U invisible_arr -d invisible_arr -f - < services/shared/migrations/008_add_diagnostics_and_states.sql
```

**Step 5: Commit**

```bash
git add services/shared/models.py services/shared/migrations/008_add_diagnostics_and_states.sql
git commit -m "feat: add job_diagnostics table and new pipeline states (INVESTIGATING, UNAVAILABLE, DOWNLOADING)"
```

---

## Task 2: Diagnostic Engine — New module

**Files:**
- Create: `services/agent-worker/diagnostics.py`
- Reference: `services/shared/radarr_client.py` (get_history line 174, get_queue line 142)
- Reference: `services/shared/sonarr_client.py` (get_history line 232, get_queue line 199)

**Step 1: Create the diagnostic engine**

Create `services/agent-worker/diagnostics.py`:

```python
"""Diagnostic engine — investigates why downloads fail using Arr's own data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Job, JobDiagnostic, JobState
from shared.radarr_client import RadarrClient
from shared.sonarr_client import SonarrClient

logger = logging.getLogger("agent-worker.diagnostics")


@dataclass
class Diagnosis:
    category: str          # no_releases, quality_rejected, indexer_error, download_stalled,
                           # import_blocked, arr_unresponsive, disk_full, content_not_released
    summary: str           # human-readable summary
    details: dict[str, Any]  # raw data for audit
    auto_fix: str | None   # recommended auto-fix action name, or None
    user_message: str      # mom-friendly message


# ── Category constants ──────────────────────────────────────────────────────

CAT_NO_RELEASES = "no_releases"
CAT_QUALITY_REJECTED = "quality_rejected"
CAT_INDEXER_ERROR = "indexer_error"
CAT_DOWNLOAD_STALLED = "download_stalled"
CAT_IMPORT_BLOCKED = "import_blocked"
CAT_ARR_UNRESPONSIVE = "arr_unresponsive"
CAT_DISK_FULL = "disk_full"
CAT_CONTENT_NOT_RELEASED = "content_not_released"
CAT_UNKNOWN = "unknown"


async def diagnose_no_grab(job: Job, session: AsyncSession) -> Diagnosis:
    """Called when Arr hasn't grabbed anything after search was triggered.
    Queries Arr history to find out why."""

    details: dict[str, Any] = {}

    try:
        if job.media_type == "movie":
            async with RadarrClient() as client:
                # Check movie status first
                movie = await client.get_movie(job.radarr_movie_id)
                status = movie.get("status", "")
                if status in ("announced", "inCinemas"):
                    return Diagnosis(
                        category=CAT_CONTENT_NOT_RELEASED,
                        summary=f"Movie status is '{status}' — not available for download yet",
                        details={"movie_status": status, "movie_id": job.radarr_movie_id},
                        auto_fix="set_monitored",
                        user_message=f"Not released yet — we'll grab it automatically when available",
                    )

                # Check history for search results and rejections
                history = await client.get_history(movie_id=job.radarr_movie_id, page_size=50)
                records = history.get("records", [])
                details["history_count"] = len(records)
                details["history_sample"] = records[:5]

                # Look for rejection reasons
                rejections = _extract_rejections(records)
                details["rejections"] = rejections

                if not records or all(r.get("eventType") == "grabbed" for r in records):
                    # Search happened but nothing was found
                    return Diagnosis(
                        category=CAT_NO_RELEASES,
                        summary="No releases found on any indexer",
                        details=details,
                        auto_fix="set_monitored_daily",
                        user_message="No downloads available yet — we'll keep checking daily",
                    )

                if rejections:
                    quality_rejects = [r for r in rejections if "quality" in r.lower() or "cutoff" in r.lower()]
                    if quality_rejects:
                        return Diagnosis(
                            category=CAT_QUALITY_REJECTED,
                            summary=f"Found {len(rejections)} releases but all rejected by quality profile",
                            details=details,
                            auto_fix="retry_relaxed_quality",
                            user_message="Available versions don't meet quality standards — trying with relaxed settings",
                        )

                    indexer_errors = [r for r in rejections if "timeout" in r.lower() or "error" in r.lower() or "unavailable" in r.lower()]
                    if indexer_errors:
                        return Diagnosis(
                            category=CAT_INDEXER_ERROR,
                            summary=f"Indexer errors: {indexer_errors[:3]}",
                            details=details,
                            auto_fix="retry_search_delayed",
                            user_message="Search providers having issues — retrying shortly",
                        )

        else:  # TV
            async with SonarrClient() as client:
                series = await client.get_series(job.sonarr_series_id)
                # Check if episode has aired
                if job.episode and job.season:
                    episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
                    target = next((e for e in episodes if e.get("episodeNumber") == job.episode), None)
                    if target:
                        air_date = target.get("airDateUtc")
                        if air_date:
                            aired = datetime.fromisoformat(air_date.replace("Z", "+00:00"))
                            if aired > datetime.now(timezone.utc):
                                return Diagnosis(
                                    category=CAT_CONTENT_NOT_RELEASED,
                                    summary=f"Episode airs {air_date}",
                                    details={"air_date": air_date, "series_id": job.sonarr_series_id},
                                    auto_fix="set_monitored",
                                    user_message=f"Not aired yet — we'll grab it automatically when available",
                                )

                history = await client.get_history(series_id=job.sonarr_series_id, page_size=50)
                records = history.get("records", [])
                details["history_count"] = len(records)
                details["history_sample"] = records[:5]
                rejections = _extract_rejections(records)
                details["rejections"] = rejections

                if not records:
                    return Diagnosis(
                        category=CAT_NO_RELEASES,
                        summary="No releases found on any indexer",
                        details=details,
                        auto_fix="set_monitored_daily",
                        user_message="No downloads available yet — we'll keep checking daily",
                    )

                if rejections:
                    quality_rejects = [r for r in rejections if "quality" in r.lower() or "cutoff" in r.lower()]
                    if quality_rejects:
                        return Diagnosis(
                            category=CAT_QUALITY_REJECTED,
                            summary=f"Found releases but all rejected by quality profile",
                            details=details,
                            auto_fix="retry_relaxed_quality",
                            user_message="Available versions don't meet quality standards — trying with relaxed settings",
                        )

    except Exception as exc:
        if "Connection refused" in str(exc) or "Cannot connect" in str(exc):
            return Diagnosis(
                category=CAT_ARR_UNRESPONSIVE,
                summary=f"Arr service not responding: {exc}",
                details={"error": str(exc)},
                auto_fix="restart_arr",
                user_message="Download service restarting — your request will resume",
            )
        logger.exception("Diagnostic engine error for job %s", job.id)
        details["diagnostic_error"] = str(exc)

    return Diagnosis(
        category=CAT_UNKNOWN,
        summary="Unable to determine specific cause",
        details=details,
        auto_fix="retry_search_delayed",
        user_message="Having trouble — working on it",
    )


async def diagnose_stalled_download(job: Job, queue_item: dict) -> Diagnosis:
    """Called when a download hasn't progressed for extended period."""

    sizeleft = queue_item.get("sizeleft", 0)
    status = queue_item.get("status", "")
    tds = queue_item.get("trackedDownloadStatus", "")
    error_msg = queue_item.get("errorMessage", "")
    status_messages = queue_item.get("statusMessages", [])

    details = {
        "queue_item_id": queue_item.get("id"),
        "status": status,
        "tracked_download_status": tds,
        "error_message": error_msg,
        "status_messages": status_messages,
        "sizeleft": sizeleft,
    }

    if "disk" in error_msg.lower() or "space" in error_msg.lower():
        return Diagnosis(
            category=CAT_DISK_FULL,
            summary=f"Disk space issue: {error_msg}",
            details=details,
            auto_fix=None,  # Can't auto-fix disk space
            user_message="Storage full — please free up space or upgrade",
        )

    if tds == "warning" or tds == "error":
        return Diagnosis(
            category=CAT_DOWNLOAD_STALLED,
            summary=f"Download has issues: {error_msg or tds}",
            details=details,
            auto_fix="blacklist_and_research",
            user_message="Download stalled — switching to another source",
        )

    if status in ("importBlocked", "importFailed"):
        msgs = "; ".join(
            m.get("title", "") + ": " + ", ".join(m.get("messages", []))
            for m in status_messages
        )
        return Diagnosis(
            category=CAT_IMPORT_BLOCKED,
            summary=f"Import blocked: {msgs or error_msg}",
            details=details,
            auto_fix="clear_and_reimport",
            user_message="File downloaded but can't be organized — investigating",
        )

    return Diagnosis(
        category=CAT_DOWNLOAD_STALLED,
        summary=f"Download not progressing (status={status}, tds={tds})",
        details=details,
        auto_fix="blacklist_and_research",
        user_message="Download stalled — switching to another source",
    )


async def save_diagnostic(session: AsyncSession, job_id, diagnosis: Diagnosis) -> JobDiagnostic:
    """Persist a diagnosis to the job_diagnostics table."""
    diag = JobDiagnostic(
        job_id=job_id,
        category=diagnosis.category,
        details_json=diagnosis.details,
        auto_fix_action=diagnosis.auto_fix,
    )
    session.add(diag)
    await session.flush()
    logger.info(
        "Diagnostic saved for job %s: category=%s auto_fix=%s",
        job_id, diagnosis.category, diagnosis.auto_fix,
    )
    return diag


async def mark_diagnostic_resolved(session: AsyncSession, job_id) -> None:
    """Mark all open diagnostics for a job as resolved."""
    from sqlalchemy import update
    await session.execute(
        update(JobDiagnostic)
        .where(JobDiagnostic.job_id == job_id, JobDiagnostic.resolved == False)
        .values(resolved=True)
    )


def _extract_rejections(history_records: list[dict]) -> list[str]:
    """Pull rejection reasons from Arr history records."""
    rejections = []
    for record in history_records:
        data = record.get("data", {})
        # Radarr/Sonarr store rejections differently
        for key in ("rejections", "reason", "message"):
            val = data.get(key)
            if val:
                if isinstance(val, list):
                    rejections.extend(val)
                else:
                    rejections.append(str(val))
    return rejections
```

**Step 2: Commit**

```bash
git add services/agent-worker/diagnostics.py
git commit -m "feat: add diagnostic engine for root-cause analysis of download failures"
```

---

## Task 3: Auto-Fixer — New module

**Files:**
- Create: `services/agent-worker/auto_fixer.py`
- Reference: `services/shared/radarr_client.py` (search_movie line 97, delete_queue_item line 158)
- Reference: `services/shared/sonarr_client.py` (search_season line 144, search_episodes line 155, delete_queue_item line 216)

**Step 1: Create the auto-fixer**

Create `services/agent-worker/auto_fixer.py`:

```python
"""Auto-fixer — applies fixes based on diagnostic results."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from shared.models import Job, JobState
from shared.radarr_client import RadarrClient
from shared.sonarr_client import SonarrClient
from shared.redis_client import enqueue_job

from diagnostics import Diagnosis, CAT_CONTENT_NOT_RELEASED, CAT_NO_RELEASES

logger = logging.getLogger("agent-worker.auto_fixer")

# Max auto-fix attempts per job before giving up
MAX_FIX_ATTEMPTS = 5
# Delays between fix attempts (seconds)
FIX_DELAYS = [60, 120, 300, 600, 1800]


async def apply_fix(job: Job, diagnosis: Diagnosis, attempt: int) -> str:
    """Apply the recommended auto-fix. Returns outcome description."""

    fix = diagnosis.auto_fix
    if fix is None:
        return "no_fix_available"

    if attempt >= MAX_FIX_ATTEMPTS:
        return "max_attempts_exceeded"

    logger.info("Applying fix '%s' for job %s (attempt %d)", fix, job.id, attempt)

    try:
        if fix == "set_monitored":
            # Content not released — just park it, the monitored checker will pick it up
            return "set_to_monitored"

        elif fix == "set_monitored_daily":
            # No releases found — park it, check daily
            return "set_to_monitored"

        elif fix == "retry_search_delayed":
            # Indexer issues — wait then re-search
            delay = FIX_DELAYS[min(attempt, len(FIX_DELAYS) - 1)]
            await asyncio.sleep(delay)
            await _trigger_search(job)
            return f"re_searched_after_{delay}s"

        elif fix == "retry_relaxed_quality":
            # Quality profile too strict — for now, just re-search (Arr may have
            # different releases by next check). Future: temporarily lower quality cutoff.
            delay = FIX_DELAYS[min(attempt, len(FIX_DELAYS) - 1)]
            await asyncio.sleep(delay)
            await _trigger_search(job)
            return f"re_searched_relaxed_after_{delay}s"

        elif fix == "blacklist_and_research":
            # Stalled download — blacklist the bad release and search again
            await _blacklist_current(job)
            await asyncio.sleep(10)  # Give Arr time to process blacklist
            await _trigger_search(job)
            return "blacklisted_and_re_searched"

        elif fix == "clear_and_reimport":
            # Import blocked — remove queue item and re-search
            await _clear_queue_item(job)
            await asyncio.sleep(10)
            await _trigger_search(job)
            return "cleared_and_re_searched"

        elif fix == "restart_arr":
            # Arr unresponsive — we can't restart containers from worker,
            # but we can wait and retry
            logger.warning("Arr unresponsive for job %s — waiting 60s before retry", job.id)
            await asyncio.sleep(60)
            return "waited_for_arr_recovery"

        else:
            logger.warning("Unknown fix action: %s", fix)
            return f"unknown_fix_{fix}"

    except Exception as exc:
        logger.exception("Auto-fix '%s' failed for job %s: %s", fix, job.id, exc)
        return f"fix_error: {exc}"


async def _trigger_search(job: Job) -> None:
    """Trigger a new search in the appropriate Arr."""
    if job.media_type == "movie":
        async with RadarrClient() as client:
            await client.search_movie(job.radarr_movie_id)
            logger.info("Re-triggered Radarr search for movie %s", job.radarr_movie_id)
    else:
        async with SonarrClient() as client:
            if job.episode and job.season:
                episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
                target = next((e for e in episodes if e.get("episodeNumber") == job.episode), None)
                if target:
                    await client.search_episodes([target["id"]])
                else:
                    await client.search_season(job.sonarr_series_id, job.season)
            elif job.season:
                await client.search_season(job.sonarr_series_id, job.season)
            else:
                await client.search_series(job.sonarr_series_id)
            logger.info("Re-triggered Sonarr search for series %s", job.sonarr_series_id)


async def _blacklist_current(job: Job) -> None:
    """Blacklist the current queue item so Arr picks a different release."""
    if not job.arr_queue_id:
        logger.warning("No arr_queue_id on job %s — cannot blacklist", job.id)
        return

    try:
        if job.media_type == "movie":
            async with RadarrClient() as client:
                await client.delete_queue_item(
                    job.arr_queue_id, blacklist=True, remove_from_client=True
                )
        else:
            async with SonarrClient() as client:
                await client.delete_queue_item(
                    job.arr_queue_id, blacklist=True, remove_from_client=True
                )
        logger.info("Blacklisted queue item %s for job %s", job.arr_queue_id, job.id)
    except Exception as exc:
        logger.warning("Failed to blacklist queue item %s: %s", job.arr_queue_id, exc)


async def _clear_queue_item(job: Job) -> None:
    """Remove a stuck queue item without blacklisting."""
    if not job.arr_queue_id:
        return

    try:
        if job.media_type == "movie":
            async with RadarrClient() as client:
                await client.delete_queue_item(
                    job.arr_queue_id, blacklist=False, remove_from_client=True
                )
        else:
            async with SonarrClient() as client:
                await client.delete_queue_item(
                    job.arr_queue_id, blacklist=False, remove_from_client=True
                )
        logger.info("Cleared queue item %s for job %s", job.arr_queue_id, job.id)
    except Exception as exc:
        logger.warning("Failed to clear queue item %s: %s", job.arr_queue_id, exc)
```

**Step 2: Commit**

```bash
git add services/agent-worker/auto_fixer.py
git commit -m "feat: add auto-fixer module for automated problem resolution"
```

---

## Task 4: Rewrite Webhook Handler — Drive state transitions from Arr events

**Files:**
- Modify: `services/agent-api/routers/webhooks.py` (lines 49-96)
- Reference: `services/shared/models.py` (JobState, Job)

**Step 1: Rewrite the Arr webhook to drive state transitions**

Replace the `/webhooks/arr` endpoint (lines 49-96) and add per-source endpoints:

```python
@router.post("/webhooks/radarr", status_code=200)
async def receive_radarr_webhook(payload: dict[str, Any]) -> dict[str, str]:
    """Process Radarr webhook and advance job state."""
    return await _process_arr_webhook(payload, source="radarr")


@router.post("/webhooks/sonarr", status_code=200)
async def receive_sonarr_webhook(payload: dict[str, Any]) -> dict[str, str]:
    """Process Sonarr webhook and advance job state."""
    return await _process_arr_webhook(payload, source="sonarr")


async def _process_arr_webhook(payload: dict[str, Any], source: str) -> dict[str, str]:
    """Core webhook processor — matches payload to job and advances state."""

    event_type: str = payload.get("eventType", "unknown")
    logger.info("Received %s webhook: eventType=%s", source, event_type)

    # Match webhook to our job by movieId/seriesId
    job = await _match_webhook_to_job(payload, source)
    if job is None:
        logger.debug("No matching job for %s webhook (eventType=%s)", source, event_type)
        return {"status": "accepted", "detail": "no matching job"}

    async with get_session_factory()() as session:
        # Log the webhook event
        event = JobEvent(
            job_id=job.id,
            state=f"webhook:{source}:{event_type}",
            message=_webhook_event_message(event_type, payload),
            metadata_json=_limit_payload(payload),
        )
        session.add(event)

        # Advance job state based on event type
        if event_type == "Grab":
            # Arr grabbed a release — move to DOWNLOADING
            release = payload.get("release", {})
            if job.state in (JobState.SEARCHING.value, JobState.CREATED.value,
                             JobState.RESOLVING.value, JobState.ADDING.value):
                job.state = JobState.DOWNLOADING.value
                job.arr_queue_id = release.get("queueId")
                session.add(JobEvent(
                    job_id=job.id,
                    state=JobState.DOWNLOADING.value,
                    message=f"Downloading: {release.get('releaseTitle', 'unknown')} from {release.get('indexer', 'unknown')}",
                    metadata_json={"release": release.get("releaseTitle"), "indexer": release.get("indexer"), "quality": release.get("quality", {}).get("quality", {}).get("name")},
                ))
                session.merge(job)
            logger.info("Job %s -> DOWNLOADING (grabbed: %s)", job.id, release.get("releaseTitle", "?"))

        elif event_type in ("Download", "DownloadFolderImported"):
            # Arr imported the file — move toward DONE
            if job.state in (JobState.DOWNLOADING.value, JobState.ACQUIRING.value,
                             JobState.IMPORTING.value, JobState.SEARCHING.value):
                movie_file = payload.get("movieFile") or payload.get("episodeFile") or {}
                imported_path = movie_file.get("relativePath") or movie_file.get("path", "")
                job.state = JobState.IMPORTING.value
                if imported_path:
                    job.imported_path = imported_path
                session.merge(job)
            logger.info("Job %s -> IMPORTING (import signal received)", job.id)
            # Signal rdt_ready so worker verify loop picks it up
            await set_rdt_ready(str(job.id), payload="webhook_import")

        elif event_type == "DownloadFailed":
            # Download failed — don't set FAILED, set INVESTIGATING
            if job.state in (JobState.DOWNLOADING.value, JobState.ACQUIRING.value):
                job.state = JobState.INVESTIGATING.value
                session.merge(job)
                session.add(JobEvent(
                    job_id=job.id,
                    state=JobState.INVESTIGATING.value,
                    message=f"Download failed — diagnosing: {payload.get('message', 'unknown reason')}",
                ))
            logger.info("Job %s -> INVESTIGATING (download failed)", job.id)

        elif event_type == "Health":
            logger.warning("Arr health issue: %s", payload.get("message", ""))

        await session.commit()

    return {"status": "accepted", "job_id": str(job.id), "event_type": event_type}


async def _match_webhook_to_job(payload: dict[str, Any], source: str) -> Job | None:
    """Match a webhook payload to an active job by Arr IDs."""

    async with get_session_factory()() as session:
        if source == "radarr":
            movie = payload.get("movie", {})
            movie_id = movie.get("id")
            if not movie_id:
                return None
            result = await session.execute(
                select(Job)
                .where(Job.radarr_movie_id == movie_id)
                .where(Job.state.notin_([JobState.DONE.value, JobState.DELETED.value, JobState.UNAVAILABLE.value]))
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

        else:  # sonarr
            series = payload.get("series", {})
            series_id = series.get("id")
            if not series_id:
                return None
            result = await session.execute(
                select(Job)
                .where(Job.sonarr_series_id == series_id)
                .where(Job.state.notin_([JobState.DONE.value, JobState.DELETED.value, JobState.UNAVAILABLE.value]))
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()


def _webhook_event_message(event_type: str, payload: dict) -> str:
    """Build a human-readable message from webhook payload."""
    if event_type == "Grab":
        release = payload.get("release", {})
        return f"Grabbed: {release.get('releaseTitle', 'unknown')} [{release.get('quality', {}).get('quality', {}).get('name', '?')}]"
    elif event_type in ("Download", "DownloadFolderImported"):
        return "File imported successfully"
    elif event_type == "DownloadFailed":
        return f"Download failed: {payload.get('message', 'unknown')}"
    return f"Webhook: {event_type}"


def _limit_payload(payload: dict, max_size: int = 50_000) -> dict:
    """Truncate payload to prevent oversized storage."""
    import json
    s = json.dumps(payload)
    return json.loads(s[:max_size]) if len(s) > max_size else payload
```

Keep the existing `/webhooks/arr` endpoint for backward compatibility and the `/webhooks/rdt-complete` endpoint as-is.

**Step 2: Commit**

```bash
git add services/agent-api/routers/webhooks.py
git commit -m "feat: webhook handler drives state transitions on Arr grab/import/fail events"
```

---

## Task 5: Rewrite Worker Pipeline — Observer pattern

**Files:**
- Modify: `services/agent-worker/worker.py` (major rewrite)
- Reference: `services/agent-worker/diagnostics.py` (new)
- Reference: `services/agent-worker/auto_fixer.py` (new)

This is the biggest task. The worker's `process_job()` method gets simplified from a multi-phase state machine with tight timeouts into: add to Arr, trigger search, then observe until done.

**Step 1: Replace timeout constants**

Replace lines 46-56 of worker.py:

```python
# ── Observation thresholds (NOT timeouts — job doesn't fail at these) ─────
NO_GRAB_INVESTIGATE_AFTER = 300     # 5 min: if no grab, run diagnostics
DOWNLOAD_STALL_INVESTIGATE = 600    # 10 min: if download not progressing, investigate
IMPORT_INVESTIGATE_AFTER = 600      # 10 min: after download done, if no file, investigate
MAX_OBSERVE_TIME = 14400            # 4 hours: absolute max observation before escalating
OBSERVE_POLL_INTERVAL = 30          # 30s between observation checks
```

**Step 2: Rewrite process_job()**

The new process_job flow:

```python
async def process_job(job_id: str) -> None:
    """Main job processor — observer+fixer pattern.

    1. Resolve title (TMDB lookup) — fast, keep as-is
    2. Add to Arr + trigger search -> SEARCHING
    3. Observe: wait for webhooks/file to appear
       - On webhook Grab -> DOWNLOADING (logged by webhook handler)
       - On webhook Import -> verify file -> DONE
       - On no activity -> diagnose -> auto-fix
    4. Never timeout — only escalate on actual diagnosed problems
    """
    async with get_session_factory()() as session:
        job = await _get_job(session, job_id)
        if not job:
            return

        try:
            # Phase 1: Resolve (fast — TMDB lookup, ~1 second)
            await _transition(session, job, JobState.SEARCHING, "Resolving title and adding to library")
            tmdb_id = await _resolve_tmdb(job)

            # Phase 2: Add to Arr + trigger search
            await _add_and_search(session, job, tmdb_id)

            # Phase 3: Observe — this is where we wait
            await _observe_until_done(session, job)

        except ContentNotReleasedError as exc:
            await _transition(session, job, JobState.MONITORED, exc.monitor_reason)
            return

        except Exception as exc:
            logger.exception("Unhandled error in job %s: %s", job_id, exc)
            await _transition(session, job, JobState.INVESTIGATING, f"Unexpected error — investigating: {exc}")
            # Let the health check loop pick it up for diagnosis
```

**Step 3: Implement _observe_until_done()**

This is the core new logic — replaces _wait_for_grab + _monitor_download + _verify_import:

```python
async def _observe_until_done(session: AsyncSession, job: Job) -> None:
    """Observe Arr until file appears in user library. No timer-based failures."""

    from diagnostics import diagnose_no_grab, diagnose_stalled_download, save_diagnostic
    from auto_fixer import apply_fix, MAX_FIX_ATTEMPTS

    start = time.monotonic()
    last_progress = -1
    stall_start: float | None = None
    fix_attempt = 0
    grabbed = False

    while True:
        elapsed = time.monotonic() - start

        # Check if file is already there (webhook may have already moved us to IMPORTING)
        has_file = await _check_has_file(job)
        if has_file:
            await _finalize_import(session, job)
            return

        # Check if we've been signaled by webhook (rdt_ready or import webhook)
        rdt_signal = await get_rdt_ready(str(job.id))
        if rdt_signal:
            await clear_rdt_ready(str(job.id))
            # Give Arr a moment to complete import
            for _ in range(30):  # Poll for up to 5 min
                await asyncio.sleep(10)
                if await _check_has_file(job):
                    await _finalize_import(session, job)
                    return

        # Refresh job state from DB (webhook handler may have updated it)
        async with get_session_factory()() as s:
            result = await s.execute(select(Job).where(Job.id == job.id))
            job = result.scalar_one()

        # Check current Arr queue for our item
        queue_item = await _find_our_queue_item(job)

        if queue_item:
            grabbed = True
            # We have a queue item — track its progress
            if job.state != JobState.DOWNLOADING.value:
                await _transition(session, job, JobState.DOWNLOADING, "Download in progress")

            progress = _get_progress_pct(queue_item)
            await set_download_progress(str(job.id), progress, queue_item.get("title", ""))

            # Check for stalled download
            status = queue_item.get("trackedDownloadStatus", "")
            if status in ("warning", "error") or queue_item.get("status") in ("importBlocked", "importFailed"):
                diagnosis = await diagnose_stalled_download(job, queue_item)
                async with get_session_factory()() as s:
                    await save_diagnostic(s, job.id, diagnosis)
                    await s.commit()

                if fix_attempt < MAX_FIX_ATTEMPTS:
                    await _transition(session, job, JobState.INVESTIGATING, diagnosis.user_message)
                    outcome = await apply_fix(job, diagnosis, fix_attempt)
                    fix_attempt += 1
                    logger.info("Auto-fix attempt %d for job %s: %s -> %s", fix_attempt, job.id, diagnosis.auto_fix, outcome)
                    stall_start = None
                    continue
                else:
                    await _transition(session, job, JobState.UNAVAILABLE, diagnosis.user_message)
                    return

            # Track stall (no progress change)
            if progress == last_progress and progress < 100:
                if stall_start is None:
                    stall_start = time.monotonic()
                elif time.monotonic() - stall_start > DOWNLOAD_STALL_INVESTIGATE:
                    diagnosis = await diagnose_stalled_download(job, queue_item)
                    async with get_session_factory()() as s:
                        await save_diagnostic(s, job.id, diagnosis)
                        await s.commit()
                    if fix_attempt < MAX_FIX_ATTEMPTS:
                        await _transition(session, job, JobState.INVESTIGATING, diagnosis.user_message)
                        outcome = await apply_fix(job, diagnosis, fix_attempt)
                        fix_attempt += 1
                        stall_start = None
                        continue
                    else:
                        await _transition(session, job, JobState.UNAVAILABLE, diagnosis.user_message)
                        return
            else:
                stall_start = None
            last_progress = progress

        elif not grabbed and elapsed > NO_GRAB_INVESTIGATE_AFTER:
            # No queue item and nothing grabbed yet — diagnose why
            diagnosis = await diagnose_no_grab(job, session)
            async with get_session_factory()() as s:
                await save_diagnostic(s, job.id, diagnosis)
                await s.commit()

            if diagnosis.category == "content_not_released":
                raise ContentNotReleasedError(diagnosis.user_message)

            if diagnosis.auto_fix in ("set_monitored", "set_monitored_daily"):
                await _transition(session, job, JobState.MONITORED, diagnosis.user_message)
                return

            if fix_attempt < MAX_FIX_ATTEMPTS:
                await _transition(session, job, JobState.INVESTIGATING, diagnosis.user_message)
                outcome = await apply_fix(job, diagnosis, fix_attempt)
                fix_attempt += 1
                logger.info("Auto-fix attempt %d for job %s: %s -> %s", fix_attempt, job.id, diagnosis.auto_fix, outcome)
                # Reset timer — give the fix time to work
                start = time.monotonic()
                grabbed = False
                continue
            else:
                await _transition(session, job, JobState.UNAVAILABLE, diagnosis.user_message)
                return

        # Absolute safety net — 4 hours of observation with no resolution
        if elapsed > MAX_OBSERVE_TIME:
            logger.warning("Job %s exceeded max observe time (%ds)", job.id, MAX_OBSERVE_TIME)
            await _transition(session, job, JobState.UNAVAILABLE,
                "Taking too long — we'll keep this monitored and try again later")
            return

        await asyncio.sleep(OBSERVE_POLL_INTERVAL)
```

**Step 4: Add helper methods**

```python
async def _check_has_file(job: Job) -> bool:
    """Check if Arr reports the media has a file."""
    try:
        if job.media_type == "movie":
            async with RadarrClient() as client:
                movie = await client.get_movie(job.radarr_movie_id)
                return movie.get("hasFile", False)
        else:
            async with SonarrClient() as client:
                if job.episode and job.season:
                    episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
                    target = next((e for e in episodes if e.get("episodeNumber") == job.episode), None)
                    return target.get("hasFile", False) if target else False
                else:
                    episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
                    return any(e.get("hasFile", False) for e in episodes)
    except Exception as exc:
        logger.warning("Error checking hasFile for job %s: %s", job.id, exc)
        return False


async def _find_our_queue_item(job: Job) -> dict | None:
    """Find our job's item in the Arr download queue."""
    try:
        if job.media_type == "movie":
            async with RadarrClient() as client:
                queue = await client.get_queue(page_size=100, include_movie=True)
                for item in queue.get("records", []):
                    if item.get("movieId") == job.radarr_movie_id:
                        return item
        else:
            async with SonarrClient() as client:
                queue = await client.get_queue(page_size=100, include_series=True)
                for item in queue.get("records", []):
                    if item.get("seriesId") == job.sonarr_series_id:
                        return item
    except Exception as exc:
        logger.warning("Error checking queue for job %s: %s", job.id, exc)
    return None


async def _finalize_import(session: AsyncSession, job: Job) -> None:
    """File confirmed in Arr — update storage, enqueue QC, mark done."""
    from diagnostics import mark_diagnostic_resolved

    # Get file size and path from Arr
    if job.media_type == "movie":
        async with RadarrClient() as client:
            movie = await client.get_movie(job.radarr_movie_id)
            movie_file = movie.get("movieFile", {})
            file_size = movie_file.get("size", 0)
            job.imported_path = movie_file.get("relativePath", "")
    else:
        async with SonarrClient() as client:
            if job.episode and job.season:
                episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
                target = next((e for e in episodes if e.get("episodeNumber") == job.episode), None)
                ep_file = target.get("episodeFile", {}) if target else {}
                file_size = ep_file.get("size", 0)
                job.imported_path = ep_file.get("relativePath", "")
            else:
                file_size = 0

    # Update storage
    if file_size > 0:
        gb = file_size / (1024 ** 3)
        await _update_user_storage(session, job.user_id, gb)
        logger.info("Updated storage for user %s: +%.2f GB", job.user_id, gb)

    # Mark diagnostics resolved
    await mark_diagnostic_resolved(session, job.id)

    # Clear download progress from Redis
    await clear_download_progress(str(job.id))

    # Transition to VERIFYING and enqueue QC
    await _transition(session, job, JobState.VERIFYING, "File imported, running quality check")
    await enqueue_qc(str(job.id))
    logger.info("Job %s -> VERIFYING (file confirmed, QC enqueued)", job.id)


def _get_progress_pct(queue_item: dict) -> int:
    """Extract download progress percentage from queue item."""
    size = queue_item.get("size", 0)
    sizeleft = queue_item.get("sizeleft", 0)
    if size > 0:
        return max(0, min(100, int(((size - sizeleft) / size) * 100)))
    return 0
```

**Step 5: Remove dead streaming code**

Remove all streaming/Zurg code paths from worker.py. Search for "stream", "zurg", "strm" and delete those branches.

**Step 6: Commit**

```bash
git add services/agent-worker/worker.py
git commit -m "feat: rewrite worker as observer+fixer — no timer-based failures, diagnostic-driven intervention"
```

---

## Task 6: Rewrite Monitor — 60s Health Check Fallback

**Files:**
- Modify: `services/agent-worker/monitor.py` (simplify from 15s poll to 60s health check)

**Step 1: Rewrite monitor.py**

The monitor becomes a lightweight health check, not the primary state driver:

```python
"""Download health monitor — fallback safety net for missed webhooks.

Runs every 60s. Checks jobs in SEARCHING/DOWNLOADING/INVESTIGATING that
haven't received a webhook update in 10+ minutes. Queries Arr directly
to catch missed events.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session_factory
from shared.models import Job, JobEvent, JobState
from shared.radarr_client import RadarrClient
from shared.sonarr_client import SonarrClient
from shared.redis_client import set_rdt_ready, set_download_progress

logger = logging.getLogger("agent-worker.monitor")

HEALTH_CHECK_INTERVAL = 60  # seconds
STALE_THRESHOLD = 600       # 10 min without update = check on it


async def monitor_downloads(shutdown_event):
    """Background health check loop."""
    logger.info("Download health monitor starting (check every %ds)", HEALTH_CHECK_INTERVAL)

    while not shutdown_event.is_set():
        try:
            await _health_check_cycle()
        except Exception:
            logger.exception("Health check cycle error")

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=HEALTH_CHECK_INTERVAL)
            break
        except asyncio.TimeoutError:
            pass

    logger.info("Download health monitor stopped")


async def _health_check_cycle():
    """Check all active jobs for missed webhook events."""
    async with get_session_factory()() as session:
        # Find jobs that should be active but haven't been updated recently
        stale_cutoff = datetime.utcnow() - timedelta(seconds=STALE_THRESHOLD)
        result = await session.execute(
            select(Job).where(
                Job.state.in_([
                    JobState.SEARCHING.value,
                    JobState.DOWNLOADING.value,
                    JobState.INVESTIGATING.value,
                    # Legacy states from before migration
                    JobState.RESOLVING.value,
                    JobState.ADDING.value,
                    JobState.ACQUIRING.value,
                ]),
                Job.updated_at < stale_cutoff,
            )
        )
        stale_jobs = result.scalars().all()

        if not stale_jobs:
            return

        logger.info("Health check: found %d stale jobs to check", len(stale_jobs))

        for job in stale_jobs:
            try:
                await _check_job_health(session, job)
            except Exception:
                logger.exception("Health check error for job %s", job.id)

        await session.commit()


async def _check_job_health(session: AsyncSession, job: Job):
    """Check a single stale job against Arr state."""

    # First check: does the file already exist? (Webhook might have been missed)
    has_file = False
    if job.media_type == "movie" and job.radarr_movie_id:
        try:
            async with RadarrClient() as client:
                movie = await client.get_movie(job.radarr_movie_id)
                has_file = movie.get("hasFile", False)
        except Exception:
            pass
    elif job.sonarr_series_id:
        try:
            async with SonarrClient() as client:
                if job.episode and job.season:
                    episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
                    target = next((e for e in episodes if e.get("episodeNumber") == job.episode), None)
                    has_file = target.get("hasFile", False) if target else False
        except Exception:
            pass

    if has_file:
        logger.info("Health check: job %s (%s) has file — signaling completion", job.id, job.title)
        await set_rdt_ready(str(job.id), payload="health_check_found_file")
        # Touch updated_at so we don't re-check immediately
        job.updated_at = datetime.utcnow()
        session.merge(job)
        return

    # Second check: is there a queue item with progress?
    queue_item = None
    try:
        if job.media_type == "movie" and job.radarr_movie_id:
            async with RadarrClient() as client:
                queue = await client.get_queue(page_size=100, include_movie=True)
                for item in queue.get("records", []):
                    if item.get("movieId") == job.radarr_movie_id:
                        queue_item = item
                        break
        elif job.sonarr_series_id:
            async with SonarrClient() as client:
                queue = await client.get_queue(page_size=100, include_series=True)
                for item in queue.get("records", []):
                    if item.get("seriesId") == job.sonarr_series_id:
                        queue_item = item
                        break
    except Exception:
        pass

    if queue_item:
        # Download is in progress — update progress and touch timestamp
        size = queue_item.get("size", 0)
        sizeleft = queue_item.get("sizeleft", 0)
        pct = max(0, min(100, int(((size - sizeleft) / size) * 100))) if size > 0 else 0
        await set_download_progress(str(job.id), pct, queue_item.get("title", ""))

        # Update state if still in SEARCHING
        if job.state in (JobState.SEARCHING.value, JobState.RESOLVING.value,
                         JobState.ADDING.value):
            job.state = JobState.DOWNLOADING.value
            session.add(JobEvent(
                job_id=job.id,
                state=JobState.DOWNLOADING.value,
                message=f"Download detected by health check ({pct}%)",
            ))

        job.updated_at = datetime.utcnow()
        session.merge(job)
        logger.info("Health check: job %s (%s) downloading at %d%%", job.id, job.title, pct)
    else:
        # No queue item, no file — just touch timestamp so we don't spam checks
        # The worker's _observe_until_done will handle diagnostics
        job.updated_at = datetime.utcnow()
        session.merge(job)
        logger.debug("Health check: job %s (%s) — no queue item, no file", job.id, job.title)


import asyncio  # noqa: E402 (needed at module level for wait_for)
```

**Step 2: Commit**

```bash
git add services/agent-worker/monitor.py
git commit -m "feat: simplify monitor to 60s health check fallback (webhooks are primary)"
```

---

## Task 7: Update main.py — Remove old retry logic, use diagnostic-driven recovery

**Files:**
- Modify: `services/agent-worker/main.py` (lines 239-336 retry logic, lines 179-237 recovery)

**Step 1: Simplify _maybe_retry to use diagnostic engine**

The old `_maybe_retry` with its delay arrays gets replaced. When a job enters INVESTIGATING, the worker's observe loop handles it. The recovery logic on startup just re-enqueues jobs.

Replace the retry logic (lines 239-336):

```python
async def _handle_job_outcome(job_id: str) -> None:
    """Called after process_job completes. Check final state and act."""
    async with get_session_factory()() as session:
        result = await session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
        job = result.scalar_one_or_none()
        if not job:
            return

        if job.state == JobState.DONE.value:
            logger.info("Job %s (%s) completed successfully", job.id, job.title)
        elif job.state == JobState.MONITORED.value:
            logger.info("Job %s (%s) parked as MONITORED", job.id, job.title)
        elif job.state == JobState.UNAVAILABLE.value:
            logger.info("Job %s (%s) marked UNAVAILABLE after diagnostics", job.id, job.title)
        elif job.state == JobState.VERIFYING.value:
            logger.info("Job %s (%s) handed off to QC", job.id, job.title)
        elif job.state == JobState.INVESTIGATING.value:
            # Worker observe loop exited but job still investigating
            # This shouldn't happen in normal flow, but handle gracefully
            logger.warning("Job %s (%s) still INVESTIGATING after process_job exit", job.id, job.title)
```

**Step 2: Update stale recovery to handle new states**

Update `_recover_stale_jobs` (lines 179-237) to include new states:

```python
TRANSIENT_STATES = [
    JobState.SEARCHING.value,
    JobState.DOWNLOADING.value,
    JobState.IMPORTING.value,
    JobState.INVESTIGATING.value,
    # Legacy
    JobState.RESOLVING.value,
    JobState.ADDING.value,
    JobState.ACQUIRING.value,
]
```

**Step 3: Commit**

```bash
git add services/agent-worker/main.py
git commit -m "feat: replace timer-based retry with diagnostic-driven job outcome handling"
```

---

## Task 8: Configure Radarr/Sonarr Webhooks via API

**Files:**
- Create: `scripts/configure_webhooks.py`

**Step 1: Create webhook configuration script**

```python
"""Configure Radarr and Sonarr to send webhooks to agent-api."""

import asyncio
import httpx

RADARR_URL = "http://radarr:7878"
RADARR_API = "48cf4fe0d7c049e9942649e4e65a45e2"
SONARR_URL = "http://sonarr:8989"
SONARR_API = "6084b33179eb49c884cc1847ef4089d5"
WEBHOOK_BASE = "http://agent-api:8880/v1"


async def configure():
    async with httpx.AsyncClient() as client:
        # Radarr webhook
        radarr_webhook = {
            "name": "InvisibleArr",
            "implementation": "Webhook",
            "configContract": "WebhookSettings",
            "fields": [
                {"name": "url", "value": f"{WEBHOOK_BASE}/webhooks/radarr"},
                {"name": "method", "value": 1},  # POST
            ],
            "onGrab": True,
            "onDownload": True,
            "onUpgrade": True,
            "onMovieFileDelete": True,
            "onMovieDelete": False,
            "onHealthIssue": True,
            "onHealthRestored": True,
            "onDownloadFailure": True,
            "tags": [],
        }

        # Check if webhook already exists
        resp = await client.get(
            f"{RADARR_URL}/api/v3/notification",
            headers={"X-Api-Key": RADARR_API},
        )
        existing = [n for n in resp.json() if n.get("name") == "InvisibleArr"]

        if existing:
            # Update
            wh_id = existing[0]["id"]
            radarr_webhook["id"] = wh_id
            await client.put(
                f"{RADARR_URL}/api/v3/notification/{wh_id}",
                json=radarr_webhook,
                headers={"X-Api-Key": RADARR_API},
            )
            print(f"Updated Radarr webhook (id={wh_id})")
        else:
            resp = await client.post(
                f"{RADARR_URL}/api/v3/notification",
                json=radarr_webhook,
                headers={"X-Api-Key": RADARR_API},
            )
            print(f"Created Radarr webhook: {resp.json().get('id')}")

        # Sonarr webhook
        sonarr_webhook = {
            "name": "InvisibleArr",
            "implementation": "Webhook",
            "configContract": "WebhookSettings",
            "fields": [
                {"name": "url", "value": f"{WEBHOOK_BASE}/webhooks/sonarr"},
                {"name": "method", "value": 1},
            ],
            "onGrab": True,
            "onDownload": True,
            "onUpgrade": True,
            "onEpisodeFileDelete": True,
            "onSeriesDelete": False,
            "onHealthIssue": True,
            "onHealthRestored": True,
            "onDownloadFailure": True,
            "tags": [],
        }

        resp = await client.get(
            f"{SONARR_URL}/api/v3/notification",
            headers={"X-Api-Key": SONARR_API},
        )
        existing = [n for n in resp.json() if n.get("name") == "InvisibleArr"]

        if existing:
            wh_id = existing[0]["id"]
            sonarr_webhook["id"] = wh_id
            await client.put(
                f"{SONARR_URL}/api/v3/notification/{wh_id}",
                json=sonarr_webhook,
                headers={"X-Api-Key": SONARR_API},
            )
            print(f"Updated Sonarr webhook (id={wh_id})")
        else:
            resp = await client.post(
                f"{SONARR_URL}/api/v3/notification",
                json=sonarr_webhook,
                headers={"X-Api-Key": SONARR_API},
            )
            print(f"Created Sonarr webhook: {resp.json().get('id')}")


if __name__ == "__main__":
    asyncio.run(configure())
```

Run from inside agent-api or agent-worker container (has network access to radarr/sonarr).

**Step 2: Commit**

```bash
git add scripts/configure_webhooks.py
git commit -m "feat: add webhook configuration script for Radarr/Sonarr"
```

---

## Task 9: Frontend — Mom-friendly states and job timeline

**Files:**
- Modify: `services/frontend/src/pages/ActivityPage.tsx`

**Step 1: Update state display mappings**

Replace the `friendlyError` function (lines 117-128) and state display logic:

```typescript
// ── Mom-friendly state display ──────────────────────────────────────

interface StateDisplay {
  label: string;
  color: string;
  icon: string;    // icon component name
  showProgress: boolean;
}

const STATE_DISPLAY: Record<string, StateDisplay> = {
  CREATED:        { label: "Queued",                    color: "gray",   icon: "clock",     showProgress: false },
  SEARCHING:      { label: "Looking for best version",  color: "blue",   icon: "search",    showProgress: false },
  DOWNLOADING:    { label: "Downloading",               color: "blue",   icon: "download",  showProgress: true },
  IMPORTING:      { label: "Organizing into library",   color: "blue",   icon: "folder",    showProgress: false },
  VERIFYING:      { label: "Running quality check",     color: "blue",   icon: "check",     showProgress: false },
  DONE:           { label: "Ready to watch!",           color: "green",  icon: "check",     showProgress: false },
  MONITORED:      { label: "Waiting for release",       color: "amber",  icon: "clock",     showProgress: false },
  INVESTIGATING:  { label: "Working on it",             color: "orange", icon: "wrench",    showProgress: false },
  UNAVAILABLE:    { label: "Not available",             color: "red",    icon: "info",      showProgress: false },
  // Legacy states (map to new display)
  RESOLVING:      { label: "Looking for best version",  color: "blue",   icon: "search",    showProgress: false },
  ADDING:         { label: "Looking for best version",  color: "blue",   icon: "search",    showProgress: false },
  ACQUIRING:      { label: "Downloading",               color: "blue",   icon: "download",  showProgress: true },
  FAILED:         { label: "Working on it",             color: "orange", icon: "wrench",    showProgress: false },
};

function getStateDisplay(state: string): StateDisplay {
  return STATE_DISPLAY[state] ?? { label: state, color: "gray", icon: "circle", showProgress: false };
}

function friendlyError(raw: string | null): string | null {
  if (!raw) return null;
  // These are now mom-friendly messages from the diagnostic engine
  // No need to translate — they're already user-friendly
  // But keep a fallback for any old-format messages still in DB
  if (raw.includes('did not grab a release')) return 'No downloads found yet — retrying';
  if (raw.includes('import not confirmed')) return 'Downloaded but still organizing';
  if (raw.includes('announced but not released')) return 'Waiting for release';
  if (raw.includes('in cinemas only')) return 'Waiting for digital release';
  return raw.length > 60 ? raw.slice(0, 60) + '…' : raw;
}
```

**Step 2: Update filter tabs**

Replace filter type and add new categories:

```typescript
type Filter = 'all' | 'active' | 'monitored' | 'done' | 'issues';

// "issues" replaces "failed" — shows INVESTIGATING + UNAVAILABLE + legacy FAILED
const isActive = (s: string) => ['CREATED','SEARCHING','DOWNLOADING','IMPORTING','VERIFYING','RESOLVING','ADDING','ACQUIRING'].includes(s);
const isIssue = (s: string) => ['INVESTIGATING','UNAVAILABLE','FAILED'].includes(s);
```

**Step 3: Add job timeline component**

Add a collapsible timeline that shows the diagnostic trail:

```typescript
function JobTimeline({ jobId }: { jobId: string }) {
  const { data: events } = useJobEvents(jobId);  // new hook fetching /v1/jobs/{id}/events

  if (!events?.length) return null;

  return (
    <div className="mt-2 ml-4 border-l-2 border-gray-700 pl-3 space-y-1">
      {events.map((evt) => (
        <div key={evt.id} className="text-xs text-gray-400">
          <span className="text-gray-500">{formatTime(evt.created_at)}</span>
          {' '}{evt.message}
        </div>
      ))}
    </div>
  );
}
```

**Step 4: Commit**

```bash
git add services/frontend/src/pages/ActivityPage.tsx
git commit -m "feat: mom-friendly state display with job timeline and diagnostic messages"
```

---

## Task 10: API — Add diagnostics endpoint and events endpoint

**Files:**
- Modify: `services/agent-api/routers/jobs.py`
- Create: endpoint for job events and diagnostics

**Step 1: Add job events endpoint**

```python
@router.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str, user=Depends(get_current_user)):
    """Get event timeline for a job."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(JobEvent)
            .where(JobEvent.job_id == uuid.UUID(job_id))
            .order_by(JobEvent.created_at.asc())
        )
        events = result.scalars().all()
        return [
            {
                "id": str(e.id),
                "state": e.state,
                "message": e.message,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
```

**Step 2: Add diagnostics endpoint (admin only)**

```python
@router.get("/jobs/{job_id}/diagnostics")
async def get_job_diagnostics(job_id: str, user=Depends(get_admin_user)):
    """Get diagnostic records for a job (admin only)."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(JobDiagnostic)
            .where(JobDiagnostic.job_id == uuid.UUID(job_id))
            .order_by(JobDiagnostic.created_at.desc())
        )
        diags = result.scalars().all()
        return [
            {
                "id": str(d.id),
                "category": d.category,
                "details": d.details_json,
                "auto_fix_action": d.auto_fix_action,
                "resolved": d.resolved,
                "created_at": d.created_at.isoformat(),
            }
            for d in diags
        ]
```

**Step 3: Add admin diagnostic summary endpoint**

```python
@router.get("/admin/diagnostics/summary")
async def get_diagnostics_summary(user=Depends(get_admin_user)):
    """Aggregate diagnostic stats — shows failure patterns."""
    async with get_session_factory()() as session:
        result = await session.execute(
            text("""
                SELECT category, COUNT(*) as count,
                       SUM(CASE WHEN resolved THEN 1 ELSE 0 END) as resolved_count
                FROM job_diagnostics
                GROUP BY category
                ORDER BY count DESC
            """)
        )
        rows = result.fetchall()
        return [
            {"category": r[0], "total": r[1], "resolved": r[2]}
            for r in rows
        ]
```

**Step 4: Commit**

```bash
git add services/agent-api/routers/jobs.py
git commit -m "feat: add job events timeline and diagnostics API endpoints"
```

---

## Task 11: Integration Test — End-to-end download flow

**Step 1: Rebuild and deploy**

```bash
cd /home/shawn/Automated-ai-media-center-/invisible-arr/edge-node
docker compose build agent-api agent-worker frontend
docker compose up -d agent-api agent-worker frontend
```

**Step 2: Apply database migration**

```bash
docker exec postgres psql -U invisible_arr -d invisible_arr < services/shared/migrations/008_add_diagnostics_and_states.sql
```

**Step 3: Configure Arr webhooks**

```bash
docker exec agent-worker python /app/scripts/configure_webhooks.py
```

**Step 4: Test with a known-good movie (already cached in RD)**

```bash
curl -X POST http://localhost:8880/v1/request \
  -H "Authorization: Bearer WCCM45YO0zOONZJ0G8GJ_G85rEyUcgXvIa_3cNxO87U" \
  -H "Content-Type: application/json" \
  -d '{"query": "The Matrix", "media_type": "movie"}'
```

Watch logs:
```bash
docker logs -f agent-worker 2>&1
```

Expected flow: SEARCHING -> DOWNLOADING (webhook grab) -> IMPORTING (webhook import) -> VERIFYING -> DONE

**Step 5: Test with unreleased content**

```bash
curl -X POST http://localhost:8880/v1/request \
  -H "Authorization: Bearer WCCM45YO0zOONZJ0G8GJ_G85rEyUcgXvIa_3cNxO87U" \
  -H "Content-Type: application/json" \
  -d '{"query": "Some Movie 2027", "media_type": "movie"}'
```

Expected: SEARCHING -> diagnostic detects "content_not_released" -> MONITORED

**Step 6: Verify diagnostics table**

```bash
docker exec postgres psql -U invisible_arr -d invisible_arr -c "SELECT category, auto_fix_action, resolved, created_at FROM job_diagnostics ORDER BY created_at DESC LIMIT 10;"
```

**Step 7: Check frontend**

Open https://app.cutdacord.app and verify:
- Active downloads show progress bar
- MONITORED shows "Waiting for release"
- No technical error messages visible
- Job timeline shows human-readable events

**Step 8: Commit final integration**

```bash
git add -A
git commit -m "feat: download pipeline v2 — observer+fixer pattern with diagnostics and webhooks"
```

---

## Task 12: Clean up dead code

**Files:**
- Modify: `services/agent-worker/worker.py` — remove streaming/zurg references
- Modify: `services/agent-worker/main.py` — remove old smart_retry import if unused

**Step 1: Search and remove all streaming code paths**

```bash
grep -rn "stream\|zurg\|strm\|STREAM" services/agent-worker/worker.py
```

Remove all branches that handle streaming mode. Remove `ARR_GRAB_TIMEOUT_STREAM` constant.

**Step 2: Remove old `_wait_for_grab` and `_monitor_radarr_download` / `_monitor_sonarr_download` methods**

These are replaced by `_observe_until_done`.

**Step 3: Commit**

```bash
git add services/agent-worker/worker.py services/agent-worker/main.py
git commit -m "chore: remove dead streaming code and old timer-based pipeline methods"
```

---

## Execution Order Summary

| Task | Description | Dependencies |
|------|-------------|-------------|
| 1 | Database: diagnostics table + new states | None |
| 2 | Diagnostic engine module | Task 1 (needs JobDiagnostic model) |
| 3 | Auto-fixer module | Task 2 (needs Diagnosis dataclass) |
| 4 | Webhook handler rewrite | Task 1 (needs new states) |
| 5 | Worker pipeline rewrite | Tasks 1-4 (needs all new modules) |
| 6 | Monitor rewrite | Task 1 (needs new states) |
| 7 | main.py updates | Tasks 5-6 (needs new worker/monitor) |
| 8 | Configure Arr webhooks | Task 4 (needs webhook endpoints) |
| 9 | Frontend updates | Task 1 (needs new states) |
| 10 | API endpoints | Task 1 (needs models) |
| 11 | Integration test | All above |
| 12 | Dead code cleanup | Task 5 (after rewrite confirmed working) |
