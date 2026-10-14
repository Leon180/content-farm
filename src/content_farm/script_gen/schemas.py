"""Script generation domain models. All frozen/immutable."""

from __future__ import annotations

from pydantic import BaseModel, Field

from content_farm.types import (
    GenreTemplate,
    Orientation,
    PipelineArtifact,
    Tone,
    VideoLength,
)


class ScriptRequest(BaseModel):
    """Validated input for script generation."""

    model_config = {"frozen": True}

    topic: str = Field(min_length=3, max_length=200)
    keywords: tuple[str, ...] = ()
    video_length: VideoLength = VideoLength.MEDIUM
    tone: Tone = Tone.EDUCATIONAL
    language: str = "zh-TW"  # Output language for narration
    target_scene_count: int | None = None
    orientation: Orientation = Orientation.PORTRAIT
    genre: GenreTemplate | None = None


class VisualHint(BaseModel):
    """What should appear on screen during narration."""

    model_config = {"frozen": True}

    description: str
    style: str = "stock_footage"
    keywords: tuple[str, ...] = ()
    source_preference: str = "auto"  # "auto" | "stock" | "ai"


class Scene(BaseModel):
    """One scene in the video script."""

    model_config = {"frozen": True}

    scene_number: int
    title: str
    narration: str
    visual_hint: VisualHint
    duration_seconds: float
    transition: str = "cut"
    chapter_number: int | None = None  # long-form only
    b_roll_keywords: tuple[str, ...] = ()  # long-form B-roll refresh


class ChapterOutline(BaseModel):
    """One chapter in a long-form video — produced before scene expansion."""

    model_config = {"frozen": True}

    chapter_number: int
    title: str
    summary: str
    duration_seconds: float
    key_points: tuple[str, ...] = ()
    hook: str = ""
    payoff: str = ""
    start_timestamp: float = 0.0  # seconds from video start


class ChapterOutlineList(BaseModel):
    """Chapter-level outline returned by the cheap model for long-form videos."""

    model_config = {"frozen": True}

    video_title: str
    description: str
    chapters: tuple[ChapterOutline, ...] = ()
    tags: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()


class SceneOutline(BaseModel):
    """Lightweight scene outline from Phase 1 (cheap model)."""

    model_config = {"frozen": True}

    scene_number: int
    title: str
    summary: str
    duration_seconds: float


class SceneOutlineList(BaseModel):
    """List of scene outlines returned by the cheap model."""

    model_config = {"frozen": True}

    video_title: str
    description: str
    scenes: tuple[SceneOutline, ...] = ()
    tags: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()


class ExpandedScene(BaseModel):
    """Full scene narration + visual hint from Phase 2 (expensive model)."""

    model_config = {"frozen": True}

    scene_number: int
    title: str
    narration: str
    visual_hint: VisualHint
    duration_seconds: float
    transition: str = "cut"


class Script(PipelineArtifact):
    """Complete video script — output of the script generation stage."""

    model_config = {"frozen": True}

    stage: str = "script_generation"
    video_title: str
    description: str
    scenes: tuple[Scene, ...] = ()
    target_length: VideoLength = VideoLength.MEDIUM
    tone: Tone = Tone.EDUCATIONAL
    language: str = "zh-TW"
    total_duration_seconds: float = 0
    tags: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    ai_disclosure: bool = True
    pronunciation_map: dict[str, str] = {}
    orientation: Orientation = Orientation.PORTRAIT
    genre: GenreTemplate | None = None
    chapters: tuple[ChapterOutline, ...] = ()  # non-empty for long-form

    @property
    def full_narration(self) -> str:
        """Concatenate all scene narrations."""
        return "\n\n".join(s.narration for s in self.scenes)
