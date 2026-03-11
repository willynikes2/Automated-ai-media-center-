"""Admin endpoints -- RD status, VPN status, user/invite management, stats."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from dependencies import require_admin
from shared.config import get_config
from shared.database import get_session_factory
from shared.models import Invite, Job, RdPoolAccount, User
from shared.radarr_client import RadarrClient
from shared.schemas import (
    AdminStatsResponse,
    AdminUserCreate,
    AdminUserUpdate,
    InviteCreate,
    InviteResponse,
    UserResponse,
)
from shared.sonarr_client import SonarrClient

logger = logging.getLogger("agent-api.admin")
router = APIRouter()


# ---------------------------------------------------------------------------
# Local response models (RD / VPN status)
# ---------------------------------------------------------------------------


class RDStatusResponse(BaseModel):
    enabled: bool
    username: str | None = None
    type: str | None = None
    expiration: str | None = None
    points: int | None = None


class VPNStatusResponse(BaseModel):
    enabled: bool
    connected: bool = False
    public_ip: str | None = None
    provider: str | None = None


class ArrServiceDiagnostics(BaseModel):
    service: str
    system_status: dict | None = None
    quality_profiles: list[dict] = Field(default_factory=list)
    root_folders: list[dict] = Field(default_factory=list)
    download_clients: list[dict] = Field(default_factory=list)
    error: str | None = None


class ArrDiagnosticsResponse(BaseModel):
    radarr: ArrServiceDiagnostics
    sonarr: ArrServiceDiagnostics


# ---------------------------------------------------------------------------
# RD / VPN status (now secured)
# ---------------------------------------------------------------------------


@router.get("/admin/rd-status", response_model=RDStatusResponse)
async def get_rd_status(user: User = Depends(require_admin)) -> RDStatusResponse:
    """Return Real-Debrid account status."""
    config = get_config()

    if not config.rd_enabled or not config.rd_api_token:
        return RDStatusResponse(enabled=False)

    try:
        from shared.rd_client import RealDebridClient

        async with RealDebridClient(config.rd_api_token) as rd:
            user_info = await rd.check_auth()

        return RDStatusResponse(
            enabled=True,
            username=user_info.get("username"),
            type=user_info.get("type"),
            expiration=user_info.get("expiration"),
            points=user_info.get("points"),
        )
    except Exception:
        logger.exception("Failed to fetch RD status")
        return RDStatusResponse(enabled=True, username="Error fetching status")


@router.get("/admin/vpn-status", response_model=VPNStatusResponse)
async def get_vpn_status(user: User = Depends(require_admin)) -> VPNStatusResponse:
    """Return VPN/Gluetun connection status."""
    config = get_config()

    if not config.vpn_enabled:
        return VPNStatusResponse(enabled=False, provider=config.vpn_provider or None)

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("http://gluetun:9999/v1/publicip/ip")
            if resp.status_code == 200:
                data = resp.json()
                return VPNStatusResponse(
                    enabled=True,
                    connected=True,
                    public_ip=data.get("public_ip") or data.get("ip"),
                    provider=config.vpn_provider or None,
                )
    except Exception:
        logger.warning("Could not reach Gluetun control server")

    return VPNStatusResponse(
        enabled=True,
        connected=False,
        provider=config.vpn_provider or None,
    )


@router.get("/admin/arr-diagnostics", response_model=ArrDiagnosticsResponse)
async def get_arr_diagnostics(user: User = Depends(require_admin)) -> ArrDiagnosticsResponse:
    """Return Sonarr/Radarr config snapshots to debug add/import failures quickly."""
    radarr_diag = ArrServiceDiagnostics(service="radarr")
    sonarr_diag = ArrServiceDiagnostics(service="sonarr")

    try:
        async with RadarrClient() as radarr:
            radarr_diag.system_status = await radarr.system_status()
            radarr_diag.quality_profiles = await radarr.get_quality_profiles()
            radarr_diag.root_folders = await radarr.get_root_folders()
            radarr_diag.download_clients = await radarr.get_download_clients()
    except Exception as exc:
        logger.exception("Failed to collect Radarr diagnostics")
        radarr_diag.error = str(exc)

    try:
        async with SonarrClient() as sonarr:
            sonarr_diag.system_status = await sonarr.system_status()
            sonarr_diag.quality_profiles = await sonarr.get_quality_profiles()
            sonarr_diag.root_folders = await sonarr.get_root_folders()
            sonarr_diag.download_clients = await sonarr.get_download_clients()
    except Exception as exc:
        logger.exception("Failed to collect Sonarr diagnostics")
        sonarr_diag.error = str(exc)

    return ArrDiagnosticsResponse(
        radarr=radarr_diag,
        sonarr=sonarr_diag,
    )


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


@router.post("/admin/users", response_model=UserResponse)
async def create_user(
    body: AdminUserCreate,
    user: User = Depends(require_admin),
) -> UserResponse:
    """Create a new user (admin only). Returns the created user with api_key."""
    factory = get_session_factory()
    async with factory() as session:
        # Check for duplicate email
        existing = await session.execute(
            select(User).where(User.email == body.email)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Email already exists")

        new_user = User(
            name=body.name,
            email=body.email,
            role=body.role,
            tier=body.tier,
            is_active=body.is_active,
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        logger.info("Admin created user: %s (%s)", new_user.email, new_user.id)
        return UserResponse.model_validate(new_user)


@router.get("/admin/users", response_model=list[UserResponse])
async def list_users(user: User = Depends(require_admin)) -> list[UserResponse]:
    """List all users ordered by created_at descending."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(User).order_by(User.created_at.desc())
        )
        users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.put("/admin/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    user: User = Depends(require_admin),
) -> UserResponse:
    """Update a user's role, tier, or limits."""
    factory = get_session_factory()
    async with factory() as session:
        target = await session.get(User, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(target, field, value)

        await session.commit()
        await session.refresh(target)
        return UserResponse.model_validate(target)


@router.delete("/admin/users/{user_id}")
async def deactivate_user(
    user_id: uuid.UUID,
    user: User = Depends(require_admin),
) -> dict[str, str]:
    """Soft-deactivate a user (set is_active = False)."""
    factory = get_session_factory()
    async with factory() as session:
        target = await session.get(User, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User not found")

        target.is_active = False

        # Deprovision IPTV line
        if target.iptv_line_username:
            try:
                config = get_config()
                if config.kemoiptv_api_url:
                    from shared.kemoiptv_client import KemoIPTVClient
                    async with KemoIPTVClient(
                        config.kemoiptv_api_url,
                        config.kemoiptv_reseller_username,
                        config.kemoiptv_reseller_password,
                    ) as client:
                        await client.disable_line(target.iptv_line_username)
            except Exception as e:
                logger.warning("Failed to disable IPTV line for %s: %s", user_id, e)

        # Release RD pool slot
        if target.rd_pool_account_id:
            pool = await session.get(RdPoolAccount, target.rd_pool_account_id)
            if pool and pool.current_users > 0:
                pool.current_users -= 1
            target.rd_pool_account_id = None
            target.rd_source = "user_provided"

        await session.commit()
    return {"status": "deactivated"}


# ---------------------------------------------------------------------------
# Invite management
# ---------------------------------------------------------------------------


@router.get("/admin/invites", response_model=list[InviteResponse])
async def list_invites(user: User = Depends(require_admin)) -> list[InviteResponse]:
    """List all invites."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Invite).order_by(Invite.created_at.desc())
        )
        invites = result.scalars().all()
    return [InviteResponse.model_validate(inv) for inv in invites]


@router.post("/admin/invites", response_model=InviteResponse, status_code=201)
async def create_invite(
    body: InviteCreate,
    user: User = Depends(require_admin),
) -> InviteResponse:
    """Create a new invite code."""
    code = f"AUTOMEDIA-{secrets.token_hex(4).upper()}"

    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=body.expires_in_days)

    invite = Invite(
        code=code,
        created_by=user.id,
        tier=body.tier,
        max_uses=body.max_uses,
        expires_at=expires_at,
    )

    factory = get_session_factory()
    async with factory() as session:
        session.add(invite)
        await session.commit()
        await session.refresh(invite)
        return InviteResponse.model_validate(invite)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/admin/stats", response_model=AdminStatsResponse)
async def get_stats(user: User = Depends(require_admin)) -> AdminStatsResponse:
    """Return system-wide statistics."""
    factory = get_session_factory()
    async with factory() as session:
        total_users = await session.scalar(select(func.count(User.id))) or 0
        active_users = await session.scalar(
            select(func.count(User.id)).where(User.is_active.is_(True))
        ) or 0
        total_jobs = await session.scalar(select(func.count(Job.id))) or 0

        # Jobs grouped by state
        state_rows = await session.execute(
            select(Job.state, func.count(Job.id)).group_by(Job.state)
        )
        jobs_by_state: dict[str, int] = {
            row[0]: row[1] for row in state_rows.all()
        }

        # Total storage used across all users
        storage_used_gb = await session.scalar(
            select(func.coalesce(func.sum(User.storage_used_gb), 0.0))
        ) or 0.0

    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        total_jobs=total_jobs,
        jobs_by_state=jobs_by_state,
        storage_used_gb=round(float(storage_used_gb), 2),
    )
