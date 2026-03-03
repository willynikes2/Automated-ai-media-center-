"""Async qBittorrent Web API client for VPN torrent fallback."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class QBittorrentError(Exception):
    """Raised for qBittorrent API errors."""


class QBittorrentClient:
    """Async wrapper around the qBittorrent Web API.

    Assumes qBittorrent runs behind Gluetun VPN container.
    """

    def __init__(self, base_url: str, username: str = "admin", password: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        self._authenticated = False

    async def _login(self) -> None:
        """Authenticate with the qBittorrent Web API."""
        if self._authenticated:
            return
        resp = await self._client.post("/api/v2/auth/login", data={
            "username": self._username,
            "password": self._password,
        })
        if resp.status_code != 200 or resp.text.strip().upper() != "OK.":
            raise QBittorrentError(f"Login failed: {resp.status_code} {resp.text}")
        self._authenticated = True
        logger.info("qBittorrent authenticated")

    async def add_magnet(self, magnet: str, save_path: str, category: str = "automedia") -> None:
        """Add a magnet link for download."""
        await self._login()
        resp = await self._client.post("/api/v2/torrents/add", data={
            "urls": magnet,
            "savepath": save_path,
            "category": category,
        })
        if resp.status_code != 200:
            raise QBittorrentError(f"Add torrent failed: {resp.status_code} {resp.text}")
        logger.info("Added magnet to qBittorrent, save_path=%s", save_path)

    async def get_torrent_info(self, info_hash: str) -> dict | None:
        """Get torrent info by hash. Returns None if not found."""
        await self._login()
        resp = await self._client.get("/api/v2/torrents/info", params={
            "hashes": info_hash.lower(),
        })
        resp.raise_for_status()
        torrents = resp.json()
        return torrents[0] if torrents else None

    async def poll_until_complete(
        self, info_hash: str, timeout: int = 3600, interval: int = 10
    ) -> dict:
        """Poll until torrent reaches 100% or times out."""
        elapsed = 0
        while elapsed < timeout:
            info = await self.get_torrent_info(info_hash)
            if info is None:
                raise QBittorrentError(f"Torrent {info_hash} not found in qBittorrent")

            progress = info.get("progress", 0)
            state = info.get("state", "unknown")
            logger.debug("Torrent %s: %.1f%% state=%s", info_hash[:8], progress * 100, state)

            if progress >= 1.0:
                return info

            if state in ("error", "missingFiles"):
                raise QBittorrentError(f"Torrent entered error state: {state}")

            await asyncio.sleep(interval)
            elapsed += interval

        raise QBittorrentError(f"Torrent {info_hash} timed out after {timeout}s")

    async def delete_torrent(self, info_hash: str, delete_files: bool = False) -> None:
        """Remove a torrent from qBittorrent."""
        await self._login()
        resp = await self._client.post("/api/v2/torrents/delete", data={
            "hashes": info_hash.lower(),
            "deleteFiles": str(delete_files).lower(),
        })
        if resp.status_code != 200:
            logger.warning("Failed to delete torrent %s: %s", info_hash, resp.text)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "QBittorrentClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
