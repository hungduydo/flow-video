from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    url: str
    cookies_file: Optional[str] = None
    model: Literal["large-v3", "large-v2", "medium", "small", "base"] = "large-v3"
    transcriber: Literal["whisper", "deepgram"] = "whisper"
    translator: Literal["gemini", "claude", "ollama_cloud"] = "gemini"
    tts_provider: Literal["edge_tts", "elevenlabs"] = "edge_tts"
    platform: Literal["youtube", "tiktok", "both"] = "youtube"
    show_subtitle: bool = True
    crf: int = Field(default=23, ge=0, le=51)
    tiktok_crop_x: Optional[int] = None
    from_step: Optional[int] = Field(default=None, ge=1, le=7)
    force: bool = False
    output_dir: str = "output"


class RetryRequest(BaseModel):
    """All fields are optional — overrides merged on top of original job request."""
    from_step: Optional[int] = Field(default=None, ge=1, le=7)
    model: Optional[Literal["large-v3", "large-v2", "medium", "small", "base"]] = None
    transcriber: Optional[Literal["whisper", "deepgram"]] = None
    translator: Optional[Literal["gemini", "claude", "ollama_cloud"]] = None
    tts_provider: Optional[Literal["edge_tts", "elevenlabs"]] = None
    platform: Optional[Literal["youtube", "tiktok", "both"]] = None
    show_subtitle: Optional[bool] = None
    crf: Optional[int] = Field(default=None, ge=0, le=51)
    tiktok_crop_x: Optional[int] = None
    force: Optional[bool] = None


class FileInfo(BaseModel):
    name: str
    size_bytes: Optional[int]
    available: bool


class FileListResponse(BaseModel):
    job_id: str
    output_dir: Optional[str]
    files: list[FileInfo]


class JobResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]
    video_id: Optional[str]
    current_step: Optional[int | str]
    current_step_name: Optional[str]
    failed_step: Optional[int | str]
    failed_step_name: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error: Optional[str]
    output_files: list[str]
    request: JobCreateRequest


class LogsResponse(BaseModel):
    job_id: str
    lines: list[str]
    cursor: int
    is_done: bool


class HealthResponse(BaseModel):
    status: str
    jobs: dict[str, int]


# ── Flow models ───────────────────────────────────────────────────────────────

class FlowCreateRequest(BaseModel):
    name: str
    definition: JobCreateRequest
    schedule: Optional[str] = None   # cron string e.g. "0 9 * * *"
    enabled: bool = True


class FlowUpdateRequest(BaseModel):
    name: Optional[str] = None
    definition: Optional[JobCreateRequest] = None
    schedule: Optional[str] = None
    enabled: Optional[bool] = None


class FlowResponse(BaseModel):
    id: str
    name: str
    definition: JobCreateRequest
    schedule: Optional[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime
