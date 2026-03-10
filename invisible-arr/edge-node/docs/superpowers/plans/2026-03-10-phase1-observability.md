# Phase 1 Observability Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close observability gaps — expand Sentry + Prometheus to all services, add alerting rules, and create a unified ops dashboard.

**Architecture:** Most infrastructure already exists (Sentry in agent-api/worker/frontend, Prometheus+Loki+Grafana running, 9 metrics defined, correlation IDs, bug report endpoint). This plan fills the gaps: Sentry in 3 remaining services, metrics endpoints on worker processes, expanded Prometheus scrape targets, alerting rules, and a consolidated ops dashboard.

**Tech Stack:** Python/FastAPI, Sentry SDK, prometheus_client, Grafana provisioned dashboards/alerts, Docker Compose

---

## Chunk 1: Sentry + Metrics for Worker Services

### Task 1: Add Sentry to agent-qc

**Files:**
- Modify: `services/agent-qc/main.py` (lines 1-42)
- Modify: `services/agent-qc/requirements.txt`
- Modify: `docker-compose.yml` (agent-qc environment block, ~line 537)

- [ ] **Step 1: Add sentry-sdk to requirements.txt**

Add `sentry-sdk[pure_eval]` to `services/agent-qc/requirements.txt`.

- [ ] **Step 2: Add Sentry init + structured logging to agent-qc/main.py**

Replace the logging setup (lines 37-41) with:

```python
import os
import sentry_sdk

from shared.logging import setup_logging

# Sentry
_sentry_dsn = os.environ.get("SENTRY_DSN_BACKEND", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.environ.get("ENV", "dev"),
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

logger = setup_logging("agent-qc")
```

Remove the old `logging.basicConfig(...)` and `logger = logging.getLogger("agent-qc")` lines.

- [ ] **Step 3: Add SENTRY_DSN_BACKEND + ENV to docker-compose agent-qc env**

Add to agent-qc environment block in `docker-compose.yml`:
```yaml
      - SENTRY_DSN_BACKEND=${SENTRY_DSN_BACKEND:-}
      - ENV=${ENV:-dev}
```

- [ ] **Step 4: Commit**

```bash
git add services/agent-qc/main.py services/agent-qc/requirements.txt docker-compose.yml
git commit -m "feat(observability): add Sentry error tracking to agent-qc"
```

---

### Task 2: Add Sentry to agent-storage

**Files:**
- Modify: `services/agent-storage/main.py` (lines 1-38)
- Modify: `services/agent-storage/requirements.txt`
- Modify: `docker-compose.yml` (agent-storage environment block, ~line 559)

- [ ] **Step 1: Add sentry-sdk to requirements.txt**

Add `sentry-sdk[pure_eval]` to `services/agent-storage/requirements.txt`.

- [ ] **Step 2: Add Sentry init + structured logging to agent-storage/main.py**

Replace the logging setup (lines 31-38) with:

```python
import sentry_sdk
from shared.logging import setup_logging

_sentry_dsn = os.environ.get("SENTRY_DSN_BACKEND", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.environ.get("ENV", "dev"),
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

logger = setup_logging("agent-storage")
```

Remove the old `logging.basicConfig(...)` and `logger = logging.getLogger("agent-storage")` lines.

- [ ] **Step 3: Add SENTRY_DSN_BACKEND + ENV to docker-compose agent-storage env**

Add to agent-storage environment block in `docker-compose.yml`:
```yaml
      - SENTRY_DSN_BACKEND=${SENTRY_DSN_BACKEND:-}
      - ENV=${ENV:-dev}
```

- [ ] **Step 4: Commit**

```bash
git add services/agent-storage/main.py services/agent-storage/requirements.txt docker-compose.yml
git commit -m "feat(observability): add Sentry error tracking to agent-storage"
```

---

### Task 3: Add Sentry + metrics to iptv-gateway

**Files:**
- Modify: `services/iptv-gateway/main.py` (lines 1-30, add metrics endpoint)
- Modify: `services/iptv-gateway/requirements.txt`
- Modify: `docker-compose.yml` (iptv-gateway environment block, ~line 580)

- [ ] **Step 1: Add sentry-sdk and prometheus-client to requirements.txt**

Add `sentry-sdk[pure_eval]` and `prometheus-client` to `services/iptv-gateway/requirements.txt`.

- [ ] **Step 2: Add Sentry init + metrics endpoint to iptv-gateway/main.py**

Add before the FastAPI app creation:

```python
import os
import sentry_sdk

_sentry_dsn = os.environ.get("SENTRY_DSN_BACKEND", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.environ.get("ENV", "dev"),
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
```

Add a `/metrics` endpoint after the app is created:

```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

Also add the CorrelationMiddleware if not already present:

```python
from shared.middleware import CorrelationMiddleware
app.add_middleware(CorrelationMiddleware)
```

- [ ] **Step 3: Add SENTRY_DSN_BACKEND + ENV to docker-compose iptv-gateway env**

Add to iptv-gateway environment block in `docker-compose.yml`:
```yaml
      - SENTRY_DSN_BACKEND=${SENTRY_DSN_BACKEND:-}
      - ENV=${ENV:-dev}
```

- [ ] **Step 4: Commit**

```bash
git add services/iptv-gateway/main.py services/iptv-gateway/requirements.txt docker-compose.yml
git commit -m "feat(observability): add Sentry + Prometheus metrics to iptv-gateway"
```

---

### Task 4: Add lightweight metrics HTTP server to agent-worker

Worker processes don't have a web server, so we need a minimal one for Prometheus to scrape.

**Files:**
- Create: `services/shared/metrics_server.py`
- Modify: `services/agent-worker/main.py` (add metrics server startup in `_run()`)

- [ ] **Step 1: Create shared/metrics_server.py**

```python
"""Tiny HTTP server that exposes /metrics for Prometheus scraping.

Use in non-FastAPI services (workers, QC) that need a metrics endpoint.
"""

import asyncio
import logging
from aiohttp import web
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)

async def _metrics_handler(_request: web.Request) -> web.Response:
    return web.Response(body=generate_latest(), content_type=CONTENT_TYPE_LATEST)

async def _health_handler(_request: web.Request) -> web.Response:
    return web.Response(text="ok")

async def start_metrics_server(port: int = 9090) -> web.AppRunner:
    """Start a background HTTP server on *port* serving /metrics and /health."""
    app = web.Application()
    app.router.add_get("/metrics", _metrics_handler)
    app.router.add_get("/health", _health_handler)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Metrics server listening on :%d", port)
    return runner
```

- [ ] **Step 2: Add aiohttp to agent-worker/requirements.txt**

Add `aiohttp` to `services/agent-worker/requirements.txt`.

- [ ] **Step 3: Start metrics server in agent-worker/main.py _run()**

Add near the top of `_run()`, after Redis connection:

```python
from shared.metrics_server import start_metrics_server
metrics_runner = await start_metrics_server(port=9090)
```

And in the shutdown cleanup section, before `logger.info("Shutting down agent-worker")`:

```python
await metrics_runner.cleanup()
```

- [ ] **Step 4: Expose port 9090 in docker-compose for agent-worker**

The port only needs to be accessible on the internal Docker network (Prometheus can reach it). No host mapping needed. But we can add a `ports` entry for debugging if desired. Actually, since Prometheus is on the same Docker network, no port mapping needed at all.

- [ ] **Step 5: Commit**

```bash
git add services/shared/metrics_server.py services/agent-worker/main.py services/agent-worker/requirements.txt
git commit -m "feat(observability): add metrics HTTP server for worker processes"
```

---

### Task 5: Add metrics server to agent-qc

**Files:**
- Modify: `services/agent-qc/main.py` (add metrics server startup)
- Modify: `services/agent-qc/requirements.txt`

- [ ] **Step 1: Add aiohttp + prometheus-client to requirements.txt**

Add `aiohttp` and `prometheus-client` to `services/agent-qc/requirements.txt`.

- [ ] **Step 2: Start metrics server in agent-qc/main.py _main()**

Add after Redis connection established:

```python
from shared.metrics_server import start_metrics_server
metrics_runner = await start_metrics_server(port=9091)
```

And in the finally block, before Redis close:

```python
await metrics_runner.cleanup()
```

- [ ] **Step 3: Commit**

```bash
git add services/agent-qc/main.py services/agent-qc/requirements.txt
git commit -m "feat(observability): add metrics server to agent-qc"
```

---

### Task 6: Add metrics server to agent-storage

**Files:**
- Modify: `services/agent-storage/main.py`
- Modify: `services/agent-storage/requirements.txt`

- [ ] **Step 1: Add aiohttp + prometheus-client to requirements.txt**

Add `aiohttp` and `prometheus-client` to `services/agent-storage/requirements.txt`.

- [ ] **Step 2: Start metrics server in agent-storage/main.py _main()**

Add after `init_db(DATABASE_URL)`:

```python
from shared.metrics_server import start_metrics_server
metrics_runner = await start_metrics_server(port=9092)
```

And add cleanup before the final log line, wrapped in a try/finally around the main loop:

```python
# In the while loop, wrap with try/finally:
try:
    while not _shutdown_event.is_set():
        # ... existing code ...
finally:
    await metrics_runner.cleanup()
```

- [ ] **Step 3: Commit**

```bash
git add services/agent-storage/main.py services/agent-storage/requirements.txt
git commit -m "feat(observability): add metrics server to agent-storage"
```

---

## Chunk 2: Prometheus Config + Alerting Rules

### Task 7: Expand Prometheus scrape targets

**Files:**
- Modify: `config/prometheus/prometheus.yml`

- [ ] **Step 1: Add all services to prometheus.yml**

Replace contents with:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alerts.yml"

scrape_configs:
  - job_name: "agent-api"
    static_configs:
      - targets: ["agent-api:8880"]
    metrics_path: /metrics
    scrape_interval: 10s

  - job_name: "agent-worker"
    static_configs:
      - targets: ["agent-worker:9090"]
    metrics_path: /metrics
    scrape_interval: 15s

  - job_name: "agent-qc"
    static_configs:
      - targets: ["agent-qc:9091"]
    metrics_path: /metrics
    scrape_interval: 15s

  - job_name: "agent-storage"
    static_configs:
      - targets: ["agent-storage:9092"]
    metrics_path: /metrics
    scrape_interval: 30s

  - job_name: "iptv-gateway"
    static_configs:
      - targets: ["iptv-gateway:8881"]
    metrics_path: /metrics
    scrape_interval: 15s
```

- [ ] **Step 2: Commit**

```bash
git add config/prometheus/prometheus.yml
git commit -m "feat(observability): expand Prometheus to scrape all services"
```

---

### Task 8: Create Prometheus alerting rules

**Files:**
- Create: `config/prometheus/alerts.yml`

- [ ] **Step 1: Create alerts.yml with 5 actionable alerts**

```yaml
groups:
  - name: cutdacord_alerts
    rules:
      # 1. API error rate spike (>10% of requests returning 5xx over 5 min)
      - alert: HighAPIErrorRate
        expr: |
          (
            sum(rate(requests_total{status=~"5.."}[5m]))
            /
            sum(rate(requests_total[5m]))
          ) > 0.10
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "API error rate above 10%"
          description: "{{ $value | humanizePercentage }} of API requests returning 5xx over the last 5 minutes."

      # 2. Job failure rate spike (>30% of completed jobs failing over 1 hour)
      - alert: HighJobFailureRate
        expr: |
          (
            sum(rate(job_completions_total{final_state="FAILED"}[1h]))
            /
            sum(rate(job_completions_total[1h]))
          ) > 0.30
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Job failure rate above 30%"
          description: "{{ $value | humanizePercentage }} of jobs failing over the last hour."

      # 3. Service down (metrics endpoint unreachable)
      - alert: ServiceDown
        expr: up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.job }} is down"
          description: "Prometheus cannot reach {{ $labels.instance }} for 2+ minutes."

      # 4. API p95 latency above 5s
      - alert: HighAPILatency
        expr: |
          histogram_quantile(0.95,
            sum(rate(request_duration_seconds_bucket[5m])) by (le)
          ) > 5
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "API p95 latency above 5 seconds"
          description: "p95 request latency is {{ $value | humanizeDuration }}."

      # 5. No jobs processed in 2 hours (possible queue stall)
      - alert: JobQueueStalled
        expr: |
          sum(increase(job_completions_total[2h])) == 0
          and
          sum(active_jobs) > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "No jobs completed in 2 hours despite active jobs"
          description: "There are {{ with query \"sum(active_jobs)\" }}{{ . | first | value }}{{ end }} active jobs but none have completed."
```

- [ ] **Step 2: Commit**

```bash
git add config/prometheus/alerts.yml
git commit -m "feat(observability): add 5 Prometheus alerting rules"
```

---

### Task 9: Configure Grafana alerting provisioning

**Files:**
- Create: `config/grafana/provisioning/alerting/alerting.yml`

- [ ] **Step 1: Create Grafana alert contact point provisioning**

```yaml
apiVersion: 1

contactPoints:
  - orgId: 1
    name: default
    receivers:
      - uid: grafana-default-email
        type: email
        settings:
          addresses: "${GF_SMTP_FROM_ADDRESS:-admin@cutdacord.com}"
        disableResolveMessage: false

policies:
  - orgId: 1
    receiver: default
    group_by: ['alertname', 'job']
    group_wait: 30s
    group_interval: 5m
    repeat_interval: 4h
```

Note: Grafana's built-in alerting will read the Prometheus alert rules directly via the Prometheus datasource. The provisioning here just sets up the notification channel.

- [ ] **Step 2: Commit**

```bash
git add config/grafana/provisioning/alerting/alerting.yml
git commit -m "feat(observability): add Grafana alert notification provisioning"
```

---

## Chunk 3: Ops Dashboard

### Task 10: Create consolidated Ops Dashboard

**Files:**
- Create: `config/grafana/dashboards/ops-overview.json`

- [ ] **Step 1: Create the ops-overview dashboard JSON**

This dashboard should have 4 rows:

**Row 1 — Service Health (stat panels)**
- Panel: "Services Up" — `count(up == 1)` stat
- Panel: "Services Down" — `count(up == 0)` stat (red if > 0)
- Panel: "Active Alerts" — count of firing alerts

**Row 2 — API Performance**
- Panel: "Request Rate" — `sum(rate(requests_total[5m]))` timeseries
- Panel: "Error Rate %" — `sum(rate(requests_total{status=~"5.."}[5m])) / sum(rate(requests_total[5m])) * 100` timeseries
- Panel: "p95 Latency" — `histogram_quantile(0.95, sum(rate(request_duration_seconds_bucket[5m])) by (le))` timeseries

**Row 3 — Job Pipeline**
- Panel: "Active Jobs by State" — `active_jobs` by state, bar gauge
- Panel: "Jobs Completed/Failed" — `sum(rate(job_completions_total[5m])) by (final_state)` timeseries
- Panel: "Job Duration p95" — `histogram_quantile(0.95, sum(rate(job_duration_seconds_bucket[5m])) by (le))` stat

**Row 4 — Logs (Loki)**
- Panel: "Error Logs" — Loki query `{job=~".+"} |= "ERROR"` log panel, last 50 entries

The JSON will be large. Generate it programmatically or write it by hand. Use Grafana dashboard JSON format with `__inputs` for the Prometheus and Loki datasources.

- [ ] **Step 2: Verify dashboard provisioning config includes the dashboards dir**

Check that `config/grafana/provisioning/dashboards/dashboards.yml` points to `/var/lib/grafana/dashboards`. It should already work since existing dashboards load from there.

- [ ] **Step 3: Commit**

```bash
git add config/grafana/dashboards/ops-overview.json
git commit -m "feat(observability): add consolidated ops overview Grafana dashboard"
```

---

## Chunk 4: Build + Deploy

### Task 11: Rebuild and deploy

- [ ] **Step 1: Rebuild affected containers**

```bash
cd /home/shawn/Automated-ai-media-center-/invisible-arr/edge-node
docker compose build agent-qc agent-storage agent-worker iptv-gateway
```

- [ ] **Step 2: Restart observability stack to pick up new configs**

```bash
docker compose restart prometheus grafana
```

- [ ] **Step 3: Rolling restart of agent services**

```bash
docker compose up -d agent-worker agent-qc agent-storage
# iptv-gateway only if iptv profile is active:
# docker compose --profile iptv up -d iptv-gateway
```

- [ ] **Step 4: Verify Prometheus targets**

Open `http://localhost:9090/targets` or:
```bash
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep -E '"job"|"health"'
```

All 5 targets should show `health: "up"`.

- [ ] **Step 5: Verify Grafana dashboard loads**

Open `https://status.cutdacord.app` and check:
- Ops Overview dashboard exists and has data
- Alert rules appear under Alerting > Alert Rules

- [ ] **Step 6: Verify Sentry receives events**

Trigger a test error in agent-qc or agent-storage (or check Sentry dashboard for the project).

- [ ] **Step 7: Final commit with any fixes**

```bash
git add -A
git commit -m "feat(observability): Phase 1 complete — all services instrumented"
```

---

## Summary of Changes

| What | Before | After |
|------|--------|-------|
| Sentry coverage | 2/5 backend services | 5/5 backend services |
| Prometheus targets | 1 (agent-api) | 5 (all services) |
| Alert rules | 0 | 5 actionable alerts |
| Dashboards | 3 (api/jobs/system) | 4 (+ops overview) |
| Bug reporting | Already complete | Already complete |
| Structured logging | Already complete | Already complete |
| Correlation IDs | Already complete | Already complete |
