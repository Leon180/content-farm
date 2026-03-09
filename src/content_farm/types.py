"""Shared domain types for the content farm pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Tone(str, Enum):
    EDUCATIONAL = "educational"
    ENTERTAINING = "entertaining"
    DRAMATIC = "dramatic"
    CONVERSATIONAL = "conversational"
    DOCUMENTARY = "documentary"


class VideoLength(str, Enum):
    SHORT = "short"    # 1-3 min
    MEDIUM = "medium"  # 5-10 min
    LONG = "long"      # 10-20 min


class PipelineArtifact(BaseModel):
    """Base for all pipeline stage outputs. Frozen for immutability."""

    model_config = {"frozen": True}

    artifact_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stage: str


class TopicBrief(BaseModel):
    """Input to the pipeline — what video to make."""

    model_config = {"frozen": True}

    topic: str
    keywords: tuple[str, ...] = ()
    video_length: VideoLength = VideoLength.MEDIUM
    tone: Tone = Tone.EDUCATIONAL
