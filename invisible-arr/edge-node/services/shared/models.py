"""SQLAlchemy ORM models for the Invisible Arr edge node."""

import enum
import secrets
import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, func
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
    CREATED = "CREATED"
    RESOLVING = "RESOLVING"
    ADDING = "ADDING"        # Added to Sonarr/Radarr, waiting for grab
    SEARCHING = "SEARCHING"
    SELECTED = "SELECTED"
    ACQUIRING = "ACQUIRING"
    IMPORTING = "IMPORTING"
    VERIFYING = "VERIFYING"
    MONITORED = "MONITORED"     # Waiting for release (Radarr/Sonarr monitoring)
    DONE = "DONE"
    FAILED = "FAILED"
    DELETED = "DELETED"


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
    last_login: Mapped[datetime | None] = mapped_column(nullable=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    prefs: Mapped[list["Prefs"]] = relationship(back_populates="user", lazy="noload")
    jobs: Mapped[list["Job"]] = relationship(back_populates="user", lazy="noload")


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
    state: Mapped[str] = mapped_column(String(50), default=JobState.CREATED)
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
    message: Mapped[str] = mapped_column(String(2000))
    metadata_json: Mapped[dict | None] = mapped_column(type_=JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())

    job: Mapped["Job"] = relationship(back_populates="events")


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
