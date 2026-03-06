"""Pydantic v2 request/response schemas for the Invisible Arr API."""

import uuid
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class RequestCreate(BaseModel):
    """Body for POST /v1/request."""

    query: str = Field(min_length=1, max_length=500)
    tmdb_id: int | None = None
    media_type: Literal["movie", "tv"]
    season: int | None = None
    episode: int | None = None
    preferred_resolution: int | None = Field(None, ge=240, le=8640)
    preferred_downloader: Literal["rd", "torrent"] | None = None
    acquisition_mode: Literal["download", "stream"] = "download"


class BatchRequestCreate(BaseModel):
    """Body for POST /v1/request/batch — request multiple seasons/episodes."""

    query: str = Field(min_length=1, max_length=500)
    tmdb_id: int | None = None
    media_type: Literal["tv"] = "tv"
    seasons: list[int] | None = None
    episodes: list[dict] | None = None  # [{"season": 1, "episode": 5}, ...]
    acquisition_mode: Literal["download", "stream"] = "download"


class PrefsUpdate(BaseModel):
    """Body for PATCH /v1/prefs.  All fields optional."""

    max_resolution: int | None = Field(None, ge=240, le=8640)
    allow_4k: bool | None = None
    max_movie_size_gb: float | None = Field(None, ge=0.1, le=200.0)
    max_episode_size_gb: float | None = Field(None, ge=0.1, le=100.0)
    prune_watched_after_days: int | None = None
    keep_favorites: bool | None = None
    storage_soft_limit_percent: int | None = Field(None, ge=1, le=100)
    upgrade_policy: Literal["on", "off"] | None = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class JobEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    state: str
    message: str
    metadata_json: dict | None = None
    created_at: datetime


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    media_type: str
    tmdb_id: int | None = None
    title: str
    query: str | None = None
    season: int | None = None
    episode: int | None = None
    state: str
    selected_candidate: dict | None = None
    rd_torrent_id: str | None = None
    imported_path: str | None = None
    acquisition_mode: str = "download"
    acquisition_method: str | None = None
    streaming_urls: dict | None = None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    events: list[JobEventResponse] = []


class JobListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    media_type: str
    tmdb_id: int | None = None
    title: str
    query: str | None = None
    season: int | None = None
    episode: int | None = None
    state: str
    selected_candidate: dict | None = None
    rd_torrent_id: str | None = None
    imported_path: str | None = None
    acquisition_mode: str = "download"
    acquisition_method: str | None = None
    streaming_urls: dict | None = None
    retry_count: int
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class PrefsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    max_resolution: int
    allow_4k: bool
    max_movie_size_gb: float
    max_episode_size_gb: float
    prune_watched_after_days: int | None = None
    keep_favorites: bool
    storage_soft_limit_percent: int
    upgrade_policy: str


class CandidateInfo(BaseModel):
    """Structured info about a release candidate."""

    title: str
    resolution: int
    source: str
    codec: str
    audio: str
    size_gb: float
    seeders: int
    score: int
    magnet_link: str
    info_hash: str


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
    version: str


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Body for POST /v1/auth/register."""

    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    invite_code: str = Field(min_length=1, max_length=50)


class EmailLoginRequest(BaseModel):
    """Body for POST /v1/auth/login."""

    email: str
    password: str


class AuthResponse(BaseModel):
    """Response for login/register endpoints."""

    user_id: uuid.UUID
    api_key: str
    name: str
    role: str
    tier: str
    setup_complete: bool = False


class UserResponse(BaseModel):
    """Public user info (no secrets)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None = None
    role: str
    tier: str
    is_active: bool
    storage_quota_gb: float
    storage_used_gb: float
    max_concurrent_jobs: int
    max_requests_per_day: int
    created_at: datetime
    last_login: datetime | None = None


class GoogleCallbackRequest(BaseModel):
    """Body for POST /v1/auth/google/callback."""

    code: str
    redirect_uri: str


class SetupRequest(BaseModel):
    """Body for POST /v1/auth/setup — onboarding wizard."""

    rd_api_token: str | None = None
    preferred_resolution: int | None = Field(None, ge=240, le=8640)
    allow_4k: bool | None = None


class InviteCreate(BaseModel):
    """Body for POST /v1/admin/invites."""

    tier: str = "starter"
    max_uses: int = Field(default=1, ge=1, le=100)
    expires_in_days: int | None = Field(None, ge=1, le=365)


class InviteResponse(BaseModel):
    """Response for invite endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    tier: str
    max_uses: int
    times_used: int
    expires_at: datetime | None = None
    is_active: bool
    created_at: datetime


class AdminStatsResponse(BaseModel):
    """Response for GET /v1/admin/stats."""

    total_users: int
    active_users: int
    total_jobs: int
    jobs_by_state: dict[str, int]
    storage_used_gb: float


class AdminUserUpdate(BaseModel):
    """Body for PUT /v1/admin/users/{id}."""

    role: str | None = None
    tier: str | None = None
    is_active: bool | None = None
    storage_quota_gb: float | None = None
    max_concurrent_jobs: int | None = None
    max_requests_per_day: int | None = None


# ---------------------------------------------------------------------------
# Bug report schemas
# ---------------------------------------------------------------------------


class BugReportCreate(BaseModel):
    """Body for POST /v1/bugs."""

    route: str = Field(max_length=500)
    description: str = Field(min_length=1, max_length=5000)
    correlation_id: str | None = Field(None, max_length=255)
    browser_info: str | None = Field(None, max_length=1000)


class BugReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    route: str
    description: str
    correlation_id: str | None = None
    browser_info: str | None = None
    status: str
    admin_notes: str | None = None
    created_at: datetime


class BugReportUpdate(BaseModel):
    """Body for PUT /v1/admin/bugs/{id}."""

    status: str | None = None
    admin_notes: str | None = Field(None, max_length=5000)
