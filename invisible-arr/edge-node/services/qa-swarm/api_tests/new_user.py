"""New User persona: basic request-and-check flows."""
from __future__ import annotations

import asyncio

from conftest import APIClient, QAConfig
from runner import BasePersona, register_persona


@register_persona("new_user")
class NewUserPersona(BasePersona):
    name = "new_user"

    async def run_all(self):
        await self.run_scenario("request_movie", self._request_movie)
        await self.run_scenario("request_tv_show", self._request_tv_show)
        await self.run_scenario("check_library", self._check_library)
        await self.run_scenario("check_quota", self._check_quota)
        return self.results

    async def _request_movie(self):
        """Request a popular movie and verify pipeline starts."""
        resp = await self.client.post("/v1/request", json={
            "query": "The Shawshank Redemption",
            "media_type": "movie",
            "tmdb_id": 278,
        })
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "id" in data, f"Response missing job ID: {data}"
        job_id = data["id"]
        cid = self.client.get_correlation_id(resp)

        if self.config.mode == "dry-run":
            # Just verify job was created with correct initial state
            await asyncio.sleep(2)
            status_resp = await self.client.get(f"/v1/jobs/{job_id}")
            assert status_resp.status_code == 200
            job = status_resp.json()
            # Any non-terminal state means the pipeline started correctly
            non_terminal = {"CREATED", "REQUESTED", "RESOLVING", "SEARCHING",
                           "SELECTED", "DOWNLOADING", "IMPORTING", "WAITING",
                           "ACQUIRING", "VERIFYING", "ADDING"}
            assert job["state"] in non_terminal, \
                f"Unexpected state: {job['state']}"
        elif self.config.mode in ("mock", "full"):
            # Poll until terminal state (max 5 min)
            for _ in range(60):
                await asyncio.sleep(5)
                status_resp = await self.client.get(f"/v1/jobs/{job_id}")
                job = status_resp.json()
                if job["state"] in ("AVAILABLE", "FAILED", "DELETED"):
                    break
            assert job["state"] == "AVAILABLE", f"Job did not complete: {job['state']}"

        return [cid] if cid else []

    async def _request_tv_show(self):
        """Request a TV show and verify pipeline starts."""
        resp = await self.client.post("/v1/request", json={
            "query": "Breaking Bad",
            "media_type": "tv",
            "tmdb_id": 1396,
        })
        # 201 = created, 429 = rate limited (acceptable if previous requests used quota)
        assert resp.status_code in (201, 429), f"Expected 201/429, got {resp.status_code}: {resp.text}"
        if resp.status_code == 429:
            return []  # Rate limited is valid behavior
        data = resp.json()
        assert "id" in data
        cid = self.client.get_correlation_id(resp)

        if self.config.mode == "dry-run":
            await asyncio.sleep(2)
            status_resp = await self.client.get(f"/v1/jobs/{data['id']}")
            assert status_resp.status_code == 200
            job = status_resp.json()
            non_terminal = {"CREATED", "REQUESTED", "RESOLVING", "SEARCHING",
                           "SELECTED", "DOWNLOADING", "IMPORTING", "WAITING",
                           "ACQUIRING", "VERIFYING", "ADDING"}
            assert job["state"] in non_terminal, \
                f"Unexpected state: {job['state']}"

        return [cid] if cid else []

    async def _check_library(self):
        """Verify library endpoint returns valid data."""
        resp = await self.client.get("/v1/library")
        assert resp.status_code == 200, f"Library returned {resp.status_code}"
        data = resp.json()
        assert isinstance(data, (list, dict)), f"Unexpected library format: {type(data)}"
        return [self.client.get_correlation_id(resp)]

    async def _check_quota(self):
        """Verify quota endpoint returns valid counts."""
        resp = await self.client.get("/v1/library/quota")
        assert resp.status_code == 200, f"Quota returned {resp.status_code}"
        data = resp.json()
        assert "movie_count" in data, f"Missing movie_count: {data}"
        assert "movie_quota" in data, f"Missing movie_quota: {data}"
        return [self.client.get_correlation_id(resp)]
