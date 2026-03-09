"""SRT format helpers — pure functions, no I/O."""

from __future__ import annotations

from content_farm.subtitle.schemas import SubtitleSegment


def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp ``HH:MM:SS,mmm``."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def render_srt(segments: tuple[SubtitleSegment, ...]) -> str:
    """Render subtitle segments into SRT format string."""
    blocks: list[str] = []
    for seg in segments:
        block = (
            f"{seg.index}\n"
            f"{format_timestamp(seg.start_seconds)} --> "
            f"{format_timestamp(seg.end_seconds)}\n"
            f"{seg.text}\n"
        )
        blocks.append(block)
    return "\n".join(blocks)
