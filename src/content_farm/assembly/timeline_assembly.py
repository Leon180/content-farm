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

# Matches "MM:SS~MM:SS.<ext>" or "MM:SS.mmm~MM:SS.mmm.<ext>"
# (no _NN index = user's final pick)
_TIMELINE_RE = re.compile(
    rf"^(\d{{2}}):(\d{{2}})(?:\.(\d{{1,3}}))?~(\d{{2}}):(\d{{2}})(?:\.(\d{{1,3}}))?\.({_EXTS_PATTERN})$",
    re.IGNORECASE,
)

# Matches "MM:SS~MM:SS_NN.<ext>" (with index = candidate, not yet selected)
_CANDIDATE_RE = re.compile(
    rf"^(\d{{2}}):(\d{{2}})(?:\.(\d{{1,3}}))?~(\d{{2}}):(\d{{2}})(?:\.(\d{{1,3}}))?_\d+\.({_EXTS_PATTERN})$",
    re.IGNORECASE,
)


def _parse_ms(ms_str: str | None) -> float:
    """Parse optional millisecond group (1-3 digits) to fractional seconds."""
    if not ms_str:
        return 0.0
    return int(ms_str.ljust(3, "0")) / 1000.0


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
        start = int(m.group(1)) * 60 + int(m.group(2)) + _parse_ms(m.group(3))
        end = int(m.group(4)) * 60 + int(m.group(5)) + _parse_ms(m.group(6))
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
    width: int = 1080,
    height: int = 1920,
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

    # Step 1: Normalize each clip, filling gaps with black frames
    normalized: list[Path] = []
    cursor = 0.0  # current position in seconds
    for i, clip in enumerate(clips):
        # Insert black filler if there's a gap before this clip
        gap = clip.start_seconds - cursor
        if gap > 0.05:  # >50ms gap
            filler_path = tmp_dir / f"black_{i:03d}.mp4"
            await _generate_black(
                filler_path, duration=gap,
                ffmpeg_path=ffmpeg_path,
                width=width, height=height, fps=fps,
            )
            normalized.append(filler_path)

        norm_path = tmp_dir / f"norm_{i:03d}.mp4"
        await _normalize_clip(
            clip, norm_path,
            ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path,
            width=width, height=height, fps=fps,
        )
        normalized.append(norm_path)
        cursor = clip.end_seconds

    # Step 2: Concat normalized clips
    concat_path = tmp_dir / "video_only.mp4"
    await _concat_clips(normalized, concat_path, ffmpeg_path)

    # Step 3: Merge with audio
    merged_path = tmp_dir / "merged.mp4"
    await _merge_audio(concat_path, audio_path, merged_path, ffmpeg_path)

    # Step 4: Burn subtitles (or just copy)
    draft_path = output_dir / "draft.mp4"
    if subtitle_path and subtitle_path.is_file():
        await _burn_subtitles(
            merged_path, subtitle_path, draft_path, ffmpeg_path,
            width=width, height=height,
        )
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
        # Video: trim to target duration (take first N seconds only)
        args = [
            ffmpeg_path, "-y",
            "-i", input_path,
            "-t", f"{target_dur:.2f}",
            "-vf", vf_scale,
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
        "-movflags", "+faststart",
        str(output_path),
    ]
    await _run(args)


async def _burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    ffmpeg_path: str,
    width: int = 1080,
    height: int = 1920,
) -> None:
    """Burn SRT subtitles into the video using the ASS filter.

    Converts SRT → ASS with correct PlayResX/PlayResY so that libass
    uses the actual video dimensions as its coordinate space.  Alignment=5
    (SSA numpad 5) centers text both horizontally and vertically.
    FontSize=52 is calibrated for a 1080px-wide canvas.
    """
    from content_farm.assembly.drawtext import find_cjk_font

    # Step 1: convert SRT → raw ASS via FFmpeg
    tmp_srt = output_path.parent / f"_tmp_subs_{output_path.stem}.srt"
    tmp_ass_raw = output_path.parent / f"_tmp_subs_{output_path.stem}_raw.ass"
    tmp_ass = output_path.parent / f"_tmp_subs_{output_path.stem}.ass"
    shutil.copy2(subtitle_path, tmp_srt)

    try:
        convert_args = [
            ffmpeg_path, "-y",
            "-i", str(tmp_srt),
            str(tmp_ass_raw),
        ]
        await _run(convert_args)

        # Step 2: rewrite ASS header with correct PlayRes and style
        font_name = "Arial"
        cjk_font = find_cjk_font()
        if cjk_font:
            font_name = Path(cjk_font).stem

        ass_content = tmp_ass_raw.read_text(encoding="utf-8")
        new_header = (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            f"PlayResX: {width}\n"
            f"PlayResY: {height}\n"
            "ScaledBorderAndShadow: yes\n"
            "\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour,"
            " OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut,"
            " ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow,"
            " Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{font_name},78,"
            "&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
            "1,0,0,0,100,100,0,0,1,3,1,5,40,40,0,1\n"
        )

        import re as _re
        patched = _re.sub(
            r"\[Script Info\].*?(?=\[Events\])",
            new_header + "\n",
            ass_content,
            flags=_re.DOTALL,
        )
        tmp_ass.write_text(patched, encoding="utf-8")

        # Step 3: burn ASS into video
        args = [
            ffmpeg_path, "-y",
            "-i", str(video_path),
            "-vf", f"ass={tmp_ass}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]
        await _run(args)
    finally:
        tmp_srt.unlink(missing_ok=True)
        tmp_ass_raw.unlink(missing_ok=True)
        tmp_ass.unlink(missing_ok=True)


async def _generate_black(
    output_path: Path,
    *,
    duration: float,
    ffmpeg_path: str,
    width: int,
    height: int,
    fps: int,
) -> None:
    """Generate a silent black video of the given duration."""
    args = [
        ffmpeg_path, "-y",
        "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}:d={duration:.2f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
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
