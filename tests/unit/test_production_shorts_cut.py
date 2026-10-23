"""Short from a long run (R5): timing, subtitle re-layout, script, spec, runner wiring, QC."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from content_farm.assembly.drawtext import find_cjk_font
from content_farm.explainer.deck import load_deck
from content_farm.explainer.to_script import deck_to_script
from content_farm.production import qc
from content_farm.production import runner as runner_mod
from content_farm.production import shorts_cut as cut
from content_farm.production.channels import Gate, load_channel
from content_farm.production.runner import Outcome, Runner, decide
from content_farm.production.shorts_render import ass_text, page_html
from content_farm.production.state import Decision, load_state, save_state
from content_farm.production.steps import SHORTS_CUT_STEPS, Command, Context, RunOptions, step_names

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos"
needs_font = pytest.mark.skipif(find_cjk_font() is None, reason="no CJK font")


def _spec(long_dir: Path, **overrides: object) -> cut.ShortSpec:
    fields = {"long_run_dir": str(long_dir), "slide_id": "s09", "number": "7,722", "unit": "mm²",
              "caption": "台積電規劃的超級載板可用面積", "title": "7,722 平方毫米有多大", "long_channel": "晶片貓",
              "long_title": "AI 晶片卡在哪一關？"}
    return cut.ShortSpec(**{**fields, **overrides})


# --- timing -----------------------------------------------------------------------------------

def test_scene_window_is_back_to_back() -> None:
    assert cut.scene_window([10.0, 5.0, 7.5], 1) == (0.0, 10.0)
    assert cut.scene_window([10.0, 5.0, 7.5], 3) == (15.0, 22.5)
    with pytest.raises(ValueError, match="out of range"):
        cut.scene_window([10.0], 2)


def test_scene_durations_prefer_the_measured_audio_over_stale_script_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from content_farm.script_gen.schemas import Script

    class _Scene:
        def __init__(self, seconds: float) -> None:
            self.duration_seconds = seconds

    monkeypatch.setattr(Script, "model_validate_json", classmethod(lambda cls, text: type("S", (), {"scenes": [_Scene(23.0), _Scene(17.0)]})()))
    (tmp_path / "script.json").write_text("{}", encoding="utf-8")
    assert cut.scene_durations(tmp_path) == [23.0, 17.0]                  # no audio files: the script's values
    (tmp_path / "audio").mkdir()
    for number in (1, 2):
        (tmp_path / "audio" / f"scene_{number:03d}.mp3").write_bytes(b"x")
    monkeypatch.setattr(cut, "_audio_seconds", lambda path: {"scene_001.mp3": 29.0, "scene_002.mp3": 21.5}[path.name])
    assert cut.scene_durations(tmp_path) == [29.0, 21.5]                  # measured wins when every scene has audio


def test_plan_timing_overlaps_intro_with_narration_and_caps_length() -> None:
    timing = cut.plan_timing(22.15, 1.5, 2.5)
    assert (timing.intro, round(timing.body, 2), timing.outro) == (1.5, 20.65, 2.5)
    assert round(timing.total, 2) == 24.65  # intro plays over the narration, outro after it
    with pytest.raises(ValueError, match="limit 60"):
        cut.plan_timing(58.0, 1.5, 2.5)
    with pytest.raises(ValueError, match="not longer"):
        cut.plan_timing(1.0, 1.5, 2.5)


# --- subtitles --------------------------------------------------------------------------------

def test_cues_in_window_shifts_clips_and_tolerates_early_alignment() -> None:
    cues = [cut.Cue(9.0, 10.0, "前一段"), cut.Cue(9.8, 12.0, "早了一點"), cut.Cue(14.0, 21.0, "跨出邊界"),
            cut.Cue(20.0, 22.0, "下一段")]
    picked = cut.cues_in_window(cues, 10.0, 20.0)
    assert [c.text for c in picked] == ["早了一點", "跨出邊界"]
    assert picked[0].start == 0.0 and picked[1].end == 10.0
    with pytest.raises(ValueError, match="no subtitle cue"):
        cut.cues_in_window(cues, 30.0, 40.0)


def test_relayout_wraps_for_portrait_without_splitting_numbers() -> None:
    cues = cut.relayout([cut.Cue(0, 3, "要做更大的中介層，就得把好幾張拼起來印。"),
                         cut.Cue(3, 5, "可用面積 7,722 平方毫米。")])
    assert all(len(line) <= cut.SUB_MAX_CHARS + 4 for c in cues for line in c.text.split("\n"))
    assert cues[0].text == "要做更大的中介層，\n就得把好幾張拼起來印。"
    assert "7,722" in cues[1].text.replace("\n", "")
    assert not any(line.endswith("7,") for c in cues for line in c.text.split("\n"))


@needs_font
def test_relayout_output_passes_the_portrait_width_check(tmp_path: Path) -> None:
    # Regression: wrap_text kept this 16-char line whole (punctuation allowance) and it overflowed.
    cues = cut.relayout([cut.Cue(0, 2.3, "就像影印機一次只能印一張 A4。")])
    assert all(len(line) <= cut.SUB_MAX_CHARS + 1 for c in cues for line in c.text.split("\n"))
    srt = tmp_path / "s.srt"
    srt.write_text(cut.to_srt(cues), encoding="utf-8")
    assert qc.portrait_subtitle_findings(srt)[0].level == "ok"


def test_relayout_splits_tall_cues_in_time_and_keeps_the_span() -> None:
    long_text = "一二三四五六七八九十，一二三四五六七八九十，一二三四五六七八九十，一二三四五六七八九十。"
    cues = cut.relayout([cut.Cue(2.0, 10.0, long_text)])
    assert len(cues) == 2 and all(c.text.count("\n") <= 1 for c in cues)
    assert cues[0].start == 2.0 and cues[-1].end == 10.0 and cues[0].end == cues[1].start


def test_srt_round_trip() -> None:
    cues = [cut.Cue(0.0, 1.25, "第一句"), cut.Cue(61.5, 63.0, "兩行\n字幕")]
    assert cut.parse_cues(cut.to_srt(cues)) == cues


# --- script & spec ----------------------------------------------------------------------------

def test_short_script_is_one_portrait_scene_with_the_slide_sources() -> None:
    deck = load_deck(EXAMPLE / "deck.json")
    slide = next(s for s in deck.slides if s.id == "s09")
    script = cut.short_script(deck_to_script(deck), deck, slide, _spec(Path("/tmp/long")),
                              cut.plan_timing(22.0, 1.5, 2.5))
    assert script.video_title == "7,722 平方毫米有多大 #Shorts"
    assert len(script.scenes) == 1 and script.scenes[0].narration == slide.narration
    assert script.scenes[0].duration_seconds == 24.5 and script.chapters == ()
    assert script.orientation.value == "portrait" and "#Shorts" in script.description
    assert len(script.sources) == len(slide.source_ids) == 1 and "http" in script.sources[0]
    assert script.tags[0] == "Shorts"


def test_shorts_title_appends_hashtag_once() -> None:
    assert cut.shorts_title("數字") == "數字 #Shorts"
    assert cut.shorts_title("數字 #shorts") == "數字 #shorts"


def test_spec_rejects_relative_long_dir() -> None:
    with pytest.raises(ValueError, match="absolute"):
        _spec(Path("relative/run"))


def _long_run(tmp_path: Path, approved: bool = True) -> Path:
    long_dir = tmp_path / "long"
    (long_dir / "subtitles").mkdir(parents=True)
    shutil.copy(EXAMPLE / "deck.json", long_dir / "deck.json")
    (long_dir / "script.json").write_text(deck_to_script(load_deck(long_dir / "deck.json")).model_dump_json())
    (long_dir / "subtitles" / "subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n句子\n")
    state = load_state(long_dir, "chipcat")
    if approved:
        state = state.with_decision(Decision("deck", "approved", "f" * 16, "2026-10-15T00:00:00+00:00"))
    save_state(long_dir, state)
    return long_dir


def test_spec_from_long_defaults_to_the_big_number_and_needs_an_approved_deck(tmp_path: Path) -> None:
    chipcat = load_channel("chipcat")
    options = {"slide": "s09", "title": "t"}
    spec = cut.short_spec_from_long(_long_run(tmp_path), chipcat, options)
    assert (spec.number, spec.unit, spec.long_channel) == ("9", "倍光罩", "晶片貓")
    spec = cut.short_spec_from_long(tmp_path / "long", chipcat, {**options, "number": "7,722", "unit": "mm²"})
    assert (spec.number, spec.unit) == ("7,722", "mm²")
    with pytest.raises(ValueError, match="not a big_number"):
        cut.short_spec_from_long(tmp_path / "long", chipcat, {"slide": "s04", "title": "t"})
    with pytest.raises(ValueError, match="not approved"):
        cut.short_spec_from_long(_long_run(tmp_path / "b", approved=False), chipcat, options)


# --- runner wiring ----------------------------------------------------------------------------

def test_short_run_dir_uses_the_cut_steps_and_only_the_final_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_mod, "LOCK_PATH", tmp_path / "render.lock")
    offwork = load_channel("offwork")
    run_dir = tmp_path / "short"
    assert "skit_script" in step_names(offwork, run_dir)  # no spec yet → the channel's own pipeline
    cut.write_spec(run_dir, _spec(tmp_path))
    assert step_names(offwork, run_dir) == tuple(s.name for s in SHORTS_CUT_STEPS)

    calls: list[str] = []

    def fake(command: Command, log_path: Path) -> int:
        calls.append(Path(command.argv[1]).name)
        for name in ("assembly/final.mp4", "script.json", "subtitles/subtitles.srt"):
            (run_dir / name).parent.mkdir(parents=True, exist_ok=True)
            (run_dir / name).write_text("x", encoding="utf-8")
        return 0

    result = Runner(Context(offwork, run_dir, RunOptions(panels=False)), executor=fake, log=lambda _: None).run()
    assert calls == ["short_from_long.py"]
    assert result.outcome is Outcome.GATE and result.step == "gate_final"
    with pytest.raises(ValueError, match="override"):  # a manual approval is the panel back door
        decide(run_dir, offwork, Gate.FINAL, "approved")
    with pytest.raises(ValueError, match="no gate 'script'"):
        decide(run_dir, offwork, Gate.SCRIPT, "approved")


# --- QC & rendering helpers -------------------------------------------------------------------

def test_short_on_a_landscape_channel_is_checked_as_a_short(tmp_path: Path) -> None:
    chipcat = load_channel("chipcat")  # 16:9, 420-660 s
    run_dir = tmp_path / "short"
    assert qc.qc_channel(run_dir, chipcat) is chipcat  # not a cut: the channel's own format
    cut.write_spec(run_dir, _spec(tmp_path))
    checked = qc.qc_channel(run_dir, chipcat)
    assert (checked.format.aspect, checked.format.target_seconds) == ("9:16", (1, 60))
    assert checked.media == chipcat.media and chipcat.format.aspect == "16:9"  # copy, original untouched
    streams = {"streams": [{"codec_type": "video", "width": 1080, "height": 1920, "duration": "21.1"},
                           {"codec_type": "audio", "duration": "21.1"}]}
    levels = {f.check: f.level for f in qc.format_findings(checked, streams)}
    assert levels == {"resolution": "ok", "duration": "ok", "av_drift": "ok"}
    assert {f.check: f.level for f in qc.format_findings(chipcat, streams)}["resolution"] == "error"


@needs_font
def test_portrait_subtitle_check_flags_wide_and_tall_cues(tmp_path: Path) -> None:
    srt = tmp_path / "s.srt"
    srt.write_text(cut.to_srt([cut.Cue(0, 1, "可用面積 7,722 平方毫米。")]), encoding="utf-8")
    assert qc.portrait_subtitle_findings(srt)[0].level == "ok"
    srt.write_text(cut.to_srt([cut.Cue(0, 1, "這一行字幕實在是太長了一定會超出畫面的邊界喔")]), encoding="utf-8")
    assert "wider" in qc.portrait_subtitle_findings(srt)[0].message
    srt.write_text(cut.to_srt([cut.Cue(0, 1, "一\n二\n三")]), encoding="utf-8")
    assert "over 2 lines" in qc.portrait_subtitle_findings(srt)[0].message


def test_pages_escape_text_and_carry_the_brand() -> None:
    offwork = load_channel("offwork")
    spec = _spec(Path("/tmp/long"), caption="<b>載板</b>")
    body = page_html("body", spec, offwork, "來源：IFTLE")
    assert "&lt;b&gt;載板&lt;/b&gt;" in body and "<b>載板" not in body
    assert 'data-target="7,722"' in body and "--bg: #ffd84d" in body  # offwork tokens
    assert "完整" in page_html("outro", spec, offwork, "") and "這是多大" in page_html("intro", spec, offwork, "")


def test_ass_events_use_portrait_play_res_and_ass_line_breaks() -> None:
    text = ass_text([cut.Cue(0.0, 1.5, "兩行\n字幕{x}")], "Font")
    assert "PlayResX: 1080" in text and "PlayResY: 1920" in text
    assert "Dialogue: 0,0:00:00.00,0:00:01.50,Default,,0,0,0,,兩行\\N字幕(x)" in text
    assert json.dumps(cut.SUB_MARGIN_V) in text
