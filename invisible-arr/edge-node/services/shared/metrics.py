"""Prometheus metric definitions."""
from prometheus_client import Counter, Gauge, Histogram, Info

REQUEST_DURATION = Histogram(
    "request_duration_seconds",
    "HTTP request latency",
    labelnames=["method", "endpoint", "status"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

REQUESTS_TOTAL = Counter(
    "requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

REQUESTS_IN_PROGRESS = Gauge(
    "requests_in_progress",
    "HTTP requests currently being processed",
)

ACTIVE_JOBS = Gauge(
    "active_jobs",
    "Active jobs by state",
    labelnames=["state"],
)

JOB_DURATION = Histogram(
    "job_duration_seconds",
    "Job processing time",
    labelnames=["acquisition_method", "media_type"],
    buckets=[10, 30, 60, 120, 300, 600, 1800, 3600],
)

JOB_COMPLETIONS = Counter(
    "job_completions_total",
    "Jobs reaching terminal state",
    labelnames=["final_state", "acquisition_method"],
)

REDIS_CACHE_HITS = Counter("redis_cache_hits_total", "Redis cache hits")
REDIS_CACHE_MISSES = Counter("redis_cache_misses_total", "Redis cache misses")

APP_INFO = Info("app", "Application metadata")
APP_INFO.info({"version": "1.0.0", "service": "cutdacord"})
