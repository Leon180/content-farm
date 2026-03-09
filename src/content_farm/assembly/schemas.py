"""Assembly domain models. All frozen/immutable."""

from __future__ import annotations

from pydantic import BaseModel, Field

from content_farm.script_gen.schemas import Script
from content_farm.types import PipelineArtifact
from content_farm.visual.schemas import VisualArtifact
from content_farm.voice.schemas import VoiceArtifact


class AssemblyInput(BaseModel):
    """Bundle of all inputs needed for video assembly."""

    model_config = {"frozen": True}

    script: Script
    voice: VoiceArtifact
    visual: VisualArtifact
    background_music_path: str | None = None
    subtitle_path: str | None = None


class ComposedScene(BaseModel):
    """One fully composed scene (video + audio merged)."""

    model_config = {"frozen": True}

    scene_number: int
    file_path: str
    duration_seconds: float
    video_source: str
    audio_source: str


class AssemblySettings(BaseModel):
    """Render settings for the final output."""

    model_config = {"frozen": True}

    width: int = 1920
    height: int = 1080
    fps: int = 30
    video_bitrate: str = "5M"
    audio_bitrate: str = "192k"
    pixel_format: str = "yuv420p"
    preset: str = "medium"
    crf: int = Field(default=23, ge=0, le=51)
    background_music_volume: float = Field(default=0.15, ge=0.0, le=1.0)


class AssemblyArtifact(PipelineArtifact):
    """Output of the video assembly stage."""

    model_config = {"frozen": True}

    stage: str = "video_assembly"
    file_path: str = ""
    scenes: tuple[ComposedScene, ...] = ()
    total_duration_seconds: float = 0.0
    resolution: str = "1920x1080"
    fps: int = 30
    file_size_bytes: int = 0
    output_dir: str = ""
