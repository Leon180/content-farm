"""Manual-upload kit (upload/manual/): README, plain-text fields, thumbnail, captions, preview.html."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from PIL import Image

from content_farm.explainer.deck import load_deck
from content_farm.explainer.to_script import deck_to_script
from content_farm.production import manual_kit, publish
from content_farm.production.channels import load_channel
from content_farm.production.manual_readme import MACHINE_VOICE_BANNER

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos"
SRT = "1\n00:00:00,000 --> 00:00:02,500\n第一句\n\n2\n00:00:02,500 --> 00:00:05,000\n第二句\n"


def _run(tmp_path: Path, *, title: str | None = None) -> Path:
    run = tmp_path / "run"
    for sub in ("assembly", "slides", "subtitles", "logs", "qc"):
        (run / sub).mkdir(parents=True)
    (run / "assembly" / "draft.mp4").write_bytes(b"not really a video")
    script = deck_to_script(load_deck(EXAMPLE / "deck.json"))
    if title is not None:
        script = script.model_copy(update={"video_title": title})
    (run / "script.json").write_text(script.model_dump_json(), encoding="utf-8")
    (run / "credits.json").write_text(json.dumps({"entries": [], "pending": [], "description_text": ""}))
    Image.new("RGB", (1920, 1080), "#f5f1e8").save(run / "slides" / "slide_001.png")
    (run / "subtitles" / "subtitles.srt").write_text(SRT, encoding="utf-8")
    (run / "logs" / "voice.log").write_text(f"x {manual_kit.MACHINE_VOICE_MARK} INFO say\n", encoding="utf-8")
    (run / "qc" / "qc_report.json").write_text(json.dumps({"errors": 1, "warnings": 2}))
    return run


def test_kit_writes_every_file_with_title_slide_thumbnail(tmp_path: Path) -> None:
    run = _run(tmp_path)
    paths = manual_kit.write_kit(load_channel("cel"), run)
    kit = run / manual_kit.KIT_DIR
    assert {p.name for p in paths} == {"thumbnail.png", "title.txt", "description.txt", "tags.txt",
                                       "subtitles.srt", "subtitles.vtt", "README.md", "preview.html"}
    with Image.open(kit / "thumbnail.png") as thumb:
        assert thumb.size == (1280, 720)
    assert (kit / "thumbnail.png").stat().st_size < manual_kit.THUMB_MAX_BYTES
    meta = publish.build_meta(load_channel("cel"), run)
    assert (kit / "title.txt").read_text(encoding="utf-8").strip() == meta["title"]
    assert (kit / "description.txt").read_text(encoding="utf-8") == meta["description"]
    assert (kit / "tags.txt").read_text(encoding="utf-8").strip() == ", ".join(meta["tags"])


def test_readme_flags_machine_voice_first_and_lists_studio_fields(tmp_path: Path) -> None:
    run = _run(tmp_path)
    manual_kit.write_kit(load_channel("cel"), run)
    readme = (run / manual_kit.KIT_DIR / "README.md").read_text(encoding="utf-8")
    assert readme.startswith(MACHINE_VOICE_BANNER)
    for needle in ("賽璐璐研究室", "否，這不是為兒童打造的內容", "中文（台灣）", "教育", "變造或合成內容",
                   "成片閘門尚未核可", "1 error / 2 warn", "標題投影片", str((run / "assembly" / "draft.mp4").resolve())):
        assert needle in readme, needle


def test_fish_voice_override_drops_banner(tmp_path: Path) -> None:
    run = _run(tmp_path)
    manual_kit.write_kit(load_channel("cel"), run, machine_voice=False)
    kit = run / manual_kit.KIT_DIR
    assert MACHINE_VOICE_BANNER not in (kit / "README.md").read_text(encoding="utf-8")
    assert "Fish Audio" in (kit / "preview.html").read_text(encoding="utf-8")


def test_package_meta_is_preferred_over_rebuilding(tmp_path: Path) -> None:
    run = _run(tmp_path)
    meta = {**publish.build_meta(load_channel("cel"), run), "title": "套件用的 package 標題"}
    publish.write_meta(run, meta)
    manual_kit.write_kit(load_channel("cel"), run)
    kit = run / manual_kit.KIT_DIR
    assert (kit / "title.txt").read_text(encoding="utf-8").strip() == "套件用的 package 標題"
    assert "成片閘門尚未核可" not in (kit / "README.md").read_text(encoding="utf-8")


def test_preview_is_offline_relative_and_escaped(tmp_path: Path) -> None:
    run = _run(tmp_path, title="<script>alert(1)</script> 標題")
    manual_kit.write_kit(load_channel("cel"), run)
    html = (run / manual_kit.KIT_DIR / "preview.html").read_text(encoding="utf-8")
    assert 'src="../../assembly/draft.mp4"' in html
    assert '<track kind="captions" src="subtitles.vtt"' in html and " default>" in html
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)" in html
    assert not re.search(r"<(script|link|img)[^>]+(src|href)=\"https?://", html)  # no CDN / remote assets
    stamps = re.findall(r'data-t="(\d+)"', html)
    assert stamps and stamps[0] == "0" and len(stamps) == 6
    assert "macOS say" in html and "1 error / 2 warn" in html and 'class="landscape"' in html


def test_vertical_channel_gets_vertical_player(tmp_path: Path) -> None:
    run = _run(tmp_path)
    manual_kit.write_kit(load_channel("offwork"), run)
    assert 'class="vertical"' in (run / manual_kit.KIT_DIR / "preview.html").read_text(encoding="utf-8")


def test_srt_to_vtt() -> None:
    vtt = manual_kit.srt_to_vtt(SRT)
    assert vtt.startswith("WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.500\n")
    assert "," not in vtt.split("\n")[3]


def test_missing_thumbnail_source_is_an_error(tmp_path: Path) -> None:
    run = _run(tmp_path)
    (run / "slides" / "slide_001.png").unlink()
    with pytest.raises(FileNotFoundError, match="title slide"):
        manual_kit.write_kit(load_channel("cel"), run)


def test_no_video_is_an_error(tmp_path: Path) -> None:
    run = _run(tmp_path)
    (run / "assembly" / "draft.mp4").unlink()
    with pytest.raises(FileNotFoundError):
        manual_kit.write_kit(load_channel("cel"), run)
