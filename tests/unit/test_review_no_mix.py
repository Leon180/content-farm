"""A channel without ``audio.enabled`` is judged without the BGM / ducking standard, and a ``mix`` fix on it is
a channel-config matter (listed, not routed). Plus ``produce.py new-cycle`` (archive used-up panel rounds)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.evaluation.aggregate import column_scores, objective_checks
from content_farm.production.panel_flow import new_stage_cycle
from content_farm.review.gate import _rework
from content_farm.review.materials_video import audio_mix_enabled


def _objective(bgm_under: float | None) -> dict:
    window = {"rate": 4.5, "bgm_under_voice_db": bgm_under}
    return {
        "dead_zones": [],
        "content": {"first_hook": 5, "max_gap": 6, "rehook_gaps": [], "chapter_teases": []},
        "visual": {"longest_still": 3, "still_max": 8, "blanks": [], "held_blends": [], "sync": [],
                   "subtitle": {"height_pct": 5.5, "box": True}, "density": {"dense_pages": []}, "cuts_per_minute": 8},
        "audio": {"integrated": -14.0, "true_peak": -2.0, "clipped_samples": 0, "pitch_spread_st": 2.0,
                  "ducking_db": None, "dead_air": [], "windows": [window], "speech_check": {"mean_cer": 0.02}},
    }


def _run_dir(tmp_path: Path, channel: str) -> Path:
    (tmp_path / "production.json").write_text(json.dumps({"channel": channel}), encoding="utf-8")
    (tmp_path / "review").mkdir()
    return tmp_path


def test_a_bgm_free_cut_is_red_on_audio_only_when_the_channel_mixes():
    mixed = column_scores(objective_checks(_objective(None)))
    unmixed = column_scores(objective_checks(_objective(None), mix=False))
    assert mixed["audio"]["light"] == "red"            # old standard: no bed under the voice = critical miss
    assert unmixed["audio"]["light"] != "red"
    names = {c.name for c in objective_checks(_objective(None), mix=False)}
    assert not any("BGM" in n or "ducking" in n for n in names)


def test_loudness_and_dead_air_still_count_without_a_mix():
    obj = _objective(None)
    obj["audio"]["integrated"] = -20.0
    assert column_scores(objective_checks(obj, mix=False))["audio"]["light"] == "red"


def test_the_channel_decides_whether_the_mix_standard_applies(tmp_path: Path):
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
    assert audio_mix_enabled(_run_dir(tmp_path / "a", "chipcat")) is True
    assert audio_mix_enabled(_run_dir(tmp_path / "b", "yokai")) is False
    assert audio_mix_enabled(tmp_path / "c") is True      # unreadable channel: keep the full standard


def _mix_issue() -> dict:
    return {"ref": {"target": "audio", "t": "1:00"}, "category": "audio", "severity": "high", "problem": "沒有配樂",
            "fix": "加 BGM", "evidence": "audio.txt", "who": "editor_audio-1", "caused_by": "mix"}


def _card(issues: list[dict]) -> dict:
    return {"round": 1, "label": "round-1", "verdict": {"pass": False, "reasons": ["x"], "issues": issues}}


def test_a_mix_fix_on_an_unmixed_channel_is_channel_config_not_a_deck_rework(tmp_path: Path):
    run_dir = _run_dir(tmp_path, "yokai")
    plan = _rework(run_dir, "final", "final", _card([_mix_issue()]), "assembly")
    assert "mix" not in plan["steps"] and "deck" not in plan["steps"]
    assert [a["caused_by"] for a in plan["advisory"]] == ["channel-config"]


def test_a_mix_fix_on_a_mixed_channel_still_goes_to_the_mix_step(tmp_path: Path):
    run_dir = _run_dir(tmp_path, "chipcat")
    plan = _rework(run_dir, "final", "final", _card([_mix_issue()]), "assembly")
    assert "mix" in plan["steps"] and "advisory" not in plan


def test_new_cycle_moves_rounds_and_the_fix_list_aside(tmp_path: Path):
    for n in (1, 2, 3):
        (tmp_path / "review" / "media" / f"round-{n}").mkdir(parents=True)
        (tmp_path / "review" / "media" / f"round-{n}" / "scorecard.json").write_text("{}", encoding="utf-8")
    (tmp_path / "review" / "media.fixes.json").write_text("{}", encoding="utf-8")
    assert new_stage_cycle(tmp_path, ("media", "final"), reason="leftover rounds of a cloned run") == {"media": "cycle-1"}      # final had nothing to move
    assert not list((tmp_path / "review" / "media").glob("round-*"))
    assert (tmp_path / "review" / "media" / "cycle-1" / "round-3" / "scorecard.json").is_file()
    assert (tmp_path / "review" / "media.fixes.cycle-1.json").is_file()
    (tmp_path / "review" / "media" / "round-1").mkdir()
    assert new_stage_cycle(tmp_path, ("media",), reason="leftover rounds of a cloned run") == {"media": "cycle-2"}              # numbering continues


def test_new_cycle_refuses_an_unknown_stage(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown stage"):
        new_stage_cycle(tmp_path, ("nope",), reason="leftover rounds of a cloned run")


def test_new_cycle_needs_a_real_reason_and_logs_it(tmp_path: Path):
    (tmp_path / "review" / "media" / "round-1").mkdir(parents=True)
    for reason in ("", "   ", "again"):
        with pytest.raises(ValueError, match="--reason"):
            new_stage_cycle(tmp_path, ("media",), reason=reason)
    assert (tmp_path / "review" / "media" / "round-1").is_dir()           # nothing moved by a refused call
    new_stage_cycle(tmp_path, ("media",), reason="re-run after the touch guard fix")
    line = json.loads((tmp_path / "review" / "new_cycle.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["reason"] == "re-run after the touch guard fix" and line["stages"] == {"media": "cycle-1"}
    assert "new_cycle" in (tmp_path / "production.log.jsonl").read_text(encoding="utf-8")
