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
        logger.debug("Prometheus query failed: %s -- %s", query, e)
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
            AND (message ILIKE '%error%' OR message ILIKE '%fail%')
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
