"""YouTube upload domain models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from content_farm.script_gen.schemas import Script
from content_farm.types import PipelineArtifact


class UploadSettings(BaseModel):
    """Configuration for a YouTube video upload."""

    model_config = {"frozen": True}

    privacy_status: str = "private"  # "private" | "unlisted" | "public"
    category_id: str = "22"  # People & Blogs
    made_for_kids: bool = False
    default_language: str = "zh-TW"
    chunk_size_bytes: int = Field(default=256 * 1024 * 1024, ge=1)  # 256MB
    # Scheduled release (RFC 3339 with offset). YouTube only honours it on private videos.
    publish_at: str | None = None
    # status.containsSyntheticMedia — altered/synthetic content disclosure. None = not sent.
    contains_synthetic_media: bool | None = None


class UploadInput(BaseModel):
    """Input data for the YouTube upload stage."""

    model_config = {"frozen": True}

    script: Script
    video_path: str
    thumbnail_path: str | None = None
    subtitle_path: str | None = None
    tags: tuple[str, ...] = ()


class UploadArtifact(PipelineArtifact):
    """Output from the YouTube upload stage."""

    model_config = {"frozen": True}

    stage: str = "youtube_upload"
    video_id: str = ""
    url: str = ""
    privacy_status: str = "private"
    thumbnail_set: bool = False
    captions_set: bool = False
