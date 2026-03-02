"""Health-check endpoint -- verifies DB and Redis connectivity."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from shared.database import get_session_factory
from shared.redis_client import get_redis
from shared.schemas import HealthResponse

logger = logging.getLogger("agent-api.health")
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service health including DB and Redis status."""

    db_status = "connected"
    redis_status = "connected"

    # -- Database ping ---------------------------------------------------
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        db_status = "error"

    # -- Redis ping ------------------------------------------------------
    try:
        redis = await get_redis()
        await redis.ping()
    except Exception:
        logger.exception("Redis health check failed")
        redis_status = "error"

    return HealthResponse(
        status="ok",
        db=db_status,
        redis=redis_status,
        version="1.0.0",
    )
