"""Garbage collection for orphaned canonical content.

Runs hourly. Removes canonical content that no active users reference,
after a 7-day grace period.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select

from shared.database import get_session_factory
from shared.models import CanonicalContent, UserContent
from shared.radarr_client import RadarrClient
from shared.sonarr_client import SonarrClient

logger = logging.getLogger("agent-worker.gc")

GC_INTERVAL = int(os.environ.get("GC_INTERVAL_SECONDS", "3600"))  # 1 hour
GC_GRACE_DAYS = int(os.environ.get("GC_GRACE_DAYS", "7"))


async def run_gc(shutdown_event: asyncio.Event) -> None:
    """Background task: periodically garbage-collect orphaned canonical content."""
    logger.info("Canonical GC starting (interval=%ds, grace=%dd)", GC_INTERVAL, GC_GRACE_DAYS)

    while not shutdown_event.is_set():
        try:
            await _gc_cycle()
        except Exception:
            logger.exception("GC cycle error")

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=GC_INTERVAL)
            break
        except asyncio.TimeoutError:
            pass

    logger.info("Canonical GC stopped")


async def _gc_cycle() -> None:
    """One GC pass: find and remove orphaned canonical content past grace period."""
    grace_cutoff = datetime.utcnow() - timedelta(days=GC_GRACE_DAYS)
    factory = get_session_factory()

    async with factory() as session:
        # Find canonical entries that are GC-eligible and past grace period
        result = await session.execute(
            select(CanonicalContent).where(
                CanonicalContent.gc_eligible_at.isnot(None),
                CanonicalContent.gc_eligible_at < grace_cutoff,
            )
        )
        candidates = list(result.scalars().all())

        if not candidates:
            return

        logger.info("GC: found %d candidates past grace period", len(candidates))

        for entry in candidates:
            # Double-check: no active references
            active_count = await session.scalar(
                select(func.count(UserContent.id)).where(
                    UserContent.canonical_content_id == entry.id,
                    UserContent.status == "active",
                )
            )
            if active_count and active_count > 0:
                entry.gc_eligible_at = None
                logger.info("GC: skipping %s — %d active refs", entry.title, active_count)
                continue

            # Remove from Radarr/Sonarr (canonical instance)
            try:
                if entry.media_type == "movie" and entry.radarr_id:
                    async with RadarrClient() as radarr:
                        await radarr.delete_movie(entry.radarr_id, delete_files=True)
                elif entry.sonarr_id:
                    async with SonarrClient() as sonarr:
                        await sonarr.delete_series(entry.sonarr_id, delete_files=True)
            except Exception:
                logger.warning("GC: failed to remove from Arr: %s", entry.title, exc_info=True)

            # Delete canonical files from disk
            try:
                if os.path.exists(entry.canonical_path):
                    shutil.rmtree(entry.canonical_path)
                    logger.info("GC: deleted %s", entry.canonical_path)
            except Exception:
                logger.warning("GC: failed to delete %s", entry.canonical_path, exc_info=True)
                continue

            # Clean up DB: remove user_content rows, then canonical_content row
            await session.execute(
                delete(UserContent).where(UserContent.canonical_content_id == entry.id)
            )
            await session.delete(entry)
            logger.info("GC: removed canonical entry: %s (tmdb=%d)", entry.title, entry.tmdb_id)

        await session.commit()
