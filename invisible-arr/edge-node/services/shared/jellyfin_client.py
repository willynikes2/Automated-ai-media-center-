"""Jellyfin admin API helper — per-user library provisioning."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

import httpx

from shared.config import get_config

logger = logging.getLogger("shared.jellyfin_client")


class JellyfinAdmin:
    """Thin wrapper around the Jellyfin admin API for user/library management."""

    def __init__(self) -> None:
        config = get_config()
        self._base = config.jellyfin_url.rstrip("/")
        self._token = config.jellyfin_admin_token
        self._media_path = config.media_path

    @property
    def enabled(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {
            "X-Emby-Token": self._token,
            "Content-Type": "application/json",
        }

    async def get_virtual_folders(self) -> list[dict]:
        """Return all Jellyfin virtual folder (library) definitions."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base}/Library/VirtualFolders",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def create_library(
        self, name: str, collection_type: str, path: str
    ) -> str | None:
        """Create a Jellyfin virtual folder. Returns the ItemId or None."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base}/Library/VirtualFolders",
                params={
                    "name": name,
                    "collectionType": collection_type,
                    "refreshLibrary": "false",
                    "paths": path,
                },
                headers=self._headers(),
                json={},
            )
            if resp.status_code >= 400:
                logger.warning(
                    "Failed to create Jellyfin library %s: %s",
                    name,
                    resp.text[:200],
                )
                return None

        # Fetch folders to find the new library's ItemId
        folders = await self.get_virtual_folders()
        for f in folders:
            if f["Name"] == name:
                return f["ItemId"]
        return None

    async def get_user_policy(self, jellyfin_user_id: str) -> dict | None:
        """Get a Jellyfin user's full policy object."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base}/Users/{jellyfin_user_id}",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return None
            return resp.json().get("Policy")

    async def set_user_library_access(
        self, jellyfin_user_id: str, folder_ids: list[str]
    ) -> bool:
        """Restrict a Jellyfin user to specific library folders."""
        policy = await self.get_user_policy(jellyfin_user_id)
        if policy is None:
            return False

        policy["EnableAllFolders"] = False
        policy["EnabledFolders"] = folder_ids

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._base}/Users/{jellyfin_user_id}/Policy",
                headers=self._headers(),
                json=policy,
            )
            return resp.status_code < 400

    async def set_user_audio_defaults(self, jellyfin_user_id: str) -> bool:
        """Set English audio/subtitle preference for a Jellyfin user."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base}/Users/{jellyfin_user_id}",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return False
            user_config = resp.json().get("Configuration", {})

        user_config["AudioLanguagePreference"] = "eng"
        user_config["SubtitleLanguagePreference"] = "eng"
        user_config["SubtitleMode"] = "Default"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._base}/Users/{jellyfin_user_id}/Configuration",
                headers=self._headers(),
                json=user_config,
            )
            if resp.status_code < 400:
                logger.info("Set English audio defaults for Jellyfin user %s", jellyfin_user_id)
                return True
            return False

    async def refresh_library(self) -> None:
        """Trigger a Jellyfin library scan."""
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self._base}/Library/Refresh",
                headers=self._headers(),
            )

    async def provision_user_libraries(
        self, user_id: str, username: str, jellyfin_user_id: str
    ) -> bool:
        """Create per-user Jellyfin libraries and restrict access.

        Creates "{username} Movies" and "{username} TV" libraries pointing
        at the user's per-user media directories, then restricts the
        Jellyfin user to only see those libraries.

        Returns True if provisioning succeeded.
        """
        if not self.enabled:
            logger.debug("Jellyfin admin token not set, skipping library provisioning")
            return False

        user_media = Path(self._media_path) / "users" / user_id
        movies_path = str(user_media / "Movies")
        tv_path = str(user_media / "TV")

        # Check if libraries already exist for this user
        existing = await self.get_virtual_folders()
        existing_names = {f["Name"] for f in existing}

        movies_name = f"{username} Movies"
        tv_name = f"{username} TV"

        folder_ids: list[str] = []

        # Create or find Movies library
        if movies_name in existing_names:
            for f in existing:
                if f["Name"] == movies_name:
                    folder_ids.append(f["ItemId"])
                    break
        else:
            mid = await self.create_library(movies_name, "movies", movies_path)
            if mid:
                folder_ids.append(mid)
                logger.info("Created Jellyfin library: %s", movies_name)

        # Create or find TV library
        if tv_name in existing_names:
            for f in existing:
                if f["Name"] == tv_name:
                    folder_ids.append(f["ItemId"])
                    break
        else:
            tid = await self.create_library(tv_name, "tvshows", tv_path)
            if tid:
                folder_ids.append(tid)
                logger.info("Created Jellyfin library: %s", tv_name)

        if not folder_ids:
            logger.warning("No libraries created for user %s", username)
            return False

        # Restrict Jellyfin user to their libraries
        ok = await self.set_user_library_access(jellyfin_user_id, folder_ids)
        if ok:
            logger.info(
                "Provisioned Jellyfin libraries for %s: %s",
                username,
                folder_ids,
            )
        else:
            logger.warning("Failed to set library access for %s", username)

        # Set English audio/subtitle defaults
        await self.set_user_audio_defaults(jellyfin_user_id)

        return ok

    async def get_user_items_resume(self, user_id: str, limit: int = 12) -> list[dict]:
        """Get resumable/in-progress items for a user."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base}/Users/{user_id}/Items/Resume",
                params={"Limit": limit, "Fields": "Overview,Genres,OfficialRating,CommunityRating"},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return []
            return resp.json().get("Items", [])

    async def get_user_items_latest(self, user_id: str, limit: int = 16) -> list[dict]:
        """Get latest added items for a user."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base}/Users/{user_id}/Items/Latest",
                params={"Limit": limit, "Fields": "Overview,Genres,OfficialRating,CommunityRating"},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return []
            return resp.json() if isinstance(resp.json(), list) else []

    async def get_user_items_played(self, user_id: str, limit: int = 20) -> list[dict]:
        """Get recently played items sorted by DatePlayed."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base}/Users/{user_id}/Items",
                params={
                    "SortBy": "DatePlayed",
                    "SortOrder": "Descending",
                    "Filters": "IsPlayed",
                    "Recursive": "true",
                    "Limit": limit,
                    "IncludeItemTypes": "Movie,Series,Episode",
                    "Fields": "Overview,Genres,OfficialRating,CommunityRating,SeriesName",
                },
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return []
            return resp.json().get("Items", [])

    async def get_similar_items(self, item_id: str, user_id: str, limit: int = 12) -> list[dict]:
        """Get similar items from Jellyfin's built-in recommendation engine."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base}/Items/{item_id}/Similar",
                params={"UserId": user_id, "Limit": limit, "Fields": "PrimaryImageAspectRatio"},
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return []
            return resp.json().get("Items", [])
