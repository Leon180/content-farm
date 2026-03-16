"""Assemble final video from timeline-named clips.

Scans visual/ for user-selected clips named ``MM:SS~MM:SS.<ext>``
(no index suffix), normalizes, concatenates, merges full audio,
and burns subtitles.  Supports both video (.mp4/.mov/.webm/.mkv)
and image (.png/.jpg/.jpeg/.webp) files.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_VIDEO_EXTS = frozenset({"mp4", "mov", "webm", "mkv"})
_IMAGE_EXTS = frozenset({"png", "jpg", "jpeg", "webp"})
_ALL_EXTS = _VIDEO_EXTS | _IMAGE_EXTS
_EXTS_PATTERN = "|".join(sorted(_ALL_EXTS))

# Matches "MM:SS~MM:SS.<ext>" (no _NN index = user's final pick)
_TIMELINE_RE = re.compile(
    rf"^(\d{{2}}):(\d{{2}})~(\d{{2}}):(\d{{2}})\.({_EXTS_PATTERN})$",
    re.IGNORECASE,
)

# Matches "MM:SS~MM:SS_NN.<ext>" (with index = candidate, not yet selected)
_CANDIDATE_RE = re.compile(
    rf"^(\d{{2}}):(\d{{2}})~(\d{{2}}):(\d{{2}})_\d+\.({_EXTS_PATTERN})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TimelineClip:
    """A user-selected clip with parsed time range."""

    path: Path
    start_seconds: float
    end_seconds: float

    @property
    def target_duration(self) -> float:
        return self.end_seconds - self.start_seconds

    @property
    def is_image(self) -> bool:
        return self.path.suffix.lower().lstrip(".") in _IMAGE_EXTS


def scan_timeline_clips(visual_dir: Path) -> list[TimelineClip]:
    """Find user-selected timeline clips, sorted by start time.

    Picks ``MM:SS~MM:SS.<ext>`` (without index suffix).
    Supports video (.mp4/.mov/.webm/.mkv) and image (.png/.jpg/.jpeg/.webp).
    """
    clips: list[TimelineClip] = []
    for f in visual_dir.iterdir():
        m = _TIMELINE_RE.match(f.name)
        if not m:
            continue
        start = int(m.group(1)) * 60 + int(m.group(2))
        end = int(m.group(3)) * 60 + int(m.group(4))
        clips.append(TimelineClip(path=f, start_seconds=start, end_seconds=end))

    clips.sort(key=lambda c: c.start_seconds)
    return clips


def has_timeline_clips(visual_dir: Path) -> bool:
    """Check if any timeline-named clips exist (for mode detection)."""
    return any(_TIMELINE_RE.match(f.name) for f in visual_dir.iterdir())


async def assemble_from_timeline(
    *,
    visual_dir: Path,
    audio_path: Path,
    subtitle_path: Path | None,
    output_dir: Path,
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path:
    """Full timeline assembly pipeline.

    1. Scan visual/ for MM:SS~MM:SS.mp4 clips
    2. Normalize each (scale/pad, fps, strip audio)
    3. Concat video segments
    4. Merge with full.mp3
    5. Burn subtitles if provided
    6. Output assembly/draft.mp4
    """
    clips = scan_timeline_clips(visual_dir)
    if not clips:
        msg = f"No timeline clips found in {visual_dir}"
        raise FileNotFoundError(msg)

    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = output_dir / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Normalize each clip
    normalized: list[Path] = []
    for i, clip in enumerate(clips):
        norm_path = tmp_dir / f"norm_{i:03d}.mp4"
        await _normalize_clip(
            clip, norm_path,
            ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path,
            width=width, height=height, fps=fps,
        )
        normalized.append(norm_path)

    # Step 2: Concat normalized clips
    concat_path = tmp_dir / "video_only.mp4"
    await _concat_clips(normalized, concat_path, ffmpeg_path)

    # Step 3: Merge with audio
    merged_path = tmp_dir / "merged.mp4"
    await _merge_audio(concat_path, audio_path, merged_path, ffmpeg_path)

    # Step 4: Burn subtitles (or just copy)
    draft_path = output_dir / "draft.mp4"
    if subtitle_path and subtitle_path.is_file():
        await _burn_subtitles(merged_path, subtitle_path, draft_path, ffmpeg_path)
    else:
        shutil.copy2(merged_path, draft_path)

    logger.info(
        "Timeline assembly complete: %d clips -> %s",
        len(clips), draft_path,
    )
    return draft_path


async def _normalize_clip(
    clip: TimelineClip,
    output_path: Path,
    *,
    ffmpeg_path: str,
    ffprobe_path: str,
    width: int,
    height: int,
    fps: int,
) -> None:
    """Normalize a clip to target resolution, fps, and duration.

    Handles both video files (speed-adjust to fit) and image files
    (loop as still frame for the target duration).
    """
    target_dur = clip.target_duration

    # Use file: protocol to handle : in filenames
    input_path = f"file:{clip.path.resolve()}"

    vf_scale = (
        f"scale={width}:{height}"
        ":force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,fps={fps}"
    )

    if clip.is_image:
        # Image → video: loop still image for target duration
        args = [
            ffmpeg_path, "-y",
            "-loop", "1",
            "-i", input_path,
            "-t", f"{target_dur:.2f}",
            "-vf", vf_scale,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
    else:
        # Video: speed-adjust to match target duration
        source_dur = await _probe_duration(clip.path, ffprobe_path)
        if source_dur > 0 and abs(source_dur - target_dur) > 0.1:
            speed = source_dur / target_dur
            pts = f"setpts=PTS/{speed:.4f}"
        else:
            pts = "setpts=PTS"

        vf = f"{vf_scale},{pts}"
        args = [
            ffmpeg_path, "-y",
            "-i", input_path,
            "-t", f"{target_dur:.2f}",
            "-vf", vf,
            "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]

    await _run(args)


async def _concat_clips(
    clip_paths: list[Path],
    output_path: Path,
    ffmpeg_path: str,
) -> None:
    """Concat normalized clips using concat demuxer."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False,
    ) as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")
        concat_list = f.name

    try:
        args = [
            ffmpeg_path, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            str(output_path),
        ]
        await _run(args)
    finally:
        Path(concat_list).unlink(missing_ok=True)


async def _merge_audio(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    ffmpeg_path: str,
) -> None:
    """Merge silent video with full audio track."""
    args = [
        ffmpeg_path, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]
    await _run(args)


async def _burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    ffmpeg_path: str,
) -> None:
    """Burn SRT subtitles into the video.

    Copies SRT to /tmp to avoid FFmpeg issues with CJK paths.
    """
    from content_farm.assembly.drawtext import build_drawtext_filter

    drawtext_vf = build_drawtext_filter(subtitle_path)

    # Write filter to file to avoid shell escaping issues
    vf_file = output_path.parent / f".vf_{output_path.stem}.txt"
    vf_file.write_text(drawtext_vf, encoding="utf-8")

    args = [
        ffmpeg_path, "-y",
        "-i", str(video_path),
        "-filter_script:v", str(vf_file),
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]
    await _run(args)


async def _probe_duration(path: Path, ffprobe_path: str) -> float:
    """Get video duration in seconds."""
    try:
        import json
        # Use file: protocol for paths with colons
        input_path = f"file:{path.resolve()}"
        proc = await asyncio.create_subprocess_exec(
            ffprobe_path, "-v", "quiet", "-print_format", "json",
            "-show_format", input_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            data = json.loads(stdout)
            return float(data["format"]["duration"])
    except (FileNotFoundError, KeyError, ValueError):
        pass
    return 0.0


async def _run(args: list[str]) -> None:
    """Run a subprocess, raising on failure."""
    logger.debug("Running: %s", " ".join(args))
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = stderr.decode(errors="replace")[-500:]
        raise RuntimeError(
            f"Command failed (exit {proc.returncode}): {detail}"
        )
