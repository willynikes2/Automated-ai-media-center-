"""Invisible Arr — Agent Storage Manager.

Periodically monitors disk usage, prunes watched media, and manages
storage pressure for the edge node.
"""

import asyncio
import os
import signal
import sys
from types import FrameType

import sentry_sdk

from shared.database import get_session_factory, init_db
from storage import run_storage_check

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHECK_INTERVAL_SECONDS = int(os.environ.get("STORAGE_CHECK_INTERVAL", "3600"))  # 60 min
MEDIA_PATH = os.environ.get("MEDIA_PATH", "/data/media")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://invisiblearr:changeme@postgres:5432/invisiblearr",
)

# ---------------------------------------------------------------------------
# Logging & Sentry
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_shutdown_event = asyncio.Event()


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — initiating graceful shutdown.", sig_name)
    _shutdown_event.set()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def _main() -> None:
    """Initialise the database and run periodic storage checks."""
    logger.info("Agent-Storage starting.")
    logger.info("  Media path:      %s", MEDIA_PATH)
    logger.info("  Check interval:  %d seconds (%d minutes)", CHECK_INTERVAL_SECONDS, CHECK_INTERVAL_SECONDS // 60)
    logger.info("  Database:        %s", DATABASE_URL.split("@")[-1])

    init_db(DATABASE_URL)
    session_factory = get_session_factory()

    # Metrics server --------------------------------------------------------
    from shared.metrics_server import start_metrics_server
    metrics_runner = await start_metrics_server(port=9092)

    # Run an immediate check on startup, then loop.
    try:
        while not _shutdown_event.is_set():
            try:
                async with session_factory() as session:
                    await run_storage_check(MEDIA_PATH, session)
                    await session.commit()
            except Exception:
                logger.exception("Storage check failed — will retry next cycle.")

            # Wait for the next interval or until shutdown is requested.
            try:
                await asyncio.wait_for(
                    _shutdown_event.wait(),
                    timeout=CHECK_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                # Normal — timeout means it's time for the next check.
                pass
    finally:
        await metrics_runner.cleanup()

    logger.info("Agent-Storage shut down cleanly.")


def main() -> None:
    """Entry point — wire up signal handlers and run the async loop."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
