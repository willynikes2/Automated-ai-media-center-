"""SQLAlchemy ORM models for the Invisible Arr edge node."""

import enum
import secrets
import uuid
from datetime import datetime, timezone

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
    SEARCHING = "SEARCHING"
    SELECTED = "SELECTED"
    ACQUIRING = "ACQUIRING"
    IMPORTING = "IMPORTING"
    VERIFYING = "VERIFYING"
    DONE = "DONE"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(255))
    api_key: Mapped[str] = mapped_column(String(255), unique=True, default=lambda: secrets.token_urlsafe(32))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now())

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
    state: Mapped[JobState] = mapped_column(default=JobState.CREATED)
    selected_candidate: Mapped[dict | None] = mapped_column(type_=JSON, default=None)
    rd_torrent_id: Mapped[str | None] = mapped_column(String(255), default=None)
    imported_path: Mapped[str | None] = mapped_column(String(1000), default=None)
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
