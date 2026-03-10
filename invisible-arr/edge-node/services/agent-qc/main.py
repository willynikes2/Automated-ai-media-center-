"""Invisible Arr Agent QC -- Redis queue consumer for quality-control jobs.

Dequeues job IDs from the ``queue:qc`` list, runs ffprobe-based validation,
and transitions jobs to DONE (with a Jellyfin library refresh) or handles
failures with blacklisting and optional retry.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path
from uuid import UUID

import sentry_sdk

import httpx
import redis.asyncio as aioredis
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Ensure the shared package is importable (shared/ is mounted at /app/shared)
# ---------------------------------------------------------------------------
_app_root = Path("/app")
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

from shared.config import get_config  # noqa: E402
from shared.database import get_session_factory, init_db  # noqa: E402
from shared.models import Blacklist, Job, JobEvent, JobState  # noqa: E402

from qc import validate_file  # noqa: E402

# ---------------------------------------------------------------------------
# Logging & Sentry
# ---------------------------------------------------------------------------
from shared.logging import setup_logging  # noqa: E402

_sentry_dsn = os.environ.get("SENTRY_DSN_BACKEND", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.environ.get("ENV", "dev"),
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

logger = setup_logging("agent-qc")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
QC_QUEUE = "invisiblearr:qc"
WORKER_QUEUE = "invisiblearr:jobs"
DEQUEUE_TIMEOUT_SECONDS = 5
MAX_RETRIES = 1
JELLYFIN_REFRESH_TIMEOUT_SECONDS = 15

# ---------------------------------------------------------------------------
# Shutdown flag
# ---------------------------------------------------------------------------
_shutdown_event = asyncio.Event()


def _request_shutdown(signame: str) -> None:
    """Signal handler that sets the shutdown event."""
    logger.info("Received %s -- requesting graceful shutdown", signame)
    _shutdown_event.set()


# ---------------------------------------------------------------------------
# Jellyfin library refresh
# ---------------------------------------------------------------------------
async def _trigger_jellyfin_refresh(jellyfin_url: str, token: str = "") -> None:
    """POST to Jellyfin's library-refresh endpoint with auth token."""
    url = f"{jellyfin_url.rstrip('/')}/Library/Refresh"
    headers: dict[str, str] = {}
    if token:
        headers["X-Emby-Token"] = token
    try:
        async with httpx.AsyncClient(timeout=JELLYFIN_REFRESH_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, headers=headers)
            resp.raise_for_status()
        logger.info("Jellyfin library refresh triggered successfully")
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Jellyfin refresh returned HTTP %s: %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except Exception:
        logger.exception("Failed to trigger Jellyfin library refresh")


# ---------------------------------------------------------------------------
# Job event helper
# ---------------------------------------------------------------------------
def _make_event(job_id: UUID, state: str, message: str) -> JobEvent:
    """Create a new ``JobEvent`` row."""
    return JobEvent(job_id=job_id, state=state, message=message)


# ---------------------------------------------------------------------------
# Core job processor
# ---------------------------------------------------------------------------
async def _process_job(job_id_str: str, rds: aioredis.Redis) -> None:
    """Fetch the job from the DB, run QC, and handle the result."""
    config = get_config()
    session_factory = get_session_factory()

    try:
        job_id = UUID(job_id_str)
    except ValueError:
        logger.error("Invalid job ID received from queue: %s", job_id_str)
        return

    async with session_factory() as session:
        async with session.begin():
            result = await session.execute(select(Job).where(Job.id == job_id))
            job: Job | None = result.scalar_one_or_none()

            if job is None:
                logger.error("Job %s not found in database", job_id)
                return

            if job.state not in (JobState.VERIFYING, JobState.IMPORTING,
                                  JobState.VERIFYING.value, JobState.IMPORTING.value):
                logger.warning(
                    "Job %s is in state %s, expected VERIFYING or IMPORTING -- skipping",
                    job_id,
                    job.state,
                )
                return

            imported_path: str | None = job.imported_path
            if not imported_path:
                logger.error("Job %s has no imported_path", job_id)
                job.state = JobState.FAILED
                session.add(
                    _make_event(job.id, JobState.FAILED, "No imported_path set on job")
                )
                return

            # ---------------------------------------------------------------
            # Run ffprobe QC
            # ---------------------------------------------------------------
            logger.info("Running QC on job %s -- file: %s", job_id, imported_path)
            passed, reason = await validate_file(imported_path)

            if passed:
                # ---- PASS ----
                job.state = JobState.AVAILABLE
                session.add(_make_event(job.id, JobState.AVAILABLE, reason))
                logger.info("Job %s QC PASSED -- transitioning to AVAILABLE", job_id)
            else:
                # ---- FAIL ----
                logger.warning("Job %s QC FAILED: %s", job_id, reason)

                # Blacklist the release
                release_hash: str = ""
                release_title: str = ""
                if job.selected_candidate and isinstance(job.selected_candidate, dict):
                    release_hash = job.selected_candidate.get("info_hash", "")
                    release_title = job.selected_candidate.get("title", "")

                if release_hash:
                    blacklist_entry = Blacklist(
                        user_id=job.user_id,
                        release_hash=release_hash,
                        release_title=release_title,
                        reason=reason,
                    )
                    session.add(blacklist_entry)
                    logger.info(
                        "Blacklisted release %s for job %s: %s",
                        release_hash[:12],
                        job_id,
                        reason,
                    )

                # Retry logic
                if job.retry_count < MAX_RETRIES:
                    job.retry_count += 1
                    job.state = JobState.SEARCHING
                    session.add(
                        _make_event(
                            job.id,
                            JobState.SEARCHING,
                            f"QC failed ({reason}), retrying (attempt {job.retry_count})",
                        )
                    )
                    logger.info(
                        "Job %s retry %d/%d -- re-enqueuing for worker",
                        job_id,
                        job.retry_count,
                        MAX_RETRIES,
                    )
                else:
                    job.state = JobState.FAILED
                    session.add(
                        _make_event(
                            job.id,
                            JobState.FAILED,
                            f"QC failed after {job.retry_count + 1} attempt(s): {reason}",
                        )
                    )
                    logger.info("Job %s exhausted retries -- transitioning to FAILED", job_id)

    # ---- Post-commit actions (outside the DB transaction) ----
    if passed:
        await _trigger_jellyfin_refresh(config.jellyfin_url, config.jellyfin_admin_token or "")
    elif job.retry_count <= MAX_RETRIES and job.state == JobState.SEARCHING:
        # Re-enqueue for the worker to pick the next candidate
        await rds.lpush(WORKER_QUEUE, job_id_str)
        logger.info("Job %s pushed to %s for retry", job_id, WORKER_QUEUE)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
async def _main() -> None:
    """Initialise resources and run the blocking dequeue loop."""
    config = get_config()

    # Database
    logger.info("Initialising database engine")
    init_db(config.database_url)

    # Redis
    logger.info("Connecting to Redis at %s", config.redis_url)
    rds = aioredis.from_url(config.redis_url, decode_responses=True)
    try:
        await rds.ping()
        logger.info("Redis connection established")
    except Exception:
        logger.exception("Failed to connect to Redis")
        raise

    # Metrics server --------------------------------------------------------
    from shared.metrics_server import start_metrics_server
    metrics_runner = await start_metrics_server(port=9091)

    logger.info("Agent QC service started -- listening on %s", QC_QUEUE)

    try:
        while not _shutdown_event.is_set():
            # BRPOP blocks until a message arrives or timeout elapses
            result: tuple[str, str] | None = await rds.brpop(
                QC_QUEUE, timeout=DEQUEUE_TIMEOUT_SECONDS
            )

            if result is None:
                # Timeout -- loop back and check shutdown flag
                continue

            _queue_name, job_id_str = result
            logger.info("Dequeued QC job: %s", job_id_str)

            try:
                await _process_job(job_id_str, rds)
            except Exception:
                logger.exception("Unhandled error processing job %s", job_id_str)
    finally:
        await metrics_runner.cleanup()
        logger.info("Closing Redis connection")
        await rds.aclose()

        from shared.database import get_engine
        engine = get_engine()
        await engine.dispose()
        logger.info("Database engine disposed -- agent-qc shut down cleanly")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Register signal handlers and run the async main loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Register SIGTERM / SIGINT for graceful shutdown.
    # add_signal_handler is Unix-only; fall back to signal.signal on Windows.
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _request_shutdown, sig_name)
        except NotImplementedError:
            signal.signal(sig, lambda _s, _f, name=sig_name: _request_shutdown(name))

    try:
        loop.run_until_complete(_main())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received -- exiting")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
