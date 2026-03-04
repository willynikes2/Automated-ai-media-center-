"""Request endpoint -- accepts a media request and creates a job."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from dependencies import (
    check_concurrent_jobs,
    check_rate_limit,
    check_storage_quota,
    get_current_user,
)
from shared.config import get_config
from shared.database import get_session_factory
from shared.models import Job, JobState, User
from shared.redis_client import enqueue_job
from shared.schemas import BatchRequestCreate, JobResponse, RequestCreate

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


@router.post("/request/batch", response_model=list[JobResponse], status_code=201)
async def create_batch_request(
    body: BatchRequestCreate,
    user: User = Depends(get_current_user),
) -> list[JobResponse]:
    """Create multiple jobs for a TV series (by season or episode)."""

    # Build list of (season, episode) pairs to create jobs for
    job_specs: list[tuple[int | None, int | None]] = []

    if body.episodes:
        for ep in body.episodes:
            job_specs.append((ep.get("season"), ep.get("episode")))
    elif body.seasons:
        for s in body.seasons:
            job_specs.append((s, None))
    else:
        # Fetch season count from TMDB to create one job per season
        config = get_config()
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    f"https://api.themoviedb.org/3/tv/{body.tmdb_id}",
                    params={"api_key": config.tmdb_api_key},
                )
                r.raise_for_status()
                data = r.json()
                for s in data.get("seasons", []):
                    sn = s.get("season_number", 0)
                    if sn > 0:
                        job_specs.append((sn, None))
        except Exception:
            logger.exception("Failed to fetch TMDB seasons for batch request")
            raise HTTPException(status_code=400, detail="tmdb_id required for all-seasons batch request")

    if not job_specs:
        raise HTTPException(status_code=400, detail="No seasons or episodes to request")

    # Check limits against total batch size
    await check_rate_limit(user)
    await check_concurrent_jobs(user)
    await check_storage_quota(user)

    created_jobs: list[JobResponse] = []
    async with get_session_factory()() as session:
        for season, episode in job_specs:
            job = Job(
                user_id=user.id,
                title=body.query,
                query=body.query,
                tmdb_id=body.tmdb_id,
                media_type="tv",
                season=season,
                episode=episode,
                state=JobState.CREATED,
                acquisition_mode=body.acquisition_mode,
            )
            session.add(job)
            await session.flush()

            created_jobs.append(JobResponse(
                id=job.id,
                user_id=job.user_id,
                title=job.title,
                query=job.query,
                tmdb_id=job.tmdb_id,
                media_type=job.media_type,
                season=job.season,
                episode=job.episode,
                state=job.state,
                selected_candidate=None,
                rd_torrent_id=None,
                imported_path=None,
                acquisition_mode=job.acquisition_mode,
                acquisition_method=None,
                streaming_urls=None,
                retry_count=0,
                created_at=job.created_at,
                updated_at=job.updated_at,
                events=[],
            ))
        await session.commit()

    # Enqueue all jobs
    for jr in created_jobs:
        try:
            await enqueue_job(str(jr.id))
        except Exception:
            logger.exception("Failed to enqueue batch job id=%s", jr.id)

    logger.info(
        "Batch created %d jobs for %r (user=%s)",
        len(created_jobs), body.query, user.id,
    )
    return created_jobs
