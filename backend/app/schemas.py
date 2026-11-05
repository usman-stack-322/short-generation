from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.tts.director import VoiceSelection, VoiceProvider
from app.core.languages import language_info


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RegisterInput(InputModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    workspace_name: str = Field(default="My Workspace", min_length=2, max_length=160)


class LoginInput(InputModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class MemberInput(InputModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    role: str = "MEMBER"

    @field_validator("role")
    @classmethod
    def valid_role(cls, value):
        value = value.upper()
        if value not in {"ADMIN", "MEMBER"}:
            raise ValueError("Role must be ADMIN or MEMBER.")
        return value


class MemberStatusInput(InputModel):
    active: bool | None = None
    role: str | None = Field(default=None, pattern='^(OWNER|ADMIN|MEMBER)$')
    can_manage_admins: bool | None = None


class ChannelInput(InputModel):
    evergreen_source_urls: list[str] = Field(default_factory=list,max_length=20)
    @field_validator('evergreen_source_urls')
    @classmethod
    def historical_references(cls,value):
        from app.core.network import reference_urls
        return reference_urls(value)
    automatic_evergreen_fallback: bool = False
    automatic_generation_enabled: bool = False
    generation_duration: int = Field(default=45,ge=30,le=60)
    @field_validator('generation_duration')
    @classmethod
    def automatic_duration(cls,value):
        if value not in {30,45,60}:raise ValueError('Duration must be 30, 45 or 60 seconds')
        return value
    niche: str = Field(default='',max_length=160)
    voice_style: VoiceSelection = 'auto'
    tts_provider: VoiceProvider = 'auto'
    name: str = Field(min_length=2, max_length=160)
    member_id: str | None = None
    youtube_channel_id: str | None = Field(default=None, max_length=255)
    profile_image_url: str | None = Field(default=None, max_length=1000)
    default_language: str = Field(default="en-US", max_length=20)
    @field_validator('default_language')
    @classmethod
    def channel_language(cls,value):
        return language_info(value).code
    default_voice: str = Field(default="en-US", max_length=80)
    daily_video_target: int = Field(default=1, ge=1, le=3)
    approval_required: bool = True
    approval_policy: str = "owner_only"

    @field_validator('approval_policy')
    @classmethod
    def policy(cls, value):
        if value not in {'owner_only','member_only','either','both'}:
            raise ValueError('Invalid approval policy')
        return value


class PersonalityInput(InputModel):
    visibility: str | None = None
    default_voice_style: VoiceSelection = 'auto'
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(default="General", max_length=100)
    description: str = Field(default="", max_length=2000)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    preferred_language: str = Field(default="en-US", max_length=20)
    @field_validator('preferred_language')
    @classmethod
    def theme_language(cls,value):
        return language_info(value).code
    tone: str = Field(default="Clear and energetic", max_length=160)
    default_duration: int = Field(default=45, ge=30, le=60)
    default_voice: str = Field(default="en-US", max_length=80)
    enabled: bool = True
    channel_id: str | None = None
    research_keywords: list[str] = Field(default_factory=list, max_length=20)


class GenerateVideoInput(InputModel):
    content_mode: str = 'hybrid'
    collection_id: str | None = None
    avoid_recent_media: bool = True
    @field_validator('content_mode')
    @classmethod
    def valid_content_mode(cls,value):
        if value not in {'auto','hybrid','my_assets'}:raise ValueError('Choose Auto Research, Hybrid or My Assets')
        return value
    operation_id: str | None = Field(default=None,min_length=8,max_length=80)
    voice_style: VoiceSelection | None = None
    tts_provider: VoiceProvider | None = None
    channel_id: str
    personality_id: str
    topic_mode: str = "current"
    manual_topic: str | None = Field(default=None, max_length=300)
    duration: int = Field(default=45, ge=30, le=60)
    voice: str | None = Field(default=None, min_length=1, max_length=80)
    language: str | None = Field(default=None, max_length=20)
    video_style: str = Field(default="Documentary", max_length=80)
    candidate_id: str | None = None
    music_id: str | None = None

    @field_validator("duration")
    @classmethod
    def valid_duration(cls, value):
        if value not in {30, 45, 60}:
            raise ValueError("Duration must be 30, 45 or 60 seconds.")
        return value

    @field_validator("language")
    @classmethod
    def valid_language(cls, value):
        return language_info(value).code if value is not None else None

    @field_validator("topic_mode")
    @classmethod
    def valid_topic_mode(cls, value):
        value = value.lower()
        if value not in {"current", "manual"}:
            raise ValueError("Topic mode must be current or manual.")
        return value


class RegenerateInput(InputModel):
    language: str | None = Field(default=None,max_length=20)
    @field_validator('language')
    @classmethod
    def output_language(cls,value):
        return language_info(value).code if value is not None else None
    voice_style: VoiceSelection | None = None
    scope: str = "all"

    @field_validator("scope")
    @classmethod
    def valid_scope(cls, value):
        if value not in {"all", "script", "voice", "video", "assets", "cover", "seo", "retry"}:
            raise ValueError("Invalid regeneration scope")
        return value


class ScriptInput(InputModel):
    hook: str = Field(min_length=1, max_length=1000)
    context: str = Field(min_length=1, max_length=2000)
    main_story: str = Field(min_length=1, max_length=4000)
    why_it_matters: str = Field(min_length=1, max_length=2000)
    ending: str = Field(min_length=1, max_length=1000)


class RejectInput(InputModel):
    note: str = Field(default='',max_length=1000)


class PublishInput(InputModel):
    content_revision: int = Field(ge=1)
    confirmed: bool
    privacy_status: str = 'private'
    made_for_kids: bool
    scheduled_at: str | None = None
    timezone: str = 'UTC'

    @field_validator('privacy_status')
    @classmethod
    def privacy(cls,value):
        if value != 'private':
            raise ValueError('Only private uploads are permitted; publish manually in YouTube Studio')
        return value


class SettingsInput(InputModel):
    default_provider: str = 'local'
    default_voice: str = Field(default='en-US',max_length=80)
    default_duration: int = Field(default=45,ge=30,le=60)
    subtitle_mode: str = 'sentence'
    font_size: int = Field(default=58,ge=36,le=90)
    caption_position: str = 'bottom'
    max_words: int = Field(default=6,ge=2,le=9)
    highlight_color: str = Field(default='#61e8b6',pattern=r'^#[0-9a-fA-F]{6}$')
    transitions: bool = True
    research_provider: str = 'demo'
    background_music_id: str | None = None
    voice_speed: float = Field(default=1,ge=.75,le=1.4)

    @field_validator('default_provider')
    @classmethod
    def provider(cls,v):
        if v not in {'auto','local','google','elevenlabs'}: raise ValueError('Invalid voice provider')
        return v

    @field_validator('subtitle_mode')
    @classmethod
    def captions(cls,v):
        if v not in {'sentence','word-highlight'}: raise ValueError('Invalid subtitle mode')
        return v

    @field_validator('caption_position')
    @classmethod
    def position(cls,v):
        if v not in {'bottom','center'}: raise ValueError('Invalid caption position')
        return v

    @field_validator('research_provider')
    @classmethod
    def research(cls,v):
        if v not in {'demo','rss'}: raise ValueError('Invalid research provider')
        return v

