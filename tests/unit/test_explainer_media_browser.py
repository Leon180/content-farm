"""v2 media through a real headless Chromium + ffmpeg (no network: stock is disabled/mocked)."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path

import pytest
from PIL import Image

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.capture import PageCapturer
from content_farm.explainer.deck import Deck
from content_farm.explainer.media_run import MediaOptions, media_to_visual
from content_farm.explainer.pages import build_pages
from content_farm.explainer.render import render_pages
from content_farm.explainer.timeline import plan_slide_timeline
from tests.unit.explainer_helpers import deck_dict

pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def _deck() -> Deck:
    data = deck_dict()
    data["sources"][0].update(publisher="經濟日報", published="2026-07-17")
    sections = data["sections"]
    sections[0]["slides"][0]["media"] = {"kind": "stock", "query": "wafer"}  # → fallback
    sections[1]["slides"][0]["media"] = {"kind": "animated", "animation": "count_up"}
    sections[1]["slides"][1]["media"] = {"kind": "ai_image", "prompt": "a grey cat"}
    sections[2]["slides"][0]["media"] = {"kind": "title_card", "source_id": "s1"}
    return Deck.model_validate(data)


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def test_animation_frames_are_a_function_of_time(tmp_path: Path) -> None:
    page = build_pages(_deck(), animate=True)[1]  # big_number count_up
    html = tmp_path / "p.html"
    html.write_text(page.html, encoding="utf-8")
    with PageCapturer() as cap:
        shots = []
        for name in ("a", "b"):
            cap._open(html).evaluate("window.__anim.seek(0.5)")  # noqa: SLF001
            out = tmp_path / f"{name}.png"
            cap._page.screenshot(path=str(out))  # noqa: SLF001
            shots.append(out)
        capture = cap.animate(html, tmp_path / "anim.mp4", 3.0)
        final = cap.still(html, tmp_path / "final.png")
    assert _md5(shots[0]) == _md5(shots[1])  # same t → same pixels
    assert _md5(shots[0]) != _md5(final)     # mid-animation differs from the end state
    assert capture.animation_seconds < 3.0
    assert capture.frames_captured == math.ceil(capture.animation_seconds * 30) + 1
    assert ffmpeg_ops.probe(capture.clip)["duration"] == pytest.approx(3.0, abs=0.04)
    # held on the final frame after the animation
    tail = Image.open(ffmpeg_ops.frame_at(capture.clip, 2.9, tmp_path / "tail.png")).convert("RGB")
    end = Image.open(final).convert("RGB")
    diff = sum(abs(a - b) for a, b in zip(tail.resize((96, 54)).tobytes(), end.resize((96, 54)).tobytes()))
    assert diff / (96 * 54 * 3) < 4


def test_media_to_visual_end_to_end_offline(tmp_path: Path) -> None:
    deck = _deck()
    run_dir = tmp_path / "run"
    render_pages(build_pages(deck), run_dir / "slides")
    clips = plan_slide_timeline([1.2, 1.4, 1.1, 1.3])
    run = media_to_visual(deck, run_dir, clips, stock=None,
                          options=MediaOptions(transition="crossfade", transition_seconds=0.3))

    used = [r.used for r in run.results]
    assert used == ["animated", "animated", "ai_placeholder", "title_card"]
    assert "FALLBACK stock→animated: stock disabled" in run.results[0].note
    assert [p.suffix for p in run.placed] == [".mp4"] * 4
    for placed, clip in zip(run.placed, clips):
        assert ffmpeg_ops.probe(placed)["duration"] == pytest.approx(clip.seconds, abs=0.04)

    report = json.loads(run.report_path.read_text())
    assert report["slides"][0]["fallback"] is True and report["slides"][2]["placeholder"] is True
    assert json.loads(run.credits_path.read_text())["entries"] == []
    assert (run_dir / "ai_image_prompts.md").is_file()
    assert run.contact_sheet.is_file()


def test_ai_image_present_gets_ken_burns_and_credit(tmp_path: Path) -> None:
    deck = _deck()
    run_dir = tmp_path / "run"
    render_pages(build_pages(deck), run_dir / "slides")
    image_dir = run_dir / "assets" / "ai_images"
    image_dir.mkdir(parents=True)
    Image.new("RGB", (1600, 900), "#335577").save(image_dir / "b2_01.png")
    run = media_to_visual(deck, run_dir, plan_slide_timeline([1.0, 1.0, 1.2, 1.0]), stock=None,
                          options=MediaOptions(transition="none"))
    ai = run.results[2]
    assert ai.used == "ai_image" and "b2_01.png" in ai.note
    assert json.loads(run.credits_path.read_text())["entries"][0]["kind"] == "ai_image"


def test_transition_none_keeps_plain_slides_as_png(tmp_path: Path) -> None:
    deck = Deck.model_validate(deck_dict())  # v1 deck: no media at all
    run_dir = tmp_path / "run"
    rendered = render_pages(build_pages(deck), run_dir / "slides")
    run = media_to_visual(deck, run_dir, plan_slide_timeline([1, 1, 1, 1]), stock=None,
                          options=MediaOptions(transition="none"))
    assert [p.suffix for p in run.placed] == [".png"] * 4
    assert [_md5(p) for p in run.placed] == [_md5(r.png_path) for r in rendered]
