"""Job query endpoints -- retrieve job status and history."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dependencies import get_current_user
from shared.database import get_session_factory
from shared.models import Job, JobDiagnostic, JobEvent, JobState, User
from shared.redis_client import enqueue_job, get_download_progress
from shared.schemas import JobEventResponse, JobListResponse, JobResponse
from sqlalchemy import text

logger = logging.getLogger("agent-api.jobs")
router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> JobResponse:
    """Return a single job with its events."""

    async with get_session_factory()() as session:
        stmt = (
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.events))
        )
        if user.role != "admin":
            stmt = stmt.where(Job.user_id == user.id)

        result = await session.execute(stmt)
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
        acquisition_mode=job.acquisition_mode,
        acquisition_method=job.acquisition_method,
        streaming_urls=job.streaming_urls,
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
    all_users: bool = Query(default=False, description="Admins: show jobs from all users"),
    user: User = Depends(get_current_user),
) -> list[JobListResponse]:
    """Return a paginated list of jobs, optionally filtered by status."""

    async with get_session_factory()() as session:
        from sqlalchemy.orm import selectinload

        stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
        stmt = stmt.options(selectinload(Job.events))

        if status is not None:
            stmt = stmt.where(Job.state == status)

        # Non-admins always see only their own jobs.
        # Admins see only their own unless all_users=True.
        if not (user.role == "admin" and all_users):
            stmt = stmt.where(Job.user_id == user.id)

        result = await session.execute(stmt)
        jobs: list[Job] = list(result.scalars().all())

    def _last_error(j: Job) -> str | None:
        error_states = {JobState.FAILED.value, JobState.INVESTIGATING.value, JobState.UNAVAILABLE.value}
        if j.state not in {JobState.FAILED, JobState.INVESTIGATING, JobState.UNAVAILABLE} and j.state not in error_states:
            if not j.events:
                return None
        if not j.events:
            return None
        # Find the most recent event from an error/investigating state
        relevant = [e for e in j.events if e.state in error_states]
        if relevant:
            return max(relevant, key=lambda e: e.created_at).message
        return None

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
            acquisition_mode=j.acquisition_mode,
            acquisition_method=j.acquisition_method,
            streaming_urls=j.streaming_urls,
            retry_count=j.retry_count,
            last_error=_last_error(j),
            created_at=j.created_at,
            updated_at=j.updated_at,
        )
        for j in jobs
    ]


@router.post("/jobs/{job_id}/retry", response_model=JobListResponse)
async def retry_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> JobListResponse:
    """Reset a FAILED job to CREATED and re-enqueue it for processing."""

    async with get_session_factory()() as session:
        stmt = select(Job).where(Job.id == job_id)
        if user.role != "admin":
            stmt = stmt.where(Job.user_id == user.id)

        result = await session.execute(stmt)
        job: Job | None = result.scalar_one_or_none()

        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        retryable = {JobState.FAILED, JobState.INVESTIGATING, JobState.UNAVAILABLE}
        if job.state not in retryable:
            raise HTTPException(status_code=400, detail="Only failed/investigating/unavailable jobs can be retried")

        now = datetime.utcnow()
        job.state = JobState.CREATED
        job.retry_count = job.retry_count + 1
        job.updated_at = now

        event = JobEvent(
            job_id=job.id,
            state=JobState.CREATED.value,
            message=f"Manual retry (attempt #{job.retry_count})",
            created_at=now,
        )
        session.add(event)
        await session.commit()

        # Re-enqueue
        await enqueue_job(str(job.id))
        logger.info("Job %s manually retried (attempt #%d)", job_id, job.retry_count)

        return JobListResponse(
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
        )


@router.post("/jobs/{job_id}/cancel", response_model=JobListResponse)
async def cancel_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> JobListResponse:
    """Cancel a non-terminal job by marking it FAILED."""

    terminal = {JobState.DONE, JobState.FAILED}

    async with get_session_factory()() as session:
        stmt = select(Job).where(Job.id == job_id)
        if user.role != "admin":
            stmt = stmt.where(Job.user_id == user.id)

        result = await session.execute(stmt)
        job: Job | None = result.scalar_one_or_none()

        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.state in terminal:
            raise HTTPException(status_code=400, detail="Job is already in a terminal state")

        now = datetime.utcnow()
        job.state = JobState.FAILED
        job.updated_at = now

        event = JobEvent(
            job_id=job.id,
            state=JobState.FAILED.value,
            message="Cancelled by user",
            created_at=now,
        )
        session.add(event)
        await session.commit()

        logger.info("Job %s cancelled by user %s", job_id, user.id)

        return JobListResponse(
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
        )


@router.get("/jobs/{job_id}/progress")
async def job_progress(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> dict:
    """Return download progress for an active job."""

    # Verify the job belongs to the requesting user (admins can see all).
    async with get_session_factory()() as session:
        stmt = select(Job.id).where(Job.id == job_id)
        if user.role != "admin":
            stmt = stmt.where(Job.user_id == user.id)
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Job not found")

    progress = await get_download_progress(str(job_id))
    if progress is None:
        return {"percent": -1, "detail": "No active download"}
    return progress


@router.get("/jobs/{job_id}/events")
async def get_job_events(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Get event timeline for a job — shows what happened at each step."""

    async with get_session_factory()() as session:
        # Verify access
        stmt = select(Job.id, Job.user_id).where(Job.id == job_id)
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if user.role != "admin" and row[1] != user.id:
            raise HTTPException(status_code=404, detail="Job not found")

        result = await session.execute(
            select(JobEvent)
            .where(JobEvent.job_id == job_id)
            .order_by(JobEvent.created_at.asc())
        )
        events = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "state": e.state,
            "message": e.message,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


@router.get("/jobs/{job_id}/diagnostics")
async def get_job_diagnostics(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Get diagnostic records for a job — shows what was investigated and what fixes were tried."""

    async with get_session_factory()() as session:
        # Verify access (admin only for full diagnostics)
        stmt = select(Job.id, Job.user_id).where(Job.id == job_id)
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if user.role != "admin" and row[1] != user.id:
            raise HTTPException(status_code=404, detail="Job not found")

        result = await session.execute(
            select(JobDiagnostic)
            .where(JobDiagnostic.job_id == job_id)
            .order_by(JobDiagnostic.created_at.desc())
        )
        diags = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "category": d.category,
            "details": d.details_json if user.role == "admin" else None,
            "auto_fix_action": d.auto_fix_action,
            "resolved": d.resolved,
            "created_at": d.created_at.isoformat(),
        }
        for d in diags
    ]


@router.get("/admin/diagnostics/summary")
async def get_diagnostics_summary(
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Aggregate diagnostic stats — shows failure patterns across all jobs."""

    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    async with get_session_factory()() as session:
        result = await session.execute(
            text("""
                SELECT category, COUNT(*) as total,
                       SUM(CASE WHEN resolved THEN 1 ELSE 0 END) as resolved_count
                FROM job_diagnostics
                GROUP BY category
                ORDER BY total DESC
            """)
        )
        rows = result.fetchall()

    return [
        {"category": r[0], "total": r[1], "resolved": r[2]}
        for r in rows
    ]
