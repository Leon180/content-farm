"""Shorts show AI pictures (visual v4, Leon 2026-10-24): >= 3 per Short, every one moving, all credited."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from content_farm.production.channels import load_channel
from content_farm.production.news import script as ns
from content_farm.production.news import visuals
from content_farm.production.news.render import page_html, write_credits

PROMPT = "a small robot sorting glowing cards on a desk, flat colours, original generic scene"


def _script(prompts: dict[str, str]) -> ns.NewsScript:
    beats = tuple(ns.Beat(kind=k, narration="測試旁白" * 8, screen=ns.Screen(headline="標題", points=("一點",)),
                          image_prompt=prompts.get(k, "")) for k in ns.BEAT_ORDER)
    return ns.NewsScript(item_id="hn-1", title="測試標題四字", summary="一句摘要要夠長才行吧", importance=3,
                         sources=(ns.SourceRef(url="https://ex1.com/a", title="t", read_at="2026-10-23T09:00:00+08:00"),),
                         beats=beats)


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, request, out: Path) -> dict:
        self.calls.append(request.slide_id)
        out.write_bytes(b"\x89PNG fake")
        return {"provider": "fake", "model": "z-image-turbo", "model_name": "Z-Image-Turbo (4-bit)", "license": "Apache-2.0",
                "license_url": "https://example.com/license", "steps": 9, "seconds": 1.0}


def test_a_picture_channel_needs_three_beats_with_prompts() -> None:
    channel = load_channel("technews")
    assert visuals.needs_pictures(channel)
    assert len(visuals.problems(_script({"hook": PROMPT, "what": PROMPT}), channel)) == 1
    assert visuals.problems(_script({"hook": PROMPT, "what": PROMPT, "analogy": PROMPT}), channel) == []
    bad = visuals.problems(_script({"hook": PROMPT, "what": PROMPT, "why": "photorealistic robot"}), channel)
    assert any("photoreal" in p.lower() for p in bad)


def test_the_retired_text_only_channel_is_exempt() -> None:
    assert not visuals.needs_pictures(load_channel("ent"))
    assert visuals.problems(_script({}), load_channel("ent")) == []


def test_missing_pictures_are_drawn_once_with_the_channel_style(tmp_path: Path) -> None:
    channel = load_channel("technews")
    news = _script({"hook": PROMPT, "what": PROMPT, "take": PROMPT})
    provider = FakeProvider()
    records = visuals.ensure_images(tmp_path, news, channel, provider=provider)
    assert provider.calls == ["beat1", "beat2", "beat5"] and len(records) == 3
    assert records[0]["prompt"].startswith(channel.ai_illustration.style_prefix.strip().split()[0])
    assert records[0]["seed"] == channel.ai_illustration.seed and records[1]["seed"] == channel.ai_illustration.seed + 1
    assert visuals.ensure_images(tmp_path, news, channel, provider=provider) == []         # nothing redrawn
    assert (tmp_path / "assets" / "ai_images" / "beat1.json").is_file()


def test_motion_unpacks_a_parallax_clip_into_page_frames_and_falls_back_to_a_still(tmp_path: Path, monkeypatch) -> None:
    channel = load_channel("technews")
    news = _script({"hook": PROMPT, "what": PROMPT, "take": PROMPT})
    visuals.ensure_images(tmp_path, news, channel, provider=FakeProvider())

    def fake_ensure(paths, run_dir, slide_id, image, params):
        assert (params.width, params.height) == (visuals.PIC_W, visuals.PIC_H)
        clip = run_dir / "assets" / "ai_motion" / f"{slide_id}.parallax.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(b"clip")
        return clip, {"params": {"seconds": 3.0}, "stats": {"seconds": 3.0}}

    def fake_unpack(clip: Path, out_dir: Path, run=None) -> list[str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        names = [f"f{n:03d}.jpg" for n in range(1, 4)]
        for name in names:
            (out_dir / name).write_bytes(b"jpg")
        return names

    monkeypatch.setattr(visuals, "_unpack", fake_unpack)
    pictures = visuals.ensure_motion(tmp_path, news, paths=SimpleNamespace(), ensure=fake_ensure)
    assert sorted(pictures) == [0, 1, 4] and pictures[0].frames == ("frames/beat1/f001.jpg", "frames/beat1/f002.jpg",
                                                                      "frames/beat1/f003.jpg")
    assert pictures[0].motion["kind"] == "parallax"

    def broken(*args, **kwargs):
        raise RuntimeError("depth worker died")

    still = visuals.ensure_motion(tmp_path, news, paths=SimpleNamespace(), ensure=broken)
    assert still[0].frames == () and still[0].motion["kind"] == "still" and "depth worker died" in still[0].motion["fallback_reason"]


def test_credits_list_every_picture_with_badge_model_prompt_seed_and_motion(tmp_path: Path) -> None:
    channel = load_channel("technews")
    news = _script({"hook": PROMPT, "what": PROMPT, "take": PROMPT})
    visuals.ensure_images(tmp_path, news, channel, provider=FakeProvider())
    pictures = {i: visuals.BeatPicture(i, tmp_path / "assets" / "ai_images" / f"beat{i + 1}.png", (), {"kind": "still"})
                for i in visuals.ai_beats(news)}
    (tmp_path / ns.ITEM_FILE).write_text(json.dumps({"series": "technews"}), encoding="utf-8")
    path = write_credits(tmp_path, news, pictures)
    entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
    assert [e["slide_id"] for e in entries] == ["beat1", "beat2", "beat5"]
    assert all(e["ai_label"] == "AI 示意圖" and e["model"] and e["prompt"] and e["seed"] is not None for e in entries)
    from content_farm.review import license_rules

    assert license_rules.problems(json.loads(path.read_text(encoding="utf-8"))) == []


def test_beat_page_shows_the_picture_frames_and_the_badge() -> None:
    channel = load_channel("technews")
    news = _script({"hook": PROMPT, "what": PROMPT, "take": PROMPT})
    pic = visuals.BeatPicture(0, Path("beat1.png"), ("frames/beat1/f001.jpg", "frames/beat1/f002.jpg"), {"kind": "parallax"})
    html = page_html("beat", news=news, channel=channel, day="2026-10-23", index=0, duration=5.0,
                     card={"domain": "ex1.com", "title": "t", "date": ""}, pic=pic)
    assert 'class="card hasimg"' in html and html.count('class="pf"') == 2 and "AI 示意圖" in html
    plain = page_html("beat", news=news, channel=channel, day="2026-10-23", index=1, duration=5.0,
                      card={"domain": "ex1.com", "title": "t", "date": ""})
    assert "hasimg" not in plain.split("<body")[1]


def test_the_page_swaps_frames_in_the_seek_runtime(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from content_farm.explainer.capture import PageCapturer

    channel = load_channel("technews")
    news = _script({"hook": PROMPT, "what": PROMPT, "take": PROMPT})
    frames = ("frames/beat1/f001.jpg", "frames/beat1/f002.jpg", "frames/beat1/f003.jpg")
    for name in frames:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"")
    pic = visuals.BeatPicture(0, Path("beat1.png"), frames, {"kind": "parallax"})
    html = tmp_path / "beat.html"
    html.write_text(page_html("beat", news=news, channel=channel, day="d", index=0, duration=5.0,
                              card={"domain": "x", "title": "t", "date": ""}, pic=pic), encoding="utf-8")
    try:
        capturer = PageCapturer(size=(1080, 1920)).__enter__()
    except Exception as exc:        # no browser on this machine
        pytest.skip(f"no chromium: {exc}")
    try:
        page = capturer._open(html)
        shown = []
        for t in (0.0, 1 / 30, 2 / 30, 3 / 30, 4 / 30):          # ping-pong over 3 frames: 0 1 2 1 0
            page.evaluate(f"window.__anim.seek({t})")
            shown.append(page.evaluate("Array.from(document.querySelectorAll('.pic img.pf')).findIndex(i => i.style.display === 'block')"))
        assert shown == [0, 1, 2, 1, 0]
    finally:
        capturer.__exit__(None, None, None)
