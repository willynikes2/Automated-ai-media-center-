"""Storage info endpoint -- disk usage and policy summary."""

from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter
from pydantic import BaseModel

from shared.config import get_config

logger = logging.getLogger("agent-api.storage")
router = APIRouter()


class StorageResponse(BaseModel):
    total_gb: float
    used_gb: float
    free_gb: float
    media_gb: float
    soft_limit_pct: int
    prune_policy: str


@router.get("/storage", response_model=StorageResponse)
async def get_storage() -> StorageResponse:
    """Return disk usage info and storage policy summary."""
    config = get_config()

    try:
        disk = shutil.disk_usage(config.media_path)
        total_gb = round(disk.total / (1024 ** 3), 1)
        used_gb = round(disk.used / (1024 ** 3), 1)
        free_gb = round(disk.free / (1024 ** 3), 1)
    except Exception:
        logger.exception("Failed to get disk usage")
        total_gb = used_gb = free_gb = 0.0

    # Estimate media folder size (best effort)
    media_gb = 0.0
    try:
        from pathlib import Path

        media_path = Path(config.media_path)
        if media_path.exists():
            media_bytes = sum(f.stat().st_size for f in media_path.rglob("*") if f.is_file())
            media_gb = round(media_bytes / (1024 ** 3), 1)
    except Exception:
        logger.warning("Could not calculate media folder size")

    # Build policy description
    prune_days = getattr(config, "default_prune_watched_after_days", None)
    soft_limit = getattr(config, "default_storage_soft_limit_percent", 90)

    policy_parts = []
    if prune_days:
        policy_parts.append(f"Watched media pruned after {prune_days} days")
    else:
        policy_parts.append("No auto-pruning configured")
    policy_parts.append(f"Storage soft limit at {soft_limit}%")

    return StorageResponse(
        total_gb=total_gb,
        used_gb=used_gb,
        free_gb=free_gb,
        media_gb=media_gb,
        soft_limit_pct=soft_limit,
        prune_policy=". ".join(policy_parts),
    )
