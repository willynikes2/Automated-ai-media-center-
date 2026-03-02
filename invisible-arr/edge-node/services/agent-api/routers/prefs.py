"""User preferences endpoints -- get and upsert prefs for the default user."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from shared.database import get_session_factory
from shared.models import Prefs, User
from shared.schemas import PrefsResponse, PrefsUpdate

logger = logging.getLogger("agent-api.prefs")
router = APIRouter()

_DEFAULT_USER_NAME = "default"


async def _get_default_user_id() -> str | None:
    """Look up the default user's id. Returns None if no default user exists."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(User.id).where(User.name == _DEFAULT_USER_NAME)
        )
        row = result.scalar_one_or_none()
        return row


@router.get("/prefs", response_model=PrefsResponse)
async def get_prefs() -> PrefsResponse:
    """Return the current preferences for the default user."""

    user_id = await _get_default_user_id()
    if user_id is None:
        raise HTTPException(status_code=404, detail="Default user not found. Submit a request first.")

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Prefs).where(Prefs.user_id == user_id)
        )
        prefs: Prefs | None = result.scalar_one_or_none()

    if prefs is None:
        raise HTTPException(status_code=404, detail="No preferences set yet")

    return PrefsResponse(
        id=prefs.id,
        user_id=prefs.user_id,
        max_resolution=prefs.max_resolution,
        allow_4k=prefs.allow_4k,
        max_movie_size_gb=prefs.max_movie_size_gb,
        max_episode_size_gb=prefs.max_episode_size_gb,
        prune_watched_after_days=prefs.prune_watched_after_days,
        keep_favorites=prefs.keep_favorites,
        storage_soft_limit_percent=prefs.storage_soft_limit_percent,
        upgrade_policy=prefs.upgrade_policy,
    )


@router.post("/prefs", response_model=PrefsResponse, status_code=200)
async def upsert_prefs(body: PrefsUpdate) -> PrefsResponse:
    """Create or update preferences for the default user (upsert)."""

    user_id = await _get_default_user_id()
    if user_id is None:
        raise HTTPException(status_code=404, detail="Default user not found. Submit a request first.")

    async with get_session_factory()() as session:
        result = await session.execute(
            select(Prefs).where(Prefs.user_id == user_id)
        )
        prefs: Prefs | None = result.scalar_one_or_none()

        if prefs is None:
            prefs = Prefs(user_id=user_id)
            session.add(prefs)

        # Apply only the fields that were explicitly provided.
        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(prefs, field, value)

        await session.commit()
        await session.refresh(prefs)

        logger.info("Upserted preferences for user_id=%s", user_id)

        return PrefsResponse(
            id=prefs.id,
            user_id=prefs.user_id,
            max_resolution=prefs.max_resolution,
            allow_4k=prefs.allow_4k,
            max_movie_size_gb=prefs.max_movie_size_gb,
            max_episode_size_gb=prefs.max_episode_size_gb,
            prune_watched_after_days=prefs.prune_watched_after_days,
            keep_favorites=prefs.keep_favorites,
            storage_soft_limit_percent=prefs.storage_soft_limit_percent,
            upgrade_policy=prefs.upgrade_policy,
        )
