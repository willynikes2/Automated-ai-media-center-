"""Authentication router — register, login, Jellyfin SSO, Google OAuth, and onboarding."""

from __future__ import annotations

import logging
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path

import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from dependencies import get_current_user
from shared.config import get_config
from shared.database import get_session_factory
from shared.encryption import encrypt
from shared.jellyfin_client import JellyfinAdmin
from shared.models import Invite, Prefs, User
from shared.radarr_client import RadarrClient
from shared.sonarr_client import SonarrClient
from shared.schemas import (
    AuthResponse,
    EmailLoginRequest,
    GoogleCallbackRequest,
    RegisterRequest,
    SetupRequest,
    UserResponse,
)
from shared.tiers import get_tier_limits

logger = logging.getLogger("agent-api.auth")
router = APIRouter()

# Trash Guides quality profile IDs (created by Recyclarr)
# "HD Bluray + WEB" in Radarr, "WEB-1080p" in Sonarr
RADARR_QUALITY_PROFILE_ID = 7
SONARR_QUALITY_PROFILE_ID = 7


async def _provision_arr_root_folders(user_id: uuid.UUID) -> tuple[int | None, int | None]:
    """Register per-user root folders in Sonarr/Radarr. Returns (radarr_id, sonarr_id)."""
    config = get_config()
    user_media = f"/data/media/users/{user_id}"
    radarr_id = sonarr_id = None

    try:
        async with RadarrClient() as radarr:
            # Check if folder already registered
            existing = await radarr.get_root_folders()
            movie_path = f"{user_media}/Movies"
            for rf in existing:
                if rf["path"] == movie_path:
                    radarr_id = rf["id"]
                    break
            if radarr_id is None:
                result = await radarr.add_root_folder(movie_path)
                radarr_id = result["id"]
                logger.info("Registered Radarr root folder: %s (id=%d)", movie_path, radarr_id)
    except Exception:
        logger.exception("Failed to register Radarr root folder for user %s", user_id)

    try:
        async with SonarrClient() as sonarr:
            existing = await sonarr.get_root_folders()
            tv_path = f"{user_media}/TV"
            for rf in existing:
                if rf["path"] == tv_path:
                    sonarr_id = rf["id"]
                    break
            if sonarr_id is None:
                result = await sonarr.add_root_folder(tv_path)
                sonarr_id = result["id"]
                logger.info("Registered Sonarr root folder: %s (id=%d)", tv_path, sonarr_id)
    except Exception:
        logger.exception("Failed to register Sonarr root folder for user %s", user_id)

    return radarr_id, sonarr_id


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

    # Provision per-user media directories and Arr root folders
    try:
        config = get_config()
        user_media = Path(config.media_path) / "users" / str(user.id)
        (user_media / "Movies").mkdir(parents=True, exist_ok=True)
        (user_media / "TV").mkdir(parents=True, exist_ok=True)

        radarr_rf_id, sonarr_rf_id = await _provision_arr_root_folders(user.id)
        if radarr_rf_id or sonarr_rf_id:
            async with factory() as session:
                result = await session.execute(select(User).where(User.id == user.id))
                db_user = result.scalar_one()
                if radarr_rf_id:
                    db_user.radarr_root_folder_id = radarr_rf_id
                if sonarr_rf_id:
                    db_user.sonarr_root_folder_id = sonarr_rf_id
                await session.commit()
    except Exception:
        logger.exception("Failed to provision media folders for %s", user.name)

    return AuthResponse(
        user_id=user.id,
        api_key=user.api_key,
        name=user.name,
        role=user.role,
        tier=user.tier,
        setup_complete=user.setup_complete,
    )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@router.post("/auth/login", response_model=AuthResponse)
async def login(body: EmailLoginRequest):
    """Authenticate with email/username and password."""
    factory = get_session_factory()
    async with factory() as session:
        # Try email first, then fall back to username
        result = await session.execute(
            select(User).where(
                (User.email == body.email) | (User.name == body.email)
            )
        )
        user: User | None = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if user.password_hash is None or not bcrypt.checkpw(
            body.password.encode(), user.password_hash.encode()
        ):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user.last_login = datetime.utcnow()
        await session.commit()
        await session.refresh(user)

    return AuthResponse(
        user_id=user.id,
        api_key=user.api_key,
        name=user.name,
        role=user.role,
        tier=user.tier,
        setup_complete=user.setup_complete,
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

    # Provision per-user media directories, Jellyfin libraries, and Arr root folders
    try:
        config = get_config()
        user_media = Path(config.media_path) / "users" / str(user.id)
        (user_media / "Movies").mkdir(parents=True, exist_ok=True)
        (user_media / "TV").mkdir(parents=True, exist_ok=True)

        jf = JellyfinAdmin()
        if jf.enabled and user.role != "admin":
            await jf.provision_user_libraries(
                user_id=str(user.id),
                username=user.name,
                jellyfin_user_id=body.jellyfin_user_id,
            )
    except Exception:
        logger.exception("Failed to provision Jellyfin libraries for %s", user.name)

    # Register root folders in Sonarr/Radarr if not already done
    if user.radarr_root_folder_id is None or user.sonarr_root_folder_id is None:
        try:
            radarr_rf_id, sonarr_rf_id = await _provision_arr_root_folders(user.id)
            if radarr_rf_id or sonarr_rf_id:
                factory = get_session_factory()
                async with factory() as session:
                    result = await session.execute(select(User).where(User.id == user.id))
                    db_user = result.scalar_one()
                    if radarr_rf_id:
                        db_user.radarr_root_folder_id = radarr_rf_id
                    if sonarr_rf_id:
                        db_user.sonarr_root_folder_id = sonarr_rf_id
                    await session.commit()
        except Exception:
            logger.exception("Failed to provision Arr root folders for %s", user.name)

    return AuthResponse(
        user_id=user.id,
        api_key=user.api_key,
        name=user.name,
        role=user.role,
        tier=user.tier,
        setup_complete=user.setup_complete,
    )


# ---------------------------------------------------------------------------
# GET /auth/google/url — get Google OAuth consent URL
# ---------------------------------------------------------------------------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


@router.get("/auth/google/url")
async def google_auth_url():
    """Return the Google OAuth2 consent URL for the frontend to redirect to."""
    config = get_config()
    if not config.google_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    params = {
        "client_id": config.google_client_id,
        "redirect_uri": config.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return {"url": url}


# ---------------------------------------------------------------------------
# POST /auth/google/callback — exchange code for user
# ---------------------------------------------------------------------------


@router.post("/auth/google/callback", response_model=AuthResponse)
async def google_callback(body: GoogleCallbackRequest):
    """Exchange Google auth code for user info, create/link user, return API key."""
    config = get_config()
    if not config.google_client_id or not config.google_client_secret:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": body.code,
                "client_id": config.google_client_id,
                "client_secret": config.google_client_secret,
                "redirect_uri": body.redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if token_resp.status_code != 200:
        logger.error("Google token exchange failed: %s", token_resp.text)
        raise HTTPException(status_code=401, detail="Google authentication failed")

    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="No access token from Google")

    # Fetch user info from Google
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if userinfo_resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Failed to fetch Google user info")

    google_user = userinfo_resp.json()
    google_id = google_user.get("id")
    google_email = google_user.get("email")
    google_name = google_user.get("name", google_email)
    avatar_url = google_user.get("picture")

    if not google_id or not google_email:
        raise HTTPException(status_code=401, detail="Incomplete Google profile")

    # Find or create user
    factory = get_session_factory()
    async with factory() as session:
        # First: check if a user is already linked by google_id
        result = await session.execute(
            select(User).where(User.google_id == google_id)
        )
        user: User | None = result.scalar_one_or_none()

        if user is None:
            # Check if email matches an existing account (link it)
            result = await session.execute(
                select(User).where(User.email == google_email)
            )
            user = result.scalar_one_or_none()
            if user is not None:
                # Link Google to existing account
                user.google_id = google_id
                if avatar_url:
                    user.avatar_url = avatar_url
                logger.info("Linked Google account to existing user: %s", user.name)

        if user is None:
            # New user — create account (no invite required for Google SSO)
            user = User(
                name=google_name,
                email=google_email,
                google_id=google_id,
                avatar_url=avatar_url,
                role="user",
                tier="starter",
            )
            session.add(user)
            await session.flush()
            logger.info("Created new Google user: %s (id=%s)", user.name, user.id)

            # Create default prefs
            limits = get_tier_limits("starter")
            prefs = Prefs(
                user_id=user.id,
                max_resolution=limits["max_resolution"],
                allow_4k=limits["allow_4k"],
                max_movie_size_gb=limits["max_movie_size_gb"],
                max_episode_size_gb=limits["max_episode_size_gb"],
            )
            session.add(prefs)

        user.last_login = datetime.utcnow()
        await session.commit()
        await session.refresh(user)

    # Provision per-user media directories and Arr root folders
    try:
        user_media = Path(config.media_path) / "users" / str(user.id)
        (user_media / "Movies").mkdir(parents=True, exist_ok=True)
        (user_media / "TV").mkdir(parents=True, exist_ok=True)

        if user.radarr_root_folder_id is None or user.sonarr_root_folder_id is None:
            radarr_rf_id, sonarr_rf_id = await _provision_arr_root_folders(user.id)
            if radarr_rf_id or sonarr_rf_id:
                async with factory() as session:
                    result = await session.execute(select(User).where(User.id == user.id))
                    db_user = result.scalar_one()
                    if radarr_rf_id:
                        db_user.radarr_root_folder_id = radarr_rf_id
                    if sonarr_rf_id:
                        db_user.sonarr_root_folder_id = sonarr_rf_id
                    await session.commit()
    except Exception:
        logger.exception("Failed to provision media folders for Google user %s", user.name)

    return AuthResponse(
        user_id=user.id,
        api_key=user.api_key,
        name=user.name,
        role=user.role,
        tier=user.tier,
        setup_complete=user.setup_complete,
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

        # Mark setup as complete
        db_user.setup_complete = True

        await session.commit()

    return {"status": "ok"}
