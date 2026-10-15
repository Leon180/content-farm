"""manual-kit: Studio upload checklist, plain-text fields, offline preview page."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from content_farm.explainer.deck import load_deck
from content_farm.explainer.to_script import deck_to_script
from content_farm.production import manual_kit as mk
from content_farm.production import publish
from content_farm.production.channels import load_channel

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_srt_to_vtt() -> None:
    vtt = mk.srt_to_vtt("1\n00:00:01,500 --> 00:00:03,000\n兩行\n字幕\n")
    assert vtt == "WEBVTT\n\n00:00:01.500 --> 00:00:03.000\n兩行\n字幕\n"


def test_description_html_escapes_and_links_chapter_stamps() -> None:
    out = mk.description_html("章節：\n0:00 開場\n1:02:03 尾聲\n<script>x</script> 9:99 不是行首")
    assert '<a data-t="0">0:00</a> 開場' in out and '<a data-t="3723">1:02:03</a>' in out
    assert "&lt;script&gt;" in out and "<script>" not in out
    assert 'data-t="639"' not in out  # only line-leading stamps are chapters


SAY = "2026-10-15 17:59:58,398 content_farm.voice.macos_say INFO macOS say TTS: 231174 bytes -> a.mp3\n"
REUSE = "2026-10-15 23:14:16,953 content_farm.voice.generator INFO Reusing existing audio: a.mp3\n"
FISH = "2026-10-16 09:00:00,000 content_farm.voice.fish_audio INFO Fish Audio TTS: 1 bytes -> a.mp3\n"


def test_machine_voice_follows_the_last_synthesis_not_the_last_run(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir()
    log = tmp_path / "logs" / "voice.log"
    assert not mk.uses_machine_voice(tmp_path)  # no log → unknown, not claimed
    log.write_text(f"$ voice\n{SAY}", encoding="utf-8")
    assert mk.uses_machine_voice(tmp_path)
    # Regression (2026-10-15): a cached re-run logs only "Reusing existing audio" — still `say`.
    log.write_text(f"$ voice\n{SAY}\n$ voice\n{REUSE}", encoding="utf-8")
    assert mk.uses_machine_voice(tmp_path)
    log.write_text(f"$ voice\n{SAY}\n$ voice\n{FISH}\n$ voice\n{REUSE}", encoding="utf-8")
    assert not mk.uses_machine_voice(tmp_path)


def test_synthetic_advice_follows_the_flag() -> None:
    assert "否" in mk.synthetic_advice({"contains_synthetic_media": False})
    assert "建議選「是」" in mk.synthetic_advice({"contains_synthetic_media": True})


def _long_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    for sub in ("assembly", "slides", "subtitles", "logs", "qc"):
        (run / sub).mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=0x3366cc:s=320x180:d=1",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", "-pix_fmt", "yuv420p",
                    "-shortest", str(run / "assembly" / "final.mp4")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=white:s=1920x1080", "-frames:v", "1",
                    str(run / "slides" / "slide_001.png")], check=True)
    (run / "script.json").write_text(deck_to_script(load_deck(EXAMPLE / "deck.json")).model_dump_json())
    (run / "subtitles" / "subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n句子</b>\n")
    (run / "credits.json").write_text(json.dumps({"entries": [], "pending": [], "description_text": ""}))
    (run / "qc" / "qc_report.json").write_text(json.dumps({"errors": 0, "warnings": 1, "findings": []}))
    (run / "logs" / "voice.log").write_text(f"$ voice\n{SAY}")
    return run


@needs_ffmpeg
def test_write_kit_builds_every_file_and_flags_preview_and_machine_voice(tmp_path: Path) -> None:
    run = _long_run(tmp_path)
    kit = mk.write_kit(run, load_channel("chipcat"))
    out = run / "upload" / "manual"
    assert kit.preview and kit.machine_voice and not kit.is_short
    for name in ("README.md", "preview.html", "title.txt", "description.txt", "tags.txt",
                 "subtitles.srt", "subtitles.vtt", "thumbnail.png"):
        assert (out / name).is_file(), name
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert readme.startswith(mk.MACHINE_VOICE_BANNER) and "成片閘門尚未核可" in readme
    assert "否，這不是為兒童打造的內容" in readme and "晶片貓" in readme
    page = (out / "preview.html").read_text(encoding="utf-8")
    assert 'src="../../assembly/final.mp4"' in page and "createObjectURL" in page
    assert "句子<\\/b>" in page and "aspect-ratio: 16 / 9" in page  # VTT cannot close its <script>
    assert "http" not in page.split("<main>")[0]  # no CDN / external request in the head
    with subprocess.Popen(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                           str(out / "thumbnail.png")], stdout=subprocess.PIPE, text=True) as probe:
        assert probe.communicate()[0].strip() == "1280,720"


@needs_ffmpeg
def test_kit_prefers_the_packaged_meta(tmp_path: Path) -> None:
    run = _long_run(tmp_path)
    meta = publish.build_meta(load_channel("chipcat"), run)
    publish.write_meta(run, {**meta, "title": "核可後的標題"})
    kit = mk.write_kit(run, load_channel("chipcat"))
    assert not kit.preview
    assert (run / "upload" / "manual" / "title.txt").read_text(encoding="utf-8") == "核可後的標題\n"
