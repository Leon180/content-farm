"""offwork (shorts_skit): topic step + topic panel, skit_script producer agent, comedy script panel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.production import runner as runner_mod
from content_farm.production.channels import Gate, Pipeline, load_channel
from content_farm.production.runner import Outcome, Runner
from content_farm.production.state import load_state
from content_farm.production.steps import Context, RunOptions, step_names, steps_for
from content_farm.review import prompts, schemas
from content_farm.review.client import Call, CallResult
from content_farm.review.config import load_review
from content_farm.review.producers import is_skit_channel, producer_tier
from tests.unit.test_production_runner import FakeExecutor
from tests.unit.test_production_skit import good_script

CANDIDATES = {"candidates": [{"id": f"t0{n}", "title": f"題目{n}", "hook": "鋪陳 → 笑點", "minutes": 0.5, "sources": [],
                              "note": "工程師梗"} for n in range(1, 6)]}


@pytest.fixture()
def run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(runner_mod, "LOCK_PATH", tmp_path / "render.lock")
    path = tmp_path / "run"
    path.mkdir()
    return path


class Studio:
    """Fake ``claude -p``: producer agents write their files into the run-dir, reviewers answer from fixed scores."""

    def __init__(self, comedy_score: float = 8.0) -> None:
        self.calls: list[Call] = []
        self.comedy_score = comedy_score

    def __call__(self, call: Call) -> CallResult:
        self.calls.append(call)
        if call.write_tools:
            out = self._produce(call)
        elif call.schema == schemas.TOPIC_VIEWER:
            out = {"persona": "p", "overall": "ok", "picks": [{"candidate_id": c["id"], "click": 8 - i, "why": "好笑"}
                                                          for i, c in enumerate(CANDIDATES["candidates"])]}
        elif call.schema == schemas.SCRIPT_VIEWER:
            out = {"persona": "p", "overall": "ok", "finish": True, "left_at_sentence": None, "top_fixes": [],
                   "segments": [{"slide_id": f"c{n}", "engagement": 8, "decision": "stay", "why": "ok"} for n in range(1, 5)]}
        elif call.schema == schemas.PRO:
            out = {"role": "writer_comedy", "score": self.comedy_score, "issues": [], "verdict": "ok",
                   "rubric": {name: self.comedy_score for name in ("笑點", "鋪陳", "停頓", "時長", "頻道調性")}}
        else:
            raise AssertionError(f"unexpected call {call.rid}")
        return CallResult(call.rid, True, out, (), call.model, call.effort, (f"claude-{call.model}-5-5",), 1.0)

    def _produce(self, call: Call) -> dict:
        if call.rid.startswith("topic"):
            target, payload = call.cwd / "topics" / "candidates.json", CANDIDATES
        else:
            target, payload = call.cwd / "script.json", good_script()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return {"files": [str(target)], "summary": "ok"}


def _runner(run_dir: Path, studio: Studio) -> Runner:
    options = RunOptions(mock_voice=True, auto_agents=True, review_client=studio)
    return Runner(Context(load_channel("offwork"), run_dir, options), executor=FakeExecutor(run_dir), log=lambda _: None)


def test_offwork_steps_start_with_topic_then_script_gate() -> None:
    channel = load_channel("offwork")
    names = step_names(channel)
    assert names[:4] == ("topic", "gate_topic", "skit_script", "gate_script")
    assert names.index("voice") < names.index("skit_render")
    assert channel.gate_enabled(Gate.TOPIC) and channel.pipeline is Pipeline.SHORTS_SKIT


def test_skit_script_step_is_checked_by_the_skit_lint() -> None:
    step = next(s for s in steps_for(load_channel("offwork")) if s.name == "skit_script")
    command = step.verify(Context(load_channel("offwork"), Path("/tmp/x"), RunOptions()))  # type: ignore[misc]
    assert Path(command.argv[1]).name == "check_skit.py"


def test_a_run_reaches_the_voice_step_through_both_panels(run_dir: Path) -> None:
    studio = Studio()
    result = _runner(run_dir, studio).run(until="voice")
    assert result.outcome is Outcome.COMPLETE, result.message
    state = load_state(run_dir, "offwork")
    assert state.decisions["topic"].by == "agent-panel:shorts_topic"
    assert state.decisions["script"].by == "agent-panel:shorts_script"
    assert (run_dir / "topic.json").is_file() and (run_dir / "script.json").is_file()
    assert (run_dir / "audio" / "scene_001.mp3").is_file()


def test_producers_run_on_sonnet_and_get_the_skit_tasks(run_dir: Path) -> None:
    studio = Studio()
    _runner(run_dir, studio).run(until="gate_script")
    producers = {c.rid.rsplit("-", 1)[0]: c for c in studio.calls if c.write_tools}
    assert set(producers) == {"topic", "skit_script"}
    assert {c.model for c in producers.values()} == {"sonnet"}           # not the long videos' opus plan stage
    assert "冷笑話選題" in producers["topic"].prompt and "不需要上網查資料" in producers["topic"].prompt
    assert "skit-script/SKILL.md" in producers["skit_script"].prompt
    assert any("check_skit.py" in tool for tool in producers["skit_script"].tools)


def test_script_panel_seats_three_viewers_and_a_comedy_writer(run_dir: Path) -> None:
    studio = Studio()
    _runner(run_dir, studio).run(until="gate_script")
    script_calls = [c for c in studio.calls if not c.write_tools and c.schema in (schemas.SCRIPT_VIEWER, schemas.PRO)]
    assert sorted(c.rid for c in script_calls) == ["viewer-engineer", "viewer-office_worker", "viewer-student",
                                                   "writer_comedy-1"]
    assert {(c.model, c.effort) for c in script_calls} == {("sonnet", "low")}
    comedy = next(c for c in script_calls if c.rid == "writer_comedy-1")
    for rubric_item in ("笑點", "鋪陳", "停頓", "時長", "頻道調性"):
        assert rubric_item in comedy.prompt
    assert any(who in " ".join(c.prompt for c in script_calls) for who in ("上班族", "後端工程師", "大學生"))


def test_a_low_comedy_score_sends_the_script_back_to_skit_script(run_dir: Path) -> None:
    studio = Studio(comedy_score=4.0)
    result = _runner(run_dir, studio).run(until="gate_script")
    assert result.outcome is Outcome.REWORK and result.step == "gate_script", result.message
    assert load_state(run_dir, "offwork").steps["skit_script"].status == "rework"
    plan = json.loads((run_dir / "review" / "script.fixes.json").read_text(encoding="utf-8"))
    assert plan["restart"] == "skit_script" and set(plan["steps"]) == {"skit_script"}


def test_offwork_review_config_is_valid_and_wired() -> None:
    config = load_review("offwork")
    stage = config.stages["shorts_script"]
    assert stage.rework == "skit_script"
    assert [(s.role, s.count) for s in stage.seats] == [("viewer", 3), ("writer_comedy", 1)]
    assert config.roles["writer_comedy"].rubric == ("笑點", "鋪陳", "停頓", "時長", "頻道調性")
    assert {s.model for s in stage.seats} == {"sonnet"}
    assert load_review("chipcat").stages["shorts_script"].rework == "deck"       # other channels unchanged


def test_comedy_writer_is_not_a_free_pass_for_other_roles() -> None:
    """Only the story writer's seat may be filled by the comedy writer; dropping viewers still breaks the rule."""
    from content_farm.review.config import ReviewConfig, rule_violations

    config = load_review("offwork")
    raw = config.model_dump()
    raw["stages"]["shorts_script"]["seats"] = [s for s in raw["stages"]["shorts_script"]["seats"] if s["role"] != "viewer"]
    with pytest.raises(ValueError, match="needs viewer"):
        ReviewConfig.model_validate(raw)
    assert rule_violations(config) == []


def test_skit_channel_detection_and_topic_tier() -> None:
    assert is_skit_channel("offwork") and not is_skit_channel("chipcat") and not is_skit_channel("no-such-channel")
    config = load_review("offwork")
    assert producer_tier(config, "topic").model == "opus"                       # long-video plan stage
    assert producer_tier(config, "topic", skit=True).model == "sonnet"          # shorts_topic producer
    assert producer_tier(config, "skit_script").model == "sonnet"


def test_reviewers_may_name_skit_script_as_the_cause() -> None:
    assert "skit_script" in prompts.CAUSED_BY and "skit_script" in schemas.ISSUE["properties"]["caused_by"]["enum"]


def test_script_materials_list_the_skit_structure(tmp_path: Path) -> None:
    from content_farm.review import materials

    (tmp_path / "script.json").write_text(json.dumps(good_script(), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    built = materials.short_script(tmp_path, out)
    text = (out / built.files[0]).read_text(encoding="utf-8")
    assert "## 場景結構" in text and "[c2] 鋪陳｜金魚表情 neutral｜之後停頓 0.6 秒" in text and "[c3] 笑點" in text
    assert "約" in built.extra["duration_text"] and "停頓" in built.notes[built.files[0]]
