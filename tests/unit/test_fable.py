"""寓言學堂 (fable channel): the script model and its checks, prepare, the panel materials, the render's pure parts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.production.channels import Gate, Pipeline, load_channel
from content_farm.production.fable import cards, check, compose, guesses, model, prepare, render
from content_farm.production.steps import step_names

NAME = "測試概念"


def _beat(index: int, act: str, text: str, **extra) -> dict:
    base = {"id": f"b{index}", "act": act, "narration": text, "must_keep": ["留"], "must_avoid": ["避"],
            "shots": [{"image_prompt": f"a small fox in a quiet valley, scene {index}"}]}
    return {**base, **extra}


def _story(index: int, hook: str | None = None) -> dict:
    two_shots = [{"image_prompt": f"a fox by the lantern, scene {index}"}, {"image_prompt": f"a fox on the hill, scene {index}"}]
    return _beat(index, "story", "小狐狸慢慢走過山谷，" * 7, shots=two_shots, **({"plants": [hook]} if hook else {}))


def fable_dict(**overrides) -> dict:
    row = {"story": "小狐狸的選擇", "concept": "概念的一個要素"}
    data = {
        "version": 1, "format": "short", "title": "小狐狸為什麼不肯回頭",
        "concept": {"name": NAME, "aliases": ["測試別名"], "english": ["test concept"], "domain": "測試學",
                    "references": ["某教科書第一章"]},
        "elements": [{"id": "e1", "concept_part": "第一個要素", "story_ref": "小狐狸的選擇"},
                     {"id": "e2", "concept_part": "第二個要素", "story_ref": "小狐狸的代價"}],
        "hooks": [{"id": "h1", "text": "小狐狸為什麼不回頭"}],
        "beats": [
            _beat(1, "hook", "這個故事在講一個測試學的概念，你猜得到嗎？"),
            _story(2, "h1"), _story(3), _story(4),
            _beat(5, "reveal", f"這個故事，講的就是{NAME}。你以為只是選擇，其實是代價。" * 2, resolves=["h1"],
                  card={"title": NAME}, shots=[{"reuse": "b2.1"}]),
            _beat(6, "explain", "第一個要素對應小狐狸的選擇，每一次往前都有它的理由，我們一個一個來看。", maps=["e1"],
                  card={"title": "對照", "rows": [row]}, shots=[{"reuse": "b2.2"}]),
            _beat(7, "explain", "第二個要素對應小狐狸的代價，它走得越遠，能回頭的路就越少，這就是第二件事。", maps=["e2"],
                  card={"title": "對照", "rows": [row]}, shots=[{"reuse": "b3.1"}]),
            _beat(8, "apply", "現實裡，很多人都在這樣做決定，像買東西或換工作。", shots=[{"reuse": "b1.1"}]),
        ],
    }
    return {**data, **overrides}


def load(data: dict) -> model.Fable:
    return model.Fable.model_validate(data)


def test_a_well_formed_fable_has_no_problems() -> None:
    assert check.fable_problems(load(fable_dict())) == []


def test_the_concept_name_before_the_reveal_is_a_leak() -> None:
    data = fable_dict()
    data["beats"][2] = _beat(3, "story", f"小狐狸說：這就是{NAME}。" * 5, shots=data["beats"][2]["shots"])
    problems = check.fable_problems(load(data))
    assert any("b3" in p and "概念名" in p for p in problems)


def test_an_alias_in_the_title_or_an_english_name_in_a_picture_prompt_is_a_leak() -> None:
    data = fable_dict(title="測試別名的故事狐狸")
    data["beats"][1]["shots"][0] = {"image_prompt": "a fox thinking about a Test Concept"}
    problems = check.leak_problems(load(data))
    assert any("標題" in p for p in problems) and any("b2" in p for p in problems)


def test_after_the_reveal_the_name_may_appear_anywhere() -> None:
    data = fable_dict()
    data["beats"][5]["narration"] = f"{NAME}的第一個要素，就是小狐狸的選擇。" * 3
    assert check.leak_problems(load(data)) == []


def test_a_thread_planted_but_never_paid_off_is_flagged() -> None:
    data = fable_dict()
    data["beats"][4]["resolves"] = []
    assert any("h1" in p and "收掉" in p for p in check.ledger_problems(load(data)))


def test_a_thread_planted_after_the_reveal_is_flagged() -> None:
    data = fable_dict()
    data["beats"][1]["plants"] = []
    data["beats"][5]["plants"] = ["h1"]
    assert any("h1" in p and "揭曉前" in p for p in check.ledger_problems(load(data)))


def test_every_element_must_be_mapped_by_an_explain_beat() -> None:
    data = fable_dict()
    data["beats"][6]["maps"] = ["e1"]
    assert any("e2" in p for p in check.mapping_problems(load(data)))


def test_people_in_a_picture_prompt_are_refused() -> None:
    data = fable_dict()
    data["beats"][1]["shots"][0] = {"image_prompt": "an old farmer holding a lantern"}
    assert any("farmer" in p for p in check.picture_problems(load(data)))


def test_a_reuse_must_point_at_an_earlier_drawn_shot() -> None:
    data = fable_dict()
    data["beats"][5]["shots"] = [{"reuse": "b7.1"}]
    assert any("b6.1" in p for p in check.picture_problems(load(data)))


def test_act_order_and_the_last_beat_are_enforced() -> None:
    data = fable_dict()
    data["beats"][7]["act"] = "explain"
    assert any("apply" in p for p in check.order_problems(load(data)))


def test_too_short_a_short_is_flagged_and_a_beat_over_the_limit_too() -> None:
    data = fable_dict()
    data["beats"][2]["narration"] = "短。" * 3
    data["beats"][3]["narration"] = "短。" * 3
    assert any("全片" in p for p in check.length_problems(load(data)))
    data = fable_dict()
    data["beats"][2]["narration"] = "小狐狸慢慢走過山谷，" * 12
    assert any("b3" in p and "上限" in p for p in check.length_problems(load(data)))


def test_trendy_words_and_filler_are_flagged() -> None:
    data = fable_dict()
    data["beats"][2]["narration"] = "這隻狐狸狂走，欸欸，" * 8
    problems = check.tone_problems(load(data))
    assert any("狂" in p for p in problems) and any("欸" in p for p in problems)


def test_must_keep_and_avoid_are_required() -> None:
    data = fable_dict()
    data["beats"][3]["must_avoid"] = []
    assert any("b4" in p for p in check.keep_avoid_problems(load(data)))


def test_prepare_writes_one_scene_per_beat_and_keeps_measured_durations(tmp_path: Path) -> None:
    (tmp_path / "fable.json").write_text(json.dumps(fable_dict(), ensure_ascii=False), encoding="utf-8")
    script = prepare.prepare(tmp_path)
    assert [s.title for s in script.scenes][:2] == ["01 hook", "02 story"] and len(script.scenes) == 8
    assert script.orientation.value == "portrait"
    measured = json.loads((tmp_path / "script.json").read_text(encoding="utf-8"))
    measured["scenes"][0]["duration_seconds"] = 3.21
    (tmp_path / "script.json").write_text(json.dumps(measured, ensure_ascii=False), encoding="utf-8")
    assert prepare.prepare(tmp_path).scenes[0].duration_seconds == 3.21        # same words: the voice run's number stays
    changed = fable_dict()
    changed["beats"][0]["narration"] = "這個故事在講一個測試學的概念，你猜得到嗎？真的嗎？"
    (tmp_path / "fable.json").write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    assert prepare.prepare(tmp_path).scenes[0].duration_seconds != 3.21


def test_a_mid_fable_is_landscape(tmp_path: Path) -> None:
    (tmp_path / "fable.json").write_text(json.dumps(fable_dict(format="mid"), ensure_ascii=False), encoding="utf-8")
    assert prepare.prepare(tmp_path).orientation.value == "landscape"
    assert model.format_of(tmp_path) == "mid" and model.format_of(tmp_path / "nowhere") is None


def test_panel_materials_split_before_and_after_the_reveal(tmp_path: Path) -> None:
    from content_farm.review.materials import short_script

    (tmp_path / "fable.json").write_text(json.dumps(fable_dict(), ensure_ascii=False), encoding="utf-8")
    prepare.prepare(tmp_path)
    out = tmp_path / "round"
    mats = short_script(tmp_path, out)
    before = (out / "part1_before_reveal.txt").read_text(encoding="utf-8")
    after = (out / "part2_reveal_and_after.txt").read_text(encoding="utf-8")
    assert NAME not in before and NAME in after and "[c1.1]" in before and "[c5.1]" in after
    assert mats.extra["fable"] is True
    assert "part2_reveal_and_after.txt" in mats.visible_to("fact").files and "part1_before_reveal.txt" not in mats.visible_to("fact").files


def test_the_fact_stage_reads_the_same_fable_script(tmp_path: Path) -> None:
    from content_farm.review.materials import script

    (tmp_path / "fable.json").write_text(json.dumps(fable_dict(), ensure_ascii=False), encoding="utf-8")
    prepare.prepare(tmp_path)
    assert script(tmp_path, tmp_path / "r").extra["fable"] is True       # no deck.json: falls back to the fable builder


def test_guesses_are_turned_into_seconds_and_judged_right_or_wrong(tmp_path: Path) -> None:
    (tmp_path / "fable.json").write_text(json.dumps(fable_dict(), ensure_ascii=False), encoding="utf-8")
    prepare.prepare(tmp_path)
    results = tmp_path / "review" / "shorts_script" / "round-1" / "results"
    results.mkdir(parents=True)
    for name, concept, at in (("viewer-a", "測試別名", "c3.1"), ("viewer-b", "別的東西", None)):
        (results / f"{name}.json").write_text(json.dumps(
            {"persona": name, "guess": {"concept": concept, "at_sentence": at}, "reveal_surprise": 6}), encoding="utf-8")
    rows = guesses.collect(tmp_path)
    assert rows[0]["correct"] and rows[0]["seconds"] > 4 and not rows[1]["correct"] and rows[1]["seconds"] is None
    assert "never before the reveal" in guesses.table(rows)


def test_the_fable_channel_has_its_own_pipeline_and_two_reviews() -> None:
    channel = load_channel("fable")
    assert channel.pipeline is Pipeline.FABLE and set(channel.gates) == {Gate.SCRIPT, Gate.DECK_FACTS, Gate.FINAL}
    names = step_names(channel)
    assert names.index("fable_script") < names.index("gate_script") < names.index("gate_facts") < names.index("voice")
    assert names.index("fable_images") < names.index("fable_render") < names.index("mix") < names.index("package")


def test_a_failed_script_review_routes_to_the_fable_script_step() -> None:
    from content_farm.review.config import REWORK_STEPS, load_review

    config = load_review("fable")
    assert "fable_script" in REWORK_STEPS
    assert config.stages["shorts_script"].rework == "fable_script" and config.stages["script_facts"].rework == "fable_script"
    assert config.stages["script_facts"].reviews == ("script.json",)


def test_shots_are_split_evenly_but_never_below_the_minimum() -> None:
    assert render.shot_seconds(9.0, 3) == [3.0, 3.0, 3.0]
    assert render.shot_seconds(2.0, 3) == [2.0]
    assert render.shot_seconds(4.0, 3) == pytest.approx([2.0, 2.0])


def test_explain_rows_appear_one_by_one_across_the_beat() -> None:
    times = cards.row_times(3, 12.0)
    assert len(times) == 3 and times == sorted(times) and times[0] > 0.8 and times[-1] < 12.0
    assert cards.row_times(0, 12.0) == []


def test_the_diagram_filter_lays_a_window_on_paper_and_steps_through_the_panels() -> None:
    graph = compose.diagram_filter(cards.GEOMETRY["short"], [0.0, 2.5, 5.0], fade=None)
    assert "crop=1080:880:0:520,pad=1080:1920:0:0:color=0xF3E9D2" in graph
    assert "between(t,0.000,2.500)" in graph and "gte(t,5.000)" in graph and graph.endswith("[v]")
    wide = compose.diagram_filter(cards.GEOMETRY["mid"], [0.0], fade=(0.9, 0.5))
    assert "crop=1080:1080:420:0" in wide and "fade=t=in:st=0.90" in wide


def test_the_join_uses_one_xfade_at_the_reveal() -> None:
    graph = compose.join_filter(6, reveal=3, pre_seconds=40.0)
    assert "xfade=transition=circleopen" in graph and "offset=39.300" in graph and "concat=n=3" in graph
    assert "xfade" not in compose.join_filter(4, reveal=None, pre_seconds=0.0)


def test_overlay_pages_show_the_concept_and_only_the_rows_so_far() -> None:
    fable = load(fable_dict())
    reveal = fable.beats[4]
    assert NAME in cards.overlay_html(fable, reveal) and "測試學" in cards.overlay_html(fable, reveal)
    explain = fable.beats[5]
    assert "概念的一個要素" in cards.overlay_html(fable, explain) and "概念的一個要素" not in cards.overlay_html(fable, explain, rows_visible=0)
