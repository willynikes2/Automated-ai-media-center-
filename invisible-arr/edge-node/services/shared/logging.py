"""Structured JSON logging for all services."""
import logging
import os
import sys
from pythonjsonlogger.json import JsonFormatter


class CorrelationFilter(logging.Filter):
    """Injects correlation_id from context var into every log record."""
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            try:
                from shared.middleware import correlation_id_var
                record.correlation_id = correlation_id_var.get("")
            except (ImportError, LookupError):
                record.correlation_id = ""
        return True


def setup_logging(service_name: str) -> logging.Logger:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    formatter = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
        static_fields={"service": service_name},
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(CorrelationFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger(service_name)
