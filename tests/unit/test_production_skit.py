"""The 冷笑話小劇場 script format: structure, pause, length, tone and the check_skit.py script."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from content_farm.production import skit
from content_farm.production.skit import EXPRESSIONS, estimated_seconds, skit_problems

REPO = Path(__file__).resolve().parents[2]


def _scene(number: int, beat: str, narration: str, face: str = "neutral", transition: str = "cut") -> dict[str, Any]:
    return {"scene_number": number, "title": f"{number:02d} {beat}", "narration": narration,
            "visual_hint": {"description": face, "keywords": []}, "duration_seconds": 5.0, "transition": transition}


SETUP_1 = "週五下午五點，同事在群組裡說只是改一行字，保證不會有事，大家都很放心地點了頭，還有人回了一個大拇指。"
SETUP_2 = "我住在飲水機裡，看過太多個週五。他按下部署的那一刻，整層樓突然安靜得只剩氣泡的聲音。"
PUNCHLINE = "最後被關掉的，是我的水。"
TAG = "下週一，我還是在這裡。"


def good_script() -> dict[str, Any]:
    return {
        "stage": "script_generation", "video_title": "週五下午五點的部署", "description": "原創冷笑話，角色為 AI 生成。",
        "language": "zh-TW", "target_length": "short", "orientation": "portrait", "ai_disclosure": True,
        "tags": ["冷笑話", "#Shorts"], "sources": [],
        "scenes": [_scene(1, "鋪陳", SETUP_1), _scene(2, "鋪陳", SETUP_2, transition="pause:0.6"),
                   _scene(3, "笑點", PUNCHLINE, face="smug"), _scene(4, "收尾", TAG, face="speechless")],
        "total_duration_seconds": 25,
    }


def _padded(script: dict[str, Any], extra_chars: int) -> dict[str, Any]:
    out = copy.deepcopy(script)
    out["scenes"][0]["narration"] += "這是一句用來把長度拉長的鋪陳，" * (extra_chars // 15)
    return out


def test_a_good_script_passes_and_is_inside_the_window() -> None:
    script = good_script()
    assert skit_problems(script) == []
    assert 20 <= estimated_seconds(script) <= 50


def test_the_pause_counts_toward_the_length() -> None:
    script = good_script()
    spoken = sum(skit.estimate_seconds(s["narration"]) for s in script["scenes"])
    assert estimated_seconds(script) == pytest.approx(spoken + 0.6, abs=0.11)


def test_too_short_and_too_long_are_refused() -> None:
    short = good_script()
    short["scenes"] = [_scene(1, "鋪陳", "只是改一行。", transition="pause:0.6"), _scene(2, "笑點", "水被關了。", face="smug")]
    assert any("outside 20–50" in p for p in skit_problems(short))
    assert any("outside 20–50" in p for p in skit_problems(_padded(good_script(), 300)))


def test_the_beat_before_the_laugh_must_pause() -> None:
    no_pause = good_script()
    no_pause["scenes"][1]["transition"] = "cut"
    assert any("pause:0.6" in p for p in skit_problems(no_pause))
    long_pause = good_script()
    long_pause["scenes"][1]["transition"] = "pause:2"
    assert any("pause:0.6" in p for p in skit_problems(long_pause))
    stray = good_script()
    stray["scenes"][0]["transition"] = "pause:0.6"
    assert any("only the beat before" in p for p in skit_problems(stray))


@pytest.mark.parametrize("mutate, expected", [
    (lambda s: s["scenes"].pop(2), "exactly one 笑點"),
    (lambda s: s["scenes"].insert(3, copy.deepcopy(s["scenes"][2])), "exactly one 笑點"),
    (lambda s: s["scenes"][3].update(title="04 鋪陳"), "only an optional 收尾"),
    (lambda s: s["scenes"][0].update(title="第一場"), "must read"),
    (lambda s: s["scenes"].insert(0, _scene(9, "收尾", "先收尾")), "before 笑點"),
])
def test_structure_problems(mutate, expected: str) -> None:
    script = good_script()
    mutate(script)
    assert any(expected in p for p in skit_problems(script)), skit_problems(script)


def test_tag_must_be_last_and_at_most_once() -> None:
    script = good_script()
    script["scenes"].insert(2, _scene(7, "收尾", "太早收尾"))
    assert any("optional, at most one, and last" in p for p in skit_problems(script))


def test_four_setup_scenes_are_too_many() -> None:
    script = good_script()
    script["scenes"] = [_scene(i, "鋪陳", SETUP_1) for i in range(1, 5)] + [script["scenes"][2]]
    script["scenes"][3]["transition"] = "pause:0.6"
    assert any("at most 3" in p for p in skit_problems(script))


def test_a_long_punchline_is_refused() -> None:
    script = good_script()
    script["scenes"][2]["narration"] = "最後被關掉的，其實是我整個週末和我辛苦攢了很久的水，連一點氣泡都沒有留給我自己，也沒有人跟我說聲再見。"
    assert any("over 40" in p for p in skit_problems(script))


def test_trendy_words_and_filler_are_refused() -> None:
    trendy = good_script()
    trendy["scenes"][0]["narration"] += "這個部署狂出事。"
    assert any("「狂」" in p for p in skit_problems(trendy))
    filler = good_script()
    filler["scenes"][0]["narration"] += "欸，真的欸。"
    assert any("「欸」" in p for p in skit_problems(filler))
    one = good_script()
    one["scenes"][0]["narration"] += "欸。"
    assert skit_problems(one) == []


def test_expression_must_be_a_goldfish_layer() -> None:
    script = good_script()
    script["scenes"][0]["visual_hint"]["description"] = "angry"
    assert any("not a goldfish expression" in p for p in skit_problems(script))


def test_expressions_match_the_pack_manifest() -> None:
    manifest = json.loads((REPO / "src/content_farm/explainer/pngtuber/packs/cooler-goldfish-3d/manifest.json")
                          .read_text(encoding="utf-8"))
    assert set(EXPRESSIONS) == set(manifest["expressions"])


def test_metadata_rules() -> None:
    script = good_script()
    script["ai_disclosure"] = False
    script["video_title"] = ""
    script["description"] = " "
    problems = " | ".join(skit_problems(script))
    assert "ai_disclosure must be true" in problems and "video_title" in problems and "description is empty" in problems


def test_not_a_script_at_all() -> None:
    assert skit_problems({"scenes": "nope"})[0].startswith("not a valid script.json")


def test_script_survives_the_voice_stage_round_trip() -> None:
    """The voice step rewrites script.json through the Script model: the skit fields must come back unchanged."""
    from content_farm.script_gen.schemas import Script

    script = good_script()
    again = Script.model_validate(script).model_dump(mode="json")
    assert [s["title"] for s in again["scenes"]] == [s["title"] for s in script["scenes"]]
    assert [s["transition"] for s in again["scenes"]] == [s["transition"] for s in script["scenes"]]
    assert [s["visual_hint"]["description"] for s in again["scenes"]] == [s["visual_hint"]["description"] for s in script["scenes"]]
    assert skit_problems(again) == []


def _run_check(run_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(REPO / "scripts" / "check_skit.py"), "--run-dir", str(run_dir)],
                          capture_output=True, text=True, env={"PYTHONPATH": str(REPO / "src"), "PATH": "/usr/bin:/bin"},
                          check=False)


def test_check_script_exit_codes(tmp_path: Path) -> None:
    assert _run_check(tmp_path).returncode == 2                      # no script.json
    (tmp_path / "script.json").write_text("{not json", encoding="utf-8")
    assert _run_check(tmp_path).returncode == 2
    bad = good_script()
    bad["scenes"][1]["transition"] = "cut"
    (tmp_path / "script.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    broken = _run_check(tmp_path)
    assert broken.returncode == 1 and "pause:0.6" in broken.stdout
    (tmp_path / "script.json").write_text(json.dumps(good_script(), ensure_ascii=False), encoding="utf-8")
    ok = _run_check(tmp_path)
    assert ok.returncode == 0 and "0 problem(s)" in ok.stdout
