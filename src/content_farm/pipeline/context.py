"""Pipeline execution context — mutable state bag passed through stages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from content_farm.assembly.schemas import AssemblyArtifact
from content_farm.config import Settings
from content_farm.script_gen.schemas import Script
from content_farm.subtitle.schemas import SubtitleArtifact
from content_farm.telegram.approval import ApprovalGate
from content_farm.thumbnail.schemas import ThumbnailArtifact
from content_farm.visual.schemas import VisualArtifact
from content_farm.voice.schemas import VoiceArtifact
from content_farm.youtube.schemas import UploadArtifact


@dataclass
class PipelineContext:
    """Carries all intermediate pipeline state.

    Mutable by design — stages write their artifact into the
    corresponding slot. The orchestrator reads completed_stages
    to decide what to skip.
    """

    settings: Settings
    run_id: str
    run_dir: Path
    gate: ApprovalGate
    mode: str = "materials"  # "materials" | "full"

    # Completed stage names loaded from checkpoint DB
    completed_stages: set[str] = field(default_factory=set)

    # Artifact slots — populated by stages or checkpoint restore
    script: Script | None = None
    voice: VoiceArtifact | None = None
    visual: VisualArtifact | None = None
    subtitle: SubtitleArtifact | None = None
    thumbnail: ThumbnailArtifact | None = None
    assembly: AssemblyArtifact | None = None
    upload: UploadArtifact | None = None
    drive_link: str = ""
    template_video_path: str = ""

    def is_completed(self, stage: str) -> bool:
        """Check if a stage has been completed."""
        return stage in self.completed_stages

    def mark_completed(self, stage: str) -> None:
        """Mark a stage as completed."""
        self.completed_stages.add(stage)


def create_run_dir(base_output_dir: Path, topic: str) -> Path:
    """Create a timestamped run directory."""
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_topic = re.sub(r"[^\w\u4e00-\u9fff]", "_", topic)[:30].strip("_")
    run_dir = base_output_dir / f"{timestamp}_{safe_topic}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir