"""Staging manager for collecting user-provided material clips."""

from __future__ import annotations

import logging
from pathlib import Path

from content_farm.compose.schemas import StagedClip
from content_farm.compose.timeline import classify_media, parse_clip_filename

logger = logging.getLogger(__name__)


class StagingManager:
    """Manages a material-staging session for a single pipeline run.

    Collects files sent by the user, validates timestamps, and
    tracks coverage of the final timeline.
    """

    def __init__(
        self,
        staging_dir: Path,
        run_id: str,
        voice_duration: float,
        voice_paths: tuple[Path, ...],
        subtitle_path: Path | None = None,
    ) -> None:
        self._staging_dir = staging_dir
        self._run_id = run_id
        self._voice_duration = voice_duration
        self._voice_paths = voice_paths
        self._subtitle_path = subtitle_path
        self._clips: list[StagedClip] = []

        staging_dir.mkdir(parents=True, exist_ok=True)

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def voice_duration(self) -> float:
        return self._voice_duration

    @property
    def voice_paths(self) -> tuple[Path, ...]:
        return self._voice_paths

    @property
    def subtitle_path(self) -> Path | None:
        return self._subtitle_path

    @property
    def staging_dir(self) -> Path:
        return self._staging_dir

    @property
    def clip_count(self) -> int:
        return len(self._clips)

    def add_clip(self, file_path: Path, original_filename: str) -> StagedClip | str:
        """Parse filename, validate, and add a clip.

        Returns ``StagedClip`` on success or an error message string.
        """
        parsed = parse_clip_filename(original_filename)
        if parsed is None:
            return (
                f"檔名格式不正確: {original_filename}\n"
                "請使用 MM:SStoMM:SS.ext 格式（例如 00:00to00:03.mp4）"
            )

        start, end, ext = parsed

        try:
            media_type = classify_media(ext)
        except ValueError:
            return f"不支援的檔案格式: .{ext}"

        # Check duration bounds
        if start >= self._voice_duration:
            return (
                f"起始時間 {start:.0f}s 超出影片總長 "
                f"{self._voice_duration:.0f}s"
            )

        clip_end = min(end, self._voice_duration)

        # Check overlap with existing clips
        for existing in self._clips:
            if start < existing.end_seconds and clip_end > existing.start_seconds:
                return (
                    f"時間重疊: {original_filename} "
                    f"({start:.0f}-{clip_end:.0f}s) 與 "
                    f"{existing.original_filename} "
                    f"({existing.start_seconds:.0f}-{existing.end_seconds:.0f}s)"
                )

        clip = StagedClip(
            file_path=str(file_path),
            original_filename=original_filename,
            start_seconds=start,
            end_seconds=clip_end,
            media_type=media_type,
        )
        self._clips.append(clip)
        logger.info(
            "Staged clip: %s → %.1f-%.1fs (%s)",
            original_filename, start, clip_end, media_type,
        )
        return clip

    def get_clips(self) -> tuple[StagedClip, ...]:
        """Return all staged clips sorted by start time."""
        return tuple(sorted(self._clips, key=lambda c: c.start_seconds))

    def format_summary(self) -> str:
        """Format a user-friendly summary of staged clips and coverage."""
        if not self._clips:
            return "尚未收到任何素材。"

        sorted_clips = sorted(self._clips, key=lambda c: c.start_seconds)
        total = self._voice_duration
        covered = sum(c.end_seconds - c.start_seconds for c in sorted_clips)
        pct = (covered / total * 100) if total > 0 else 0

        lines = [f"已收到 {len(sorted_clips)} 個素材 (覆蓋率: {pct:.0f}%)"]
        for clip in sorted_clips:
            dur = clip.end_seconds - clip.start_seconds
            lines.append(
                f"  {clip.start_seconds:.0f}-{clip.end_seconds:.0f}s "
                f"({dur:.0f}s) {clip.original_filename}"
            )

        # Show gaps
        gaps: list[tuple[float, float]] = []
        cursor = 0.0
        for clip in sorted_clips:
            if clip.start_seconds > cursor + 0.01:
                gaps.append((cursor, clip.start_seconds))
            cursor = max(cursor, clip.end_seconds)
        if cursor < total - 0.01:
            gaps.append((cursor, total))

        if gaps:
            lines.append(f"\n空白區間 ({len(gaps)} 段):")
            for g_start, g_end in gaps:
                lines.append(f"  {g_start:.0f}-{g_end:.0f}s ({g_end - g_start:.0f}s)")

        return "\n".join(lines)
