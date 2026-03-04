"""Invisible Arr Agent Worker -- Redis queue consumer entry point."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
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

from monitor import monitor_downloads  # noqa: E402
from worker import process_job  # noqa: E402

MAX_RETRIES = 5
RETRY_DELAYS = [30, 60, 120, 300, 600]  # seconds between retries

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

    # Consumer loop ----------------------------------------------------------
    logger.info("Entering job consumer loop")
    monitor_task = asyncio.create_task(monitor_downloads(_shutdown_event))
    while not _shutdown_event.is_set():
        try:
            job_id = await dequeue_job(timeout=2)
        except Exception:
            logger.exception("Error dequeueing job, retrying in 5s")
            await asyncio.sleep(5)
            continue

        if job_id is None:
            # dequeue_job returned None (timeout / empty queue) -- loop back
            continue

        logger.info("Dequeued job %s", job_id)
        try:
            await process_job(job_id)
            logger.info("Job %s completed successfully", job_id)
        except Exception:
            logger.exception("Unhandled exception while processing job %s", job_id)
            try:
                await _fail_job(job_id)
            except Exception:
                logger.exception("Could not transition job %s to FAILED", job_id)

        # Check if the job failed and should be retried
        try:
            await _maybe_retry(job_id)
        except Exception:
            logger.exception("Error checking retry for job %s", job_id)

    # Shutdown cleanup -------------------------------------------------------
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


async def _maybe_retry(job_id: str) -> None:
    """If a job is FAILED and under the retry limit, handle Arr cleanup and re-enqueue."""
    from shared.models import Job, JobState, JobEvent  # noqa: E402
    from sqlalchemy import select
    from sqlalchemy import update as sa_update
    import uuid
    from datetime import datetime

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()
        if job is None or job.state != JobState.FAILED:
            return
        if job.retry_count >= MAX_RETRIES:
            logger.info("Job %s exceeded max retries (%d), staying FAILED", job_id, MAX_RETRIES)
            return

        new_count = job.retry_count + 1
        delay = RETRY_DELAYS[min(new_count - 1, len(RETRY_DELAYS) - 1)]

        # --- Smart retry analysis ---
        strategy_note = ""
        should_blacklist = True
        should_re_search = True
        try:
            from smart_retry import analyze_failure

            strategy = await analyze_failure(job_id)
            if strategy is not None:
                should_blacklist = strategy.blacklist_queue_item
                should_re_search = strategy.trigger_re_search
                strategy_note = f" [smart: {strategy.reasoning[:80]}]"
        except Exception:
            logger.exception("Smart retry analysis failed for job %s, using dumb retry", job_id)

        # --- Arr cleanup: blacklist failed queue item and optionally re-search ---
        try:
            if job.arr_queue_id:
                if job.radarr_movie_id:
                    from shared.radarr_client import RadarrClient
                    async with RadarrClient() as radarr:
                        await radarr.delete_queue_item(
                            job.arr_queue_id,
                            blacklist=should_blacklist,
                        )
                        if should_re_search and job.radarr_movie_id:
                            await radarr.search_movie(job.radarr_movie_id)
                elif job.sonarr_series_id:
                    from shared.sonarr_client import SonarrClient
                    async with SonarrClient() as sonarr:
                        await sonarr.delete_queue_item(
                            job.arr_queue_id,
                            blacklist=should_blacklist,
                        )
                        if should_re_search:
                            if job.season is not None:
                                await sonarr.search_season(job.sonarr_series_id, job.season)
                            else:
                                await sonarr.search_series(job.sonarr_series_id)
        except Exception:
            logger.exception("Failed to cleanup Arr queue for job %s", job_id)

        # Reset to CREATED and bump retry count (clear arr_queue_id for fresh monitoring)
        now = datetime.utcnow()
        await session.execute(
            sa_update(Job).where(Job.id == job.id).values(
                state=JobState.CREATED.value,
                retry_count=new_count,
                arr_queue_id=None,
                updated_at=now,
            )
        )
        event = JobEvent(
            job_id=job.id,
            state=JobState.CREATED.value,
            message=f"Auto-retry #{new_count}/{MAX_RETRIES} (waiting {delay}s){strategy_note}",
            created_at=now,
        )
        session.add(event)
        await session.commit()

    logger.info("Job %s: scheduling retry #%d in %ds%s", job_id, new_count, delay, strategy_note)

    # Schedule the delayed re-enqueue in the background so we don't block
    # the consumer loop from processing other jobs.
    async def _delayed_enqueue() -> None:
        await asyncio.sleep(delay)
        if _shutdown_event.is_set():
            logger.info("Shutdown requested, skipping retry for job %s", job_id)
            return
        await enqueue_job(job_id)
        logger.info("Job %s re-enqueued for retry #%d", job_id, new_count)

    asyncio.create_task(_delayed_enqueue())


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

        job.state = JobState.FAILED
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
