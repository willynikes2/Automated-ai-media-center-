"""Async Radarr v3 API client."""

import logging

import httpx

from shared.config import get_config

logger = logging.getLogger(__name__)


class RadarrClient:
    """Async wrapper around the Radarr v3 REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        config = get_config()
        self._base_url = (base_url or config.radarr_url).rstrip("/")
        self._api_key = api_key or config.radarr_api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-Api-Key": self._api_key},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    # -- Movies ---------------------------------------------------------------

    async def lookup_movie(self, tmdb_id: int) -> dict | None:
        """Lookup a movie by TMDB ID. Returns the first match or None."""
        resp = await self._client.get(
            "/api/v3/movie/lookup", params={"term": f"tmdb:{tmdb_id}"}
        )
        resp.raise_for_status()
        results = resp.json()
        return results[0] if results else None

    async def add_movie(
        self,
        tmdb_id: int,
        title: str,
        root_folder_path: str,
        quality_profile_id: int,
        search_for_movie: bool = True,
    ) -> dict:
        """Add a movie to Radarr and optionally trigger a search."""
        # Lookup first to get full metadata
        lookup = await self.lookup_movie(tmdb_id)
        if not lookup:
            raise ValueError(f"Radarr lookup failed for tmdb:{tmdb_id}")

        payload = {
            "tmdbId": tmdb_id,
            "title": lookup.get("title", title),
            "titleSlug": lookup.get("titleSlug", ""),
            "year": lookup.get("year", 0),
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder_path,
            "images": lookup.get("images", []),
            "monitored": True,
            "minimumAvailability": "released",
            "addOptions": {"searchForMovie": search_for_movie},
        }
        logger.info("Adding movie to Radarr: %s (tmdb:%d)", title, tmdb_id)
        resp = await self._client.post("/api/v3/movie", json=payload)
        if resp.is_error:
            detail = resp.text[:2000]
            logger.error(
                "Radarr add_movie failed status=%d payload_root=%s profile=%s body=%s",
                resp.status_code,
                payload.get("rootFolderPath"),
                payload.get("qualityProfileId"),
                detail,
            )
            raise RuntimeError(
                f"Radarr add movie failed ({resp.status_code}): {detail}"
            )
        movie = resp.json()
        logger.info("Radarr movie added: id=%d", movie["id"])
        return movie

    async def get_movie(self, movie_id: int) -> dict:
        """Get movie by Radarr internal ID."""
        resp = await self._client.get(f"/api/v3/movie/{movie_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_movie_by_tmdb(self, tmdb_id: int) -> dict | None:
        """Find an existing movie in Radarr by TMDB ID."""
        resp = await self._client.get("/api/v3/movie", params={"tmdbId": tmdb_id})
        resp.raise_for_status()
        results = resp.json()
        return results[0] if results else None

    async def search_movie(self, movie_id: int) -> dict:
        """Trigger a manual search for a movie."""
        payload = {"name": "MoviesSearch", "movieIds": [movie_id]}
        resp = await self._client.post("/api/v3/command", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_releases(self, movie_id: int) -> list[dict]:
        """Get interactive search results for a movie (manual release selection)."""
        resp = await self._client.get(
            "/api/v3/release", params={"movieId": movie_id}
        )
        resp.raise_for_status()
        return resp.json()

    async def grab_release(self, guid: str, indexer_id: int) -> dict:
        """Grab a specific release by GUID (manual selection download)."""
        payload = {"guid": guid, "indexerId": indexer_id}
        resp = await self._client.post("/api/v3/release", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def trigger_downloaded_movies_scan(
        self,
        path: str,
        download_client_id: str | None = None,
        import_mode: str = "Move",
    ) -> dict:
        """Trigger Radarr DownloadedMoviesScan for an already-downloaded path."""
        payload: dict = {
            "name": "DownloadedMoviesScan",
            "path": path,
            "importMode": import_mode,
        }
        if download_client_id:
            payload["downloadClientId"] = download_client_id
        resp = await self._client.post("/api/v3/command", json=payload)
        if resp.is_error:
            detail = resp.text[:2000]
            logger.error(
                "Radarr DownloadedMoviesScan failed status=%d path=%s body=%s",
                resp.status_code,
                path,
                detail,
            )
            raise RuntimeError(
                f"Radarr DownloadedMoviesScan failed ({resp.status_code}): {detail}"
            )
        return resp.json()

    async def delete_movie(self, movie_id: int, delete_files: bool = False) -> None:
        """Delete a movie from Radarr."""
        resp = await self._client.delete(
            f"/api/v3/movie/{movie_id}",
            params={"deleteFiles": str(delete_files).lower()},
        )
        resp.raise_for_status()

    # -- Queue ----------------------------------------------------------------

    async def get_queue(
        self, page: int = 1, page_size: int = 50, include_movie: bool = True
    ) -> dict:
        """Get the download queue."""
        resp = await self._client.get(
            "/api/v3/queue",
            params={
                "page": page,
                "pageSize": page_size,
                "includeMovie": str(include_movie).lower(),
                "includeUnknownMovieItems": "false",
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_queue_item(
        self, queue_id: int, blacklist: bool = True, remove_from_client: bool = True
    ) -> None:
        """Remove a queue item (failed/stuck download)."""
        resp = await self._client.delete(
            f"/api/v3/queue/{queue_id}",
            params={
                "removeFromClient": str(remove_from_client).lower(),
                "blocklist": str(blacklist).lower(),
            },
        )
        resp.raise_for_status()
        logger.info("Removed Radarr queue item %d (blacklist=%s)", queue_id, blacklist)

    # -- History --------------------------------------------------------------

    async def get_history(
        self, movie_id: int | None = None, page: int = 1, page_size: int = 20
    ) -> dict:
        """Get download history, optionally filtered by movie."""
        params: dict = {"page": page, "pageSize": page_size, "sortKey": "date", "sortDirection": "descending"}
        if movie_id is not None:
            params["movieIds"] = movie_id
        resp = await self._client.get("/api/v3/history", params=params)
        resp.raise_for_status()
        return resp.json()

    # -- Quality Profiles -----------------------------------------------------

    async def get_quality_profiles(self) -> list[dict]:
        """List all quality profiles."""
        resp = await self._client.get("/api/v3/qualityprofile")
        resp.raise_for_status()
        return resp.json()

    async def create_quality_profile(self, profile: dict) -> dict:
        """Create a new quality profile."""
        resp = await self._client.post("/api/v3/qualityprofile", json=profile)
        resp.raise_for_status()
        return resp.json()

    async def update_quality_profile(self, profile_id: int, profile: dict) -> dict:
        """Update an existing quality profile."""
        resp = await self._client.put(f"/api/v3/qualityprofile/{profile_id}", json=profile)
        resp.raise_for_status()
        return resp.json()

    # -- Custom Formats -------------------------------------------------------

    async def get_custom_formats(self) -> list[dict]:
        """List all custom formats."""
        resp = await self._client.get("/api/v3/customformat")
        resp.raise_for_status()
        return resp.json()

    async def create_custom_format(self, cf: dict) -> dict:
        """Create a new custom format."""
        resp = await self._client.post("/api/v3/customformat", json=cf)
        resp.raise_for_status()
        return resp.json()

    # -- Root Folders ---------------------------------------------------------

    async def get_root_folders(self) -> list[dict]:
        """List root folders."""
        resp = await self._client.get("/api/v3/rootfolder")
        resp.raise_for_status()
        return resp.json()

    async def add_root_folder(self, path: str) -> dict:
        """Register a new root folder path."""
        resp = await self._client.post("/api/v3/rootfolder", json={"path": path})
        if resp.is_error:
            detail = resp.text[:2000]
            logger.error(
                "Radarr add_root_folder failed status=%d path=%s body=%s",
                resp.status_code,
                path,
                detail,
            )
            raise RuntimeError(
                f"Radarr add root folder failed ({resp.status_code}): {detail}"
            )
        return resp.json()

    # -- Download Clients -----------------------------------------------------

    async def get_download_clients(self) -> list[dict]:
        """List configured download clients."""
        resp = await self._client.get("/api/v3/downloadclient")
        resp.raise_for_status()
        return resp.json()

    async def add_download_client(self, client_config: dict) -> dict:
        """Add a download client."""
        resp = await self._client.post("/api/v3/downloadclient", json=client_config)
        resp.raise_for_status()
        return resp.json()

    # -- System ---------------------------------------------------------------

    async def system_status(self) -> dict:
        """GET /api/v3/system/status"""
        resp = await self._client.get("/api/v3/system/status")
        resp.raise_for_status()
        return resp.json()

    # -- Lifecycle ------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "RadarrClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
