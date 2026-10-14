"""Voice generation domain models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from content_farm.types import PipelineArtifact


class VoiceSettings(BaseModel):
    """ElevenLabs voice parameters."""

    model_config = {"frozen": True}

    stability: float = Field(default=0.5, ge=0.0, le=1.0)
    similarity_boost: float = Field(default=0.75, ge=0.0, le=1.0)
    style: float = Field(default=0.0, ge=0.0, le=1.0)
    use_speaker_boost: bool = False


class AudioSegment(BaseModel):
    """One audio segment corresponding to a scene."""

    model_config = {"frozen": True}

    scene_number: int
    file_path: str
    duration_seconds: float
    character_count: int
    format: str = "mp3"
    tts_text: str = ""  # Text sent to TTS (after pronunciation_map); used for alignment


class VoiceArtifact(PipelineArtifact):
    """Output of the voice generation stage."""

    model_config = {"frozen": True}

    stage: str = "voice_generation"
    segments: tuple[AudioSegment, ...] = ()
    total_duration_seconds: float = 0.0
    total_characters: int = 0
    voice_id: str = ""
    model_id: str = ""
    output_dir: str = ""
    full_audio_path: str = ""
