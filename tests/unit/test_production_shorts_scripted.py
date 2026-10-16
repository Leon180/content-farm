"""Scripted Shorts (policy review 2026-10, C2): beats, script, runner wiring, motion QC, layout math."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from content_farm.explainer.deck import load_deck
from content_farm.explainer.to_script import deck_to_script
from content_farm.production import qc
from content_farm.production import runner as runner_mod
from content_farm.production import shorts_cut as cut
from content_farm.production import shorts_scripted_render as render
from content_farm.production.channels import load_channel
from content_farm.production.runner import Outcome, Runner
from content_farm.production.shorts_scripted import ShortBeat, check_beats
from content_farm.production.state import Decision, load_state, save_state
from content_farm.production.steps import SHORTS_SCRIPTED_STEPS, Command, Context, RunOptions, step_names

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos"
BEATS = json.loads((Path(__file__).resolve().parents[2] / "docs" / "launch-fixes" / "chipcat-7722-beats.json")
                   .read_text(encoding="utf-8"))


def _beats() -> tuple[ShortBeat, ...]:
    return tuple(ShortBeat.model_validate(beat) for beat in BEATS["beats"])


def _long_run(tmp_path: Path) -> Path:
    long_dir = tmp_path / "long"
    (long_dir / "subtitles").mkdir(parents=True)
    shutil.copy(EXAMPLE / "deck.json", long_dir / "deck.json")
    (long_dir / "script.json").write_text(deck_to_script(load_deck(long_dir / "deck.json")).model_dump_json())
    (long_dir / "subtitles" / "subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n句子\n")
    save_state(long_dir, load_state(long_dir, "chipcat").with_decision(
        Decision("deck", "approved", "f" * 16, "2026-10-15T00:00:00+00:00")))
    return long_dir


def _spec(long_dir: Path, **overrides: object) -> cut.ShortSpec:
    fields = {"long_run_dir": str(long_dir), "slide_id": "s09", "number": "7,722", "unit": "mm²",
              "caption": "9 倍光罩中介層面積", "title": "7,722 平方毫米有多大", "long_channel": "晶片貓",
              "long_title": "AI 晶片卡在哪一關？", "beats": _beats(), "answer": BEATS["answer"]}
    return cut.ShortSpec(**{**fields, **overrides})


def test_the_7722_beats_hook_first_say_the_answer_and_end_on_the_full_video() -> None:
    beats = _beats()
    assert check_beats(beats, BEATS["answer"]) == []
    assert beats[0].visual == "number" and beats[-1].visual == "outro"
    assert "超級載板" not in json.dumps(BEATS, ensure_ascii=False)


def test_beat_checks_catch_a_missing_answer_and_a_misplaced_outro() -> None:
    beats = _beats()
    problems = check_beats(beats[::-1], "8.8 乘 8.8 公分")
    assert any("hook" in p for p in problems) and any("outro" in p for p in problems)
    assert any("never spoken" in p for p in check_beats(beats, "10 公分"))


def test_visuals_require_their_fields() -> None:
    with pytest.raises(ValidationError, match="side_cm"):
        ShortBeat(narration="一片晶圓排得下五片。", visual="wafer", count=5)
    with pytest.raises(ValidationError, match="items"):
        ShortBeat(narration="一張、兩張、三張光罩。", visual="grow")


def test_scripted_spec_switches_the_runner_to_script_gate_then_voice(tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_mod, "LOCK_PATH", tmp_path / "render.lock")
    chipcat = load_channel("chipcat")
    run_dir = tmp_path / "short"
    cut.write_spec(run_dir, _spec(_long_run(tmp_path)))
    assert step_names(chipcat, run_dir) == tuple(s.name for s in SHORTS_SCRIPTED_STEPS)
    calls: list[str] = []

    def fake(command: Command, log_path: Path) -> int:
        calls.append(Path(command.argv[1]).name)
        return 0

    result = Runner(Context(chipcat, run_dir, RunOptions()), executor=fake, log=lambda _: None).run()
    assert result.outcome is Outcome.GATE and result.step == "gate_script" and calls == []
    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    assert [s["narration"] for s in script["scenes"]] == [b["narration"] for b in BEATS["beats"]]
    assert script["orientation"] == "portrait" and script["video_title"].endswith("#Shorts")


def test_classic_spec_keeps_the_cut_steps(tmp_path: Path) -> None:
    run_dir = tmp_path / "short"
    cut.write_spec(run_dir, _spec(tmp_path, beats=(), answer=""))
    assert step_names(load_channel("chipcat"), run_dir)[0] == "cut"


def test_wafer_layout_places_the_requested_squares_inside_the_wafer() -> None:
    px_per_mm = 760 / 300
    slots = render.wafer_slots(87.9, 5, px_per_mm)
    assert len(slots) == 5
    half = 87.9 * px_per_mm / 2
    radius = (150 - 3) * px_per_mm
    for x, y in slots:
        corners = [(x + dx, y + dy) for dx in (-half, half) for dy in (-half, half)]
        assert all((cx * cx + cy * cy) ** 0.5 <= radius + 1 for cx, cy in corners)
    assert len(render.wafer_slots(87.9, 9, px_per_mm)) == 5  # control: only 5 fit, never more


def test_grow_blocks_scale_with_area() -> None:
    sizes = render.grow_sizes(("1 張光罩", "3.3 倍", "9 倍"), largest_px=900)
    assert sizes[-1] == 900 and sizes[0] == 300 and sizes[0] < sizes[1] < sizes[2]


@pytest.mark.parametrize(("visual", "seconds", "limit_ok"), [
    ("number", 4.62, True), ("number", 9.0, False), ("grow", 7.5, True), ("outro", 6.0, False)])
def test_hold_seconds_against_the_three_second_rule(visual: str, seconds: float, limit_ok: bool) -> None:
    beat = next(b for b in _beats() if b.visual == visual)
    assert (render.hold_seconds(beat, seconds) <= 3.0) is limit_ok


def test_short_motion_qc(tmp_path: Path) -> None:
    (tmp_path / "short").mkdir()
    report = {"max_step_seconds": 3.0, "beats": [{"beat": 1, "visual": "number", "longest_hold": 2.1},
                                                 {"beat": 2, "visual": "outro", "longest_hold": 4.0}]}
    (tmp_path / "short" / "beat_report.json").write_text(json.dumps(report), encoding="utf-8")
    finding = qc.short_motion_findings(tmp_path)[0]
    assert finding.level == "error" and "beat 2 outro" in finding.message
    report["beats"][1]["longest_hold"] = 2.5
    (tmp_path / "short" / "beat_report.json").write_text(json.dumps(report), encoding="utf-8")
    assert qc.short_motion_findings(tmp_path)[0].level == "ok"
    assert qc.short_motion_findings(tmp_path / "nothing") == []  # not a scripted Short: no check
