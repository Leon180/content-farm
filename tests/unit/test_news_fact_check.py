"""news.py factcheck: confidence >= 0.5 counts as an error, ONE automatic fix, no re-check."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.production.news import audit_step, fact_check
from content_farm.production.news import script as ns
from content_farm.production.news.fact_check import Issue
from content_farm.review.client import CallResult


def _script() -> ns.NewsScript:
    def beat(kind: str, text: str) -> dict:
        return {"kind": kind, "narration": text, "screen": {"headline": "標題"}}

    return ns.NewsScript.model_validate({
        "item_id": "hn-1", "title": "測試標題一二三", "summary": "這是一則測試用的摘要文字。", "importance": 3,
        "sources": [{"url": "https://ex.com/a", "title": "A", "read_at": "2026-10-25T10:00:00+08:00"}],
        "beats": [beat("hook", "公司砍了二十五萬棵樹。"), beat("what", "據報導，面積約三百公頃，官員要求停工。"),
                  beat("why", "原文沒列台灣的數字。"), beat("analogy", "環評像地基檢查。"), beat("take", "我覺得重點是順序。")]})


def _run_dir(tmp_path: Path) -> Path:
    page = tmp_path / "page.txt"
    page.write_text("original text", encoding="utf-8")
    (tmp_path / ns.ITEM_FILE).write_text(json.dumps({"read": {"ok": True, "text_path": str(page)}}), encoding="utf-8")
    (tmp_path / ns.SCRIPT_FILE).write_text(_script().model_dump_json(), encoding="utf-8")
    return tmp_path


def _client(issues: list[dict], ok: bool = True):
    def call(c):
        return CallResult(c.rid, ok, {"issues": issues} if ok else None, () if ok else ("boom",), "sonnet", "medium",
                          cost_usd=0.05, tokens={"output": 10})
    return call


def test_only_confident_issues_are_errors() -> None:
    issues = [Issue(1, "a", "p", 0.49, ""), Issue(2, "b", "p", 0.5, ""), Issue(3, "c", "p", 0.9, "x")]
    assert [i.beat for i in fact_check.errors_only(issues)] == [2, 3]


def test_apply_fixes_rewrites_deletes_and_reports_missing_sentences() -> None:
    errors = [Issue(2, "面積約三百公頃", "原文是 330 公頃", 0.9, "面積約三百三十公頃"),
              Issue(2, "官員要求停工", "原文只說機關要求暫停", 0.7, ""),
              Issue(1, "不存在的句子", "p", 0.9, "")]
    fixed, fixes = fact_check.apply_fixes(_script(), errors)
    assert "三百三十公頃" in fixed.beats[1].narration and "官員" not in fixed.beats[1].narration
    assert [f.action for f in fixes] == ["rewritten", "deleted", "not_found"]
    assert fixed.beats[0] == _script().beats[0]            # untouched beats stay identical


def test_run_fixes_once_logs_and_does_not_recheck(tmp_path: Path) -> None:
    run = _run_dir(tmp_path)
    issues = [{"beat": 1, "sentence": "公司砍了二十五萬棵樹", "problem": "原文是被指控", "confidence": 0.8,
               "fix": "公司被指砍了約二十五萬棵樹"},
              {"beat": 4, "sentence": "環評像地基檢查", "problem": "其實沒問題", "confidence": 0.2, "fix": ""}]
    assert fact_check.run(run, "technews", _client(issues)) == 0
    report = json.loads((run / audit_step.REPORT).read_text(encoding="utf-8"))
    assert report["outcome"] == "auto_fixed_then_passed" and len(report["fixes"]) == 1
    assert "被指砍了" in ns.load_script(run).beats[0].narration
    assert (run / audit_step.DRAFT).is_file() and audit_step.was_fixed(run)
    log = (run / "review" / "auto_fix.jsonl").read_text(encoding="utf-8")
    assert "fix_issued" in log and "passed_without_recheck" in log

    def must_not_call(_):
        raise AssertionError("a fixed script is not checked again")
    assert fact_check.run(run, "technews", must_not_call) == 0


def test_clean_script_is_left_alone(tmp_path: Path) -> None:
    run = _run_dir(tmp_path)
    before = (run / ns.SCRIPT_FILE).read_text(encoding="utf-8")
    assert fact_check.run(run, "technews", _client([{"beat": 2, "sentence": "x", "problem": "p",
                                                      "confidence": 0.3, "fix": ""}])) == 0
    assert (run / ns.SCRIPT_FILE).read_text(encoding="utf-8") == before
    assert json.loads((run / audit_step.REPORT).read_text(encoding="utf-8"))["outcome"] == "clean"
