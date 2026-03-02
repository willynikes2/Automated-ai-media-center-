"""Smart storage management for the Invisible Arr edge node.

Handles disk pressure monitoring, watched-media pruning, and
resolution upgrade decisions.
"""

import logging
import os
import shutil
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Prefs

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Disk usage
# ---------------------------------------------------------------------------


def get_disk_usage(path: str) -> tuple[float, float, float]:
    """Return (total_gb, used_gb, percent_used) for the filesystem containing *path*.

    Falls back to (0, 0, 0) if the path doesn't exist.
    """
    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        percent = (usage.used / usage.total) * 100 if usage.total > 0 else 0.0
        return total_gb, used_gb, percent
    except OSError:
        logger.warning("Cannot stat disk usage for %s", path)
        return 0.0, 0.0, 0.0


# ---------------------------------------------------------------------------
# Watched-item detection (v1 stub)
# ---------------------------------------------------------------------------


async def get_watched_items(db_session: AsyncSession) -> list[str]:
    """Return a list of media paths that the user has watched.

    v1 stub — returns an empty list.  A future version will query the
    Jellyfin "Played Items" API and cross-reference local file paths.
    """
    _ = db_session  # will be used in v2
    return []


# ---------------------------------------------------------------------------
# Pruning logic
# ---------------------------------------------------------------------------


def _file_age_days(filepath: str) -> float:
    """Return the age of *filepath* in days based on its mtime."""
    try:
        mtime = os.path.getmtime(filepath)
        return (time.time() - mtime) / 86400.0
    except OSError:
        return 0.0


def _is_favorite(filepath: str) -> bool:
    """Check if a media file is marked as a favorite.

    v1 stub — always returns False.  Will integrate with Jellyfin
    favorites API in a later version.
    """
    _ = filepath
    return False


def prune_watched(
    user_prefs: Prefs,
    media_path: str,
    dry_run: bool = False,
) -> list[str]:
    """Remove watched media older than the configured threshold.

    Parameters
    ----------
    user_prefs:
        The user's preference row (provides ``prune_watched_after_days``
        and ``keep_favorites``).
    media_path:
        Root media directory to scan (e.g. ``/data/media``).
    dry_run:
        When True, return what *would* be deleted without actually
        removing anything.

    Returns
    -------
    list[str]
        Paths that were (or would be) pruned.
    """
    prune_after = user_prefs.prune_watched_after_days
    if prune_after is None or prune_after <= 0:
        logger.debug("Pruning disabled (prune_watched_after_days=%s).", prune_after)
        return []

    keep_favs = user_prefs.keep_favorites
    pruned: list[str] = []
    root = Path(media_path)

    if not root.exists():
        logger.warning("Media path does not exist: %s", media_path)
        return pruned

    for filepath in root.rglob("*"):
        if not filepath.is_file():
            continue

        age = _file_age_days(str(filepath))
        if age < prune_after:
            continue

        if keep_favs and _is_favorite(str(filepath)):
            logger.debug("Skipping favorite: %s", filepath)
            continue

        if dry_run:
            logger.info("[DRY RUN] Would prune: %s (%.1f days old)", filepath, age)
        else:
            try:
                filepath.unlink()
                logger.info("Pruned: %s (%.1f days old)", filepath, age)
            except OSError as exc:
                logger.error("Failed to prune %s: %s", filepath, exc)
                continue

        pruned.append(str(filepath))

    logger.info(
        "Pruning complete: %d files %s.",
        len(pruned),
        "would be removed" if dry_run else "removed",
    )
    return pruned


# ---------------------------------------------------------------------------
# Disk pressure
# ---------------------------------------------------------------------------


def check_disk_pressure(user_prefs: Prefs, media_path: str) -> bool:
    """Return True if disk usage exceeds the user's soft limit.

    Parameters
    ----------
    user_prefs:
        Provides ``storage_soft_limit_percent``.
    media_path:
        Path to check disk usage on.
    """
    _, _, percent = get_disk_usage(media_path)
    limit = user_prefs.storage_soft_limit_percent
    under_pressure = percent > limit
    if under_pressure:
        logger.warning(
            "Disk pressure: %.1f%% used (limit: %d%%) on %s",
            percent,
            limit,
            media_path,
        )
    else:
        logger.debug(
            "Disk OK: %.1f%% used (limit: %d%%) on %s",
            percent,
            limit,
            media_path,
        )
    return under_pressure


# ---------------------------------------------------------------------------
# Upgrade policy
# ---------------------------------------------------------------------------


def should_upgrade(
    current_resolution: int,
    new_resolution: int,
    upgrade_policy: str,
) -> bool:
    """Determine whether a media file should be upgraded to a higher resolution.

    Parameters
    ----------
    current_resolution:
        The resolution of the existing file (e.g. 720, 1080).
    new_resolution:
        The resolution of the candidate replacement.
    upgrade_policy:
        ``"on"`` to allow upgrades, anything else disables them.

    Returns
    -------
    bool
        True if the upgrade should proceed.
    """
    if upgrade_policy != "on":
        return False
    return new_resolution > current_resolution


# ---------------------------------------------------------------------------
# Main storage check (single iteration)
# ---------------------------------------------------------------------------


async def run_storage_check(
    media_path: str,
    db_session: AsyncSession,
) -> None:
    """Execute one storage-management cycle.

    1. Load the first user's prefs (single-user v1).
    2. Check disk pressure.
    3. If under pressure, prune watched media.
    """
    result = await db_session.execute(select(Prefs).limit(1))
    prefs_row = result.scalar_one_or_none()

    if prefs_row is None:
        logger.info("No user prefs found; skipping storage check.")
        return

    total_gb, used_gb, percent = get_disk_usage(media_path)
    logger.info(
        "Storage: %.1f / %.1f GB (%.1f%%)",
        used_gb,
        total_gb,
        percent,
    )

    under_pressure = check_disk_pressure(prefs_row, media_path)

    if under_pressure:
        logger.info("Disk pressure detected — running prune cycle.")
        pruned = prune_watched(prefs_row, media_path)
        if pruned:
            logger.info("Pruned %d items to relieve disk pressure.", len(pruned))
        else:
            logger.warning(
                "Disk pressure persists but no items eligible for pruning. "
                "Consider increasing storage or adjusting prune settings."
            )
    else:
        logger.info("No disk pressure. Storage check complete.")
