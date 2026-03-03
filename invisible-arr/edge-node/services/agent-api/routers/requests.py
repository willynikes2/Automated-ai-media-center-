"""Request endpoint -- accepts a media request and creates a job."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from dependencies import (
    check_concurrent_jobs,
    check_rate_limit,
    check_storage_quota,
    get_current_user,
)
from shared.database import get_session_factory
from shared.models import Job, JobState, User
from shared.redis_client import enqueue_job
from shared.schemas import JobResponse, RequestCreate

logger = logging.getLogger("agent-api.requests")
router = APIRouter()


@router.post("/request", response_model=JobResponse, status_code=201)
async def create_request(
    body: RequestCreate,
    user: User = Depends(get_current_user),
) -> JobResponse:
    """Accept a media request, persist a Job, and enqueue it for processing."""

    # Enforce per-user limits
    await check_rate_limit(user)
    await check_concurrent_jobs(user)
    await check_storage_quota(user)

    async with get_session_factory()() as session:
        job = Job(
            user_id=user.id,
            title=body.query,
            query=body.query,
            tmdb_id=body.tmdb_id,
            media_type=body.media_type,
            season=body.season,
            episode=body.episode,
            state=JobState.CREATED,
            acquisition_mode=body.acquisition_mode,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)

        logger.info("Created job id=%s for query=%r (user=%s)", job.id, body.query, user.id)

    # Enqueue the job for the worker to pick up.
    try:
        await enqueue_job(str(job.id))
        logger.info("Enqueued job id=%s to Redis", job.id)
    except Exception:
        logger.exception("Failed to enqueue job id=%s", job.id)
        raise HTTPException(
            status_code=503,
            detail="Job created but could not be enqueued. Retry later.",
        )

    return JobResponse(
        id=job.id,
        user_id=job.user_id,
        title=job.title,
        query=job.query,
        tmdb_id=job.tmdb_id,
        media_type=job.media_type,
        season=job.season,
        episode=job.episode,
        state=job.state,
        selected_candidate=job.selected_candidate,
        rd_torrent_id=job.rd_torrent_id,
        imported_path=job.imported_path,
        acquisition_mode=job.acquisition_mode,
        acquisition_method=job.acquisition_method,
        streaming_urls=job.streaming_urls,
        retry_count=job.retry_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
        events=[],
    )
