"""Invisible Arr Agent Worker -- Redis queue consumer entry point."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

import sentry_sdk

# ---------------------------------------------------------------------------
# Ensure the shared package is importable when running inside the container
# (shared/ is volume-mounted at /app/shared).
# ---------------------------------------------------------------------------
_app_root = Path("/app")
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

from shared.config import get_config  # noqa: E402
from shared.database import init_db, get_engine, get_session_factory  # noqa: E402
from shared.redis_client import dequeue_job, enqueue_job, get_redis  # noqa: E402

from shared.models import JobState  # noqa: E402
from monitor import monitor_downloads  # noqa: E402
from worker import process_request, check_timeouts  # noqa: E402

MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "3"))
TIMEOUT_CHECK_INTERVAL = 60  # Check every 60 seconds

from shared.logging import setup_logging  # noqa: E402

# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------
_sentry_dsn = os.environ.get("SENTRY_DSN_BACKEND", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.environ.get("ENV", "dev"),
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

logger = setup_logging("agent-worker")

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_shutdown_event: asyncio.Event = asyncio.Event()


def _request_shutdown(sig: signal.Signals) -> None:  # noqa: ARG001
    """Signal handler that sets the shutdown event."""
    logger.info("Received shutdown signal, draining current job then exiting")
    _shutdown_event.set()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
async def _run() -> None:
    """Initialise resources and consume jobs from the Redis queue forever."""
    config = get_config()
    logger.info("Agent-worker starting (db=%s)", config.database_url.split("@")[-1])

    # Database ---------------------------------------------------------------
    try:
        init_db()
        logger.info("Database engine initialised")
    except Exception:
        logger.exception("Failed to initialise database engine")
        raise

    # Redis ------------------------------------------------------------------
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("Redis connection established")
    except Exception:
        logger.exception("Failed to connect to Redis")
        raise

    # Recover stale in-flight jobs from previous crash -----------------------
    await _recover_stale_jobs()

    # Consumer loop ----------------------------------------------------------
    logger.info("Entering job consumer loop (max_concurrent=%d)", MAX_CONCURRENT_JOBS)
    monitor_task = asyncio.create_task(monitor_downloads(_shutdown_event))
    waiting_checker_task = asyncio.create_task(_check_waiting_jobs(_shutdown_event))
    timeout_checker_task = asyncio.create_task(_timeout_checker(_shutdown_event))
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
                await process_request(job_id)
            except Exception:
                logger.exception("Unhandled exception while processing job %s", job_id)
                try:
                    await _fail_job(job_id)
                except Exception:
                    logger.exception("Could not transition job %s to FAILED", job_id)

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
    waiting_checker_task.cancel()
    timeout_checker_task.cancel()
    for bg_task in (monitor_task, waiting_checker_task, timeout_checker_task):
        try:
            await bg_task
        except asyncio.CancelledError:
            pass

    logger.info("Shutting down agent-worker")
    await redis.aclose()
    engine = get_engine()
    await engine.dispose()
    logger.info("Resources released, goodbye")


async def _recover_stale_jobs() -> None:
    """Re-enqueue jobs stuck in transient states from a previous worker crash.

    On startup, any job in SEARCHING/DOWNLOADING/IMPORTING has no active
    worker processing it.  We reset them to REQUESTED and re-enqueue so the
    pipeline restarts cleanly.
    """
    from shared.models import Job, JobState, JobEvent  # noqa: E402
    from sqlalchemy import select
    from sqlalchemy import update as sa_update

    TRANSIENT_STATES = (
        JobState.SEARCHING.value,
    )

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Job).where(Job.state.in_(TRANSIENT_STATES))
        )
        stale_jobs = list(result.scalars().all())

    if not stale_jobs:
        logger.info("No stale in-flight jobs found on startup")
        return

    logger.warning("Found %d stale in-flight jobs from previous run, recovering", len(stale_jobs))

    for job in stale_jobs:
        try:
            now = datetime.utcnow()
            async with factory() as session:
                await session.execute(
                    sa_update(Job).where(Job.id == job.id).values(
                        state=JobState.REQUESTED.value,
                        arr_queue_id=None,
                        updated_at=now,
                    )
                )
                event = JobEvent(
                    job_id=job.id,
                    state=JobState.REQUESTED.value,
                    message=f"Recovered from stale state '{job.state}' after worker restart",
                    created_at=now,
                )
                session.add(event)
                await session.commit()
            await enqueue_job(str(job.id))
            logger.info(
                "Recovered stale job %s (%s) from state %s -> REQUESTED",
                job.id, getattr(job, 'query', 'unknown'), job.state,
            )
        except Exception:
            logger.exception("Failed to recover stale job %s", job.id)


async def _fail_job(job_id: str) -> None:
    """Best-effort transition of a job to FAILED after an unhandled error."""
    from shared.models import Job, JobState, JobEvent  # noqa: E402
    from sqlalchemy import select
    import uuid
    from datetime import datetime

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()
        if job is None:
            logger.error("Job %s not found when trying to mark FAILED", job_id)
            return

        job.state = JobState.FAILED.value
        job.updated_at = datetime.utcnow()

        event = JobEvent(
            job_id=job.id,
            state=JobState.FAILED.value,
            message="Unhandled exception during processing",
            created_at=datetime.utcnow(),
        )
        session.add(event)
        await session.commit()
        logger.info("Transitioned job %s to FAILED (post-crash)", job_id)


# ---------------------------------------------------------------------------
# WAITING job checker (formerly MONITORED)
# ---------------------------------------------------------------------------
WAITING_CHECK_INTERVAL = int(os.environ.get("MONITORED_CHECK_INTERVAL", "1800"))  # 30 min


async def _check_waiting_jobs(shutdown_event: asyncio.Event) -> None:
    """Periodically check WAITING jobs to see if content is now available.

    For movies: checks Radarr hasFile.
    For TV: checks Sonarr episodeFile existence.
    When available, re-enqueues the job so it resumes the pipeline.
    """
    from shared.models import Job, JobState, JobEvent  # noqa: E402
    from shared.radarr_client import RadarrClient
    from shared.sonarr_client import SonarrClient
    from sqlalchemy import select
    from sqlalchemy import update as sa_update

    logger.info("WAITING job checker starting (interval=%ds)", WAITING_CHECK_INTERVAL)

    # Wait a bit on startup before first check
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=60)
        return  # Shutdown requested during initial wait
    except asyncio.TimeoutError:
        pass

    while not shutdown_event.is_set():
        try:
            factory = get_session_factory()
            async with factory() as session:
                result = await session.execute(
                    select(Job).where(
                        Job.state == JobState.WAITING.value
                    )
                )
                waiting_jobs = list(result.scalars().all())

            if waiting_jobs:
                logger.info("Checking %d WAITING jobs for availability", len(waiting_jobs))

            for job in waiting_jobs:
                if shutdown_event.is_set():
                    break
                try:
                    available = False
                    if job.media_type == "movie" and job.radarr_movie_id:
                        async with RadarrClient() as radarr:
                            movie = await radarr.get_movie(job.radarr_movie_id)
                            status = movie.get("status", "")
                            has_file = movie.get("hasFile", False)
                            # Available if status changed from announced/inCinemas to released
                            if status not in ("announced", "inCinemas") or has_file:
                                available = True
                    elif job.media_type == "tv" and job.sonarr_series_id:
                        if job.season is not None and job.episode is not None:
                            async with SonarrClient() as sonarr:
                                episodes = await sonarr.get_episodes(job.sonarr_series_id, job.season)
                                target_ep = next(
                                    (e for e in episodes if e.get("episodeNumber") == job.episode),
                                    None,
                                )
                                if target_ep:
                                    if target_ep.get("hasFile"):
                                        available = True
                                    else:
                                        air_date = target_ep.get("airDateUtc")
                                        if air_date:
                                            from datetime import datetime, timezone
                                            try:
                                                aired = datetime.fromisoformat(air_date.replace("Z", "+00:00"))
                                                if aired <= datetime.now(timezone.utc):
                                                    available = True
                                            except (ValueError, TypeError):
                                                pass
                        else:
                            # Full season -- just re-check, Sonarr will handle it
                            available = True

                    if available:
                        logger.info("WAITING job %s (%s) -- content now available, re-enqueuing", job.id, job.title)
                        now = datetime.utcnow()
                        async with factory() as session:
                            await session.execute(
                                sa_update(Job).where(Job.id == job.id).values(
                                    state=JobState.REQUESTED.value,
                                    updated_at=now,
                                )
                            )
                            event = JobEvent(
                                job_id=job.id,
                                state=JobState.REQUESTED.value,
                                message="Content now available -- resuming download",
                                created_at=now,
                            )
                            session.add(event)
                            await session.commit()
                        await enqueue_job(str(job.id))
                except Exception:
                    logger.exception("Error checking WAITING job %s", job.id)

        except Exception:
            logger.exception("WAITING checker cycle failed")

        # Wait for next cycle or shutdown
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=WAITING_CHECK_INTERVAL)
            break
        except asyncio.TimeoutError:
            continue

    logger.info("WAITING job checker stopped")


# ---------------------------------------------------------------------------
# Timeout checker
# ---------------------------------------------------------------------------


async def _timeout_checker(shutdown_event: asyncio.Event) -> None:
    """Periodically check for timed-out SEARCHING jobs."""
    logger.info("Timeout checker starting (interval=%ds)", TIMEOUT_CHECK_INTERVAL)
    while not shutdown_event.is_set():
        try:
            await check_timeouts()
        except Exception:
            logger.exception("Timeout checker cycle failed")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=TIMEOUT_CHECK_INTERVAL)
            break
        except asyncio.TimeoutError:
            pass
    logger.info("Timeout checker stopped")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Register signal handlers and run the async consumer."""
    loop = asyncio.new_event_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_shutdown, sig)
        except NotImplementedError:
            # Windows does not support add_signal_handler; fall back
            signal.signal(sig, lambda s, _f: _request_shutdown(s))

    try:
        loop.run_until_complete(_run())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, exiting")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
