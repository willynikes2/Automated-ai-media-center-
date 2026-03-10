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
