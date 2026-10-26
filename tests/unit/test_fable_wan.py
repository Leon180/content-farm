"""Wan shots in a fable (Leon 2026-10-25): lint, requests, the step, the compose filter."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.production.channels import load_channel
from content_farm.production.fable import check, compose, model, wan_shots
from content_farm.production.steps import step_names
from tests.unit.test_fable import fable_dict, load

WAN = {"motion": "the lantern light flickers and snow drifts down, static camera"}


def with_wan(shot_index: int = 1, **spec) -> model.Fable:
    data = fable_dict()
    data["beats"][shot_index]["shots"][0] = {**data["beats"][shot_index]["shots"][0], "wan": {**WAN, **spec}}
    return load(data)


def test_a_wan_shot_with_a_wide_faceless_picture_passes() -> None:
    assert check.wan_problems(with_wan()) == []


def test_a_wan_shot_of_a_face_or_with_hands_is_refused() -> None:
    data = fable_dict()
    data["beats"][1]["shots"][0] = {"image_prompt": "close-up of a fox face", "wan": WAN}
    data["beats"][2]["shots"][0] = {"image_prompt": "a fox on a hill", "wan": {"motion": "the fox holds a lantern up"}}
    problems = check.wan_problems(load(data))
    assert any("b2.1" in p and "特寫" in p for p in problems) and any("b3.1" in p and "holds" in p for p in problems)


def test_more_than_four_wan_shots_are_refused() -> None:
    data = fable_dict()
    for index in (1, 2, 3):
        for shot in data["beats"][index]["shots"]:
            shot["wan"] = WAN
    assert any("上限" in p for p in check.wan_problems(load(data)))


def test_requests_use_the_portrait_size_for_a_short_and_chain_the_segments(tmp_path: Path) -> None:
    fable = with_wan(chain=["it keeps drifting, static camera"])
    (tmp_path / "assets" / "ai_images").mkdir(parents=True)
    (tmp_path / "assets" / "ai_images" / "b2_1.png").write_bytes(b"png")
    (request,) = wan_shots.requests_for(tmp_path, fable)
    assert (request.params.width, request.params.height) == (480, 832)
    assert request.segments == 2 and request.slide_id == "b2_1"


def test_a_missing_picture_is_an_error_not_a_silent_skip(tmp_path: Path) -> None:
    try:
        wan_shots.requests_for(tmp_path, with_wan())
    except FileNotFoundError as exc:
        assert "b2_1" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_has_wan_reads_the_raw_file(tmp_path: Path) -> None:
    assert wan_shots.has_wan(tmp_path) is False
    (tmp_path / "fable.json").write_text(json.dumps(with_wan().model_dump(mode="json")), encoding="utf-8")
    assert wan_shots.has_wan(tmp_path) is True


def test_the_manifest_round_trips_and_is_empty_without_the_step(tmp_path: Path) -> None:
    assert wan_shots.load_manifest(tmp_path) == {}
    wan_shots.write_manifest(tmp_path, {"b2_1": {"clip": "x.mp4", "fps": 24, "segments": 2, "credit": {}}})
    assert wan_shots.load_manifest(tmp_path)["b2_1"]["segments"] == 2


def test_the_wan_segment_is_slowed_at_most_a_little_then_holds_its_last_frame(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(compose, "run", lambda args, cwd: calls.append(args))
    compose.wan_segment(tmp_path / "c.mp4", (1080, 1920), 9.0, 5.7, tmp_path / "o.mp4", tmp_path)
    vf = calls[0][calls[0].index("-vf") + 1]
    assert "setpts=PTS*1.4000" in vf and "tpad=stop_mode=clone" in vf and "lanczos" in vf
    compose.wan_segment(tmp_path / "c.mp4", (1080, 1920), 4.0, 5.7, tmp_path / "o.mp4", tmp_path)
    assert "setpts=PTS*1.0000" in calls[1][calls[1].index("-vf") + 1]


def test_the_wan_step_sits_between_images_and_render_and_is_heavy() -> None:
    names = step_names(load_channel("fable"))
    assert names.index("fable_images") < names.index("fable_wan") < names.index("fable_render")


def test_a_diagram_beat_is_sliced_over_its_shots_with_rebased_panel_times() -> None:
    from content_farm.production.fable import render

    overlays = [(Path("a.png"), 0.0), (Path("b.png"), 4.0), (Path("c.png"), 9.0)]
    assert render.part_overlays(overlays, 0.0, 6.0) == [(Path("a.png"), 0.0), (Path("b.png"), 4.0)]
    assert render.part_overlays(overlays, 6.0, 12.0) == [(Path("b.png"), 0.0), (Path("c.png"), 3.0)]
