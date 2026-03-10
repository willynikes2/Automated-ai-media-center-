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
_RDT_READY_PREFIX = "invisiblearr:rdt_ready:"
_RDT_READY_TTL = 1800  # 30 minutes


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


async def set_rdt_ready(job_id: str, payload: str = "1") -> None:
    """Set a short-lived signal that rdt reported completion for this job."""
    r = await get_redis()
    key = f"{_RDT_READY_PREFIX}{job_id}"
    await _safe_redis_op(r.set(key, payload, ex=_RDT_READY_TTL))


async def get_rdt_ready(job_id: str) -> str | None:
    """Get rdt-completion signal for a job, if present."""
    r = await get_redis()
    key = f"{_RDT_READY_PREFIX}{job_id}"
    return await _safe_redis_op(r.get(key))


async def clear_rdt_ready(job_id: str) -> None:
    """Clear rdt-completion signal for a job."""
    r = await get_redis()
    await _safe_redis_op(r.delete(f"{_RDT_READY_PREFIX}{job_id}"))


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

_RATE_LIMIT_PREFIX = "invisiblearr:ratelimit:"


async def check_and_increment_rate(user_id: str, daily_limit: int) -> bool:
    """Return True if the request is allowed. Increments the daily counter.

    Uses Redis INCR with a TTL that expires at midnight UTC.
    A daily_limit of -1 means unlimited.
    """
    if daily_limit == -1:
        return True
    r = await get_redis()
    key = f"{_RATE_LIMIT_PREFIX}{user_id}"
    count = await _safe_redis_op(r.incr(key))
    if count == 1:
        # First request today — set TTL to 24 hours
        await _safe_redis_op(r.expire(key, 86400))
    return count <= daily_limit


async def get_rate_count(user_id: str) -> int:
    """Return the current daily request count for a user."""
    r = await get_redis()
    key = f"{_RATE_LIMIT_PREFIX}{user_id}"
    val = await _safe_redis_op(r.get(key))
    return int(val) if val else 0


# ---------------------------------------------------------------------------
# Generic JSON cache
# ---------------------------------------------------------------------------

_CACHE_PREFIX = "invisiblearr:cache:"


async def cache_get(key: str) -> dict | list | None:
    """Get a cached JSON value. Returns None on miss."""
    import json
    r = await get_redis()
    raw = await _safe_redis_op(r.get(f"{_CACHE_PREFIX}{key}"))
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set(key: str, data: dict | list, ttl: int) -> None:
    """Set a JSON value in cache with TTL in seconds."""
    import json
    r = await get_redis()
    await _safe_redis_op(r.set(f"{_CACHE_PREFIX}{key}", json.dumps(data), ex=ttl))
