"""寓言 thumbnails: option checks, hook layout, phone-size QC, retired-name check, cover frame, drawing requests."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from content_farm.production.channels import load_channel
from content_farm.production.fable import check, images, model, thumb
from tests.unit.test_fable import fable_dict, load

OPTION = {"hook": "誰會贏？", "image_prompt": "close-up of two small songbirds facing off, one lunging with spread wings"}


def with_thumb(*options: dict, fmt: str = "mid") -> model.Fable:
    return load(fable_dict(format=fmt, thumb=list(options or [OPTION])))


def test_valid_options_pass_the_checks() -> None:
    assert check.thumb_problems(with_thumb(OPTION, {**OPTION, "hook": "打還是讓？", "layout": "left"})) == []


def test_hook_over_eight_characters_is_a_problem() -> None:
    fable = load(fable_dict(thumb=[{**OPTION, "hook": "小狐狸為什麼不回頭"}]))
    assert any("上限 8" in p for p in check.thumb_problems(fable))


def test_hook_that_only_repeats_the_title_is_a_problem() -> None:
    fable = load(fable_dict(thumb=[{**OPTION, "hook": "為什麼不肯回頭"}]))
    assert any("重複一次" in p for p in check.thumb_problems(fable))


def test_hook_and_prompt_must_not_leak_the_concept() -> None:
    fable = load(fable_dict(thumb=[{**OPTION, "hook": "測試別名？"}, {**OPTION, "image_prompt": OPTION["image_prompt"] + " test concept"}]))
    assert len([p for p in check.thumb_problems(fable) if "洩漏" in p]) == 2


def test_thumb_is_optional_and_capped_at_three() -> None:
    assert load(fable_dict()).thumb == ()
    try:
        load(fable_dict(thumb=[OPTION] * 4))
    except ValueError:
        return
    raise AssertionError("four options should be rejected")


def test_split_hook_breaks_after_punctuation_or_in_the_middle() -> None:
    assert thumb.split_hook("為什麼，沒人贏", 2) == ["為什麼，", "沒人贏"]
    assert thumb.split_hook("為什麼沒人贏呢", 2) == ["為什麼沒", "人贏呢"]
    assert thumb.split_hook("誰會贏？", 2) == ["誰會贏？"]


def test_eight_character_hook_is_readable_at_168_px_in_every_layout() -> None:
    for layout in ("bottom", "left", "right"):
        option = model.ThumbOption(hook="為什麼沒人贏的呢", image_prompt=OPTION["image_prompt"], layout=layout)
        assert thumb.tiny_text_px(option, "mid") >= thumb.MIN_TINY_TEXT_PX, layout


def test_page_uses_the_channel_name_not_a_literal() -> None:
    channel = load_channel("fable")
    html = thumb.thumb_page(with_thumb(), channel, with_thumb().thumb[0], "file:///x.png")
    assert channel.name in html and "寓言學堂" not in html and "誰會贏？" in html


def test_retired_channel_name_is_rejected() -> None:
    channel = load_channel("fable")
    assert "寓言學堂" in channel.former_names and channel.name not in channel.former_names
    fable = with_thumb({**OPTION, "hook": "寓言學堂"})
    levels = {f.check: f.level for f in thumb.thumb_findings(Path("."), fable, channel)}
    assert levels["fable_thumb_name"] == "error"


def test_contrast_is_measured_under_the_hook_box(tmp_path: Path) -> None:
    dark, light = tmp_path / "dark.png", tmp_path / "light.png"
    Image.new("RGB", (320, 180), (40, 25, 15)).save(dark)
    Image.new("RGB", (320, 180), (250, 240, 200)).save(light)
    assert thumb.contrast_under_hook(dark, "bottom") > 8
    assert thumb.contrast_under_hook(light, "bottom") < thumb.MIN_CONTRAST


def test_missing_options_warn_and_unrendered_options_error(tmp_path: Path) -> None:
    channel = load_channel("fable")
    assert thumb.thumb_findings(tmp_path, load(fable_dict()), channel)[0].level == "warn"
    findings = thumb.thumb_findings(tmp_path, with_thumb(), channel)
    assert [f.level for f in findings] == ["error"] and "not rendered" in findings[0].message


def test_thumbnail_pictures_are_drawn_for_the_thumbnail_frame() -> None:
    channel = load_channel("fable")
    requests = thumb.thumb_requests(with_thumb(OPTION, OPTION), channel)
    assert [r.slide_id for r in requests] == ["thumb_1", "thumb_2"]
    assert all(channel.ai_illustration.style_prefix.strip() in r.prompt and "Close-up" in r.prompt for r in requests)
    assert (requests[0].width, requests[0].height) == images.DRAW["mid"]
    assert requests[0].seed != requests[1].seed


def _manifest(run_dir: Path, fable: model.Fable) -> None:
    shots = {f"{b.id}.{n}": {"draws": f"{b.id}.{n}", "image_id": f"{b.id}_{n}"} for b in fable.beats for n in range(1, len(b.shots) + 1)}
    path = run_dir / images.MANIFEST
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"shots": shots, "clips": {}}), encoding="utf-8")


def test_cover_frame_is_the_most_complete_story_picture_before_the_reveal(tmp_path: Path) -> None:
    fable = load(fable_dict())
    _manifest(tmp_path, fable)
    folder = tmp_path / "assets" / "ai_images"
    folder.mkdir(parents=True)
    flat = Image.new("RGB", (64, 36), (120, 120, 120))
    busy = Image.effect_noise((64, 36), 90).convert("RGB").point(lambda v: v)
    busy.paste((200, 60, 30), (0, 0, 32, 36))
    for beat in fable.beats:
        for n in range(1, len(beat.shots) + 1):
            (busy if (beat.id, n) == ("b3", 2) else flat).save(folder / f"{beat.id}_{n}.png")
    frame = thumb.cover_frame(tmp_path, fable, [10.0] * len(fable.beats))
    assert frame["shot"] == "b3.2" and frame["beat"] == "b3"
    assert frame["seconds"] == 25.5 and frame["timestamp"] == "0:25"
    assert "0:25" in thumb.metadata_line(frame)


def test_cover_frame_never_spoils_the_reveal(tmp_path: Path) -> None:
    fable = load(fable_dict())
    _manifest(tmp_path, fable)
    folder = tmp_path / "assets" / "ai_images"
    folder.mkdir(parents=True)
    for beat in fable.beats:
        for n in range(1, len(beat.shots) + 1):
            Image.new("RGB", (64, 36), (10 * int(beat.id[1:]), 90, 60)).save(folder / f"{beat.id}_{n}.png")
    frame = thumb.cover_frame(tmp_path, fable, [10.0] * len(fable.beats))
    assert int(frame["beat"][1:]) < 5      # b5 is the reveal in the fixture
