from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CelebrityCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    category: str = Field(default="NBA", max_length=64)


class CelebrityOut(BaseModel):
    id: str
    name: str
    slug: str
    aliases: list[str]
    category: str
    clip_count: int = 0
    total_duration_sec: float = 0.0
    created_at: datetime


class PresignedUploadRequest(BaseModel):
    celebrity_id: str
    filename: str
    content_type: str = "video/mp4"


class PresignedUploadResponse(BaseModel):
    r2_key: str
    upload_url: str
    expires_in_sec: int = 3600


class ClipIndexItem(BaseModel):
    celebrity_name: str
    category: str = "NBA"
    r2_key: str
    filename: str
    file_hash: str
    file_size_bytes: int = 0
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    aspect_ratio: str = "16:9"
    source_type: Literal["vault_upload", "web_original"] = "vault_upload"
    source_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class BulkIndexRequest(BaseModel):
    clips: list[ClipIndexItem] = Field(..., min_length=1, max_length=500)


class BulkIndexResponse(BaseModel):
    inserted: int
    skipped_existing: int
    celebrities_created: int


class ClipOut(BaseModel):
    id: str
    celebrity_id: str
    celebrity_name: str
    r2_key: str
    filename: str
    file_size_bytes: int
    duration_sec: float
    width: int
    height: int
    aspect_ratio: str
    source_type: str
    tags: list[str]
    usage_count: int
    created_at: datetime


class ProjectCreate(BaseModel):
    mode: Literal["short", "long"] = "short"
    input_type: Literal["title", "script"] = "title"
    title: str = Field(..., min_length=3, max_length=255)
    raw_input: str = Field(..., min_length=3)
    voice_name: str = "en-US-ChristopherNeural"
    target_duration_sec: int = Field(default=55, ge=15, le=1800)


class RenderJobOut(BaseModel):
    id: str
    project_id: str
    status: str
    current_step: str
    progress_pct: int
    worker_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ProjectOut(BaseModel):
    id: str
    mode: str
    input_type: str
    title: str
    raw_input: str
    final_script: Optional[str]
    detected_celebrities: list[str]
    voice_name: str
    target_duration_sec: int
    status: str
    output_r2_key: Optional[str]
    created_at: datetime
    latest_job: Optional[RenderJobOut] = None


class WorkerProgressUpdate(BaseModel):
    current_step: str
    progress_pct: int = Field(..., ge=0, le=100)
    status: Literal["processing", "completed", "failed"] = "processing"
    final_script: Optional[str] = None
    output_r2_key: Optional[str] = None
    error_message: Optional[str] = None


class MarkClipsUsedRequest(BaseModel):
    clip_ids: list[str] = Field(..., min_length=1, max_length=200)


class MarkClipsUsedResponse(BaseModel):
    updated: int


class LocalUploadResponse(BaseModel):
    uploaded: int
    skipped_existing: int
    clips: list[ClipOut]


class ScanLocalFolderRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)
    category: str = Field(default="NBA", max_length=64)
    probe_metadata: bool = False


class ScanLocalFolderStatus(BaseModel):
    scan_id: str
    folder_path: str
    category: str
    status: Literal["running", "completed", "failed"]
    total_files_found: int = 0
    processed_files: int = 0
    inserted: int = 0
    skipped_existing: int = 0
    celebrities_created: int = 0
    elapsed_ms: float = 0.0
    current_celebrity: Optional[str] = None
    error_message: Optional[str] = None


class DeleteProjectResponse(BaseModel):
    deleted: bool
    project_id: str
