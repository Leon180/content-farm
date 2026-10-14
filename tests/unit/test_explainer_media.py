"""v2 media: ffmpeg recipes, AI-image contract, cards, placement, transitions, reports."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from content_farm.assembly.timeline_assembly import scan_timeline_clips
from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.ai_images import find_image, render_prompts_md, write_prompt_files
from content_farm.explainer.cards import key_line, overlay_html, title_card_for, title_card_html
from content_farm.explainer.deck import Deck
from content_farm.explainer.media import USED_PLACEHOLDER, ClipResult
from content_farm.explainer.media_run import (
    MediaOptions,
    apply_transitions,
    credits_text,
    media_contact_sheet,
    write_report,
)
from content_farm.explainer.timeline import SlideClip, TimelineError, place_files, plan_slide_timeline
from content_farm.visual_gen.storyboard_parser import parse_storyboard
from tests.unit.explainer_helpers import deck_dict, slide

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def _deck_with_media() -> Deck:
    data = deck_dict()
    data["sources"][0].update(publisher="經濟日報", published="2026-07-17",
                              url="https://www.money.udn.com/a/1")
    sections = data["sections"]
    sections[1]["slides"][0]["media"] = {"kind": "ai_image", "prompt": "a grey cat holding a chip"}
    sections[1]["slides"][1]["media"] = {"kind": "stock", "query": "wafer"}
    sections[2]["slides"][0]["media"] = {"kind": "title_card", "source_id": "s1"}
    return Deck.model_validate(data)


class TestFfmpegMath:
    @pytest.mark.parametrize(("seconds", "frames"), [(1.0, 30), (1.001, 31), (0.01, 1), (15.391, 462)])
    def test_frame_count_never_short(self, seconds: float, frames: int) -> None:
        assert ffmpeg_ops.frame_count(seconds) == frames

    @pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
    def test_frame_count_rejects(self, bad: float) -> None:
        with pytest.raises(ValueError):
            ffmpeg_ops.frame_count(bad)

    def test_stock_plan(self) -> None:
        assert ffmpeg_ops.stock_plan(20, 10) == ("trim", 1.0)
        mode, stretch = ffmpeg_ops.stock_plan(8, 10)
        assert mode == "slow" and stretch == pytest.approx(1.25)
        assert ffmpeg_ops.stock_plan(4, 10) == ("loop", 1.0)
        with pytest.raises(ValueError):
            ffmpeg_ops.stock_plan(0, 10)

    def test_unknown_transition(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="unknown transition"):
            ffmpeg_ops.transition_into(tmp_path / "a.mp4", tmp_path / "b.png", tmp_path / "c.mp4",
                                       2.0, style="wipe", length=0.4)


def _png(path: Path, color: str, size: tuple[int, int] = (1920, 1080)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


@needs_ffmpeg
class TestFfmpegClips:
    def test_still_clip_exact_frames(self, tmp_path: Path) -> None:
        clip = ffmpeg_ops.still_to_clip(_png(tmp_path / "a.png", "red"), tmp_path / "a.mp4", 1.25)
        info = ffmpeg_ops.probe(clip)
        assert (info["width"], info["height"]) == (1920, 1080)
        assert info["duration"] == pytest.approx(38 / 30, abs=0.02)

    @pytest.mark.parametrize(("source_seconds", "mode"), [(3.0, "trim"), (1.6, "slow"), (0.5, "loop")])
    def test_stock_fit_modes_cover_crop(self, tmp_path: Path, source_seconds: float, mode: str) -> None:
        src = tmp_path / "src.mp4"
        ffmpeg_ops.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                        f"testsrc2=s=1280x720:r=25:d={source_seconds}", "-pix_fmt", "yuv420p", str(src)])
        overlay = _png(tmp_path / "ov.png", "red")
        Image.new("RGBA", (1920, 1080), (0, 0, 0, 0)).save(overlay)
        clip, used = ffmpeg_ops.stock_to_clip(src, overlay, tmp_path / "out.mp4", 2.0, source_seconds)
        info = ffmpeg_ops.probe(clip)
        assert used == mode
        assert (info["width"], info["height"]) == (1920, 1080)
        assert info["duration"] == pytest.approx(2.0, abs=0.04)

    def test_ken_burns_zooms_in(self, tmp_path: Path) -> None:
        img = tmp_path / "img.png"
        im = Image.new("RGB", (1600, 1200), "white")
        im.paste(Image.new("RGB", (400, 300), "black"), (600, 450))  # centred black box
        im.save(img)
        clip = ffmpeg_ops.ken_burns(img, None, tmp_path / "kb.mp4", 1.5, zoom=0.3)
        first = Image.open(ffmpeg_ops.frame_at(clip, 0, tmp_path / "f0.png")).convert("L")
        last = Image.open(ffmpeg_ops.frame_at(clip, 1.45, tmp_path / "f1.png")).convert("L")
        dark = lambda im: sum(1 for p in im.getdata() if p < 60)  # noqa: E731
        assert dark(last) > dark(first) * 1.3  # box grows as we push in
        assert ffmpeg_ops.probe(clip)["duration"] == pytest.approx(1.5, abs=0.04)

    @pytest.mark.parametrize("style", ["crossfade", "push", "fadeblack"])
    def test_transition_keeps_length_and_ends_on_next_frame(self, tmp_path: Path, style: str) -> None:
        a = ffmpeg_ops.still_to_clip(_png(tmp_path / "a.png", "#ff0000"), tmp_path / "a.mp4", 1.0)
        head = _png(tmp_path / "b.png", "#0000ff")
        out = ffmpeg_ops.transition_into(a, head, tmp_path / "t.mp4", 1.0, style=style, length=0.4)
        assert ffmpeg_ops.probe(out)["duration"] == pytest.approx(1.0, abs=0.04)
        start = Image.open(ffmpeg_ops.frame_at(out, 0.1, tmp_path / "s.png")).convert("RGB")
        end = Image.open(ffmpeg_ops.frame_at(out, 0.95, tmp_path / "e.png")).convert("RGB")
        assert start.getpixel((960, 540))[0] > 200  # still red
        assert end.getpixel((960, 540))[2] > 180   # blue = next clip's first frame


class TestAiImages:
    def test_find_image_precedence(self, tmp_path: Path) -> None:
        assert find_image(tmp_path / "missing", "s04") is None
        _png(tmp_path / "s04_02.png", "red", (8, 8))
        _png(tmp_path / "s04_01.png", "red", (8, 8))
        _png(tmp_path / "s040.png", "red", (8, 8))
        assert find_image(tmp_path, "s04").name == "s04_01.png"
        _png(tmp_path / "s04.jpg", "red", (8, 8))
        assert find_image(tmp_path, "s04").name == "s04.jpg"

    def test_prompts_md_parses_as_storyboard(self, tmp_path: Path) -> None:
        deck = _deck_with_media()
        requests = write_prompt_files(deck, tmp_path)
        [variant] = parse_storyboard(tmp_path / "ai_image_prompts.md")
        [shot] = variant.image_shots
        assert shot.filename == "b1.png" == requests[0].filename
        assert shot.prompt.startswith("a grey cat holding a chip") and "16:9" in shot.prompt
        payload = json.loads((tmp_path / "ai_image_prompts.json").read_text())
        assert payload[0]["file"] == "assets/ai_images/b1.png" and payload[0]["index"] == 2

    def test_no_ai_slides_writes_nothing(self, tmp_path: Path) -> None:
        assert write_prompt_files(Deck.model_validate(deck_dict()), tmp_path) == ()
        assert not (tmp_path / "ai_image_prompts.md").exists()

    def test_md_header_names_output_dir(self) -> None:
        deck = _deck_with_media()
        assert "assets/ai_images" in render_prompts_md(deck, ())


class TestCards:
    @pytest.mark.parametrize(("layout", "expected"), [
        ("title", "副標"),
        ("bullets", "第一點 · 第二點 · 第三點"),
        ("big_number", "60%　說明"),
        ("compare", "左 vs 右"),
        ("timeline", "1987 → 2020"),
        ("quote", "「引言」"),
    ])
    def test_key_line(self, layout: str, expected: str) -> None:
        data = deck_dict()
        data["sections"][1]["slides"].append(slide("k1", layout))
        deck = Deck.model_validate(data)
        assert key_line(next(s for s in deck.slides if s.id == "k1")) == expected

    def test_title_card_uses_source_meta(self) -> None:
        deck = _deck_with_media()
        card = title_card_for(deck, deck.slides[3])
        assert (card.publisher, card.date, card.source_id) == ("經濟日報", "2026-07-17", "s1")
        assert card.headline == "年報" and card.domain == "money.udn.com"
        html = title_card_html(deck, deck.sections[2], deck.slides[3], 4)
        assert "經濟日報" in html and 'data-animation="title_card"' in html
        assert "非新聞截圖" in html and "資料截至 2026-10" in html

    def test_title_card_placeholders_when_meta_missing(self) -> None:
        data = deck_dict()
        data["sections"][2]["slides"][0]["media"] = {"kind": "title_card", "source_id": "s1",
                                                     "headline": "自訂標題"}
        data["sources"][0]["url"] = ""
        deck = Deck.model_validate(data)
        card = title_card_for(deck, deck.slides[3])
        assert (card.publisher, card.date, card.headline) == ("媒體待補", "日期待補", "自訂標題")

    def test_overlay_is_transparent_and_keeps_meta(self) -> None:
        deck = _deck_with_media()
        html = overlay_html(deck, deck.sections[1], deck.slides[2], 3)
        assert "media-overlay" in html and "lower-third" in html
        assert "資料截至 2026-10" in html and "<script>" not in html


class TestPlacement:
    def test_place_files_keeps_each_suffix(self, tmp_path: Path) -> None:
        clips = plan_slide_timeline([1.5, 2.25])
        png = _png(tmp_path / "a.png", "red", (8, 8))
        mp4 = tmp_path / "b.mp4"
        mp4.write_bytes(b"x")
        placed = place_files(clips, [png, mp4], tmp_path / "visual")
        assert [p.name for p in placed] == ["00:00.000~00:01.500.png", "00:01.500~00:03.750.mp4"]
        scanned = scan_timeline_clips(tmp_path / "visual")
        assert [c.is_image for c in scanned] == [True, False]
        assert scanned[1].start_seconds == pytest.approx(1.5)

    def test_place_files_refuses_mix_without_replace(self, tmp_path: Path) -> None:
        clips = plan_slide_timeline([1.0])
        src = _png(tmp_path / "a.png", "red", (8, 8))
        place_files(clips, [src], tmp_path / "visual")
        with pytest.raises(TimelineError, match="--replace"):
            place_files(clips, [src], tmp_path / "visual")
        assert len(place_files(clips, [src], tmp_path / "visual", replace=True)) == 1

    def test_count_mismatch(self, tmp_path: Path) -> None:
        with pytest.raises(TimelineError, match="2 clips but 1 files"):
            place_files(plan_slide_timeline([1, 1]), [tmp_path / "a.png"], tmp_path / "v")

    def test_slide_clip_seconds(self) -> None:
        assert SlideClip(index=1, start_ms=1000, end_ms=3500).seconds == 2.5


def _result(i: int, requested: str, used: str, path: Path, credit: dict | None = None) -> ClipResult:
    return ClipResult(index=i, slide_id=f"s{i}", requested=requested, used=used, path=path,
                      seconds=1.0, credit=credit)


class TestRunHelpers:
    def test_options_validation(self) -> None:
        with pytest.raises(ValueError):
            MediaOptions(transition="wipe")
        with pytest.raises(ValueError):
            MediaOptions(transition_seconds=2.0)
        assert MediaOptions(transition="none").transition == "none"

    def test_no_transition_passes_clips_through(self, tmp_path: Path) -> None:
        results = [_result(1, "slide", "slide", tmp_path / "a.png"),
                   _result(2, "stock", "stock", tmp_path / "b.mp4")]
        finals = apply_transitions(results, tmp_path, MediaOptions(transition="none"))
        assert finals == [tmp_path / "a.png", tmp_path / "b.mp4"]

    def test_credits_text(self) -> None:
        entries = [{"kind": "stock", "provider": "pexels", "author": "Ann",
                    "source_url": "https://www.pexels.com/video/1/", "license": "Pexels License"},
                   {"kind": "ai_image", "file": "s04.png"}]
        text = credits_text(entries)
        assert "Ann on Pexels: https://www.pexels.com/video/1/ (Pexels License)" in text
        assert "Videos provided by Pexels" in text and "Pixabay" not in text
        assert credits_text([]) == ""

    def test_report_flags_fallback_and_placeholder(self, tmp_path: Path) -> None:
        results = [_result(1, "stock", "animated", tmp_path / "a.mp4"),
                   _result(2, "ai_image", USED_PLACEHOLDER, tmp_path / "b.mp4"),
                   _result(3, "slide", "slide", tmp_path / "c.png")]
        path = write_report(results, [r.path for r in results], MediaOptions(), tmp_path / "r.json")
        rows = json.loads(path.read_text())["slides"]
        assert [r["fallback"] for r in rows] == [True, None, None]
        assert [r["placeholder"] for r in rows] == [None, True, None]

    def test_contact_sheet_from_pngs(self, tmp_path: Path) -> None:
        results = [_result(i, "slide", USED_PLACEHOLDER if i == 2 else "slide",
                           _png(tmp_path / f"{i}.png", "gray")) for i in range(1, 4)]
        sheet = media_contact_sheet(results, tmp_path / "sheet.png", tmp_path / "frames")
        with Image.open(sheet) as im:
            # placeholder thumbnail (2nd) is framed in red
            assert im.getpixel((24 + 560 + 24 - 2, 40))[0] > 200
