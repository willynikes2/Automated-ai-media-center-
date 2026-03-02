"""Async SQLAlchemy 2.0 database engine, session factory, and dependency."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from shared.config import get_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Declarative base for all ORM models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


# ---------------------------------------------------------------------------
# Module-level engine and session factory (initialised lazily via init_db)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(url: str | None = None) -> AsyncEngine:
    """Create the async engine and session factory.

    Parameters
    ----------
    url:
        Database connection string.  Falls back to ``get_config().database_url``.
    """
    global _engine, _async_session_factory  # noqa: PLW0603

    if url is None:
        url = get_config().database_url

    _engine = create_async_engine(
        url,
        echo=False,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
        pool_timeout=30,
    )
    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("Database engine initialised for %s", url.split("@")[-1])
    return _engine


def get_engine() -> AsyncEngine:
    """Return the current engine, initialising if necessary."""
    if _engine is None:
        init_db()
    assert _engine is not None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the current session factory, initialising if necessary."""
    if _async_session_factory is None:
        init_db()
    assert _async_session_factory is not None
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Usage::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
