from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from sqlalchemy.orm import declarative_base
Base = declarative_base()


def now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    memberships = relationship("WorkspaceMember", back_populates="user")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True)
    name = Column(String(160), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    channels = relationship("Channel", back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),)

    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False, default="EDITOR")
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="memberships")
    channels = relationship("Channel", back_populates="member")


class Channel(Base):
    __tablename__ = "channels"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    member_id = Column(String, ForeignKey("workspace_members.id"))
    name = Column(String(160), nullable=False)
    youtube_channel_id = Column(String(255))
    profile_image_url = Column(String(1000))
    status = Column(String(30), default="demo", nullable=False)
    connected_at = Column(DateTime(timezone=True))
    default_language = Column(String(20), default="en", nullable=False)
    default_voice = Column(String(80), default="en-US", nullable=False)
    daily_video_target = Column(Integer, default=1, nullable=False)
    approval_required = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    workspace = relationship("Workspace", back_populates="channels")
    member = relationship("WorkspaceMember", back_populates="channels")
    personalities = relationship("Personality", back_populates="channel")


class Personality(Base):
    __tablename__ = "personalities"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    channel_id = Column(String, ForeignKey("channels.id"))
    name = Column(String(160), nullable=False)
    category = Column(String(100), default="General", nullable=False)
    description = Column(Text, default="", nullable=False)
    keywords = Column(Text, default="[]", nullable=False)
    preferred_language = Column(String(20), default="en", nullable=False)
    tone = Column(String(160), default="Clear and energetic", nullable=False)
    default_duration = Column(Integer, default=45, nullable=False)
    default_voice = Column(String(80), default="en-US", nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    research_keywords = Column(Text, default="[]", nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    channel = relationship("Channel", back_populates="personalities")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(String, primary_key=True)
    personality_id = Column(String, ForeignKey("personalities.id"), nullable=False)
    title = Column(String(300), nullable=False)
    source_name = Column(String(160), default="Local demo research", nullable=False)
    source_url = Column(String(1000))
    published_at = Column(DateTime(timezone=True))
    freshness_score = Column(Float, default=0.5, nullable=False)
    relevance_score = Column(Float, default=0.7, nullable=False)
    viral_potential_score = Column(Float, default=0.5, nullable=False)
    reliability_score = Column(Float, default=0.7, nullable=False)
    overall_score = Column(Float, default=0.6, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    channel_id = Column(String, ForeignKey("channels.id"), nullable=False)
    personality_id = Column(String, ForeignKey("personalities.id"), nullable=False)
    topic_id = Column(String, ForeignKey("topics.id"))
    topic_title = Column(String(300), default="", nullable=False)
    topic_mode = Column(String(20), default="current", nullable=False)
    manual_topic = Column(String(300))
    duration = Column(Integer, default=45, nullable=False)
    voice = Column(String(80), default="en-US", nullable=False)
    language = Column(String(20), default="en", nullable=False)
    video_style = Column(String(80), default="Documentary", nullable=False)
    warnings = Column(Text, default="[]", nullable=False)
    status = Column(String(40), default="researching", nullable=False)
    current_step = Column(String(80), default="researching", nullable=False)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    topic = relationship("Topic")
    script = relationship("Script", uselist=False, back_populates="job", cascade="all, delete-orphan")
    voice_generation = relationship("VoiceGeneration", uselist=False, back_populates="job", cascade="all, delete-orphan")
    video = relationship("Video", uselist=False, back_populates="job", cascade="all, delete-orphan")


class Script(Base):
    __tablename__ = "scripts"

    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id"), unique=True, nullable=False)
    hook = Column(Text, nullable=False)
    context = Column(Text, nullable=False)
    main_story = Column(Text, nullable=False)
    why_it_matters = Column(Text, nullable=False)
    ending = Column(Text, nullable=False)
    full_script = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    job = relationship("VideoJob", back_populates="script")
    seo = relationship("SEOData", uselist=False, back_populates="script", cascade="all, delete-orphan")


class SEOData(Base):
    __tablename__ = "seo_data"

    id = Column(String, primary_key=True)
    script_id = Column(String, ForeignKey("scripts.id"), unique=True, nullable=False)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    hashtags = Column(Text, default="[]", nullable=False)
    keywords = Column(Text, default="[]", nullable=False)
    cover_text = Column(String(80), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    script = relationship("Script", back_populates="seo")


class VoiceGeneration(Base):
    __tablename__ = "voice_generations"

    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id"), unique=True, nullable=False)
    provider = Column(String(80), nullable=False)
    voice = Column(String(80), nullable=False)
    output_path = Column(String(1000), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    job = relationship("VideoJob", back_populates="voice_generation")


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id"), nullable=False)
    source = Column(String(120), nullable=False)
    url = Column(String(1000))
    license = Column(String(120), nullable=False)
    attribution = Column(String(500), nullable=False)
    local_path = Column(String(1000), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id"), unique=True, nullable=False)
    output_path = Column(String(1000), nullable=False)
    thumbnail_path = Column(String(1000), nullable=False)
    duration = Column(Integer, nullable=False)
    status = Column(String(40), default="ready_for_review", nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    job = relationship("VideoJob", back_populates="video")


class Thumbnail(Base):
    __tablename__ = "thumbnails"
    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id"), unique=True, nullable=False)
    local_path = Column(String(1000), nullable=False)
    headline = Column(String(80), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class ChannelAuthorization(Base):
    """OAuth foundation: actual credentials belong in a future encrypted secret store."""
    __tablename__ = "channel_authorizations"
    id = Column(String, primary_key=True)
    channel_id = Column(String, ForeignKey("channels.id"), unique=True, nullable=False)
    provider = Column(String(40), default="google", nullable=False)
    provider_account_id = Column(String(255))
    credential_reference = Column(String(255))
    scopes = Column(Text, default="[]", nullable=False)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    channel = relationship("Channel")
