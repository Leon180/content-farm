"""ffmpeg recipes for explainer media clips (1920x1080, 30 fps, silent H.264).

Every builder writes exactly ``frame_count(duration)`` frames so a clip is
never shorter than its timeline slot (assembly trims, it does not pad).
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

WIDTH, HEIGHT, FPS = 1920, 1080, 30
MAX_SLOWDOWN = 1.5  # stretch footage up to 1.5x slower before looping it instead
_ENCODE = ("-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p")
_COVER = (
    f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
    f"crop={WIDTH}:{HEIGHT},setsar=1"
)

TRANSITIONS = {"crossfade": "fade", "fadeblack": "fadeblack", "push": "slideleft"}


class FFmpegError(RuntimeError):
    pass


def frame_count(duration: float, fps: int = FPS) -> int:
    if not (duration > 0 and math.isfinite(duration)):
        raise ValueError(f"bad clip duration {duration!r}")
    return max(1, math.ceil(round(duration * fps, 6)))


def run(args: list[str], *, timeout: float = 600) -> None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise FFmpegError(f"{args[0]} failed to run: {exc}") from exc
    if result.returncode != 0:
        raise FFmpegError(f"{' '.join(args[:3])}… exit {result.returncode}: {result.stderr[-600:]}")


def probe(path: Path) -> dict:
    """Duration and first video stream size."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",
             "-show_streams", "-select_streams", "v:0", str(path)],
            capture_output=True, text=True, check=True, timeout=30,
        )
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return {
            "duration": float(data["format"]["duration"]),
            "width": int(stream["width"]),
            "height": int(stream["height"]),
        }
    except (OSError, subprocess.SubprocessError, KeyError, IndexError, ValueError) as exc:
        raise FFmpegError(f"ffprobe failed for {path}: {exc}") from exc


def _out(path: Path, frames: int) -> list[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    return ["-frames:v", str(frames), "-r", str(FPS), *_ENCODE, str(path)]


def still_to_clip(image: Path, out: Path, duration: float) -> Path:
    """Hold one image for ``duration`` seconds."""
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(image),
         "-vf", _COVER, *_out(out, frame_count(duration))])
    return out


def frames_to_clip(pattern: str, out: Path, duration: float) -> Path:
    """Image sequence (``frame_%05d.png``) → clip; the last frame is held to ``duration``."""
    total = frame_count(duration)
    run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", pattern,
         "-vf", f"{_COVER},tpad=stop_mode=clone:stop={total}", *_out(out, total)])
    return out


def stock_plan(source_seconds: float, duration: float) -> tuple[str, float]:
    """``("trim"|"slow"|"loop", speed factor)`` for fitting footage into ``duration``."""
    if source_seconds <= 0:
        raise ValueError("footage has no duration")
    if source_seconds >= duration:
        return "trim", 1.0
    stretch = duration / source_seconds
    if stretch <= MAX_SLOWDOWN:
        return "slow", stretch
    return "loop", 1.0


def stock_to_clip(
    video: Path, overlay: Path | None, out: Path, duration: float, source_seconds: float,
) -> tuple[Path, str]:
    """Cover-crop footage to 1920x1080, fit its length, burn the text overlay."""
    mode, stretch = stock_plan(source_seconds, duration)
    pre = ["-stream_loop", "-1"] if mode == "loop" else []
    slow = f",setpts={stretch:.6f}*PTS" if mode == "slow" else ""
    base = f"[0:v]{_COVER}{slow},fps={FPS}[bg]"
    args = ["ffmpeg", "-y", *pre, "-i", str(video)]
    if overlay is not None:
        args += ["-i", str(overlay), "-filter_complex", f"{base};[bg][1:v]overlay=0:0[v]",
                 "-map", "[v]"]
    else:
        args += ["-filter_complex", base, "-map", "[bg]"]
    run([*args, *_out(out, frame_count(duration))])
    return out, mode


def ken_burns(
    image: Path, overlay: Path | None, out: Path, duration: float, *, zoom: float = 0.10,
) -> Path:
    """Slow centred push-in (1.0 → 1+zoom). Upscaled first so zoompan does not jitter."""
    total = frame_count(duration)
    zoompan = (
        f"scale={WIDTH * 2}:{HEIGHT * 2}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='1+{zoom}*on/{total}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total}:s={WIDTH}x{HEIGHT}:fps={FPS},setsar=1"
    )
    args = ["ffmpeg", "-y", "-i", str(image)]
    if overlay is not None:
        args += ["-i", str(overlay), "-filter_complex",
                 f"[0:v]{zoompan}[bg];[bg][1:v]overlay=0:0[v]", "-map", "[v]"]
    else:
        args += ["-vf", zoompan]
    run([*args, *_out(out, total)])
    return out


def artwork_plate(
    image: Path, overlay: Path | None, out: Path, duration: float, *, zoom: float = 0.05,
) -> Path:
    """Whole artwork (never cropped) on a blurred, darkened copy of itself, slow push-in.

    Scrolls and portrait prints would lose heads and inscriptions under the
    cover-crop that :func:`ken_burns` uses, so the work is fitted inside the
    frame above the lower third instead.
    """
    total = frame_count(duration)
    w2, h2 = WIDTH * 2, HEIGHT * 2
    graph = (
        f"[0:v]split=2[a][b];"
        f"[a]scale={w2}:{h2}:force_original_aspect_ratio=increase,crop={w2}:{h2},"
        f"boxblur=40:3,eq=brightness=-0.32:saturation=0.55[bg];"
        f"[b]scale={w2 - 360}:{h2 - 520}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2-140,"
        f"zoompan=z='1+{zoom}*on/{total}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total}:s={WIDTH}x{HEIGHT}:fps={FPS},setsar=1"
    )
    args = ["ffmpeg", "-y", "-i", str(image)]
    if overlay is not None:
        args += ["-i", str(overlay), "-filter_complex", f"{graph}[k];[k][1:v]overlay=0:0[v]",
                 "-map", "[v]"]
    else:
        args += ["-filter_complex", f"{graph}[v]", "-map", "[v]"]
    run([*args, *_out(out, total)])
    return out


def first_frame(clip: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-i", str(clip), "-frames:v", "1", str(out)])
    return out


def frame_at(clip: Path, seconds: float, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-ss", f"{max(seconds, 0):.3f}", "-i", str(clip),
         "-frames:v", "1", str(out)])
    return out


def transition_into(
    clip: Path, next_first_frame: Path, out: Path, duration: float,
    *, style: str, length: float,
) -> Path:
    """Blend the last ``length`` s of ``clip`` into the next clip's first frame.

    The next clip then starts on that very frame, so the cut is seamless and
    every timeline slot keeps its exact length (no overlap to re-time).
    """
    if style not in TRANSITIONS:
        raise ValueError(f"unknown transition {style!r}; choose {sorted(TRANSITIONS)}")
    length = min(length, duration / 2)
    total = frame_count(duration)
    offset = total / FPS - length
    graph = (
        f"[0:v]{_COVER},fps={FPS},format=yuv420p,settb=AVTB[a];"
        f"[1:v]{_COVER},fps={FPS},format=yuv420p,settb=AVTB[b];"
        f"[a][b]xfade=transition={TRANSITIONS[style]}:duration={length:.3f}:offset={offset:.3f}[v]"
    )
    run(["ffmpeg", "-y", "-i", str(clip),
         "-loop", "1", "-framerate", str(FPS), "-t", f"{length + 0.5:.3f}", "-i", str(next_first_frame),
         "-filter_complex", graph, "-map", "[v]", *_out(out, total)])
    return out
