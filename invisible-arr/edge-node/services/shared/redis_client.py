"""Async Redis helpers for job and QC queues."""

import logging
from urllib.parse import urlparse

import redis.asyncio as aioredis

from shared.config import get_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Queue names
# ---------------------------------------------------------------------------

_JOBS_QUEUE = "invisiblearr:jobs"
_QC_QUEUE = "invisiblearr:qc"

# ---------------------------------------------------------------------------
# Connection singleton
# ---------------------------------------------------------------------------

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return a cached async Redis connection, creating one if needed."""
    global _redis  # noqa: PLW0603
    if _redis is None:
        config = get_config()
        _redis = aioredis.from_url(
            config.redis_url,
            decode_responses=True,
            max_connections=10,
        )
        parsed = urlparse(config.redis_url)
        logger.info("Redis connection established to %s:%s", parsed.hostname, parsed.port)
    return _redis


async def _safe_redis_op(coro):
    """Execute a Redis coroutine, resetting the connection on failure."""
    global _redis  # noqa: PLW0603
    try:
        return await coro
    except (ConnectionError, aioredis.ConnectionError, OSError) as exc:
        logger.warning("Redis connection error, resetting client: %s", exc)
        _redis = None
        raise


# ---------------------------------------------------------------------------
# Job queue operations
# ---------------------------------------------------------------------------


async def enqueue_job(job_id: str) -> None:
    """Push a job ID onto the jobs queue (LPUSH)."""
    r = await get_redis()
    await _safe_redis_op(r.lpush(_JOBS_QUEUE, job_id))
    logger.info("Enqueued job %s", job_id)


async def dequeue_job(timeout: int = 0) -> str | None:
    """Blocking pop a job ID from the jobs queue (BRPOP).

    Parameters
    ----------
    timeout:
        Seconds to block.  0 means block indefinitely.

    Returns
    -------
    The job ID string, or ``None`` if the timeout expired.
    """
    r = await get_redis()
    result = await _safe_redis_op(r.brpop(_JOBS_QUEUE, timeout=timeout))
    if result is None:
        return None
    # brpop returns (queue_name, value)
    _queue_name, job_id = result
    logger.info("Dequeued job %s", job_id)
    return job_id


# ---------------------------------------------------------------------------
# QC queue operations
# ---------------------------------------------------------------------------


async def enqueue_qc(job_id: str) -> None:
    """Push a job ID onto the QC queue (LPUSH)."""
    r = await get_redis()
    await _safe_redis_op(r.lpush(_QC_QUEUE, job_id))
    logger.info("Enqueued QC for job %s", job_id)


async def dequeue_qc(timeout: int = 0) -> str | None:
    """Blocking pop a job ID from the QC queue (BRPOP).

    Parameters
    ----------
    timeout:
        Seconds to block.  0 means block indefinitely.

    Returns
    -------
    The job ID string, or ``None`` if the timeout expired.
    """
    r = await get_redis()
    result = await _safe_redis_op(r.brpop(_QC_QUEUE, timeout=timeout))
    if result is None:
        return None
    _queue_name, job_id = result
    logger.info("Dequeued QC job %s", job_id)
    return job_id


# ---------------------------------------------------------------------------
# Download progress tracking
# ---------------------------------------------------------------------------

_PROGRESS_PREFIX = "invisiblearr:progress:"
_PROGRESS_TTL = 3600  # 1 hour


async def set_download_progress(job_id: str, percent: int, detail: str = "") -> None:
    """Store download progress for a job."""
    r = await get_redis()
    key = f"{_PROGRESS_PREFIX}{job_id}"
    await _safe_redis_op(r.hset(key, mapping={"percent": percent, "detail": detail}))
    await _safe_redis_op(r.expire(key, _PROGRESS_TTL))


async def get_download_progress(job_id: str) -> dict | None:
    """Get download progress for a job. Returns None if no progress tracked."""
    r = await get_redis()
    key = f"{_PROGRESS_PREFIX}{job_id}"
    data = await _safe_redis_op(r.hgetall(key))
    if not data:
        return None
    return {"percent": int(data.get("percent", 0)), "detail": data.get("detail", "")}


async def clear_download_progress(job_id: str) -> None:
    """Remove progress tracking for a completed job."""
    r = await get_redis()
    await _safe_redis_op(r.delete(f"{_PROGRESS_PREFIX}{job_id}"))
