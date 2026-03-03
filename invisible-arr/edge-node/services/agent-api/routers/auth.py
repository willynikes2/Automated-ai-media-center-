"""Authentication router — Jellyfin-backed login for the frontend PWA."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from shared.database import get_session_factory
from shared.models import User

logger = logging.getLogger("agent-api.auth")
router = APIRouter()


class LoginRequest(BaseModel):
    jellyfin_user_id: str
    jellyfin_username: str
    jellyfin_token: str
    is_admin: bool = False


class LoginResponse(BaseModel):
    user_id: str
    api_key: str
    name: str
    is_admin: bool


class MeResponse(BaseModel):
    user_id: str
    name: str
    api_key: str
    is_admin: bool


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Register or retrieve a user based on Jellyfin auth.

    The frontend authenticates against Jellyfin first, then calls this
    endpoint with the Jellyfin user info.  We find-or-create a local
    User record keyed on the Jellyfin username and return our API key.
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(User).where(User.name == body.jellyfin_username)
        )
        user: User | None = result.scalar_one_or_none()

        if user is None:
            # First login — create local user
            user = User(name=body.jellyfin_username)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info("Created new user: %s (id=%s)", user.name, user.id)
        else:
            logger.info("Existing user login: %s (id=%s)", user.name, user.id)

    return LoginResponse(
        user_id=str(user.id),
        api_key=user.api_key,
        name=user.name,
        is_admin=body.is_admin,
    )


@router.get("/auth/me", response_model=MeResponse)
async def me(x_api_key: str = Header(..., alias="X-Api-Key")):
    """Return the current user from their API key."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(User).where(User.api_key == x_api_key)
        )
        user: User | None = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return MeResponse(
        user_id=str(user.id),
        name=user.name,
        api_key=user.api_key,
        is_admin=False,  # would need a role column to determine this
    )
