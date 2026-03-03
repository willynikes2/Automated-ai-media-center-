"""Invisible Arr Agent API -- FastAPI entry point."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Ensure the shared package is importable when running inside the container
# (shared/ is volume-mounted at /app/shared).
# ---------------------------------------------------------------------------
_app_root = Path("/app")
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

from shared.database import init_db, get_engine  # noqa: E402
from shared.redis_client import get_redis  # noqa: E402

from routers import health, requests, jobs, prefs, webhooks, auth, tmdb, search, storage, admin, reseller  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent-api")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialise DB engine + Redis on startup; tear down on shutdown."""
    logger.info("Starting agent-api lifespan -- initialising resources")

    # Database ----------------------------------------------------------
    try:
        init_db()
        logger.info("Database engine initialised")
    except Exception:
        logger.exception("Failed to initialise database engine")
        raise

    # Redis -------------------------------------------------------------
    redis = None
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("Redis connection established")
    except Exception:
        logger.exception("Failed to connect to Redis")
        raise

    yield  # ---- application runs ----

    # Shutdown ----------------------------------------------------------
    logger.info("Shutting down agent-api lifespan")
    if redis is not None:
        await redis.aclose()
        logger.info("Redis connection closed")
    await get_engine().dispose()
    logger.info("Database engine disposed")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Invisible Arr – Agent API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS (allow everything in dev) ----------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers ---------------------------------------------------------------
app.include_router(health.router, tags=["health"])
app.include_router(requests.router, prefix="/v1", tags=["requests"])
app.include_router(jobs.router, prefix="/v1", tags=["jobs"])
app.include_router(prefs.router, prefix="/v1", tags=["prefs"])
app.include_router(webhooks.router, prefix="/v1", tags=["webhooks"])
app.include_router(auth.router, prefix="/v1", tags=["auth"])
app.include_router(tmdb.router, prefix="/v1", tags=["tmdb"])
app.include_router(search.router, prefix="/v1", tags=["search"])
app.include_router(storage.router, prefix="/v1", tags=["storage"])
app.include_router(admin.router, prefix="/v1", tags=["admin"])
app.include_router(reseller.router, prefix="/v1", tags=["reseller"])


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    logger.warning("ValueError: %s", exc)
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(KeyError)
async def key_error_handler(_request: Request, exc: KeyError) -> JSONResponse:
    logger.warning("KeyError: %s", exc)
    return JSONResponse(status_code=400, content={"detail": f"Missing key: {exc}"})


@app.exception_handler(Exception)
async def generic_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
