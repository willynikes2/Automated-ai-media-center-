"""Async Prowlarr API client for indexer search."""

import logging

import httpx

from shared.config import get_config

logger = logging.getLogger(__name__)


class ProwlarrClient:
    """Async wrapper around the Prowlarr v1 REST API.

    Parameters
    ----------
    base_url:
        Prowlarr instance URL.  Defaults to config value.
    api_key:
        Prowlarr API key.  Defaults to config value.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        config = get_config()
        self._base_url = (base_url or config.prowlarr_url).rstrip("/")
        self._api_key = api_key or config.prowlarr_api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-Api-Key": self._api_key},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    # -- public API --------------------------------------------------------

    async def search(
        self,
        query: str,
        categories: list[int] | None = None,
        indexer_ids: list[int] | None = None,
    ) -> list[dict]:
        """Search all (or specific) indexers via Prowlarr.

        Parameters
        ----------
        query:
            Search string.
        categories:
            Newznab category IDs to filter (e.g. [2000] for movies, [5000] for TV).
        indexer_ids:
            Restrict search to these indexer IDs.

        Returns
        -------
        List of raw Prowlarr result dicts.
        """
        params: dict[str, str | int] = {"query": query, "type": "search"}

        if categories:
            params["categories"] = ",".join(str(c) for c in categories)
        if indexer_ids:
            params["indexerIds"] = ",".join(str(i) for i in indexer_ids)

        logger.info("Prowlarr search: query=%r categories=%s", query, categories)
        response = await self._client.get("/api/v1/search", params=params)
        response.raise_for_status()
        results: list[dict] = response.json()
        logger.info("Prowlarr returned %d results for %r", len(results), query)
        return results

    async def get_indexers(self) -> list[dict]:
        """GET /api/v1/indexer -- list all configured indexers."""
        response = await self._client.get("/api/v1/indexer")
        response.raise_for_status()
        indexers: list[dict] = response.json()
        logger.info("Prowlarr has %d indexers configured", len(indexers))
        return indexers

    # -- lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "ProwlarrClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
