"""Onboarding provisioning router — orchestrates IPTV, RD, Library, and Prefs setup."""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from dependencies import get_current_user
from shared.config import get_config
from shared.database import get_session_factory
from shared.encryption import encrypt
from shared.kemoiptv_client import KemoIPTVClient, KemoIPTVError
from shared.models import Prefs, RdPoolAccount, User
from shared.schemas import ProvisionRequest, ProvisionStatusResponse, ProvisionStatusItem
from shared.tiers import get_tier_limits

# Reuse the existing root-folder provisioner from auth
from routers.auth import _provision_arr_root_folders

logger = logging.getLogger("agent-api.onboarding")
router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory rate limit: 1 provision call per user per 5 minutes
# ---------------------------------------------------------------------------
_provision_rate: dict[str, float] = {}
_RATE_LIMIT_SECONDS = 300  # 5 minutes


def _check_provision_rate(user_id: uuid.UUID) -> None:
    key = str(user_id)
    now = time.monotonic()
    last = _provision_rate.get(key, 0.0)
    if now - last < _RATE_LIMIT_SECONDS:
        remaining = int(_RATE_LIMIT_SECONDS - (now - last))
        raise HTTPException(
            status_code=429,
            detail=f"Provisioning rate limited. Try again in {remaining}s.",
        )
    _provision_rate[key] = now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_status() -> dict:
    return {
        "iptv": {"status": "pending", "error": None},
        "rd": {"status": "pending", "error": None},
        "library": {"status": "pending", "error": None},
        "prefs": {"status": "pending", "error": None},
    }


def _build_response(status: dict) -> ProvisionStatusResponse:
    """Build ProvisionStatusResponse from the onboarding_status JSON."""
    if status is None:
        status = _default_status()

    def _item(key: str) -> ProvisionStatusItem:
        s = status.get(key, {"status": "pending", "error": None})
        return ProvisionStatusItem(status=s.get("status", "pending"), error=s.get("error"))

    iptv = _item("iptv")
    rd = _item("rd")
    library = _item("library")
    prefs = _item("prefs")

    # IPTV failure is non-blocking
    required_done = all(
        s.status == "done" for s in [rd, library, prefs]
    )
    all_complete = required_done and iptv.status == "done"
    setup_complete = required_done

    return ProvisionStatusResponse(
        iptv=iptv,
        rd=rd,
        library=library,
        prefs=prefs,
        all_complete=all_complete,
        setup_complete=setup_complete,
    )


# ---------------------------------------------------------------------------
# POST /v1/onboarding/provision
# ---------------------------------------------------------------------------

@router.post("/onboarding/provision", response_model=ProvisionStatusResponse)
async def provision(body: ProvisionRequest, user: User = Depends(get_current_user)):
    """Orchestrate full account provisioning (IPTV, RD, Library, Prefs)."""
    _check_provision_rate(user.id)

    config = get_config()
    factory = get_session_factory()
    limits = get_tier_limits(user.tier)

    # Load current onboarding status (idempotent — skip completed steps)
    async with factory() as session:
        result = await session.execute(select(User).where(User.id == user.id))
        db_user: User = result.scalar_one()
        status = dict(db_user.onboarding_status) if db_user.onboarding_status else _default_status()

    # -----------------------------------------------------------------------
    # 1. IPTV — non-blocking
    # -----------------------------------------------------------------------
    if status["iptv"]["status"] != "done":
        if config.kemoiptv_api_url and config.kemoiptv_reseller_username:
            try:
                iptv_username = f"cutdacord_{user.id}"
                iptv_password = secrets.token_urlsafe(16)
                max_connections = limits.get("iptv_max_connections", 1)
                exp_date = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")

                async with KemoIPTVClient(
                    base_url=config.kemoiptv_api_url,
                    username=config.kemoiptv_reseller_username,
                    password=config.kemoiptv_reseller_password,
                ) as kemo:
                    await kemo.create_line(
                        line_username=iptv_username,
                        line_password=iptv_password,
                        max_connections=max_connections,
                        exp_date=exp_date,
                    )

                # Save IPTV credentials
                async with factory() as session:
                    result = await session.execute(select(User).where(User.id == user.id))
                    db_user = result.scalar_one()
                    db_user.iptv_line_username = iptv_username
                    db_user.iptv_line_password_enc = encrypt(iptv_password)
                    db_user.iptv_provisioned_at = datetime.utcnow()
                    await session.commit()

                status["iptv"] = {"status": "done", "error": None}
                logger.info("IPTV provisioned for user %s", user.id)

            except KemoIPTVError as exc:
                status["iptv"] = {"status": "failed", "error": str(exc)}
                logger.warning("IPTV provisioning failed for user %s: %s", user.id, exc)
            except Exception as exc:
                status["iptv"] = {"status": "failed", "error": str(exc)}
                logger.exception("IPTV provisioning error for user %s", user.id)
        else:
            # IPTV not configured — mark as skipped
            status["iptv"] = {"status": "done", "error": None}
            logger.info("IPTV not configured, skipping for user %s", user.id)

    # -----------------------------------------------------------------------
    # 2. Real-Debrid
    # -----------------------------------------------------------------------
    if status["rd"]["status"] != "done":
        try:
            paid_tiers = {"pro", "family", "power"}
            if user.tier in paid_tiers:
                # Paid tier: assign from pool
                async with factory() as session:
                    result = await session.execute(
                        select(RdPoolAccount)
                        .where(
                            RdPoolAccount.is_active.is_(True),
                            RdPoolAccount.current_users < RdPoolAccount.max_users,
                        )
                        .with_for_update()
                        .limit(1)
                    )
                    pool_acct: RdPoolAccount | None = result.scalar_one_or_none()

                    if pool_acct is not None:
                        pool_acct.current_users += 1

                        result2 = await session.execute(select(User).where(User.id == user.id))
                        db_user = result2.scalar_one()
                        db_user.rd_api_token_enc = pool_acct.api_token_enc
                        db_user.rd_source = "pool"
                        db_user.rd_pool_account_id = pool_acct.id
                        await session.commit()

                        status["rd"] = {"status": "done", "error": None}
                        logger.info("RD pool account %d assigned to user %s", pool_acct.id, user.id)
                    else:
                        # No pool accounts available — fall through to user-provided
                        if body.rd_api_token:
                            result2 = await session.execute(select(User).where(User.id == user.id))
                            db_user = result2.scalar_one()
                            db_user.rd_api_token_enc = encrypt(body.rd_api_token)
                            db_user.rd_source = "user_provided"
                            await session.commit()
                            status["rd"] = {"status": "done", "error": None}
                            logger.info("RD user-provided token saved for user %s (no pool available)", user.id)
                        else:
                            await session.rollback()
                            status["rd"] = {"status": "failed", "error": "No RD pool accounts available and no token provided"}
            else:
                # Free/trial: user provides own token
                if body.rd_api_token:
                    async with factory() as session:
                        result = await session.execute(select(User).where(User.id == user.id))
                        db_user = result.scalar_one()
                        db_user.rd_api_token_enc = encrypt(body.rd_api_token)
                        db_user.rd_source = "user_provided"
                        await session.commit()
                    status["rd"] = {"status": "done", "error": None}
                    logger.info("RD user-provided token saved for user %s", user.id)
                else:
                    status["rd"] = {"status": "done", "error": None}
                    logger.info("RD skipped for user %s (no token provided, starter tier)", user.id)

        except Exception as exc:
            status["rd"] = {"status": "failed", "error": str(exc)}
            logger.exception("RD provisioning error for user %s", user.id)

    # -----------------------------------------------------------------------
    # 3. Library — create per-user dirs + Arr root folders
    # -----------------------------------------------------------------------
    if status["library"]["status"] != "done":
        try:
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

            status["library"] = {"status": "done", "error": None}
            logger.info("Library provisioned for user %s", user.id)

        except Exception as exc:
            status["library"] = {"status": "failed", "error": str(exc)}
            logger.exception("Library provisioning error for user %s", user.id)

    # -----------------------------------------------------------------------
    # 4. Prefs — create/update
    # -----------------------------------------------------------------------
    if status["prefs"]["status"] != "done":
        try:
            async with factory() as session:
                result = await session.execute(
                    select(Prefs).where(Prefs.user_id == user.id)
                )
                prefs: Prefs | None = result.scalar_one_or_none()

                if prefs is None:
                    prefs = Prefs(
                        user_id=user.id,
                        max_resolution=body.preferred_resolution or limits["max_resolution"],
                        allow_4k=body.allow_4k if body.allow_4k is not None else limits["allow_4k"],
                        max_movie_size_gb=limits["max_movie_size_gb"],
                        max_episode_size_gb=limits["max_episode_size_gb"],
                    )
                    session.add(prefs)
                else:
                    if body.preferred_resolution:
                        prefs.max_resolution = body.preferred_resolution
                    if body.allow_4k is not None:
                        prefs.allow_4k = body.allow_4k

                await session.commit()

            status["prefs"] = {"status": "done", "error": None}
            logger.info("Prefs provisioned for user %s", user.id)

        except Exception as exc:
            status["prefs"] = {"status": "failed", "error": str(exc)}
            logger.exception("Prefs provisioning error for user %s", user.id)

    # -----------------------------------------------------------------------
    # Persist onboarding_status + update setup_complete
    # -----------------------------------------------------------------------
    response = _build_response(status)

    async with factory() as session:
        result = await session.execute(select(User).where(User.id == user.id))
        db_user = result.scalar_one()
        db_user.onboarding_status = status
        if response.setup_complete:
            db_user.setup_complete = True
        await session.commit()

    return response


# ---------------------------------------------------------------------------
# GET /v1/onboarding/status
# ---------------------------------------------------------------------------

@router.get("/onboarding/status", response_model=ProvisionStatusResponse)
async def provision_status(user: User = Depends(get_current_user)):
    """Return current provisioning status for frontend polling."""
    return _build_response(user.onboarding_status)
