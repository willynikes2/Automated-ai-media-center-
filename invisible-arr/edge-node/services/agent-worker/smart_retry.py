"""AI-powered smart retry analysis for failed media acquisition jobs.

Adapted for the Sonarr/Radarr orchestration pipeline. When a download fails,
this module analyzes Arr queue errors and job event history via an LLM, then
produces a RetryStrategy — concrete actions for the next attempt (blacklist
the release, trigger re-search, suggest quality profile changes).

Falls back gracefully to dumb retry when LLM is disabled or unavailable.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from shared.config import get_config
from shared.database import get_session_factory
from shared.llm_client import LLMClient
from shared.models import Job, JobEvent
from shared.tmdb_client import TMDBClient

logger = logging.getLogger("agent-worker.smart_retry")


# ---------------------------------------------------------------------------
# Strategy dataclass
# ---------------------------------------------------------------------------


@dataclass
class RetryStrategy:
    """Concrete action plan produced by the LLM for a retry attempt."""

    blacklist_queue_item: bool = True
    trigger_re_search: bool = True
    suggest_quality_change: str | None = None  # e.g. "lower to 720p", "try Any profile"
    reasoning: str = ""


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a media acquisition retry strategist for an automated download system.

The system uses Sonarr/Radarr to search, select, and download media. Downloads
go through rdt-client (Real-Debrid proxy), SABnzbd (Usenet), or qBittorrent.

When a download fails, you analyze the Arr queue errors and job event history,
then produce a strategy for the next attempt.

Common failure patterns and fixes:
- "Download failed" in Arr queue → Blacklist the release, trigger re-search
- "Import failed" → Check if file is corrupted, retry with different release
- "No indexers returned results" → Quality profile may be too restrictive
- "Stalled download" → Blacklist + re-search with different release
- "Timeout" → Download was too slow, try different release
- Repeated failures → Suggest lowering quality requirements

You MUST respond with ONLY a JSON object:
{
  "blacklist_queue_item": true,
  "trigger_re_search": true,
  "suggest_quality_change": null,
  "reasoning": "Brief explanation"
}

Rules:
- blacklist_queue_item: Almost always true — prevents re-grabbing the same bad release
- trigger_re_search: Usually true — tells Arr to search for a new release
- suggest_quality_change: Only suggest if repeated failures indicate quality profile is too strict
  Values: "lower to 720p", "allow any quality", or null
- Be conservative. The Arr stack handles most decisions — we just need to nudge it."""


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


async def _build_failure_context(job_id: str) -> dict[str, Any]:
    """Gather all relevant context about a failed job for the LLM."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        result = await session.execute(
            select(JobEvent)
            .where(JobEvent.job_id == job.id)
            .order_by(JobEvent.created_at)
        )
        events = list(result.scalars().all())

    # Build compact event timeline
    timeline = []
    for ev in events:
        entry: dict[str, Any] = {"state": ev.state, "message": ev.message[:300]}
        if ev.metadata_json and isinstance(ev.metadata_json, dict):
            if "error" in ev.metadata_json:
                entry["error"] = str(ev.metadata_json["error"])[:200]
            if "arr_status" in ev.metadata_json:
                entry["arr_status"] = ev.metadata_json["arr_status"]
        timeline.append(entry)

    return {
        "job_id": str(job.id),
        "media_type": job.media_type,
        "canonical_title": job.title or "",
        "tmdb_id": job.tmdb_id,
        "retry_count": job.retry_count,
        "acquisition_method": job.acquisition_method,
        "arr_queue_id": job.arr_queue_id,
        "timeline": timeline[-20:],
    }


# ---------------------------------------------------------------------------
# Strategy parser
# ---------------------------------------------------------------------------


def _parse_strategy(raw: dict[str, Any]) -> RetryStrategy:
    """Validate and sanitize LLM output into a RetryStrategy."""
    strategy = RetryStrategy()
    strategy.blacklist_queue_item = bool(raw.get("blacklist_queue_item", True))
    strategy.trigger_re_search = bool(raw.get("trigger_re_search", True))

    quality_change = raw.get("suggest_quality_change")
    if quality_change and isinstance(quality_change, str):
        strategy.suggest_quality_change = quality_change[:100]

    strategy.reasoning = str(raw.get("reasoning", ""))[:500]
    return strategy


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def analyze_failure(job_id: str) -> RetryStrategy | None:
    """Analyze a failed job and produce a smart retry strategy.

    Returns None if LLM is disabled or analysis fails (caller falls back
    to dumb retry with default blacklist + re-search).
    """
    llm = LLMClient()
    if not llm.enabled:
        await llm.close()
        return None

    try:
        context = await _build_failure_context(job_id)
    except Exception:
        logger.exception("Failed to build failure context for job %s", job_id)
        await llm.close()
        return None

    user_prompt = json.dumps(context, indent=2, default=str)

    try:
        async with llm:
            raw = await llm.complete_json(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=256,
            )
        strategy = _parse_strategy(raw)

        logger.info(
            "Smart retry strategy for job %s: %s (blacklist=%s, re_search=%s, quality=%s)",
            job_id,
            strategy.reasoning[:100],
            strategy.blacklist_queue_item,
            strategy.trigger_re_search,
            strategy.suggest_quality_change,
        )
        return strategy

    except Exception:
        logger.exception(
            "LLM analysis failed for job %s, falling back to dumb retry", job_id
        )
        return None
