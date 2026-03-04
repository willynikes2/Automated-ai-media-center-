"""Async TMDB (The Movie Database) API client."""

import logging

import httpx

from shared.config import get_config

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.themoviedb.org/3"


class TMDBClient:
    """Async wrapper around the TMDB v3 REST API.

    Parameters
    ----------
    api_key:
        TMDB API key (v3 auth via query param).  Defaults to config value.
    """

    def __init__(self, api_key: str | None = None) -> None:
        config = get_config()
        self._api_key = api_key or config.tmdb_api_key
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            params={"api_key": self._api_key},
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    # -- search ------------------------------------------------------------

    async def search_movie(self, query: str, year: int | None = None) -> dict:
        """GET /search/movie -- search for movies by title."""
        params: dict[str, str | int] = {"query": query}
        if year is not None:
            params["year"] = year
        response = await self._client.get("/search/movie", params=params)
        response.raise_for_status()
        data: dict = response.json()
        logger.info(
            "TMDB movie search %r year=%s -> %d results",
            query,
            year,
            data.get("total_results", 0),
        )
        return data

    async def search_tv(self, query: str, year: int | None = None) -> dict:
        """GET /search/tv -- search for TV shows by title."""
        params: dict[str, str | int] = {"query": query}
        if year is not None:
            params["first_air_date_year"] = year
        response = await self._client.get("/search/tv", params=params)
        response.raise_for_status()
        data: dict = response.json()
        logger.info(
            "TMDB TV search %r year=%s -> %d results",
            query,
            year,
            data.get("total_results", 0),
        )
        return data

    # -- detail ------------------------------------------------------------

    async def get_movie(self, tmdb_id: int) -> dict:
        """GET /movie/{id} -- fetch full movie details."""
        response = await self._client.get(f"/movie/{tmdb_id}")
        response.raise_for_status()
        data: dict = response.json()
        logger.info("TMDB movie detail: %s (%s)", data.get("title"), tmdb_id)
        return data

    async def get_tv(self, tmdb_id: int) -> dict:
        """GET /tv/{id} -- fetch full TV show details."""
        response = await self._client.get(f"/tv/{tmdb_id}")
        response.raise_for_status()
        data: dict = response.json()
        logger.info("TMDB TV detail: %s (%s)", data.get("name"), tmdb_id)
        return data

    # -- resolve -----------------------------------------------------------

    async def resolve(
        self, query: str, media_type: str
    ) -> tuple[int, str, int]:
        """Resolve a free-text query to (tmdb_id, canonical_title, year).

        Parameters
        ----------
        query:
            User-provided search string.
        media_type:
            ``"movie"`` or ``"tv"``.

        Returns
        -------
        A tuple of (tmdb_id, canonical_title, year).

        Raises
        ------
        ValueError
            If no results are found for the query.
        """
        if media_type == "movie":
            data = await self.search_movie(query)
            results = data.get("results", [])
            if not results:
                raise ValueError(f"No TMDB movie results for query: {query!r}")
            top = results[0]
            tmdb_id: int = top["id"]
            title: str = top["title"]
            release_date: str = top.get("release_date", "")
            year = int(release_date[:4]) if release_date and len(release_date) >= 4 else 0
        elif media_type == "tv":
            data = await self.search_tv(query)
            results = data.get("results", [])
            if not results:
                raise ValueError(f"No TMDB TV results for query: {query!r}")
            top = results[0]
            tmdb_id = top["id"]
            title = top["name"]
            first_air: str = top.get("first_air_date", "")
            year = int(first_air[:4]) if first_air and len(first_air) >= 4 else 0
        else:
            raise ValueError(f"Unknown media_type: {media_type!r}")

        logger.info(
            "TMDB resolve %r (%s) -> id=%d title=%r year=%d",
            query,
            media_type,
            tmdb_id,
            title,
            year,
        )
        return tmdb_id, title, year

    # -- TV seasons/episodes -----------------------------------------------

    async def get_tv_seasons(self, tmdb_id: int) -> list[dict]:
        """Return season summaries for a TV show.

        Each dict has: season_number, name, episode_count, air_date, overview.
        Excludes specials (season 0).
        """
        data = await self.get_tv(tmdb_id)
        seasons: list[dict] = []
        for s in data.get("seasons", []):
            if s.get("season_number", 0) == 0:
                continue  # skip specials
            seasons.append({
                "season_number": s["season_number"],
                "name": s.get("name", f"Season {s['season_number']}"),
                "episode_count": s.get("episode_count", 0),
                "air_date": s.get("air_date"),
                "overview": s.get("overview", ""),
            })
        return seasons

    async def get_season_detail(self, tmdb_id: int, season_number: int) -> dict:
        """Fetch episode list for a specific season.

        Returns dict with: season_number, name, episodes (list of episode dicts).
        """
        resp = await self._client.get(f"/tv/{tmdb_id}/season/{season_number}")
        resp.raise_for_status()
        data: dict = resp.json()
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

    # -- external IDs ------------------------------------------------------

    async def get_external_ids(self, tmdb_id: int, media_type: str) -> dict:
        """GET /{media_type}/{id}/external_ids — returns tvdb_id, imdb_id, etc."""
        endpoint = "movie" if media_type == "movie" else "tv"
        resp = await self._client.get(f"/{endpoint}/{tmdb_id}/external_ids")
        resp.raise_for_status()
        return resp.json()

    # -- alternate titles --------------------------------------------------

    async def get_alternative_titles(
        self, tmdb_id: int, media_type: str
    ) -> list[str]:
        """Fetch alternative/international titles for a movie or TV show.

        Returns a list of title strings (max 10). Empty list on error.
        """
        try:
            if media_type == "movie":
                resp = await self._client.get(
                    f"/movie/{tmdb_id}/alternative_titles"
                )
                resp.raise_for_status()
                return [
                    t["title"]
                    for t in resp.json().get("titles", [])[:10]
                    if t.get("title")
                ]
            else:
                resp = await self._client.get(
                    f"/tv/{tmdb_id}/alternative_titles"
                )
                resp.raise_for_status()
                return [
                    t["title"]
                    for t in resp.json().get("results", [])[:10]
                    if t.get("title")
                ]
        except Exception:
            logger.debug("Failed to fetch alternative titles for TMDB %d", tmdb_id)
            return []

    # -- lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "TMDBClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
