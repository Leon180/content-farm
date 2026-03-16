"""Build visual timeline from SRT subtitles.

Parses subtitles → groups by scene → assigns time ranges for clip naming.
Renders timeline.md for user to review material assignments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TimelineBlock:
    """A contiguous time range mapped to one visual clip."""

    start_seconds: float
    end_seconds: float
    scene_number: int
    narration: str  # combined subtitle text in this range
    keywords: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end_seconds - self.start_seconds

    @property
    def label(self) -> str:
        """MM:SS~MM:SS label used for clip filenames."""
        return f"{format_time(self.start_seconds)}~{format_time(self.end_seconds)}"


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS (zero-padded)."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def parse_srt(srt_text: str) -> list[tuple[float, float, str]]:
    """Parse SRT into (start_sec, end_sec, text) tuples."""
    blocks: list[tuple[float, float, str]] = []
    pattern = re.compile(
        r"(\d+)\s+"
        r"(\d{2}:\d{2}:\d{2}[,.]?\d*)\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]?\d*)\s*\n"
        r"((?:(?!\d+\s*\n\d{2}:).+\n?)+)",
        re.MULTILINE,
    )
    for m in pattern.finditer(srt_text):
        start = _srt_time_to_seconds(m.group(2))
        end = _srt_time_to_seconds(m.group(3))
        text = m.group(4).strip()
        blocks.append((start, end, text))
    return blocks


def _srt_time_to_seconds(ts: str) -> float:
    """Convert HH:MM:SS,mmm or HH:MM:SS.mmm to float seconds."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def build_timeline_from_srt(
    srt_text: str,
    scene_boundaries: list[tuple[int, float, float, list[str]]],
) -> list[TimelineBlock]:
    """Build timeline blocks from SRT text and scene info.

    Args:
        srt_text: Raw SRT file content.
        scene_boundaries: List of (scene_number, start_sec, end_sec, keywords)
            for each scene.  Typically derived from voice segments + script.

    Returns:
        One TimelineBlock per scene with aggregated narration.
    """
    srt_entries = parse_srt(srt_text)

    blocks: list[TimelineBlock] = []
    for scene_num, scene_start, scene_end, keywords in scene_boundaries:
        # Collect subtitle lines within this scene's time range
        texts = []
        for s_start, _s_end, text in srt_entries:
            if scene_start <= s_start < scene_end:
                texts.append(text)

        blocks.append(TimelineBlock(
            start_seconds=scene_start,
            end_seconds=scene_end,
            scene_number=scene_num,
            narration=" ".join(texts),
            keywords=keywords,
        ))

    return blocks


def build_scene_boundaries(
    script_data: dict,
    voice_data: dict | None = None,
) -> list[tuple[int, float, float, list[str]]]:
    """Extract scene boundaries from script + voice artifacts.

    Returns list of (scene_number, start_sec, end_sec, keywords).
    """
    scenes = script_data.get("scenes", [])

    # Build duration map from voice segments if available
    durations: dict[int, float] = {}
    if voice_data:
        for seg in voice_data.get("segments", []):
            durations[seg["scene_number"]] = seg["duration_seconds"]

    boundaries: list[tuple[int, float, float, list[str]]] = []
    offset = 0.0
    for scene in scenes:
        scene_num = scene["scene_number"]
        dur = durations.get(scene_num, scene.get("duration_seconds", 10.0))
        keywords = scene.get("visual_hint", {}).get("keywords", [])
        boundaries.append((scene_num, offset, offset + dur, keywords))
        offset += dur

    return boundaries


def render_timeline_md(blocks: list[TimelineBlock]) -> str:
    """Render timeline blocks as Markdown for user review."""
    lines = ["# Visual Timeline", ""]
    lines.append("| Time | Scene | Narration | Keywords | Clip File |")
    lines.append("|------|-------|-----------|----------|-----------|")

    for b in blocks:
        narration_short = b.narration[:40] + "..." if len(b.narration) > 40 else b.narration
        kw = ", ".join(b.keywords[:4]) if b.keywords else "-"
        lines.append(
            f"| `{b.label}` | {b.scene_number} "
            f"| {narration_short} | {kw} | `{b.label}.mp4` |"
        )

    lines.append("")
    lines.append("## Instructions")
    lines.append("")
    lines.append("1. Each row = one visual clip to prepare")
    lines.append("2. Download/select clips and name them `MM:SS~MM:SS.mp4`")
    lines.append("3. Place all clips in the `visual/` directory")
    lines.append("4. Run `/project:assembly` when ready")
    lines.append("")
    return "\n".join(lines)
