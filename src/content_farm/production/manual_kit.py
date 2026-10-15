"""``upload/manual/``: everything needed to upload one video by hand in YouTube Studio.

API uploads from an unaudited Google project are locked to private, so until
the audit passes each video goes up through Studio. This kit turns
``youtube_meta.json`` (or the same dict built on the fly) into paste-ready
files, a step-by-step README in Studio's field order, a 1280x720 thumbnail
and an offline ``preview.html`` (see :mod:`content_farm.production.preview`).
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from content_farm.explainer import ffmpeg_ops
from content_farm.production.channels import Channel
from content_farm.production.preview import preview_html, srt_to_vtt

MANUAL_DIR = Path("upload") / "manual"
THUMB_SIZE = (1280, 720)
THUMB_MAX_BYTES = 2 * 1024 * 1024
CATEGORY_NAMES = {"27": "教育", "23": "喜劇", "24": "娛樂"}
MACHINE_VOICE_BANNER = "> ⚠ 暫用機器聲（macos_say），待換 Fish Audio 後重出；這一版只供審片，不要公開。"


@dataclass(frozen=True)
class KitOptions:
    machine_voice: bool
    playlist: str = ""
    thumbnail_at: float = 2.0       # seconds into the video for the thumbnail frame
    gate_final_approved: bool = False


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    seconds: float
    size_bytes: int

    @property
    def size_text(self) -> str:
        return f"{self.size_bytes / 1024 / 1024:.1f} MB"

    @property
    def length_text(self) -> str:
        minutes, seconds = divmod(round(self.seconds), 60)
        return f"{minutes}:{seconds:02d}"


def voice_is_machine(run_dir: Path) -> bool:
    """True when the voice step's log shows the macOS ``say`` stand-in was used."""
    log = run_dir / "logs" / "voice.log"
    return log.is_file() and "content_farm.voice.macos_say" in log.read_text(encoding="utf-8")


def video_info(run_dir: Path, meta: dict) -> VideoInfo:
    path = (run_dir / meta["video_path"]).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"video {path} missing")
    return VideoInfo(path, ffmpeg_ops.probe(path)["duration"], path.stat().st_size)


def make_thumbnail(video: Path, out_dir: Path, at: float) -> Path:
    """Frame of the video at ``at`` s, 1280x720; JPEG when PNG would exceed Studio's 2 MB."""
    frame = ffmpeg_ops.frame_at(video, at, out_dir / ".thumb_frame.png")
    image = Image.open(frame).convert("RGB").resize(THUMB_SIZE, Image.LANCZOS)
    frame.unlink()
    png = out_dir / "thumbnail.png"
    image.save(png, optimize=True)
    if png.stat().st_size < THUMB_MAX_BYTES:
        return png
    png.unlink()
    jpg = out_dir / "thumbnail.jpg"
    image.save(jpg, quality=90)
    return jpg


def _synthetic_answer(meta: dict) -> str:
    if meta.get("contains_synthetic_media"):
        return ("**是**。頻道設定 `ai_disclosure: true`；旁白為合成語音。"
                "畫面沒有擬真的合成人物或事件，若 Leon 判斷合成旁白不需標示，可改選「否」"
                "（說明欄的 AI 揭露文字仍保留）。")
    return "**否**。沒有合成語音或擬真合成畫面。"


def readme_text(channel: Channel, meta: dict, video: VideoInfo, thumbnail: Path,
                options: KitOptions) -> str:
    when = meta.get("publish_at")
    visibility = f"私人＋排程 {when}" if when else "私人"
    gate = "已核可" if options.gate_final_approved else "**尚未核可**（等 Leon 在 gate_final 審片）"
    lines = [
        *([MACHINE_VOICE_BANNER, ""] if options.machine_voice else []),
        f"# 手動上傳：{meta['title']}",
        "",
        f"- 目標頻道：**{channel.name}**（`{channel.code}`）— 先在 YouTube Studio 右上角切換到這個頻道",
        f"- 影片檔：`{video.path}`（{video.length_text}，{video.size_text}）",
        f"- 成片閘門：{gate}",
        "- 預覽：先用瀏覽器開 `preview.html` 看一次（字幕、章節、說明欄）",
        "",
        "## Studio 上傳步驟（照畫面順序）",
        "",
        "1. 建立 → 上傳影片 → 選上面的影片檔",
        "2. **詳細資訊**",
        "   - 標題：貼 `title.txt`",
        "   - 說明：貼 `description.txt`（章節、參考資料、畫作授權、AI 揭露都已在裡面）",
        f"   - 縮圖：上傳 `{thumbnail.name}`（1280×720，<2MB）",
        f"   - 播放清單：{options.playlist or '（未指定）'}",
        "   - 目標觀眾：**否，這不是為兒童打造的內容**",
        "3. **顯示更多**",
        f"   - 變造或合成內容：{_synthetic_answer(meta)}",
        "   - 標籤：貼 `tags.txt`",
        "   - 影片語言：中文（台灣）；字幕認證：無",
        f"   - 類別：{CATEGORY_NAMES.get(str(meta.get('category_id')), meta.get('category_id'))}",
        "   - 授權：標準 YouTube 授權；允許嵌入",
        "4. **字幕**：新增語言 中文（台灣）→ 上傳檔案（含時間）→ `subtitles.srt`",
        "5. **影片元素**",
        "   - 片尾畫面：最後 20 秒放「訂閱」＋「最新上傳的影片」（片尾目前是下集預告標題卡）",
        "   - 資訊卡：同頻道還沒有其他影片前先不加",
        "6. **檢查**：等版權檢查跑完，有聲明就停下回報",
        f"7. **瀏覽權限**：{visibility}（先私人，審完再改）",
        "",
    ]
    return "\n".join(lines)


def build_kit(channel: Channel, run_dir: Path, meta: dict, options: KitOptions) -> Path:
    out = run_dir / MANUAL_DIR
    out.mkdir(parents=True, exist_ok=True)
    video = video_info(run_dir, meta)
    (out / "title.txt").write_text(meta["title"][:100] + "\n", encoding="utf-8")
    (out / "description.txt").write_text(meta["description"], encoding="utf-8")
    (out / "tags.txt").write_text(",".join(meta.get("tags", [])) + "\n", encoding="utf-8")
    srt = run_dir / "subtitles" / "subtitles.srt"
    shutil.copy2(srt, out / "subtitles.srt")
    vtt = srt_to_vtt(srt.read_text(encoding="utf-8"))
    (out / "subtitles.vtt").write_text(vtt, encoding="utf-8")
    for old in out.glob("thumbnail.*"):
        old.unlink()
    thumbnail = make_thumbnail(video.path, out, min(options.thumbnail_at, video.seconds / 2))
    (out / "README.md").write_text(readme_text(channel, meta, video, thumbnail, options), encoding="utf-8")
    qc_path = run_dir / "qc" / "qc_report.json"
    qc = json.loads(qc_path.read_text(encoding="utf-8")) if qc_path.is_file() else None
    page = preview_html(channel, meta, video_src=_relative(video.path, out), thumbnail=thumbnail.name,
                        vtt=vtt, qc=qc, machine_voice=options.machine_voice,
                        length_text=video.length_text, size_text=video.size_text)
    (out / "preview.html").write_text(page, encoding="utf-8")
    return out


def _relative(path: Path, start: Path) -> str:
    return Path(os.path.relpath(path, start.resolve())).as_posix()
