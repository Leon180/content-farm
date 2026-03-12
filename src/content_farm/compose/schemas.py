"""Data models for the compose module."""

from __future__ import annotations

from pydantic import BaseModel


class StagedClip(BaseModel):
    """A single material file received from the user."""

    model_config = {"frozen": True}

    file_path: str
    original_filename: str
    start_seconds: float
    end_seconds: float
    media_type: str  # "video" | "image"


class TimelineSegment(BaseModel):
    """A segment on the final timeline (user clip or gap filler)."""

    model_config = {"frozen": True}

    file_path: str
    start_seconds: float
    end_seconds: float
    is_gap: bool = False

    @property
    def duration(self) -> float:
        return self.end_seconds - self.start_seconds


class ComposeResult(BaseModel):
    """Result of a compose operation."""

    model_config = {"frozen": True}

    file_path: str
    duration_seconds: float
    clip_count: int
    gap_count: int
    drive_link: str = ""
