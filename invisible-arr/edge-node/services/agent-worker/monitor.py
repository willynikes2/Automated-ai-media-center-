"""Download state monitor — polls Sonarr/Radarr queues and rdt-client for real-time status.

Runs as a background task alongside the job consumer in main.py.

Key responsibility: rdt-client tells Sonarr/Radarr that downloads are "complete"
before files are actually downloaded locally. This monitor polls rdt-client's own
API for real byte-level progress and reports it to the frontend via Redis.

Also detects stuck/failed downloads and logs warnings for the retry system.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from sqlalchemy import select, update as sa_update

from shared.config import get_config
from shared.database import get_session_factory
from shared.models import Job, JobState
from shared.radarr_client import RadarrClient
from shared.redis_client import set_rdt_ready
from shared.sonarr_client import SonarrClient

logger = logging.getLogger("agent-worker.monitor")

POLL_INTERVAL = 15  # seconds


async def monitor_downloads(shutdown_event: asyncio.Event) -> None:
    """Background loop that polls Arr queues and rdt-client for download status.

    This runs continuously until the shutdown event is set.
    """
    config = get_config()
    logger.info("Download monitor starting (poll every %ds)", POLL_INTERVAL)

    while not shutdown_event.is_set():
        try:
            await _poll_cycle(config)
        except Exception:
            logger.exception("Monitor poll cycle failed")

        # Wait for next cycle or shutdown
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=POLL_INTERVAL)
            break  # shutdown_event was set
        except asyncio.TimeoutError:
            continue  # Normal timeout, do next poll

    logger.info("Download monitor stopped")


async def _poll_cycle(config: Any) -> None:
    """Single poll cycle: check Radarr + Sonarr queues, rdt-client status."""
    active_jobs = await _get_active_jobs()

    # Poll Radarr queue
    try:
        async with RadarrClient() as radarr:
            radarr_queue = await radarr.get_queue()
            radarr_records = radarr_queue.get("records", [])
            await _sync_job_correlations_from_arr_queue(active_jobs, radarr_records, "radarr")
            await _mark_ready_from_arr_queue(active_jobs, radarr_records, "radarr")
            for item in radarr_records:
                await _process_queue_item(item, "radarr")
    except Exception:
        logger.debug("Failed to poll Radarr queue", exc_info=True)

    # Poll Sonarr queue
    try:
        async with SonarrClient() as sonarr:
            sonarr_queue = await sonarr.get_queue()
            sonarr_records = sonarr_queue.get("records", [])
            await _sync_job_correlations_from_arr_queue(active_jobs, sonarr_records, "sonarr")
            await _mark_ready_from_arr_queue(active_jobs, sonarr_records, "sonarr")
            for item in sonarr_records:
                await _process_queue_item(item, "sonarr")
    except Exception:
        logger.debug("Failed to poll Sonarr queue", exc_info=True)

    # Poll rdt-client for real download progress
    try:
        await _poll_rdt_client(config, active_jobs)
    except Exception:
        logger.debug("Failed to poll rdt-client", exc_info=True)


async def _process_queue_item(item: dict, source: str) -> None:
    """Process a single Arr queue item — log warnings for stuck/failed."""
    status = item.get("trackedDownloadStatus", "")
    state = item.get("trackedDownloadState", "")
    title = item.get("title", "unknown")

    if state == "failed":
        msgs = _extract_status_messages(item)
        logger.warning(
            "[%s] Download FAILED: %s — %s",
            source, title, msgs,
        )

    elif status == "warning":
        msgs = _extract_status_messages(item)
        logger.warning(
            "[%s] Download WARNING: %s — %s",
            source, title, msgs,
        )


def _extract_status_messages(item: dict) -> str:
    """Extract human-readable status messages from an Arr queue item."""
    messages = item.get("statusMessages", [])
    parts = []
    for msg in messages:
        if isinstance(msg, dict):
            title = msg.get("title", "")
            details = msg.get("messages", [])
            if title:
                parts.append(title)
            for d in details:
                if isinstance(d, str):
                    parts.append(d)
    return "; ".join(parts) if parts else "no details"


async def _poll_rdt_client(config: Any, active_jobs: list[Job]) -> None:
    """Poll rdt-client API for real download progress.

    rdt-client exposes a REST API at port 6500. We check active downloads
    for byte-level progress, which is more accurate than what Sonarr/Radarr
    report (since rdt-client tells Arr "done" prematurely).
    """
    rdt_url = config.rdt_client_url.rstrip("/")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{rdt_url}/Api/Torrents")
            if resp.status_code == 401:
                # Need to authenticate first
                auth_resp = await client.post(
                    f"{rdt_url}/Api/Authentication/Login",
                    json={
                        "userName": config.rdt_client_username,
                        "password": config.rdt_client_password,
                    },
                )
                if auth_resp.status_code == 200:
                    resp = await client.get(f"{rdt_url}/Api/Torrents")
                else:
                    logger.debug("rdt-client auth failed: %d", auth_resp.status_code)
                    return

            if resp.status_code != 200:
                return

            torrents = resp.json()
        except httpx.ConnectError:
            return  # rdt-client not reachable, skip silently

    if not isinstance(torrents, list):
        return

    done_ids: set[str] = set()
    for torrent in torrents:
        rd_status = torrent.get("rdStatus", "")
        download_status = torrent.get("status", "")
        progress = torrent.get("progress", 0)
        torrent_id = str(torrent.get("torrentId", "")).strip()
        filename = torrent.get("rdName", "unknown")[:60]

        if torrent_id and _is_torrent_complete(rd_status, download_status, progress):
            done_ids.add(torrent_id.lower())

        # Log any issues
        if download_status in ("Error", "Failed"):
            error = torrent.get("error", "")
            logger.warning(
                "rdt-client download error: %s — %s (status=%s)",
                filename, error, download_status,
            )
    if not done_ids:
        return

    for job in active_jobs:
        rid = (job.rd_torrent_id or "").strip().lower()
        if rid and rid in done_ids:
            await set_rdt_ready(
                str(job.id),
                payload=json.dumps(
                    {"source": "monitor:rdt", "rd_torrent_id": job.rd_torrent_id}
                ),
            )


def _is_torrent_complete(rd_status: Any, download_status: Any, progress: Any) -> bool:
    """Return True when rdt-client indicates completion."""
    rd = str(rd_status or "").strip().lower()
    st = str(download_status or "").strip().lower()
    try:
        prog = float(progress)
    except (TypeError, ValueError):
        prog = 0.0

    if prog >= 100:
        return True
    if rd in {"downloaded", "finished", "complete", "completed", "cached"}:
        return True
    if st in {"downloaded", "finished", "complete", "completed", "ready"}:
        return True
    return False


async def _get_active_jobs() -> list[Job]:
    """Load jobs that are currently waiting for download/import completion."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(Job)
            .where(Job.state.in_([JobState.ACQUIRING.value, JobState.IMPORTING.value]))
            .order_by(Job.updated_at.desc())
            .limit(200)
        )
        return list(result.scalars().all())


async def _mark_ready_from_arr_queue(
    active_jobs: list[Job], records: list[dict], source: str
) -> None:
    """Set rdt-ready when an active job's tracked Arr queue item has disappeared."""
    queue_ids = {
        int(item["id"])
        for item in records
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    for job in active_jobs:
        qid = job.arr_queue_id
        if not qid:
            continue
        if qid not in queue_ids:
            await set_rdt_ready(
                str(job.id),
                payload=json.dumps(
                    {"source": f"monitor:{source}", "arr_queue_id": qid}
                ),
            )


def _queue_download_id(item: dict) -> str | None:
    """Extract the most useful download-id/hash from an Arr queue item."""
    raw = (
        item.get("downloadId")
        or item.get("downloadClientId")
        or item.get("downloadClientInfo", {}).get("downloadId")
    )
    if isinstance(raw, str):
        raw = raw.strip()
        return raw or None
    return None


async def _sync_job_correlations_from_arr_queue(
    active_jobs: list[Job], records: list[dict], source: str
) -> None:
    """Backfill job correlation fields from currently visible Arr queue records."""
    for record in records:
        if not isinstance(record, dict):
            continue
        queue_id = record.get("id")
        if not isinstance(queue_id, int):
            continue
        download_id = _queue_download_id(record)

        for job in active_jobs:
            if source == "radarr":
                media_id = record.get("movieId")
                if not (job.radarr_movie_id and media_id == job.radarr_movie_id):
                    continue
            else:
                media_id = record.get("seriesId")
                if not (job.sonarr_series_id and media_id == job.sonarr_series_id):
                    continue

            updates: dict[str, Any] = {}
            if not job.arr_queue_id and queue_id:
                updates["arr_queue_id"] = queue_id
            if not job.rd_torrent_id and download_id:
                updates["rd_torrent_id"] = download_id

            if updates:
                await _update_job_fields(job.id, **updates)
                if "arr_queue_id" in updates:
                    job.arr_queue_id = updates["arr_queue_id"]
                if "rd_torrent_id" in updates:
                    job.rd_torrent_id = updates["rd_torrent_id"]
            break


async def _update_job_fields(job_id: Any, **kwargs: Any) -> None:
    """Persist job field updates from monitor context."""
    if not kwargs:
        return
    async with get_session_factory()() as session:
        await session.execute(
            sa_update(Job).where(Job.id == job_id).values(**kwargs)
        )
        await session.commit()
