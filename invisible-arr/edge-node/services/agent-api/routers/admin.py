"""Admin endpoints -- RD status, VPN status."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from shared.config import get_config

logger = logging.getLogger("agent-api.admin")
router = APIRouter()


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


@router.get("/admin/rd-status", response_model=RDStatusResponse)
async def get_rd_status() -> RDStatusResponse:
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
async def get_vpn_status() -> VPNStatusResponse:
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
