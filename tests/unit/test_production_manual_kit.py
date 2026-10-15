"""manual-kit: Studio upload checklist, plain-text fields, thumbnail, captions, offline preview page.

One implementation, merged from the chipcat, yokai and cel branches; every test
of the three is kept here (origin in each docstring), duplicates folded together.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from content_farm.explainer.deck import load_deck
from content_farm.explainer.ffmpeg_ops import FFmpegError
from content_farm.explainer.to_script import deck_to_script
from content_farm.production import manual_kit as mk
from content_farm.production import publish, shorts_cut, voice_source
from content_farm.production.channels import Gate, load_channel
from content_farm.production.manual_preview import description_html
from content_farm.production.manual_readme import MACHINE_VOICE_BANNER, synthetic_advice
from content_farm.production.runner import decide

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

SAY = "2026-10-15 17:59:58,398 content_farm.voice.macos_say INFO macOS say TTS: 231174 bytes -> a.mp3\n"
REUSE = "2026-10-15 23:14:16,953 content_farm.voice.generator INFO Reusing existing audio: a.mp3\n"
FISH = "2026-10-16 09:00:00,000 content_farm.voice.fish_audio INFO Fish Audio TTS: 1 bytes -> a.mp3\n"
SRT = ("1\n00:00:00,000 --> 00:00:01,500\n九尾狐</script>不是\n\n"
       "2\n00:00:01,500 --> 00:00:03,000\n句子</b>\n")


def _video(path: Path, size: str = "320x180", seconds: int = 3) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc=s={size}:d={seconds}:r=30",
                    "-f", "lavfi", "-i", f"sine=d={seconds}", "-shortest", "-pix_fmt", "yuv420p", str(path)],
                   check=True)


def _run(tmp_path: Path, *, video: str = "real", slide: bool = True, title: str | None = None,
         qc: dict | None = None) -> Path:
    """A finished run: ``video`` is "real" (320×180 final.mp4), "portrait", "fake" (draft.mp4 bytes) or "none"."""
    run = tmp_path / "run"
    for sub in ("assembly", "slides", "subtitles", "logs", "qc"):
        (run / sub).mkdir(parents=True)
    if video in ("real", "portrait"):
        _video(run / "assembly" / "final.mp4", "108x192" if video == "portrait" else "320x180")
    elif video == "fake":
        (run / "assembly" / "draft.mp4").write_bytes(b"not really a video")
    if slide:
        Image.new("RGB", (1920, 1080), "#f5f1e8").save(run / "slides" / "slide_001.png")
    script = deck_to_script(load_deck(EXAMPLE / "deck.json"))
    if title is not None:
        script = script.model_copy(update={"video_title": title})
    (run / "script.json").write_text(script.model_dump_json(), encoding="utf-8")
    (run / "subtitles" / "subtitles.srt").write_text(SRT, encoding="utf-8")
    (run / "credits.json").write_text(json.dumps({"entries": [], "pending": [], "description_text": ""}))
    (run / "qc" / "qc_report.json").write_text(json.dumps(qc or {"errors": 0, "warnings": 1, "findings": []}))
    (run / "logs" / "voice.log").write_text(f"$ voice\n{SAY}", encoding="utf-8")
    return run


def _read(run: Path, name: str) -> str:
    return (run / mk.KIT_DIR / name).read_text(encoding="utf-8")


# --- pure helpers ---------------------------------------------------------------------------


def test_srt_to_vtt() -> None:
    """chipcat + cel (duplicate folded): timestamps get a dot, cue ids and text are kept."""
    vtt = mk.srt_to_vtt("1\r\n00:00:01,500 --> 00:00:03,000\r\n兩行\r\n字幕\r\n")
    assert vtt == "WEBVTT\n\n1\n00:00:01.500 --> 00:00:03.000\n兩行\n字幕\n"


def test_description_html_escapes_and_links_chapter_stamps() -> None:
    """chipcat."""
    out = description_html("章節：\n0:00 開場\n1:02:03 尾聲\n<script>x</script> 9:99 不是行首")
    assert 'data-t="0">0:00</a> 開場' in out and 'data-t="3723">1:02:03</a>' in out
    assert "&lt;script&gt;" in out and "<script>" not in out
    assert 'data-t="639"' not in out  # only line-leading stamps are chapters


def test_machine_voice_follows_the_last_synthesis_not_the_last_run(tmp_path: Path) -> None:
    """chipcat (regression 2026-10-15) + yokai's log test (folded in)."""
    (tmp_path / "logs").mkdir()
    log = tmp_path / "logs" / "voice.log"
    assert not voice_source.uses_machine_voice(tmp_path) and voice_source.last_tts_provider(tmp_path) is None
    log.write_text("INFO content_farm.voice.fish_audio ok", encoding="utf-8")  # yokai: no TTS line
    assert not voice_source.uses_machine_voice(tmp_path)
    log.write_text(f"$ voice\n{SAY}", encoding="utf-8")
    assert voice_source.uses_machine_voice(tmp_path)
    # A cached re-run logs only "Reusing existing audio" — still `say`.
    log.write_text(f"$ voice\n{SAY}\n$ voice\n{REUSE}", encoding="utf-8")
    assert voice_source.uses_machine_voice(tmp_path)
    log.write_text(f"$ voice\n{SAY}\n$ voice\n{FISH}\n$ voice\n{REUSE}", encoding="utf-8")
    assert not voice_source.uses_machine_voice(tmp_path)
    assert voice_source.last_tts_provider(tmp_path) == "fish_audio"


def test_short_cut_reads_the_voice_of_its_long_run(tmp_path: Path) -> None:
    """integration: a Short has no voice step; the long run's log decides."""
    long_run, short = tmp_path / "long", tmp_path / "short"
    (long_run / "logs").mkdir(parents=True)
    (long_run / "logs" / "voice.log").write_text(SAY, encoding="utf-8")
    shorts_cut.write_spec(short, shorts_cut.ShortSpec(
        long_run_dir=str(long_run), slide_id="s09", number="7,722", caption="c", title="t",
        long_channel="晶片貓", long_title="CoWoS"))
    assert voice_source.uses_machine_voice(short)


def test_synthetic_advice_follows_the_flag() -> None:
    """chipcat."""
    assert "「否」" in synthetic_advice({"contains_synthetic_media": False})
    advice = synthetic_advice({"contains_synthetic_media": True})
    assert "選 **「否」**（Leon 2026-10-16 決策）" in advice  # disclosed in the description instead
    assert "「是」" not in advice and "contains_synthetic_media" in advice


# --- whole kit ------------------------------------------------------------------------------


@needs_ffmpeg
def test_write_kit_builds_every_file_and_flags_preview_and_machine_voice(tmp_path: Path) -> None:
    """chipcat + cel's file-list test (folded)."""
    run = _run(tmp_path)
    kit = mk.write_kit(run, load_channel("chipcat"))
    out = run / mk.KIT_DIR
    assert kit.preview and kit.machine_voice and not kit.is_short and kit.directory == out.resolve()
    assert {p.name for p in out.iterdir()} == {"README.md", "preview.html", "title.txt", "description.txt",
                                               "tags.txt", "subtitles.srt", "subtitles.vtt", "thumbnail.png"}
    readme = _read(run, "README.md")
    assert readme.startswith(MACHINE_VOICE_BANNER) and "成片閘門尚未核可" in readme
    assert "否，這不是為兒童打造的內容" in readme and "晶片貓" in readme
    meta = publish.build_meta(load_channel("chipcat"), run)
    assert _read(run, "title.txt").strip() == meta["title"]
    assert _read(run, "description.txt") == meta["description"]
    assert _read(run, "tags.txt").strip() == ", ".join(meta["tags"])
    page = _read(run, "preview.html")
    assert 'src="../../assembly/final.mp4"' in page and "addTextTrack" in page
    assert "aspect-ratio: 16 / 9" in page
    with Image.open(out / "thumbnail.png") as thumb:
        assert thumb.size == (1280, 720)
    assert (out / "thumbnail.png").stat().st_size < mk.THUMB_MAX_BYTES


@needs_ffmpeg
def test_packaged_meta_counts_only_while_the_final_approval_matches(tmp_path: Path) -> None:
    """chipcat (regression 2026-10-15). Supersedes cel's "package meta is preferred", which used a
    youtube_meta.json from an unapproved (possibly older) render as the final version."""
    run, chipcat = _run(tmp_path), load_channel("chipcat")
    meta = publish.build_meta(chipcat, run)
    publish.write_meta(run, {**meta, "title": "核可後的標題"})
    assert mk.write_kit(run, chipcat).preview
    decide(run, chipcat, Gate.FINAL, "approved", by="test")
    kit = mk.write_kit(run, chipcat)
    assert not kit.preview
    assert _read(run, "title.txt") == "核可後的標題\n"
    assert "成片閘門尚未核可" not in _read(run, "README.md")
    (run / "qc" / "qc_report.json").write_text(json.dumps({"errors": 0, "warnings": 0, "findings": []}))
    assert mk.write_kit(run, chipcat).preview  # reviewed artifacts changed → approval no longer matches


@needs_ffmpeg
def test_kit_files_and_readme(tmp_path: Path) -> None:
    """yokai."""
    run = _run(tmp_path)
    mk.write_kit(run, load_channel("yokai"), mk.KitOptions(playlist="山海經異獸"))
    readme = _read(run, "README.md")
    assert "妖怪溯源所" in readme and "山海經異獸" in readme and "私人" in readme
    assert "中文（台灣）" in readme and "允許嵌入" in readme and "Content ID" in readme
    assert str((run / "assembly" / "final.mp4").resolve()) in readme
    assert len(_read(run, "title.txt").strip()) <= mk.TITLE_MAX
    vtt = _read(run, "subtitles.vtt")
    assert vtt.startswith("WEBVTT") and "00:00:01.500" in vtt


@needs_ffmpeg
def test_readme_lists_status_and_studio_fields(tmp_path: Path) -> None:
    """cel."""
    run = _run(tmp_path, qc={"errors": 1, "warnings": 2})
    mk.write_kit(run, load_channel("cel"))
    readme = _read(run, "README.md")
    assert readme.startswith(MACHINE_VOICE_BANNER)
    for needle in ("賽璐璐研究室", "否，這不是為兒童打造的內容", "中文（台灣）", "教育", "變造或合成內容",
                   "成片閘門尚未核可", "1 error / 2 warn", "標題投影片", "## 先處理", "QC 有 1 個 error",
                   "## 章節", "macOS say（暫用）"):
        assert needle in readme, needle


@needs_ffmpeg
def test_fish_voice_has_no_machine_banner(tmp_path: Path) -> None:
    """yokai (real voice) + cel (--voice fish override), folded."""
    run = _run(tmp_path)
    mk.write_kit(run, load_channel("cel"), mk.KitOptions(machine_voice=False))
    assert MACHINE_VOICE_BANNER not in _read(run, "README.md") and "暫用機器聲" not in _read(run, "README.md")
    assert "Fish Audio" in _read(run, "preview.html")


@needs_ffmpeg
def test_thumbnail_falls_back_to_a_video_frame(tmp_path: Path) -> None:
    """yokai (frame thumbnail) + cel (missing title slide): no slide → a frame, 1280×720, < 2 MB."""
    run = _run(tmp_path, slide=False)
    kit = mk.write_kit(run, load_channel("yokai"))
    thumbs = list((run / mk.KIT_DIR).glob("thumbnail.*"))
    assert thumbs == [kit.thumbnail] and thumbs[0].stat().st_size < mk.THUMB_MAX_BYTES
    assert Image.open(thumbs[0]).size == (1280, 720) and "畫格" in kit.thumbnail_note
    assert not (run / mk.KIT_DIR / ".thumb_frame.png").exists()


@needs_ffmpeg
def test_thumbnail_at_uses_that_frame(tmp_path: Path) -> None:
    """yokai's --thumbnail-at, now an override over the title slide."""
    kit = mk.write_kit(_run(tmp_path), load_channel("yokai"), mk.KitOptions(thumbnail_at=1.0))
    assert "1.0 秒" in kit.thumbnail_note


def test_fake_video_without_title_slide_is_an_error(tmp_path: Path) -> None:
    """cel: no thumbnail source at all (no slide, video not decodable) is an error, not a blank kit."""
    run = _run(tmp_path, video="fake", slide=False)
    with pytest.raises(FFmpegError):
        mk.write_kit(run, load_channel("cel"))


def test_no_video_is_an_error(tmp_path: Path) -> None:
    """cel."""
    with pytest.raises(FileNotFoundError):
        mk.write_kit(_run(tmp_path, video="none"), load_channel("cel"))


def test_title_over_100_chars_is_an_error(tmp_path: Path) -> None:
    """chipcat (yokai truncated silently, cel only warned)."""
    with pytest.raises(ValueError, match="YouTube max 100"):
        mk.write_kit(_run(tmp_path, video="fake", title="長" * 101), load_channel("cel"))


# --- preview.html ---------------------------------------------------------------------------


@needs_ffmpeg
def test_preview_is_offline_and_escaped(tmp_path: Path) -> None:
    """yokai: subtitle text cannot close the script tag; chapters seek; brand accent."""
    run = _run(tmp_path)
    mk.write_kit(run, load_channel("yokai"))
    page = _read(run, "preview.html")
    assert "http" not in page.split("<main>")[0]  # no CDN / external request in the head
    assert "</script>不是" not in page and "<\\/script>不是" in page and "句子<\\/b>" in page
    assert "macOS say" in page and "QC" in page and "data-t=" in page
    assert "#e0503a" in page                    # yokai brand accent


def test_preview_is_offline_relative_and_escaped(tmp_path: Path) -> None:
    """cel: title escaped, no remote assets, every chapter clickable, QC counts, landscape fallback."""
    run = _run(tmp_path, video="fake", title="<script>alert(1)</script> 標題", qc={"errors": 1, "warnings": 2})
    mk.write_kit(run, load_channel("cel"))
    page = _read(run, "preview.html")
    assert 'src="../../assembly/draft.mp4"' in page
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)" in page
    assert not re.search(r"<(script|link|img|source)[^>]+(src|href)=\"https?://", page)
    chapters = re.findall(r'<li><a href="#" data-t="(\d+)"', page)
    assert chapters and chapters[0] == "0" and len(chapters) == 6
    assert "1 error / 2 warn" in page and "aspect-ratio: 16 / 9" in page


def test_vertical_channel_gets_vertical_player_when_the_video_cannot_be_probed(tmp_path: Path) -> None:
    """cel: falls back to the channel's aspect."""
    run = _run(tmp_path, video="fake")
    kit = mk.write_kit(run, load_channel("offwork"))
    assert kit.is_short and "aspect-ratio: 9 / 16" in _read(run, "preview.html")


@needs_ffmpeg
def test_portrait_video_gets_shorts_player_on_any_channel(tmp_path: Path) -> None:
    """yokai's Shorts test, now decided by the video's real size (not the channel or short_source.json)."""
    run = _run(tmp_path, video="portrait")
    kit = mk.write_kit(run, load_channel("yokai"))
    assert kit.is_short and "aspect-ratio: 9 / 16" in _read(run, "preview.html")
    assert Image.open(kit.thumbnail).size == mk.SHORT_THUMB_SIZE


@needs_ffmpeg
def test_out_dir_keeps_the_run_untouched_and_the_video_reachable(tmp_path: Path) -> None:
    """--out (integration): kit elsewhere, relative and absolute video sources both resolve."""
    run, out = _run(tmp_path), tmp_path / "elsewhere" / "kit"
    kit = mk.write_kit(run, load_channel("chipcat"), mk.KitOptions(out_dir=out))
    assert kit.directory == out.resolve() and not (run / mk.KIT_DIR).exists()
    page = (out / "preview.html").read_text(encoding="utf-8")
    relative = re.search(r'<source src="([^"]+)"', page).group(1)
    assert (out / relative).resolve() == (run / "assembly" / "final.mp4").resolve()
    assert (run / "assembly" / "final.mp4").resolve().as_uri() in page
