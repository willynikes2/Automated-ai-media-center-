"""SQLAlchemy ORM models for the Invisible Arr edge node."""

import enum
import secrets
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Integer, JSON, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class JobState(str, enum.Enum):
    # Primary states (user-facing)
    REQUESTED = "REQUESTED"
    SEARCHING = "SEARCHING"
    DOWNLOADING = "DOWNLOADING"
    IMPORTING = "IMPORTING"
    AVAILABLE = "AVAILABLE"
    WAITING = "WAITING"
    FAILED = "FAILED"
    DELETED = "DELETED"

    # Legacy — kept for DB compat, mapped on read
    CREATED = "CREATED"
    RESOLVING = "RESOLVING"
    ADDING = "ADDING"
    SELECTED = "SELECTED"
    ACQUIRING = "ACQUIRING"
    VERIFYING = "VERIFYING"
    DONE = "DONE"
    MONITORED = "MONITORED"
    INVESTIGATING = "INVESTIGATING"
    UNAVAILABLE = "UNAVAILABLE"


_STATE_MAP = {
    "CREATED": "REQUESTED",
    "RESOLVING": "SEARCHING",
    "ADDING": "SEARCHING",
    "SELECTED": "SEARCHING",
    "ACQUIRING": "DOWNLOADING",
    "VERIFYING": "IMPORTING",
    "DONE": "AVAILABLE",
    "MONITORED": "WAITING",
    "INVESTIGATING": "SEARCHING",
    "UNAVAILABLE": "FAILED",
}


def normalize_state(state: str) -> str:
    """Map legacy states to v2 states."""
    return _STATE_MAP.get(state, state)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"
    RESELLER = "reseller"


class UserTier(str, enum.Enum):
    STARTER = "starter"
    PRO = "pro"
    FAMILY = "family"
    POWER = "power"


class BugReportStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(255))
    api_key: Mapped[str] = mapped_column(String(255), unique=True, default=lambda: secrets.token_urlsafe(32))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.USER)
    tier: Mapped[str] = mapped_column(String(20), default=UserTier.STARTER)
    is_active: Mapped[bool] = mapped_column(default=True)
    storage_quota_gb: Mapped[float] = mapped_column(default=100.0)
    storage_used_gb: Mapped[float] = mapped_column(default=0.0)
    rd_api_token_enc: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    usenet_config_enc: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    apple_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    jellyfin_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    jellyfin_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    radarr_root_folder_id: Mapped[int | None] = mapped_column(nullable=True)
    sonarr_root_folder_id: Mapped[int | None] = mapped_column(nullable=True)
    max_concurrent_jobs: Mapped[int] = mapped_column(default=2)
    max_requests_per_day: Mapped[int] = mapped_column(default=10)
    requests_today: Mapped[int] = mapped_column(default=0)
    requests_reset_at: Mapped[datetime | None] = mapped_column(nullable=True)
    setup_complete: Mapped[bool] = mapped_column(default=False)
    movie_quota: Mapped[int] = mapped_column(default=50)
    movie_count: Mapped[int] = mapped_column(default=0)
    tv_quota: Mapped[int] = mapped_column(default=25)
    tv_count: Mapped[int] = mapped_column(default=0)
    last_login: Mapped[datetime | None] = mapped_column(nullable=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Onboarding provisioning
    iptv_line_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    iptv_line_password_enc: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    iptv_provisioned_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rd_source: Mapped[str] = mapped_column(String(20), default="user_provided")
    rd_pool_account_id: Mapped[int | None] = mapped_column(ForeignKey("rd_pool_accounts.id", ondelete="SET NULL"), nullable=True)
    onboarding_status: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    prefs: Mapped[list["Prefs"]] = relationship(back_populates="user", lazy="noload")
    jobs: Mapped[list["Job"]] = relationship(back_populates="user", lazy="noload")


class RdPoolAccount(Base):
    __tablename__ = "rd_pool_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255))
    api_token_enc: Mapped[str] = mapped_column(String(1000))
    max_users: Mapped[int] = mapped_column(default=5)
    current_users: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class Prefs(Base):
    __tablename__ = "prefs"
    __table_args__ = (
        Index("ix_prefs_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    max_resolution: Mapped[int] = mapped_column(default=1080)
    allow_4k: Mapped[bool] = mapped_column(default=False)
    max_movie_size_gb: Mapped[float] = mapped_column(default=15.0)
    max_episode_size_gb: Mapped[float] = mapped_column(default=4.0)
    prune_watched_after_days: Mapped[int | None] = mapped_column(default=None)
    keep_favorites: Mapped[bool] = mapped_column(default=True)
    storage_soft_limit_percent: Mapped[int] = mapped_column(default=90)
    upgrade_policy: Mapped[str] = mapped_column(String(20), default="off")

    user: Mapped["User"] = relationship(back_populates="prefs")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_state", "state"),
        Index("ix_jobs_user_id", "user_id"),
        Index("ix_jobs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    media_type: Mapped[str] = mapped_column(String(10))  # movie | tv
    tmdb_id: Mapped[int | None] = mapped_column(default=None)
    title: Mapped[str] = mapped_column(String(500))
    query: Mapped[str | None] = mapped_column(String(500), default=None)
    season: Mapped[int | None] = mapped_column(default=None)
    episode: Mapped[int | None] = mapped_column(default=None)
    state: Mapped[str] = mapped_column(String(50), default=JobState.REQUESTED)
    selected_candidate: Mapped[dict | None] = mapped_column(type_=JSON, default=None)
    rd_torrent_id: Mapped[str | None] = mapped_column(String(255), default=None)
    imported_path: Mapped[str | None] = mapped_column(String(1000), default=None)
    acquisition_mode: Mapped[str] = mapped_column(String(20), default="download")  # download | stream
    acquisition_method: Mapped[str | None] = mapped_column(String(20), default=None)  # rd, usenet, torrent
    streaming_urls: Mapped[dict | None] = mapped_column(type_=JSON, nullable=True, default=None)
    sonarr_series_id: Mapped[int | None] = mapped_column(nullable=True)
    radarr_movie_id: Mapped[int | None] = mapped_column(nullable=True)
    arr_queue_id: Mapped[int | None] = mapped_column(nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=_utcnow, onupdate=_utcnow, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="jobs")
    events: Mapped[list["JobEvent"]] = relationship(back_populates="job", lazy="selectin")


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"))
    state: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(type_=JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())

    job: Mapped["Job"] = relationship(back_populates="events")


class JobDiagnostic(Base):
    __tablename__ = "job_diagnostics"

    id: Mapped[uuid.UUID] = mapped_column(default=_new_uuid, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    auto_fix_action: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Blacklist(Base):
    __tablename__ = "blacklists"
    __table_args__ = (
        Index("ix_blacklists_user_id_release_hash", "user_id", "release_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    release_hash: Mapped[str] = mapped_column(String(255))
    release_title: Mapped[str] = mapped_column(String(1000))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    tier: Mapped[str] = mapped_column(String(20), default=UserTier.STARTER)
    max_uses: Mapped[int] = mapped_column(default=1)
    times_used: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())


class IptvSource(Base):
    __tablename__ = "iptv_sources"
    __table_args__ = (
        Index("ix_iptv_sources_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    m3u_url: Mapped[str] = mapped_column(String(2000))
    epg_url: Mapped[str | None] = mapped_column(String(2000), default=None)
    source_timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    headers_json: Mapped[dict | None] = mapped_column(type_=JSON, default=None)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())

    channels: Mapped[list["IptvChannel"]] = relationship(back_populates="source", lazy="noload")


class IptvChannel(Base):
    __tablename__ = "iptv_channels"
    __table_args__ = (
        Index("ix_iptv_channels_user_id", "user_id"),
        Index("ix_iptv_channels_source_id", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iptv_sources.id"))
    tvg_id: Mapped[str | None] = mapped_column(String(255), default=None)
    name: Mapped[str] = mapped_column(String(500))
    group_title: Mapped[str | None] = mapped_column(String(500), default=None)
    logo: Mapped[str | None] = mapped_column(String(2000), default=None)
    stream_url: Mapped[str] = mapped_column(String(2000))
    enabled: Mapped[bool] = mapped_column(default=True)
    channel_number: Mapped[int | None] = mapped_column(default=None)
    preferred_name: Mapped[str | None] = mapped_column(String(500), default=None)
    preferred_group: Mapped[str | None] = mapped_column(String(500), default=None)

    source: Mapped["IptvSource"] = relationship(back_populates="channels")


class BugReport(Base):
    __tablename__ = "bug_reports"
    __table_args__ = (
        Index("ix_bug_reports_user_id", "user_id"),
        Index("ix_bug_reports_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    route: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(String(5000))
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    browser_info: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=BugReportStatus.OPEN)
    admin_notes: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())


class ContentLibrary(Base):
    """Registry of all downloaded content, keyed by TMDB ID.

    Used to deduplicate downloads across users: if content already exists,
    hardlink it instead of re-downloading.
    """
    __tablename__ = "content_library"
    __table_args__ = (
        UniqueConstraint("tmdb_id", "media_type", "season", "episode", name="uq_content_identity"),
        Index("ix_content_library_tmdb_id", "tmdb_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "movie" or "tv"
    title: Mapped[str | None] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(Text, nullable=False)  # absolute path to canonical file
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    quality: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "WEBDL-1080p"
    codec: Mapped[str | None] = mapped_column(String(20), nullable=True)  # e.g. "x264", "x265"
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())


class CanonicalContent(Base):
    """Canonical library — one copy of each piece of content, shared across users."""
    __tablename__ = "canonical_content"
    __table_args__ = (
        UniqueConstraint("tmdb_id", "media_type", name="uq_canonical_tmdb"),
        Index("ix_canonical_content_tmdb_id", "tmdb_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    canonical_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    quality: Mapped[str | None] = mapped_column(String(50), nullable=True)
    codec: Mapped[str | None] = mapped_column(String(20), nullable=True)
    radarr_id: Mapped[int | None] = mapped_column(nullable=True)
    sonarr_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())
    gc_eligible_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user_refs: Mapped[list["UserContent"]] = relationship(back_populates="canonical", lazy="noload")


class UserContent(Base):
    """Maps users to canonical content — tracks who has what + reference counting for GC."""
    __tablename__ = "user_content"
    __table_args__ = (
        UniqueConstraint("user_id", "canonical_content_id", name="uq_user_canonical"),
        Index("ix_user_content_user_id", "user_id"),
        Index("ix_user_content_canonical_id", "canonical_content_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    canonical_content_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("canonical_content.id"), nullable=False)
    symlink_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    added_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())
    removed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    canonical: Mapped["CanonicalContent"] = relationship(back_populates="user_refs")


# ---------------------------------------------------------------------------
# QA Swarm Models
# ---------------------------------------------------------------------------


class QARun(Base):
    __tablename__ = "qa_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    triggered_by: Mapped[str] = mapped_column(String(50), default="manual")
    mode: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    total_scenarios: Mapped[int] = mapped_column(default=0)
    passed: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    errored: Mapped[int] = mapped_column(default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    results: Mapped[list["QAResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class QAResult(Base):
    __tablename__ = "qa_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("qa_runs.id", ondelete="CASCADE"))
    persona: Mapped[str] = mapped_column(String(50))
    scenario_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    correlation_ids: Mapped[dict] = mapped_column(JSON, default=list)
    screenshots: Mapped[dict] = mapped_column(JSON, default=list)
    github_issue_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())

    run: Mapped["QARun"] = relationship(back_populates="results")


class MetricsSnapshot(Base):
    __tablename__ = "metrics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    snapshot_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now(), index=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    overall_status: Mapped[str] = mapped_column(String(20))
