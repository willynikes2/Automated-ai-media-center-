"""Webhook receiver for Sonarr / Radarr callbacks."""

from __future__ import annotations

import json
import logging
import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import select

from shared.config import get_config
from shared.database import get_session_factory
from shared.models import Job, JobEvent, JobState
from shared.radarr_client import RadarrClient
from shared.redis_client import set_rdt_ready
from shared.sonarr_client import SonarrClient

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
    try:
        job_uuid = _uuid.UUID(job_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"Invalid job_id: {job_id_str}")

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Job).where(Job.id == job_uuid)
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


@router.post("/webhooks/rdt-complete", status_code=200)
async def receive_rdt_complete(
    payload: dict[str, Any],
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
    token: str | None = Query(default=None),
) -> dict[str, Any]:
    """Event hook for RDT completion: trigger immediate Arr import scans.

    Expected payload keys:
    - category: "sonarr" | "radarr"
    - content_path: absolute path to downloaded content folder
    - info_hash: torrent hash (optional but recommended)
    - job_id: optional Invisible Arr job UUID
    """
    config = get_config()
    expected = config.rdt_webhook_token.strip()
    provided = (x_webhook_token or token or "").strip()
    if expected and provided != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    category = str(
        payload.get("category")
        or payload.get("label")
        or payload.get("client")
        or ""
    ).strip().lower()
    content_path = str(
        payload.get("content_path")
        or payload.get("contentPath")
        or payload.get("path")
        or payload.get("save_path")
        or ""
    ).strip()
    info_hash = str(
        payload.get("info_hash")
        or payload.get("infoHash")
        or payload.get("download_client_id")
        or payload.get("downloadClientId")
        or ""
    ).strip()
    job_id = payload.get("job_id")

    if not category or not content_path:
        raise HTTPException(
            status_code=422,
            detail="category and content_path are required",
        )

    logger.info(
        "RDT completion webhook received: category=%s path=%s hash=%s",
        category,
        content_path,
        info_hash[:12] if info_hash else "",
    )

    command_response: dict[str, Any]
    if "sonarr" in category:
        async with SonarrClient() as sonarr:
            command_response = await sonarr.trigger_downloaded_episodes_scan(
                path=content_path,
                download_client_id=info_hash or None,
            )
    elif "radarr" in category:
        async with RadarrClient() as radarr:
            command_response = await radarr.trigger_downloaded_movies_scan(
                path=content_path,
                download_client_id=info_hash or None,
            )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported category '{category}'. Use sonarr or radarr.",
        )

    resolved_job: Job | None = None
    # Resolve job by explicit job_id if provided.
    if job_id:
        try:
            job_uuid = _uuid.UUID(str(job_id))
        except (ValueError, AttributeError):
            job_uuid = None
        if job_uuid:
            async with get_session_factory()() as session:
                result = await session.execute(
                    select(Job).where(Job.id == job_uuid)
                )
            resolved_job = result.scalar_one_or_none()
    # Fallback: map by tracked download hash/id captured from Arr queue.
    elif info_hash:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(Job)
                .where(Job.rd_torrent_id == info_hash)
                .where(Job.state.in_([JobState.ACQUIRING.value, JobState.IMPORTING.value]))
                .order_by(Job.updated_at.desc())
                .limit(1)
            )
            resolved_job = result.scalar_one_or_none()

    if resolved_job is not None:
        await set_rdt_ready(str(resolved_job.id), payload=json.dumps({
            "category": category,
            "content_path": content_path,
            "info_hash": info_hash,
        }))

    # If job_id is supplied, log this as a job event.
    if resolved_job is not None:
        async with get_session_factory()() as session:
            event = JobEvent(
                job_id=resolved_job.id,
                state="rdt_webhook:completed",
                message=f"RDT completion received for {category}",
                metadata_json={
                    "category": category,
                    "content_path": content_path,
                    "info_hash": info_hash,
                    "arr_command": command_response,
                },
            )
            session.add(event)
            await session.commit()

    return {
        "status": "accepted",
        "category": category,
        "content_path": content_path,
        "info_hash": info_hash,
        "job_id": str(resolved_job.id) if resolved_job is not None else None,
        "arr_command": command_response,
    }
