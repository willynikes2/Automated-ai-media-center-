"""Invisible Arr Agent Worker -- Redis queue consumer entry point."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the shared package is importable when running inside the container
# (shared/ is volume-mounted at /app/shared).
# ---------------------------------------------------------------------------
_app_root = Path("/app")
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

from shared.config import get_config  # noqa: E402
from shared.database import init_db, get_engine, get_session_factory  # noqa: E402
from shared.redis_client import dequeue_job, get_redis  # noqa: E402

from worker import process_job  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent-worker")

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
            # Attempt to transition the job to FAILED so it is not stuck
            try:
                await _fail_job(job_id)
            except Exception:
                logger.exception("Could not transition job %s to FAILED", job_id)

    # Shutdown cleanup -------------------------------------------------------
    logger.info("Shutting down agent-worker")
    await redis.aclose()
    engine = get_engine()
    await engine.dispose()
    logger.info("Resources released, goodbye")


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
