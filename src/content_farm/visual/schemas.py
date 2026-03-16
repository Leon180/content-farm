"""Visual generation domain models."""

from __future__ import annotations

from pydantic import BaseModel

from content_farm.types import PipelineArtifact


class VideoResult(BaseModel):
    """A single video search result from any provider."""

    model_config = {"frozen": True}

    provider_id: str
    url: str
    duration_seconds: int
    width: int
    height: int
    thumbnail_url: str = ""


class PhotoResult(BaseModel):
    """A single photo search result from any provider."""

    model_config = {"frozen": True}

    provider_id: str
    url: str
    width: int
    height: int



class ClipInfo(BaseModel):
    """Metadata for a single downloaded clip candidate."""

    model_config = {"frozen": True}

    scene_number: int
    clip_index: int  # 1-based sequential within scene
    file_name: str  # e.g. "scene_001_03.mp4"
    keyword: str
    provider_id: str  # e.g. "pexels:12345"
    duration_seconds: float
    width: int
    height: int
    thumbnail_url: str = ""
    selected: bool = False


class ClipsManifest(BaseModel):
    """Manifest of all downloaded clip candidates for a run."""

    clips: list[ClipInfo] = []
    output_dir: str = ""


class VisualAsset(BaseModel):
    """One visual asset corresponding to a scene."""

    model_config = {"frozen": True}

    scene_number: int
    file_path: str
    source: str
    duration_seconds: float
    query_used: str
    format: str = "mp4"


class VisualArtifact(PipelineArtifact):
    """Output of the visual generation stage."""

    model_config = {"frozen": True}

    stage: str = "visual_generation"
    assets: tuple[VisualAsset, ...] = ()
    total_duration_seconds: float = 0.0
    output_dir: str = ""
