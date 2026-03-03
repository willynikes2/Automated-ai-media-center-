"""Bug report endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from dependencies import get_current_user, require_admin
from shared.database import get_session_factory
from shared.models import BugReport, User
from shared.schemas import BugReportCreate, BugReportResponse, BugReportUpdate

logger = logging.getLogger("agent-api.bugs")
router = APIRouter()


@router.post("/bugs", response_model=BugReportResponse, status_code=201)
async def create_bug_report(
    body: BugReportCreate,
    user: User = Depends(get_current_user),
):
    """Submit a bug report."""
    report = BugReport(
        user_id=user.id,
        route=body.route,
        description=body.description,
        correlation_id=body.correlation_id,
        browser_info=body.browser_info,
    )
    factory = get_session_factory()
    async with factory() as session:
        session.add(report)
        await session.commit()
        await session.refresh(report)
    logger.info("Bug report %s created by user %s", report.id, user.id)
    return report


@router.get("/bugs", response_model=list[BugReportResponse])
async def get_my_bugs(user: User = Depends(get_current_user)):
    """List the current user's bug reports."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(BugReport)
            .where(BugReport.user_id == user.id)
            .order_by(BugReport.created_at.desc())
            .limit(50)
        )
        return result.scalars().all()


@router.get("/admin/bugs", response_model=list[BugReportResponse])
async def get_all_bugs(
    status: str | None = None,
    _admin: User = Depends(require_admin),
):
    """List all bug reports (admin)."""
    factory = get_session_factory()
    async with factory() as session:
        q = select(BugReport).order_by(BugReport.created_at.desc()).limit(100)
        if status:
            q = q.where(BugReport.status == status)
        result = await session.execute(q)
        return result.scalars().all()


@router.put("/admin/bugs/{bug_id}", response_model=BugReportResponse)
async def update_bug_report(
    bug_id: uuid.UUID,
    body: BugReportUpdate,
    _admin: User = Depends(require_admin),
):
    """Update a bug report status/notes (admin)."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(BugReport).where(BugReport.id == bug_id)
        )
        report = result.scalar_one_or_none()
        if report is None:
            raise HTTPException(status_code=404, detail="Bug report not found")
        if body.status is not None:
            report.status = body.status
        if body.admin_notes is not None:
            report.admin_notes = body.admin_notes
        await session.commit()
        await session.refresh(report)
    logger.info("Bug report %s updated by admin", bug_id)
    return report
