"""Manual-upload kit: ``upload/manual/`` for pasting into YouTube Studio by hand.

API uploads from an unaudited Google project are locked to private, so until the
audit passes every video is uploaded through YouTube Studio. This module turns a
finished run into the files that make that a copy-paste job:

- ``README.md``     step-by-step list in Studio's upload order, every field's value
- ``title.txt`` / ``description.txt`` / ``tags.txt``  plain text for copying
- ``subtitles.srt`` + ``subtitles.vtt``  whisper captions (vtt for the preview)
- ``thumbnail.png`` 1280×720, < 2 MB (the run's thumbnail, else the title slide)
- ``preview.html``  offline YouTube-like watch page (see :mod:`manual_preview`)

Metadata comes from ``upload/youtube_meta.json`` when the package step has run;
before the final gate is approved it is built in memory with the same function,
and the README says so.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image

from content_farm.production import publish
from content_farm.production.channels import Channel
from content_farm.production.qc import QC_REPORT, final_video

KIT_DIR = Path("upload") / "manual"
THUMB_SIZE = (1280, 720)
THUMB_MAX_BYTES = 2 * 1024 * 1024
TITLE_MAX = 100
TAGS_MAX_CHARS = 500
MACHINE_VOICE_MARK = "content_farm.voice.macos_say"
CATEGORY_NAMES = {"27": "教育", "23": "喜劇"}


@dataclass(frozen=True)
class KitInfo:
    """Everything the README and the preview page need, computed once."""

    channel_code: str
    channel_name: str
    channel_line: str
    vertical: bool
    meta: dict
    meta_from_package: bool
    video_abs: Path
    video_rel: str              # from KIT_DIR, for <video src>
    duration_seconds: float
    size_bytes: int
    machine_voice: bool
    qc_errors: int | None       # None = QC has not run
    qc_warnings: int | None
    thumbnail_note: str


def load_meta(channel: Channel, run_dir: Path) -> tuple[dict, bool]:
    """(meta, True) from the package step, or (meta, False) built in memory."""
    path = run_dir / publish.META_PATH
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8")), True
    return publish.build_meta(channel, run_dir, publish_at=None), False


def detect_machine_voice(run_dir: Path) -> bool:
    log = run_dir / "logs" / "voice.log"
    return log.is_file() and MACHINE_VOICE_MARK in log.read_text(encoding="utf-8", errors="replace")


def qc_counts(run_dir: Path) -> tuple[int | None, int | None]:
    path = run_dir / QC_REPORT
    if not path.is_file():
        return None, None
    report = json.loads(path.read_text(encoding="utf-8"))
    return int(report.get("errors", 0)), int(report.get("warnings", 0))


def probe_duration(video: Path) -> float | None:
    """Container duration via ffprobe; None when ffprobe is missing or the file is not a video."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, check=True, timeout=60)
        return float(out.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


_SRT_TIME = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")


def srt_to_vtt(srt: str) -> str:
    body = _SRT_TIME.sub(r"\1.\2", srt.replace("\r\n", "\n").strip())
    return "WEBVTT\n\n" + body + "\n"


def make_thumbnail(run_dir: Path, meta: dict, dest: Path) -> str:
    """Write a 1280×720 PNG under 2 MB; returns a note on where it came from."""
    own = meta.get("thumbnail_path")
    if own and (run_dir / own).is_file():
        source, note = run_dir / own, f"來自 run 的縮圖 `{own}`"
    else:
        source = run_dir / "slides" / "slide_001.png"
        if not source.is_file():
            raise FileNotFoundError(f"no thumbnail and no title slide at {source}")
        note = "尚無縮圖產生器：暫用第 1 張標題投影片（已套頻道品牌）縮成 1280×720，建議之後換正式縮圖"
    with Image.open(source) as image:
        fitted = image.convert("RGB").resize(THUMB_SIZE, Image.LANCZOS)
    fitted.save(dest, "PNG", optimize=True)
    if dest.stat().st_size > THUMB_MAX_BYTES:
        fitted.quantize(colors=256).save(dest, "PNG", optimize=True)
    if dest.stat().st_size > THUMB_MAX_BYTES:
        raise ValueError(f"{dest} is {dest.stat().st_size} bytes even after quantizing (limit 2 MB)")
    return note


def collect_info(channel: Channel, run_dir: Path, *, machine_voice: bool | None = None) -> KitInfo:
    meta, from_package = load_meta(channel, run_dir)
    video = final_video(run_dir)
    if video is None:
        raise FileNotFoundError(f"{run_dir}/assembly has no final.mp4 or draft.mp4")
    errors, warnings = qc_counts(run_dir)
    kit_dir = (run_dir / KIT_DIR).resolve()
    return KitInfo(
        channel_code=channel.code, channel_name=channel.name, channel_line=channel.line,
        vertical=channel.format.aspect == "9:16",
        meta=meta, meta_from_package=from_package,
        video_abs=video.resolve(),
        video_rel=Path(_relpath(video.resolve(), kit_dir)).as_posix(),
        duration_seconds=probe_duration(video) or float(meta.get("duration_seconds") or 0.0),
        size_bytes=video.stat().st_size,
        machine_voice=detect_machine_voice(run_dir) if machine_voice is None else machine_voice,
        qc_errors=errors, qc_warnings=warnings, thumbnail_note="")


def _relpath(target: Path, start: Path) -> str:
    return os.path.relpath(target, start)


def write_kit(channel: Channel, run_dir: Path, *, machine_voice: bool | None = None) -> list[Path]:
    """Write every kit file; returns the paths written."""
    from content_farm.production.manual_preview import build_preview_html
    from content_farm.production.manual_readme import build_readme

    info = collect_info(channel, run_dir, machine_voice=machine_voice)
    kit = run_dir / KIT_DIR
    kit.mkdir(parents=True, exist_ok=True)
    thumb = kit / "thumbnail.png"
    info = _with_note(info, make_thumbnail(run_dir, info.meta, thumb))
    written = [thumb]
    written += _write_text(kit, {
        "title.txt": info.meta["title"] + "\n",
        "description.txt": info.meta["description"],
        "tags.txt": ", ".join(info.meta.get("tags") or []) + "\n",
    })
    srt = run_dir / (info.meta.get("subtitle_path") or "subtitles/subtitles.srt")
    if srt.is_file():
        shutil.copyfile(srt, kit / "subtitles.srt")
        written.append(kit / "subtitles.srt")
        written += _write_text(kit, {"subtitles.vtt": srt_to_vtt(srt.read_text(encoding="utf-8"))})
    has_subs = srt.is_file()
    written += _write_text(kit, {
        "README.md": build_readme(info, kit.resolve(), has_subs),
        "preview.html": build_preview_html(info, channel.brand, has_subs),
    })
    return written


def _with_note(info: KitInfo, note: str) -> KitInfo:
    return replace(info, thumbnail_note=note)


def _write_text(kit: Path, files: dict[str, str]) -> list[Path]:
    paths = []
    for name, text in files.items():
        path = kit / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def human_size(size: int) -> str:
    return f"{size / 1024 / 1024:.1f} MB"


def human_duration(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}"
