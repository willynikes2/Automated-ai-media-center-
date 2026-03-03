"""IPTV source management routes -- add, list, and remove M3U/EPG sources."""

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models import IptvChannel, IptvSource, User
from m3u_parser import parse_m3u

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/iptv/sources", tags=["iptv-sources"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class SourceCreateRequest(BaseModel):
    """Body for creating a new IPTV source."""

    m3u_url: str
    epg_url: str | None = None
    source_timezone: str = "UTC"
    headers_json: dict | None = None


class ChannelSummary(BaseModel):
    """Brief channel info returned when a source is created."""

    id: uuid.UUID
    tvg_id: str | None
    name: str
    group_title: str | None
    stream_url: str


class SourceResponse(BaseModel):
    """Response schema for an IPTV source."""

    id: uuid.UUID
    m3u_url: str
    epg_url: str | None
    source_timezone: str
    headers_json: dict | None
    enabled: bool
    channel_count: int


class SourceCreateResponse(BaseModel):
    """Response after creating a new source."""

    source: SourceResponse
    channels_imported: int


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


@router.post("", response_model=SourceCreateResponse, status_code=status.HTTP_201_CREATED)
async def add_source(
    body: SourceCreateRequest,
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(...),
) -> SourceCreateResponse:
    """Add an IPTV source, fetch its M3U, and import channels."""
    user = await _get_user_from_api_key(db, x_api_key)

    # Fetch M3U content
    headers = body.headers_json or {}
    if body.m3u_url.startswith("file://"):
        # Local file path (e.g. file:///data/iptv/filtered.m3u)
        import pathlib
        local_path = pathlib.Path(body.m3u_url.removeprefix("file://"))
        allowed_dir = pathlib.Path("/data/iptv")
        if not local_path.resolve().is_relative_to(allowed_dir.resolve()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Local files must be under /data/iptv/",
            )
        try:
            m3u_content = local_path.read_text(errors="replace")
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Local M3U file not found: {local_path}",
            ) from exc
    else:
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(body.m3u_url, headers=headers)
                resp.raise_for_status()
                m3u_content = resp.text
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch M3U from %s: %s", body.m3u_url, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch M3U: {exc}",
            ) from exc

    # Parse M3U
    parsed_channels = parse_m3u(m3u_content)
    if not parsed_channels:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No channels found in M3U content",
        )

    # Create source record
    source = IptvSource(
        user_id=user.id,
        m3u_url=body.m3u_url,
        epg_url=body.epg_url,
        source_timezone=body.source_timezone,
        headers_json=body.headers_json,
    )
    db.add(source)
    await db.flush()  # populate source.id

    # Create channel records
    channel_records: list[IptvChannel] = []
    for ch in parsed_channels:
        channel = IptvChannel(
            user_id=user.id,
            source_id=source.id,
            tvg_id=ch.get("tvg_id"),
            name=ch.get("name", "Unknown"),
            group_title=ch.get("group_title"),
            logo=ch.get("logo"),
            stream_url=ch.get("stream_url", ""),
        )
        db.add(channel)
        channel_records.append(channel)

    await db.flush()

    logger.info(
        "Imported source %s with %d channels for user %s",
        source.id,
        len(channel_records),
        user.id,
    )

    return SourceCreateResponse(
        source=SourceResponse(
            id=source.id,
            m3u_url=source.m3u_url,
            epg_url=source.epg_url,
            source_timezone=source.source_timezone,
            headers_json=source.headers_json,
            enabled=source.enabled,
            channel_count=len(channel_records),
        ),
        channels_imported=len(channel_records),
    )


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(...),
) -> list[SourceResponse]:
    """List all IPTV sources for the authenticated user."""
    user = await _get_user_from_api_key(db, x_api_key)

    result = await db.execute(
        select(IptvSource).where(IptvSource.user_id == user.id)
    )
    sources = result.scalars().all()

    return [
        SourceResponse(
            id=s.id,
            m3u_url=s.m3u_url,
            epg_url=s.epg_url,
            source_timezone=s.source_timezone,
            headers_json=s.headers_json,
            enabled=s.enabled,
            channel_count=len(s.channels),
        )
        for s in sources
    ]


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(...),
) -> None:
    """Delete an IPTV source and all its associated channels."""
    user = await _get_user_from_api_key(db, x_api_key)

    # Verify source exists and belongs to user
    result = await db.execute(
        select(IptvSource).where(
            IptvSource.id == source_id,
            IptvSource.user_id == user.id,
        )
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    # Delete channels first, then source
    await db.execute(
        delete(IptvChannel).where(IptvChannel.source_id == source_id)
    )
    await db.delete(source)

    logger.info("Deleted source %s and its channels for user %s", source_id, user.id)
