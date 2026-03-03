"""Authentication router — register, login, Jellyfin SSO, and onboarding."""

from __future__ import annotations

import logging
from datetime import datetime

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from dependencies import get_current_user
from shared.database import get_session_factory
from shared.encryption import encrypt
from shared.models import Invite, Prefs, User
from shared.schemas import (
    AuthResponse,
    EmailLoginRequest,
    RegisterRequest,
    SetupRequest,
    UserResponse,
)
from shared.tiers import get_tier_limits

logger = logging.getLogger("agent-api.auth")
router = APIRouter()


# ---------------------------------------------------------------------------
# Local model (Jellyfin login is router-specific, not in shared schemas)
# ---------------------------------------------------------------------------


class JellyfinLoginRequest(BaseModel):
    jellyfin_user_id: str
    jellyfin_username: str
    jellyfin_token: str


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
async def register(body: RegisterRequest):
    """Create a new user account using an invite code."""
    factory = get_session_factory()
    async with factory() as session:
        # --- validate invite code ---
        result = await session.execute(
            select(Invite).where(
                Invite.code == body.invite_code,
                Invite.is_active.is_(True),
            )
        )
        invite: Invite | None = result.scalar_one_or_none()

        if invite is None:
            raise HTTPException(status_code=400, detail="Invalid invite code")

        if invite.times_used >= invite.max_uses:
            raise HTTPException(status_code=400, detail="Invite code has been fully used")

        if invite.expires_at is not None and invite.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Invite code has expired")

        # --- check email uniqueness ---
        existing = await session.execute(
            select(User.id).where(User.email == body.email)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=400, detail="Email already registered")

        # --- hash password ---
        password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

        # --- derive limits from invite tier ---
        limits = get_tier_limits(invite.tier)

        # --- create user ---
        user = User(
            name=body.name,
            email=body.email,
            password_hash=password_hash,
            role="user",
            tier=invite.tier,
            storage_quota_gb=limits["storage_quota_gb"],
            max_concurrent_jobs=limits["max_concurrent_jobs"],
            max_requests_per_day=limits["max_requests_per_day"],
            invited_by=invite.created_by,
        )
        session.add(user)

        # --- increment invite usage ---
        invite.times_used += 1

        await session.flush()  # populate user.id

        # --- create default prefs ---
        prefs = Prefs(
            user_id=user.id,
            max_resolution=limits["max_resolution"],
            allow_4k=limits["allow_4k"],
            max_movie_size_gb=limits["max_movie_size_gb"],
            max_episode_size_gb=limits["max_episode_size_gb"],
        )
        session.add(prefs)

        await session.commit()
        await session.refresh(user)

    return AuthResponse(
        user_id=user.id,
        api_key=user.api_key,
        name=user.name,
        role=user.role,
        tier=user.tier,
    )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@router.post("/auth/login", response_model=AuthResponse)
async def login(body: EmailLoginRequest):
    """Authenticate with email and password."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(User).where(User.email == body.email)
        )
        user: User | None = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if user.password_hash is None or not bcrypt.checkpw(
            body.password.encode(), user.password_hash.encode()
        ):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user.last_login = datetime.utcnow()
        await session.commit()
        await session.refresh(user)

    return AuthResponse(
        user_id=user.id,
        api_key=user.api_key,
        name=user.name,
        role=user.role,
        tier=user.tier,
    )


# ---------------------------------------------------------------------------
# POST /auth/jellyfin-login
# ---------------------------------------------------------------------------


@router.post("/auth/jellyfin-login", response_model=AuthResponse)
async def jellyfin_login(body: JellyfinLoginRequest):
    """Register or retrieve a user based on Jellyfin auth.

    The frontend authenticates against Jellyfin first, then calls this
    endpoint with the Jellyfin user info.  We find-or-create a local
    User record keyed on the Jellyfin username and return our API key.
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(User).where(User.jellyfin_user_id == body.jellyfin_user_id)
        )
        user: User | None = result.scalar_one_or_none()

        if user is None:
            # Fall back to name lookup for legacy records
            result = await session.execute(
                select(User).where(User.name == body.jellyfin_username)
            )
            user = result.scalar_one_or_none()

        if user is None:
            # First login — create local user
            user = User(
                name=body.jellyfin_username,
                jellyfin_user_id=body.jellyfin_user_id,
                jellyfin_token=body.jellyfin_token,
            )
            session.add(user)
            await session.flush()
            logger.info("Created new Jellyfin user: %s (id=%s)", user.name, user.id)
        else:
            # Update Jellyfin fields on existing user
            user.jellyfin_user_id = body.jellyfin_user_id
            user.jellyfin_token = body.jellyfin_token
            logger.info("Existing Jellyfin user login: %s (id=%s)", user.name, user.id)

        user.last_login = datetime.utcnow()
        await session.commit()
        await session.refresh(user)

    return AuthResponse(
        user_id=user.id,
        api_key=user.api_key,
        name=user.name,
        role=user.role,
        tier=user.tier,
    )


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


@router.get("/auth/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# POST /auth/setup
# ---------------------------------------------------------------------------


@router.post("/auth/setup")
async def setup(body: SetupRequest, user: User = Depends(get_current_user)):
    """Onboarding wizard — store RD token and initial preferences."""
    factory = get_session_factory()
    async with factory() as session:
        # Re-attach user inside this session
        result = await session.execute(
            select(User).where(User.id == user.id)
        )
        db_user: User = result.scalar_one()

        # --- encrypt and store RD token ---
        if body.rd_api_token is not None:
            db_user.rd_api_token_enc = encrypt(body.rd_api_token)

        # --- upsert prefs ---
        result = await session.execute(
            select(Prefs).where(Prefs.user_id == user.id)
        )
        prefs: Prefs | None = result.scalar_one_or_none()

        if prefs is None:
            prefs = Prefs(user_id=user.id)
            session.add(prefs)

        if body.preferred_resolution is not None:
            prefs.max_resolution = body.preferred_resolution
        if body.allow_4k is not None:
            prefs.allow_4k = body.allow_4k

        await session.commit()

    return {"status": "ok"}
