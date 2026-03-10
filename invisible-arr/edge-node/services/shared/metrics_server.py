"""Tiny HTTP server that exposes /metrics for Prometheus scraping.

Use in non-FastAPI services (workers, QC) that need a metrics endpoint.
"""

import logging
from aiohttp import web
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)


async def _metrics_handler(_request: web.Request) -> web.Response:
    # aiohttp rejects charset in content_type; pass it via headers instead.
    return web.Response(
        body=generate_latest(),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )


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
