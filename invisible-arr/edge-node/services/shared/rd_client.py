"""Async Real-Debrid API client."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class RealDebridError(Exception):
    """Raised for Real-Debrid API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

_BASE_URL = "https://api.real-debrid.com/rest/1.0"
_MAX_RETRIES = 5
_INITIAL_BACKOFF = 2.0  # seconds


class RealDebridClient:
    """Async wrapper around the Real-Debrid REST API.

    Parameters
    ----------
    token:
        Bearer token for authentication.
    """

    def __init__(self, token: str) -> None:
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    # -- helpers -----------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Execute a request with automatic 429 back-off retry."""
        backoff = _INITIAL_BACKOFF
        for attempt in range(1, _MAX_RETRIES + 1):
            response = await self._client.request(
                method, path, data=data, params=params
            )

            if response.status_code == 429:
                logger.warning(
                    "Rate-limited by Real-Debrid (attempt %d/%d), "
                    "retrying in %.1fs",
                    attempt,
                    _MAX_RETRIES,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code >= 400:
                body = response.text
                raise RealDebridError(
                    f"Real-Debrid API error {response.status_code}: {body}",
                    status_code=response.status_code,
                )

            # Some endpoints return empty bodies (204, etc.)
            if not response.content:
                return {}
            return response.json()

        raise RealDebridError("Exceeded max retries due to rate limiting")

    # -- public API --------------------------------------------------------

    async def check_auth(self) -> dict:
        """GET /user -- verify the token is valid."""
        return await self._request("GET", "/user")

    async def add_magnet(self, magnet: str) -> str:
        """POST /torrents/addMagnet -- returns the torrent ID."""
        result = await self._request("POST", "/torrents/addMagnet", data={"magnet": magnet})
        torrent_id: str = result["id"]
        logger.info("Added magnet, torrent_id=%s", torrent_id)
        return torrent_id

    async def select_files(self, torrent_id: str, file_ids: str = "all") -> None:
        """POST /torrents/selectFiles/{id} -- select which files to download."""
        await self._request(
            "POST",
            f"/torrents/selectFiles/{torrent_id}",
            data={"files": file_ids},
        )
        logger.info("Selected files for torrent %s: %s", torrent_id, file_ids)

    async def get_torrent_info(self, torrent_id: str) -> dict:
        """GET /torrents/info/{id} -- return full torrent info."""
        return await self._request("GET", f"/torrents/info/{torrent_id}")

    async def poll_until_ready(
        self, torrent_id: str, timeout: int = 600
    ) -> dict:
        """Poll get_torrent_info until status == 'downloaded'.

        Parameters
        ----------
        torrent_id:
            The Real-Debrid torrent identifier.
        timeout:
            Maximum seconds to wait before raising.

        Returns
        -------
        The final torrent info dict.
        """
        elapsed = 0.0
        interval = 5.0
        while elapsed < timeout:
            info = await self.get_torrent_info(torrent_id)
            status = info.get("status", "")
            logger.debug(
                "Torrent %s status=%s (%.0fs elapsed)", torrent_id, status, elapsed
            )

            if status == "downloaded":
                return info

            if status in ("magnet_error", "error", "virus", "dead"):
                raise RealDebridError(
                    f"Torrent {torrent_id} entered terminal state: {status}"
                )

            await asyncio.sleep(interval)
            elapsed += interval

        raise RealDebridError(
            f"Timed out waiting for torrent {torrent_id} after {timeout}s"
        )

    async def unrestrict_link(self, link: str) -> str:
        """POST /unrestrict/link -- return the unrestricted download URL."""
        result = await self._request("POST", "/unrestrict/link", data={"link": link})
        download_url: str = result["download"]
        logger.info("Unrestricted link -> %s", download_url[:80])
        return download_url

    async def download_file(
        self,
        url: str,
        dest_path: Path,
        on_progress: Callable[[int, int], Any] | None = None,
    ) -> None:
        """Stream-download a file from the given URL to a local path.

        Parameters
        ----------
        on_progress:
            Optional callback(downloaded_bytes, total_bytes) called every ~256KB.
            May be sync or async.
        """
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading %s -> %s", url[:80], dest_path)

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as dl:
            async with dl.stream("GET", url) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(dest_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 256):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_progress and total > 0:
                            result = on_progress(downloaded, total)
                            if asyncio.iscoroutine(result):
                                await result

        logger.info("Download complete: %s", dest_path)

    # -- lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "RealDebridClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
