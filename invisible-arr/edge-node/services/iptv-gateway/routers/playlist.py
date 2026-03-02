"""Dynamic playlist and EPG generation routes.

Serves M3U playlists and timezone-localized XMLTV EPG data to IPTV
clients such as TiviMate, Jellyfin Live TV, or xTeVe.
"""

import logging

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.models import IptvChannel, IptvSource, User
from m3u_parser import generate_m3u
from timezone_converter import localize_xmltv

logger = logging.getLogger(__name__)
router = APIRouter(tags=["iptv-playlist"])

# Redis cache TTL for EPG data (1 hour)
EPG_CACHE_TTL_SECONDS: int = 3600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_by_token(
    db: AsyncSession,
    user_token: str,
) -> User:
    """Look up a user by their API key (used as user_token in playlist URLs)."""
    result = await db.execute(select(User).where(User.api_key == user_token))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token",
        )
    return user


def _get_redis(request: Request) -> redis.Redis:
    """Extract the Redis client from application state."""
    redis_client: redis.Redis | None = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        )
    return redis_client


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/playlist.m3u")
async def get_playlist(
    user_token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Generate a merged M3U playlist from all enabled sources/channels.

    Authenticated by ``user_token`` query parameter (the user's API key).
    Returns ``application/x-mpegurl`` content type for IPTV client compatibility.
    """
    user = await _get_user_by_token(db, user_token)

    # Fetch all enabled channels for this user from enabled sources
    result = await db.execute(
        select(IptvChannel)
        .join(IptvSource, IptvChannel.source_id == IptvSource.id)
        .where(
            IptvChannel.user_id == user.id,
            IptvChannel.enabled.is_(True),
            IptvSource.enabled.is_(True),
        )
        .order_by(
            IptvChannel.channel_number.asc().nulls_last(),
            IptvChannel.name.asc(),
        )
    )
    channels = result.scalars().all()

    if not channels:
        logger.info("No enabled channels found for user %s", user.id)

    # Convert ORM objects to dicts for the M3U generator
    channel_dicts: list[dict] = [
        {
            "tvg_id": ch.tvg_id,
            "name": ch.name,
            "preferred_name": ch.preferred_name,
            "logo": ch.logo,
            "group_title": ch.group_title,
            "preferred_group": ch.preferred_group,
            "stream_url": ch.stream_url,
            "channel_number": ch.channel_number,
        }
        for ch in channels
    ]

    m3u_content = generate_m3u(channel_dicts)
    logger.info("Generated M3U with %d channels for user %s", len(channels), user.id)

    return Response(
        content=m3u_content,
        media_type="application/x-mpegurl",
        headers={"Content-Disposition": 'inline; filename="playlist.m3u"'},
    )


@router.get("/epg.xml")
async def get_epg(
    request: Request,
    user_token: str = Query(...),
    tz: str = Query(default="America/New_York"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Generate timezone-localized XMLTV EPG from all enabled sources.

    Authenticated by ``user_token`` query parameter. EPG data is cached in
    Redis with a 1-hour TTL, keyed by user + source + timezone.

    Parameters
    ----------
    user_token:
        The user's API key.
    tz:
        Target IANA timezone (e.g. ``America/New_York``). Defaults to
        ``America/New_York``.
    """
    user = await _get_user_by_token(db, user_token)
    redis_client = _get_redis(request)

    # Get all enabled sources with EPG URLs
    result = await db.execute(
        select(IptvSource).where(
            IptvSource.user_id == user.id,
            IptvSource.enabled.is_(True),
            IptvSource.epg_url.isnot(None),
        )
    )
    sources = result.scalars().all()

    if not sources:
        # Return a minimal valid XMLTV document
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?>\n<tv></tv>\n',
            media_type="application/xml",
        )

    # Build combined EPG from all sources, using cache where available
    combined_parts: list[str] = []

    for source in sources:
        cache_key = f"iptv:epg:{user.id}:{source.id}:{tz}"

        # Try cache first
        cached = await redis_client.get(cache_key)
        if cached is not None:
            logger.debug("EPG cache hit for source %s, tz %s", source.id, tz)
            combined_parts.append(cached if isinstance(cached, str) else cached.decode("utf-8"))
            continue

        # Fetch EPG from source
        assert source.epg_url is not None
        headers = source.headers_json or {}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(source.epg_url, headers=headers)
                resp.raise_for_status()
                raw_epg = resp.text
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch EPG from %s: %s", source.epg_url, exc)
            continue

        # Localize timezone
        try:
            localized_epg = localize_xmltv(raw_epg, source.source_timezone, tz)
        except Exception as exc:
            logger.error("Failed to localize EPG for source %s: %s", source.id, exc)
            continue

        # Cache the result
        await redis_client.set(cache_key, localized_epg, ex=EPG_CACHE_TTL_SECONDS)
        logger.info("Cached EPG for source %s, tz %s (TTL=%ds)", source.id, tz, EPG_CACHE_TTL_SECONDS)

        combined_parts.append(localized_epg)

    if not combined_parts:
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?>\n<tv></tv>\n',
            media_type="application/xml",
        )

    # If single source, return directly; if multiple, merge XML documents
    if len(combined_parts) == 1:
        epg_xml = combined_parts[0]
    else:
        epg_xml = _merge_xmltv_documents(combined_parts)

    logger.info("Serving EPG with %d source(s) for user %s in tz %s", len(combined_parts), user.id, tz)

    return Response(
        content=epg_xml,
        media_type="application/xml",
        headers={"Content-Disposition": 'inline; filename="epg.xml"'},
    )


def _merge_xmltv_documents(documents: list[str]) -> str:
    """Merge multiple XMLTV documents into a single document.

    Takes the ``<channel>`` and ``<programme>`` elements from each document
    and combines them under a single ``<tv>`` root.

    Parameters
    ----------
    documents:
        List of XMLTV XML strings.

    Returns
    -------
    str
        Merged XMLTV document.
    """
    from lxml import etree

    merged_root = etree.Element("tv")

    for doc in documents:
        try:
            root = etree.fromstring(doc.encode("utf-8"))
        except etree.XMLSyntaxError:
            logger.warning("Skipping malformed XMLTV document during merge")
            continue

        for channel in root.findall("channel"):
            merged_root.append(channel)
        for programme in root.findall("programme"):
            merged_root.append(programme)

    return etree.tostring(
        merged_root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")
