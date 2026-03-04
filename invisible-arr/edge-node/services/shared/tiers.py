"""Tier definitions and limit enforcement for multi-tenant users."""

TIER_LIMITS: dict[str, dict] = {
    "starter": {
        "storage_quota_gb": 100,
        "max_resolution": 1080,
        "allow_4k": False,
        "max_concurrent_jobs": 5,
        "max_requests_per_day": 10,
        "max_movie_size_gb": 3.0,
        "max_episode_size_gb": 1.0,
        "features": ["download"],
    },
    "pro": {
        "storage_quota_gb": 500,
        "max_resolution": 2160,
        "allow_4k": True,
        "max_concurrent_jobs": 5,
        "max_requests_per_day": 25,
        "max_movie_size_gb": 8.0,
        "max_episode_size_gb": 3.0,
        "features": ["download", "stream", "iptv"],
    },
    "family": {
        "storage_quota_gb": 1000,
        "max_resolution": 2160,
        "allow_4k": True,
        "max_concurrent_jobs": 10,
        "max_requests_per_day": 50,
        "max_movie_size_gb": 15.0,
        "max_episode_size_gb": 5.0,
        "features": ["download", "stream", "iptv", "usenet"],
    },
    "power": {
        "storage_quota_gb": -1,  # unlimited
        "max_resolution": 8640,
        "allow_4k": True,
        "max_concurrent_jobs": -1,  # unlimited
        "max_requests_per_day": -1,  # unlimited
        "max_movie_size_gb": 50.0,
        "max_episode_size_gb": 10.0,
        "features": ["download", "stream", "iptv", "usenet", "admin"],
    },
}


def get_tier_limits(tier: str) -> dict:
    """Return limits for the given tier, defaulting to starter."""
    return TIER_LIMITS.get(tier, TIER_LIMITS["starter"])
