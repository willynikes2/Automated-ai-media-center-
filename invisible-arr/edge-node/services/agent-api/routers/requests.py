"""Request endpoint -- accepts a media request and creates a job."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from shared.database import get_session_factory
from shared.models import Job, JobState, User
from shared.redis_client import enqueue_job
from shared.schemas import JobResponse, RequestCreate

logger = logging.getLogger("agent-api.requests")
router = APIRouter()

# Default user name used for the v1 single-user simplification.
_DEFAULT_USER_NAME = "default"


async def _get_or_create_default_user() -> uuid.UUID:
    """Return the default user's id, creating the row if it doesn't exist."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(User).where(User.name == _DEFAULT_USER_NAME)
        )
        user: User | None = result.scalar_one_or_none()

        if user is not None:
            return user.id

        user = User(name=_DEFAULT_USER_NAME)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.info("Created default user id=%s", user.id)
        return user.id


@router.post("/request", response_model=JobResponse, status_code=201)
async def create_request(
    body: RequestCreate,
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
) -> JobResponse:
    """Accept a media request, persist a Job, and enqueue it for processing."""

    # Use API key to look up the user; fall back to default if missing
    user_id: uuid.UUID | None = None
    if x_api_key:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(User).where(User.api_key == x_api_key)
            )
            user: User | None = result.scalar_one_or_none()
            if user:
                user_id = user.id

    if user_id is None:
        user_id = await _get_or_create_default_user()

    async with get_session_factory()() as session:
        job = Job(
            user_id=user_id,
            title=body.query,
            query=body.query,
            tmdb_id=body.tmdb_id,
            media_type=body.media_type,
            season=body.season,
            episode=body.episode,
            state=JobState.CREATED,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)

        logger.info("Created job id=%s for query=%r", job.id, body.query)

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
        retry_count=job.retry_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
        events=[],
    )
