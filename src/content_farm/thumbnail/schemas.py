"""Thumbnail domain models. All frozen/immutable."""

from __future__ import annotations

from pydantic import BaseModel, Field

from content_farm.script_gen.schemas import Script
from content_farm.types import PipelineArtifact


class ThumbnailSettings(BaseModel):
    """Render parameters for thumbnail generation."""

    model_config = {"frozen": True}

    width: int = 1280
    height: int = 720
    font_size: int = 100
    stroke_width: int = 4
    quality: int = Field(default=85, ge=1, le=100)
    text_color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    background_color: str = "#1a1a2e"
    gradient_end_color: str = "#16213e"
    font_path: str = ""
    max_title_chars: int = 40


class ThumbnailInput(BaseModel):
    """Bundle of inputs needed for thumbnail generation."""

    model_config = {"frozen": True}

    script: Script
    video_path: str | None = None
    background_image_path: str | None = None


class ThumbnailArtifact(PipelineArtifact):
    """Output of the thumbnail generation stage."""

    model_config = {"frozen": True}

    stage: str = "thumbnail_generation"
    file_path: str = ""
    width: int = 1280
    height: int = 720
    file_size_bytes: int = 0
    used_keyframe: bool = False
    output_dir: str = ""
