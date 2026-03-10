"""Shared fixtures for QA swarm: API client, test user management, mode flags."""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field

import httpx


@dataclass
class QAConfig:
    """Runtime configuration parsed from env + CLI args."""
    api_base: str = os.getenv("API_BASE_URL", "http://agent-api:8880")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://automedia-frontend:80")
    iptv_base: str = os.getenv("IPTV_BASE_URL", "http://iptv-gateway:8881")
    db_url: str = os.getenv("DATABASE_URL", "")
    prometheus_url: str = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_repo: str = os.getenv("GITHUB_REPO", "")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
    mode: str = "dry-run"  # dry-run | mock | full
    persona: str | None = None  # None = all


@dataclass
class ScenarioResult:
    """Result of a single test scenario."""
    persona: str
    scenario_name: str
    status: str  # pass, fail, error, skip
    duration_ms: int = 0
    error_message: str | None = None
    correlation_ids: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)

    @property
    def error_fingerprint(self) -> str | None:
        if not self.error_message:
            return None
        raw = f"{self.persona}:{self.scenario_name}:{self.error_message[:200]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class APIClient:
    """HTTP client for the agent-api."""

    def __init__(self, config: QAConfig, api_key: str | None = None):
        self.config = config
        self.api_key = api_key or config.admin_api_key
        self._client = httpx.AsyncClient(
            base_url=config.api_base,
            headers={"X-Api-Key": self.api_key},
            timeout=30.0,
        )

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.get(path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.post(path, **kwargs)

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.delete(path, **kwargs)

    def get_correlation_id(self, response: httpx.Response) -> str | None:
        return response.headers.get("x-correlation-id")

    async def close(self):
        await self._client.aclose()


async def create_test_user(client: APIClient, run_id: str) -> dict:
    """Create a test user via admin API. Returns {email, api_key, id}."""
    email = f"qa-{run_id[:8]}@test.cutdacord.app"
    resp = await client.post("/v1/admin/users", json={
        "email": email,
        "name": f"QA Test {run_id[:8]}",
        "role": "user",
        "is_active": True,
    })
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to create test user: {resp.status_code} {resp.text}")
    data = resp.json()
    return {"email": email, "api_key": data["api_key"], "id": data["id"]}


async def cleanup_test_user(client: APIClient, user_id: str) -> None:
    """Deactivate test user and clean up their data."""
    # Deactivate user
    await client.post(f"/v1/admin/users/{user_id}/deactivate")
    # Delete any jobs created by this user
    await client.delete(f"/v1/admin/users/{user_id}/jobs")
