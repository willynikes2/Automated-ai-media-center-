"""Invisible Arr Agent Worker -- Webhook-driven event handler.

The worker adds requests to Sonarr/Radarr, triggers a search, and exits.
All subsequent state transitions (DOWNLOADING, IMPORTING, AVAILABLE) are
driven by webhooks from Radarr/Sonarr handled in agent-api.

Job lifecycle:
  REQUESTED -> SEARCHING -> [webhook-driven] -> DOWNLOADING -> IMPORTING -> AVAILABLE
  (WAITING when content is unreleased; background task resumes when available)
  (FAILED when all download sources exhausted or unrecoverable error)
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select, update as sa_update

from shared.config import get_config
from shared.database import get_session_factory
from shared.models import Job, JobEvent, JobState, User
from shared.radarr_client import RadarrClient
from shared.redis_client import (
    clear_download_progress,
    clear_rdt_ready,
    enqueue_qc,
    set_download_progress,
)
from shared.sonarr_client import SonarrClient
from shared.tmdb_client import TMDBClient

logger = logging.getLogger("agent-worker.worker")

# Quality profile IDs created by Recyclarr (Trash Guides)
# "HD Bluray + WEB" in Radarr, "WEB-1080p" in Sonarr
RADARR_QUALITY_PROFILE_ID = 7
SONARR_QUALITY_PROFILE_ID = 7

# Search timeout: if no grab after this many seconds, mark FAILED
SEARCH_TIMEOUT = int(os.environ.get("SEARCH_TIMEOUT", "7200"))  # 2 hours


# ===========================================================================
# Helper functions
# ===========================================================================


async def get_job(job_id: str) -> Job:
    """Fetch a Job row by primary key. Raises if not found."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        session.expunge(job)
        return job


async def get_user(user_id: uuid.UUID) -> User:
    """Fetch a User row. Raises if not found."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"User {user_id} not found")
        session.expunge(user)
        return user


async def transition(
    job: Job,
    new_state: JobState,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a state transition: update the job row and append a JobEvent."""
    now = datetime.utcnow()
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            sa_update(Job)
            .where(Job.id == job.id)
            .values(state=new_state.value, updated_at=now)
        )
        event = JobEvent(
            job_id=job.id,
            state=new_state.value,
            message=message,
            metadata_json=metadata,
            created_at=now,
        )
        session.add(event)
        await session.commit()

    job.state = new_state
    job.updated_at = now
    logger.info("Job %s -> %s: %s", job.id, new_state.value, message)


async def update_job_field(job: Job, **kwargs: Any) -> None:
    """Update arbitrary fields on a job row."""
    kwargs["updated_at"] = datetime.utcnow()
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            sa_update(Job).where(Job.id == job.id).values(**kwargs)
        )
        await session.commit()
    for k, v in kwargs.items():
        if hasattr(job, k):
            setattr(job, k, v)


async def update_storage_used(user_id: uuid.UUID, added_gb: float) -> None:
    """Increment the user's storage_used_gb after a successful import."""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            sa_update(User)
            .where(User.id == user_id)
            .values(storage_used_gb=User.storage_used_gb + added_gb)
        )
        await session.commit()
    logger.info("Updated storage for user %s: +%.2f GB", user_id, added_gb)


def _apply_permissions_tree(root: Path, uid: int, gid: int) -> None:
    """Best-effort ownership/mode normalization for a user media tree."""
    if not root.exists():
        return
    for path in [root, *root.rglob("*")]:
        try:
            os.chown(path, uid, gid)
        except Exception:
            pass
        try:
            if path.is_dir():
                path.chmod(0o777)
            else:
                path.chmod(0o666)
        except Exception:
            pass


async def ensure_user_media_permissions(user: User) -> None:
    """Ensure the user's media roots are writable by Arr/runtime users."""
    config = get_config()
    uid = int(config.puid)
    gid = int(config.pgid)
    user_root = Path(config.media_path) / "users" / str(user.id)

    # Ensure base folders exist first.
    for base in (user_root, user_root / "Movies", user_root / "TV"):
        base.mkdir(parents=True, exist_ok=True)

    await asyncio.to_thread(_apply_permissions_tree, user_root, uid, gid)


class ContentNotReleasedError(Exception):
    """Raised when content is not yet digitally available (announced/inCinemas/unaired)."""

    def __init__(self, message: str, monitor_reason: str = ""):
        super().__init__(message)
        self.monitor_reason = monitor_reason or message


# ===========================================================================
# Main pipeline
# ===========================================================================


async def process_request(job_id: str) -> None:
    """Add request to Radarr/Sonarr and trigger search, then exit.

    The worker's job is done after triggering the search. All subsequent
    state transitions (DOWNLOADING, IMPORTING, AVAILABLE) are driven by
    webhooks from Radarr/Sonarr.
    """
    job = await get_job(job_id)
    user = await get_user(job.user_id)
    config = get_config()
    try:
        await ensure_user_media_permissions(user)
    except Exception:
        logger.warning("Could not normalize media permissions for user %s", user.id, exc_info=True)

    try:
        # Resolve title (TMDB lookup) and add to Arr
        await transition(job, JobState.SEARCHING, "Resolving title and searching for downloads")

        async with TMDBClient(config.tmdb_api_key) as tmdb:
            try:
                tmdb_id, canonical_title, year = await tmdb.resolve(
                    job.query or job.title, job.media_type
                )
            except Exception as exc:
                await transition(job, JobState.FAILED, f"Could not identify title: {exc}")
                return

        await update_job_field(job, tmdb_id=tmdb_id, title=canonical_title)
        logger.info("Resolved '%s' -> TMDB %d '%s' (%d)", job.query or job.title, tmdb_id, canonical_title, year)

        try:
            if job.media_type == "movie":
                arr_id = await _add_to_radarr(job, user, tmdb_id, canonical_title)
                await update_job_field(job, radarr_movie_id=arr_id, acquisition_method="radarr")
            else:
                arr_id = await _add_to_sonarr(job, user, tmdb_id, canonical_title)
                await update_job_field(job, sonarr_series_id=arr_id, acquisition_method="sonarr")
        except ContentNotReleasedError as exc:
            await transition(job, JobState.WAITING, exc.monitor_reason, metadata={"original_error": str(exc)})
            return
        except Exception as exc:
            await transition(job, JobState.FAILED, f"Failed to add to library: {exc}")
            return

        # Search triggered by _add_to_radarr/_add_to_sonarr.
        # Worker is done -- webhooks drive the rest.
        logger.info("Job %s: search triggered, worker exiting (webhooks drive the rest)", job.id)

    except ContentNotReleasedError as exc:
        await transition(job, JobState.WAITING, exc.monitor_reason)
    except Exception as exc:
        logger.exception("Unhandled error in job %s: %s", job_id, exc)
        await transition(job, JobState.FAILED, f"Unexpected error: {str(exc)[:200]}")


# ===========================================================================
# Webhook-driven event handlers
# ===========================================================================


async def handle_download_failed(job_id: str, source: str) -> None:
    """Smart retry cascade: RD -> Usenet -> Torrent -> FAILED.

    Called by webhook handler when Radarr/Sonarr reports a download failure.
    `source` is the download client that failed: "rd", "usenet", or "torrent".
    """
    job = await get_job(job_id)

    # Determine next protocol to try
    cascade = {"rd": "usenet", "usenet": "torrent", "torrent": None}
    next_protocol = cascade.get(source)

    if next_protocol is None:
        # All sources exhausted
        await transition(job, JobState.FAILED,
            f"Download failed from all sources (last: {source})",
            metadata={"last_source": source})
        await clear_download_progress(str(job.id))
        return

    # Try next protocol via re-search
    # For now, just trigger a standard Radarr/Sonarr re-search
    # Task 4 will add protocol-filtered release grab
    logger.info("Download failed from %s, triggering re-search for %s (job %s)", source, next_protocol, job.id)
    await transition(job, JobState.SEARCHING, f"Retrying with {next_protocol} after {source} failure")

    try:
        if job.media_type == "movie" and job.radarr_movie_id:
            async with RadarrClient() as radarr:
                await radarr.search_movie(job.radarr_movie_id)
        elif job.sonarr_series_id:
            async with SonarrClient() as sonarr:
                if job.episode and job.season:
                    episodes = await sonarr.get_episodes(job.sonarr_series_id, job.season)
                    target_ep = next((e for e in episodes if e.get("episodeNumber") == job.episode), None)
                    if target_ep:
                        await sonarr.search_episodes([target_ep["id"]])
                    else:
                        await sonarr.search_season(job.sonarr_series_id, job.season)
                elif job.season:
                    await sonarr.search_season(job.sonarr_series_id, job.season)
                else:
                    await sonarr.search_series(job.sonarr_series_id)
    except Exception as exc:
        logger.exception("Re-search failed for job %s: %s", job.id, exc)
        await transition(job, JobState.FAILED, f"Re-search failed after {source} failure: {str(exc)[:200]}")


async def check_timeouts() -> None:
    """Mark SEARCHING jobs as FAILED if no grab after SEARCH_TIMEOUT."""
    factory = get_session_factory()
    async with factory() as session:
        cutoff = datetime.utcnow() - timedelta(seconds=SEARCH_TIMEOUT)
        result = await session.execute(
            select(Job).where(
                Job.state == JobState.SEARCHING.value,
                Job.updated_at < cutoff,
            )
        )
        timed_out = list(result.scalars().all())

    for job in timed_out:
        logger.warning("Job %s timed out in SEARCHING state after %ds", job.id, SEARCH_TIMEOUT)
        await transition(job, JobState.FAILED, "No releases found matching quality settings")


# ===========================================================================
# Finalize import (called by webhook handler when file is imported)
# ===========================================================================


async def _finalize_import(job: Job, user: User) -> None:
    """File confirmed in Arr -- update storage, enqueue QC, transition to IMPORTING."""
    file_size = 0
    imported_path = ""

    try:
        if job.media_type == "movie" and job.radarr_movie_id:
            async with RadarrClient() as client:
                movie = await client.get_movie(job.radarr_movie_id)
                movie_file = movie.get("movieFile", {})
                file_size = movie_file.get("size", 0)
                imported_path = movie_file.get("path") or movie_file.get("relativePath", "")
        elif job.sonarr_series_id:
            async with SonarrClient() as client:
                if job.episode and job.season:
                    episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
                    target = next((e for e in episodes if e.get("episodeNumber") == job.episode), None)
                    if target and target.get("episodeFile"):
                        ep_file = target["episodeFile"]
                        file_size = ep_file.get("size", 0)
                        imported_path = ep_file.get("path") or ep_file.get("relativePath", "")
                    elif target and target.get("episodeFileId"):
                        # episodeFile not embedded, but we know it exists
                        imported_path = f"S{job.season:02d}E{job.episode:02d}"
    except Exception:
        logger.exception("Error getting file info for finalize on job %s", job.id)

    if imported_path:
        await update_job_field(job, imported_path=imported_path)

    # Update storage tracking
    if file_size > 0:
        gb = file_size / (1024 ** 3)
        await update_storage_used(job.user_id, gb)

    # Clear download progress
    await clear_download_progress(str(job.id))

    # Transition to IMPORTING and enqueue QC
    await transition(job, JobState.IMPORTING, "File imported, running quality check")

    try:
        await enqueue_qc(str(job.id))
        logger.info("Enqueued QC job for %s", job.id)
    except Exception:
        logger.exception("Failed to enqueue QC job for %s", job.id)

    await clear_rdt_ready(str(job.id))


# ===========================================================================
# Arr has-file check
# ===========================================================================


async def _check_has_file(job: Job) -> bool:
    """Check if Arr reports the media has a file."""
    try:
        if job.media_type == "movie" and job.radarr_movie_id:
            async with RadarrClient() as client:
                movie = await client.get_movie(job.radarr_movie_id)
                return movie.get("hasFile", False)
        elif job.sonarr_series_id:
            async with SonarrClient() as client:
                if job.episode and job.season:
                    episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
                    target = next((e for e in episodes if e.get("episodeNumber") == job.episode), None)
                    return target.get("hasFile", False) if target else False
                elif job.season:
                    episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
                    return any(e.get("hasFile", False) for e in episodes)
    except Exception as exc:
        logger.warning("Error checking hasFile for job %s: %s", job.id, exc)
    return False


# ===========================================================================
# Sonarr / Radarr integration
# ===========================================================================


async def _add_to_radarr(
    job: Job, user: User, tmdb_id: int, title: str
) -> int:
    """Add a movie to Radarr. Returns the Radarr movie ID."""
    preferred_root = f"/data/media/users/{user.id}/Movies"

    async with RadarrClient() as radarr:
        root_folder_path = await _ensure_radarr_root_folder(radarr, preferred_root)

        # Check if already in Radarr
        existing = await radarr.get_movie_by_tmdb(tmdb_id)
        if existing:
            movie_id = existing["id"]
            logger.info("Movie already in Radarr (id=%d), triggering search", movie_id)
            await radarr.search_movie(movie_id)
            return movie_id

        movie = await radarr.add_movie(
            tmdb_id=tmdb_id,
            title=title,
            root_folder_path=root_folder_path,
            quality_profile_id=RADARR_QUALITY_PROFILE_ID,
            search_for_movie=True,
        )
        logger.info("Added movie to Radarr: %s (id=%d)", title, movie["id"])
        return movie["id"]


async def _add_to_sonarr(
    job: Job, user: User, tmdb_id: int, title: str
) -> int:
    """Add a series to Sonarr. Returns the Sonarr series ID."""
    preferred_root = f"/data/media/users/{user.id}/TV"

    async with SonarrClient() as sonarr:
        root_folder_path = await _ensure_sonarr_root_folder(sonarr, preferred_root)

        # TMDB -> TVDB lookup (Sonarr uses TVDB)
        config = get_config()
        async with TMDBClient(config.tmdb_api_key) as tmdb:
            external_ids = await tmdb.get_external_ids(tmdb_id, "tv")
            tvdb_id = external_ids.get("tvdb_id")
            if not tvdb_id:
                raise ValueError(f"No TVDB ID found for TMDB {tmdb_id}")

        # Check if already in Sonarr
        existing = await sonarr.get_series_by_tvdb(tvdb_id)
        if existing:
            series_id = existing["id"]
            logger.info("Series already in Sonarr (id=%d), ensuring monitored + triggering search", series_id)

            # Ensure series is monitored
            if not existing.get("monitored"):
                existing["monitored"] = True
                await sonarr.update_series(existing)
                logger.info("Enabled monitoring on series %d", series_id)

            # Ensure target season is monitored
            await _ensure_sonarr_monitored(sonarr, existing, job)

            if job.season is not None and job.episode is not None:
                # Search for specific episode to avoid rate-limiting indexers
                episodes = await sonarr.get_episodes(series_id, job.season)
                target_ep = next(
                    (e for e in episodes if e.get("episodeNumber") == job.episode),
                    None,
                )
                if target_ep:
                    if not target_ep.get("monitored"):
                        target_ep["monitored"] = True
                        await sonarr.update_episode(target_ep)
                    await sonarr.search_episodes([target_ep["id"]])
                else:
                    logger.warning("Episode S%02dE%02d not found, searching full season", job.season, job.episode)
                    await sonarr.search_season(series_id, job.season)
            elif job.season is not None:
                await sonarr.search_season(series_id, job.season)
            else:
                await sonarr.search_series(series_id)
            return series_id

        # Lookup series metadata for add
        results = await sonarr.lookup_series(f"tvdb:{tvdb_id}")
        if not results:
            raise ValueError(f"Sonarr lookup failed for tvdb:{tvdb_id}")
        lookup = results[0]

        # Determine monitor type -- use "none" initially, then enable
        # monitoring on just the target season/episodes so Sonarr grabs them.
        if job.season is not None:
            monitor = "none"
        else:
            monitor = "all"

        series = await sonarr.add_series(
            tvdb_id=tvdb_id,
            title=lookup.get("title", title),
            title_slug=lookup.get("titleSlug", ""),
            seasons=lookup.get("seasons", []),
            root_folder_path=root_folder_path,
            quality_profile_id=SONARR_QUALITY_PROFILE_ID,
            monitor=monitor,
            search_for_missing=(monitor == "all"),
        )
        series_id = series["id"]
        logger.info("Added series to Sonarr: %s (id=%d)", title, series_id)

        # Ensure monitoring on target season/episodes so Sonarr will grab releases
        await _ensure_sonarr_monitored(sonarr, series, job)

        # If specific season/episode requested, trigger targeted search
        if job.season is not None and job.episode is not None:
            episodes = await sonarr.get_episodes(series_id, job.season)
            target_ep = next(
                (e for e in episodes if e.get("episodeNumber") == job.episode),
                None,
            )
            if target_ep:
                if not target_ep.get("monitored"):
                    target_ep["monitored"] = True
                    await sonarr.update_episode(target_ep)
                await sonarr.search_episodes([target_ep["id"]])
            else:
                logger.warning("Episode S%02dE%02d not found, searching full season", job.season, job.episode)
                await sonarr.search_season(series_id, job.season)
        elif job.season is not None:
            await sonarr.search_season(series_id, job.season)

        return series_id


async def _ensure_radarr_root_folder(radarr: RadarrClient, path: str) -> str:
    """Ensure a movie root folder exists in Radarr configuration.

    Returns the path to use (preferred path, or a safe fallback).
    """
    roots = await radarr.get_root_folders()
    if any(r.get("path") == path for r in roots):
        return path

    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    # Ensure Arr container user can write new per-user roots.
    try:
        p.chmod(0o777)
        parent = p.parent
        if parent.exists():
            parent.chmod(0o777)
    except Exception:
        logger.debug("Could not chmod %s for Radarr access", p, exc_info=True)

    try:
        await radarr.add_root_folder(path)
        logger.info("Registered Radarr root folder: %s", path)
        return path
    except Exception as exc:
        fallback = next((r.get("path") for r in roots if r.get("path")), None)
        if fallback:
            logger.warning(
                "Could not register Radarr root '%s' (%s). Falling back to '%s'.",
                path, exc, fallback,
            )
            return str(fallback)
        raise


async def _ensure_sonarr_monitored(sonarr: SonarrClient, series: dict, job: Job) -> None:
    """Ensure the target season (and series) are monitored in Sonarr.

    Sonarr will not grab releases for unmonitored seasons/episodes, so we
    must enable monitoring before triggering a search.
    """
    series_id = series["id"]
    changed = False

    if not series.get("monitored"):
        series["monitored"] = True
        changed = True

    if job.season is not None:
        for s in series.get("seasons", []):
            if s["seasonNumber"] == job.season and not s.get("monitored"):
                s["monitored"] = True
                changed = True

    if changed:
        await sonarr.update_series(series)
        logger.info("Enabled monitoring on series %d (season=%s)", series_id, job.season)


async def _ensure_sonarr_root_folder(sonarr: SonarrClient, path: str) -> str:
    """Ensure a TV root folder exists in Sonarr configuration.

    Returns the path to use (preferred path, or a safe fallback).
    """
    roots = await sonarr.get_root_folders()
    if any(r.get("path") == path for r in roots):
        return path

    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    try:
        p.chmod(0o777)
        parent = p.parent
        if parent.exists():
            parent.chmod(0o777)
    except Exception:
        logger.debug("Could not chmod %s for Sonarr access", p, exc_info=True)

    try:
        await sonarr.add_root_folder(path)
        logger.info("Registered Sonarr root folder: %s", path)
        return path
    except Exception as exc:
        fallback = next((r.get("path") for r in roots if r.get("path")), None)
        if fallback:
            logger.warning(
                "Could not register Sonarr root '%s' (%s). Falling back to '%s'.",
                path, exc, fallback,
            )
            return str(fallback)
        raise


async def _trigger_jellyfin_refresh() -> None:
    """Best-effort Jellyfin library refresh after stream pointer creation."""
    config = get_config()
    url = f"{config.jellyfin_url.rstrip('/')}/Library/Refresh"
    headers: dict[str, str] = {}
    if config.jellyfin_admin_token:
        headers["X-Emby-Token"] = config.jellyfin_admin_token
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers)
            resp.raise_for_status()
    except Exception:
        logger.warning("Could not trigger Jellyfin refresh at %s", url, exc_info=True)
