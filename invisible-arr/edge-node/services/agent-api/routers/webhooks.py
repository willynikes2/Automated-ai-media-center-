"""Webhook receiver for Sonarr / Radarr callbacks."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from shared.database import get_session_factory
from shared.models import Job, JobEvent

logger = logging.getLogger("agent-api.webhooks")
router = APIRouter()


def _extract_job_id(payload: dict[str, Any]) -> str | None:
    """Try to find a job_id reference in the webhook payload.

    Sonarr/Radarr payloads don't natively include our job_id, so we check
    several common locations where it might be injected via custom tags or
    environment variables set during the grab/import flow.
    """
    # Direct field
    if "job_id" in payload:
        return str(payload["job_id"])

    # Nested inside customFormatInfo or extra metadata
    for key in ("customFormatInfo", "extra", "metadata"):
        nested = payload.get(key)
        if isinstance(nested, dict) and "job_id" in nested:
            return str(nested["job_id"])

    # Check environment variables section (Radarr v4+)
    env_vars = payload.get("environmentVariables")
    if isinstance(env_vars, dict) and "job_id" in env_vars:
        return str(env_vars["job_id"])

    return None


@router.post("/webhooks/arr", status_code=200)
async def receive_arr_webhook(payload: dict[str, Any]) -> dict[str, str]:
    """Ingest a Sonarr / Radarr webhook and log it as a job event."""

    event_type: str = payload.get("eventType", "unknown")
    logger.info(
        "Received arr webhook: eventType=%s, keys=%s",
        event_type,
        list(payload.keys()),
    )

    job_id_str = _extract_job_id(payload)

    if job_id_str is None:
        logger.warning("No job_id found in webhook payload; acknowledging without logging event")
        return {"status": "accepted", "detail": "no matching job_id found"}

    # Verify the job exists before writing the event.
    async with get_session_factory()() as session:
        result = await session.execute(
            select(Job).where(Job.id == job_id_str)
        )
        job: Job | None = result.scalar_one_or_none()

        if job is None:
            logger.warning("Webhook referenced job_id=%s but no such job exists", job_id_str)
            raise HTTPException(status_code=404, detail=f"Job {job_id_str} not found")

        # Limit payload size to prevent oversized metadata storage
        payload_str = json.dumps(payload)
        limited_payload = json.loads(payload_str[:50_000]) if len(payload_str) > 50_000 else payload

        event = JobEvent(
            job_id=job.id,
            state=f"arr_webhook:{event_type}",
            message=f"Received {event_type} webhook",
            metadata_json=limited_payload,
        )
        session.add(event)
        await session.commit()
        logger.info("Logged webhook event for job_id=%s state=%s", job.id, event.state)

    return {"status": "accepted", "job_id": job_id_str}
