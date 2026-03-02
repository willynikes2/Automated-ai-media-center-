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
    retry_count: int
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
