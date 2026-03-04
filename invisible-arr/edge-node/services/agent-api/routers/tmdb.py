"""TMDB proxy routes for the frontend — avoids exposing API key to clients."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Query

from shared.config import get_config

logger = logging.getLogger("agent-api.tmdb")
router = APIRouter()

_BASE = "https://api.themoviedb.org/3"


def _params() -> dict[str, str]:
    return {"api_key": get_config().tmdb_api_key}


@router.get("/tmdb/search")
async def search(query: str = Query(...), page: int = Query(1)):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{_BASE}/search/multi", params={**_params(), "query": query, "page": page})
        r.raise_for_status()
        return r.json()


@router.get("/tmdb/trending/{media_type}/{window}")
async def trending(media_type: str, window: str = "week"):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{_BASE}/trending/{media_type}/{window}", params=_params())
        r.raise_for_status()
        return r.json()


@router.get("/tmdb/popular/{media_type}")
async def popular(media_type: str):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{_BASE}/{media_type}/popular", params=_params())
        r.raise_for_status()
        return r.json()


@router.get("/tmdb/tv/{tmdb_id}/seasons")
async def tv_seasons(tmdb_id: int):
    """Return season list for a TV show (excludes specials)."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{_BASE}/tv/{tmdb_id}", params=_params())
        r.raise_for_status()
        data = r.json()
    seasons = []
    for s in data.get("seasons", []):
        if s.get("season_number", 0) == 0:
            continue
        seasons.append({
            "season_number": s["season_number"],
            "name": s.get("name", f"Season {s['season_number']}"),
            "episode_count": s.get("episode_count", 0),
            "air_date": s.get("air_date"),
        })
    return {"seasons": seasons, "number_of_seasons": data.get("number_of_seasons", 0)}


@router.get("/tmdb/tv/{tmdb_id}/season/{season_number}")
async def season_detail(tmdb_id: int, season_number: int):
    """Return episode list for a specific season."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{_BASE}/tv/{tmdb_id}/season/{season_number}", params=_params())
        r.raise_for_status()
        data = r.json()
    episodes = []
    for ep in data.get("episodes", []):
        episodes.append({
            "episode_number": ep["episode_number"],
            "name": ep.get("name", ""),
            "air_date": ep.get("air_date"),
            "overview": ep.get("overview", ""),
            "still_path": ep.get("still_path"),
            "runtime": ep.get("runtime"),
        })
    return {
        "season_number": data.get("season_number", season_number),
        "name": data.get("name", f"Season {season_number}"),
        "episodes": episodes,
    }


@router.get("/tmdb/{media_type}/{tmdb_id}")
async def detail(media_type: str, tmdb_id: int):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{_BASE}/{media_type}/{tmdb_id}",
            params={**_params(), "append_to_response": "credits,videos"},
        )
        r.raise_for_status()
        return r.json()
