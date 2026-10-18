"""Fix scope: what an edit puts back in the queue (explainer.fix_scope)."""

from __future__ import annotations

import copy

from content_farm.explainer.fix_scope import analyse, changed_terms, voice_window


def _deck() -> dict:
    return {"title": "產能翻倍，晶片卻不一定翻倍", "description": "", "sections": [
        {"title": "開場", "slides": [
            {"id": "s01", "heading": "62 → 5", "body": {"value": "62"},
             "narration": "一倍大小排得下 62 個。晶圓產能翻倍，晶片卻不一定翻倍？我是晶片貓。"},
            {"id": "s02", "heading": "交期", "body": {"items": ["52 到 78 週"]},
             "narration": "訂一批，要等 52 到 78 週。這是第二張。"},
        ]},
        {"title": "算盤", "slides": [
            {"id": "k1", "heading": "產能翻倍，晶片不一定翻倍", "body": {"value": "200 萬"},
             "narration": "用年底每月 13 萬片粗算。全做 3.3 倍呢？大約 200 萬個；全做 9 倍呢？只剩 65 萬個。"
                          "晶圓翻倍，晶片卻不一定翻倍。"},
            {"id": "s24", "heading": "結論", "body": {"items": ["回扣"]},
             "narration": "最後回到開頭。晶片卻不一定翻倍，記住這句。"},
        ]},
    ]}


def _edit(deck: dict, slide_id: str, **changes) -> dict:
    out = copy.deepcopy(deck)
    for section in out["sections"]:
        for slide in section["slides"]:
            if slide["id"] == slide_id:
                slide.update(changes)
    return out


def test_changed_terms_finds_numbers_and_touched_clause():
    terms = changed_terms("大約 200 萬個；", "每月大約 200 萬個封裝；")
    assert "大約200萬個" in terms
    assert changed_terms("要等 52 到 78 週。", "要等 40 到 78 週。")[0] == "52"


def test_one_sentence_edit_stays_in_its_scene():
    old = _deck()
    new = _edit(old, "s02", narration="訂一批，要等很久。這是第二張。")
    scope = analyse(old, new, radius=1)
    assert scope.changed == ("s02.3",)
    assert scope.voice_windows == {"s02": ("s02.3", "s02.2")}
    assert scope.redraw_scenes == ("s02",)
    assert scope.shifted_scenes == ("k1", "s24")
    # "52 到 78 週" left the narration but is still on the slide body → flagged
    assert any(o.where == "body s02" for o in scope.occurrences)


def test_window_never_crosses_the_scene():
    assert voice_window(["a.1", "a.2", "a.3"], "a.1", 1) == ("a.1", "a.2")
    assert voice_window(["a.1", "a.2", "a.3"], "a.2", 2) == ("a.1", "a.2", "a.3")
    assert voice_window(["a.1", "a.2", "a.3"], "a.2", 0) == ("a.2",)


def test_named_term_is_flagged_everywhere_it_appears():
    old = _deck()
    new = _edit(old, "k1", narration=old["sections"][1]["slides"][0]["narration"].replace(
        "大約 200 萬個", "每月大約 200 萬個封裝"))
    outside = [("thumbnail.json promise[1]", "晶片卻不一定翻倍"), ("upload/manual/title.txt", "與此無關")]
    scope = analyse(old, new, extra_terms=["晶片卻不一定翻倍"], outside=outside)
    where = {o.where for o in scope.occurrences if o.term == "晶片卻不一定翻倍"}
    assert {"title", "narration s01.2", "narration k1.6", "narration s24.2",
            "thumbnail.json promise[1]"} <= where
    assert "heading k1" not in where  # 「晶片不一定翻倍」 is worded differently: not the same term
    assert set(scope.voice_windows) == {"k1", "s01", "s24"}
    assert scope.voice_windows["s01"] == ("s01.1", "s01.2", "s01.3")
    # the term is in the deck title, which every frame prints: fixing it redraws every slide
    assert set(scope.redraw_scenes) == {"s01", "s02", "k1", "s24"}
    assert any("every frame" in note for note in scope.notes)


def test_slide_only_change_redraws_one_scene_and_revoices_nothing():
    old = _deck()
    new = _edit(old, "s02", heading="交期一年半")
    scope = analyse(old, new)
    assert scope.changed == () and scope.voice_windows == {}
    assert scope.redraw_scenes == ("s02",)


def test_reorder_is_noted():
    old = _deck()
    new = copy.deepcopy(old)
    new["sections"][0]["slides"].reverse()
    scope = analyse(old, new)
    assert scope.changed == () and scope.notes


def test_title_change_redraws_every_slide():
    old = _deck()
    new = copy.deepcopy(old)
    new["title"] = "新標題"
    scope = analyse(old, new)
    assert scope.redraw_scenes == ("s01", "s02", "k1", "s24") and scope.voice_windows == {}
