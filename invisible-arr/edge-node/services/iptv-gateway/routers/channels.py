"""IPTV channel listing and bulk-update routes."""

import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models import IptvChannel, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/iptv/channels", tags=["iptv-channels"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChannelResponse(BaseModel):
    """Response schema for a single IPTV channel."""

    id: uuid.UUID
    source_id: uuid.UUID
    tvg_id: str | None
    name: str
    group_title: str | None
    logo: str | None
    stream_url: str
    enabled: bool
    channel_number: int | None
    preferred_name: str | None
    preferred_group: str | None


class ChannelBulkUpdateItem(BaseModel):
    """Single item in a bulk-update request."""

    id: uuid.UUID
    enabled: bool | None = None
    channel_number: int | None = None
    preferred_name: str | None = None
    preferred_group: str | None = None


class BulkUpdateResponse(BaseModel):
    """Response after a bulk channel update."""

    updated: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_from_api_key(
    db: AsyncSession,
    x_api_key: str,
) -> User:
    """Resolve a User from the X-Api-Key header."""
    result = await db.execute(select(User).where(User.api_key == x_api_key))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ChannelResponse])
async def list_channels(
    source_id: uuid.UUID | None = Query(default=None),
    group: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(...),
) -> list[ChannelResponse]:
    """List IPTV channels with optional filters.

    Query parameters:
    - ``source_id``: filter by source
    - ``group``: filter by group_title (exact match)
    - ``enabled``: filter by enabled status
    """
    user = await _get_user_from_api_key(db, x_api_key)

    stmt = select(IptvChannel).where(IptvChannel.user_id == user.id)

    if source_id is not None:
        stmt = stmt.where(IptvChannel.source_id == source_id)
    if group is not None:
        stmt = stmt.where(IptvChannel.group_title == group)
    if enabled is not None:
        stmt = stmt.where(IptvChannel.enabled == enabled)

    stmt = stmt.order_by(IptvChannel.channel_number.asc().nulls_last(), IptvChannel.name.asc())

    result = await db.execute(stmt)
    channels = result.scalars().all()

    return [
        ChannelResponse(
            id=ch.id,
            source_id=ch.source_id,
            tvg_id=ch.tvg_id,
            name=ch.name,
            group_title=ch.group_title,
            logo=ch.logo,
            stream_url=ch.stream_url,
            enabled=ch.enabled,
            channel_number=ch.channel_number,
            preferred_name=ch.preferred_name,
            preferred_group=ch.preferred_group,
        )
        for ch in channels
    ]


@router.post("/bulk", response_model=BulkUpdateResponse)
async def bulk_update_channels(
    items: list[ChannelBulkUpdateItem],
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(...),
) -> BulkUpdateResponse:
    """Bulk update channel preferences (enabled, channel_number, preferred_name, preferred_group).

    Only provided (non-None) fields are updated for each channel.
    """
    user = await _get_user_from_api_key(db, x_api_key)

    channel_ids = [item.id for item in items]
    result = await db.execute(
        select(IptvChannel).where(
            IptvChannel.id.in_(channel_ids),
            IptvChannel.user_id == user.id,
        )
    )
    channels_by_id = {ch.id: ch for ch in result.scalars().all()}

    updated_count = 0
    for item in items:
        channel = channels_by_id.get(item.id)
        if channel is None:
            logger.warning(
                "Channel %s not found or not owned by user %s -- skipping",
                item.id,
                user.id,
            )
            continue

        changed = False
        if item.enabled is not None:
            channel.enabled = item.enabled
            changed = True
        if item.channel_number is not None:
            channel.channel_number = item.channel_number
            changed = True
        if item.preferred_name is not None:
            channel.preferred_name = item.preferred_name
            changed = True
        if item.preferred_group is not None:
            channel.preferred_group = item.preferred_group
            changed = True

        if changed:
            updated_count += 1

    logger.info("Bulk-updated %d channels for user %s", updated_count, user.id)
    return BulkUpdateResponse(updated=updated_count)
