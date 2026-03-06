"""Invisible Arr Agent Worker -- Observer+Fixer acquisition pipeline.

The worker adds requests to Sonarr/Radarr and then *observes* until the file
appears.  It never fails a job on a timer -- instead it diagnoses actual
problems (via the diagnostics module) and applies targeted fixes (via
auto_fixer).  Only after exhausting fix attempts does it park the job as
UNAVAILABLE.

Job lifecycle:
  CREATED -> SEARCHING -> DOWNLOADING -> VERIFYING -> DONE
  (INVESTIGATING when a problem is detected and being fixed)
  (MONITORED when content is unreleased; background task resumes when available)
  (UNAVAILABLE when all fix attempts exhausted)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select, update as sa_update

from auto_fixer import apply_fix, MAX_FIX_ATTEMPTS
from diagnostics import diagnose_no_grab, diagnose_stalled_download, save_diagnostic, mark_diagnostic_resolved

from shared.config import get_config
from shared.database import get_session_factory
from shared.models import Job, JobEvent, JobState, User
from shared.radarr_client import RadarrClient
from shared.redis_client import (
    clear_rdt_ready,
    clear_download_progress,
    enqueue_qc,
    get_rdt_ready,
    set_download_progress,
)
from shared.sonarr_client import SonarrClient
from shared.tmdb_client import TMDBClient

logger = logging.getLogger("agent-worker.worker")

# Quality profile IDs created by Recyclarr (Trash Guides)
# "HD Bluray + WEB" in Radarr, "WEB-1080p" in Sonarr
RADARR_QUALITY_PROFILE_ID = 7
SONARR_QUALITY_PROFILE_ID = 7

# ── Observation thresholds (NOT timeouts — job doesn't fail at these) ─────
NO_GRAB_INVESTIGATE_AFTER = 300     # 5 min: if no grab, run diagnostics
DOWNLOAD_STALL_INVESTIGATE = 600    # 10 min: if download not progressing, investigate
IMPORT_INVESTIGATE_AFTER = 600      # 10 min: after download done, if no file, investigate
MAX_OBSERVE_TIME = 14400            # 4 hours: absolute max observation before parking
OBSERVE_POLL_INTERVAL = 30          # 30s between observation checks


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


async def process_job(job_id: str) -> None:
    """Execute the observer+fixer acquisition pipeline.

    1. Resolve title (TMDB lookup)
    2. Add to Arr + trigger search -> SEARCHING
    3. Observe: wait for webhooks/file to appear, diagnose actual problems
    """
    job = await get_job(job_id)
    user = await get_user(job.user_id)
    config = get_config()
    try:
        await ensure_user_media_permissions(user)
    except Exception:
        logger.warning("Could not normalize media permissions for user %s", user.id, exc_info=True)

    try:
        # Phase 1: SEARCHING — resolve + add to Arr + trigger search
        await transition(job, JobState.SEARCHING, "Resolving title and searching for downloads")

        async with TMDBClient(config.tmdb_api_key) as tmdb:
            try:
                tmdb_id, canonical_title, year = await tmdb.resolve(
                    job.query or job.title, job.media_type
                )
            except Exception as exc:
                await transition(job, JobState.INVESTIGATING, f"Could not identify title: {exc}")
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
            await transition(job, JobState.MONITORED, exc.monitor_reason, metadata={"original_error": str(exc)})
            return
        except Exception as exc:
            await transition(job, JobState.INVESTIGATING, f"Failed to add to library: {exc}")
            return

        # Phase 2: OBSERVE — let Arr do its thing, watch for completion or problems
        await _observe_until_done(job, user)

    except ContentNotReleasedError as exc:
        await transition(job, JobState.MONITORED, exc.monitor_reason)
    except Exception as exc:
        logger.exception("Unhandled error in job %s: %s", job_id, exc)
        await transition(job, JobState.INVESTIGATING, f"Unexpected error — investigating: {str(exc)[:200]}")


# ===========================================================================
# Observer loop
# ===========================================================================


async def _observe_until_done(job: Job, user: User) -> None:
    """Observe Arr until file appears in user library. No timer-based failures.

    Checks (every OBSERVE_POLL_INTERVAL seconds):
    1. Does the file exist already? (hasFile from Arr API) -> finalize
    2. Did a webhook signal completion? (rdt_ready in Redis) -> wait for import, finalize
    3. Is there a queue item? -> track progress, check for stalls/errors
    4. No queue item after NO_GRAB_INVESTIGATE_AFTER? -> diagnose and fix
    5. Absolute max observation time -> park as MONITORED
    """
    start = time.monotonic()
    last_progress = -1
    stall_start: float | None = None
    fix_attempt = 0
    grabbed = False

    while True:
        elapsed = time.monotonic() - start

        # Refresh job state from DB (webhook handler may have updated it)
        job = await get_job(str(job.id))

        # ── Check 1: File already exists? ──
        has_file = await _check_has_file(job)
        if has_file:
            await _finalize_import(job, user)
            return

        # ── Check 2: Webhook/RDT signal? ──
        rdt_signal = await get_rdt_ready(str(job.id))
        if rdt_signal:
            await clear_rdt_ready(str(job.id))
            # Give Arr time to complete import
            for _ in range(30):  # up to 5 min
                await asyncio.sleep(10)
                if await _check_has_file(job):
                    await _finalize_import(job, user)
                    return
            # Signal received but file not there yet — continue observing

        # ── Check 3: Queue item with progress? ──
        queue_item = await _find_our_queue_item(job)

        if queue_item:
            grabbed = True
            if job.state != JobState.DOWNLOADING.value:
                await transition(job, JobState.DOWNLOADING, "Download in progress")

            progress = _get_download_progress(queue_item)
            title = queue_item.get("title", job.title)
            timeleft = queue_item.get("timeleft", "")
            detail = f"{title} ({timeleft})" if timeleft else title
            await set_download_progress(str(job.id), progress, detail)

            # Check queue item for errors
            tds = queue_item.get("trackedDownloadStatus", "")
            status = queue_item.get("status", "")

            if tds in ("warning", "error") or status in ("importBlocked", "importFailed"):
                diagnosis = await diagnose_stalled_download(job, queue_item)
                factory = get_session_factory()
                async with factory() as session:
                    await save_diagnostic(session, job.id, diagnosis)
                    await session.commit()

                if fix_attempt < MAX_FIX_ATTEMPTS:
                    await transition(job, JobState.INVESTIGATING, diagnosis.user_message)
                    outcome = await apply_fix(job, diagnosis, fix_attempt)
                    fix_attempt += 1
                    logger.info("Auto-fix #%d for job %s: %s -> %s", fix_attempt, job.id, diagnosis.auto_fix, outcome)
                    stall_start = None
                    await asyncio.sleep(OBSERVE_POLL_INTERVAL)
                    continue
                else:
                    await transition(job, JobState.UNAVAILABLE, diagnosis.user_message)
                    await clear_download_progress(str(job.id))
                    return

            # Check for stall (no progress change)
            if progress == last_progress and 0 < progress < 100:
                if stall_start is None:
                    stall_start = time.monotonic()
                elif time.monotonic() - stall_start > DOWNLOAD_STALL_INVESTIGATE:
                    diagnosis = await diagnose_stalled_download(job, queue_item)
                    factory = get_session_factory()
                    async with factory() as session:
                        await save_diagnostic(session, job.id, diagnosis)
                        await session.commit()
                    if fix_attempt < MAX_FIX_ATTEMPTS:
                        await transition(job, JobState.INVESTIGATING, diagnosis.user_message)
                        outcome = await apply_fix(job, diagnosis, fix_attempt)
                        fix_attempt += 1
                        stall_start = None
                        await asyncio.sleep(OBSERVE_POLL_INTERVAL)
                        continue
                    else:
                        await transition(job, JobState.UNAVAILABLE, diagnosis.user_message)
                        await clear_download_progress(str(job.id))
                        return
            else:
                stall_start = None
            last_progress = progress

        elif not grabbed and elapsed > NO_GRAB_INVESTIGATE_AFTER:
            # No queue item and nothing grabbed — diagnose why
            factory = get_session_factory()
            async with factory() as session:
                diagnosis = await diagnose_no_grab(job, session)
                await save_diagnostic(session, job.id, diagnosis)
                await session.commit()

            if diagnosis.category == "content_not_released":
                raise ContentNotReleasedError(diagnosis.user_message)

            if diagnosis.auto_fix in ("set_monitored", "set_monitored_daily"):
                await transition(job, JobState.MONITORED, diagnosis.user_message)
                return

            if fix_attempt < MAX_FIX_ATTEMPTS:
                await transition(job, JobState.INVESTIGATING, diagnosis.user_message)
                outcome = await apply_fix(job, diagnosis, fix_attempt)
                fix_attempt += 1
                logger.info("Auto-fix #%d for job %s: %s -> %s", fix_attempt, job.id, diagnosis.auto_fix, outcome)
                # Reset observation after fix — give it time to work
                start = time.monotonic()
                grabbed = False
                await asyncio.sleep(OBSERVE_POLL_INTERVAL)
                continue
            else:
                await transition(job, JobState.UNAVAILABLE, diagnosis.user_message)
                return

        # ── Check 5: Absolute safety net ──
        if elapsed > MAX_OBSERVE_TIME:
            logger.warning("Job %s exceeded max observe time (%ds)", job.id, MAX_OBSERVE_TIME)
            await transition(job, JobState.MONITORED,
                "Taking longer than expected — we'll keep monitoring and try again later")
            await clear_download_progress(str(job.id))
            return

        await asyncio.sleep(OBSERVE_POLL_INTERVAL)


# ===========================================================================
# Observer helpers
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


async def _find_our_queue_item(job: Job) -> dict | None:
    """Find our job's item in the Arr download queue."""
    try:
        if job.media_type == "movie" and job.radarr_movie_id:
            async with RadarrClient() as client:
                queue = await client.get_queue(page_size=100, include_movie=True)
                for item in queue.get("records", []):
                    if item.get("movieId") == job.radarr_movie_id:
                        # Capture correlation data
                        if not job.arr_queue_id:
                            await update_job_field(job, arr_queue_id=item.get("id"))
                        download_id = item.get("downloadId", "")
                        if download_id and not job.rd_torrent_id:
                            await update_job_field(job, rd_torrent_id=download_id)
                        return item
        elif job.sonarr_series_id:
            async with SonarrClient() as client:
                queue = await client.get_queue(page_size=100, include_series=True)
                for item in queue.get("records", []):
                    if item.get("seriesId") == job.sonarr_series_id:
                        if not job.arr_queue_id:
                            await update_job_field(job, arr_queue_id=item.get("id"))
                        download_id = item.get("downloadId", "")
                        if download_id and not job.rd_torrent_id:
                            await update_job_field(job, rd_torrent_id=download_id)
                        return item
    except Exception as exc:
        logger.warning("Error checking queue for job %s: %s", job.id, exc)
    return None


def _get_download_progress(queue_item: dict) -> int:
    """Extract download progress percentage from queue item."""
    size = queue_item.get("size", 0)
    sizeleft = queue_item.get("sizeleft", 0)
    if size > 0:
        return max(0, min(100, int(((size - sizeleft) / size) * 100)))
    return 0


async def _finalize_import(job: Job, user: User) -> None:
    """File confirmed in Arr — update storage, enqueue QC, transition to VERIFYING."""
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

    # Mark diagnostics resolved
    factory = get_session_factory()
    async with factory() as session:
        await mark_diagnostic_resolved(session, job.id)
        await session.commit()

    # Clear download progress
    await clear_download_progress(str(job.id))

    # Transition to VERIFYING and enqueue QC
    await transition(job, JobState.VERIFYING, "File imported, running quality check")

    try:
        await enqueue_qc(str(job.id))
        logger.info("Enqueued QC job for %s", job.id)
    except Exception:
        logger.exception("Failed to enqueue QC job for %s", job.id)

    await clear_rdt_ready(str(job.id))


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

        # Determine monitor type — use "none" initially, then enable
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
