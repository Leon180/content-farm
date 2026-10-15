"""Manual YouTube Studio upload kit + offline preview page."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from content_farm.explainer.deck import load_deck
from content_farm.explainer.to_script import deck_to_script
from content_farm.production import manual_kit, publish
from content_farm.production.channels import load_channel

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos"
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

SRT = "1\n00:00:00,000 --> 00:00:01,500\n九尾狐</script>不是\n\n2\n00:00:01,500 --> 00:00:03,000\n狐狸精\n"


def _run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "assembly").mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=1920x1080:d=3:r=30",
                    "-f", "lavfi", "-i", "sine=d=3", "-shortest", "-pix_fmt", "yuv420p",
                    str(run / "assembly" / "final.mp4")], check=True)
    (run / "subtitles").mkdir()
    (run / "subtitles" / "subtitles.srt").write_text(SRT, encoding="utf-8")
    script = deck_to_script(load_deck(EXAMPLE / "deck.json"))
    (run / "script.json").write_text(script.model_dump_json(), encoding="utf-8")
    (run / "credits.json").write_text(json.dumps({"entries": [], "pending": [], "description_text": ""}))
    (run / "qc").mkdir()
    (run / "qc" / "qc_report.json").write_text(json.dumps({"errors": 0, "warnings": 1, "findings": []}))
    return run


def _kit(run: Path, **options: object) -> Path:
    channel = load_channel("yokai")
    meta = publish.build_meta(channel, run)
    return manual_kit.build_kit(channel, run, meta, manual_kit.KitOptions(**options))


def test_kit_files_and_readme(tmp_path: Path) -> None:
    out = _kit(_run(tmp_path), machine_voice=True, playlist="山海經異獸")
    for name in ("README.md", "title.txt", "description.txt", "tags.txt", "subtitles.srt",
                 "subtitles.vtt", "preview.html"):
        assert (out / name).is_file(), name
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert readme.splitlines()[0].startswith("> ⚠ 暫用機器聲")
    assert "妖怪溯源所" in readme and "山海經異獸" in readme and "私人" in readme
    assert "中文（台灣）" in readme and "否" in readme
    assert str((tmp_path / "run" / "assembly" / "final.mp4").resolve()) in readme
    assert len((out / "title.txt").read_text(encoding="utf-8").strip()) <= 100
    assert (out / "subtitles.vtt").read_text(encoding="utf-8").startswith("WEBVTT")
    assert "00:00:01.500" in (out / "subtitles.vtt").read_text(encoding="utf-8")


def test_voice_is_machine_reads_voice_log(tmp_path: Path) -> None:
    assert manual_kit.voice_is_machine(tmp_path) is False
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "voice.log").write_text("INFO content_farm.voice.fish_audio ok", encoding="utf-8")
    assert manual_kit.voice_is_machine(tmp_path) is False
    (tmp_path / "logs" / "voice.log").write_text("content_farm.voice.macos_say INFO macOS say TTS",
                                                 encoding="utf-8")
    assert manual_kit.voice_is_machine(tmp_path) is True


def test_real_voice_has_no_machine_banner(tmp_path: Path) -> None:
    out = _kit(_run(tmp_path), machine_voice=False)
    assert "暫用機器聲" not in (out / "README.md").read_text(encoding="utf-8")


def test_thumbnail_is_1280x720_under_2mb(tmp_path: Path) -> None:
    out = _kit(_run(tmp_path), machine_voice=True)
    thumbs = list(out.glob("thumbnail.*"))
    assert len(thumbs) == 1 and thumbs[0].stat().st_size < 2 * 1024 * 1024
    assert Image.open(thumbs[0]).size == (1280, 720)


def test_preview_is_offline_and_escaped(tmp_path: Path) -> None:
    out = _kit(_run(tmp_path), machine_voice=True)
    page = (out / "preview.html").read_text(encoding="utf-8")
    assert "http://" not in page.replace("http://www.w3.org", "") and "https://cdn" not in page
    assert 'src="../../assembly/final.mp4"' in page
    assert "macos_say" in page and "QC" in page
    assert "</script>不是" not in page          # subtitle text cannot close the script tag
    assert "data-seek=" in page                 # chapters are clickable
    assert "#e0503a" in page                    # yokai brand accent


def test_shorts_use_portrait_player(tmp_path: Path) -> None:
    run = _run(tmp_path)
    channel = load_channel("offwork")
    meta = {**publish.build_meta(load_channel("yokai"), run), "channel": "offwork"}
    out = manual_kit.build_kit(channel, run, meta, manual_kit.KitOptions(machine_voice=True))
    assert "player portrait" in (out / "preview.html").read_text(encoding="utf-8")
