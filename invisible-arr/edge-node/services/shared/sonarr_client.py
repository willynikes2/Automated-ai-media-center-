"""Async Sonarr v3 API client."""

import logging

import httpx

from shared.config import get_config

logger = logging.getLogger(__name__)


class SonarrClient:
    """Async wrapper around the Sonarr v3 REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        config = get_config()
        self._base_url = (base_url or config.sonarr_url).rstrip("/")
        self._api_key = api_key or config.sonarr_api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-Api-Key": self._api_key},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    # -- Series ---------------------------------------------------------------

    async def lookup_series(self, term: str) -> list[dict]:
        """Search for a series by name or tvdb:ID."""
        resp = await self._client.get(
            "/api/v3/series/lookup", params={"term": term}
        )
        resp.raise_for_status()
        return resp.json()

    async def add_series(
        self,
        tvdb_id: int,
        title: str,
        title_slug: str,
        seasons: list[dict],
        root_folder_path: str,
        quality_profile_id: int,
        monitor: str = "all",
        season_folder: bool = True,
        search_for_missing: bool = True,
    ) -> dict:
        """Add a series to Sonarr and optionally search for missing episodes."""
        payload = {
            "tvdbId": tvdb_id,
            "title": title,
            "titleSlug": title_slug,
            "seasons": seasons,
            "rootFolderPath": root_folder_path,
            "qualityProfileId": quality_profile_id,
            "seasonFolder": season_folder,
            "monitored": True,
            "addOptions": {
                "monitor": monitor,  # "all", "future", "missing", "existing", "firstSeason", "none"
                "searchForMissingEpisodes": search_for_missing,
                "searchForCutoffUnmetEpisodes": False,
            },
        }
        logger.info("Adding series to Sonarr: %s (tvdb:%d)", title, tvdb_id)
        resp = await self._client.post("/api/v3/series", json=payload)
        if resp.is_error:
            detail = resp.text[:2000]
            logger.error(
                "Sonarr add_series failed status=%d payload_root=%s profile=%s body=%s",
                resp.status_code,
                payload.get("rootFolderPath"),
                payload.get("qualityProfileId"),
                detail,
            )
            raise RuntimeError(
                f"Sonarr add series failed ({resp.status_code}): {detail}"
            )
        series = resp.json()
        logger.info("Sonarr series added: id=%d", series["id"])
        return series

    async def get_series(self, series_id: int) -> dict:
        """Get series by Sonarr internal ID."""
        resp = await self._client.get(f"/api/v3/series/{series_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_series_by_tvdb(self, tvdb_id: int) -> dict | None:
        """Find an existing series in Sonarr by TVDB ID."""
        resp = await self._client.get("/api/v3/series")
        resp.raise_for_status()
        for s in resp.json():
            if s.get("tvdbId") == tvdb_id:
                return s
        return None

    async def update_series(self, series: dict) -> dict:
        """Update a series in Sonarr (e.g. to change monitored state)."""
        resp = await self._client.put(f"/api/v3/series/{series['id']}", json=series)
        resp.raise_for_status()
        return resp.json()

    async def update_episode(self, episode: dict) -> dict:
        """Update an episode in Sonarr (e.g. to change monitored state)."""
        resp = await self._client.put(f"/api/v3/episode/{episode['id']}", json=episode)
        resp.raise_for_status()
        return resp.json()

    async def delete_series(self, series_id: int, delete_files: bool = False) -> None:
        """Delete a series from Sonarr."""
        resp = await self._client.delete(
            f"/api/v3/series/{series_id}",
            params={"deleteFiles": str(delete_files).lower()},
        )
        resp.raise_for_status()

    # -- Episodes -------------------------------------------------------------

    async def get_episodes(self, series_id: int, season: int | None = None) -> list[dict]:
        """Get episodes for a series, optionally filtered by season."""
        params: dict = {"seriesId": series_id}
        if season is not None:
            params["seasonNumber"] = season
        resp = await self._client.get("/api/v3/episode", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_episode(self, episode_id: int) -> dict:
        """Get a single episode by Sonarr episode ID."""
        resp = await self._client.get(f"/api/v3/episode/{episode_id}")
        resp.raise_for_status()
        return resp.json()

    async def delete_episode_file(self, episode_file_id: int) -> None:
        """Delete an episode file from Sonarr."""
        resp = await self._client.delete(f"/api/v3/episodefile/{episode_file_id}")
        resp.raise_for_status()

    # -- Search Commands ------------------------------------------------------

    async def search_season(self, series_id: int, season_number: int) -> dict:
        """Trigger a manual search for a specific season."""
        payload = {
            "name": "SeasonSearch",
            "seriesId": series_id,
            "seasonNumber": season_number,
        }
        resp = await self._client.post("/api/v3/command", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def search_episodes(self, episode_ids: list[int]) -> dict:
        """Trigger a manual search for specific episodes."""
        payload = {"name": "EpisodeSearch", "episodeIds": episode_ids}
        resp = await self._client.post("/api/v3/command", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_releases(self, series_id: int, season_number: int | None = None, episode_id: int | None = None) -> list[dict]:
        """Get interactive search results for a series/season/episode."""
        params: dict = {"seriesId": series_id}
        if episode_id is not None:
            params["episodeId"] = episode_id
        elif season_number is not None:
            params["seasonNumber"] = season_number
        resp = await self._client.get("/api/v3/release", params=params)
        resp.raise_for_status()
        return resp.json()

    async def grab_release(self, guid: str, indexer_id: int) -> dict:
        """Grab a specific release by GUID."""
        payload = {"guid": guid, "indexerId": indexer_id}
        resp = await self._client.post("/api/v3/release", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def search_series(self, series_id: int) -> dict:
        """Trigger a full series search."""
        payload = {"name": "SeriesSearch", "seriesId": series_id}
        resp = await self._client.post("/api/v3/command", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def trigger_downloaded_episodes_scan(
        self,
        path: str,
        download_client_id: str | None = None,
        import_mode: str = "Move",
    ) -> dict:
        """Trigger Sonarr DownloadedEpisodesScan for an already-downloaded path."""
        payload: dict = {
            "name": "DownloadedEpisodesScan",
            "path": path,
            "importMode": import_mode,
        }
        if download_client_id:
            payload["downloadClientId"] = download_client_id
        resp = await self._client.post("/api/v3/command", json=payload)
        if resp.is_error:
            detail = resp.text[:2000]
            logger.error(
                "Sonarr DownloadedEpisodesScan failed status=%d path=%s body=%s",
                resp.status_code,
                path,
                detail,
            )
            raise RuntimeError(
                f"Sonarr DownloadedEpisodesScan failed ({resp.status_code}): {detail}"
            )
        return resp.json()

    # -- Queue ----------------------------------------------------------------

    async def get_queue(
        self, page: int = 1, page_size: int = 50, include_series: bool = True
    ) -> dict:
        """Get the download queue."""
        resp = await self._client.get(
            "/api/v3/queue",
            params={
                "page": page,
                "pageSize": page_size,
                "includeSeries": str(include_series).lower(),
                "includeEpisode": "true",
                "includeUnknownSeriesItems": "false",
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
        logger.info("Removed Sonarr queue item %d (blacklist=%s)", queue_id, blacklist)

    # -- History --------------------------------------------------------------

    async def get_history(
        self, series_id: int | None = None, page: int = 1, page_size: int = 20
    ) -> dict:
        """Get download history."""
        params: dict = {"page": page, "pageSize": page_size, "sortKey": "date", "sortDirection": "descending"}
        if series_id is not None:
            params["seriesId"] = series_id
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
                "Sonarr add_root_folder failed status=%d path=%s body=%s",
                resp.status_code,
                path,
                detail,
            )
            raise RuntimeError(
                f"Sonarr add root folder failed ({resp.status_code}): {detail}"
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

    async def __aenter__(self) -> "SonarrClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
