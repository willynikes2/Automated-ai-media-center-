"""Release search endpoint -- preview available downloads before requesting."""

from __future__ import annotations

import logging
import shutil
from dataclasses import asdict

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel

from shared.config import get_config
from shared.prowlarr_client import ProwlarrClient
from shared.scoring import parse_release_title, score_candidate

logger = logging.getLogger("agent-api.search")
router = APIRouter()


class ReleaseResult(BaseModel):
    title: str
    resolution: int
    source: str
    codec: str
    audio: str
    size_gb: float
    seeders: int
    score: int
    info_hash: str
    indexer: str
    downloaders: list[str]  # e.g. ["rd", "torrent"]


class SearchResponse(BaseModel):
    query: str
    total_raw: int
    results: list[ReleaseResult]
    downloaders_available: list[str]
    storage_free_gb: float
    recommended_index: int | None  # index of best pick


@router.get("/search/releases", response_model=SearchResponse)
async def search_releases(
    query: str = Query(..., min_length=1),
    media_type: str = Query("movie", regex="^(movie|tv)$"),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
):
    """Search Prowlarr for releases matching a query and return scored results.

    This lets the frontend show available download options before the user
    commits to a request.
    """
    config = get_config()

    # Determine which downloaders are available
    available_downloaders: list[str] = []
    if config.rd_enabled and config.rd_api_token:
        available_downloaders.append("rd")
    if config.vpn_enabled:
        available_downloaders.append("torrent")
    # Torrent is always technically possible (Prowlarr returns magnets)
    if "torrent" not in available_downloaders:
        available_downloaders.append("torrent")

    # Storage info
    try:
        disk = shutil.disk_usage(config.media_path)
        storage_free_gb = round(disk.free / (1024 ** 3), 1)
    except Exception:
        storage_free_gb = 0.0

    # Default prefs for scoring
    prefs = {
        "max_resolution": config.default_max_resolution,
        "allow_4k": config.default_allow_4k,
        "max_movie_size_gb": config.default_max_movie_size_gb if media_type == "movie" else config.default_max_episode_size_gb,
    }

    # Search Prowlarr
    categories = [2000] if media_type == "movie" else [5000]
    try:
        async with ProwlarrClient(config.prowlarr_url, config.prowlarr_api_key) as prowlarr:
            raw_results = await prowlarr.search(query=query, categories=categories)
    except Exception as exc:
        logger.exception("Prowlarr search failed")
        return SearchResponse(
            query=query, total_raw=0, results=[],
            downloaders_available=available_downloaders,
            storage_free_gb=storage_free_gb,
            recommended_index=None,
        )

    # Parse, score, and sort
    scored: list[tuple[ReleaseResult, int]] = []
    for r in raw_results:
        parsed = parse_release_title(r.get("title", ""))
        parsed.size_gb = r.get("size", 0) / (1024 ** 3)
        parsed.seeders = r.get("seeders", 0)
        parsed.info_hash = r.get("infoHash", "")
        parsed.indexer = r.get("indexer", "")

        s = score_candidate(parsed, prefs)
        if s < 0:
            continue  # rejected by policy

        # Determine which downloaders work for this release
        release_downloaders: list[str] = []
        has_magnet = bool(r.get("magnetUrl") or r.get("downloadUrl", ""))
        if "rd" in available_downloaders and has_magnet:
            release_downloaders.append("rd")
        if "torrent" in available_downloaders and has_magnet:
            release_downloaders.append("torrent")

        scored.append((
            ReleaseResult(
                title=parsed.title,
                resolution=parsed.resolution,
                source=parsed.source,
                codec=parsed.codec,
                audio=parsed.audio,
                size_gb=round(parsed.size_gb, 2),
                seeders=parsed.seeders,
                score=s,
                info_hash=parsed.info_hash,
                indexer=parsed.indexer,
                downloaders=release_downloaders,
            ),
            s,
        ))

    # Sort by score desc, then size asc
    scored.sort(key=lambda x: (-x[1], x[0].size_gb))
    results = [r for r, _ in scored[:50]]  # cap at 50

    recommended = 0 if results else None

    return SearchResponse(
        query=query,
        total_raw=len(raw_results),
        results=results,
        downloaders_available=available_downloaders,
        storage_free_gb=storage_free_gb,
        recommended_index=recommended,
    )
