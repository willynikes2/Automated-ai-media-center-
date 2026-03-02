"""IPTV Gateway service -- FastAPI application entry point.

Provides M3U playlist management, XMLTV EPG with timezone conversion,
and dynamic playlist generation for IPTV clients.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import get_config
from shared.database import init_db, get_engine, Base
from routers import sources, channels, playlist

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise database and Redis on startup; tear down on shutdown."""
    cfg = get_config()

    # Database
    engine = init_db(cfg.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")

    # Redis
    redis_client = redis.from_url(
        cfg.redis_url,
        decode_responses=True,
    )
    try:
        await redis_client.ping()
        logger.info("Redis connected at %s", cfg.redis_url)
    except redis.ConnectionError:
        logger.warning("Redis not reachable at %s -- EPG caching disabled", cfg.redis_url)

    app.state.redis = redis_client

    yield

    # Shutdown
    await redis_client.aclose()
    engine = get_engine()
    await engine.dispose()
    logger.info("IPTV Gateway shutdown complete")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Invisible Arr -- IPTV Gateway",
    version="0.1.0",
    description="IPTV playlist management, EPG timezone conversion, and dynamic M3U/XMLTV generation.",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(sources.router)
app.include_router(channels.router)
app.include_router(playlist.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Basic health check endpoint."""
    cfg = get_config()
    db_status = "ok"
    redis_status = "unknown"

    # Check Redis
    redis_client: redis.Redis | None = getattr(app.state, "redis", None)
    if redis_client is not None:
        try:
            await redis_client.ping()
            redis_status = "ok"
        except redis.ConnectionError:
            redis_status = "unreachable"
    else:
        redis_status = "not_configured"

    return {
        "status": "ok",
        "db": db_status,
        "redis": redis_status,
        "version": "0.1.0",
    }
