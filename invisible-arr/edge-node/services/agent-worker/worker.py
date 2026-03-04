"""Invisible Arr Agent Worker -- Sonarr/Radarr orchestrator.

The worker is a *supervisor*: it adds requests to Sonarr/Radarr (which handle
searching, quality profiles, download client selection), then monitors the
download queue and reports progress until completion.

Job lifecycle:
  CREATED -> RESOLVING -> ADDING -> ACQUIRING -> IMPORTING -> VERIFYING -> DONE
  (FAILED possible at any step; retries handled by main.py)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select, update as sa_update

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

# Timeouts
ARR_GRAB_TIMEOUT_STREAM = 120    # stream-mode: short wait, then fallback to Zurg lookup
ARR_GRAB_TIMEOUT_DOWNLOAD = 600  # download-mode: allow slower indexer/queue grabs
DOWNLOAD_TIMEOUT = 3600      # seconds to wait for download completion
DOWNLOAD_POLL_INTERVAL = 15  # seconds between queue polls
IMPORT_TIMEOUT = 300         # seconds to wait for Arr to import after download
STREAM_SOURCE_TIMEOUT = 300  # seconds to wait for Zurg source in stream mode
STREAM_SOURCE_POLL_INTERVAL = 10


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


def diagnose_failure(error: Exception) -> str:
    """Map raw errors to actionable diagnostic messages."""
    error_str = str(error).lower()

    if "401" in error_str or "unauthorized" in error_str:
        return "Authentication failed. Check API credentials."
    if "403" in error_str or "forbidden" in error_str:
        return "Access denied by upstream service."
    if "429" in error_str or "rate limit" in error_str:
        return "Rate-limited by provider. Retry later."
    if "timeout" in error_str or "timed out" in error_str:
        return "Operation timed out. Source may be slow or unavailable."
    if "no space" in error_str or "disk full" in error_str or "errno 28" in error_str:
        return "Disk full. Free space or increase storage allocation."
    if "connection" in error_str and "refused" in error_str:
        return "Could not connect to a required service."
    if "not found" in error_str or "404" in error_str:
        return "Requested resource was not found."

    return f"Unexpected error: {str(error)[:200]}"


# ===========================================================================
# Main pipeline
# ===========================================================================


async def process_job(job_id: str) -> None:
    """Execute the Sonarr/Radarr orchestrated acquisition pipeline."""
    job = await get_job(job_id)
    user = await get_user(job.user_id)
    config = get_config()
    try:
        await ensure_user_media_permissions(user)
    except Exception:
        logger.warning(
            "Could not normalize media permissions for user %s", user.id, exc_info=True
        )

    # ------------------------------------------------------------------
    # 1. RESOLVING — canonical identity via TMDB
    # ------------------------------------------------------------------
    await transition(job, JobState.RESOLVING, "Resolving TMDB identity")

    async with TMDBClient(config.tmdb_api_key) as tmdb:
        try:
            tmdb_id, canonical_title, year = await tmdb.resolve(
                job.query or job.title, job.media_type
            )
        except Exception as exc:
            await transition(job, JobState.FAILED, f"TMDB resolution failed: {exc}")
            return

    await update_job_field(job, tmdb_id=tmdb_id, title=canonical_title)
    logger.info(
        "Resolved '%s' -> TMDB %d '%s' (%d)",
        job.query or job.title, tmdb_id, canonical_title, year,
    )

    # ------------------------------------------------------------------
    # 2. ADDING — add to Sonarr or Radarr
    # ------------------------------------------------------------------
    await transition(job, JobState.ADDING, f"Adding to {'Sonarr' if job.media_type == 'tv' else 'Radarr'}")

    try:
        method = "stream" if job.acquisition_mode == "stream" else None
        if job.media_type == "movie":
            arr_id = await _add_to_radarr(job, user, tmdb_id, canonical_title)
            await update_job_field(
                job,
                radarr_movie_id=arr_id,
                acquisition_method=method or "radarr",
            )
        else:
            arr_id = await _add_to_sonarr(job, user, tmdb_id, canonical_title)
            await update_job_field(
                job,
                sonarr_series_id=arr_id,
                acquisition_method=method or "sonarr",
            )
    except Exception as exc:
        await transition(job, JobState.FAILED, f"Failed to add to Arr: {exc}")
        return

    # ------------------------------------------------------------------
    # 3. ACQUIRING — wait for Arr to grab + download
    # ------------------------------------------------------------------
    await clear_rdt_ready(str(job.id))
    await transition(job, JobState.ACQUIRING, "Waiting for download")

    try:
        if job.media_type == "movie":
            await _monitor_radarr_download(job)
        else:
            await _monitor_sonarr_download(job)
    except TimeoutError as exc:
        await transition(job, JobState.FAILED, diagnose_failure(exc))
        return
    except Exception as exc:
        await transition(job, JobState.FAILED, diagnose_failure(exc))
        return
    finally:
        await clear_download_progress(str(job.id))

    # ------------------------------------------------------------------
    # 4a. STREAM MODE — create .strm pointer in the user library
    # ------------------------------------------------------------------
    if job.acquisition_mode == "stream":
        await transition(job, JobState.IMPORTING, "Creating Zurg stream pointer")
        try:
            strm_path, target_url = await _materialize_stream_pointer(
                job=job,
                user=user,
                canonical_title=canonical_title,
                year=year,
            )
            await update_job_field(
                job,
                imported_path=strm_path,
                streaming_urls={
                    "primary": target_url,
                    "strm_path": strm_path,
                },
            )
            await _trigger_jellyfin_refresh()
        except Exception as exc:
            await transition(
                job,
                JobState.FAILED,
                f"Failed to create streaming pointer: {diagnose_failure(exc)}",
            )
            return

        await transition(
            job,
            JobState.DONE,
            "Stream is ready in library",
            metadata={"acquisition_mode": "stream", "imported_path": strm_path},
        )
        await clear_rdt_ready(str(job.id))
        return

    # ------------------------------------------------------------------
    # 4b. DOWNLOAD MODE — Sonarr/Radarr handle import automatically
    #    We verify the file landed in the user's library
    # ------------------------------------------------------------------
    await transition(job, JobState.IMPORTING, "Verifying import")

    try:
        imported_path = await _verify_import(job, user)
        if imported_path:
            await update_job_field(job, imported_path=imported_path)

            # Track storage
            try:
                p = Path(imported_path)
                if p.exists():
                    size_gb = p.stat().st_size / (1024 ** 3)
                    await update_storage_used(job.user_id, size_gb)
            except Exception:
                logger.exception("Failed to update storage tracking")
    except Exception as exc:
        logger.warning("Import verification issue (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # 5. VERIFYING — QC via ffprobe
    # ------------------------------------------------------------------
    try:
        await enqueue_qc(str(job.id))
        logger.info("Enqueued QC job for %s", job.id)
    except Exception:
        logger.exception("Failed to enqueue QC job for %s", job.id)

    await transition(
        job, JobState.VERIFYING,
        f"File imported, running QC validation",
    )
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
            logger.info("Series already in Sonarr (id=%d), triggering search", series_id)
            if job.season is not None:
                await sonarr.search_season(series_id, job.season)
            else:
                await sonarr.search_series(series_id)
            return series_id

        # Lookup series metadata for add
        results = await sonarr.lookup_series(f"tvdb:{tvdb_id}")
        if not results:
            raise ValueError(f"Sonarr lookup failed for tvdb:{tvdb_id}")
        lookup = results[0]

        # Determine monitor type
        if job.season is not None and job.episode is not None:
            monitor = "none"  # We'll search for the specific episode after adding
        elif job.season is not None:
            monitor = "none"  # We'll search for the specific season
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

        # If specific season/episode requested, trigger targeted search
        if job.season is not None and job.episode is not None:
            # Find the episode ID
            episodes = await sonarr.get_episodes(series_id, job.season)
            target_ep = next(
                (e for e in episodes if e.get("episodeNumber") == job.episode),
                None,
            )
            if target_ep:
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


async def _monitor_radarr_download(job: Job) -> None:
    """Poll Radarr queue until the movie is downloaded and imported."""
    movie_id = job.radarr_movie_id
    if not movie_id:
        raise ValueError("No radarr_movie_id set on job")

    elapsed = 0

    async with RadarrClient() as radarr:
        # Phase 1: Wait for Arr to grab a release
        logger.info("Waiting for Radarr to grab a release for movie %d", movie_id)
        grab_timeout = (
            ARR_GRAB_TIMEOUT_STREAM
            if job.acquisition_mode == "stream"
            else ARR_GRAB_TIMEOUT_DOWNLOAD
        )
        grab_waited = 0
        queue_item = None
        while grab_waited < grab_timeout:
            if await _is_rdt_ready(job):
                logger.info("RDT completion signal received before Radarr queue grab")
                return

            queue = await radarr.get_queue()
            queue_item = _find_queue_item(queue, "movieId", movie_id)
            if queue_item:
                await _capture_queue_correlation(job, queue_item)
                logger.info("Radarr grabbed release: %s", queue_item.get("title", "unknown"))
                if job.acquisition_mode == "stream":
                    logger.info("Stream mode: proceeding after Arr grab for job %s", job.id)
                    return
                break

            # Check if already completed (e.g. instant RD cache hit)
            movie = await radarr.get_movie(movie_id)
            if movie.get("hasFile"):
                logger.info("Movie already has file — instant completion")
                return

            await asyncio.sleep(10)
            grab_waited += 10

        if not queue_item:
            if job.acquisition_mode == "stream":
                logger.info(
                    "Stream mode: no Arr grab within %ss; proceeding with Zurg source lookup for job %s",
                    grab_timeout,
                    job.id,
                )
                return
            raise TimeoutError(f"Radarr did not grab a release within {grab_timeout}s")

        # Phase 2: Monitor download progress
        await _poll_queue_until_done(radarr, "movieId", movie_id, job)

        # Phase 3: Wait for import
        await _wait_for_import_radarr(radarr, movie_id)


async def _monitor_sonarr_download(job: Job) -> None:
    """Poll Sonarr queue until the episode(s) are downloaded and imported."""
    series_id = job.sonarr_series_id
    if not series_id:
        raise ValueError("No sonarr_series_id set on job")

    async with SonarrClient() as sonarr:
        # Phase 1: Wait for grab
        logger.info("Waiting for Sonarr to grab a release for series %d", series_id)
        grab_timeout = (
            ARR_GRAB_TIMEOUT_STREAM
            if job.acquisition_mode == "stream"
            else ARR_GRAB_TIMEOUT_DOWNLOAD
        )
        grab_waited = 0
        queue_item = None
        while grab_waited < grab_timeout:
            if await _is_rdt_ready(job):
                logger.info("RDT completion signal received before Sonarr queue grab")
                return

            queue = await sonarr.get_queue()
            queue_item = _find_queue_item(queue, "seriesId", series_id)
            if queue_item:
                await _capture_queue_correlation(job, queue_item)
                logger.info("Sonarr grabbed release: %s", queue_item.get("title", "unknown"))
                if job.acquisition_mode == "stream":
                    logger.info("Stream mode: proceeding after Arr grab for job %s", job.id)
                    return
                break

            # Check if specific episode already has file
            if job.season is not None and job.episode is not None:
                episodes = await sonarr.get_episodes(series_id, job.season)
                target = next(
                    (e for e in episodes if e.get("episodeNumber") == job.episode),
                    None,
                )
                if target and target.get("hasFile"):
                    logger.info("Episode already has file — instant completion")
                    return

            await asyncio.sleep(10)
            grab_waited += 10

        if not queue_item:
            if job.acquisition_mode == "stream":
                logger.info(
                    "Stream mode: no Arr grab within %ss; proceeding with Zurg source lookup for job %s",
                    grab_timeout,
                    job.id,
                )
                return
            raise TimeoutError(f"Sonarr did not grab a release within {grab_timeout}s")

        # Phase 2: Monitor download progress
        await _poll_queue_until_done(sonarr, "seriesId", series_id, job)

        # Phase 3: Wait for import
        await _wait_for_import_sonarr(sonarr, job)


def _find_queue_item(queue_response: dict, id_field: str, id_value: int) -> dict | None:
    """Find a queue item matching the given Arr entity ID."""
    for record in queue_response.get("records", []):
        if record.get(id_field) == id_value:
            return record
    return None


async def _capture_queue_correlation(job: Job, queue_item: dict) -> None:
    """Persist Arr queue id + download id/hash for webhook correlation."""
    arr_queue_id = queue_item.get("id")
    download_id = (
        queue_item.get("downloadId")
        or queue_item.get("downloadClientId")
        or queue_item.get("downloadClientInfo", {}).get("downloadId")
    )

    updates: dict[str, Any] = {}
    if arr_queue_id:
        updates["arr_queue_id"] = arr_queue_id
    if isinstance(download_id, str) and download_id.strip():
        updates["rd_torrent_id"] = download_id.strip()

    if updates:
        await update_job_field(job, **updates)


async def _is_rdt_ready(job: Job) -> bool:
    """Return True if rdt completion signal exists for this job."""
    return bool(await get_rdt_ready(str(job.id)))


async def _poll_queue_until_done(
    arr_client: RadarrClient | SonarrClient,
    id_field: str,
    id_value: int,
    job: Job,
) -> None:
    """Poll the Arr queue until the item disappears (completed) or fails."""
    elapsed = 0
    stall_count = 0
    last_size_left = None

    while elapsed < DOWNLOAD_TIMEOUT:
        if await _is_rdt_ready(job):
            logger.info("RDT completion signal received for job %s", job.id)
            return

        await asyncio.sleep(DOWNLOAD_POLL_INTERVAL)
        elapsed += DOWNLOAD_POLL_INTERVAL

        queue = await arr_client.get_queue()
        item = _find_queue_item(queue, id_field, id_value)

        if item is None:
            # Item left the queue — download complete + import started
            logger.info("Download complete (item left queue after %ds)", elapsed)
            return

        # Check for failure
        status = item.get("trackedDownloadStatus", "")
        state = item.get("trackedDownloadState", "")

        if state == "importBlocked":
            # Import is pending — download itself is done
            logger.info("Download done, import pending (will be handled by Arr)")
            return

        if status == "warning":
            msgs = item.get("statusMessages", [])
            warning_text = "; ".join(
                m.get("title", "") for m in msgs if isinstance(m, dict)
            )
            logger.warning("Download warning: %s", warning_text)

        if state == "failed":
            error_msg = "; ".join(
                m.get("title", "") for m in item.get("statusMessages", [])
                if isinstance(m, dict)
            )
            raise RuntimeError(f"Download failed in Arr: {error_msg or 'unknown error'}")

        await _capture_queue_correlation(job, item)

        # Calculate and report progress
        size_total = item.get("size", 0)
        size_left = item.get("sizeleft", 0)
        if size_total > 0:
            pct = int((1 - size_left / size_total) * 100)
            dl_client = item.get("downloadClient", "unknown")
            title = item.get("title", "")[:60]
            time_left = item.get("timeleft", "")

            await set_download_progress(
                str(job.id), pct,
                f"Downloading via {dl_client}: {title} ({time_left} remaining)"
            )

            # Stall detection
            if last_size_left is not None and size_left == last_size_left:
                stall_count += 1
                if stall_count >= 20:  # 20 * 15s = 5 minutes stalled
                    raise TimeoutError(
                        f"Download stalled at {pct}% for {stall_count * DOWNLOAD_POLL_INTERVAL}s"
                    )
            else:
                stall_count = 0
            last_size_left = size_left

    raise TimeoutError(f"Download did not complete within {DOWNLOAD_TIMEOUT}s")


async def _wait_for_import_radarr(radarr: RadarrClient, movie_id: int) -> None:
    """Wait for Radarr to finish importing the downloaded file."""
    elapsed = 0
    while elapsed < IMPORT_TIMEOUT:
        movie = await radarr.get_movie(movie_id)
        if movie.get("hasFile"):
            logger.info("Radarr import confirmed — movie has file")
            return
        await asyncio.sleep(10)
        elapsed += 10

    logger.warning("Import not confirmed within %ds — proceeding anyway", IMPORT_TIMEOUT)


async def _wait_for_import_sonarr(sonarr: SonarrClient, job: Job) -> None:
    """Wait for Sonarr to finish importing the downloaded episode(s)."""
    if job.season is None:
        # Full series request — just give Sonarr time
        await asyncio.sleep(30)
        return

    elapsed = 0
    while elapsed < IMPORT_TIMEOUT:
        episodes = await sonarr.get_episodes(job.sonarr_series_id, job.season)
        if job.episode is not None:
            target = next(
                (e for e in episodes if e.get("episodeNumber") == job.episode),
                None,
            )
            if target and target.get("hasFile"):
                logger.info("Sonarr import confirmed — episode has file")
                return
        else:
            # Season request: check if any episode now has a file
            if any(e.get("hasFile") for e in episodes):
                logger.info("Sonarr import confirmed — season has files")
                return
        await asyncio.sleep(10)
        elapsed += 10

    logger.warning("Sonarr import not confirmed within %ds — proceeding anyway", IMPORT_TIMEOUT)


# ===========================================================================
# Stream-mode helpers (.strm + Zurg)
# ===========================================================================


def _sanitize_name(value: str) -> str:
    """Return a filesystem-safe title."""
    value = re.sub(r"[\\/:*?\"<>|]+", "", value).strip()
    return value or "Unknown"


def _build_stream_url(source_path: Path, zurg_mount: Path, zurg_base_url: str) -> str:
    """Build the URL written into the .strm file."""
    if zurg_base_url:
        rel = source_path.relative_to(zurg_mount).as_posix()
        base = zurg_base_url.rstrip("/")
        return f"{base}/{quote(rel)}"
    return source_path.resolve().as_uri()


def _pick_zurg_source(
    *,
    zurg_mount: Path,
    canonical_title: str,
    year: int,
    media_type: str,
    season: int | None,
    episode: int | None,
) -> Path:
    """Find a best-effort video file in the Zurg mount."""
    if not zurg_mount.exists():
        raise FileNotFoundError(f"Zurg mount not found at {zurg_mount}")

    video_exts = {".mkv", ".mp4", ".m4v", ".avi", ".ts"}
    title_tokens = [t for t in re.split(r"[^a-z0-9]+", canonical_title.lower()) if t]
    season_token = f"s{season:02d}" if season is not None else ""
    episode_token = f"e{episode:02d}" if episode is not None else ""
    year_token = str(year) if year else ""

    best: Path | None = None
    best_score = -1
    for path in zurg_mount.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in video_exts:
            continue

        name = path.name.lower()
        hay = f"{path.parent.name.lower()} {name}"
        score = 0

        if all(tok in hay for tok in title_tokens[:3]):
            score += 5
        for tok in title_tokens:
            if tok in hay:
                score += 1
        if year_token and year_token in hay:
            score += 3
        if media_type == "tv" and season_token and season_token in hay:
            score += 4
        if media_type == "tv" and episode_token and episode_token in hay:
            score += 5

        if score > best_score:
            best = path
            best_score = score

    if best is None or best_score < 3:
        raise FileNotFoundError(
            f"No matching stream source found in Zurg mount for {canonical_title}"
        )
    return best


async def _materialize_stream_pointer(
    *,
    job: Job,
    user: User,
    canonical_title: str,
    year: int,
) -> tuple[str, str]:
    """Create a .strm file in the user's library and return (strm_path, target_url)."""
    config = get_config()
    if not config.zurg_enabled:
        raise RuntimeError("ZURG_ENABLED=false; enable Zurg streaming first")

    zurg_mount = Path(config.zurg_mount_path)
    source_path: Path | None = None
    waited = 0
    while waited <= STREAM_SOURCE_TIMEOUT:
        try:
            source_path = _pick_zurg_source(
                zurg_mount=zurg_mount,
                canonical_title=canonical_title,
                year=year,
                media_type=job.media_type,
                season=job.season,
                episode=job.episode,
            )
            break
        except FileNotFoundError:
            if waited >= STREAM_SOURCE_TIMEOUT:
                raise
            await asyncio.sleep(STREAM_SOURCE_POLL_INTERVAL)
            waited += STREAM_SOURCE_POLL_INTERVAL

    if source_path is None:
        raise FileNotFoundError(
            f"No matching stream source found in Zurg mount for {canonical_title}"
        )
    target_url = _build_stream_url(source_path, zurg_mount, config.zurg_base_url)

    user_root = Path(config.media_path) / "users" / str(user.id)
    safe_title = _sanitize_name(canonical_title)

    if job.media_type == "movie":
        folder = user_root / "Movies" / f"{safe_title} ({year})"
        strm_file = folder / f"{safe_title} ({year}).strm"
    else:
        season_num = job.season or 1
        episode_num = job.episode or 1
        folder = user_root / "TV" / safe_title / f"Season {season_num:02d}"
        strm_file = folder / f"{safe_title} - S{season_num:02d}E{episode_num:02d}.strm"

    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o777)
    except Exception:
        logger.debug("Could not chmod stream folder %s", folder, exc_info=True)
    strm_file.write_text(f"{target_url}\n", encoding="utf-8")
    try:
        strm_file.chmod(0o666)
    except Exception:
        logger.debug("Could not chmod stream file %s", strm_file, exc_info=True)
    logger.info("Created stream pointer for job %s: %s -> %s", job.id, strm_file, source_path)
    return str(strm_file), target_url


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


# ===========================================================================
# Import verification
# ===========================================================================


async def _verify_import(job: Job, user: User) -> str | None:
    """Check that the file landed in the user's library. Returns the path."""
    config = get_config()
    user_media = Path(config.media_path) / "users" / str(user.id)

    if job.media_type == "movie":
        # Ask Radarr for the file path
        if job.radarr_movie_id:
            try:
                async with RadarrClient() as radarr:
                    movie = await radarr.get_movie(job.radarr_movie_id)
                    movie_file = movie.get("movieFile", {})
                    if movie_file:
                        return movie_file.get("path")
            except Exception:
                logger.exception("Failed to get movie file path from Radarr")
    else:
        # Ask Sonarr for episode file
        if job.sonarr_series_id:
            try:
                async with SonarrClient() as sonarr:
                    if job.season is not None and job.episode is not None:
                        episodes = await sonarr.get_episodes(job.sonarr_series_id, job.season)
                        target = next(
                            (e for e in episodes if e.get("episodeNumber") == job.episode),
                            None,
                        )
                        if target and target.get("episodeFile"):
                            return target["episodeFile"].get("path")
            except Exception:
                logger.exception("Failed to get episode file path from Sonarr")

    # Fallback: scan user's media directory
    media_type_dir = "Movies" if job.media_type == "movie" else "TV"
    search_dir = user_media / media_type_dir
    if search_dir.exists():
        video_exts = {".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".ts"}
        for f in sorted(search_dir.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file() and f.suffix.lower() in video_exts:
                return str(f)

    return None
