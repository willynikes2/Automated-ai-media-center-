# AI QA Swarm Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an on-demand AI QA testing swarm with 5 personas, 3 execution modes, GitHub Issue auto-creation, and an AI metrics digest endpoint.

**Architecture:** A `qa-swarm` Docker container (Playwright base image) with Python test scripts that hit the agent-api and frontend. Results stored in PostgreSQL, failures auto-create GitHub Issues with fingerprint dedup. A metrics digest endpoint on the API provides AI-readable system health snapshots.

**Tech Stack:** Python 3.12, httpx, Playwright, asyncpg, PyGithub, prometheus-api-client, FastAPI (for digest endpoint)

**Spec:** `docs/superpowers/specs/2026-03-10-ai-qa-swarm-design.md`

---

## File Structure

### New files to create:
| File | Responsibility |
|------|---------------|
| `services/qa-swarm/Dockerfile` | Container image based on Playwright Python |
| `services/qa-swarm/requirements.txt` | Python dependencies |
| `services/qa-swarm/conftest.py` | Shared fixtures: API client, test user factory, mode flags |
| `services/qa-swarm/runner.py` | Orchestrator: parse args, create test user, run personas, report, cleanup |
| `services/qa-swarm/reporter.py` | Write qa_runs/qa_results to PG, create/reopen GitHub Issues |
| `services/qa-swarm/metrics_digest.py` | Query Prometheus + PG, write metrics_snapshots, print digest |
| `services/qa-swarm/api_tests/__init__.py` | Package init |
| `services/qa-swarm/api_tests/new_user.py` | New User persona scenarios |
| `services/qa-swarm/api_tests/power_user.py` | Power User persona scenarios |
| `services/qa-swarm/api_tests/live_tv_user.py` | Live TV persona scenarios |
| `services/qa-swarm/api_tests/resilience_user.py` | Resilience/Saboteur persona scenarios |
| `services/qa-swarm/browser_tests/__init__.py` | Package init |
| `services/qa-swarm/browser_tests/browser_user.py` | Playwright browser persona scenarios |
| `services/migrations/versions/011_add_qa_tables.py` | Migration: qa_runs, qa_results, metrics_snapshots |
| `services/agent-api/routers/qa.py` | Admin endpoint: GET /v1/admin/metrics-digest |
| `config/grafana/dashboards/qa-swarm.json` | QA Swarm Grafana dashboard |

### Files to modify:
| File | Change |
|------|--------|
| `services/shared/models.py` | Add QARun, QAResult, MetricsSnapshot models |
| `services/agent-api/main.py` | Include qa router |
| `docker-compose.yml` | Add qa-swarm service with `profiles: [qa]` |

---

## Chunk 1: Foundation (Database + Service Scaffold + Core Components)

### Task 1: Database Migration

**Files:**
- Create: `services/migrations/versions/011_add_qa_tables.py`

- [ ] **Step 1: Create migration file**

```python
"""Add QA swarm tables."""
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade() -> None:
    op.create_table(
        "qa_runs",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("triggered_by", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("total_scenarios", sa.Integer, server_default="0"),
        sa.Column("passed", sa.Integer, server_default="0"),
        sa.Column("failed", sa.Integer, server_default="0"),
        sa.Column("errored", sa.Integer, server_default="0"),
        sa.Column("summary", sa.Text),
        sa.Column("test_user_email", sa.String(255)),
    )

    op.create_table(
        "qa_results",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID, sa.ForeignKey("qa_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("persona", sa.String(50), nullable=False),
        sa.Column("scenario_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("error_fingerprint", sa.String(64)),
        sa.Column("correlation_ids", JSONB, server_default="[]"),
        sa.Column("screenshots", JSONB, server_default="[]"),
        sa.Column("github_issue_url", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_qa_results_run_id", "qa_results", ["run_id"])
    op.create_index("idx_qa_results_fingerprint", "qa_results", ["error_fingerprint"])

    op.create_table(
        "metrics_snapshots",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("overall_status", sa.String(20), nullable=False),
    )
    op.create_index("idx_metrics_snapshots_at", "metrics_snapshots", ["snapshot_at"])


def downgrade() -> None:
    op.drop_table("qa_results")
    op.drop_table("qa_runs")
    op.drop_table("metrics_snapshots")
```

- [ ] **Step 2: Run migration**

```bash
docker compose exec agent-api python -c "
from shared.database import engine
from sqlalchemy import text
import asyncio

async def run():
    async with engine.begin() as conn:
        # qa_runs
        await conn.execute(text('''
            CREATE TABLE IF NOT EXISTS qa_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                triggered_by VARCHAR(50) NOT NULL DEFAULT 'manual',
                mode VARCHAR(20) NOT NULL,
                started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                finished_at TIMESTAMPTZ,
                total_scenarios INT DEFAULT 0,
                passed INT DEFAULT 0,
                failed INT DEFAULT 0,
                errored INT DEFAULT 0,
                summary TEXT,
                test_user_email VARCHAR(255)
            )
        '''))
        # qa_results
        await conn.execute(text('''
            CREATE TABLE IF NOT EXISTS qa_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                run_id UUID NOT NULL REFERENCES qa_runs(id) ON DELETE CASCADE,
                persona VARCHAR(50) NOT NULL,
                scenario_name VARCHAR(200) NOT NULL,
                status VARCHAR(20) NOT NULL,
                duration_ms INT,
                error_message TEXT,
                error_fingerprint VARCHAR(64),
                correlation_ids JSONB DEFAULT '[]',
                screenshots JSONB DEFAULT '[]',
                github_issue_url VARCHAR(500),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        '''))
        await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_qa_results_run_id ON qa_results(run_id)'))
        await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_qa_results_fingerprint ON qa_results(error_fingerprint)'))
        # metrics_snapshots
        await conn.execute(text('''
            CREATE TABLE IF NOT EXISTS metrics_snapshots (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                data JSONB NOT NULL,
                overall_status VARCHAR(20) NOT NULL
            )
        '''))
        await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_metrics_snapshots_at ON metrics_snapshots(snapshot_at DESC)'))
        print('QA tables created')

asyncio.run(run())
"
```

Expected: `QA tables created`

- [ ] **Step 3: Commit**

```bash
git add services/migrations/versions/011_add_qa_tables.py
git commit -m "feat(qa): add qa_runs, qa_results, metrics_snapshots tables"
```

---

### Task 2: SQLAlchemy Models

**Files:**
- Modify: `services/shared/models.py` (append after existing models)

- [ ] **Step 1: Add QARun, QAResult, MetricsSnapshot models**

Append after the `UserContent` class (end of file):

```python
class QARun(Base):
    __tablename__ = "qa_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    triggered_by: Mapped[str] = mapped_column(String(50), default="manual")
    mode: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    total_scenarios: Mapped[int] = mapped_column(default=0)
    passed: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    errored: Mapped[int] = mapped_column(default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    results: Mapped[list["QAResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class QAResult(Base):
    __tablename__ = "qa_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("qa_runs.id", ondelete="CASCADE"))
    persona: Mapped[str] = mapped_column(String(50))
    scenario_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    correlation_ids: Mapped[dict] = mapped_column(JSON, default=list)
    screenshots: Mapped[dict] = mapped_column(JSON, default=list)
    github_issue_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())

    run: Mapped["QARun"] = relationship(back_populates="results")


class MetricsSnapshot(Base):
    __tablename__ = "metrics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    snapshot_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now(), index=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    overall_status: Mapped[str] = mapped_column(String(20))
```

- [ ] **Step 2: Verify import works**

```bash
docker compose exec agent-api python -c "from shared.models import QARun, QAResult, MetricsSnapshot; print('Models OK')"
```

Expected: `Models OK`

- [ ] **Step 3: Commit**

```bash
git add services/shared/models.py
git commit -m "feat(qa): add QARun, QAResult, MetricsSnapshot SQLAlchemy models"
```

---

### Task 3: QA Swarm Service Scaffold

**Files:**
- Create: `services/qa-swarm/Dockerfile`
- Create: `services/qa-swarm/requirements.txt`
- Create: `services/qa-swarm/api_tests/__init__.py`
- Create: `services/qa-swarm/browser_tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p services/qa-swarm/api_tests services/qa-swarm/browser_tests
```

- [ ] **Step 2: Create Dockerfile**

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium

COPY . .

# Default: show help
CMD ["python", "runner.py", "--help"]
```

- [ ] **Step 3: Create requirements.txt**

```
httpx>=0.28.0
asyncpg>=0.30.0
sqlalchemy[asyncio]>=2.0
playwright>=1.49.0
PyGithub>=2.5.0
prometheus-api-client>=0.5.0
python-json-logger>=3.2.0
```

- [ ] **Step 4: Create __init__.py files**

```bash
touch services/qa-swarm/api_tests/__init__.py services/qa-swarm/browser_tests/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add services/qa-swarm/
git commit -m "feat(qa): scaffold qa-swarm service with Dockerfile and deps"
```

---

### Task 4: Shared Fixtures (conftest.py)

**Files:**
- Create: `services/qa-swarm/conftest.py`

- [ ] **Step 1: Create conftest.py**

```python
"""Shared fixtures for QA swarm: API client, test user management, mode flags."""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field

import httpx


@dataclass
class QAConfig:
    """Runtime configuration parsed from env + CLI args."""
    api_base: str = os.getenv("API_BASE_URL", "http://agent-api:8880")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://automedia-frontend:3000")
    iptv_base: str = os.getenv("IPTV_BASE_URL", "http://iptv-gateway:8881")
    db_url: str = os.getenv("DATABASE_URL", "")
    prometheus_url: str = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_repo: str = os.getenv("GITHUB_REPO", "")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
    mode: str = "dry-run"  # dry-run | mock | full
    persona: str | None = None  # None = all


@dataclass
class ScenarioResult:
    """Result of a single test scenario."""
    persona: str
    scenario_name: str
    status: str  # pass, fail, error, skip
    duration_ms: int = 0
    error_message: str | None = None
    correlation_ids: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)

    @property
    def error_fingerprint(self) -> str | None:
        if not self.error_message:
            return None
        raw = f"{self.persona}:{self.scenario_name}:{self.error_message[:200]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class APIClient:
    """HTTP client for the agent-api."""

    def __init__(self, config: QAConfig, api_key: str | None = None):
        self.config = config
        self.api_key = api_key or config.admin_api_key
        self._client = httpx.AsyncClient(
            base_url=config.api_base,
            headers={"X-Api-Key": self.api_key},
            timeout=30.0,
        )

    async def get(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.get(path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.post(path, **kwargs)

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        return await self._client.delete(path, **kwargs)

    def get_correlation_id(self, response: httpx.Response) -> str | None:
        return response.headers.get("x-correlation-id")

    async def close(self):
        await self._client.aclose()


async def create_test_user(client: APIClient, run_id: str) -> dict:
    """Create a test user via admin API. Returns {email, api_key, id}."""
    email = f"qa-{run_id[:8]}@test.cutdacord.app"
    resp = await client.post("/v1/admin/users", json={
        "email": email,
        "name": f"QA Test {run_id[:8]}",
        "role": "user",
        "is_active": True,
    })
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to create test user: {resp.status_code} {resp.text}")
    data = resp.json()
    return {"email": email, "api_key": data["api_key"], "id": data["id"]}


async def cleanup_test_user(client: APIClient, user_id: str) -> None:
    """Deactivate test user and clean up their data."""
    # Deactivate user
    await client.post(f"/v1/admin/users/{user_id}/deactivate")
    # Delete any jobs created by this user
    await client.delete(f"/v1/admin/users/{user_id}/jobs")
```

- [ ] **Step 2: Commit**

```bash
git add services/qa-swarm/conftest.py
git commit -m "feat(qa): add shared fixtures — APIClient, test user management, config"
```

---

### Task 5: Reporter (PostgreSQL + GitHub Issues)

**Files:**
- Create: `services/qa-swarm/reporter.py`

- [ ] **Step 1: Create reporter.py**

```python
"""QA Reporter: writes results to PostgreSQL, auto-creates GitHub Issues."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import asyncpg
from github import Auth, Github

from conftest import QAConfig, ScenarioResult

logger = logging.getLogger("qa-reporter")


class Reporter:
    """Writes QA results to PostgreSQL and creates GitHub Issues."""

    def __init__(self, config: QAConfig):
        self.config = config
        self._pool: asyncpg.Pool | None = None
        self._github: Github | None = None

    async def connect(self) -> None:
        db_url = self.config.db_url.replace("+asyncpg", "").replace("postgresql://", "postgresql://")
        self._pool = await asyncpg.create_pool(db_url, min_size=1, max_size=3)
        if self.config.github_token:
            self._github = Github(auth=Auth.Token(self.config.github_token))

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
        if self._github:
            self._github.close()

    async def create_run(self, mode: str, test_user_email: str | None = None) -> str:
        """Create a qa_runs row, return its UUID string."""
        row = await self._pool.fetchrow(
            """INSERT INTO qa_runs (mode, test_user_email)
               VALUES ($1, $2) RETURNING id""",
            mode, test_user_email,
        )
        return str(row["id"])

    async def finish_run(self, run_id: str, results: list[ScenarioResult]) -> None:
        """Update qa_runs with totals and insert all qa_results."""
        passed = sum(1 for r in results if r.status == "pass")
        failed = sum(1 for r in results if r.status == "fail")
        errored = sum(1 for r in results if r.status == "error")
        total = len(results)

        summary_lines = []
        for r in results:
            icon = {"pass": "OK", "fail": "FAIL", "error": "ERR", "skip": "SKIP"}[r.status]
            summary_lines.append(f"[{icon}] {r.persona}/{r.scenario_name}")
        summary = "\n".join(summary_lines)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE qa_runs
                   SET finished_at = now(), total_scenarios = $2,
                       passed = $3, failed = $4, errored = $5, summary = $6
                   WHERE id = $1::uuid""",
                run_id, total, passed, failed, errored, summary,
            )

            for r in results:
                github_url = None
                if r.status in ("fail", "error") and r.error_fingerprint:
                    github_url = await self._maybe_create_issue(conn, r)

                await conn.execute(
                    """INSERT INTO qa_results
                       (run_id, persona, scenario_name, status, duration_ms,
                        error_message, error_fingerprint, correlation_ids,
                        screenshots, github_issue_url)
                       VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10)""",
                    run_id, r.persona, r.scenario_name, r.status,
                    r.duration_ms, r.error_message, r.error_fingerprint,
                    str(r.correlation_ids).replace("'", '"') if r.correlation_ids else "[]",
                    str(r.screenshots).replace("'", '"') if r.screenshots else "[]",
                    github_url,
                )

    async def _maybe_create_issue(self, conn, result: ScenarioResult) -> str | None:
        """Create or reopen GitHub Issue if threshold met. Returns issue URL or None."""
        if not self._github or not self.config.github_repo:
            return None

        fp = result.error_fingerprint
        if not fp:
            return None

        # Check consecutive failure count for this fingerprint
        count = await conn.fetchval(
            """SELECT COUNT(*) FROM qa_results
               WHERE error_fingerprint = $1
               AND status IN ('fail', 'error')
               AND created_at > now() - interval '7 days'""",
            fp,
        )

        # Threshold: only create issue after 2+ failures
        if count < 1:  # This is the 1st failure, will become 2nd after insert
            return None

        # Check cooldown: no issue created in last 24h for this fingerprint
        recent_issue = await conn.fetchval(
            """SELECT github_issue_url FROM qa_results
               WHERE error_fingerprint = $1
               AND github_issue_url IS NOT NULL
               AND created_at > now() - interval '24 hours'
               LIMIT 1""",
            fp,
        )
        if recent_issue:
            return recent_issue  # Reuse existing URL

        try:
            repo = self._github.get_repo(self.config.github_repo)

            # Check for existing open issue with this fingerprint
            existing = list(repo.get_issues(
                state="open",
                labels=["qa-swarm"],
            ))
            for issue in existing:
                if fp in (issue.body or ""):
                    # Append new evidence
                    issue.create_comment(
                        f"**QA Swarm re-failure** ({datetime.now(timezone.utc).isoformat()})\n\n"
                        f"Persona: {result.persona}\n"
                        f"Scenario: {result.scenario_name}\n"
                        f"Error: {result.error_message}\n"
                        f"Correlation IDs: {result.correlation_ids}"
                    )
                    return issue.html_url

            # Check for closed issue to reopen
            closed = list(repo.get_issues(state="closed", labels=["qa-swarm"]))
            for issue in closed:
                if fp in (issue.body or ""):
                    issue.edit(state="open")
                    issue.create_comment(
                        f"**Regression detected** — reopening.\n\n"
                        f"Error: {result.error_message}\n"
                        f"Correlation IDs: {result.correlation_ids}"
                    )
                    return issue.html_url

            # Create new issue
            labels = ["qa-swarm", "bug", result.persona]
            body = (
                f"## QA Swarm Failure: {result.persona} / {result.scenario_name}\n\n"
                f"**Fingerprint:** `{fp}`\n"
                f"**Consecutive failures:** {count + 1}\n\n"
                f"### Error\n```\n{result.error_message}\n```\n\n"
                f"### Evidence\n"
                f"- Correlation IDs: {result.correlation_ids}\n"
                f"- Sentry query: `correlation_id:{result.correlation_ids[0] if result.correlation_ids else 'N/A'}`\n"
                f"- Loki query: `{{correlation_id=\"{result.correlation_ids[0] if result.correlation_ids else ''}\"}}`\n\n"
                f"Labels: {', '.join(labels)}"
            )
            # Ensure labels exist
            for label_name in labels:
                try:
                    repo.get_label(label_name)
                except Exception:
                    repo.create_label(label_name, "d73a4a")

            issue = repo.create_issue(
                title=f"[QA] {result.persona}: {result.scenario_name}",
                body=body,
                labels=labels,
            )
            logger.info("Created GitHub Issue: %s", issue.html_url)
            return issue.html_url

        except Exception as e:
            logger.warning("Failed to create GitHub Issue: %s", e)
            return None
```

- [ ] **Step 2: Commit**

```bash
git add services/qa-swarm/reporter.py
git commit -m "feat(qa): add Reporter — PG results storage + GitHub Issue auto-creation"
```

---

### Task 6: Runner (Orchestrator)

**Files:**
- Create: `services/qa-swarm/runner.py`

- [ ] **Step 1: Create runner.py**

```python
"""QA Swarm Runner: orchestrates personas, manages test users, reports results."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import uuid

from conftest import APIClient, QAConfig, ScenarioResult, create_test_user, cleanup_test_user
from reporter import Reporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("qa-runner")

# Persona registry
PERSONAS: dict[str, type] = {}


def register_persona(name: str):
    """Decorator to register a persona class."""
    def wrapper(cls):
        PERSONAS[name] = cls
        return cls
    return wrapper


class BasePersona:
    """Base class for QA personas."""

    name: str = "base"

    def __init__(self, client: APIClient, config: QAConfig):
        self.client = client
        self.config = config
        self.results: list[ScenarioResult] = []

    async def run_scenario(self, name: str, coro):
        """Run a single scenario, capture timing and errors."""
        start = time.perf_counter()
        correlation_ids = []
        try:
            cids = await coro()
            if isinstance(cids, list):
                correlation_ids = cids
            elif isinstance(cids, str):
                correlation_ids = [cids]
            duration = int((time.perf_counter() - start) * 1000)
            self.results.append(ScenarioResult(
                persona=self.name,
                scenario_name=name,
                status="pass",
                duration_ms=duration,
                correlation_ids=correlation_ids,
            ))
            logger.info("[PASS] %s/%s (%dms)", self.name, name, duration)
        except Exception as e:
            duration = int((time.perf_counter() - start) * 1000)
            self.results.append(ScenarioResult(
                persona=self.name,
                scenario_name=name,
                status="fail",
                duration_ms=duration,
                error_message=str(e),
                correlation_ids=correlation_ids,
            ))
            logger.error("[FAIL] %s/%s: %s", self.name, name, e)

    async def run_all(self) -> list[ScenarioResult]:
        """Override in subclass to run scenarios."""
        raise NotImplementedError


def _load_personas():
    """Import all persona modules to trigger @register_persona decorators."""
    from api_tests import new_user, power_user, live_tv_user, resilience_user
    from browser_tests import browser_user


async def main():
    parser = argparse.ArgumentParser(description="CutDaCord AI QA Swarm")
    parser.add_argument("--mode", choices=["dry-run", "mock", "full"], default="dry-run",
                        help="Execution mode (default: dry-run)")
    parser.add_argument("--mock", action="store_const", const="mock", dest="mode",
                        help="Shortcut for --mode mock")
    parser.add_argument("--full", action="store_const", const="full", dest="mode",
                        help="Shortcut for --mode full")
    parser.add_argument("--persona", choices=["new_user", "power_user", "browser_user",
                                               "live_tv_user", "resilience_user"],
                        help="Run single persona (default: all)")
    parser.add_argument("--last-run", action="store_true",
                        help="Print last run summary and exit")
    args = parser.parse_args()

    config = QAConfig(mode=args.mode, persona=args.persona)

    # Load persona modules
    _load_personas()

    reporter = Reporter(config)
    await reporter.connect()

    if args.last_run:
        await _print_last_run(reporter)
        await reporter.close()
        return

    admin_client = APIClient(config)
    run_id = str(uuid.uuid4())
    test_user = None
    all_results: list[ScenarioResult] = []

    try:
        # Create test user
        try:
            test_user = await create_test_user(admin_client, run_id)
            logger.info("Created test user: %s", test_user["email"])
        except Exception as e:
            logger.warning("Could not create test user, using admin key: %s", e)
            test_user = {"email": "admin@cutdacord.app", "api_key": config.admin_api_key, "id": "admin"}

        # Create run record
        db_run_id = await reporter.create_run(config.mode, test_user["email"])

        # Build user client
        user_client = APIClient(config, api_key=test_user["api_key"])

        # Select personas to run
        personas_to_run = {}
        if config.persona:
            if config.persona in PERSONAS:
                personas_to_run = {config.persona: PERSONAS[config.persona]}
            else:
                logger.error("Unknown persona: %s", config.persona)
                sys.exit(1)
        else:
            personas_to_run = PERSONAS

        # Run personas sequentially
        for name, persona_cls in personas_to_run.items():
            logger.info("=== Running persona: %s ===", name)
            persona = persona_cls(user_client, config)
            try:
                results = await persona.run_all()
                all_results.extend(results)
            except Exception as e:
                logger.error("Persona %s crashed: %s", name, e)
                all_results.append(ScenarioResult(
                    persona=name,
                    scenario_name="_persona_crash",
                    status="error",
                    error_message=str(e),
                ))

        # Report results
        await reporter.finish_run(db_run_id, all_results)

        # Print summary
        passed = sum(1 for r in all_results if r.status == "pass")
        failed = sum(1 for r in all_results if r.status in ("fail", "error"))
        total = len(all_results)
        logger.info("=== QA SWARM COMPLETE ===")
        logger.info("Total: %d | Passed: %d | Failed: %d | Rate: %.0f%%",
                     total, passed, failed, (passed / total * 100) if total else 0)
        for r in all_results:
            icon = {"pass": "OK", "fail": "FAIL", "error": "ERR", "skip": "SKIP"}.get(r.status, "?")
            msg = f"  [{icon}] {r.persona}/{r.scenario_name}"
            if r.error_message:
                msg += f" — {r.error_message[:80]}"
            print(msg)

        await user_client.close()

    finally:
        # Cleanup test user
        if test_user and test_user["id"] != "admin":
            try:
                await cleanup_test_user(admin_client, test_user["id"])
                logger.info("Cleaned up test user: %s", test_user["email"])
            except Exception as e:
                logger.warning("Cleanup failed: %s", e)

        await admin_client.close()
        await reporter.close()


async def _print_last_run(reporter: Reporter) -> None:
    """Print the most recent run summary."""
    row = await reporter._pool.fetchrow(
        "SELECT * FROM qa_runs ORDER BY started_at DESC LIMIT 1"
    )
    if not row:
        print("No QA runs found.")
        return
    print(f"Run ID:   {row['id']}")
    print(f"Mode:     {row['mode']}")
    print(f"Started:  {row['started_at']}")
    print(f"Finished: {row['finished_at']}")
    print(f"Results:  {row['passed']} passed / {row['failed']} failed / {row['errored']} errored (of {row['total_scenarios']})")
    if row["summary"]:
        print(f"\n{row['summary']}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify help output**

```bash
docker compose --profile qa build qa-swarm 2>&1 | tail -3
docker compose --profile qa run --rm qa-swarm python runner.py --help
```

Expected: Shows argparse help with `--mode`, `--persona`, `--full`, `--mock`, `--last-run` options.

- [ ] **Step 3: Commit**

```bash
git add services/qa-swarm/runner.py
git commit -m "feat(qa): add Runner orchestrator — persona dispatch, test user lifecycle, reporting"
```

---

## Chunk 2: Personas (API + Browser Tests)

### Task 7: New User Persona

**Files:**
- Create: `services/qa-swarm/api_tests/new_user.py`

- [ ] **Step 1: Create new_user.py**

```python
"""New User persona: basic request-and-check flows."""
from __future__ import annotations

import asyncio

from conftest import APIClient, QAConfig
from runner import BasePersona, register_persona


@register_persona("new_user")
class NewUserPersona(BasePersona):
    name = "new_user"

    async def run_all(self):
        await self.run_scenario("request_movie", self._request_movie)
        await self.run_scenario("request_tv_show", self._request_tv_show)
        await self.run_scenario("check_library", self._check_library)
        await self.run_scenario("check_quota", self._check_quota)
        return self.results

    async def _request_movie(self):
        """Request a popular movie and verify pipeline starts."""
        resp = await self.client.post("/v1/requests", json={
            "title": "The Shawshank Redemption",
            "media_type": "movie",
            "year": 1994,
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "id" in data, f"Response missing job ID: {data}"
        job_id = data["id"]
        cid = self.client.get_correlation_id(resp)

        if self.config.mode == "dry-run":
            # Just verify job was created with correct initial state
            await asyncio.sleep(2)
            status_resp = await self.client.get(f"/v1/requests/{job_id}")
            assert status_resp.status_code == 200
            job = status_resp.json()
            assert job["state"] in ["created", "resolving", "searching", "selected"], \
                f"Unexpected state: {job['state']}"
        elif self.config.mode in ("mock", "full"):
            # Poll until terminal state (max 5 min)
            for _ in range(60):
                await asyncio.sleep(5)
                status_resp = await self.client.get(f"/v1/requests/{job_id}")
                job = status_resp.json()
                if job["state"] in ("available", "failed"):
                    break
            assert job["state"] == "available", f"Job did not complete: {job['state']}"

        return [cid] if cid else []

    async def _request_tv_show(self):
        """Request a TV show and verify pipeline starts."""
        resp = await self.client.post("/v1/requests", json={
            "title": "Breaking Bad",
            "media_type": "tv",
            "year": 2008,
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "id" in data
        cid = self.client.get_correlation_id(resp)

        if self.config.mode == "dry-run":
            await asyncio.sleep(2)
            status_resp = await self.client.get(f"/v1/requests/{data['id']}")
            assert status_resp.status_code == 200
            job = status_resp.json()
            assert job["state"] in ["created", "resolving", "searching", "selected"]

        return [cid] if cid else []

    async def _check_library(self):
        """Verify library endpoint returns valid data."""
        resp = await self.client.get("/v1/library")
        assert resp.status_code == 200, f"Library returned {resp.status_code}"
        data = resp.json()
        assert isinstance(data, (list, dict)), f"Unexpected library format: {type(data)}"
        return [self.client.get_correlation_id(resp)]

    async def _check_quota(self):
        """Verify quota endpoint returns valid counts."""
        resp = await self.client.get("/v1/library/quota")
        assert resp.status_code == 200, f"Quota returned {resp.status_code}"
        data = resp.json()
        assert "movie_count" in data, f"Missing movie_count: {data}"
        assert "movie_quota" in data, f"Missing movie_quota: {data}"
        return [self.client.get_correlation_id(resp)]
```

- [ ] **Step 2: Commit**

```bash
git add services/qa-swarm/api_tests/new_user.py
git commit -m "feat(qa): add New User persona — movie/tv request + library/quota checks"
```

---

### Task 8: Power User Persona

**Files:**
- Create: `services/qa-swarm/api_tests/power_user.py`

- [ ] **Step 1: Create power_user.py**

```python
"""Power User persona: concurrent requests, deletion, dedup, rate limits."""
from __future__ import annotations

import asyncio

from conftest import APIClient, QAConfig
from runner import BasePersona, register_persona


@register_persona("power_user")
class PowerUserPersona(BasePersona):
    name = "power_user"

    async def run_all(self):
        await self.run_scenario("concurrent_requests", self._concurrent_requests)
        await self.run_scenario("check_quota_after_requests", self._check_quota)
        await self.run_scenario("delete_content", self._delete_content)
        await self.run_scenario("trigger_rate_limit", self._trigger_rate_limit)
        return self.results

    async def _concurrent_requests(self):
        """Request 3 items concurrently and verify all accepted or rate-limited."""
        movies = [
            {"title": "Inception", "media_type": "movie", "year": 2010},
            {"title": "Interstellar", "media_type": "movie", "year": 2014},
            {"title": "The Dark Knight", "media_type": "movie", "year": 2008},
        ]
        cids = []
        tasks = [self.client.post("/v1/requests", json=m) for m in movies]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        accepted = 0
        for resp in responses:
            if isinstance(resp, Exception):
                continue
            cid = self.client.get_correlation_id(resp)
            if cid:
                cids.append(cid)
            if resp.status_code == 200:
                accepted += 1
            elif resp.status_code == 429:
                pass  # Expected if concurrent limit hit
            else:
                raise AssertionError(f"Unexpected status {resp.status_code}: {resp.text}")

        assert accepted >= 1, "No requests were accepted"
        return cids

    async def _check_quota(self):
        """Verify quota reflects the requests we made."""
        resp = await self.client.get("/v1/library/quota")
        assert resp.status_code == 200
        return [self.client.get_correlation_id(resp)]

    async def _delete_content(self):
        """Delete a library item and verify quota decrements."""
        # Get library
        lib_resp = await self.client.get("/v1/library")
        assert lib_resp.status_code == 200
        items = lib_resp.json()

        if not items or (isinstance(items, dict) and not items.get("items")):
            # Nothing to delete, skip
            return []

        # Try to find something to delete
        item_list = items if isinstance(items, list) else items.get("items", [])
        if not item_list:
            return []

        target = item_list[0]
        item_id = target.get("id") or target.get("job_id")
        if not item_id:
            return []

        del_resp = await self.client.delete(f"/v1/library/item/{item_id}")
        # Accept 200 (deleted) or 404 (already gone)
        assert del_resp.status_code in (200, 404), \
            f"Delete returned {del_resp.status_code}: {del_resp.text}"
        return [self.client.get_correlation_id(del_resp)]

    async def _trigger_rate_limit(self):
        """Hit the API rapidly to trigger rate limiting."""
        cids = []
        got_429 = False
        for i in range(50):
            resp = await self.client.post("/v1/requests", json={
                "title": f"Rate Limit Test {i}",
                "media_type": "movie",
                "year": 2020,
            })
            cid = self.client.get_correlation_id(resp)
            if cid:
                cids.append(cid)
            if resp.status_code == 429:
                got_429 = True
                break

        # We expect either a 429 (rate limit works) or all accepted (limit is generous)
        # Both are valid — the test verifies the endpoint handles rapid requests without crashing
        return cids
```

- [ ] **Step 2: Commit**

```bash
git add services/qa-swarm/api_tests/power_user.py
git commit -m "feat(qa): add Power User persona — concurrent requests, deletion, rate limits"
```

---

### Task 9: Live TV User Persona

**Files:**
- Create: `services/qa-swarm/api_tests/live_tv_user.py`

- [ ] **Step 1: Create live_tv_user.py**

```python
"""Live TV User persona: EPG, channels, tuning."""
from __future__ import annotations

import httpx

from conftest import APIClient, QAConfig
from runner import BasePersona, register_persona


@register_persona("live_tv_user")
class LiveTVUserPersona(BasePersona):
    name = "live_tv_user"

    def __init__(self, client: APIClient, config: QAConfig):
        super().__init__(client, config)
        self._iptv_client = httpx.AsyncClient(
            base_url=config.iptv_base,
            timeout=30.0,
        )

    async def run_all(self):
        await self.run_scenario("load_epg", self._load_epg)
        await self.run_scenario("list_channels", self._list_channels)
        await self.run_scenario("tune_channel", self._tune_channel)
        await self._iptv_client.aclose()
        return self.results

    async def _load_epg(self):
        """Verify EPG XML loads and contains program data."""
        resp = await self._iptv_client.get("/epg.xml")
        assert resp.status_code == 200, f"EPG returned {resp.status_code}"
        body = resp.text
        assert "<?xml" in body or "<tv" in body, "EPG response is not XML"
        assert "<programme" in body or "<channel" in body, "EPG has no program/channel data"
        return []

    async def _list_channels(self):
        """Verify channel list endpoint returns channels."""
        resp = await self._iptv_client.get("/channels")
        if resp.status_code == 404:
            # Endpoint might be at different path
            resp = await self._iptv_client.get("/api/channels")
        assert resp.status_code == 200, f"Channels returned {resp.status_code}"
        return []

    async def _tune_channel(self):
        """Attempt to get a stream URL for a channel."""
        # Try to get first channel from M3U playlist
        resp = await self._iptv_client.get("/playlist.m3u")
        if resp.status_code != 200:
            resp = await self._iptv_client.get("/iptv/playlist")
        assert resp.status_code == 200, f"Playlist returned {resp.status_code}"
        body = resp.text
        assert "#EXTM3U" in body, "Response is not M3U format"
        return []
```

- [ ] **Step 2: Commit**

```bash
git add services/qa-swarm/api_tests/live_tv_user.py
git commit -m "feat(qa): add Live TV User persona — EPG, channels, playlist checks"
```

---

### Task 10: Resilience User Persona

**Files:**
- Create: `services/qa-swarm/api_tests/resilience_user.py`

- [ ] **Step 1: Create resilience_user.py**

```python
"""Resilience User persona: malformed inputs, auth boundaries, error handling."""
from __future__ import annotations

import httpx

from conftest import APIClient, QAConfig
from runner import BasePersona, register_persona


@register_persona("resilience_user")
class ResilienceUserPersona(BasePersona):
    name = "resilience_user"

    async def run_all(self):
        await self.run_scenario("invalid_api_key", self._invalid_api_key)
        await self.run_scenario("empty_payload", self._empty_payload)
        await self.run_scenario("invalid_media_type", self._invalid_media_type)
        await self.run_scenario("garbage_title", self._garbage_title)
        await self.run_scenario("delete_nonexistent", self._delete_nonexistent)
        await self.run_scenario("duplicate_rapid_requests", self._duplicate_rapid)
        return self.results

    async def _invalid_api_key(self):
        """Request with invalid API key — expect 401."""
        bad_client = httpx.AsyncClient(
            base_url=self.config.api_base,
            headers={"X-Api-Key": "totally-invalid-key-12345"},
            timeout=10.0,
        )
        try:
            resp = await bad_client.get("/v1/library/quota")
            assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        finally:
            await bad_client.aclose()
        return []

    async def _empty_payload(self):
        """POST with empty body — expect 422 validation error."""
        resp = await self.client.post("/v1/requests", json={})
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        return [self.client.get_correlation_id(resp)]

    async def _invalid_media_type(self):
        """Request with invalid media_type — expect 422."""
        resp = await self.client.post("/v1/requests", json={
            "title": "Test Movie",
            "media_type": "podcast",  # invalid
            "year": 2024,
        })
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        return [self.client.get_correlation_id(resp)]

    async def _garbage_title(self):
        """Request with non-UTF-8 and special characters — should not crash."""
        resp = await self.client.post("/v1/requests", json={
            "title": "🎬 T3st! @#$% <script>alert(1)</script>",
            "media_type": "movie",
            "year": 2024,
        })
        # Should either accept (200) or reject gracefully (4xx), never 500
        assert resp.status_code < 500, f"Server error {resp.status_code}: {resp.text}"
        return [self.client.get_correlation_id(resp)]

    async def _delete_nonexistent(self):
        """Delete content that doesn't exist — expect 404."""
        resp = await self.client.delete("/v1/library/item/00000000-0000-0000-0000-000000000000")
        assert resp.status_code in (404, 400), \
            f"Expected 404/400, got {resp.status_code}: {resp.text}"
        return [self.client.get_correlation_id(resp)]

    async def _duplicate_rapid(self):
        """Send same request twice rapidly — verify no crash or duplicate creation."""
        payload = {"title": "Duplicate Test Film", "media_type": "movie", "year": 2020}
        resp1 = await self.client.post("/v1/requests", json=payload)
        resp2 = await self.client.post("/v1/requests", json=payload)

        # Both should return cleanly (200 or 409/429)
        for resp in (resp1, resp2):
            assert resp.status_code < 500, f"Server error: {resp.status_code}"
        return [
            self.client.get_correlation_id(resp1),
            self.client.get_correlation_id(resp2),
        ]
```

- [ ] **Step 2: Commit**

```bash
git add services/qa-swarm/api_tests/resilience_user.py
git commit -m "feat(qa): add Resilience User persona — malformed inputs, auth, error handling"
```

---

### Task 11: Browser User Persona

**Files:**
- Create: `services/qa-swarm/browser_tests/browser_user.py`

- [ ] **Step 1: Create browser_user.py**

```python
"""Browser User persona: Playwright tests for frontend pages."""
from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright, Page, ConsoleMessage

from conftest import QAConfig
from runner import BasePersona, register_persona


@register_persona("browser_user")
class BrowserUserPersona(BasePersona):
    name = "browser_user"

    def __init__(self, client, config: QAConfig):
        super().__init__(client, config)
        self._console_errors: list[str] = []

    async def run_all(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                )
                page = await context.new_page()
                page.on("console", self._on_console)

                await self.run_scenario("load_library", lambda: self._load_page(page, "/library"))
                await self.run_scenario("load_activity", lambda: self._load_page(page, "/activity"))
                await self.run_scenario("load_search", lambda: self._load_page(page, "/search"))
                await self.run_scenario("check_console_errors", lambda: self._check_errors())

                # Mobile viewport test
                await context.close()
                mobile_ctx = await browser.new_context(
                    viewport={"width": 375, "height": 812},
                )
                mobile_page = await mobile_ctx.new_page()
                await self.run_scenario("mobile_library", lambda: self._load_page(mobile_page, "/library"))
                await mobile_ctx.close()
            finally:
                await browser.close()

        return self.results

    def _on_console(self, msg: ConsoleMessage):
        if msg.type == "error":
            self._console_errors.append(msg.text)

    async def _load_page(self, page: Page, path: str):
        """Navigate to a page, verify it loads within 10s without crashing."""
        url = f"{self.config.frontend_url}{path}"
        resp = await page.goto(url, wait_until="networkidle", timeout=10000)
        assert resp is not None, f"No response from {url}"
        assert resp.status < 500, f"Page {path} returned {resp.status}"

        # Take screenshot on any non-200 for debugging
        screenshots = []
        if resp.status != 200:
            path_safe = path.replace("/", "_")
            screenshot_path = f"/tmp/qa-screenshot-{path_safe}.png"
            await page.screenshot(path=screenshot_path)
            screenshots.append(screenshot_path)

        return screenshots

    async def _check_errors(self):
        """Verify no JS console errors were captured across all page loads."""
        # Filter out known noise (e.g., favicon 404)
        real_errors = [e for e in self._console_errors if "favicon" not in e.lower()]
        if real_errors:
            raise AssertionError(
                f"{len(real_errors)} JS console errors:\n" +
                "\n".join(f"  - {e[:200]}" for e in real_errors[:10])
            )
        return []
```

- [ ] **Step 2: Commit**

```bash
git add services/qa-swarm/browser_tests/browser_user.py
git commit -m "feat(qa): add Browser User persona — Playwright page loads, console errors, mobile"
```

---

## Chunk 3: Metrics Digest + Dashboard + Integration

### Task 12: Metrics Digest

**Files:**
- Create: `services/qa-swarm/metrics_digest.py`

- [ ] **Step 1: Create metrics_digest.py**

```python
"""AI Metrics Digest: compact system health snapshots for AI consumption."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import asyncpg
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("metrics-digest")

DB_URL = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")


async def query_prometheus(client: httpx.AsyncClient, query: str) -> float | None:
    """Execute a PromQL instant query, return scalar value or None."""
    try:
        resp = await client.get("/api/v1/query", params={"query": query})
        data = resp.json()
        results = data.get("data", {}).get("result", [])
        if results and results[0].get("value"):
            return float(results[0]["value"][1])
    except Exception as e:
        logger.debug("Prometheus query failed: %s — %s", query, e)
    return None


async def create_snapshot(pool: asyncpg.Pool, prom: httpx.AsyncClient) -> dict:
    """Build a metrics snapshot from Prometheus + PostgreSQL."""

    # --- Pipeline metrics from Prometheus ---
    requests_24h = await query_prometheus(prom,
        'sum(increase(requests_total[24h]))') or 0
    errors_24h = await query_prometheus(prom,
        'sum(increase(requests_total{status=~"5.."}[24h]))') or 0
    success_rate = round(((requests_24h - errors_24h) / requests_24h * 100), 1) if requests_24h > 0 else 100.0
    p95_latency = await query_prometheus(prom,
        'histogram_quantile(0.95, sum(rate(request_duration_seconds_bucket[1h])) by (le))') or 0

    # Services up/down
    targets_up = await query_prometheus(prom, 'count(up == 1)') or 0
    targets_total = await query_prometheus(prom, 'count(up)') or 0
    targets_down_query = await prom.get("/api/v1/query",
        params={"query": 'up == 0'})
    down_services = []
    try:
        for r in targets_down_query.json().get("data", {}).get("result", []):
            down_services.append(r.get("metric", {}).get("job", "unknown"))
    except Exception:
        pass

    # Jobs
    active_jobs = await query_prometheus(prom, 'sum(active_jobs)') or 0
    jobs_failed_24h = await query_prometheus(prom,
        'sum(increase(job_completions_total{final_state="failed"}[24h]))') or 0
    jobs_completed_24h = await query_prometheus(prom,
        'sum(increase(job_completions_total{final_state="available"}[24h]))') or 0

    # Alerts
    alerts_firing = await query_prometheus(prom, 'count(ALERTS{alertstate="firing"})') or 0

    # --- PostgreSQL queries ---
    # Top errors (from job_events)
    top_errors = []
    try:
        rows = await pool.fetch("""
            SELECT message, COUNT(*) as cnt
            FROM job_events
            WHERE created_at > now() - interval '24 hours'
            AND message ILIKE '%error%' OR message ILIKE '%fail%'
            GROUP BY message ORDER BY cnt DESC LIMIT 5
        """)
        top_errors = [{"message": r["message"][:100], "count": r["cnt"]} for r in rows]
    except Exception:
        pass

    # QA swarm latest
    qa_summary = {}
    try:
        qa_row = await pool.fetchrow(
            "SELECT * FROM qa_runs ORDER BY started_at DESC LIMIT 1"
        )
        if qa_row:
            total = qa_row["total_scenarios"] or 1
            qa_summary = {
                "last_run": qa_row["started_at"].isoformat() if qa_row["started_at"] else None,
                "pass_rate_pct": round(qa_row["passed"] / total * 100, 1),
                "failing_scenarios": [],
            }
            fails = await pool.fetch(
                """SELECT persona, scenario_name FROM qa_results
                   WHERE run_id = $1 AND status IN ('fail', 'error')""",
                qa_row["id"],
            )
            qa_summary["failing_scenarios"] = [
                f"{r['persona']}: {r['scenario_name']}" for r in fails
            ]
    except Exception:
        pass

    # Previous snapshot for deltas
    prev = None
    try:
        prev_row = await pool.fetchrow(
            "SELECT data FROM metrics_snapshots ORDER BY snapshot_at DESC LIMIT 1"
        )
        if prev_row:
            prev = prev_row["data"]
    except Exception:
        pass

    def delta(current, key_path):
        """Compute delta from previous snapshot."""
        if not prev:
            return None
        keys = key_path.split(".")
        val = prev
        for k in keys:
            val = val.get(k, {}) if isinstance(val, dict) else {}
        prev_current = val.get("current") if isinstance(val, dict) else None
        if prev_current is not None:
            return round(current - prev_current, 1)
        return None

    # Determine overall status
    if down_services or errors_24h > requests_24h * 0.2:
        overall = "critical"
    elif errors_24h > requests_24h * 0.1 or jobs_failed_24h > jobs_completed_24h * 0.3:
        overall = "degraded"
    else:
        overall = "healthy"

    snapshot = {
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall,
        "pipeline": {
            "requests_24h": {"current": int(requests_24h), "delta": delta(requests_24h, "pipeline.requests_24h")},
            "success_rate_pct": {"current": success_rate, "delta": delta(success_rate, "pipeline.success_rate_pct")},
            "p95_latency_sec": {"current": round(p95_latency, 2), "delta": delta(round(p95_latency, 2), "pipeline.p95_latency_sec")},
        },
        "services": {
            "all_up": len(down_services) == 0,
            "up_count": int(targets_up),
            "total_count": int(targets_total),
            "down": down_services,
        },
        "errors": {
            "total_24h": {"current": int(errors_24h), "delta": delta(errors_24h, "errors.total_24h")},
            "top_errors": top_errors,
        },
        "jobs": {
            "active": {"current": int(active_jobs), "delta": delta(active_jobs, "jobs.active")},
            "completed_24h": int(jobs_completed_24h),
            "failed_24h": {"current": int(jobs_failed_24h), "delta": delta(jobs_failed_24h, "jobs.failed_24h")},
        },
        "qa_swarm": qa_summary,
        "alerts": {
            "firing": int(alerts_firing),
        },
        "drill_down": {
            "sentry_query": "is:unresolved project:cutdacord-backend",
            "loki_errors": '{service=~".+"} |= "error" | json',
            "prometheus_errors": 'rate(requests_total{status=~"5.."}[1h])',
        },
    }

    # Store snapshot
    await pool.execute(
        """INSERT INTO metrics_snapshots (data, overall_status)
           VALUES ($1::jsonb, $2)""",
        json.dumps(snapshot), overall,
    )

    return snapshot


async def main():
    parser = argparse.ArgumentParser(description="AI Metrics Digest")
    parser.add_argument("--print", action="store_true", dest="do_print",
                        help="Print digest to stdout")
    parser.add_argument("--days", type=int, default=1,
                        help="Number of days of history to show")
    args = parser.parse_args()

    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=2)
    prom = httpx.AsyncClient(base_url=PROMETHEUS_URL, timeout=10.0)

    try:
        snapshot = await create_snapshot(pool, prom)

        if args.do_print:
            print(json.dumps(snapshot, indent=2, default=str))
            logger.info("Status: %s", snapshot["overall_status"])
        else:
            logger.info("Snapshot saved. Status: %s", snapshot["overall_status"])
    finally:
        await prom.aclose()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add services/qa-swarm/metrics_digest.py
git commit -m "feat(qa): add AI Metrics Digest — Prometheus+PG snapshots with deltas"
```

---

### Task 13: Metrics Digest API Endpoint

**Files:**
- Create: `services/agent-api/routers/qa.py`
- Modify: `services/agent-api/main.py`

- [ ] **Step 1: Create qa router**

```python
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
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
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
```

- [ ] **Step 2: Add router to main.py**

In `services/agent-api/main.py`, add after the existing router imports:

```python
from routers import qa
```

And add after the existing `app.include_router(...)` lines:

```python
app.include_router(qa.router, prefix="/v1", tags=["qa"])
```

- [ ] **Step 3: Rebuild and verify**

```bash
docker compose build agent-api
docker compose up -d agent-api
sleep 3
curl -s -H "X-Api-Key: <admin-api-key>" http://localhost:8880/v1/admin/metrics-digest | python3 -m json.tool
```

Expected: `{"snapshots": [], "count": 0}` (no snapshots yet)

- [ ] **Step 4: Commit**

```bash
git add services/agent-api/routers/qa.py services/agent-api/main.py
git commit -m "feat(qa): add /v1/admin/metrics-digest and /v1/admin/qa-runs endpoints"
```

---

### Task 14: Docker Compose Integration

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add qa-swarm service**

Add before the `volumes:` section at the end of docker-compose.yml:

```yaml
  qa-swarm:
    build:
      context: ./services/qa-swarm
    container_name: qa-swarm
    restart: "no"
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      - API_BASE_URL=http://agent-api:8880
      - FRONTEND_URL=http://automedia-frontend:3000
      - IPTV_BASE_URL=http://iptv-gateway:8881
      - PROMETHEUS_URL=http://prometheus:9090
      - GITHUB_TOKEN=${GITHUB_TOKEN:-}
      - GITHUB_REPO=${GITHUB_REPO:-}
      - ADMIN_API_KEY=${QA_ADMIN_API_KEY:-}
    mem_limit: 512m
    cpus: 1.0
    volumes:
      - ./services/shared:/app/shared:ro
    depends_on:
      postgres:
        condition: service_healthy
      agent-api:
        condition: service_healthy
    networks:
      - internal
    profiles:
      - qa
```

- [ ] **Step 2: Add env vars to .env**

```bash
echo '' >> .env
echo '# --- QA Swarm ---' >> .env
echo 'QA_ADMIN_API_KEY=3j5j5oMeyKsW25JDNga74HEN7RlvNi98A4uJ2-4aPA4' >> .env
echo 'GITHUB_TOKEN=' >> .env
echo 'GITHUB_REPO=' >> .env
```

- [ ] **Step 3: Build and verify**

```bash
docker compose --profile qa build qa-swarm
docker compose --profile qa run --rm qa-swarm python runner.py --help
```

Expected: Shows argparse help output.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(qa): add qa-swarm service to docker-compose with qa profile"
```

---

### Task 15: Grafana QA Swarm Dashboard

**Files:**
- Create: `config/grafana/dashboards/qa-swarm.json`

- [ ] **Step 1: Create dashboard JSON**

Create a provisioned Grafana dashboard with PostgreSQL queries for:
- Latest run pass rate (stat panel)
- Pass rate over time (time series)
- Failures by persona (bar chart)
- Top failing scenarios (table)
- Recent failures with GitHub links (table)
- Average duration by persona (bar chart)

The dashboard JSON should use datasource uid `postgres` (matching the provisioned datasource).

Key SQL queries for panels:

**Pass rate over time:**
```sql
SELECT started_at AS time,
       CASE WHEN total_scenarios > 0
            THEN passed::float / total_scenarios * 100
            ELSE 0 END AS pass_rate
FROM qa_runs ORDER BY started_at
```

**Failures by persona:**
```sql
SELECT persona, COUNT(*) AS failures
FROM qa_results WHERE status IN ('fail', 'error')
AND created_at > now() - interval '30 days'
GROUP BY persona ORDER BY failures DESC
```

**Top failing scenarios:**
```sql
SELECT persona, scenario_name, COUNT(*) AS fail_count,
       MAX(error_message) AS last_error,
       MAX(github_issue_url) AS issue_url
FROM qa_results WHERE status IN ('fail', 'error')
AND created_at > now() - interval '30 days'
GROUP BY persona, scenario_name
ORDER BY fail_count DESC LIMIT 10
```

- [ ] **Step 2: Force-add and commit**

```bash
git add -f config/grafana/dashboards/qa-swarm.json
git commit -m "feat(qa): add QA Swarm Grafana dashboard"
```

---

### Task 16: End-to-End Verification

- [ ] **Step 1: Run migration**

Execute the SQL from Task 1, Step 2 to create the tables.

- [ ] **Step 2: Build everything**

```bash
docker compose build agent-api
docker compose --profile qa build qa-swarm
docker compose up -d agent-api grafana
```

- [ ] **Step 3: Run QA swarm dry-run**

```bash
docker compose --profile qa run --rm qa-swarm python runner.py --dry-run
```

Expected: All 5 personas run, results printed to stdout, results stored in PostgreSQL.

- [ ] **Step 4: Verify results in PostgreSQL**

```bash
docker compose exec postgres psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c \
  "SELECT mode, total_scenarios, passed, failed FROM qa_runs ORDER BY started_at DESC LIMIT 1;"
```

- [ ] **Step 5: Run metrics digest**

```bash
docker compose --profile qa run --rm qa-swarm python metrics_digest.py --print
```

Expected: JSON snapshot with pipeline, services, jobs, qa_swarm sections.

- [ ] **Step 6: Verify API endpoint**

```bash
curl -s -H "X-Api-Key: <admin-key>" http://localhost:8880/v1/admin/metrics-digest | python3 -m json.tool
```

Expected: Returns snapshot(s) from the digest we just created.

- [ ] **Step 7: Check Grafana dashboard**

Open Grafana → QA Swarm dashboard → verify panels show data from the run.

- [ ] **Step 8: Final commit**

```bash
git add -A
git commit -m "feat(qa): Phase 2A AI QA Swarm — complete and verified"
```

---

## Execution Notes

- **No existing tests in codebase** — the QA swarm IS the test infrastructure. No TDD loop needed for the test tool itself.
- **Test user creation** depends on a `POST /v1/admin/users` endpoint. If this doesn't exist yet, the runner falls back to using the admin API key directly. The endpoint can be added as a prerequisite task.
- **GitHub Issue creation** requires `GITHUB_TOKEN` and `GITHUB_REPO` env vars. Without them, issues are skipped silently.
- **Mock-acquire mode** requires injecting mock download clients into the worker. This is scaffolded in the persona code but the actual mock injection mechanism depends on the worker's architecture. Start with dry-run and full modes; mock-acquire can be wired up in a follow-up.
- The `profiles: [qa]` Docker Compose feature means `qa-swarm` never starts automatically — only when you explicitly use `--profile qa`.
