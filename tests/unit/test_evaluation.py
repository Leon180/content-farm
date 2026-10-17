"""Review panel config, aggregation, homepage stats, feed mockups, eval-loop log."""

from __future__ import annotations

import json

from PIL import Image

from content_farm.evaluation import aggregate, homepage
from content_farm.evaluation.loop import append_log, read_log
from content_farm.evaluation.panel import Thresholds, load_panels, roster, word_persona


def test_panels_config_loads_and_has_holdouts() -> None:
    panels = load_panels()
    for code in ("chipcat", "yokai", "cel"):
        assert sum(p.holdout for p in panels.personas[code]) == 1
    assert panels.stages["rough_cut"].pros["editor"] >= 1 and panels.stages["rough_cut"].pros["director"] >= 1


def test_holdout_only_in_final_round_and_wording_changes() -> None:
    panels = load_panels()
    first = roster(panels, "rough_cut", "chipcat", 1, final_round=False)
    last = roster(panels, "rough_cut", "chipcat", 3, final_round=True)
    assert not any(r.holdout for r in first)
    assert any(r.holdout for r in last)
    assert len([r for r in first if r.kind == "viewer"]) == 5
    engineer = panels.personas["chipcat"][1]
    assert word_persona(panels, engineer, 1) != word_persona(panels, engineer, 2)


def _view(persona: str, left: str | None, click: dict, holdout: bool = False) -> dict:
    return {"persona": persona, "_rid": f"viewer-{persona}", "_holdout": holdout, "left_at": left, "click": click,
            "segments": [{"engagement": 5}] * 6, "finish": left is None,
            "top_fixes": [{"t": "0:40", "category": "visual", "problem": f"{persona} 靜止太久", "fix": "加動畫"}]}


def test_audience_leave_click_and_curve() -> None:
    views = [_view("a", "0:30", {"A": 6, "B": 8}), _view("b", None, {"A": 7, "B": 8}), _view("c", "0:50", {"A": 5, "B": 6})]
    aud = aggregate.audience(views, 60.0, ["A", "B"])
    assert aud["leave_median_pct"] == 0.83
    assert aud["best_variant"] == "B" and aud["click_best"] == 7.33
    assert aud["curve"][:4] == [1.0, 1.0, 1.0, 0.67]


def test_fix_list_groups_by_time_and_skips_holdout() -> None:
    views = [_view("a", None, {}), _view("b", None, {}), _view("h", None, {}, holdout=True)]
    pros = [{"_rid": "pro-editor-1", "issues": [{"t": "0:50", "category": "visual", "problem": "同一張卡太久", "fix": "推近"}]}]
    fixes = aggregate.fix_list(views, pros)
    assert fixes[0]["votes"] == 3 and "viewer-h" not in fixes[0]["who"]


def test_homepage_stats_and_verdict() -> None:
    keys = {"v1_feed1_phone.jpg": {"variant": "A", "ours_card": 4, "cards": 12}}
    views = [{"_holdout": False, "homepage": [{"feed": "feeds/v1_feed1_phone.jpg", "noticed": [4, 1, 2], "picked": 4}]}]
    home = aggregate.homepage_stats(views, keys)
    assert home["A"]["noticed_median"] == 1 and home["A"]["pick_rate"] == 1.0
    result = aggregate.verdict({"count": 1, "leave_median_pct": 0.6, "click_best": 7.5}, home,
                               {"visual": {"light": "green"}}, Thresholds())
    assert result["pass"]
    failed = aggregate.verdict({"count": 1, "leave_median_pct": 0.3, "click_best": 7.5}, home,
                               {"visual": {"light": "red"}}, Thresholds())
    assert not failed["pass"] and len(failed["reasons"]) == 2


def test_feed_image_marks_cards(tmp_path) -> None:
    cards = []
    for i, colour in enumerate(("red", "blue", "green")):
        path = tmp_path / f"t{i}.jpg"
        Image.new("RGB", (480, 360), colour).save(path)
        cards.append(homepage.Card(path, f"標題 {i} 很長很長很長很長很長很長很長很長", "頻道", ours=i == 1))
    phone = homepage.feed_image(cards, tmp_path / "phone.jpg")
    desk = homepage.feed_image(cards, tmp_path / "desk.jpg", desktop=True)
    assert Image.open(phone).width == homepage.PHONE_W + 30
    assert Image.open(desk).width > Image.open(phone).width
    arranged = homepage.arrange(cards[1], [cards[0], cards[2]], seed="x", total=3)
    assert sum(c.ours for c in arranged) == 1


def test_hue_and_contrast() -> None:
    assert homepage.hue_distance(350, 10) == 20
    assert homepage.contrast_ratio((255, 255, 255), (0, 0, 0)) == 21.0
    hue, _ = homepage.mean_hue(Image.new("RGB", (64, 36), (255, 0, 0)))
    assert hue in (0.0, 360.0)


def test_loop_log_appends(tmp_path) -> None:
    append_log(tmp_path, {"round": 1})
    append_log(tmp_path, {"round": 2})
    assert [e["round"] for e in read_log(tmp_path)] == [1, 2]
    assert json.loads((tmp_path / "eval" / "loop.jsonl").read_text().splitlines()[0]) == {"round": 1}
