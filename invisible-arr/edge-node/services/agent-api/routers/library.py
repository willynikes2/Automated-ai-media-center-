"""User library endpoint — scans per-user media directory on disk."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update

from dependencies import get_current_user
from shared.config import get_config
from shared.database import get_session_factory
from shared.jellyfin_client import JellyfinAdmin
from shared.models import Job, JobState, User
from shared.radarr_client import RadarrClient
from shared.sonarr_client import SonarrClient

logger = logging.getLogger("agent-api.library")
router = APIRouter()

VIDEO_EXTENSIONS = frozenset({".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".ts", ".strm"})


class LibraryItem(BaseModel):
    """A single media item in the user's library."""

    title: str
    year: int | None = None
    media_type: str  # "movie" or "tv"
    file_path: str
    file_name: str
    size_bytes: int
    folder: str  # e.g. "The Matrix (1999)" or "Breaking Bad/Season 01"


class LibraryResponse(BaseModel):
    items: list[LibraryItem]
    total: int
    movies_count: int
    tv_count: int


def _parse_movie_folder(folder_name: str) -> tuple[str, int | None]:
    """Extract title and year from a folder like 'The Matrix (1999)'."""
    import re

    match = re.match(r"^(.+?)\s*\((\d{4})\)$", folder_name)
    if match:
        return match.group(1).strip(), int(match.group(2))
    return folder_name, None


def _scan_movies(user_movies: Path) -> list[LibraryItem]:
    """Scan Movies/ directory for video files."""
    items: list[LibraryItem] = []
    if not user_movies.exists():
        return items

    for movie_dir in sorted(user_movies.iterdir()):
        if not movie_dir.is_dir():
            continue
        title, year = _parse_movie_folder(movie_dir.name)

        for f in movie_dir.iterdir():
            if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
                try:
                    size = f.stat().st_size
                except OSError:
                    size = 0
                items.append(
                    LibraryItem(
                        title=title,
                        year=year,
                        media_type="movie",
                        file_path=str(f),
                        file_name=f.name,
                        size_bytes=size,
                        folder=movie_dir.name,
                    )
                )
    return items


def _scan_tv(user_tv: Path) -> list[LibraryItem]:
    """Scan TV/ directory for video files."""
    items: list[LibraryItem] = []
    if not user_tv.exists():
        return items

    for show_dir in sorted(user_tv.iterdir()):
        if not show_dir.is_dir():
            continue
        show_name = show_dir.name

        for season_dir in sorted(show_dir.iterdir()):
            if not season_dir.is_dir():
                continue

            for f in season_dir.iterdir():
                if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
                    try:
                        size = f.stat().st_size
                    except OSError:
                        size = 0
                    items.append(
                        LibraryItem(
                            title=show_name,
                            year=None,
                            media_type="tv",
                            file_path=str(f),
                            file_name=f.name,
                            size_bytes=size,
                            folder=f"{show_name}/{season_dir.name}",
                        )
                    )
    return items


@router.get("/library", response_model=LibraryResponse)
async def get_library(
    media_type: str | None = Query(
        default=None, description="Filter: 'movie' or 'tv'"
    ),
    user: User = Depends(get_current_user),
) -> LibraryResponse:
    """Return the authenticated user's media library from disk."""
    config = get_config()
    user_media = Path(config.media_path) / "users" / str(user.id)

    movies = _scan_movies(user_media / "Movies")
    tv = _scan_tv(user_media / "TV")

    if media_type == "movie":
        items = movies
    elif media_type == "tv":
        items = tv
    else:
        items = movies + tv

    return LibraryResponse(
        items=items,
        total=len(movies) + len(tv),
        movies_count=len(movies),
        tv_count=len(tv),
    )


class DeleteRequest(BaseModel):
    file_path: str
    media_type: str  # "movie" or "tv"
    delete_scope: str = "file"  # "file", "season", "series"


class DeleteResponse(BaseModel):
    freed_bytes: int
    deleted_files: int


def _safe_delete_path(target: Path, user_media: Path) -> int:
    """Delete a file or directory, return bytes freed. Validates path is under user_media."""
    resolved = target.resolve()
    if not str(resolved).startswith(str(user_media.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    if not resolved.exists():
        return 0

    freed = 0
    if resolved.is_file():
        freed = resolved.stat().st_size
        resolved.unlink()
    elif resolved.is_dir():
        for f in resolved.rglob("*"):
            if f.is_file():
                freed += f.stat().st_size
        shutil.rmtree(resolved)

    # Clean up empty parent directories up to user_media
    parent = resolved.parent if resolved.is_file() else resolved
    while parent != user_media.resolve() and parent.exists():
        try:
            if not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
            else:
                break
        except OSError:
            break

    return freed


@router.delete("/library/item", response_model=DeleteResponse)
async def delete_library_item(
    req: DeleteRequest,
    user: User = Depends(get_current_user),
) -> DeleteResponse:
    """Delete media from disk, clean up Arr services, refresh Jellyfin, update storage."""
    config = get_config()
    user_media = Path(config.media_path) / "users" / str(user.id)

    # Validate the file_path is under user's media directory
    target = Path(req.file_path).resolve()
    if not str(target).startswith(str(user_media.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Determine what to delete based on scope
    freed = 0
    deleted_files = 0

    if req.media_type == "movie":
        # Delete the movie folder (parent of the file)
        movie_folder = target.parent if target.is_file() else target
        for f in movie_folder.rglob("*"):
            if f.is_file():
                deleted_files += 1
        freed = _safe_delete_path(movie_folder, user_media)

        # Clean up Radarr
        try:
            async with get_session_factory()() as session:
                result = await session.execute(
                    select(Job).where(
                        Job.user_id == user.id,
                        Job.media_type == "movie",
                        Job.imported_path.ilike(f"%{movie_folder.name}%"),
                        Job.state == JobState.DONE,
                    )
                )
                jobs = result.scalars().all()
                for job in jobs:
                    if job.radarr_movie_id:
                        try:
                            async with RadarrClient() as radarr:
                                await radarr.delete_movie(job.radarr_movie_id, delete_files=True)
                        except Exception as e:
                            logger.warning("Failed to delete from Radarr: %s", e)
                    job.state = JobState.DELETED
                await session.commit()
        except Exception as e:
            logger.warning("Failed to clean up Radarr/jobs: %s", e)

    elif req.media_type == "tv":
        if req.delete_scope == "series":
            # Delete entire show folder
            show_folder = target
            # Walk up to find the show folder (direct child of TV/)
            tv_root = user_media / "TV"
            while show_folder.parent != tv_root and show_folder != tv_root:
                show_folder = show_folder.parent
            for f in show_folder.rglob("*"):
                if f.is_file():
                    deleted_files += 1
            freed = _safe_delete_path(show_folder, user_media)

            # Clean up Sonarr - delete entire series
            try:
                async with get_session_factory()() as session:
                    result = await session.execute(
                        select(Job).where(
                            Job.user_id == user.id,
                            Job.media_type == "tv",
                            Job.imported_path.ilike(f"%{show_folder.name}%"),
                            Job.state == JobState.DONE,
                        )
                    )
                    jobs = result.scalars().all()
                    series_id = None
                    for job in jobs:
                        if job.sonarr_series_id:
                            series_id = job.sonarr_series_id
                        job.state = JobState.DELETED
                    if series_id:
                        try:
                            async with SonarrClient() as sonarr:
                                await sonarr.delete_series(series_id, delete_files=True)
                        except Exception as e:
                            logger.warning("Failed to delete from Sonarr: %s", e)
                    await session.commit()
            except Exception as e:
                logger.warning("Failed to clean up Sonarr/jobs: %s", e)

        elif req.delete_scope == "season":
            # Delete season folder
            season_folder = target if target.is_dir() else target.parent
            for f in season_folder.rglob("*"):
                if f.is_file():
                    deleted_files += 1
            freed = _safe_delete_path(season_folder, user_media)

            # Mark matching jobs as DELETED
            try:
                async with get_session_factory()() as session:
                    result = await session.execute(
                        select(Job).where(
                            Job.user_id == user.id,
                            Job.media_type == "tv",
                            Job.imported_path.ilike(f"%{season_folder.name}%"),
                            Job.state == JobState.DONE,
                        )
                    )
                    for job in result.scalars().all():
                        job.state = JobState.DELETED
                    await session.commit()
            except Exception as e:
                logger.warning("Failed to update jobs: %s", e)

        else:
            # Delete single file
            if target.is_file():
                deleted_files = 1
                freed = _safe_delete_path(target, user_media)

            # Mark matching job as DELETED
            try:
                async with get_session_factory()() as session:
                    result = await session.execute(
                        select(Job).where(
                            Job.user_id == user.id,
                            Job.media_type == "tv",
                            Job.imported_path == str(target),
                            Job.state == JobState.DONE,
                        )
                    )
                    for job in result.scalars().all():
                        job.state = JobState.DELETED
                    await session.commit()
            except Exception as e:
                logger.warning("Failed to update jobs: %s", e)

    # Update user storage
    if freed > 0:
        freed_gb = freed / (1024 ** 3)
        try:
            async with get_session_factory()() as session:
                await session.execute(
                    update(User)
                    .where(User.id == user.id)
                    .values(storage_used_gb=User.storage_used_gb - freed_gb)
                )
                await session.commit()
        except Exception as e:
            logger.warning("Failed to update storage: %s", e)

    # Refresh Jellyfin library
    try:
        jf = JellyfinAdmin()
        if jf.enabled:
            await jf.refresh_library()
    except Exception as e:
        logger.warning("Failed to refresh Jellyfin: %s", e)

    return DeleteResponse(freed_bytes=freed, deleted_files=deleted_files)
