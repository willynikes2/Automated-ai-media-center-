"""Request middleware: correlation IDs, request timing, metrics."""
import re
import time
import uuid
import logging
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

logger = logging.getLogger("middleware")

# UUID pattern for path normalization
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _normalize_path(path: str) -> str:
    """Replace UUIDs in paths with {id} to prevent cardinality explosion."""
    return _UUID_RE.sub("{id}", path)


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex[:16]
        correlation_id_var.set(cid)

        start = time.perf_counter()

        from shared.metrics import REQUESTS_IN_PROGRESS
        REQUESTS_IN_PROGRESS.inc()
        try:
            response = await call_next(request)
        finally:
            REQUESTS_IN_PROGRESS.dec()

        duration = time.perf_counter() - start

        response.headers["X-Correlation-ID"] = cid

        # Skip logging and metrics for /metrics and /health (noisy)
        path = request.url.path
        if path not in ("/metrics", "/health"):
            normalized = _normalize_path(path)
            status = str(response.status_code)

            # Record Prometheus metrics
            from shared.metrics import REQUEST_DURATION, REQUESTS_TOTAL
            REQUEST_DURATION.labels(
                method=request.method,
                endpoint=normalized,
                status=status,
            ).observe(duration)
            REQUESTS_TOTAL.labels(
                method=request.method,
                endpoint=normalized,
                status=status,
            ).inc()

            logger.info(
                "request_completed",
                extra={
                    "correlation_id": cid,
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                    "client_ip": request.client.host if request.client else None,
                },
            )

        return response
