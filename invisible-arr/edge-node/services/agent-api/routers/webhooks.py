"""Webhook receiver for Sonarr / Radarr callbacks."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import select

from shared.config import get_config
from shared.database import get_session_factory
from shared.models import Job, JobEvent, JobState, User
from shared.radarr_client import RadarrClient
from shared.redis_client import set_rdt_ready, clear_download_progress
from shared.sonarr_client import SonarrClient
from shared.media_utils import trigger_jellyfin_refresh, register_content
from shared.canonical import (
    add_user_content,
    check_canonical,
    create_user_symlink,
    increment_user_count,
    register_canonical,
)

logger = logging.getLogger("agent-api.webhooks")
router = APIRouter()

# Shared webhook secret — Arr webhook URLs should include ?token=<secret>
_WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def _verify_webhook_token(
    token: str | None,
    x_webhook_token: str | None = None,
) -> None:
    """Reject requests when WEBHOOK_SECRET is set but caller doesn't match."""
    if not _WEBHOOK_SECRET:
        return  # Not configured — allow (backwards compat during rollout)
    provided = (x_webhook_token or token or "").strip()
    if provided != _WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook token")


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
async def receive_arr_webhook(
    payload: dict[str, Any],
    token: str | None = Query(default=None),
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
) -> dict[str, str]:
    """Ingest a Sonarr / Radarr webhook and log it as a job event."""
    _verify_webhook_token(token, x_webhook_token)

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
    expected = (config.rdt_webhook_token or "").strip()
    provided = (x_webhook_token or token or "").strip()
    # Also accept the shared WEBHOOK_SECRET as fallback
    if expected and provided != expected and provided != _WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    if not expected and _WEBHOOK_SECRET and provided != _WEBHOOK_SECRET:
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
                .where(Job.state.in_([JobState.DOWNLOADING.value, JobState.IMPORTING.value]))
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


# ---------------------------------------------------------------------------
# Radarr / Sonarr-specific webhook endpoints (state-driving)
# ---------------------------------------------------------------------------

# Terminal states — webhooks should not match jobs in these states.
_TERMINAL_STATES = {JobState.AVAILABLE.value, JobState.DELETED.value}


def _limit_payload(payload: dict[str, Any], max_size: int = 50_000) -> dict[str, Any]:
    """Truncate a payload dict to *max_size* bytes of JSON for safe DB storage."""
    raw = json.dumps(payload)
    if len(raw) <= max_size:
        return payload
    return json.loads(raw[:max_size])


def _safe_quality_name(quality_obj) -> str:
    """Safely extract quality name from Arr webhook payload (may be str or nested dict)."""
    if quality_obj is None:
        return "?"
    if isinstance(quality_obj, str):
        return quality_obj
    if isinstance(quality_obj, dict):
        inner = quality_obj.get("quality", quality_obj)
        if isinstance(inner, dict):
            return inner.get("name", "?")
        return str(inner)
    return str(quality_obj)


def _webhook_event_message(event_type: str, payload: dict[str, Any]) -> str:
    """Build a concise, human-readable message from an Arr webhook."""
    if event_type == "Grab":
        release = payload.get("release", {})
        title = release.get("releaseTitle") or release.get("title") or "unknown"
        quality = _safe_quality_name(release.get("quality"))
        indexer = release.get("indexer", "?")
        return f"Grabbed: {title} [{quality}] from {indexer}"

    if event_type in ("Download", "DownloadFolderImported"):
        movie_file = payload.get("movieFile") or {}
        episode_file = payload.get("episodeFile") or {}
        path = movie_file.get("relativePath") or episode_file.get("relativePath") or "unknown"
        return f"Imported: {path}"

    if event_type == "DownloadFailed":
        reason = payload.get("message") or "unknown reason"
        return f"Download failed: {reason}"

    if event_type == "Health":
        return f"Health check: {payload.get('message', 'no details')}"

    return f"Webhook event: {event_type}"


async def _match_webhook_to_job(
    payload: dict[str, Any],
    source: str,
    session: Any,
) -> Job | None:
    """Find the most recent active job matching the webhook's Arr entity ID."""
    if source == "radarr":
        arr_id = payload.get("movie", {}).get("id")
        if arr_id is None:
            return None
        stmt = (
            select(Job)
            .where(Job.radarr_movie_id == int(arr_id))
            .where(Job.state.notin_(_TERMINAL_STATES))
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    elif source == "sonarr":
        arr_id = payload.get("series", {}).get("id")
        if arr_id is None:
            return None
        # Try episode-level matching first for more precise correlation
        episodes_payload = payload.get("episodes", [])
        ep_num = episodes_payload[0].get("episodeNumber") if episodes_payload else None
        season_num = episodes_payload[0].get("seasonNumber") if episodes_payload else None

        if ep_num is not None and season_num is not None:
            # Try to match a job for this specific episode
            ep_stmt = (
                select(Job)
                .where(Job.sonarr_series_id == int(arr_id))
                .where(Job.season == season_num)
                .where(Job.episode == ep_num)
                .where(Job.state.notin_(_TERMINAL_STATES))
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            result = await session.execute(ep_stmt)
            ep_match = result.scalar_one_or_none()
            if ep_match:
                return ep_match

        # Fall back to series-level matching
        stmt = (
            select(Job)
            .where(Job.sonarr_series_id == int(arr_id))
            .where(Job.state.notin_(_TERMINAL_STATES))
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    else:
        return None

    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _extract_source_badge(payload: dict[str, Any]) -> str:
    """Extract download source from Arr webhook payload."""
    client = (payload.get("downloadClient") or "").lower()
    if "rdt" in client or "debrid" in client:
        return "RD"
    elif "sab" in client or "nzb" in client or "usenet" in client:
        return "Usenet"
    else:
        return "Torrent"


async def _fulfill_sibling_jobs(
    primary_job: Job,
    source_file_path: str,
    rel_path: str,
    source: str,
    session: Any,
) -> None:
    """Find other users' active jobs for the same Arr entity and hardlink the file.

    When multiple users request the same movie/show, Radarr/Sonarr only has one
    entry. This function finds sibling jobs (same radarr_movie_id or
    sonarr_series_id, different user) and creates hardlinks so each user gets the
    file in their own library folder without extra disk usage.
    """
    if source == "radarr" and primary_job.radarr_movie_id is not None:
        arr_col = Job.radarr_movie_id
        arr_id = primary_job.radarr_movie_id
        media_subdir = "Movies"
    elif source == "sonarr" and primary_job.sonarr_series_id is not None:
        arr_col = Job.sonarr_series_id
        arr_id = primary_job.sonarr_series_id
        media_subdir = "TV"
    else:
        return

    # Find sibling jobs: same arr entity, different user, still active
    stmt = (
        select(Job)
        .where(arr_col == arr_id)
        .where(Job.user_id != primary_job.user_id)
        .where(Job.state.notin_(_TERMINAL_STATES))
    )
    result = await session.execute(stmt)
    siblings = result.scalars().all()

    if not siblings:
        return

    source_path = Path(source_file_path)
    if not source_path.exists():
        logger.warning("Source file not found for sibling hardlink: %s", source_file_path)
        return

    # We need user info to build destination paths
    sibling_user_ids = [s.user_id for s in siblings]
    user_stmt = select(User).where(User.id.in_(sibling_user_ids))
    user_result = await session.execute(user_stmt)
    users_by_id = {u.id: u for u in user_result.scalars().all()}

    for sibling in siblings:
        user = users_by_id.get(sibling.user_id)
        if not user:
            continue

        try:
            # Create symlink from sibling user's dir to canonical folder
            canonical_folder = str(source_path.parent)
            symlink_dest = create_user_symlink(
                canonical_folder, str(user.id), primary_job.media_type,
            )

            # Track in user_content
            try:
                canonical = await check_canonical(session, primary_job.tmdb_id, primary_job.media_type)
                if canonical:
                    await add_user_content(
                        session, str(user.id), canonical,
                        job_id=str(sibling.id), symlink_path=symlink_dest,
                    )
                    await increment_user_count(session, user.id, primary_job.media_type)
            except Exception:
                logger.warning("Failed to track user_content for sibling job %s", sibling.id, exc_info=True)

            # Mark sibling job as AVAILABLE
            sibling.imported_path = rel_path
            sibling.state = JobState.AVAILABLE.value
            event = JobEvent(
                job_id=sibling.id,
                state=f"webhook:{source}:Download",
                message=f"Symlinked from canonical library: {rel_path}",
            )
            session.add(event)
            logger.info("Sibling job %s → AVAILABLE (symlink from job %s)", sibling.id, primary_job.id)

            try:
                await clear_download_progress(str(sibling.id))
            except Exception:
                pass
        except OSError as exc:
            logger.error("Failed to symlink for sibling job %s: %s", sibling.id, exc)


async def _process_arr_webhook(
    payload: dict[str, Any],
    source: str,
) -> dict[str, str]:
    """Shared processor for Radarr/Sonarr webhooks that drives job state."""
    event_type: str = payload.get("eventType", "unknown")
    logger.info(
        "Received %s webhook: eventType=%s keys=%s",
        source,
        event_type,
        list(payload.keys()),
    )

    async with get_session_factory()() as session:
        job = await _match_webhook_to_job(payload, source, session)

        if job is None:
            logger.debug(
                "No active job matched %s webhook (eventType=%s)",
                source,
                event_type,
            )
            return {"status": "accepted", "detail": "no matching job"}

        # Log the webhook as a JobEvent regardless of transition.
        event = JobEvent(
            job_id=job.id,
            state=f"webhook:{source}:{event_type}",
            message=_webhook_event_message(event_type, payload),
            metadata_json=_limit_payload(payload),
        )
        session.add(event)

        # ── State transitions based on eventType ──

        if event_type == "Grab":
            source_badge = _extract_source_badge(payload)
            if job.state in (
                JobState.REQUESTED.value,
                JobState.SEARCHING.value,
                JobState.FAILED.value,  # retry grabs
            ):
                job.state = JobState.DOWNLOADING.value
                logger.info("Job %s → DOWNLOADING via %s Grab (%s)", job.id, source, source_badge)

            release = payload.get("release", {})
            if release:
                event.metadata_json = _limit_payload({
                    "release_title": release.get("releaseTitle") or release.get("title"),
                    "indexer": release.get("indexer"),
                    "quality": _safe_quality_name(release.get("quality")),
                    "size": release.get("size"),
                    "source": source_badge,
                    "full_payload": payload,
                })
            # Capture download ID for correlation
            download_id = payload.get("downloadId") or (release.get("downloadId") if release else None)
            if download_id and not job.rd_torrent_id:
                job.rd_torrent_id = str(download_id)
            # Capture queue ID if the release carries one.
            queue_id = release.get("downloadId") or release.get("id")
            if queue_id is not None:
                job.arr_queue_id = int(queue_id) if str(queue_id).isdigit() else job.arr_queue_id

        elif event_type in ("Download", "DownloadFolderImported"):
            file_info = payload.get("movieFile") or payload.get("episodeFile") or {}
            rel_path = file_info.get("relativePath") or file_info.get("path")
            if rel_path:
                job.imported_path = rel_path

            if job.state in (
                JobState.DOWNLOADING.value,
                JobState.IMPORTING.value,
                JobState.SEARCHING.value,
            ):
                # Transition directly to AVAILABLE — file is imported by Arr
                job.state = JobState.AVAILABLE.value
                logger.info("Job %s → AVAILABLE via %s %s", job.id, source, event_type)

                # Clear download progress tracking
                try:
                    await clear_download_progress(str(job.id))
                except Exception:
                    pass

                # Register content in the shared library for dedup
                full_file_path = file_info.get("path")
                if full_file_path:
                    try:
                        await register_content(session, job, full_file_path)
                    except Exception:
                        logger.error("Failed to register content for job %s", job.id, exc_info=True)

                    # Register in canonical library for cross-user dedup
                    try:
                        canonical_path = os.path.dirname(full_file_path)  # folder, not file
                        canonical = await register_canonical(
                            session, job.tmdb_id, job.media_type,
                            title=job.title,
                            canonical_path=canonical_path,
                            radarr_id=job.radarr_movie_id,
                            sonarr_id=job.sonarr_series_id,
                        )
                        # Track this user's reference
                        await add_user_content(
                            session, str(job.user_id), canonical,
                            job_id=str(job.id), symlink_path=str(Path(full_file_path).parent),
                        )
                        await increment_user_count(session, job.user_id, job.media_type)
                    except Exception:
                        logger.warning("Failed to register canonical content for job %s", job.id, exc_info=True)

                # Symlink/hardlink file to other users who requested the same content
                if full_file_path and rel_path:
                    try:
                        await _fulfill_sibling_jobs(job, full_file_path, rel_path, source, session)
                    except Exception:
                        logger.error("Failed to fulfill sibling jobs for %s", job.id, exc_info=True)

                # Trigger Jellyfin library refresh (best effort)
                await trigger_jellyfin_refresh()

            # Also signal RDT-ready for QC pipeline (if enabled)
            await set_rdt_ready(str(job.id), payload="webhook_import")

        elif event_type == "DownloadFailed":
            source_badge = _extract_source_badge(payload)
            failure_msg = payload.get("message") or "unknown reason"
            event.message = f"Download failed ({source_badge}): {failure_msg}"
            event.metadata_json = _limit_payload({
                "failed_source": source_badge.lower(),
                "failure_message": failure_msg,
                "full_payload": payload,
            })

            if job.state in (JobState.DOWNLOADING.value, JobState.SEARCHING.value):
                # Radarr/Sonarr will automatically try the next download client
                # by priority (rdt-client → SABnzbd → qBittorrent).
                # Set back to SEARCHING so the timeout checker can catch truly stuck jobs.
                job.state = JobState.SEARCHING.value
                logger.info(
                    "Job %s: %s download failed (%s), Radarr/Sonarr will try next client",
                    job.id, source_badge, failure_msg[:100],
                )

        elif event_type == "Health":
            logger.warning(
                "%s health event: %s",
                source,
                payload.get("message", "no details"),
            )

        await session.commit()
        logger.info(
            "Processed %s webhook for job %s (eventType=%s, state=%s)",
            source,
            job.id,
            event_type,
            job.state,
        )

    return {"status": "accepted", "job_id": str(job.id), "new_state": job.state}


@router.post("/webhooks/radarr", status_code=200)
async def receive_radarr_webhook(
    payload: dict[str, Any],
    token: str | None = Query(default=None),
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
) -> dict[str, str]:
    """Process Radarr webhook and advance job state."""
    _verify_webhook_token(token, x_webhook_token)
    return await _process_arr_webhook(payload, source="radarr")


@router.post("/webhooks/sonarr", status_code=200)
async def receive_sonarr_webhook(
    payload: dict[str, Any],
    token: str | None = Query(default=None),
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
) -> dict[str, str]:
    """Process Sonarr webhook and advance job state."""
    _verify_webhook_token(token, x_webhook_token)
    return await _process_arr_webhook(payload, source="sonarr")
