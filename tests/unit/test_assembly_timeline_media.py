"""assembly_timeline with v2 media: mp4 clips next to PNG stills; PNG-only and Shorts unchanged."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from content_farm.assembly import timeline_assembly
from content_farm.assembly.timeline_assembly import TimelineClip, assemble_from_timeline
from content_farm.types import Orientation

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def _capture_normalize(clip: TimelineClip, **kwargs: object) -> list[str]:
    calls: list[list[str]] = []

    async def fake_run(args: list[str]) -> None:
        calls.append(args)

    with patch.object(timeline_assembly, "_run", fake_run):
        asyncio.run(timeline_assembly._normalize_clip(  # noqa: SLF001
            clip, Path("/tmp/out.mp4"), ffmpeg_path="ffmpeg", ffprobe_path="ffprobe",
            width=kwargs.get("width", 1080), height=kwargs.get("height", 1920), fps=30,
        ))
    [args] = calls
    return args


def test_png_still_args_unchanged() -> None:
    """Pin the v1 still-image command so v2 media work cannot drift it."""
    clip = TimelineClip(path=Path("/v/00:00.000~00:02.500.png"), start_seconds=0, end_seconds=2.5)
    assert _capture_normalize(clip) == [
        "ffmpeg", "-y", "-loop", "1", "-i", "file:/v/00:00.000~00:02.500.png", "-t", "2.50",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "/tmp/out.mp4",
    ]


def test_mp4_clip_args_unchanged() -> None:
    clip = TimelineClip(path=Path("/v/00:02.500~00:04.000.mp4"), start_seconds=2.5, end_seconds=4.0)
    args = _capture_normalize(clip, width=1920, height=1080)
    assert args[:6] == ["ffmpeg", "-y", "-i", "file:/v/00:02.500~00:04.000.mp4", "-t", "1.50"]
    assert "-an" in args and "-loop" not in args
    assert "scale=1920:1080" in args[args.index("-vf") + 1]


def test_shorts_default_is_still_portrait(tmp_path: Path) -> None:
    visual = tmp_path / "visual"
    visual.mkdir()
    Image.new("RGB", (8, 8)).save(visual / "00:00~00:01.png")
    seen: list[list[str]] = []

    async def fake_run(args: list[str]) -> None:
        seen.append(args)
        Path(args[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(args[-1]).write_bytes(b"")

    with patch.object(timeline_assembly, "_run", fake_run):
        asyncio.run(assemble_from_timeline(
            visual_dir=visual, audio_path=tmp_path / "a.mp3", subtitle_path=None,
            output_dir=tmp_path / "assembly",
        ))
    assert "scale=1080:1920" in seen[0][seen[0].index("-vf") + 1]


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, capture_output=True)


@needs_ffmpeg
def test_mixed_png_and_mp4_assemble_without_gaps(tmp_path: Path) -> None:
    visual = tmp_path / "visual"
    visual.mkdir()
    Image.new("RGB", (640, 360), "#2060c0").save(visual / "00:00.000~00:01.000.png")
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=1.5", "-pix_fmt", "yuv420p",
            str(visual / "00:01.000~00:02.500.mp4"))
    Image.new("RGB", (640, 360), "#c06020").save(visual / "00:02.500~00:03.000.png")
    audio = tmp_path / "full.mp3"
    _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "3", str(audio))

    draft = asyncio.run(assemble_from_timeline(
        visual_dir=visual, audio_path=audio, subtitle_path=None, output_dir=tmp_path / "out",
        orientation=Orientation.LANDSCAPE, width=640, height=360,
    ))
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
         "-of", "csv=p=0", str(draft)], capture_output=True, text=True, check=True,
    )
    assert float(probe.stdout) == pytest.approx(3.0, abs=0.1)
    black = subprocess.run(
        ["ffmpeg", "-i", str(draft), "-vf", "blackdetect=d=0.05:pix_th=0.10", "-an", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    assert "black_start" not in black.stderr
    assert not list((tmp_path / "out" / "_tmp").glob("black_*.mp4"))  # no gap filler needed


def test_normalized_clips_are_reused_per_scene(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    visual = tmp_path / "visual"
    visual.mkdir()
    Image.new("RGB", (640, 360), "#2060c0").save(visual / "00:00.000~00:01.000.png")
    Image.new("RGB", (640, 360), "#c06020").save(visual / "00:01.000~00:02.000.png")
    audio = tmp_path / "full.mp3"
    _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2", str(audio))

    def assemble() -> Path:
        return asyncio.run(assemble_from_timeline(
            visual_dir=visual, audio_path=audio, subtitle_path=None, output_dir=tmp_path / "out",
            orientation=Orientation.LANDSCAPE, width=640, height=360))

    caplog.set_level("INFO", logger="content_farm.assembly.timeline_assembly")
    first = assemble().read_bytes()
    Image.new("RGB", (640, 360), "#20c060").save(visual / "00:01.000~00:02.000.png")   # scene 2 changed
    second = assemble()
    assert "Normalized 2 clip(s), reused 0" in caplog.text
    assert "Normalized 1 clip(s), reused 1" in caplog.text
    assert second.read_bytes() != first
    assert len(list((tmp_path / "out" / "norm_cache").iterdir())) == 2   # the stale entry was pruned
