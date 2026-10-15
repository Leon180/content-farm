"""QC checks and upload metadata."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from content_farm.explainer.deck import load_deck
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
    assert meta["contains_synthetic_media"] is True
    assert meta["description"].startswith("章節：\n0:00 ")
    assert "影片素材 / Stock footage:" in meta["description"]
    assert publish.AI_DISCLOSURE_VOICE_LINE in meta["description"]  # no AI illustration credited
    assert len(meta["chapters"]) == 6 and meta["chapters"][0]["timestamp"] == "0:00"


def test_ai_disclosure_mentions_illustrations_only_when_present() -> None:
    assert publish.ai_disclosure_line(None) == publish.AI_DISCLOSURE_VOICE_LINE
    assert publish.ai_disclosure_line({"entries": [{"kind": "stock"}], "pending": []}) == \
        publish.AI_DISCLOSURE_VOICE_LINE
    assert publish.ai_disclosure_line({"entries": [{"kind": "ai_image"}]}) == publish.AI_DISCLOSURE_LINE
    assert publish.ai_disclosure_line({"pending": [{"kind": "ai_image"}]}) == publish.AI_DISCLOSURE_LINE


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
