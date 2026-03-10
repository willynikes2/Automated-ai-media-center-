"""QA and metrics digest admin endpoints."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, desc

from shared.database import get_session_factory
from shared.models import MetricsSnapshot, QARun, QAResult, User
from dependencies import require_admin

router = APIRouter()


class MetricsDigestResponse(BaseModel):
    snapshots: list[dict[str, Any]]
    count: int


class QARunSummary(BaseModel):
    id: str
    mode: str
    started_at: datetime | None
    finished_at: datetime | None
    total_scenarios: int
    passed: int
    failed: int
    errored: int
    summary: str | None


@router.get("/admin/metrics-digest", response_model=MetricsDigestResponse)
async def get_metrics_digest(
    days: int = Query(default=7, ge=1, le=90),
    user: User = Depends(require_admin),
) -> MetricsDigestResponse:
    """Return AI-readable metrics snapshots for the last N days."""
    factory = get_session_factory()
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with factory() as session:
        result = await session.execute(
            select(MetricsSnapshot)
            .where(MetricsSnapshot.snapshot_at >= cutoff)
            .order_by(desc(MetricsSnapshot.snapshot_at))
            .limit(days)
        )
        snapshots = result.scalars().all()
    return MetricsDigestResponse(
        snapshots=[s.data for s in snapshots],
        count=len(snapshots),
    )


@router.get("/admin/qa-runs", response_model=list[QARunSummary])
async def list_qa_runs(
    limit: int = Query(default=10, ge=1, le=100),
    user: User = Depends(require_admin),
) -> list[QARunSummary]:
    """List recent QA swarm runs."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(QARun)
            .order_by(desc(QARun.started_at))
            .limit(limit)
        )
        runs = result.scalars().all()
    return [
        QARunSummary(
            id=str(r.id), mode=r.mode,
            started_at=r.started_at, finished_at=r.finished_at,
            total_scenarios=r.total_scenarios, passed=r.passed,
            failed=r.failed, errored=r.errored, summary=r.summary,
        )
        for r in runs
    ]
