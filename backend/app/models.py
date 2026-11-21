import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """Phase 1 uses a single default owner; Phase 2 SaaS plugs auth directly into this table."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="Studio Owner")
    plan_tier: Mapped[str] = mapped_column(String(32), default="personal")  # personal | pro | agency
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    celebrities: Mapped[list["Celebrity"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    projects: Mapped[list["VideoProject"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Celebrity(Base):
    __tablename__ = "celebrities"
    __table_args__ = (
        UniqueConstraint("owner_id", "slug", name="uq_celebrity_owner_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, index=True)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of aliases e.g. ["King James", "LBJ"]
    category: Mapped[str] = mapped_column(String(64), default="NBA")  # NBA | Basketball | Celebrity
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped["User"] = relationship(back_populates="celebrities")
    clips: Mapped[list["MediaClip"]] = relationship(back_populates="celebrity", cascade="all, delete-orphan")


class MediaClip(Base):
    """Metadata index for the 100 GB Celebrity Vault stored in Cloudflare R2."""

    __tablename__ = "media_clips"
    __table_args__ = (
        UniqueConstraint("owner_id", "file_hash", name="uq_clip_owner_hash"),
        Index("ix_clips_celeb_usage", "celebrity_id", "usage_count"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    celebrity_id: Mapped[str] = mapped_column(String(36), ForeignKey("celebrities.id", ondelete="CASCADE"), index=True)

    r2_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="16:9")  # 9:16 | 16:9 | 1:1

    source_type: Mapped[str] = mapped_column(String(32), default="vault_upload")  # vault_upload | web_original
    source_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")  # e.g. ["interview", "press_conference", "dunk"]

    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    celebrity: Mapped["Celebrity"] = relationship(back_populates="clips")


class VideoProject(Base):
    """Supports Shorts now (mode='short') and Long-Form videos next (mode='long')."""

    __tablename__ = "video_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)

    mode: Mapped[str] = mapped_column(String(16), default="short")  # short (9:16) | long (16:9)
    input_type: Mapped[str] = mapped_column(String(16), default="title")  # title | script
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    final_script: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    detected_celebrities_json: Mapped[str] = mapped_column(Text, default="[]")
    voice_name: Mapped[str] = mapped_column(String(64), default="en-US-ChristopherNeural")
    target_duration_sec: Mapped[int] = mapped_column(Integer, default=55)

    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    output_r2_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped["User"] = relationship(back_populates="projects")
    jobs: Mapped[list["RenderJob"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class RenderJob(Base):
    """Polled by the Local PC Worker (Phase 1) or Cloud Worker (Phase 2)."""

    __tablename__ = "render_jobs"
    __table_args__ = (
        Index("ix_render_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("video_projects.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)

    status: Mapped[str] = mapped_column(String(32), default="queued")  # queued | processing | completed | failed
    current_step: Mapped[str] = mapped_column(String(64), default="queued")  # script | audio | clips | captions | render | upload
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["VideoProject"] = relationship(back_populates="jobs")
