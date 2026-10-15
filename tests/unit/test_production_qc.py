"""QC checks and upload metadata."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from content_farm.explainer.deck import Deck, load_deck
from content_farm.explainer.to_script import deck_to_script
from content_farm.production import publish, qc
from content_farm.production.channels import load_channel

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_policy_blocks_stock_on_yokai_but_not_chipcat() -> None:
    deck = load_deck(EXAMPLE / "deck.json")
    assert qc.policy_findings(load_channel("chipcat"), deck)[0].level == "ok"
    finding = qc.policy_findings(load_channel("yokai"), deck)[0]
    assert finding.level == "error" and "stock" in finding.message


def test_policy_allows_artwork_only_where_the_channel_does() -> None:
    data = json.loads((EXAMPLE / "deck.json").read_text(encoding="utf-8"))
    slide = data["sections"][0]["slides"][0]
    slide["media"] = {"kind": "artwork", "artwork": "tamamo"}
    for section in data["sections"]:
        for other in section["slides"]:
            if other is not slide and (other.get("media") or {}).get("kind") == "stock":
                other["media"] = None
    deck = Deck.model_validate(data)
    assert qc.policy_findings(load_channel("yokai"), deck)[0].level == "ok"
    finding = qc.policy_findings(load_channel("chipcat"), deck)[0]
    assert finding.level == "error" and "artwork" in finding.message


def test_credits_pending_and_missing_fields_are_errors() -> None:
    chipcat = load_channel("chipcat")
    credits = {"entries": [{"slide_id": "s16", "kind": "stock", "license": "Pexels", "source_url": ""}],
               "pending": [{"slide_id": "s01", "kind": "ai_image"}]}
    checks = {f.check: f.level for f in qc.credits_findings(chipcat, credits)}
    assert checks == {"credits_pending": "error", "credits_fields": "error"}
    assert qc.credits_findings(chipcat, None)[0].level == "error"
    clean = {"entries": [{"slide_id": "s16", "kind": "stock", "license": "Pexels",
                          "source_url": "https://pexels.com/v/1"}], "pending": []}
    assert [f.level for f in qc.credits_findings(chipcat, clean)] == ["ok"]


@pytest.mark.parametrize(("licence", "url", "ok"), [
    ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/", True),
    ("CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/", False),
    ("Public domain", "", False),
])
def test_artwork_licence_must_allow_commercial_use(licence: str, url: str, ok: bool) -> None:
    credits = {"entries": [{"slide_id": "s02", "kind": "artwork", "license": licence,
                            "license_url": url}], "pending": []}
    levels = {f.level for f in qc.credits_findings(load_channel("yokai"), credits)}
    assert (levels == {"ok"}) is ok


def test_format_findings() -> None:
    chipcat = load_channel("chipcat")
    streams = {"streams": [{"codec_type": "video", "width": 1920, "height": 1080, "duration": "503.2"},
                           {"codec_type": "audio", "duration": "504.6"}]}
    assert {f.check: f.level for f in qc.format_findings(chipcat, streams)} == {
        "resolution": "ok", "duration": "ok", "av_drift": "ok"}
    short = {"streams": [{"codec_type": "video", "width": 1080, "height": 1920, "duration": "30"},
                         {"codec_type": "audio", "duration": "35"}]}
    levels = {f.check: f.level for f in qc.format_findings(chipcat, short)}
    assert levels == {"resolution": "error", "duration": "warn", "av_drift": "warn"}
    assert qc.format_findings(chipcat, {"streams": []})[0].level == "error"


@needs_ffmpeg
def test_blackdetect_finds_black_and_passes_colour(tmp_path: Path) -> None:
    black, colour = tmp_path / "black.mp4", tmp_path / "colour.mp4"
    for path, src in ((black, "color=black:s=320x180:d=1.5"), (colour, "color=0x3366cc:s=320x180:d=1.5")):
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", src, "-pix_fmt", "yuv420p",
                        str(path)], check=True)
    assert qc.black_findings(qc.black_segments(black))[0].level == "error"  # control: detector fires
    assert qc.black_findings(qc.black_segments(colour))[0].level == "ok"


@needs_ffmpeg
def test_short_cut_on_a_long_channel_is_judged_as_a_short(tmp_path: Path) -> None:
    """88093246da75: the 7,722 Short moved to chipcat (16:9 long channel); 1080x1920 is right."""
    from content_farm.production import shorts_cut

    run = tmp_path / "run"
    (run / "assembly").mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=0x3366cc:s=1080x1920:d=20",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "20", "-pix_fmt", "yuv420p",
                    "-shortest", str(run / "assembly" / "final.mp4")], check=True)
    chipcat = load_channel("chipcat")

    def resolution() -> str:
        report = qc.run_qc(run, chipcat, None)
        return next(f for f in report["findings"] if f["check"] == "resolution")["level"]

    assert resolution() == "error"  # control: without short_source.json it is a 16:9 long video
    shorts_cut.write_spec(run, shorts_cut.ShortSpec(
        long_run_dir=str(tmp_path), slide_id="s09", number="7,722", caption="c", title="t",
        long_channel="晶片貓", long_title="CoWoS"))
    assert resolution() == "ok"
    report = qc.run_qc(run, chipcat, None)
    assert next(f for f in report["findings"] if f["check"] == "duration")["level"] == "ok"


def _script_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "assembly").mkdir(parents=True)
    (run / "assembly" / "final.mp4").write_bytes(b"x")
    (run / "assembly" / "draft.mp4").write_bytes(b"x")
    script = deck_to_script(load_deck(EXAMPLE / "deck.json"))
    (run / "script.json").write_text(script.model_dump_json(), encoding="utf-8")
    (run / "credits.json").write_text(json.dumps({"entries": [], "pending": [],
                                                  "description_text": "影片素材 / Stock footage:\n• Pexels"}))
    return run


def test_meta_uses_final_video_credits_chapters_and_schedule(tmp_path: Path) -> None:
    run = _script_run(tmp_path)
    when = datetime(2026, 10, 22, 19, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    meta = publish.build_meta(load_channel("chipcat"), run, publish_at=when)
    assert meta["video_path"] == "assembly/final.mp4"
    assert meta["privacy_status"] == "private" and meta["publish_at"] == "2026-10-22T19:00:00+08:00"
    assert meta["contains_synthetic_media"] is False  # Studio checkbox off (916c2864e31f)
    assert meta["description"].startswith("章節：\n0:00 ")
    assert "影片素材 / Stock footage:" in meta["description"]
    assert publish.AI_DISCLOSURE_VOICE_LINE in meta["description"]  # no AI illustration credited
    assert len(meta["chapters"]) == 6 and meta["chapters"][0]["timestamp"] == "0:00"


def test_ai_images_follow_credits_then_deck_then_assume_yes(tmp_path: Path) -> None:
    # chipcat + yokai regression: the line claimed 「部分插圖」 on videos with no AI image.
    assert not publish.uses_ai_images(tmp_path, {"entries": [{"kind": "stock"}], "pending": []})
    assert not publish.uses_ai_images(tmp_path, {"entries": [{"kind": "artwork"}], "pending": []})
    assert publish.uses_ai_images(tmp_path, {"entries": [{"kind": "ai_image"}]})
    assert publish.uses_ai_images(tmp_path, {"pending": [{"kind": "ai_image"}]})  # placeholder still counts
    assert publish.uses_ai_images(tmp_path, None)  # nothing recorded → do not under-disclose
    deck = {"sections": [{"slides": [{"media": {"kind": "stock"}}, {"media": None}]}]}
    (tmp_path / "deck.json").write_text(json.dumps(deck), encoding="utf-8")
    assert not publish.uses_ai_images(tmp_path, None)
    deck["sections"][0]["slides"][1]["media"] = {"kind": "ai_image"}
    (tmp_path / "deck.json").write_text(json.dumps(deck), encoding="utf-8")
    assert publish.uses_ai_images(tmp_path, None)


def test_synthetic_voice_follows_the_voice_log(tmp_path: Path) -> None:
    assert publish.uses_synthetic_voice(tmp_path)  # no log → assumed TTS
    (tmp_path / "logs").mkdir()
    log = tmp_path / "logs" / "voice.log"
    log.write_text("x content_farm.voice.fish_audio INFO Fish Audio TTS: 1 bytes -> a.mp3\n", encoding="utf-8")
    assert publish.uses_synthetic_voice(tmp_path)
    log.write_text("$ voice\n(audio supplied by hand)\n", encoding="utf-8")
    assert not publish.uses_synthetic_voice(tmp_path)


def test_ai_disclosure_line_names_only_what_is_there() -> None:
    line = publish.ai_disclosure_line
    assert line(publish.SyntheticContent(voice=True, images=True)) == publish.AI_DISCLOSURE_LINE
    assert line(publish.SyntheticContent(voice=True, images=False)) == publish.AI_DISCLOSURE_VOICE_LINE
    assert line(publish.SyntheticContent(voice=False, images=True)) == publish.AI_DISCLOSURE_IMAGE_LINE
    assert line(publish.SyntheticContent(voice=False, images=False)) is None
    assert "插圖" not in publish.AI_DISCLOSURE_VOICE_LINE


def test_meta_disclosure_for_a_stock_only_run_without_tts(tmp_path: Path) -> None:
    """The cel EP1 case: stock B-roll only. With TTS → voice-only line; without → no line, flag off."""
    run = _script_run(tmp_path)
    (run / "logs").mkdir()
    (run / "logs" / "voice.log").write_text(
        "x content_farm.voice.macos_say INFO macOS say TTS: 1 bytes -> a.mp3\n", encoding="utf-8")
    meta = publish.build_meta(load_channel("cel"), run)
    assert publish.AI_DISCLOSURE_VOICE_LINE in meta["description"] and "部分插圖" not in meta["description"]
    assert meta["contains_synthetic_media"] is False
    (run / "logs" / "voice.log").write_text("$ voice\n", encoding="utf-8")
    meta = publish.build_meta(load_channel("cel"), run)
    assert "AI 輔助製作" not in meta["description"] and meta["contains_synthetic_media"] is False


def test_studio_label_and_description_disclosure_are_separate_switches(tmp_path: Path) -> None:
    """916c2864e31f: Studio 「變造或合成內容」 unchecked, the description still discloses."""
    run = _script_run(tmp_path)
    chipcat = load_channel("chipcat")
    assert chipcat.youtube.ai_disclosure and not chipcat.youtube.altered_content_label
    meta = publish.build_meta(chipcat, run)
    assert meta["contains_synthetic_media"] is False and publish.DISCLOSURE_MARK in meta["description"]
    labelled = chipcat.model_copy(update={"youtube": chipcat.youtube.model_copy(
        update={"altered_content_label": True})})
    assert publish.build_meta(labelled, run)["contains_synthetic_media"] is True
    silent = chipcat.model_copy(update={"youtube": chipcat.youtube.model_copy(
        update={"ai_disclosure": False, "altered_content_label": True})})
    meta = publish.build_meta(silent, run)
    assert publish.DISCLOSURE_MARK not in meta["description"] and meta["contains_synthetic_media"] is True


def test_chapters_follow_measured_durations(tmp_path: Path) -> None:
    run = _script_run(tmp_path)
    data = json.loads((run / "script.json").read_text(encoding="utf-8"))
    for scene in data["scenes"]:
        scene["duration_seconds"] = 20.0
    (run / "script.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    meta = publish.build_meta(load_channel("chipcat"), run)
    first_scenes_in_ch2 = sum(1 for s in data["scenes"] if s["chapter_number"] == 1)
    assert meta["chapters"][1]["timestamp"] == publish._format_timestamp(20.0 * first_scenes_in_ch2)
    assert meta["publish_at"] is None and meta["privacy_status"] == "private"


def test_chapter_block_rejects_short_or_few_chapters() -> None:
    assert publish.chapter_block([(0, "a"), (60, "b")], 120) == []
    assert publish.chapter_block([(0, "a"), (5, "b"), (60, "c")], 120) == []
    assert publish.chapter_block([(1, "a"), (60, "b"), (90, "c")], 120) == []
    assert publish.chapter_block([(0, "a"), (60, "b"), (90, "c")], 120)[1] == "0:00 a"


def test_naive_publish_time_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone"):
        publish.build_meta(load_channel("chipcat"), _script_run(tmp_path), publish_at=datetime(2026, 10, 22))
