"""Item 3 (cf-pipeline-speed): a small deck rework is one no-tool JSON turn that the program applies; anything that does
not fit falls back to the full agent."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.review import producers, quick_patch
from content_farm.review.client import CallResult
from content_farm.review.config import load_review

CONFIG = load_review()


def _deck(slides: int = 12) -> dict:
    return {"title": "t", "sections": [{"title": "A", "slides": [
        {"id": f"s{n:02d}", "narration": f"第{n}張第一句。第{n}張第二句。", "sentence_ids": [f"x{n}a", f"x{n}b"]}
        for n in range(1, slides + 1)]}]}


def _fix(ids: list[str], problem: str = "太長", fix: str = "縮短", **extra) -> dict:
    return {"ref": {"target": "script", "sentence_ids": ids}, "problem": problem, "fix": fix,
            "scope": {"sentence_ids": ids, "titles": [], "thumbnail": False, "description": False, "chapters": []}, **extra}


def _plan(*fixes: dict, **extra) -> dict:
    return {"round": 1, "steps": {"deck": {"fixes": list(fixes)}}, **extra}


def _setup(tmp_path: Path, plan: dict) -> Path:
    (tmp_path / "review").mkdir()
    (tmp_path / "deck.json").write_text(json.dumps(_deck(), ensure_ascii=False), encoding="utf-8")
    (tmp_path / "review" / "deck.fixes.json").write_text(json.dumps(plan), encoding="utf-8")
    return tmp_path


def _client(answer: dict, calls: list):
    def run(call):
        calls.append(call)
        return CallResult(call.rid, True, answer, (), "sonnet", "medium", seconds=9.0, cost_usd=0.01,
                          tokens={"output": 120})
    return run


def test_eligibility_rules() -> None:
    deck = _deck()                                           # 24 sentences → 10% = 2.4
    assert quick_patch.eligibility(deck, _plan(_fix(["x1a"])))[0] is True
    assert "over 10%" in quick_patch.eligibility(deck, _plan(_fix(["x1a", "x1b", "x2a"])))[1]
    assert quick_patch.eligibility(deck, _plan(_fix(["x1a"], fix="補上來源")))[0] is False
    assert quick_patch.eligibility(deck, _plan(_fix(["x1a"]), prompt_only=["s01"]))[0] is False
    assert quick_patch.eligibility(deck, _plan({"ref": {"target": "script"}, "problem": "p", "fix": "f",
                                                "scope": {"sentence_ids": []}}))[0] is False
    assert quick_patch.eligibility(deck, _plan(_fix(["zz"])))[0] is False
    assert quick_patch.eligibility(deck, _plan(_fix(["x1a"], rerouted_from="article")))[0] is False


def test_quick_path_applies_the_patch_without_tools(tmp_path: Path, monkeypatch) -> None:
    run_dir = _setup(tmp_path, _plan(_fix(["x1a"])))
    monkeypatch.setattr(quick_patch, "strict_check", lambda *a: [])
    calls: list = []
    answer = {"replace": {"x1a": "改短了。"}, "deletes": [], "summary": "縮短"}
    result = producers.produce("deck", run_dir, channel="chipcat", config=CONFIG, python="/py", client=_client(answer, calls))
    assert len(calls) == 1 and calls[0].tools == () and calls[0].write_tools is False
    assert result.ok and result.output["fixed"] == ["x1a"] and result.output["files"] == ["deck.json", "script.json"]
    assert json.loads((run_dir / "deck.json").read_text(encoding="utf-8"))["sections"][0]["slides"][0]["narration"] == "改短了。第1張第二句。"
    rows = [json.loads(x) for x in (run_dir / "review/producers/producers.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["quick"] is True and rows[0]["quick_ok"] is True and rows[0]["tokens"]["output"] == 120


def test_unnamed_sentence_or_failed_lint_falls_back_to_the_agent(tmp_path: Path, monkeypatch) -> None:
    run_dir = _setup(tmp_path, _plan(_fix(["x1a"])))
    before = (run_dir / "deck.json").read_text(encoding="utf-8")
    calls: list = []
    stray = {"replace": {"x9a": "亂改。"}, "deletes": [], "summary": "s"}
    agent = {"files": ["deck.json"], "summary": "full agent"}
    answers = iter([stray, agent])
    client = lambda call: _client(next(answers), calls)(call)           # noqa: E731
    result = producers.produce("deck", run_dir, channel="chipcat", config=CONFIG, python="/py", client=client)
    assert len(calls) == 2 and calls[0].tools == () and calls[1].tools != () and result.output == agent
    assert (run_dir / "deck.json").read_text(encoding="utf-8") == before        # the refused patch changed nothing

    monkeypatch.setattr(quick_patch, "strict_check", lambda *a: ["[lint:x] too long"])
    calls.clear()
    answers = iter([{"replace": {"x1a": "好。"}, "deletes": [], "summary": "s"}, agent])
    producers.produce("deck", run_dir, channel="chipcat", config=CONFIG, python="/py", client=client)
    assert len(calls) == 2
    assert (run_dir / "deck.json").read_text(encoding="utf-8") == before        # lint failure restored the deck
    rows = [json.loads(x) for x in (run_dir / "review/producers/producers.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r.get("quick") and not r["quick_ok"] and "lint" in r["quick_why"] for r in rows)


def test_needs_tools_answer_and_big_lists_use_the_agent(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, _plan(_fix(["x1a"])))
    calls: list = []
    producers.produce("deck", run_dir, channel="chipcat", config=CONFIG, python="/py",
                      client=_client({"replace": {}, "deletes": [], "summary": "", "needs_tools": True}, calls))
    assert len(calls) == 2
    (tmp_path / "b").mkdir()
    run_dir2 = _setup(tmp_path / "b", _plan(_fix(["x1a", "x1b", "x2a"])))
    calls2: list = []
    producers.produce("deck", run_dir2, channel="chipcat", config=CONFIG, python="/py",
                      client=_client({"files": ["deck.json"], "summary": "ok"}, calls2))
    assert len(calls2) == 1 and calls2[0].tools != ()                    # too many sentences: straight to the agent
    assert "over 10%" in (run_dir2 / "review/producers/quick.jsonl").read_text(encoding="utf-8")


def test_switch_off(tmp_path: Path, monkeypatch) -> None:
    run_dir = _setup(tmp_path, _plan(_fix(["x1a"])))
    monkeypatch.setenv("CF_QUICK_PATCH", "0")
    calls: list = []
    producers.produce("deck", run_dir, channel="chipcat", config=CONFIG, python="/py",
                      client=_client({"files": ["deck.json"], "summary": "ok"}, calls))
    assert len(calls) == 1 and calls[0].tools != ()


def test_no_tool_call_drops_the_allowed_tools_flag() -> None:
    from content_farm.review.client import argv_for

    argv = argv_for(quick_patch.build_call("deck-1", "p", CONFIG.stages["script_structure"].producer
                                           or type("T", (), {"model": "sonnet", "effort": "medium"})(), Path(".")))
    assert "--tools" in argv and argv[argv.index("--tools") + 1] == "" and "--allowed-tools" not in argv
