from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.session import Base


def now_utc():
    return datetime.now(timezone.utc)


class PasswordReset(Base):
    """Time-limited one-time e-mail verification code. Only an HMAC of the code is stored."""
    __tablename__ = "password_resets"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    purpose = Column(String(20), nullable=False, default="reset")
    code_hash = Column(String(128), nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True))


class AdminAudit(Base):
    __tablename__ = 'admin_audit'
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey('workspaces.id'), nullable=False)
    actor_id = Column(String, nullable=False)
    target_id = Column(String, nullable=False)
    action = Column(String(80), nullable=False)
    details = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email_verified_at = Column(DateTime(timezone=True))
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
    role = Column(String(20), nullable=False, default="MEMBER")
    can_manage_admins = Column(Boolean, default=False, server_default='0', nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    last_active_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="memberships")
    channels = relationship("Channel", back_populates="member")


class Channel(Base):
    __tablename__ = "channels"

    id = Column(String, primary_key=True)
    operational_defaults = Column(Text, default='{}', server_default='{}', nullable=False)
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
    approval_policy = Column(String(20), default="owner_only", server_default="owner_only", nullable=False)
    subscriber_count = Column(Integer)
    video_count = Column(Integer)
    channel_url = Column(String(1000))
    connection_error = Column(Text)
    tts_provider = Column(String(30), default="local", server_default="local", nullable=False)
    voice_style = Column(String(30), default="auto", server_default="auto", nullable=False)
    brand_color = Column(String(20), default="#61e8b6", server_default="#61e8b6", nullable=False)
    automatic_evergreen_fallback = Column(Boolean, default=False, server_default='0', nullable=False)
    automatic_generation_enabled = Column(Boolean, default=False, server_default='0', nullable=False)
    generation_duration = Column(Integer, default=45, server_default='45', nullable=False)
    niche = Column(String(160), default='', server_default='', nullable=False)
    evergreen_source_urls = Column(Text, default='[]', server_default='[]', nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    workspace = relationship("Workspace", back_populates="channels")
    member = relationship("WorkspaceMember", back_populates="channels")
    personalities = relationship("Personality", back_populates="channel")


class Personality(Base):
    __tablename__ = "personalities"

    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    creator_member_id = Column(String, ForeignKey('workspace_members.id'))
    visibility = Column(String(20),default='workspace',server_default='workspace',nullable=False)
    default_voice_style = Column(String(30),default='auto',server_default='auto',nullable=False)
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
    __table_args__ = (UniqueConstraint('channel_id','event_identity',name='uq_channel_event_identity'),)

    id = Column(String, primary_key=True)
    personality_id = Column(String, ForeignKey("personalities.id"), nullable=False)
    title = Column(String(300), nullable=False)
    source_name = Column(String(160), default="Local demo research", nullable=False)
    source_url = Column(String(1000))
    event_identity = Column(String(64))
    channel_id = Column(String, ForeignKey("channels.id"))
    summary = Column(Text, default="", server_default="", nullable=False)
    verification_status = Column(String(40), default="demo", server_default="demo", nullable=False)
    evidence = Column(Text, default="[]", server_default="[]", nullable=False)
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
    content_mode = Column(String(20), default='hybrid', server_default='hybrid', nullable=False)
    collection_id = Column(String, ForeignKey('media_collections.id'))
    avoid_recent_media = Column(Boolean, default=True, server_default='1', nullable=False)
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
    language_code = Column(String(20), default='en-US', server_default='en-US', nullable=False)
    language_name = Column(String(80), default='English', server_default='English', nullable=False)
    locale = Column(String(20), default='en-US', server_default='en-US', nullable=False)
    video_style = Column(String(80), default="Documentary", nullable=False)
    voice_style = Column(String(30), default="auto", server_default="auto", nullable=False)
    tts_provider = Column(String(30))
    warnings = Column(Text, default="[]", nullable=False)
    research_trace = Column(Text, default="{}", server_default="{}", nullable=False)
    status = Column(String(40), default="researching", nullable=False)
    current_step = Column(String(80), default="researching", nullable=False)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0, nullable=False)
    failed_step = Column(String(80))
    content_revision = Column(Integer, default=1, server_default="1", nullable=False)
    media_revision = Column(Integer, default=1, server_default="1", nullable=False)
    row_version = Column(Integer, default=1, server_default="1", nullable=False)
    __mapper_args__ = {'version_id_col': row_version}
    rejection_note = Column(Text)
    music_id = Column(String, ForeignKey("music_tracks.id"))
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
    script_hash = Column(String(64), default='', server_default='', nullable=False)
    __tablename__ = "voice_generations"

    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id"), unique=True, nullable=False)
    provider = Column(String(80), nullable=False)
    voice = Column(String(80), nullable=False)
    language = Column(String(20), default="en", server_default="en", nullable=False)
    speed = Column(Float, default=1, server_default="1", nullable=False)
    voice_profile = Column(Text)
    delivery = Column(Text)
    output_path = Column(String(1000), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    job = relationship("VideoJob", back_populates="voice_generation")


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id"), nullable=False)
    source = Column(String(120), nullable=False)
    url = Column(String(1000))
    creator = Column(String(500))
    download_url = Column(String(2000))
    scene_number = Column(Integer)
    license = Column(String(120), nullable=False)
    attribution = Column(String(500), nullable=False)
    local_path = Column(String(1000), nullable=False)
    provenance = Column(Text, nullable=False, default="{}", server_default="{}")
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id"), unique=True, nullable=False)
    output_path = Column(String(1000), nullable=False)
    thumbnail_path = Column(String(1000), nullable=False)
    duration = Column(Integer, nullable=False)
    status = Column(String(40), default="ready_for_review", nullable=False)
    media_revision = Column(Integer, default=1, server_default="0", nullable=False)
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
    encrypted_tokens = Column(Text)
    authorized_member_id = Column(String, ForeignKey("workspace_members.id"))
    scopes = Column(Text, default="[]", nullable=False)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    channel = relationship("Channel")


class OAuthState(Base):
    __tablename__ = "oauth_states"
    id = Column(String, primary_key=True)
    member_id = Column(String, ForeignKey("workspace_members.id"), nullable=False)
    verifier = Column(Text, nullable=False)
    browser_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed = Column(Boolean, default=False, nullable=False)


class ResearchCandidate(Base):
    __tablename__ = "research_candidates"
    id = Column(String, primary_key=True)
    personality_id = Column(String, ForeignKey("personalities.id"), nullable=False)
    channel_id = Column(String, ForeignKey("channels.id"))
    title = Column(String(500), nullable=False)
    data = Column(Text, nullable=False)
    status = Column(String(40), nullable=False)
    rejection_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class Scene(Base):
    __tablename__ = "scenes"
    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id", ondelete="CASCADE"), nullable=False)
    scene_number = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    narration = Column(Text, nullable=False)
    visual_query = Column(String(300), nullable=False)
    visual_type = Column(String(40), nullable=False)
    caption = Column(String(300), nullable=False)
    emphasis_word = Column(String(80), nullable=False)


class GenerationRequest(Base):
    __tablename__ = 'generation_requests'
    workspace_id = Column(String, ForeignKey('workspaces.id'), primary_key=True)
    operation_key = Column(String(64), primary_key=True)
    fingerprint = Column(String(64), nullable=False)
    job_id = Column(String, ForeignKey('video_jobs.id', ondelete='CASCADE'), unique=True, nullable=False)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("job_id", "member_id", "revision", name="uq_job_member_revision"),)
    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(String, ForeignKey("workspace_members.id"), nullable=False)
    revision = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class UploadTask(Base):
    __tablename__ = "upload_tasks"
    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id", ondelete="CASCADE"), unique=True, nullable=False)
    requested_by = Column(String, ForeignKey("workspace_members.id"), nullable=False)
    content_revision = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False)
    scheduled_at = Column(DateTime(timezone=True))
    timezone = Column(String(80), default="UTC", nullable=False)
    privacy_status = Column(String(20), default="private", nullable=False)
    made_for_kids = Column(Boolean, default=False, nullable=False)
    progress = Column(Float, default=0, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    resumable_uri_encrypted = Column(Text)
    youtube_video_id = Column(String(100))
    youtube_url = Column(String(500))
    uploaded_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    response = Column(Text)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class Analytics(Base):
    __tablename__ = "video_analytics"
    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("video_jobs.id", ondelete="CASCADE"), unique=True, nullable=False)
    views = Column(Integer, default=0, nullable=False)
    likes = Column(Integer, default=0, nullable=False)
    comments = Column(Integer, default=0, nullable=False)
    published_at = Column(DateTime(timezone=True))
    last_synced_at = Column(DateTime(timezone=True))


class ChannelAnalyticsCache(Base):
    __tablename__ = 'channel_analytics_cache'
    workspace_id = Column(String, ForeignKey('workspaces.id'), primary_key=True)
    channel_id = Column(String, ForeignKey('channels.id', ondelete='CASCADE'), primary_key=True)
    report_key = Column(String(120), primary_key=True)
    payload = Column(Text)
    synced_at = Column(DateTime(timezone=True))
    attempted_at = Column(DateTime(timezone=True))
    lease_until = Column(DateTime(timezone=True))
    error = Column(Text)


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"
    workspace_id = Column(String, ForeignKey("workspaces.id"), primary_key=True)
    data = Column(Text, default="{}", nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    channel_id = Column(String, ForeignKey("channels.id"))
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    read_by = Column(Text, default="[]", nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class MusicTrack(Base):
    __tablename__ = "music_tracks"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    name = Column(String(120), nullable=False)
    local_path = Column(String(1000), nullable=False)
    source = Column(String(1000), nullable=False)
    license = Column(String(500), nullable=False)
    attribution = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)


class ChannelAssignment(Base):
    __tablename__='channel_assignments'
    channel_id=Column(String,ForeignKey('channels.id',ondelete='CASCADE'),primary_key=True)
    member_id=Column(String,ForeignKey('workspace_members.id',ondelete='CASCADE'),primary_key=True)

class MediaCollection(Base):
    __tablename__='media_collections'
    id=Column(String,primary_key=True)
    workspace_id=Column(String,ForeignKey('workspaces.id'),nullable=False)
    member_id=Column(String,ForeignKey('workspace_members.id'),nullable=False)
    channel_id=Column(String,ForeignKey('channels.id'))
    name=Column(String(160),nullable=False)
    created_at=Column(DateTime(timezone=True),default=now_utc,nullable=False)


class LibraryMedia(Base):
    __tablename__='library_media'
    __table_args__=(UniqueConstraint('collection_id','content_hash',name='uq_collection_content'),)
    id=Column(String,primary_key=True)
    collection_id=Column(String,ForeignKey('media_collections.id'),nullable=False)
    personality_id=Column(String,ForeignKey('personalities.id'))
    name=Column(String(160),nullable=False)
    media_type=Column(String(20),nullable=False)
    tags=Column(Text,default='[]',nullable=False)
    description=Column(Text,default='',server_default='',nullable=False)
    width=Column(Integer)
    height=Column(Integer)
    original_path=Column(Text)
    source_url=Column(String(1000))
    creator=Column(String(200),nullable=False)
    license=Column(String(100),nullable=False)
    credit=Column(Text,default='',nullable=False)
    approved=Column(Boolean,default=False,nullable=False)
    archived=Column(Boolean,default=False,nullable=False)
    content_hash=Column(String(64),nullable=False)
    local_path=Column(Text,nullable=False)
    created_at=Column(DateTime(timezone=True),default=now_utc,nullable=False)


class MediaUsage(Base):
    __tablename__='media_usage'
    __table_args__=(UniqueConstraint('media_id','job_id','revision',name='uq_media_revision_usage'),)
    id=Column(String,primary_key=True)
    media_id=Column(String,ForeignKey('library_media.id'),nullable=False)
    job_id=Column(String,ForeignKey('video_jobs.id',ondelete='CASCADE'),nullable=False)
    revision=Column(Integer,nullable=False)
    created_at=Column(DateTime(timezone=True),default=now_utc,nullable=False)


class TitleShortDraft(Base):
    __tablename__ = 'title_short_drafts'
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey('workspaces.id'), nullable=False, index=True)
    creator_id = Column(String, ForeignKey('users.id'), nullable=False)
    title = Column(String(500), nullable=False)
    duration = Column(Integer, nullable=False)
    language = Column(String(20), nullable=False)
    style = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False, default='researching')
    revision = Column(Integer, nullable=False, default=1)
    data = Column(Text, nullable=False, default='{}')
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
