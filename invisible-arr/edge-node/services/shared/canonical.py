"""Canonical library operations — shared content with per-user symlink views."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_config
from shared.models import (
    CanonicalContent,
    Job,
    JobState,
    User,
    UserContent,
)

logger = logging.getLogger("shared.canonical")

_QUALITY_RE = re.compile(
    r"(WEBDL|WEB-DL|WEBRip|BluRay|Bluray|BDRip|HDRip|HDTV|DVDRip|CAM|TS|TC|TELESYNC)"
    r"[.\-_ ]*(\d{3,4}p)?",
    re.IGNORECASE,
)
_CODEC_RE = re.compile(r"\b(x264|x265|h\.?264|h\.?265|HEVC|AVC|AV1|VP9)\b", re.IGNORECASE)


def _extract_quality(filename: str) -> Optional[str]:
    m = _QUALITY_RE.search(filename)
    return f"{m.group(1)}-{m.group(2)}" if m and m.group(2) else (m.group(1) if m else None)


def _extract_codec(filename: str) -> Optional[str]:
    m = _CODEC_RE.search(filename)
    return m.group(1) if m else None


# -----------------------------------------------------------------------
# Check / Lookup
# -----------------------------------------------------------------------


async def check_canonical(
    session: AsyncSession,
    tmdb_id: int,
    media_type: str,
) -> Optional[CanonicalContent]:
    """Look up canonical content by TMDB ID. Returns row if found AND path exists on disk."""
    result = await session.execute(
        select(CanonicalContent).where(
            CanonicalContent.tmdb_id == tmdb_id,
            CanonicalContent.media_type == media_type,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None

    if not os.path.exists(entry.canonical_path):
        logger.warning("Canonical entry tmdb=%d points to missing path: %s", tmdb_id, entry.canonical_path)
        return None

    return entry


async def check_inflight_download(
    session: AsyncSession,
    tmdb_id: int,
    media_type: str,
) -> Optional[Job]:
    """Check if another job is already downloading this content. Returns the active job if found."""
    result = await session.execute(
        select(Job).where(
            Job.tmdb_id == tmdb_id,
            Job.media_type == media_type,
            Job.state.in_([JobState.SEARCHING.value, JobState.DOWNLOADING.value]),
        ).limit(1)
    )
    return result.scalar_one_or_none()


# -----------------------------------------------------------------------
# Register
# -----------------------------------------------------------------------


async def register_canonical(
    session: AsyncSession,
    tmdb_id: int,
    media_type: str,
    title: str,
    canonical_path: str,
    radarr_id: int | None = None,
    sonarr_id: int | None = None,
) -> CanonicalContent:
    """Register content in the canonical library. Idempotent — updates if exists."""
    result = await session.execute(
        select(CanonicalContent).where(
            CanonicalContent.tmdb_id == tmdb_id,
            CanonicalContent.media_type == media_type,
        )
    )
    entry = result.scalar_one_or_none()

    # Get file info from canonical path
    file_size = None
    quality = None
    codec = None
    if os.path.isdir(canonical_path):
        for f in Path(canonical_path).rglob("*"):
            if f.is_file() and f.suffix in (".mkv", ".mp4", ".avi"):
                file_size = f.stat().st_size
                quality = _extract_quality(f.name)
                codec = _extract_codec(f.name)
                break

    if entry is None:
        entry = CanonicalContent(
            tmdb_id=tmdb_id,
            media_type=media_type,
            title=title,
            canonical_path=canonical_path,
            file_size_bytes=file_size,
            quality=quality,
            codec=codec,
            radarr_id=radarr_id,
            sonarr_id=sonarr_id,
        )
        session.add(entry)
    else:
        entry.canonical_path = canonical_path
        entry.file_size_bytes = file_size
        entry.quality = quality
        entry.codec = codec
        entry.updated_at = datetime.utcnow()
        entry.gc_eligible_at = None  # Clear GC if re-added
        if radarr_id:
            entry.radarr_id = radarr_id
        if sonarr_id:
            entry.sonarr_id = sonarr_id

    await session.flush()
    return entry


# -----------------------------------------------------------------------
# Symlink operations
# -----------------------------------------------------------------------


def create_user_symlink(
    canonical_path: str,
    user_id: str,
    media_type: str,
) -> str:
    """Create a folder-level symlink from user's library to canonical content.

    Returns the symlink path.
    """
    config = get_config()
    folder_name = os.path.basename(canonical_path)
    subdir = "Movies" if media_type == "movie" else "TV"
    user_dir = os.path.join(config.media_path, "users", user_id, subdir)
    symlink_path = os.path.join(user_dir, folder_name)

    # Ensure user subdir exists
    os.makedirs(user_dir, exist_ok=True)

    # Create symlink (idempotent)
    if os.path.islink(symlink_path):
        current_target = os.readlink(symlink_path)
        if current_target != canonical_path:
            os.unlink(symlink_path)
            os.symlink(canonical_path, symlink_path)
    elif os.path.exists(symlink_path):
        # Real dir exists (legacy per-user content) — leave it alone
        logger.warning("Real directory exists at symlink target, skipping: %s", symlink_path)
        return symlink_path
    else:
        os.symlink(canonical_path, symlink_path)

    logger.info("Symlinked %s -> %s", symlink_path, canonical_path)
    return symlink_path


# -----------------------------------------------------------------------
# User content tracking
# -----------------------------------------------------------------------


async def add_user_content(
    session: AsyncSession,
    user_id: str,
    canonical: CanonicalContent,
    job_id: str | None = None,
    symlink_path: str | None = None,
    status: str = "active",
) -> UserContent:
    """Add or reactivate a user_content row. Idempotent."""
    import uuid as _uuid
    uid = _uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    jid = _uuid.UUID(job_id) if isinstance(job_id, str) and job_id else job_id

    result = await session.execute(
        select(UserContent).where(
            UserContent.user_id == uid,
            UserContent.canonical_content_id == canonical.id,
        )
    )
    uc = result.scalar_one_or_none()

    if uc is None:
        uc = UserContent(
            user_id=uid,
            canonical_content_id=canonical.id,
            symlink_path=symlink_path,
            job_id=jid,
            status=status,
        )
        session.add(uc)
    else:
        uc.status = status
        uc.symlink_path = symlink_path or uc.symlink_path
        uc.removed_at = None
        if jid:
            uc.job_id = jid

    await session.flush()
    return uc


async def remove_user_content(
    session: AsyncSession,
    user_id: str,
    canonical_content_id: str,
) -> bool:
    """Mark a user_content row as removed. Returns True if this was the last reference (GC eligible)."""
    import uuid as _uuid
    uid = _uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    cid = _uuid.UUID(canonical_content_id) if isinstance(canonical_content_id, str) else canonical_content_id

    result = await session.execute(
        select(UserContent).where(
            UserContent.user_id == uid,
            UserContent.canonical_content_id == cid,
        )
    )
    uc = result.scalar_one_or_none()
    if uc is None:
        return False

    uc.status = "removed"
    uc.removed_at = datetime.utcnow()

    # Check if any active references remain
    count = await session.scalar(
        select(func.count(UserContent.id)).where(
            UserContent.canonical_content_id == cid,
            UserContent.status == "active",
            UserContent.user_id != uid,
        )
    )

    if count == 0:
        # Mark canonical for GC
        await session.execute(
            sa_update(CanonicalContent)
            .where(CanonicalContent.id == cid)
            .values(gc_eligible_at=datetime.utcnow())
        )
        return True

    return False


# -----------------------------------------------------------------------
# Quota checks (item-count based)
# -----------------------------------------------------------------------


async def check_item_quota(
    session: AsyncSession,
    user: User,
    media_type: str,
) -> None:
    """Check user's item-count quota. Raises ValueError if exceeded."""
    if media_type == "movie":
        if user.movie_quota == -1:
            return
        if user.movie_count >= user.movie_quota:
            raise ValueError(
                f"Movie quota reached: {user.movie_count}/{user.movie_quota} movies. "
                f"Delete content or upgrade your plan."
            )
    else:
        if user.tv_quota == -1:
            return
        if user.tv_count >= user.tv_quota:
            raise ValueError(
                f"TV quota reached: {user.tv_count}/{user.tv_quota} series. "
                f"Delete content or upgrade your plan."
            )


async def increment_user_count(
    session: AsyncSession,
    user_id,
    media_type: str,
) -> None:
    """Increment the user's movie_count or tv_count."""
    if media_type == "movie":
        await session.execute(
            sa_update(User).where(User.id == user_id).values(movie_count=User.movie_count + 1)
        )
    else:
        await session.execute(
            sa_update(User).where(User.id == user_id).values(tv_count=User.tv_count + 1)
        )


async def decrement_user_count(
    session: AsyncSession,
    user_id,
    media_type: str,
) -> None:
    """Decrement the user's movie_count or tv_count (floor at 0)."""
    if media_type == "movie":
        await session.execute(
            sa_update(User).where(User.id == user_id)
            .values(movie_count=func.greatest(User.movie_count - 1, 0))
        )
    else:
        await session.execute(
            sa_update(User).where(User.id == user_id)
            .values(tv_count=func.greatest(User.tv_count - 1, 0))
        )
