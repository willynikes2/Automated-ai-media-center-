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


@router.get("/tmdb/{media_type}/{tmdb_id}")
async def detail(media_type: str, tmdb_id: int):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{_BASE}/{media_type}/{tmdb_id}",
            params={**_params(), "append_to_response": "credits,videos"},
        )
        r.raise_for_status()
        return r.json()
