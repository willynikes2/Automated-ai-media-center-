"""Auto-fixer -- applies fixes based on diagnostic results.

Given a Diagnosis from the diagnostic engine, this module selects and
executes the appropriate corrective action (blacklist-and-retry, delayed
re-search, queue cleanup, etc.) against the Radarr/Sonarr APIs.
"""

from __future__ import annotations

import asyncio
import logging

from diagnostics import Diagnosis
from shared.models import Job
from shared.radarr_client import RadarrClient
from shared.sonarr_client import SonarrClient

logger = logging.getLogger("agent-worker.auto_fixer")

MAX_FIX_ATTEMPTS = 5
FIX_DELAYS = [60, 120, 300, 600, 1800]  # seconds between fix attempts


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def apply_fix(job: Job, diagnosis: Diagnosis, attempt: int) -> str:
    """Apply an automated fix for *diagnosis* on *job*.

    Returns a short string describing the outcome (for logging / state
    tracking by the caller).
    """
    if attempt >= MAX_FIX_ATTEMPTS:
        logger.warning(
            "Max fix attempts (%d) reached for job=%s action=%s",
            MAX_FIX_ATTEMPTS,
            job.id,
            diagnosis.auto_fix,
        )
        return "max_attempts_exceeded"

    action = diagnosis.auto_fix
    if action is None:
        logger.info("No auto-fix available for job=%s category=%s", job.id, diagnosis.category)
        return "no_fix_available"

    logger.info(
        "Applying fix action=%s attempt=%d/%d for job=%s",
        action,
        attempt + 1,
        MAX_FIX_ATTEMPTS,
        job.id,
    )

    try:
        if action in ("set_monitored", "set_monitored_daily"):
            # Caller is responsible for persisting the monitored state change.
            return "set_to_monitored"

        if action == "retry_search_delayed":
            return await _retry_search_delayed(job, attempt)

        if action in ("retry_search", "retry_relaxed_quality"):
            # retry_relaxed_quality: future enhancement will lower quality
            # cutoff before searching.  For now, behaves like retry_search_delayed.
            return await _retry_search_delayed(job, attempt)

        if action == "blacklist_and_research":
            return await _blacklist_and_research(job)

        if action in ("clear_and_reimport", "retry_import", "retry_download"):
            return await _clear_and_research(job)

        if action == "restart_arr":
            logger.warning(
                "Arr restart requested for job=%s -- waiting for recovery",
                job.id,
            )
            await asyncio.sleep(60)
            return "waited_for_arr_recovery"

        if action == "relax_quality":
            # Future: programmatically lower quality cutoff.
            # For now, retry search in case new releases appear.
            return await _retry_search_delayed(job, attempt)

        if action == "free_disk_space":
            # Cannot safely auto-free disk; log and let operator handle it.
            logger.error(
                "Disk full detected for job=%s -- manual intervention required",
                job.id,
            )
            return "no_fix_available"

        logger.warning("Unknown fix action '%s' for job=%s", action, job.id)
        return "no_fix_available"

    except Exception:
        logger.exception("Fix action=%s failed for job=%s", action, job.id)
        return "fix_error"


# ---------------------------------------------------------------------------
# Fix strategies
# ---------------------------------------------------------------------------


async def _retry_search_delayed(job: Job, attempt: int) -> str:
    """Wait an escalating delay then trigger a new Arr search."""
    delay = FIX_DELAYS[min(attempt, len(FIX_DELAYS) - 1)]
    logger.info("Waiting %ds before retry search for job=%s", delay, job.id)
    await asyncio.sleep(delay)
    await _trigger_search(job)
    return f"retry_search_after_{delay}s"


async def _blacklist_and_research(job: Job) -> str:
    """Blacklist the current queue item and trigger a fresh search."""
    await _blacklist_current(job)
    await asyncio.sleep(10)
    await _trigger_search(job)
    return "blacklisted_and_researched"


async def _clear_and_research(job: Job) -> str:
    """Remove a stuck queue item (no blacklist) and trigger a fresh search."""
    await _clear_queue_item(job)
    await asyncio.sleep(10)
    await _trigger_search(job)
    return "cleared_and_researched"


# ---------------------------------------------------------------------------
# Arr interaction helpers
# ---------------------------------------------------------------------------


async def _trigger_search(job: Job) -> None:
    """Trigger a new search in the appropriate Arr."""
    try:
        if job.media_type == "movie":
            async with RadarrClient() as client:
                await client.search_movie(job.radarr_movie_id)
            logger.info("Triggered Radarr search for movie_id=%s", job.radarr_movie_id)
        else:
            await _trigger_tv_search(job)
    except Exception:
        logger.exception("Failed to trigger search for job=%s", job.id)
        raise


async def _trigger_tv_search(job: Job) -> None:
    """Trigger the most specific Sonarr search possible for a TV job."""
    async with SonarrClient() as client:
        if job.episode is not None and job.season is not None:
            # Search for a specific episode -- need to resolve episode ID first
            episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
            ep_id = _find_episode_id(episodes, job.season, job.episode)
            if ep_id is not None:
                await client.search_episodes([ep_id])
                logger.info(
                    "Triggered Sonarr episode search series=%s S%02dE%02d (ep_id=%d)",
                    job.sonarr_series_id,
                    job.season,
                    job.episode,
                    ep_id,
                )
                return
            # Fallback: episode not found, search the whole season
            logger.warning(
                "Episode S%02dE%02d not found for series=%s, falling back to season search",
                job.season,
                job.episode,
                job.sonarr_series_id,
            )

        if job.season is not None:
            await client.search_season(job.sonarr_series_id, job.season)
            logger.info(
                "Triggered Sonarr season search series=%s S%02d",
                job.sonarr_series_id,
                job.season,
            )
        else:
            await client.search_series(job.sonarr_series_id)
            logger.info("Triggered Sonarr series search series=%s", job.sonarr_series_id)


def _find_episode_id(episodes: list[dict], season: int, episode: int) -> int | None:
    """Return the Sonarr episode ID matching a season/episode pair."""
    for ep in episodes:
        if ep.get("seasonNumber") == season and ep.get("episodeNumber") == episode:
            return ep.get("id")
    return None


async def _blacklist_current(job: Job) -> None:
    """Blacklist the current queue item for the job."""
    if not job.arr_queue_id:
        logger.warning("No arr_queue_id on job=%s -- cannot blacklist", job.id)
        return

    try:
        if job.media_type == "movie":
            async with RadarrClient() as client:
                await client.delete_queue_item(
                    job.arr_queue_id, blacklist=True, remove_from_client=True,
                )
        else:
            async with SonarrClient() as client:
                await client.delete_queue_item(
                    job.arr_queue_id, blacklist=True, remove_from_client=True,
                )
        logger.info("Blacklisted queue item %d for job=%s", job.arr_queue_id, job.id)
    except Exception:
        logger.exception("Failed to blacklist queue item %d for job=%s", job.arr_queue_id, job.id)
        raise


async def _clear_queue_item(job: Job) -> None:
    """Remove a stuck queue item without blacklisting."""
    if not job.arr_queue_id:
        logger.warning("No arr_queue_id on job=%s -- cannot clear queue item", job.id)
        return

    try:
        if job.media_type == "movie":
            async with RadarrClient() as client:
                await client.delete_queue_item(
                    job.arr_queue_id, blacklist=False, remove_from_client=True,
                )
        else:
            async with SonarrClient() as client:
                await client.delete_queue_item(
                    job.arr_queue_id, blacklist=False, remove_from_client=True,
                )
        logger.info("Cleared queue item %d (no blacklist) for job=%s", job.arr_queue_id, job.id)
    except Exception:
        logger.exception("Failed to clear queue item %d for job=%s", job.arr_queue_id, job.id)
        raise
