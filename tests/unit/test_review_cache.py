"""Per-seat result cache and per-seat inputs (cf-cost-fix, Leon 2026-10-22): the same content is never judged twice,
and a reviewer is shown only the files it needs."""

from __future__ import annotations

import pytest

import dataclasses
import json
from pathlib import Path

from content_farm.review import cache
from content_farm.review.client import Call, CallResult
from functools import partial as _partial
from pathlib import Path as _Path

from content_farm.review import config as _config

load_review = _partial(_config.load_review, path=_Path(__file__).parents[1] / "fixtures" / "review_panels_v3.yaml")
from content_farm.review.rounds import run_round
from tests.unit.test_production_runner import run_dir as run_dir  # noqa: F401  (fixture)
from tests.unit.test_review_script_stages import Panel

CONFIG = load_review()
KW = {"stage_name": "script_structure", "config": CONFIG, "channel": "chipcat", "channel_name": "晶片貓",
      "with_holdout": False}


class Priced(Panel):
    """A panel whose every answer is billed 0.5 (nominal)."""

    def __call__(self, call: Call) -> CallResult:
        return dataclasses.replace(super().__call__(call), cost_usd=0.5)


def _with_sources(run_dir: Path) -> None:
    (run_dir / "article.md").write_text("# 文章\n\n台積電的製程很先進。\n", encoding="utf-8")
    (run_dir / "sources.json").write_text(json.dumps({"sources": [{"id": "s1", "title": "t", "url": "https://x.test"}]}),
                                          encoding="utf-8")


def _edit_first_sentence(run_dir: Path) -> None:
    deck = json.loads((run_dir / "deck.json").read_text(encoding="utf-8"))
    slide = deck["sections"][0]["slides"][0]
    slide["narration"] = slide["narration"].replace("。", "，而且這是新改的一句。", 1)
    (run_dir / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")


def test_an_unchanged_second_round_makes_no_calls_and_costs_nothing(run_dir: Path) -> None:  # noqa: F811
    _with_sources(run_dir)
    panel = Priced()
    first = run_round(run_dir, round_no=1, client=panel, **KW)
    live = len(panel.calls)
    assert live == len(first["seats"]) and first["cache"]["hits"] == 0 and first["cost_usd"] > 0
    second = run_round(run_dir, round_no=2, client=panel, **KW)      # persona wording and order differ in round 2
    assert len(panel.calls) == live, "an unchanged script must not be judged again"
    assert second["cache"]["hits"] == len(second["seats"]) and second["cost_usd"] == 0
    assert second["cache"]["saved_usd"] == first["cost_usd"]
    assert all(seat.get("cached") for seat in second["seats"])
    assert second["verdict"]["scores"] == first["verdict"]["scores"]


def test_a_changed_sentence_is_judged_again_by_everyone_who_reads_it(run_dir: Path) -> None:  # noqa: F811
    _with_sources(run_dir)
    panel = Panel()
    first = run_round(run_dir, round_no=1, client=panel, **KW)
    _edit_first_sentence(run_dir)
    before = len(panel.calls)
    second = run_round(run_dir, round_no=2, client=panel, **KW)
    assert len(panel.calls) - before == len(first["seats"])
    assert second["cache"]["hits"] == 0


def test_changing_only_the_sources_reruns_the_fact_checker_not_the_viewers(run_dir: Path) -> None:  # noqa: F811
    _with_sources(run_dir)
    panel = Panel()
    run_round(run_dir, round_no=1, client=panel, **KW)
    (run_dir / "sources.json").write_text(json.dumps({"sources": [{"id": "s2", "title": "u", "url": "https://y.test"}]}),
                                          encoding="utf-8")
    before = len(panel.calls)
    second = run_round(run_dir, round_no=2, client=panel, **KW)
    reran = [rid for _, rid in panel.calls[before:]]
    assert reran == ["fact_checker-1"], reran
    assert second["cache"]["hits"] == len(second["seats"]) - 1


def test_a_failed_answer_is_never_cached(run_dir: Path) -> None:  # noqa: F811
    _with_sources(run_dir)

    def broken(call: Call) -> CallResult:
        return CallResult(call.rid, False, None, ("schema: nope",), call.model, call.effort)

    run_round(run_dir, round_no=1, client=broken, **KW)
    assert not list((run_dir / cache.CACHE_DIR).glob("*.json"))


def test_the_cache_can_be_turned_off(run_dir: Path, monkeypatch) -> None:  # noqa: F811
    _with_sources(run_dir)
    monkeypatch.setenv("CF_REVIEW_CACHE", "0")
    panel = Panel()
    run_round(run_dir, round_no=1, client=panel, **KW)
    live = len(panel.calls)
    run_round(run_dir, round_no=2, client=panel, **KW)
    assert len(panel.calls) == 2 * live


def test_each_reviewer_is_listed_only_the_files_it_needs(run_dir: Path) -> None:  # noqa: F811
    _with_sources(run_dir)
    run_round(run_dir, round_no=1, client=Panel(), **KW)
    prompts = run_dir / "review" / "script_structure" / "round-1" / "prompts"
    viewer = next(prompts.glob("viewer-*.md")).read_text(encoding="utf-8")
    fact = (prompts / "fact_checker-1.md").read_text(encoding="utf-8")
    director = (prompts / "director-1.md").read_text(encoding="utf-8")
    assert "script.txt" in viewer and "storyboard.txt" in viewer
    assert "sources.json" not in viewer and "article.md" not in viewer
    assert "sources.json" in fact and "article.md" in fact and "storyboard.txt" not in fact
    assert "sources.json" not in director and "article.md" not in director


def test_volatile_fields_do_not_change_a_file_digest(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({"slides": [{"id": "s1", "build_seconds": 12.5}], "generated_at": "t1", "reused": 3}))
    b.write_text(json.dumps({"slides": [{"id": "s1", "build_seconds": 0.0}], "generated_at": "t2", "reused": 26}))
    assert cache.file_digest(a) == cache.file_digest(b)
    b.write_text(json.dumps({"slides": [{"id": "s2", "build_seconds": 0.0}], "generated_at": "t2"}))
    assert cache.file_digest(a) != cache.file_digest(b)


def test_derived_files_are_left_out_of_the_content_digest(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "sheet.png").write_bytes(b"1")
    one = cache.content_digest(tmp_path, ["a.txt", "sheet.png"], derived=frozenset({"sheet.png"}))
    (tmp_path / "sheet.png").write_bytes(b"2")
    assert cache.content_digest(tmp_path, ["a.txt", "sheet.png"], derived=frozenset({"sheet.png"})) == one
    assert cache.content_digest(tmp_path, ["a.txt", "sheet.png"]) != one


pytestmark = pytest.mark.usefixtures("v3_panels")   # drives the full v3 panel set; v4 turns most of it off (see test_review_v4.py)
