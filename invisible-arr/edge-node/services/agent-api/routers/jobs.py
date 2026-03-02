"""Job query endpoints -- retrieve job status and history."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared.database import get_session_factory
from shared.models import Job, JobEvent, JobState
from shared.schemas import JobEventResponse, JobListResponse, JobResponse

logger = logging.getLogger("agent-api.jobs")
router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID) -> JobResponse:
    """Return a single job with its events."""

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.events))
        )
        job: Job | None = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

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
        retry_count=job.retry_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
        events=[
            JobEventResponse(
                id=e.id,
                job_id=e.job_id,
                state=e.state,
                message=e.message,
                metadata_json=e.metadata_json,
                created_at=e.created_at,
            )
            for e in job.events
        ],
    )


@router.get("/jobs", response_model=list[JobListResponse])
async def list_jobs(
    status: JobState | None = Query(default=None, description="Filter by job state"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
) -> list[JobListResponse]:
    """Return a paginated list of jobs, optionally filtered by status."""

    async with get_session_factory()() as session:
        stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)

        if status is not None:
            stmt = stmt.where(Job.state == status)

        result = await session.execute(stmt)
        jobs: list[Job] = list(result.scalars().all())

    return [
        JobListResponse(
            id=j.id,
            user_id=j.user_id,
            title=j.title,
            query=j.query,
            tmdb_id=j.tmdb_id,
            media_type=j.media_type,
            season=j.season,
            episode=j.episode,
            state=j.state,
            selected_candidate=j.selected_candidate,
            rd_torrent_id=j.rd_torrent_id,
            imported_path=j.imported_path,
            retry_count=j.retry_count,
            created_at=j.created_at,
            updated_at=j.updated_at,
        )
        for j in jobs
    ]
