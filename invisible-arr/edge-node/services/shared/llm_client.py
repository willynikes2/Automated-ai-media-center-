"""Thin async LLM client supporting OpenAI and Anthropic via raw HTTP.

No SDK dependencies — uses httpx (already in the stack).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from shared.config import get_config

logger = logging.getLogger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20241001",
}


class LLMClient:
    """Async LLM client that dispatches to OpenAI or Anthropic based on config."""

    def __init__(self) -> None:
        config = get_config()
        self._provider = config.llm_provider.lower()
        self._api_key = config.llm_api_key
        self._model = config.llm_model or _DEFAULT_MODELS.get(self._provider, "")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    @property
    def enabled(self) -> bool:
        return self._provider in ("openai", "anthropic") and bool(self._api_key)

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Send a prompt and parse the response as JSON."""
        if self._provider == "openai":
            return await self._openai_call(system_prompt, user_prompt, max_tokens)
        elif self._provider == "anthropic":
            return await self._anthropic_call(system_prompt, user_prompt, max_tokens)
        else:
            raise RuntimeError(f"LLM provider '{self._provider}' not supported")

    async def _openai_call(
        self, system: str, user: str, max_tokens: int
    ) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = await self._client.post(
            _OPENAI_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return json.loads(text)

    async def _anthropic_call(
        self, system: str, user: str, max_tokens: int
    ) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        resp = await self._client.post(
            _ANTHROPIC_URL,
            json=payload,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
