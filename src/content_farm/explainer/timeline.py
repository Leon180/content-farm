"""Place rendered slides on the assembly timeline (``visual/MM:SS.mmm~MM:SS.mmm.png``).

Boundaries come from the *cumulative* measured duration, rounded once per
boundary, so slide N's end and slide N+1's start are the same string. Summing
per-slide rounded durations would drift by up to 0.5 ms per slide and
``assemble_from_timeline`` fills any gap > 50 ms with black frames.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from content_farm.assembly.timeline_assembly import scan_timeline_clips
from content_farm.script_gen.schemas import Script
from content_farm.voice.schemas import VoiceArtifact

MAX_TIMELINE_MS = 100 * 60 * 1000  # MM is two digits in the assembly filename regex


class TimelineError(ValueError):
    """Durations or files cannot be turned into a valid slide timeline."""


@dataclass(frozen=True)
class SlideClip:
    index: int  # 1-based, matches scene_number and slide_NNN.png
    start_ms: int
    end_ms: int

    @property
    def filename(self) -> str:
        return f"{format_timestamp(self.start_ms)}~{format_timestamp(self.end_ms)}.png"


def format_timestamp(ms: int) -> str:
    if not 0 <= ms < MAX_TIMELINE_MS:
        raise TimelineError(f"timestamp {ms} ms outside 00:00.000-99:59.999")
    minutes, rest = divmod(ms, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def plan_slide_timeline(durations: Sequence[float]) -> tuple[SlideClip, ...]:
    """Contiguous clips for per-slide durations (seconds)."""
    if not durations:
        raise TimelineError("no durations")
    bad = [i for i, d in enumerate(durations, start=1) if not (d > 0 and math.isfinite(d))]
    if bad:
        raise TimelineError(f"non-positive duration for slide(s) {bad}")
    boundaries = [round(math.fsum(durations[:i]) * 1000) for i in range(len(durations) + 1)]
    clips = tuple(
        SlideClip(index=i, start_ms=boundaries[i - 1], end_ms=boundaries[i])
        for i in range(1, len(durations) + 1)
    )
    format_timestamp(clips[-1].end_ms)  # fail early if the video is too long
    return clips


def probe_duration(path: Path) -> float:
    """Exact container duration via ffprobe (raises TimelineError on failure)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, check=True, text=True, timeout=30,
        )
        return float(json.loads(result.stdout)["format"]["duration"])
    except (OSError, subprocess.SubprocessError, KeyError, ValueError) as exc:
        raise TimelineError(f"ffprobe failed for {path}: {exc}") from exc


def durations_from_audio(
    audio_dir: Path, count: int, probe: Callable[[Path], float] = probe_duration,
) -> list[float]:
    """Measured length of ``scene_001.mp3`` … — the same files concatenated into full.mp3."""
    paths = [audio_dir / f"scene_{i:03d}.mp3" for i in range(1, count + 1)]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        raise TimelineError(f"missing audio in {audio_dir}: {missing}")
    return [probe(p) for p in paths]


def durations_from_voice_artifact(path: Path, count: int) -> list[float]:
    """Fallback: voice_artifact.json durations (rounded to 10 ms by voice)."""
    artifact = VoiceArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    by_scene = {s.scene_number: s.duration_seconds for s in artifact.segments}
    missing = [i for i in range(1, count + 1) if i not in by_scene]
    if missing:
        raise TimelineError(f"{path.name} has no segment for scene(s) {missing}")
    return [by_scene[i] for i in range(1, count + 1)]


def durations_from_script(script: Script) -> list[float]:
    """Pre-voice estimates — preview only, never for a real assembly."""
    return [s.duration_seconds for s in sorted(script.scenes, key=lambda s: s.scene_number)]


def place_slides(
    clips: Sequence[SlideClip],
    slides_dir: Path,
    visual_dir: Path,
    *,
    replace: bool = False,
) -> list[Path]:
    """Copy ``slides/slide_NNN.png`` to ``visual/<timeline name>.png``.

    Refuses to mix with timeline files already in ``visual/`` (assembly would
    pick both up) unless ``replace`` is set, in which case only those
    timeline-named files are removed.
    """
    sources = [slides_dir / f"slide_{c.index:03d}.png" for c in clips]
    missing = [p.name for p in sources if not p.is_file()]
    if missing:
        raise TimelineError(f"missing rendered slides in {slides_dir}: {missing}")

    visual_dir.mkdir(parents=True, exist_ok=True)
    existing = scan_timeline_clips(visual_dir)
    if existing and not replace:
        raise TimelineError(
            f"{visual_dir} already has {len(existing)} timeline file(s); pass --replace"
        )
    for clip in existing:
        clip.path.unlink()

    placed: list[Path] = []
    for clip, source in zip(clips, sources):
        target = visual_dir / clip.filename
        shutil.copy2(source, target)
        placed.append(target)
    return placed
