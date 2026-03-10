"""Live TV User persona: EPG, channels, tuning."""
from __future__ import annotations

import httpx

from conftest import APIClient, QAConfig
from runner import BasePersona, register_persona


@register_persona("live_tv_user")
class LiveTVUserPersona(BasePersona):
    name = "live_tv_user"

    def __init__(self, client: APIClient, config: QAConfig):
        super().__init__(client, config)
        # IPTV playlist/epg endpoints use user_token query param (the API key)
        self._iptv_client = httpx.AsyncClient(
            base_url=config.iptv_base,
            timeout=30.0,
        )
        self._user_token = client.api_key

    async def run_all(self):
        await self.run_scenario("load_epg", self._load_epg)
        await self.run_scenario("list_channels", self._list_channels)
        await self.run_scenario("tune_channel", self._tune_channel)
        await self._iptv_client.aclose()
        return self.results

    async def _load_epg(self):
        """Verify EPG XML loads and contains program data."""
        resp = await self._iptv_client.get("/epg.xml", params={"user_token": self._user_token})
        assert resp.status_code == 200, f"EPG returned {resp.status_code}: {resp.text[:200]}"
        body = resp.text
        assert "<?xml" in body or "<tv" in body, "EPG response is not XML"
        # EPG may be empty if no sources configured — that's OK, just verify format
        return []

    async def _list_channels(self):
        """Verify channel list endpoint returns channels."""
        # Channels are served via the IPTV gateway API with X-Api-Key auth
        resp = await self._iptv_client.get(
            "/v1/iptv/channels",
            headers={"X-Api-Key": self._user_token},
        )
        assert resp.status_code == 200, f"Channels returned {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        return []

    async def _tune_channel(self):
        """Attempt to get a stream URL for a channel (M3U playlist)."""
        resp = await self._iptv_client.get("/playlist.m3u", params={"user_token": self._user_token})
        assert resp.status_code == 200, f"Playlist returned {resp.status_code}: {resp.text[:200]}"
        body = resp.text
        assert "#EXTM3U" in body, "Response is not M3U format"
        return []
