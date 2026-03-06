"""Download health monitor — fallback safety net for missed webhooks.

Runs every 60s. Checks jobs in active states that haven't received a
webhook update in 10+ minutes. Queries Arr directly to catch missed events.
This is a SAFETY NET, not the primary state driver (webhooks are primary).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from shared.database import get_session_factory
from shared.models import Job, JobEvent, JobState
from shared.radarr_client import RadarrClient
from shared.sonarr_client import SonarrClient
from shared.redis_client import set_rdt_ready, set_download_progress

logger = logging.getLogger("agent-worker.monitor")

HEALTH_CHECK_INTERVAL = 60  # seconds between checks
STALE_THRESHOLD = 600       # 10 min without update = check on it


async def monitor_downloads(shutdown_event: asyncio.Event) -> None:
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


async def _health_check_cycle() -> None:
    """Check all active jobs for missed webhook events."""
    async with get_session_factory()() as session:
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


async def _check_job_health(session, job: Job) -> None:
    """Check a single stale job against Arr state."""

    # Check 1: Does the file already exist? (Webhook might have been missed)
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
                elif job.season:
                    episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
                    has_file = any(e.get("hasFile", False) for e in episodes)
        except Exception:
            pass

    if has_file:
        logger.info("Health check: job %s (%s) has file — signaling completion", job.id, job.title)
        await set_rdt_ready(str(job.id), payload="health_check_found_file")
        job.updated_at = datetime.utcnow()
        session.add(job)
        return

    # Check 2: Is there a queue item with progress?
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

        # Update state if still in SEARCHING/legacy states
        if job.state in (JobState.SEARCHING.value, JobState.RESOLVING.value,
                         JobState.ADDING.value):
            job.state = JobState.DOWNLOADING.value
            session.add(JobEvent(
                job_id=job.id,
                state=JobState.DOWNLOADING.value,
                message=f"Download detected by health check ({pct}%)",
            ))

        job.updated_at = datetime.utcnow()
        session.add(job)
        logger.info("Health check: job %s (%s) downloading at %d%%", job.id, job.title, pct)
    else:
        # No queue item, no file — just touch timestamp so we don't spam
        # The worker's _observe_until_done handles diagnostics
        job.updated_at = datetime.utcnow()
        session.add(job)
        logger.debug("Health check: job %s (%s) — no queue item, no file", job.id, job.title)
