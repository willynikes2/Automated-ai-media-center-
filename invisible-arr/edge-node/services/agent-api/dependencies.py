"""Shared FastAPI dependencies for authentication and authorization."""

from __future__ import annotations

import logging

from fastapi import Header, HTTPException
from sqlalchemy import func, select

from shared.database import get_session_factory
from shared.models import Job, JobState, User
from shared.redis_client import check_and_increment_rate

logger = logging.getLogger("agent-api.dependencies")

# Active job states (not terminal)
_ACTIVE_STATES = [
    JobState.CREATED, JobState.RESOLVING, JobState.SEARCHING,
    JobState.SELECTED, JobState.ACQUIRING, JobState.IMPORTING,
    JobState.VERIFYING,
]


async def get_current_user(
    x_api_key: str = Header(..., alias="X-Api-Key"),
) -> User:
    """Validate X-Api-Key header and return the corresponding User."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(User).where(User.api_key == x_api_key)
        )
        user: User | None = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    return user


async def require_admin(
    x_api_key: str = Header(..., alias="X-Api-Key"),
) -> User:
    """Require admin role."""
    user = await get_current_user(x_api_key)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def check_rate_limit(user: User) -> None:
    """Check if user has exceeded their daily request limit."""
    allowed = await check_and_increment_rate(
        str(user.id), user.max_requests_per_day
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {user.max_requests_per_day} requests per day.",
        )


async def check_concurrent_jobs(user: User) -> None:
    """Check if user has too many active jobs."""
    if user.max_concurrent_jobs == -1:
        return  # unlimited
    factory = get_session_factory()
    async with factory() as session:
        count = await session.scalar(
            select(func.count(Job.id)).where(
                Job.user_id == user.id,
                Job.state.in_([s.value for s in _ACTIVE_STATES]),
            )
        )
    if count is not None and count >= user.max_concurrent_jobs:
        raise HTTPException(
            status_code=429,
            detail=f"Too many active jobs ({count}/{user.max_concurrent_jobs}). Wait for current jobs to complete.",
        )


async def check_storage_quota(user: User) -> None:
    """Check if user has exceeded their storage quota."""
    if user.storage_quota_gb == -1:
        return  # unlimited
    if user.storage_used_gb >= user.storage_quota_gb:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Storage quota exceeded. Using {user.storage_used_gb:.1f}GB "
                f"of {user.storage_quota_gb:.0f}GB. Free up space or upgrade your plan."
            ),
        )


async def check_item_quota(user: User, media_type: str) -> None:
    """Check if user has exceeded their item-count quota."""
    if media_type == "movie":
        if user.movie_quota == -1:
            return
        if user.movie_count >= user.movie_quota:
            raise HTTPException(
                status_code=429,
                detail=f"Movie quota reached ({user.movie_count}/{user.movie_quota}). Delete content or upgrade.",
            )
    else:
        if user.tv_quota == -1:
            return
        if user.tv_count >= user.tv_quota:
            raise HTTPException(
                status_code=429,
                detail=f"TV quota reached ({user.tv_count}/{user.tv_quota}). Delete content or upgrade.",
            )
