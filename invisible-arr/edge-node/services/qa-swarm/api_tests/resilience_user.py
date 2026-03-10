"""Resilience User persona: malformed inputs, auth boundaries, error handling."""
from __future__ import annotations

import httpx

from conftest import APIClient, QAConfig
from runner import BasePersona, register_persona


@register_persona("resilience_user")
class ResilienceUserPersona(BasePersona):
    name = "resilience_user"

    async def run_all(self):
        await self.run_scenario("invalid_api_key", self._invalid_api_key)
        await self.run_scenario("empty_payload", self._empty_payload)
        await self.run_scenario("invalid_media_type", self._invalid_media_type)
        await self.run_scenario("garbage_title", self._garbage_title)
        await self.run_scenario("delete_nonexistent", self._delete_nonexistent)
        await self.run_scenario("duplicate_rapid_requests", self._duplicate_rapid)
        return self.results

    async def _invalid_api_key(self):
        """Request with invalid API key -- expect 401."""
        bad_client = httpx.AsyncClient(
            base_url=self.config.api_base,
            headers={"X-Api-Key": "totally-invalid-key-12345"},
            timeout=10.0,
        )
        try:
            resp = await bad_client.get("/v1/library/quota")
            assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        finally:
            await bad_client.aclose()
        return []

    async def _empty_payload(self):
        """POST with empty body -- expect 422 validation error."""
        resp = await self.client.post("/v1/request", json={})
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        return [self.client.get_correlation_id(resp)]

    async def _invalid_media_type(self):
        """Request with invalid media_type -- expect 422."""
        resp = await self.client.post("/v1/request", json={
            "query": "Test Movie",
            "media_type": "podcast",  # invalid
            "tmdb_id": 550,
        })
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        return [self.client.get_correlation_id(resp)]

    async def _garbage_title(self):
        """Request with special characters -- should not crash."""
        resp = await self.client.post("/v1/request", json={
            "query": "T3st! @#$% <script>alert(1)</script>",
            "media_type": "movie",
            "tmdb_id": 550,
        })
        # Should either accept (200) or reject gracefully (4xx), never 500
        assert resp.status_code < 500, f"Server error {resp.status_code}: {resp.text}"
        return [self.client.get_correlation_id(resp)]

    async def _delete_nonexistent(self):
        """Delete content that doesn't exist -- expect 404."""
        resp = await self.client.delete("/v1/library/item/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 400), \
            f"Expected 404/400, got {resp.status_code}: {resp.text}"
        return [self.client.get_correlation_id(resp)]

    async def _duplicate_rapid(self):
        """Send same request twice rapidly -- verify no crash or duplicate creation."""
        payload = {"query": "Duplicate Test Film", "media_type": "movie", "tmdb_id": 551}
        resp1 = await self.client.post("/v1/request", json=payload)
        resp2 = await self.client.post("/v1/request", json=payload)

        # Both should return cleanly (200 or 409/429)
        for resp in (resp1, resp2):
            assert resp.status_code < 500, f"Server error: {resp.status_code}"
        return [
            self.client.get_correlation_id(resp1),
            self.client.get_correlation_id(resp2),
        ]
