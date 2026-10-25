"""``upload/manual/``: everything needed to upload one run by hand in YouTube Studio.

API uploads from an unaudited Google project are locked to private, so until
the audit passes every video goes up through Studio. The kit:

- ``README.md``     step-by-step list in Studio's field order (:mod:`manual_readme`)
- ``title.txt`` / ``description.txt`` / ``tags.txt``  plain text for pasting
- ``subtitles.srt`` + ``subtitles.vtt``
- ``thumbnail.png`` (or ``.jpg`` when a PNG would pass Studio's 2 MB limit)
- ``preview.html``  offline YouTube-like watch page (:mod:`manual_preview`)

Metadata is ``upload/youtube_meta.json`` only while the final gate's approval
matches the current render (an old file can outlive a re-render); otherwise it
is built the same way in memory and the kit is marked as a preview: nothing in
it means "approved". Merged from three channel branches (REPORT-channels-integrate).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageOps

from content_farm.explainer import ffmpeg_ops
from content_farm.production import publish, shorts_cut, voice_source
from content_farm.production.channels import Channel, Gate
from content_farm.production.qc import QC_REPORT, final_video
from content_farm.production.runner import gate_fingerprint, scheduled_publish_at
from content_farm.production.state import load_state
from content_farm.production.steps import steps_for

KIT_DIR = Path("upload") / "manual"
THUMB_SIZE = (1280, 720)
SHORT_THUMB_SIZE = (1080, 1920)
THUMB_MAX_BYTES = 2 * 1024 * 1024
TITLE_MAX = 100
TAGS_MAX_CHARS = 500
DEFAULT_FRAME_AT = 2.0
CATEGORY_NAMES = {"27": "教育（Education）", "23": "喜劇（Comedy）", "24": "娛樂（Entertainment）"}
PLAYLISTS = {"chipcat": "晶片貓｜台灣科技產業拆解", "offwork": "晶片貓下班了｜一個數字",
             "yokai": "怪談開談", "cel": "賽璐璐研究室"}


@dataclass(frozen=True)
class KitOptions:
    out_dir: Path | None = None          # default: <run-dir>/upload/manual
    machine_voice: bool | None = None    # None: read logs/voice.log
    playlist: str = ""                   # default: PLAYLISTS, then the channel line
    thumbnail_at: float | None = None    # seconds; set → use that video frame as the thumbnail


@dataclass(frozen=True)
class Kit:
    """Everything README and preview need, computed once."""

    directory: Path
    run_dir: Path
    channel: Channel
    meta: dict
    preview: bool                # the final gate has not approved the current render
    voice_provider: str | None
    machine_voice: bool
    is_short: bool               # vertical video: Shorts player and Studio hints
    short_spec: shorts_cut.ShortSpec | None
    video: Path
    video_rel: str               # from the kit directory, for <video src>
    seconds: float
    size_bytes: int
    qc_errors: int | None        # None: QC has not run
    qc_warnings: int | None
    playlist: str
    thumbnail: Path | None = None
    thumbnail_note: str = ""
    variants: tuple[Path, ...] = ()     # thumbnail_A/B/C.jpg for YouTube Studio 「測試與比較」
    subtitles: tuple[shorts_cut.Cue, ...] = ()

    @property
    def category(self) -> str:
        return CATEGORY_NAMES.get(str(self.meta.get("category_id")), str(self.meta.get("category_id")))


def final_approved(run_dir: Path, channel: Channel) -> bool:
    """The final gate is approved for the video as it is now (not an older render)."""
    step = next((s for s in steps_for(channel, run_dir) if s.gate is Gate.FINAL), None)
    if step is None:
        return False
    return load_state(run_dir, channel.code).approved(Gate.FINAL.value, gate_fingerprint(run_dir, step))


def load_or_preview_meta(run_dir: Path, channel: Channel) -> tuple[dict, bool]:
    """(meta, is_preview). Packaged meta only counts once the current render is approved."""
    path = run_dir / publish.META_PATH
    if path.is_file() and final_approved(run_dir, channel):
        return json.loads(path.read_text(encoding="utf-8")), False
    from datetime import datetime

    from content_farm.production.publish_slot import peek

    kind = "short" if channel.format.length == "short" else "long"
    when = scheduled_publish_at(run_dir) or peek(run_dir, channel.code, kind, now=datetime.now().astimezone())
    return publish.build_meta(channel, run_dir, publish_at=when), True


def probe_video(video: Path) -> tuple[float, int, int] | None:
    """(duration, width, height), or None when ffprobe is missing or the file is not a video."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "json", str(video)],
            capture_output=True, text=True, check=True, timeout=60)
        data = json.loads(out.stdout)
        stream = data["streams"][0]
        return float(data["format"]["duration"]), int(stream["width"]), int(stream["height"])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
        return None


def qc_counts(run_dir: Path) -> tuple[int | None, int | None]:
    path = run_dir / QC_REPORT
    if not path.is_file():
        return None, None
    report = json.loads(path.read_text(encoding="utf-8"))
    return int(report.get("errors", 0)), int(report.get("warnings", 0))


_SRT_TIME = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")


def srt_to_vtt(srt: str) -> str:
    return "WEBVTT\n\n" + _SRT_TIME.sub(r"\1.\2", srt.replace("\r\n", "\n").strip()) + "\n"


def _thumbnail_source(kit: Kit, at: float | None) -> tuple[Path | None, str]:
    """(image, note); image None means "grab a frame of the video"."""
    if at is not None:
        return None, f"影片第 {at:.1f} 秒的畫格（--thumbnail-at）"
    own = kit.meta.get("thumbnail_path")
    if own and (kit.run_dir / own).is_file():
        if (kit.run_dir / "thumbnail.json").is_file():
            return kit.run_dir / own, "頻道縮圖產生器（run-dir 的 thumbnail.json → scripts/make_thumbnail.py）"
        return kit.run_dir / own, f"來自 run 的縮圖 `{own}`"
    intro = kit.run_dir / "short" / "intro.png"
    if kit.short_spec is not None and intro.is_file():
        return intro, "Short 片頭頁（品牌色、數字）；Shorts 縮圖要在 YouTube 手機 App 換"
    slide = kit.run_dir / "slides" / "slide_001.png"
    if slide.is_file():
        return slide, "暫用第 1 張標題投影片（已套頻道品牌）；品牌縮圖產生器（R2）還沒做"
    return None, f"沒有縮圖也沒有標題投影片：暫用影片第 {DEFAULT_FRAME_AT:.0f} 秒畫格"


def make_thumbnail(kit: Kit, at: float | None) -> tuple[Path, str]:
    """1280×720 (1080×1920 for Shorts), cover-cropped; PNG → quantized PNG → JPEG to stay < 2 MB."""
    source, note = _thumbnail_source(kit, at)
    for old in kit.directory.glob("thumbnail.*"):
        old.unlink()
    if source is None:
        when = DEFAULT_FRAME_AT if at is None else at
        frame = kit.directory / ".thumb_frame.png"
        ffmpeg_ops.frame_at(kit.video, min(when, kit.seconds / 2) if kit.seconds else when, frame)
        source = frame
    with Image.open(source) as image:
        fitted = ImageOps.fit(image.convert("RGB"), SHORT_THUMB_SIZE if kit.is_short else THUMB_SIZE,
                              Image.LANCZOS)
    (kit.directory / ".thumb_frame.png").unlink(missing_ok=True)
    png = kit.directory / "thumbnail.png"
    fitted.save(png, "PNG", optimize=True)
    if png.stat().st_size > THUMB_MAX_BYTES:
        fitted.quantize(colors=256).save(png, "PNG", optimize=True)
    if png.stat().st_size <= THUMB_MAX_BYTES:
        return png, note
    png.unlink()
    jpg = kit.directory / "thumbnail.jpg"
    fitted.save(jpg, "JPEG", quality=90)
    if jpg.stat().st_size > THUMB_MAX_BYTES:
        raise ValueError(f"{jpg} is {jpg.stat().st_size} bytes even as JPEG (limit 2 MB)")
    return jpg, note


def collect(run_dir: Path, channel: Channel, options: KitOptions) -> Kit:
    meta, preview = load_or_preview_meta(run_dir, channel)
    if len(meta["title"]) > TITLE_MAX:
        raise ValueError(f"title is {len(meta['title'])} chars (YouTube max {TITLE_MAX})")
    video = (run_dir / meta["video_path"]).resolve() if meta.get("video_path") else final_video(run_dir)
    if video is None or not video.is_file():
        raise FileNotFoundError(f"{run_dir}/assembly has no final.mp4 or draft.mp4")
    probed = probe_video(video)
    spec = shorts_cut.load_spec(run_dir) if shorts_cut.is_short_cut(run_dir) else None
    vertical = probed[2] > probed[1] if probed else (spec is not None or channel.format.aspect == "9:16")
    directory = (options.out_dir or run_dir / KIT_DIR).resolve()
    provider = voice_source.last_tts_provider(run_dir)
    if options.machine_voice is not None:  # --voice machine|fish overrides what the log says
        provider = voice_source.MACHINE_PROVIDER if options.machine_voice else "fish_audio"
    errors, warnings = qc_counts(run_dir)
    return Kit(
        directory=directory, run_dir=run_dir, channel=channel, meta=meta, preview=preview,
        voice_provider=provider, machine_voice=provider == voice_source.MACHINE_PROVIDER,
        is_short=vertical, short_spec=spec, video=video,
        video_rel=Path(os.path.relpath(video, directory)).as_posix(),
        seconds=probed[0] if probed else float(meta.get("duration_seconds") or 0.0),
        size_bytes=video.stat().st_size, qc_errors=errors, qc_warnings=warnings,
        playlist=options.playlist or PLAYLISTS.get(channel.code, channel.line))


def write_kit(run_dir: Path, channel: Channel, options: KitOptions | None = None) -> Kit:
    """Write every kit file; returns the Kit (directory, preview/machine-voice flags, …)."""
    from content_farm.production.manual_preview import build_preview_html
    from content_farm.production.manual_readme import build_readme

    options = options or KitOptions()
    kit = collect(run_dir, channel, options)
    out = kit.directory
    out.mkdir(parents=True, exist_ok=True)
    thumbnail, note = make_thumbnail(kit, options.thumbnail_at)
    kit = replace(kit, thumbnail=thumbnail, thumbnail_note=note, variants=copy_variants(run_dir, out))
    _write(out / "title.txt", kit.meta["title"] + "\n")
    _write(out / "description.txt", kit.meta["description"])
    _write(out / "tags.txt", ", ".join(kit.meta.get("tags") or []) + "\n")
    srt = run_dir / "subtitles" / "subtitles.srt"
    if srt.is_file():
        shutil.copyfile(srt, out / "subtitles.srt")
        text = srt.read_text(encoding="utf-8")
        _write(out / "subtitles.vtt", srt_to_vtt(text))
        kit = replace(kit, subtitles=tuple(shorts_cut.parse_cues(text)))
    _write(out / "README.md", build_readme(kit))
    _write(out / "preview.html", build_preview_html(kit))
    return kit


def copy_variants(run_dir: Path, out: Path) -> tuple[Path, ...]:
    """thumbnails/variant_<k>.jpg → <kit>/thumbnail_<K>.jpg (each already < 2 MB)."""
    for old in out.glob("thumbnail_?.jpg"):
        old.unlink()
    copied = []
    for source in sorted((run_dir / "thumbnails").glob("variant_?.jpg")):
        target = out / f"thumbnail_{source.stem[-1].upper()}.jpg"
        shutil.copyfile(source, target)
        copied.append(target)
    return tuple(copied)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def human_size(size: int) -> str:
    return f"{size / 1024 / 1024:.1f} MB"


def human_duration(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}"
