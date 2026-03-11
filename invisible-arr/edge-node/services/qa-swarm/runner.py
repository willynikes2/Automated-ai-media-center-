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
    from api_tests import new_user, power_user, live_tv_user, resilience_user  # noqa: F401
    from api_tests import onboarding_user  # noqa: F401
    from browser_tests import browser_user  # noqa: F401
    from browser_tests import app_audit  # noqa: F401


async def main():
    parser = argparse.ArgumentParser(description="CutDaCord AI QA Swarm")
    parser.add_argument("--mode", choices=["dry-run", "mock", "full"], default="dry-run",
                        help="Execution mode (default: dry-run)")
    parser.add_argument("--mock", action="store_const", const="mock", dest="mode",
                        help="Shortcut for --mode mock")
    parser.add_argument("--full", action="store_const", const="full", dest="mode",
                        help="Shortcut for --mode full")
    parser.add_argument("--persona", choices=["new_user", "power_user", "browser_user",
                                               "live_tv_user", "resilience_user",
                                               "onboarding", "app-audit"],
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
        logger.info("Created QA run: %s", db_run_id)

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
            personas_to_run = dict(PERSONAS)

        logger.info("Personas to run: %s", list(personas_to_run.keys()))

        # Run personas sequentially
        for name, persona_cls in personas_to_run.items():
            logger.info("=== Running persona: %s ===", name)
            persona = persona_cls(user_client, config)
            try:
                results = await persona.run_all()
                all_results.extend(results)
            except Exception as e:
                logger.error("Persona %s crashed: %s", name, e, exc_info=True)
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
    # Ensure this module is importable as 'runner' (not __main__) so
    # persona modules that do `from runner import ...` share the same
    # PERSONAS dict.
    import importlib
    sys.modules["runner"] = sys.modules[__name__]
    asyncio.run(main())
