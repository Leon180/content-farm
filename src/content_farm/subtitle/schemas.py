"""Subtitle domain models. All frozen/immutable."""

from __future__ import annotations

from pydantic import BaseModel

from content_farm.script_gen.schemas import Script
from content_farm.types import PipelineArtifact
from content_farm.voice.schemas import VoiceArtifact


class SubtitleSegment(BaseModel):
    """One subtitle entry with timing and text."""

    model_config = {"frozen": True}

    index: int
    start_seconds: float
    end_seconds: float
    text: str
    scene_number: int


class SubtitleInput(BaseModel):
    """Bundle of inputs needed for subtitle generation."""

    model_config = {"frozen": True}

    script: Script
    voice: VoiceArtifact


class SubtitleArtifact(PipelineArtifact):
    """Output of the subtitle generation stage."""

    model_config = {"frozen": True}

    stage: str = "subtitle_generation"
    file_path: str = ""
    segments: tuple[SubtitleSegment, ...] = ()
    total_segments: int = 0
    total_duration_seconds: float = 0.0
    language: str = "zh-TW"
    output_dir: str = ""
