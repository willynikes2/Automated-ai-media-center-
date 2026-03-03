"""Reseller endpoints -- stats, invite management for reseller-role users."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from dependencies import get_current_user
from shared.database import get_session_factory
from shared.models import Invite, User
from shared.schemas import InviteCreate, InviteResponse

logger = logging.getLogger("agent-api.reseller")
router = APIRouter()


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def require_reseller(user: User = Depends(get_current_user)) -> User:
    """Require reseller or admin role."""
    if user.role not in ("reseller", "admin"):
        raise HTTPException(status_code=403, detail="Reseller access required")
    return user


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ResellerStatsResponse(BaseModel):
    total_referred: int
    active_referred: int
    total_invites: int
    storage_used_gb: float


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/reseller/stats", response_model=ResellerStatsResponse)
async def get_reseller_stats(
    user: User = Depends(require_reseller),
) -> ResellerStatsResponse:
    """Return stats for users referred by this reseller."""
    factory = get_session_factory()
    async with factory() as session:
        total_referred = await session.scalar(
            select(func.count(User.id)).where(User.invited_by == user.id)
        ) or 0

        active_referred = await session.scalar(
            select(func.count(User.id)).where(
                User.invited_by == user.id,
                User.is_active.is_(True),
            )
        ) or 0

        total_invites = await session.scalar(
            select(func.count(Invite.id)).where(Invite.created_by == user.id)
        ) or 0

        storage_used_gb = await session.scalar(
            select(func.coalesce(func.sum(User.storage_used_gb), 0.0)).where(
                User.invited_by == user.id
            )
        ) or 0.0

    return ResellerStatsResponse(
        total_referred=total_referred,
        active_referred=active_referred,
        total_invites=total_invites,
        storage_used_gb=round(float(storage_used_gb), 2),
    )


# ---------------------------------------------------------------------------
# Invite management
# ---------------------------------------------------------------------------


@router.get("/reseller/invites", response_model=list[InviteResponse])
async def list_reseller_invites(
    user: User = Depends(require_reseller),
) -> list[InviteResponse]:
    """List invites created by this reseller."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Invite)
            .where(Invite.created_by == user.id)
            .order_by(Invite.created_at.desc())
        )
        invites = result.scalars().all()
    return [InviteResponse.model_validate(inv) for inv in invites]


class ResellerInviteCreate(BaseModel):
    """Body for POST /v1/reseller/invites (restricted vs admin create)."""

    max_uses: int = Field(default=1, ge=1, le=5)
    expires_in_days: int | None = Field(None, ge=1, le=365)


@router.post("/reseller/invites", response_model=InviteResponse, status_code=201)
async def create_reseller_invite(
    body: ResellerInviteCreate,
    user: User = Depends(require_reseller),
) -> InviteResponse:
    """Create an invite code. Resellers are limited to starter tier and max 5 uses."""
    # Resellers are forced to starter tier; admins can use the admin endpoint
    # for other tiers.
    tier = "starter"
    max_uses = min(body.max_uses, 5)

    # Admins using the reseller endpoint still get reseller restrictions
    # (they should use /admin/invites for full control).

    code = f"AUTOMEDIA-{secrets.token_hex(4).upper()}"

    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=body.expires_in_days)

    invite = Invite(
        code=code,
        created_by=user.id,
        tier=tier,
        max_uses=max_uses,
        expires_at=expires_at,
    )

    factory = get_session_factory()
    async with factory() as session:
        session.add(invite)
        await session.commit()
        await session.refresh(invite)
        return InviteResponse.model_validate(invite)
