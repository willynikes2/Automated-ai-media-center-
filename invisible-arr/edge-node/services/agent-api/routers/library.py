"""User library endpoint — scans per-user media directory on disk."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from dependencies import get_current_user
from shared.config import get_config
from shared.models import User

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
