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
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import sentry_sdk
from sqlalchemy import select, update as sa_update

from shared.config import get_config
from shared.database import get_session_factory
from shared.models import Job, JobEvent, JobState, User
from shared.tiers import get_tier_limits
from shared.radarr_client import RadarrClient
from shared.redis_client import (
    clear_download_progress,
    clear_rdt_ready,
    enqueue_qc,
    set_download_progress,
)
from shared.media_utils import (
    check_content_registry,
    hardlink_media,
    register_content,
    trigger_jellyfin_refresh,
)
from shared.canonical import (
    add_user_content,
    check_canonical,
    check_inflight_download,
    check_item_quota,
    create_user_symlink,
    increment_user_count,
    register_canonical,
)
from shared.sonarr_client import SonarrClient
from shared.tmdb_client import TMDBClient

logger = logging.getLogger("agent-worker.worker")

# Quality profile names — resolved to IDs dynamically at first use
RADARR_STANDARD_PROFILE_NAME = os.environ.get("RADARR_PROFILE_NAME", "HD Bluray + WEB")
RADARR_THEATER_PROFILE_NAME = os.environ.get("RADARR_THEATER_PROFILE_NAME", "Theater Releases")
SONARR_PROFILE_NAME = os.environ.get("SONARR_PROFILE_NAME", "WEB-1080p")

# Cached profile IDs (resolved on first use)
_profile_cache: dict[str, int] = {}

# Search timeout: if no grab after this many seconds, mark FAILED
SEARCH_TIMEOUT = int(os.environ.get("SEARCH_TIMEOUT", "1800"))  # 30 minutes

# Minimum free disk space (GB) -- reject new jobs below this threshold
MIN_FREE_DISK_GB = float(os.environ.get("MIN_FREE_DISK_GB", "10.0"))

# Canonical library root folder paths (shared across all users)
CANONICAL_MOVIES_ROOT = "/data/media/library/Movies"
CANONICAL_TV_ROOT = "/data/media/library/TV"


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

    # Track per-user completions for terminal states
    if new_state in (JobState.AVAILABLE, JobState.FAILED):
        try:
            from shared.metrics import USER_JOB_COMPLETIONS
            user = await get_user(job.user_id)
            USER_JOB_COMPLETIONS.labels(
                user_email=user.email or str(job.user_id),
                final_state=new_state.value,
                media_type=job.media_type,
            ).inc()
        except Exception:
            logger.debug("Could not record user job completion metric for job %s", job.id)


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


async def _measure_user_storage(user_id: uuid.UUID, config: Any) -> float:
    """Measure actual disk usage for a user in GB (blocking I/O in thread)."""
    user_root = Path(config.media_path) / "users" / str(user_id)
    if not user_root.exists():
        return 0.0

    def _du() -> float:
        total = 0
        for path in user_root.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
        return total / (1024 ** 3)

    return await asyncio.to_thread(_du)


async def _check_quota_before_download(
    user: User, config: Any, current_job: Job | None = None,
) -> None:
    """Check user storage quota and system disk space before adding to Arr.

    Raises ValueError with a descriptive message if the quota is exceeded
    or disk space is critically low.
    """
    # 1. System disk space check -- never let disk go below MIN_FREE_DISK_GB
    try:
        stat = os.statvfs(config.media_path)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        if free_gb < MIN_FREE_DISK_GB:
            raise ValueError(
                f"System disk space critically low ({free_gb:.1f}GB free, "
                f"minimum {MIN_FREE_DISK_GB:.0f}GB required). "
                f"Cannot accept new downloads."
            )
    except OSError:
        logger.warning("Could not check disk space at %s", config.media_path)

    # 2. User quota check (skip for unlimited users)
    if user.storage_quota_gb == -1:
        return

    # Measure actual disk usage (more reliable than DB counter)
    actual_gb = await _measure_user_storage(user.id, config)

    # Sync DB value with reality
    if abs(actual_gb - user.storage_used_gb) > 0.1:
        await update_storage_used_absolute(user.id, actual_gb)
        logger.info(
            "Synced storage for user %s: DB had %.1fGB, actual %.1fGB",
            user.name, user.storage_used_gb, actual_gb,
        )

    if actual_gb >= user.storage_quota_gb:
        raise ValueError(
            f"Storage quota exceeded: using {actual_gb:.1f}GB "
            f"of {user.storage_quota_gb:.0f}GB. "
            f"Delete content or upgrade your plan."
        )

    # 3. Account for in-flight jobs (SEARCHING/DOWNLOADING) that will consume space
    exclude_id = current_job.id if current_job else None
    in_flight_gb = await _estimate_inflight_storage(user, exclude_job_id=exclude_id)
    projected_gb = actual_gb + in_flight_gb

    if projected_gb >= user.storage_quota_gb:
        raise ValueError(
            f"Storage quota would be exceeded: using {actual_gb:.1f}GB "
            f"+ ~{in_flight_gb:.1f}GB in-flight downloads = "
            f"~{projected_gb:.1f}GB of {user.storage_quota_gb:.0f}GB quota. "
            f"Wait for current downloads to finish or delete content."
        )

    logger.info(
        "Quota check passed for %s: %.1f/%.0f GB used (%.1fGB in-flight)",
        user.name, actual_gb, user.storage_quota_gb, in_flight_gb,
    )


async def _estimate_inflight_storage(
    user: User, exclude_job_id: uuid.UUID | None = None,
) -> float:
    """Estimate storage that in-flight jobs will consume when they complete.

    Counts active SEARCHING/DOWNLOADING jobs for this user and estimates
    their size based on tier limits (max_movie_size_gb, max_episode_size_gb).
    Excludes the current job (already in SEARCHING) to avoid double-counting.
    """
    active_states = [JobState.SEARCHING.value, JobState.DOWNLOADING.value]
    factory = get_session_factory()
    async with factory() as session:
        query = select(Job.media_type).where(
            Job.user_id == user.id,
            Job.state.in_(active_states),
        )
        if exclude_job_id:
            query = query.where(Job.id != exclude_job_id)
        result = await session.execute(query)
        active_jobs = list(result.scalars().all())

    if not active_jobs:
        return 0.0

    limits = get_tier_limits(user.tier)
    max_movie = limits.get("max_movie_size_gb", 3.0)
    max_episode = limits.get("max_episode_size_gb", 1.0)

    total = 0.0
    for media_type in active_jobs:
        total += max_movie if media_type == "movie" else max_episode

    return total


async def update_storage_used_absolute(user_id: uuid.UUID, gb: float) -> None:
    """Set the user's storage_used_gb to an absolute value."""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            sa_update(User)
            .where(User.id == user_id)
            .values(storage_used_gb=gb)
        )
        await session.commit()


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


async def _resolve_radarr_profile(name: str) -> int:
    """Resolve a Radarr quality profile name to its ID (cached)."""
    cache_key = f"radarr:{name}"
    if cache_key in _profile_cache:
        return _profile_cache[cache_key]
    async with RadarrClient() as client:
        profiles = await client.get_quality_profiles()
        for p in profiles:
            _profile_cache[f"radarr:{p['name']}"] = p["id"]
    if cache_key not in _profile_cache:
        raise ValueError(f"Radarr quality profile '{name}' not found. Available: {[p['name'] for p in profiles]}")
    return _profile_cache[cache_key]


async def _resolve_sonarr_profile(name: str) -> int:
    """Resolve a Sonarr quality profile name to its ID (cached)."""
    cache_key = f"sonarr:{name}"
    if cache_key in _profile_cache:
        return _profile_cache[cache_key]
    async with SonarrClient() as client:
        profiles = await client.get_quality_profiles()
        for p in profiles:
            _profile_cache[f"sonarr:{p['name']}"] = p["id"]
    if cache_key not in _profile_cache:
        raise ValueError(f"Sonarr quality profile '{name}' not found. Available: {[p['name'] for p in profiles]}")
    return _profile_cache[cache_key]


class ContentNotReleasedError(Exception):
    """Raised when content is not yet available (announced/unaired TV)."""

    def __init__(self, message: str, monitor_reason: str = ""):
        super().__init__(message)
        self.monitor_reason = monitor_reason or message


# ===========================================================================
# Content registry shortcut
# ===========================================================================


async def _try_fulfill_from_registry(
    job: Job,
    user: User,
    tmdb_id: int,
    title: str,
    config: Any,
) -> bool:
    """Legacy content registry check (hardlink). Kept as fallback.

    Returns True if the job was fulfilled (caller should return early).
    """
    factory = get_session_factory()
    async with factory() as session:
        entry = await check_content_registry(
            session, tmdb_id, job.media_type,
            season=job.season, episode=job.episode,
        )
        if entry is None:
            return False

        source_path = entry.file_path
        source_parent = os.path.dirname(source_path)
        source_folder_name = os.path.basename(source_parent)

        if job.media_type == "movie":
            dest_dir = os.path.join(
                config.media_path, "users", str(user.id), "Movies", source_folder_name,
            )
        else:
            source_grandparent = os.path.dirname(source_parent)
            series_folder = os.path.basename(source_grandparent)
            if re.match(r"(?i)season\s+\d+", source_folder_name):
                dest_dir = os.path.join(
                    config.media_path, "users", str(user.id), "TV",
                    series_folder, source_folder_name,
                )
            else:
                dest_dir = os.path.join(
                    config.media_path, "users", str(user.id), "TV", source_folder_name,
                )

        dest_path = hardlink_media(source_path, dest_dir)
        logger.info(
            "Hardlinked from registry: %s -> %s for user %s",
            source_path, dest_path, user.name,
        )

    rel_path = os.path.basename(source_path)
    await update_job_field(job, imported_path=rel_path)
    await transition(
        job, JobState.AVAILABLE,
        f"Fulfilled from content registry (hardlink from existing download)",
        metadata={"source_path": source_path, "dest_path": dest_path},
    )
    await clear_download_progress(str(job.id))
    await trigger_jellyfin_refresh()
    return True


async def _try_fulfill_from_canonical(
    job: Job,
    user: User,
    tmdb_id: int,
    title: str,
    config: Any,
) -> bool:
    """Check canonical library and fulfill via symlink if content exists.

    Also adds content to Radarr/Sonarr for the user so Arr manages metadata/upgrades.
    Returns True if fulfilled (caller should return early).
    """
    factory = get_session_factory()
    async with factory() as session:
        canonical = await check_canonical(session, tmdb_id, job.media_type)
        if canonical is None:
            # Check if another job is already downloading this TMDB ID
            inflight = await check_inflight_download(session, tmdb_id, job.media_type)
            if inflight and inflight.id != job.id:
                # Let this job proceed — Radarr/Sonarr will see file already exists
                # and the webhook handler uses _fulfill_sibling_jobs to handle dedup
                logger.info(
                    "Job %s: inflight download for tmdb=%d (job %s), proceeding to Arr (dedup at Arr level)",
                    job.id, tmdb_id, inflight.id,
                )
            return False

        # Content exists in canonical library — fulfill via symlink
        # 1. Check item quota
        await check_item_quota(session, user, job.media_type)

        # 2. Create symlink from user's dir to canonical
        symlink_path = create_user_symlink(
            canonical.canonical_path, str(user.id), job.media_type,
        )

        # 3. Track in user_content
        await add_user_content(
            session, str(user.id), canonical,
            job_id=str(job.id), symlink_path=symlink_path,
        )

        # 4. Increment item count
        await increment_user_count(session, user.id, job.media_type)

        await session.commit()

    # 5. Update job and transition to AVAILABLE
    await update_job_field(job, imported_path=os.path.basename(canonical.canonical_path), tmdb_id=tmdb_id)
    await transition(
        job, JobState.AVAILABLE,
        f"Fulfilled from canonical library (symlink)",
        metadata={"canonical_path": canonical.canonical_path, "symlink_path": symlink_path},
    )
    await clear_download_progress(str(job.id))
    await trigger_jellyfin_refresh()

    # 6. Add to Radarr/Sonarr so Arr manages metadata and upgrades
    try:
        if job.media_type == "movie":
            await _add_to_radarr(job, user, tmdb_id, canonical.title or title)
        else:
            await _add_to_sonarr(job, user, tmdb_id, canonical.title or title)
    except Exception:
        # Non-fatal: content is already available, Arr registration is best-effort
        logger.warning("Could not register symlinked content in Arr for user %s", user.name, exc_info=True)

    logger.info(
        "Job %s fulfilled from canonical (symlink) for user %s: %s",
        job.id, user.name, canonical.canonical_path,
    )
    return True


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
    sentry_sdk.set_user({"id": str(user.id), "email": user.email})
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

        # ── Check canonical library: symlink if content already exists ──
        try:
            fulfilled = await _try_fulfill_from_canonical(
                job, user, tmdb_id, canonical_title, config,
            )
            if fulfilled:
                return
        except ValueError as exc:
            # Item quota exceeded
            await transition(job, JobState.FAILED, str(exc))
            return
        except Exception:
            logger.warning(
                "Canonical check failed for job %s, proceeding with normal flow",
                job.id, exc_info=True,
            )

        # ── Fallback: legacy content registry (hardlink) ──
        try:
            fulfilled = await _try_fulfill_from_registry(
                job, user, tmdb_id, canonical_title, config,
            )
            if fulfilled:
                return
        except Exception:
            logger.warning(
                "Content registry check failed for job %s, proceeding with normal flow",
                job.id, exc_info=True,
            )

        # ── Enforce quotas before adding to Arr ──
        # Downloads go to canonical library (shared), so per-user GB quota
        # is no longer relevant. Check item-count quota and system disk only.
        try:
            # System disk space check
            stat = os.statvfs(config.media_path)
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
            if free_gb < MIN_FREE_DISK_GB:
                raise ValueError(
                    f"System disk space critically low ({free_gb:.1f}GB free, "
                    f"minimum {MIN_FREE_DISK_GB:.0f}GB required). "
                    f"Cannot accept new downloads."
                )
        except OSError:
            logger.warning("Could not check disk space at %s", config.media_path)
        try:
            # Item-count quota check
            factory = get_session_factory()
            async with factory() as session:
                await check_item_quota(session, user, job.media_type)
        except ValueError as exc:
            await transition(job, JobState.FAILED, str(exc))
            return

        try:
            if job.media_type == "movie":
                arr_id = await _add_to_radarr(job, user, tmdb_id, canonical_title)
                # arr_id already saved inside _add_to_radarr before search trigger
            else:
                arr_id = await _add_to_sonarr(job, user, tmdb_id, canonical_title)
                # arr_id already saved inside _add_to_sonarr before search trigger
        except ContentNotReleasedError as exc:
            await transition(job, JobState.WAITING, exc.monitor_reason, metadata={"original_error": str(exc)})
            return
        except Exception as exc:
            await transition(job, JobState.FAILED, f"Failed to add to library: {exc}")
            return

        # Search triggered by _add_to_radarr/_add_to_sonarr.
        # Worker is done -- webhooks drive the rest.
        logger.info("Job %s: search triggered, worker exiting (webhooks drive the rest)", job.id)

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

    # Update storage tracking — sync from filesystem for accuracy
    try:
        config = get_config()
        actual_gb = await _measure_user_storage(job.user_id, config)
        await update_storage_used_absolute(job.user_id, actual_gb)
    except Exception:
        # Fallback to incremental update if measurement fails
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
    """Add a movie to Radarr. Returns the Radarr movie ID.

    Uses the 'Theater Releases' profile for in-cinema movies (allows CAM/TS/TC
    with auto-upgrade to HD when proper release comes out). Falls back to
    standard profile if theater profile doesn't exist.
    """
    # Use canonical root for new downloads (shared across users)
    # Radarr manages the canonical copy; users get symlinks
    preferred_root = CANONICAL_MOVIES_ROOT

    async with RadarrClient() as radarr:
        root_folder_path = await _ensure_radarr_root_folder(radarr, preferred_root)

        # Check if already in Radarr
        existing = await radarr.get_movie_by_tmdb(tmdb_id)
        if existing:
            movie_id = existing["id"]
            # Save Arr ID BEFORE triggering search (prevents webhook race)
            await update_job_field(job, radarr_movie_id=movie_id, acquisition_method="radarr")
            logger.info("Movie already in Radarr (id=%d), triggering search", movie_id)

            # If movie is in cinemas and on standard profile, switch to theater profile
            movie_status = existing.get("status", "")
            if movie_status == "inCinemas":
                try:
                    theater_id = await _resolve_radarr_profile(RADARR_THEATER_PROFILE_NAME)
                    if existing.get("qualityProfileId") != theater_id:
                        existing["qualityProfileId"] = theater_id
                        await radarr.update_movie(existing)
                        logger.info("Switched movie %d to Theater profile for in-cinema release", movie_id)
                except ValueError:
                    logger.debug("Theater profile not found, using existing profile")

            await radarr.search_movie(movie_id)
            return movie_id

        # Determine quality profile based on movie status
        # For in-cinema movies, use theater profile (allows CAM/TS/TC with upgrade)
        try:
            standard_profile_id = await _resolve_radarr_profile(RADARR_STANDARD_PROFILE_NAME)
        except ValueError:
            # Fallback to hardcoded ID 7 if name resolution fails
            standard_profile_id = 7
            logger.warning("Could not resolve profile '%s', falling back to ID 7", RADARR_STANDARD_PROFILE_NAME)

        quality_profile_id = standard_profile_id

        movie = await radarr.add_movie(
            tmdb_id=tmdb_id,
            title=title,
            root_folder_path=root_folder_path,
            quality_profile_id=quality_profile_id,
            search_for_movie=False,  # Don't search yet — save ID first
        )
        movie_id = movie["id"]

        # Save Arr ID BEFORE triggering search (prevents webhook race)
        await update_job_field(job, radarr_movie_id=movie_id, acquisition_method="radarr")

        # Check if in-cinema and switch to theater profile
        movie_status = movie.get("status", "")
        if movie_status == "inCinemas":
            try:
                theater_id = await _resolve_radarr_profile(RADARR_THEATER_PROFILE_NAME)
                movie["qualityProfileId"] = theater_id
                await radarr.update_movie(movie)
                logger.info("Using Theater profile for in-cinema movie: %s", title)
            except ValueError:
                logger.info("Theater profile not available, using standard for: %s", title)

        # Now trigger search
        await radarr.search_movie(movie_id)
        logger.info("Added movie to Radarr: %s (id=%d)", title, movie_id)
        return movie_id


async def _add_to_sonarr(
    job: Job, user: User, tmdb_id: int, title: str
) -> int:
    """Add a series to Sonarr. Returns the Sonarr series ID."""
    # Use canonical root for new downloads (shared across users)
    preferred_root = CANONICAL_TV_ROOT

    async with SonarrClient() as sonarr:
        root_folder_path = await _ensure_sonarr_root_folder(sonarr, preferred_root)

        # TMDB -> TVDB lookup (Sonarr uses TVDB)
        config = get_config()
        async with TMDBClient(config.tmdb_api_key) as tmdb:
            external_ids = await tmdb.get_external_ids(tmdb_id, "tv")
            tvdb_id = external_ids.get("tvdb_id")
            if not tvdb_id:
                raise ValueError(f"No TVDB ID found for TMDB {tmdb_id}")

        # Resolve quality profile dynamically
        try:
            sonarr_profile_id = await _resolve_sonarr_profile(SONARR_PROFILE_NAME)
        except ValueError:
            sonarr_profile_id = 7
            logger.warning("Could not resolve Sonarr profile '%s', falling back to ID 7", SONARR_PROFILE_NAME)

        # Check if already in Sonarr
        existing = await sonarr.get_series_by_tvdb(tvdb_id)
        if existing:
            series_id = existing["id"]
            # Save Arr ID BEFORE triggering search (prevents webhook race)
            await update_job_field(job, sonarr_series_id=series_id, acquisition_method="sonarr")
            logger.info("Series already in Sonarr (id=%d), ensuring monitored + triggering search", series_id)

            # Ensure series is monitored
            if not existing.get("monitored"):
                existing["monitored"] = True
                await sonarr.update_series(existing)
                logger.info("Enabled monitoring on series %d", series_id)

            # Ensure target season is monitored
            await _ensure_sonarr_monitored(sonarr, existing, job)

            # Check if content has aired — move to WAITING if not
            await _check_sonarr_aired(sonarr, series_id, job)

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
            quality_profile_id=sonarr_profile_id,
            monitor=monitor,
            search_for_missing=False,  # Don't search yet — save ID first
        )
        series_id = series["id"]
        # Save Arr ID BEFORE triggering search (prevents webhook race)
        await update_job_field(job, sonarr_series_id=series_id, acquisition_method="sonarr")
        logger.info("Added series to Sonarr: %s (id=%d)", title, series_id)

        # Ensure monitoring on target season/episodes so Sonarr will grab releases
        await _ensure_sonarr_monitored(sonarr, series, job)

        # Check if content has aired — move to WAITING if not
        await _check_sonarr_aired(sonarr, series_id, job)

        # Trigger search (was deferred so we could save ID first)
        if monitor == "all":
            await sonarr.search_series(series_id)
            return series_id

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
            # Monitor all episodes in the season before searching —
            # Sonarr ignores unmonitored episodes even if the season is monitored
            episodes = await sonarr.get_episodes(series_id, job.season)
            unmonitored = [e for e in episodes if not e.get("monitored")]
            for ep in unmonitored:
                ep["monitored"] = True
                await sonarr.update_episode(ep)
            if unmonitored:
                logger.info(
                    "Monitored %d episodes for S%02d before season search",
                    len(unmonitored), job.season,
                )
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


async def _check_sonarr_aired(sonarr: SonarrClient, series_id: int, job: Job) -> None:
    """Raise ContentNotReleasedError if no episodes have aired yet.

    Checks the specific season/episode requested, or the whole series if no
    season specified.  Uses Sonarr's airDateUtc on episodes.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    if job.season is not None:
        episodes = await sonarr.get_episodes(series_id, job.season)
    else:
        # No specific season — check all episodes
        episodes = await sonarr.get_episodes(series_id)

    if job.episode is not None:
        # Specific episode requested
        target = next((e for e in episodes if e.get("episodeNumber") == job.episode
                        and e.get("seasonNumber") == (job.season or 1)), None)
        if target:
            air = target.get("airDateUtc")
            if air:
                air_dt = datetime.fromisoformat(air.replace("Z", "+00:00"))
                if air_dt > now:
                    raise ContentNotReleasedError(
                        f"Episode S{job.season:02d}E{job.episode:02d} airs {air_dt.strftime('%Y-%m-%d')}",
                        monitor_reason=f"Episode has not aired yet (airs {air_dt.strftime('%Y-%m-%d')}). Monitoring.",
                    )
            else:
                # No air date at all — unannounced
                raise ContentNotReleasedError(
                    f"Episode S{job.season:02d}E{job.episode:02d} has no air date",
                    monitor_reason="Episode has no scheduled air date. Monitoring.",
                )
        return  # Episode not found in Sonarr data — let search proceed

    # Season or full series — check if ANY episode has aired
    aired_count = 0
    for ep in episodes:
        air = ep.get("airDateUtc")
        if air:
            air_dt = datetime.fromisoformat(air.replace("Z", "+00:00"))
            if air_dt <= now:
                aired_count += 1

    if aired_count == 0 and episodes:
        # Find the earliest air date to report
        earliest = None
        for ep in episodes:
            air = ep.get("airDateUtc")
            if air:
                dt = datetime.fromisoformat(air.replace("Z", "+00:00"))
                if earliest is None or dt < earliest:
                    earliest = dt

        date_str = earliest.strftime('%Y-%m-%d') if earliest else "TBA"
        raise ContentNotReleasedError(
            f"No episodes have aired yet (premieres {date_str})",
            monitor_reason=f"Show has not aired yet (premieres {date_str}). Monitoring.",
        )


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
    else:
        # Full series request — monitor ALL seasons
        for s in series.get("seasons", []):
            if not s.get("monitored"):
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
