"""``upload/manual/``: everything needed to upload one run by hand in YouTube Studio.

API uploads from an unaudited Google project are locked to private, so until
the audit passes each video goes up through Studio. The kit is generated from
``upload/youtube_meta.json`` (written by ``package`` after the final gate). If
the final gate is not approved yet, the same metadata is built as a preview
and the README says so: nothing in the kit means "approved".
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from content_farm.production import publish, shorts_cut
from content_farm.production.channels import Channel
from content_farm.production.runner import scheduled_publish_at

KIT_DIR = Path("upload") / "manual"
THUMB_SIZE = (1280, 720)
THUMB_MAX_BYTES = 2 * 1024 * 1024
TITLE_MAX = 100
CATEGORY_NAMES = {"27": "教育（Education）", "23": "喜劇（Comedy）"}
PLAYLISTS = {"chipcat": "晶片貓｜台灣科技產業拆解", "offwork": "晶片貓下班了｜一個數字",
             "yokai": "妖怪溯源所", "cel": "賽璐璐研究室"}
MACHINE_VOICE_BANNER = "> ⚠️ **暫用機器聲（macOS say），待換 Fish Audio 後重出。** 這一版不要公開。"


@dataclass(frozen=True)
class Kit:
    directory: Path
    preview: bool          # built without an approved final gate
    machine_voice: bool
    is_short: bool


def load_or_preview_meta(run_dir: Path, channel: Channel) -> tuple[dict, bool]:
    path = run_dir / publish.META_PATH
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8")), False
    return publish.build_meta(channel, run_dir, publish_at=scheduled_publish_at(run_dir)), True


_TTS_LINE = re.compile(r"content_farm\.voice\.(?!generator\b)(\w+) INFO .*TTS", re.IGNORECASE)


def uses_machine_voice(run_dir: Path) -> bool:
    """The audio was last synthesized by macOS ``say`` (for a Short: the long run it was cut from).

    Looks at the last provider that actually synthesized, not the last run: a re-run that only
    logs "Reusing existing audio" keeps whatever voice was there before.
    """
    source = Path(shorts_cut.load_spec(run_dir).long_run_dir) if shorts_cut.is_short_cut(run_dir) else run_dir
    log = source / "logs" / "voice.log"
    if not log.is_file():
        return False
    providers = _TTS_LINE.findall(log.read_text(encoding="utf-8", errors="replace"))
    return bool(providers) and providers[-1] == "macos_say"


def _ffmpeg_still(source: Path, out: Path, *, at: float | None = None, size: tuple[int, int] = THUMB_SIZE) -> Path:
    width, height = size
    seek = ["-ss", f"{at:.2f}"] if at is not None else []
    scale = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *seek, "-i", str(source), "-frames:v", "1", "-vf", scale,
                    str(out)], check=True, capture_output=True, timeout=120)
    return out


def make_thumbnail(run_dir: Path, out: Path, is_short: bool) -> tuple[Path, str]:
    """Stop-gap until the branded thumbnail generator (roadmap R2) exists."""
    if is_short:
        intro = run_dir / "short" / "intro.png"
        _ffmpeg_still(intro, out, size=(1080, 1920))
        note = "Short 片頭頁（品牌色、數字），1080×1920；Shorts 縮圖要在 YouTube 手機 App 換"
    else:
        _ffmpeg_still(run_dir / "slides" / "slide_001.png", out)
        note = "暫用標題頁投影片（slides/slide_001.png）縮成 1280×720；品牌縮圖產生器（R2）還沒做"
    if out.stat().st_size > THUMB_MAX_BYTES:
        raise ValueError(f"{out} is {out.stat().st_size} bytes (> 2 MB)")
    return out, note


def srt_to_vtt(srt_text: str) -> str:
    cues = shorts_cut.parse_cues(srt_text)
    blocks = [f"{shorts_cut._stamp(c.start).replace(',', '.')} --> {shorts_cut._stamp(c.end).replace(',', '.')}\n"
              f"{c.text}\n" for c in cues]
    return "WEBVTT\n\n" + "\n".join(blocks)


def synthetic_advice(meta: dict) -> str:
    if not meta.get("contains_synthetic_media"):
        return "選「否」（頻道設定 ai_disclosure: false）。"
    return ("頻道設定要求揭露（ai_disclosure: true），建議選「是」。理由：旁白是合成語音。"
            "嚴格說 YouTube 只要求「看起來像真實」的變造內容（真人說沒說過的話、真實事件、寫實場景）揭露，"
            "本片是明顯的解說投影片＋卡通角色，不勾也不違規；要不要勾由 Leon 決定（見報告）。")


def _video_facts(run_dir: Path, meta: dict) -> tuple[Path, float, int]:
    video = (run_dir / meta["video_path"]).resolve()
    seconds = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        check=True, capture_output=True, text=True, timeout=60).stdout.strip())
    return video, seconds, video.stat().st_size


def _qc_counts(run_dir: Path) -> tuple[int | None, int | None]:
    path = run_dir / "qc" / "qc_report.json"
    if not path.is_file():
        return None, None
    report = json.loads(path.read_text(encoding="utf-8"))
    return report["errors"], report["warnings"]


def readme_text(meta: dict, channel: Channel, facts: tuple[Path, float, int], kit: Kit, thumb_note: str) -> str:
    video, seconds, size = facts
    visibility = (f"排程：{meta['publish_at']}（先選「私人」再設排程）" if meta.get("publish_at")
                  else "私人（Leon 看過成片再改）")
    lines = [
        *( [MACHINE_VOICE_BANNER, ""] if kit.machine_voice else [] ),
        *( ["> ⚠️ **成片閘門尚未核可**：以下是預覽資料，Leon `produce.py approve --gate final` 之後重跑 "
            "`produce.py manual-kit` 才是正式版。", ""] if kit.preview else [] ),
        f"# 手動上傳：{meta['title']}",
        "",
        f"- 目標頻道：**{channel.name}**（`{channel.code}`）{'— Shorts（直式 ≤60 秒，Studio 會自動判定）' if kit.is_short else ''}",
        f"- 影片檔：`{video}`",
        f"- 片長 {seconds:.1f} 秒，檔案 {size / 1_048_576:.1f} MB",
        "- 本機預覽：`preview.html`（同資料夾）",
        "",
        "## YouTube Studio 步驟",
        "",
        "1. 右上「建立」→「上傳影片」→ 選上面的影片檔。",
        "2. **詳細資訊**",
        f"   - 標題：貼 `title.txt`（{len(meta['title'])}/{TITLE_MAX} 字）",
        "   - 說明：貼 `description.txt`（章節、參考資料、素材授權、AI 揭露都在裡面）",
        f"   - 縮圖：上傳 `thumbnail.png`（{thumb_note}）",
        f"   - 播放清單：{PLAYLISTS.get(channel.code, '（無）')}",
        "   - 觀眾：**否，這不是為兒童打造的內容**",
        f"   - 「變造或合成內容」：{synthetic_advice(meta)}",
        "   - 展開「顯示更多」：",
        "     - 標籤：貼 `tags.txt`",
        "     - 影片語言：中文（台灣）；字幕認證：無",
        f"     - 類別：{CATEGORY_NAMES.get(str(meta.get('category_id')), meta.get('category_id'))}",
        "3. **影片元素**",
        "   - 字幕：新增 →「上傳檔案」→「含時間碼」→ `subtitles.srt`，語言 中文（台灣）",
        *( ["   - Shorts 沒有片尾畫面／資訊卡；改在「相關影片」連到晶片貓的 CoWoS 長片（長片上線後再設）"]
           if kit.is_short else
           ["   - 片尾畫面：最後 20 秒放「訂閱」＋「最新上傳影片」（本片最後一頁是結論，不會被擋到重點）",
            "   - 資訊卡：在「台灣的位置」章節放晶片貓頻道的下一支長片（還沒有就先不放）"] ),
        "4. **檢查**：等版權檢查跑完、沒有問題再按下一步。",
        f"5. **瀏覽權限**：{visibility}",
        "",
        f"說明欄裡的章節：{len(meta.get('chapters') or [])} 個；AI 揭露旗標 `contains_synthetic_media={meta.get('contains_synthetic_media')}`。",
    ]
    return "\n".join(lines) + "\n"


_STAMP_LINE = re.compile(r"^(\d{1,2}(?::\d{2}){1,2})(?= )", re.MULTILINE)


def stamp_seconds(stamp: str) -> int:
    seconds = 0
    for part in stamp.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def description_html(description: str) -> str:
    """Escaped description; line-leading chapter timestamps become seek links (as on YouTube)."""
    escaped = html.escape(description)
    return _STAMP_LINE.sub(lambda m: f'<a data-t="{stamp_seconds(m.group(1))}">{m.group(1)}</a>', escaped)


def preview_html(meta: dict, channel: Channel, facts: tuple[Path, float, int], kit: Kit, vtt: str,
                 qc_counts: tuple[int | None, int | None], run_dir: Path) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    from content_farm.explainer.brands import brand_palette

    video, seconds, size = facts
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                      autoescape=select_autoescape(["html", "j2"]))
    chapters = [{**ch, "seconds": stamp_seconds(ch["timestamp"])} for ch in meta.get("chapters") or []]
    return env.get_template("preview.html.j2").render(
        meta={**meta, "chapters": chapters}, channel_name=channel.name, is_short=kit.is_short,
        machine_voice=kit.machine_voice, preview=kit.preview, seconds=seconds, size_mb=size / 1_048_576,
        qc_errors=qc_counts[0], qc_warnings=qc_counts[1],
        video_src=Path(os.path.relpath(video, run_dir / KIT_DIR)).as_posix(),
        description_html=description_html(meta["description"]),
        category=CATEGORY_NAMES.get(str(meta.get("category_id")), meta.get("category_id")),
        brand_color=brand_palette(channel.brand).get("accent", "#cc0000"),
        vtt=vtt.replace("</", "<\\/"),
    )


def write_kit(run_dir: Path, channel: Channel) -> Kit:
    meta, preview = load_or_preview_meta(run_dir, channel)
    if len(meta["title"]) > TITLE_MAX:
        raise ValueError(f"title is {len(meta['title'])} chars (YouTube max {TITLE_MAX})")
    kit = Kit(run_dir / KIT_DIR, preview, uses_machine_voice(run_dir), shorts_cut.is_short_cut(run_dir))
    out = kit.directory
    out.mkdir(parents=True, exist_ok=True)
    (out / "title.txt").write_text(meta["title"] + "\n", encoding="utf-8")
    (out / "description.txt").write_text(meta["description"], encoding="utf-8")
    (out / "tags.txt").write_text(",".join(meta.get("tags") or []) + "\n", encoding="utf-8")
    srt = run_dir / "subtitles" / "subtitles.srt"
    shutil.copy2(srt, out / "subtitles.srt")
    vtt = srt_to_vtt(srt.read_text(encoding="utf-8"))
    (out / "subtitles.vtt").write_text(vtt, encoding="utf-8")
    _, thumb_note = make_thumbnail(run_dir, out / "thumbnail.png", kit.is_short)
    facts = _video_facts(run_dir, meta)
    (out / "README.md").write_text(readme_text(meta, channel, facts, kit, thumb_note), encoding="utf-8")
    (out / "preview.html").write_text(
        preview_html(meta, channel, facts, kit, vtt, _qc_counts(run_dir), run_dir), encoding="utf-8")
    return kit
