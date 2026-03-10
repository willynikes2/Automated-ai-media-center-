# CutDaCord Phase 2A: AI QA Swarm

## Goal

Build an on-demand AI QA testing system that simulates real users, collects structured failure data, and auto-creates GitHub Issues — providing a data-driven bug backlog before hiring human QA testers.

## Architecture

A single `qa-swarm` Docker container running on the VPS with three internal components:

```
qa-swarm container
├── api_tests/           Python + httpx — hits agent-api directly
│   ├── new_user.py
│   ├── power_user.py
│   ├── live_tv_user.py
│   └── resilience_user.py
├── browser_tests/       Playwright (serial, single worker)
│   └── browser_user.py
├── runner.py            Orchestrator — runs personas, manages test users
├── reporter.py          Writes to PostgreSQL + creates GitHub Issues
├── metrics_digest.py    Queries Prometheus/PG, writes AI-readable snapshots
└── conftest.py          Shared fixtures, API client, mode flags
```

**Key architectural decisions:**
- Runs on VPS alongside the stack (no external CI dependency)
- On-demand only (CLI trigger) — no scheduled runs until disk allows
- Serial Playwright execution (`--workers=1`) to avoid resource exhaustion
- Docker image based on `mcr.microsoft.com/playwright/python`
- Container resource limits: `mem_limit: 512m`, `cpus: 1.0`

---

## Test Data Isolation

QA tests must not contaminate production state.

**Strategy:**
- Each run creates a dedicated test user: `qa-{run_id}@test.cutdacord.app`
- Test user gets tag `qa_run_id` on all created jobs
- All content requested by test users is tagged for cleanup
- Runner has a mandatory `cleanup()` phase that:
  - Deletes all jobs created by the test user
  - Removes any downloaded test content
  - Deactivates the test user
- Cleanup runs in a `finally` block so it executes even on crash

**Test user creation:**
- `POST /v1/admin/users` with `is_test=true` flag
- Test users excluded from production Grafana dashboards via `WHERE email NOT LIKE 'qa-%@test%'`

---

## Execution Modes

Three modes, selectable via CLI flag:

| Mode | Flag | What it does | Disk usage |
|------|------|-------------|------------|
| Dry-run | `--dry-run` (default) | Pipeline stops before ACQUIRING. Tests request creation, resolution, search, selection. | None |
| Mock-acquire | `--mock` | Mocks download clients to return dummy files. Tests import pipeline, file renaming, Jellyfin scan, content registration. | ~50MB temp files, cleaned up |
| Full | `--full` | Real downloads end-to-end. Tests everything including RD/Usenet acquisition. | Real media files |

**Mock-acquire details:**
- Injects a mock acquisition client that writes a small dummy `.mkv` to the expected import path
- Worker's import/rename/scan pipeline runs against the dummy file
- Validates: file lands in correct library path, Jellyfin detects it, content_library row created, quota updated
- Dummy files cleaned up after run

---

## Personas & Scenarios

### 1. New User (API)
- Request a popular movie by title
- Request a TV show (1 season)
- Poll job state transitions: CREATED -> RESOLVING -> SEARCHING -> SELECTED [-> ACQUIRING -> AVAILABLE in full mode]
- GET /v1/library — verify content appears
- GET /v1/library/quota — verify counts updated

### 2. Power User (API)
- Request 3 items concurrently
- Verify concurrent job limit enforced (expect 429 when exceeded)
- Delete an existing library item via API
- Re-request same content (verify dedup/canonical library works)
- Exceed rate limit intentionally, verify 429 response
- Check quota after delete (verify counts decremented)

### 3. Browser User (Playwright)
- Load library page — no JS console errors, page renders within 5s
- Load activity page — job cards render with correct state badges
- Search for a title — results appear within 3s
- Click into detail page — metadata and poster load
- Mobile viewport (375px) — layout doesn't break
- Navigate between pages — no uncaught exceptions

### 4. Live TV User (API)
- GET /iptv/epg.xml — EPG loads, contains channel entries
- GET /iptv/channels — channel list returns, count > 0
- Attempt to tune a channel — stream URL returns valid response
- Verify EPG data freshness (last_updated within 24h)

### 5. Resilience User (API)
- Send malformed request bodies (empty payload, invalid media_type, non-UTF-8 strings)
- Request with invalid API key — verify 401
- Request with deactivated user — verify 403
- Request movie with garbage TMDB ID — verify graceful error
- Delete content that doesn't exist — verify 404
- Send duplicate requests rapidly — verify idempotency/dedup

---

## Data Model

### Migration: qa_runs + qa_results tables

```sql
CREATE TABLE qa_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    triggered_by VARCHAR(50) NOT NULL DEFAULT 'manual',
    mode VARCHAR(20) NOT NULL,  -- dry-run, mock, full
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    total_scenarios INT DEFAULT 0,
    passed INT DEFAULT 0,
    failed INT DEFAULT 0,
    errored INT DEFAULT 0,
    summary TEXT,
    test_user_email VARCHAR(255)
);

CREATE TABLE qa_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES qa_runs(id) ON DELETE CASCADE,
    persona VARCHAR(50) NOT NULL,
    scenario_name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- pass, fail, error, skip
    duration_ms INT,
    error_message TEXT,
    error_fingerprint VARCHAR(64),  -- SHA256 hash for dedup
    correlation_ids JSONB DEFAULT '[]',
    screenshots JSONB DEFAULT '[]',
    github_issue_url VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_qa_results_run_id ON qa_results(run_id);
CREATE INDEX idx_qa_results_fingerprint ON qa_results(error_fingerprint);
```

### Migration: metrics_snapshots table

```sql
CREATE TABLE metrics_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    data JSONB NOT NULL,
    overall_status VARCHAR(20) NOT NULL  -- healthy, degraded, critical
);

CREATE INDEX idx_metrics_snapshots_at ON metrics_snapshots(snapshot_at DESC);
```

---

## GitHub Issue Auto-Creation

### Fingerprinting
Issues are deduplicated using an error fingerprint hash computed from:
```
SHA256(persona + scenario_name + error_class + normalized_error_message)
```

This prevents:
- Same root cause from creating multiple issues across scenarios
- Renamed scenarios from creating duplicate issues

### Noise suppression
- **Threshold:** Only create an issue after **2 consecutive failures** of the same fingerprint across runs
- **Cooldown:** Once an issue is created, same fingerprint suppressed for **24 hours**
- **Reopen:** If a closed issue's fingerprint fails again, reopen + append new evidence instead of creating a new issue

### Issue format
```markdown
## QA Swarm Failure: {persona} / {scenario}

**Fingerprint:** `{hash}`
**Consecutive failures:** {count}
**Mode:** {dry-run|mock|full}

### Error
{error_message}

### Evidence
- Correlation IDs: {ids}
- Sentry query: `correlation_id:{id}`
- Loki query: `{correlation_id="{id}"}`
- Screenshots: {paths}

### Run Context
- Run ID: {run_id}
- Duration: {duration_ms}ms
- Timestamp: {created_at}

Labels: qa-swarm, bug, {persona}
```

---

## AI Metrics Digest

### Purpose
Provide AI agents with a compact, structured view of system health that costs ~300-500 tokens to read, with drill-down handles for deeper investigation.

### Snapshot format (JSON)
```json
{
  "snapshot_id": "uuid",
  "snapshot_at": "2026-03-10T14:00:00Z",
  "overall_status": "healthy",
  "pipeline": {
    "requests_24h": {"current": 12, "delta": 3},
    "success_rate_pct": {"current": 75.0, "delta": -8.3},
    "p95_duration_sec": {"current": 180, "delta": 30}
  },
  "services": {
    "all_up": true,
    "uptime_pct": 99.8,
    "down": []
  },
  "errors": {
    "total_24h": {"current": 5, "delta": 2},
    "top_errors": [
      {"message": "magnet resolution timeout", "count": 3, "service": "agent-worker"}
    ]
  },
  "storage": {
    "used_gb": 45.2,
    "available_gb": 54.8,
    "pct_full": 45.2
  },
  "jobs": {
    "active": {"current": 3, "delta": 1},
    "stuck": 0,
    "failed_24h": {"current": 2, "delta": 1}
  },
  "qa_swarm": {
    "last_run": "2026-03-10T03:00:00Z",
    "pass_rate_pct": 81.8,
    "failing_scenarios": ["Power User: dedup test", "Live TV: tune channel"]
  },
  "users": {
    "active_24h": 3,
    "most_active": "admin@cutdacord.app"
  },
  "alerts": {
    "firing": 0,
    "resolved_24h": 1
  },
  "drill_down": {
    "sentry_query": "is:unresolved project:cutdacord-backend",
    "loki_query": "{service=~\".+\"} |= \"error\" | json",
    "prometheus_query": "rate(requests_total{status=~\"5..\"}[1h])",
    "latest_qa_run_id": "uuid"
  }
}
```

### API endpoint
`GET /v1/admin/metrics-digest?days=7`

Returns an array of snapshots (one per day for the requested range). AI agents call this to get a quick health picture without scraping dashboards.

### CLI
```bash
docker exec qa-swarm python metrics_digest.py          # create snapshot now
docker exec qa-swarm python metrics_digest.py --print   # create + print to stdout
```

---

## Grafana Dashboard: QA Swarm

New provisioned dashboard `qa-swarm.json` with panels:

| Panel | Type | Source |
|-------|------|--------|
| Latest run pass rate | Stat | PostgreSQL |
| Pass rate over time | Time series | PostgreSQL |
| Failures by persona | Bar chart | PostgreSQL |
| Top failing scenarios (last 30 days) | Table | PostgreSQL |
| Recent failures with GitHub links | Table | PostgreSQL |
| Average scenario duration by persona | Bar chart | PostgreSQL |

---

## CLI Interface

```bash
# Run all personas, dry-run mode (default)
docker exec qa-swarm python runner.py

# Run all personas, mock-acquire mode
docker exec qa-swarm python runner.py --mock

# Run all personas, full downloads
docker exec qa-swarm python runner.py --full

# Run single persona
docker exec qa-swarm python runner.py --persona new_user
docker exec qa-swarm python runner.py --persona resilience_user --mock

# Generate metrics digest
docker exec qa-swarm python metrics_digest.py --print

# View last run summary
docker exec qa-swarm python runner.py --last-run
```

---

## Docker Compose Addition

```yaml
qa-swarm:
  build:
    context: ./services/qa-swarm
    dockerfile: Dockerfile
  container_name: qa-swarm
  restart: "no"
  environment:
    - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    - API_BASE_URL=http://agent-api:8880
    - FRONTEND_URL=http://automedia-frontend:3000
    - IPTV_BASE_URL=http://iptv-gateway:8881
    - PROMETHEUS_URL=http://prometheus:9090
    - GITHUB_TOKEN=${GITHUB_TOKEN:-}
    - GITHUB_REPO=${GITHUB_REPO:-}
    - ADMIN_API_KEY=${QA_ADMIN_API_KEY}
  mem_limit: 512m
  cpus: 1.0
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

Using `profiles: [qa]` so the container only starts when explicitly requested:
```bash
docker compose --profile qa run --rm qa-swarm python runner.py --mock
```

---

## File Structure

```
services/qa-swarm/
├── Dockerfile
├── requirements.txt          # httpx, playwright, asyncpg, PyGithub
├── runner.py                 # Orchestrator: parse args, create test user, run personas, cleanup
├── reporter.py               # Write qa_runs/qa_results to PG, create/reopen GitHub Issues
├── metrics_digest.py         # Query Prometheus + PG, write metrics_snapshots
├── conftest.py               # Shared: API client, test user factory, mode flags
├── api_tests/
│   ├── __init__.py
│   ├── new_user.py           # New User persona scenarios
│   ├── power_user.py         # Power User persona scenarios
│   ├── live_tv_user.py       # Live TV persona scenarios
│   └── resilience_user.py    # Resilience/Saboteur persona scenarios
└── browser_tests/
    ├── __init__.py
    └── browser_user.py       # Playwright browser persona scenarios
```

---

## What's NOT in scope
- Scheduled/nightly runs (add when disk allows)
- CI/CD quality gates (add after baseline established)
- k6/Locust load testing (Phase 3)
- Bug clustering/intelligence worker (Phase 3)
- AI auto-fix PR flow (Phase 3)
- Reseller/billing/AI assistant personas (features not built yet)

---

## Acceptance Criteria

Phase 2A is complete when:
1. `docker compose --profile qa run --rm qa-swarm python runner.py` executes all 5 personas in dry-run mode
2. Results stored in `qa_runs` + `qa_results` tables
3. GitHub Issues auto-created for failures (with fingerprint dedup + threshold)
4. `--mock` mode tests the import pipeline with dummy files
5. `--full` mode runs real downloads end-to-end
6. Metrics digest endpoint returns structured JSON at `/v1/admin/metrics-digest`
7. QA Swarm Grafana dashboard shows pass rates and failure trends
8. Test data cleanup runs after every run (no prod contamination)

---

## Reviewed By
- **Gemini 2.5 Pro:** Added mock-acquire mode, saboteur persona, issue thresholding, JSON+deltas digest, Playwright resource constraints
- **Codex GPT-5.3:** Added test data isolation, error fingerprinting, two-layer digest with drill-down handles, resilience persona
