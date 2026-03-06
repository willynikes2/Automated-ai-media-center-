"""Diagnostic engine for root-cause analysis of download failures.

Instead of reporting generic timeouts, this module queries Radarr/Sonarr
to determine *why* a download failed and produces actionable diagnostics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import JobDiagnostic
from shared.radarr_client import RadarrClient
from shared.sonarr_client import SonarrClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Diagnosis data object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """Structured result of a diagnostic investigation."""

    category: str  # no_releases | quality_rejected | indexer_error |
    #                download_stalled | import_blocked | arr_unresponsive |
    #                disk_full | content_not_released | unknown
    summary: str  # technical summary for logs
    details: dict  # raw Arr data for audit trail
    auto_fix: str | None  # recommended fix action name, or None
    user_message: str  # plain-English message for end users


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REJECTION_EVENT_TYPES = {"downloadFailed", "grabbed", "downloadFolderImported"}

_REJECTION_KEYWORDS = frozenset({
    "quality", "cutoff", "not wanted", "rejected", "custom format",
    "minimum", "maximum", "size", "not meeting",
})

_INDEXER_ERROR_KEYWORDS = frozenset({
    "indexer", "api limit", "rate limit", "unavailable", "timeout",
    "connection", "502", "503",
})


def _extract_rejections(history_records: list[dict]) -> list[str]:
    """Pull rejection reasons from Arr history data dicts.

    Radarr/Sonarr store rejection info in the ``data`` sub-dict of history
    records, typically under keys like ``rejections``, ``reason``, or
    ``droppedPath`` / ``message``.
    """
    rejections: list[str] = []
    for record in history_records:
        data = record.get("data") or {}

        # Explicit rejection list (Radarr v3+)
        if "rejections" in data:
            raw = data["rejections"]
            if isinstance(raw, list):
                rejections.extend(str(r) for r in raw)
            elif isinstance(raw, str):
                rejections.append(raw)

        # Single reason string
        if "reason" in data:
            rejections.append(str(data["reason"]))

        # Message field on downloadFailed events
        if record.get("eventType") == "downloadFailed":
            msg = data.get("message") or record.get("sourceTitle", "")
            if msg:
                rejections.append(msg)

    return rejections


def _has_quality_rejections(rejections: list[str]) -> bool:
    """Return True if any rejection string looks quality-related."""
    lower = [r.lower() for r in rejections]
    return any(
        any(kw in r for kw in _REJECTION_KEYWORDS)
        for r in lower
    )


def _has_indexer_errors(history_records: list[dict]) -> bool:
    """Return True if history contains indexer-related errors."""
    for record in history_records:
        data = record.get("data") or {}
        haystack = " ".join(str(v) for v in data.values()).lower()
        if any(kw in haystack for kw in _INDEXER_ERROR_KEYWORDS):
            return True
    return False


def _episode_air_date(episodes: list[dict], season: int | None, episode: int | None) -> datetime | None:
    """Find the air date of the target episode, if available."""
    for ep in episodes:
        if season is not None and ep.get("seasonNumber") != season:
            continue
        if episode is not None and ep.get("episodeNumber") != episode:
            continue
        raw = ep.get("airDateUtc") or ep.get("airDate")
        if raw:
            try:
                # Sonarr returns ISO-8601 with Z suffix
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return dt
            except (ValueError, TypeError):
                pass
    return None


# ---------------------------------------------------------------------------
# Public diagnostic functions
# ---------------------------------------------------------------------------


async def diagnose_no_grab(job, session: AsyncSession) -> Diagnosis:
    """Diagnose why Arr hasn't grabbed anything after a search was triggered.

    Queries the relevant Arr API for movie/series status, history, and
    episode air dates to determine root cause.
    """
    try:
        if job.media_type == "movie":
            return await _diagnose_no_grab_movie(job)
        else:
            return await _diagnose_no_grab_tv(job)
    except Exception as exc:
        logger.warning("Arr unreachable during no-grab diagnosis: %s", exc)
        return Diagnosis(
            category="arr_unresponsive",
            summary=f"Could not reach Arr API: {exc}",
            details={"error": str(exc)},
            auto_fix="retry_search",
            user_message=(
                "We're having trouble communicating with the download system. "
                "We'll keep trying automatically."
            ),
        )


async def _diagnose_no_grab_movie(job) -> Diagnosis:
    """No-grab diagnosis for movies via Radarr."""
    async with RadarrClient() as client:
        movie = await client.get_movie(job.radarr_movie_id)
        history_resp = await client.get_history(movie_id=job.radarr_movie_id, page_size=50)

    status = movie.get("status", "").lower()
    records = history_resp.get("records", [])

    # Content not yet released
    if status in ("announced", "inCinemas"):
        return Diagnosis(
            category="content_not_released",
            summary=f"Movie status is '{status}' — not yet available for download",
            details={"movie_status": status, "title": movie.get("title")},
            auto_fix="set_monitored",
            user_message=(
                f"'{movie.get('title', 'This movie')}' hasn't been released for "
                "home viewing yet. We'll grab it automatically once it becomes available."
            ),
        )

    # Check history for rejection reasons
    rejections = _extract_rejections(records)
    if rejections and _has_quality_rejections(rejections):
        return Diagnosis(
            category="quality_rejected",
            summary=f"Releases found but rejected: {rejections[:5]}",
            details={"rejections": rejections[:20]},
            auto_fix="relax_quality",
            user_message=(
                "We found some versions of this movie, but none of them met your "
                "quality settings. You may want to adjust your quality preferences."
            ),
        )

    # Indexer errors
    if _has_indexer_errors(records):
        return Diagnosis(
            category="indexer_error",
            summary="Indexer errors detected in recent history",
            details={"record_count": len(records), "rejections": rejections[:10]},
            auto_fix="retry_search",
            user_message=(
                "Some of our search sources are having issues right now. "
                "We'll retry the search shortly."
            ),
        )

    # No history at all — truly nothing found
    if not records:
        return Diagnosis(
            category="no_releases",
            summary="No history records — zero releases found by any indexer",
            details={"movie_id": job.radarr_movie_id, "movie_status": status},
            auto_fix="retry_search",
            user_message=(
                "We searched everywhere but couldn't find this movie available "
                "for download right now. We'll keep looking."
            ),
        )

    # Fallback — there are records but we can't pinpoint the issue
    return Diagnosis(
        category="unknown",
        summary=f"History has {len(records)} records but no clear failure pattern",
        details={"record_count": len(records), "rejections": rejections[:10]},
        auto_fix="retry_search",
        user_message=(
            "Something unexpected happened while searching for this movie. "
            "We're looking into it and will retry."
        ),
    )


async def _diagnose_no_grab_tv(job) -> Diagnosis:
    """No-grab diagnosis for TV via Sonarr."""
    async with SonarrClient() as client:
        series = await client.get_series(job.sonarr_series_id)
        episodes = await client.get_episodes(job.sonarr_series_id, season=job.season)
        history_resp = await client.get_history(series_id=job.sonarr_series_id, page_size=50)

    status = series.get("status", "").lower()
    records = history_resp.get("records", [])

    # Check episode air date
    air_dt = _episode_air_date(episodes, job.season, job.episode)
    if air_dt and air_dt > datetime.now(timezone.utc):
        return Diagnosis(
            category="content_not_released",
            summary=f"Episode airs {air_dt.isoformat()} — still in the future",
            details={
                "series_title": series.get("title"),
                "air_date": air_dt.isoformat(),
                "season": job.season,
                "episode": job.episode,
            },
            auto_fix="set_monitored",
            user_message=(
                f"This episode of '{series.get('title', 'the show')}' hasn't aired yet. "
                "We'll download it automatically after it airs."
            ),
        )

    # Series ended / continuing but nothing found
    if status in ("upcoming",):
        return Diagnosis(
            category="content_not_released",
            summary=f"Series status is '{status}' — season may not have started",
            details={"series_status": status, "title": series.get("title")},
            auto_fix="set_monitored",
            user_message=(
                f"'{series.get('title', 'This show')}' hasn't started airing yet. "
                "We'll grab episodes automatically once they become available."
            ),
        )

    # Quality rejections
    rejections = _extract_rejections(records)
    if rejections and _has_quality_rejections(rejections):
        return Diagnosis(
            category="quality_rejected",
            summary=f"Releases rejected by quality filter: {rejections[:5]}",
            details={"rejections": rejections[:20]},
            auto_fix="relax_quality",
            user_message=(
                "We found some episodes, but they didn't meet your quality "
                "settings. You may want to adjust your quality preferences."
            ),
        )

    # Indexer errors
    if _has_indexer_errors(records):
        return Diagnosis(
            category="indexer_error",
            summary="Indexer errors detected in recent history",
            details={"record_count": len(records), "rejections": rejections[:10]},
            auto_fix="retry_search",
            user_message=(
                "Some of our search sources are having issues right now. "
                "We'll retry the search shortly."
            ),
        )

    # No history — nothing found
    if not records:
        return Diagnosis(
            category="no_releases",
            summary="No history records — zero releases found by any indexer",
            details={
                "series_id": job.sonarr_series_id,
                "season": job.season,
                "episode": job.episode,
            },
            auto_fix="retry_search",
            user_message=(
                "We searched everywhere but couldn't find this episode available "
                "for download right now. We'll keep looking."
            ),
        )

    return Diagnosis(
        category="unknown",
        summary=f"History has {len(records)} records but no clear failure pattern",
        details={"record_count": len(records), "rejections": rejections[:10]},
        auto_fix="retry_search",
        user_message=(
            "Something unexpected happened while searching for this episode. "
            "We're looking into it and will retry."
        ),
    )


async def diagnose_stalled_download(job, queue_item: dict) -> Diagnosis:
    """Diagnose why a download is not progressing.

    Inspects queue item fields returned by the Arr API to classify the
    stall into disk_full, import_blocked, or generic download_stalled.
    """
    error_msg = (queue_item.get("errorMessage") or "").lower()
    tracked_status = (queue_item.get("trackedDownloadStatus") or "").lower()
    status = (queue_item.get("status") or "").lower()
    title = queue_item.get("title") or queue_item.get("sourceTitle") or "Unknown"
    status_messages = queue_item.get("statusMessages") or []

    # Disk full / space issues
    if "disk" in error_msg or "space" in error_msg:
        return Diagnosis(
            category="disk_full",
            summary=f"Disk space issue: {queue_item.get('errorMessage')}",
            details={
                "errorMessage": queue_item.get("errorMessage"),
                "title": title,
                "size": queue_item.get("size"),
                "sizeleft": queue_item.get("sizeleft"),
            },
            auto_fix="free_disk_space",
            user_message=(
                "The server is running low on disk space, so your download "
                "can't be saved right now. We're working on freeing up room."
            ),
        )

    # Import blocked or failed
    if status in ("importblocked", "importfailed"):
        messages = []
        for sm in status_messages:
            messages.extend(sm.get("messages", []))
        return Diagnosis(
            category="import_blocked",
            summary=f"Import issue (status={status}): {messages[:3]}",
            details={
                "status": status,
                "statusMessages": status_messages[:5],
                "errorMessage": queue_item.get("errorMessage"),
                "title": title,
            },
            auto_fix="retry_import",
            user_message=(
                "Your download finished but the system is having trouble "
                "organizing the file. We'll try to fix this automatically."
            ),
        )

    # Tracked download warning/error
    if tracked_status in ("warning", "error"):
        return Diagnosis(
            category="download_stalled",
            summary=f"Download client reports {tracked_status}: {queue_item.get('errorMessage', 'no details')}",
            details={
                "trackedDownloadStatus": tracked_status,
                "errorMessage": queue_item.get("errorMessage"),
                "title": title,
                "protocol": queue_item.get("protocol"),
                "downloadClient": queue_item.get("downloadClient"),
                "size": queue_item.get("size"),
                "sizeleft": queue_item.get("sizeleft"),
            },
            auto_fix="retry_download",
            user_message=(
                "Your download ran into a problem and appears to be stuck. "
                "We'll try a different source."
            ),
        )

    # Default stall
    return Diagnosis(
        category="download_stalled",
        summary=f"Download not progressing (status={status}, tracked={tracked_status})",
        details={
            "status": status,
            "trackedDownloadStatus": tracked_status,
            "errorMessage": queue_item.get("errorMessage"),
            "title": title,
            "size": queue_item.get("size"),
            "sizeleft": queue_item.get("sizeleft"),
            "timeleft": queue_item.get("timeleft"),
        },
        auto_fix="retry_download",
        user_message=(
            "Your download seems to have stalled. "
            "We'll try to find a better source."
        ),
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def save_diagnostic(session: AsyncSession, job_id, diagnosis: Diagnosis) -> JobDiagnostic:
    """Persist a diagnosis to the job_diagnostics table."""
    record = JobDiagnostic(
        job_id=job_id,
        category=diagnosis.category,
        details_json={
            "summary": diagnosis.summary,
            "details": diagnosis.details,
            "user_message": diagnosis.user_message,
        },
        auto_fix_action=diagnosis.auto_fix,
        resolved=False,
    )
    session.add(record)
    await session.flush()
    logger.info(
        "Saved diagnostic job=%s category=%s auto_fix=%s",
        job_id,
        diagnosis.category,
        diagnosis.auto_fix,
    )
    return record


async def mark_diagnostic_resolved(session: AsyncSession, job_id) -> None:
    """Mark all open diagnostics for a job as resolved."""
    stmt = (
        update(JobDiagnostic)
        .where(
            JobDiagnostic.job_id == job_id,
            JobDiagnostic.resolved == False,  # noqa: E712 — SQLAlchemy requires ==
        )
        .values(resolved=True)
    )
    result = await session.execute(stmt)
    if result.rowcount:
        logger.info(
            "Resolved %d open diagnostic(s) for job=%s",
            result.rowcount,
            job_id,
        )
