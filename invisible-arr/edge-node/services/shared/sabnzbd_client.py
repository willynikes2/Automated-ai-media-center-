"""Async SABnzbd API client for Usenet downloads."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class SABnzbdError(Exception):
    """Raised for SABnzbd API errors."""


class SABnzbdClient:
    """Async wrapper around the SABnzbd API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    async def _api(self, mode: str, **kwargs) -> dict:
        """Make a SABnzbd API call."""
        params = {"apikey": self._api_key, "mode": mode, "output": "json", **kwargs}
        resp = await self._client.get("/api", params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") is False:
            raise SABnzbdError(f"SABnzbd error: {data.get('error', 'unknown')}")
        return data

    async def add_nzb_url(self, nzb_url: str, category: str = "automedia", name: str = "") -> str:
        """Send an NZB URL to SABnzbd for download. Returns the NZO ID."""
        data = await self._api("addurl", name=nzb_url, cat=category, nzbname=name)
        nzo_ids = data.get("nzo_ids", [])
        if not nzo_ids:
            raise SABnzbdError("SABnzbd returned no NZO IDs after adding URL")
        nzo_id = nzo_ids[0]
        logger.info("Added NZB to SABnzbd, nzo_id=%s", nzo_id)
        return nzo_id

    async def get_slot(self, nzo_id: str) -> dict | None:
        """Get download slot info for a specific NZO ID."""
        # Check active queue
        data = await self._api("queue")
        for slot in data.get("queue", {}).get("slots", []):
            if slot.get("nzo_id") == nzo_id:
                return {**slot, "phase": "downloading"}

        # Check history (completed/failed)
        data = await self._api("history", limit=50)
        for slot in data.get("history", {}).get("slots", []):
            if slot.get("nzo_id") == nzo_id:
                return {**slot, "phase": "completed"}

        return None

    async def poll_until_complete(self, nzo_id: str, timeout: int = 3600, interval: int = 10) -> dict:
        """Poll until NZB download completes or times out."""
        elapsed = 0
        while elapsed < timeout:
            slot = await self.get_slot(nzo_id)
            if slot is None:
                raise SABnzbdError(f"NZO {nzo_id} not found in SABnzbd")

            if slot["phase"] == "completed":
                status = slot.get("status", "")
                if status == "Completed":
                    logger.info("SABnzbd download complete: %s", nzo_id)
                    return slot
                if status == "Failed":
                    raise SABnzbdError(f"SABnzbd download failed: {slot.get('fail_message', 'unknown')}")

            logger.debug("SABnzbd %s: %s%% phase=%s", nzo_id, slot.get("percentage", "?"), slot["phase"])
            await asyncio.sleep(interval)
            elapsed += interval

        raise SABnzbdError(f"SABnzbd download {nzo_id} timed out after {timeout}s")

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "SABnzbdClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
