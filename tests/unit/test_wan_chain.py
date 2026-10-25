"""Longer Wan shots: chained segments (last frame → next start), text-to-video starts, the deck's own
Wan budget, and the 1080p upscale filter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from content_farm.explainer import ffmpeg_ops, motion_bake, wan, wan_chain
from content_farm.explainer.deck import Deck, Motion
from content_farm.explainer.motion import plan_motion
from content_farm.explainer.motion_cache import MotionPaths, clip_paths, write_record
from content_farm.production import qc
from tests.unit.explainer_helpers import deck_dict, slide

TINY = wan.WanParams(width=64, height=64, num_frames=9, fps=24, steps=1)


def _deck(*media: dict, budget: int | None = None) -> Deck:
    data = deck_dict()
    data["sections"][1]["slides"] = [slide(f"w{i}", "quote", media={"kind": "ai_image", "prompt": f"fox {i}", **m})
                                     for i, m in enumerate(media)]
    if budget:
        data["wan_budget"] = budget
    return Deck.model_validate(data)


def _paths(tmp_path: Path) -> MotionPaths:
    home = tmp_path / "mlx-video"
    for sub in ("venv/bin/python", "models/depth-anything-v2-small-hf/model.safetensors",
                "models/wan22-ti2v-5b-q8/model.safetensors"):
        (home / sub).parent.mkdir(parents=True, exist_ok=True)
        (home / sub).write_text("x")
    paths = MotionPaths.from_env({"CF_MLX_VIDEO_HOME": str(home)})
    assert paths is not None
    return paths


def _still(run_dir: Path, slide_id: str) -> Path:
    path = run_dir / "assets" / "ai_images" / f"{slide_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), (10, 20, 30)).save(path)
    path.with_suffix(".json").write_text(json.dumps({"prompt": "deep sea", "seed": 7}))
    return path


class FakeWan:
    """Stands in for the mlx_video process: records each call and writes a 9-frame clip whose
    colour changes per call (so a joined clip really contains every segment)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, argv: list[str], **_: object) -> subprocess.CompletedProcess:
        def flag(name: str) -> str | None:
            return argv[argv.index(name) + 1] if name in argv else None

        out = Path(flag("--output-path"))
        self.calls.append({"image": flag("--image"), "prompt": flag("--prompt"), "out": out.name})
        colour = "0x%02x4060" % (40 * len(self.calls))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        f"color=c={colour}:s=64x64:r=24:d=0.375", "-frames:v", "9", "-pix_fmt", "yuv420p",
                        str(out)], check=True)
        return subprocess.CompletedProcess(argv, 0, stdout="Peak memory: 21.5 GB\n", stderr="")


def _frames(clip: Path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames", "-of", "csv=p=0", str(clip)], capture_output=True, text=True,
                         check=True).stdout
    return int(out.strip())


def test_media_validates_chain_and_t2v_only_for_wan() -> None:
    _deck({"motion": "wan", "motion_prompt": "a", "wan_chain": ["b", "c"], "wan_t2v": True})
    with pytest.raises(ValidationError, match="motion: wan"):
        _deck({"motion": "parallax", "wan_chain": ["b"]})
    with pytest.raises(ValidationError):
        _deck({"motion": "wan", "wan_chain": ["b", "c", "d"]})   # ≤3 segments (≈8.5 s)


def test_wan_budget_replaces_the_three_shot_limit(tmp_path: Path) -> None:
    six = [{"motion": "wan", "motion_prompt": "mist"} for _ in range(6)]
    with pytest.raises(ValueError, match="max 3"):
        motion_bake.wan_shots(_deck(*six), tmp_path)
    deck = _deck(*six, budget=6)
    assert wan.max_shots(deck) == 6 and len(motion_bake.wan_shots(deck, tmp_path)) == 6
    assert qc.wan_count_findings(deck) == [] and qc.wan_count_findings(_deck(*six))[0].level == "error"
    with pytest.raises(ValidationError):
        _deck(*six, budget=11)
    (tmp_path / "deck.json").write_text(json.dumps({"wan_budget": 6}))
    assert wan.run_limit(tmp_path) == 6 and wan.run_limit(tmp_path / "nope") == 3


def test_credits_limit_follows_the_budget() -> None:
    move = {"kind": "wan", "model": "m", "prompt": "p", "seed": 1}
    entries = [{"kind": "ai_image", "slide_id": s, "ai_label": "AI 示意圖", "model": "m", "prompt": "p", "seed": 1,
                "motion": move} for s in "abcde"]
    assert any(f.level == "error" for f in qc.ai_image_findings(entries))
    assert not any(f.level == "error" for f in qc.ai_image_findings(entries, 5))


def test_cache_key_is_unchanged_for_plain_clips_and_differs_for_chains(tmp_path: Path) -> None:
    image = _still(tmp_path, "w0")
    plain = wan.request_for("w0", image, {"prompt": "x", "seed": 7}, "mist")
    chained = wan.request_for("w0", image, {"prompt": "x", "seed": 7}, "mist", chain=("more",))
    t2v = wan.request_for("w0", image, {"prompt": "x", "seed": 7}, "mist", t2v=True)
    keys = {wan.key_for(r, "sha") for r in (plain, chained, t2v)}
    assert len(keys) == 3
    assert plain.segments == 1 and chained.segments == 2
    # a t2v clip does not depend on the still, so redrawing the still keeps it
    assert wan.key_for(t2v, "sha-a") == wan.key_for(t2v, "sha-b")


def test_request_checks_every_chain_prompt() -> None:
    with pytest.raises(ValueError, match="photo"):
        wan.request_for("w0", Path("x.png"), {}, "mist", chain=("a photorealistic whale",))


def test_argv_drops_image_for_t2v_and_overrides_for_a_segment(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    image = _still(tmp_path, "w0")
    t2v = wan.request_for("w0", image, {}, "mist", t2v=True)
    assert "--image" not in wan.argv(paths, t2v, tmp_path / "o.mp4")
    seg = wan.argv(paths, t2v, tmp_path / "o.mp4", image=tmp_path / "last.png", prompt="next")
    assert seg[seg.index("--image") + 1].endswith("last.png") and seg[seg.index("--prompt") + 1] == "next"


def test_join_drops_the_repeated_first_frame_of_each_continuation() -> None:
    assert wan_chain.joined_frames(1, 69) == 69 and wan_chain.joined_frames(3, 69) == 205
    graph = wan_chain.concat_args([Path("a.mp4"), Path("b.mp4"), Path("c.mp4")], Path("o.mp4"))
    text = " ".join(graph)
    assert text.count("trim=start_frame=1") == 2 and "concat=n=3" in text


def test_chain_runs_segments_from_the_previous_last_frame_and_joins_them(tmp_path: Path) -> None:
    image = _still(tmp_path, "w0")
    request = wan.WanRequest("w0", image, "first", TINY, ("second", "third"))
    fake = FakeWan()
    record = wan.generate(_paths(tmp_path), tmp_path, request, lambda: 1.5, fake)
    assert [c["prompt"] for c in fake.calls] == ["first", "second", "third"]
    assert fake.calls[0]["image"] == str(image)
    assert fake.calls[1]["image"].endswith("w0.wan.seg0.last.png")
    assert fake.calls[2]["image"].endswith("w0.wan.seg1.last.png")
    clip, sidecar = clip_paths(tmp_path, "w0", "wan")
    assert _frames(clip) == wan_chain.joined_frames(3, 9) == 25
    assert record["segments"] == 3 and record["chain_prompts"] == ["second", "third"]
    assert record["gate_wait_seconds"] == 4.5 and record["reported_peak_gb"] == 21.5 and sidecar.is_file()
    assert wan.cached(tmp_path, request) is not None


def test_an_interrupted_chain_resumes_at_the_segment_it_stopped_in(tmp_path: Path) -> None:
    image = _still(tmp_path, "w0")
    request = wan.WanRequest("w0", image, "first", TINY, ("second",))
    first = FakeWan()

    def dies_on_second(argv: list[str], **kw: object) -> subprocess.CompletedProcess:
        if len(first.calls) == 1:
            raise RuntimeError("machine slept")
        return first(argv, **kw)

    with pytest.raises(RuntimeError, match="slept"):
        wan.generate(_paths(tmp_path), tmp_path, request, lambda: 0.0, dies_on_second)
    resumed = FakeWan()
    record = wan.generate(_paths(tmp_path), tmp_path, request, lambda: 0.0, resumed)
    assert [c["prompt"] for c in resumed.calls] == ["second"]      # segment 0 came from its cache
    assert record["segments"] == 2 and _frames(clip_paths(tmp_path, "w0", "wan")[0]) == 17


def test_text_to_video_start_has_no_image_and_a_still_redraw_does_not_stale_it(tmp_path: Path) -> None:
    image = _still(tmp_path, "w0")
    request = wan.WanRequest("w0", image, "a huge silhouette drifts", TINY, (), True)
    fake = FakeWan()
    wan.generate(_paths(tmp_path), tmp_path, request, lambda: 0.0, fake)
    assert fake.calls[0]["image"] is None
    assert fake.calls[0]["out"] == "w0.wan.seg0.mp4"
    other = wan.WanRequest("w0", image, "a huge silhouette drifts", TINY, (), True)
    assert wan.key_for(other, "redrawn-still") == wan.key_for(request, "w0-still")


def test_media_plan_uses_the_joined_clip(tmp_path: Path) -> None:
    deck = _deck({"motion": "wan", "motion_prompt": "mist", "wan_chain": ["more"]})
    image = _still(tmp_path, "w0")
    request = wan.request_for("w0", image, {"prompt": "deep sea", "seed": 7}, "mist", chain=("more",))
    clip, _ = clip_paths(tmp_path, "w0", "wan")
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"x")
    write_record(tmp_path, "w0", "wan", {"key": wan.key_for(request, wan.file_sha256(image)), "prompt": "p",
                                         "params": {"seed": 7}, "segments": 2, "frames": 137})
    plan = plan_motion(None, tmp_path, next(x for x in deck.slides if x.id == "w0"), 1, image, {"prompt": "deep sea", "seed": 7})
    assert plan.used == Motion.WAN and "2 segments" in plan.note and "137f" in plan.note
    assert plan.credit["segments"] == 2


def test_bake_announces_the_segment_count(tmp_path: Path) -> None:
    deck = _deck({"motion": "wan", "motion_prompt": "a", "wan_chain": ["b", "c"]})
    _still(tmp_path, "w0")
    shots = motion_bake.wan_shots(deck, tmp_path)
    logs: list[str] = []
    motion_bake.bake(shots, _paths(tmp_path), lambda: 0.0, log=logs.append,
                     generate=lambda *a: {"seconds": 1, "gate_wait_seconds": 0, "reported_peak_gb": None})
    assert "3 segment(s)" in logs[0] and "~45 min" in logs[0]


def test_upscale_filter_sharpens_only_wan_clips() -> None:
    assert "unsharp" in ffmpeg_ops.upscale_filter(sharpen=True)
    assert "unsharp" not in ffmpeg_ops.upscale_filter(sharpen=False)
    assert "lanczos" in ffmpeg_ops.upscale_filter(sharpen=False)
