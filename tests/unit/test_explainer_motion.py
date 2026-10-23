"""ai_image motion (decision 2bacb8a2b8b0): parallax by default, baked Wan for ≤2 key shots,
Ken Burns as the last fallback; cache keys, the machine gate, credits and QC."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from content_farm.explainer import ffmpeg_ops, motion_bake, parallax, wan
from content_farm.explainer.deck import Deck, Motion
from content_farm.explainer.media_run import credits_text
from content_farm.explainer.motion import plan_motion
from content_farm.explainer.motion_cache import MotionPaths, clip_paths, motion_env, write_record
from content_farm.production import qc
from content_farm.production.channels import load_channel
from content_farm.production.steps import EXPLAINER_STEPS
from tests.unit.explainer_helpers import deck_dict, slide

STYLE = "Ink wash illustration, not a photograph."


def _deck(*motions: str | None) -> Deck:
    data = deck_dict()
    slides = []
    for index, move in enumerate(motions):
        media = {"kind": "ai_image", "prompt": f"a white fox number {index}"}
        if move:
            media["motion"] = move
        slides.append(slide(f"m{index}", "quote", media=media))
    data["sections"][1]["slides"] = slides
    return Deck.model_validate(data)


def _image(run_dir: Path, slide_id: str, seed: int = 42) -> Path:
    path = run_dir / "assets" / "ai_images" / f"{slide_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 36), (120, 110, 100)).save(path)
    path.with_suffix(".json").write_text(json.dumps({"prompt": f"{STYLE} a fox", "seed": seed}))
    return path


def _paths(tmp_path: Path) -> MotionPaths:
    home = tmp_path / "mlx-video"
    for sub in ("venv/bin/python", "models/depth-anything-v2-small-hf/model.safetensors",
                "models/wan22-ti2v-5b-q8/model.safetensors"):
        (home / sub).parent.mkdir(parents=True, exist_ok=True)
        (home / sub).write_text("x")
    paths = MotionPaths.from_env({"CF_MLX_VIDEO_HOME": str(home)})
    assert paths is not None
    return paths


class FakeWorker:
    """Stands in for motion_parallax_worker.py: writes --out and prints its stats line."""

    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.returncode = returncode

    def __call__(self, argv: list[str], **_: object) -> subprocess.CompletedProcess:
        self.calls.append(argv)
        if self.returncode == 0:
            Path(argv[argv.index("--out") + 1]).write_bytes(b"mp4")
        stats = {"ok": True, "seconds": 3.0, "build_seconds": 2.0, "depth_strength": 0.8, "thin_share": 0.03}
        return subprocess.CompletedProcess(argv, self.returncode, stdout=json.dumps(stats), stderr="boom")


# --- deck schema ---------------------------------------------------------------------------

def test_motion_defaults_to_parallax_and_only_applies_to_ai_image() -> None:
    deck = _deck(None, "wan")
    assert [s.media.motion_kind for s in deck.slides[1:3]] == [Motion.PARALLAX, Motion.WAN]
    data = deck_dict()
    data["sections"][1]["slides"][0]["media"] = {"kind": "stock", "query": "fab", "motion": "wan"}
    with pytest.raises(ValidationError, match="only apply to media kind 'ai_image'"):
        Deck.model_validate(data)


# --- paths ---------------------------------------------------------------------------------

def test_paths_come_from_env_with_per_path_overrides(tmp_path: Path) -> None:
    assert MotionPaths.from_env({}) is None
    paths = MotionPaths.from_env({"CF_MLX_VIDEO_HOME": "/m", "CF_WAN_MODEL_DIR": "/elsewhere/wan"})
    assert paths == MotionPaths(Path("/m/venv/bin/python"), Path("/m/models/depth-anything-v2-small-hf"),
                                Path("/elsewhere/wan"))
    assert any("python not found" in p for p in paths.problems())
    assert _paths(tmp_path).problems(wan=True) == []
    env_file = tmp_path / "env"
    env_file.write_text("CF_MLX_VIDEO_HOME=/from/file\n")
    assert motion_env(env_file, {})["CF_MLX_VIDEO_HOME"] == "/from/file"
    assert motion_env(env_file, {"CF_MLX_VIDEO_HOME": "/env"})["CF_MLX_VIDEO_HOME"] == "/env"


# --- parallax ------------------------------------------------------------------------------

def test_parallax_clip_is_capped_at_three_seconds_and_alternates_direction() -> None:
    with pytest.raises(ValueError, match="≤3.0s"):
        parallax.ParallaxParams(seconds=3.5)
    assert parallax.params_for(1).pan_x == -parallax.params_for(2).pan_x != 0


def test_parallax_clip_is_cached_by_image_and_params(tmp_path: Path) -> None:
    paths, worker, image = _paths(tmp_path), FakeWorker(), _image(tmp_path, "s1")
    clip, record = parallax.ensure_clip(paths, tmp_path, "s1", image, parallax.params_for(1), run=worker)
    assert clip == clip_paths(tmp_path, "s1", "parallax")[0] and not record["from_cache"]
    argv = worker.calls[0]
    assert argv[0] == str(paths.python) and argv[argv.index("--seconds") + 1] == "3.0"
    assert argv[argv.index("--depth-model") + 1] == str(paths.depth_model)
    _, again = parallax.ensure_clip(paths, tmp_path, "s1", image, parallax.params_for(1), run=worker)
    assert again["from_cache"] and len(worker.calls) == 1
    parallax.ensure_clip(paths, tmp_path, "s1", image, parallax.params_for(2), run=worker)  # new params
    Image.new("RGB", (64, 36), (0, 0, 0)).save(image)  # new pixels
    parallax.ensure_clip(paths, tmp_path, "s1", image, parallax.params_for(2), run=worker)
    assert len(worker.calls) == 3


def test_wan_and_parallax_clips_of_one_slide_do_not_share_a_file(tmp_path: Path) -> None:
    wan_clip, wan_record = clip_paths(tmp_path, "s06", "wan")
    px_clip, px_record = clip_paths(tmp_path, "s06", "parallax")
    assert (wan_clip.name, wan_record.name) == ("s06.wan.mp4", "s06.wan.json")
    assert len({wan_clip, wan_record, px_clip, px_record}) == 4


def test_parallax_worker_failure_raises_with_its_output(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="exit 1: boom"):
        parallax.ensure_clip(_paths(tmp_path), tmp_path, "s1", _image(tmp_path, "s1"),
                             parallax.params_for(1), run=FakeWorker(returncode=1))


# --- plan ----------------------------------------------------------------------------------

def test_plan_falls_back_parallax_to_ken_burns_and_says_why(tmp_path: Path, monkeypatch) -> None:
    deck, image = _deck(None, "ken_burns"), _image(tmp_path, "m0")
    plan = plan_motion(None, tmp_path, deck.slides[1], 2, image, None)
    assert plan.used == Motion.KEN_BURNS and plan.clip is None
    assert plan.credit["requested"] == "parallax" and "CF_MLX_VIDEO_HOME" in plan.credit["fallback_reason"]
    asked = plan_motion(None, tmp_path, deck.slides[2], 3, image, None)
    assert asked.used == Motion.KEN_BURNS and asked.credit == {"kind": "ken_burns"}  # asked for, no fallback
    monkeypatch.setattr(parallax.subprocess, "run", FakeWorker(returncode=1))
    broken = plan_motion(_paths(tmp_path), tmp_path, deck.slides[1], 2, image, None)
    assert broken.used == Motion.KEN_BURNS and "parallax failed" in broken.note


def test_plan_uses_baked_wan_else_parallax(tmp_path: Path, monkeypatch) -> None:
    deck, image = _deck("wan"), _image(tmp_path, "m0")
    record = json.loads(image.with_suffix(".json").read_text())
    monkeypatch.setattr(parallax.subprocess, "run", FakeWorker())
    paths = _paths(tmp_path)
    unbaked = plan_motion(paths, tmp_path, deck.slides[1], 2, image, record)
    assert unbaked.used == Motion.PARALLAX and unbaked.credit["requested"] == "wan"
    assert "not baked" in unbaked.credit["fallback_reason"] and unbaked.credit["tool_repo"]
    request = wan.request_for("m0", image, record, "", deck.slides[1].media.prompt)
    clip, _ = clip_paths(tmp_path, "m0", "wan")
    clip.write_bytes(b"mp4")
    write_record(tmp_path, "m0", "wan", {"key": wan.key_for(request, wan.file_sha256(image)),
                                         "prompt": request.prompt, "params": {"seed": 42}})
    baked = plan_motion(paths, tmp_path, deck.slides[1], 2, image, record)
    assert baked.used == Motion.WAN and baked.clip == clip and baked.retime_fps == 24
    assert baked.credit["model"] == "wan22-ti2v-5b-q8" and baked.credit["seed"] == 42
    assert "requested" not in baked.credit


# --- wan -----------------------------------------------------------------------------------

def test_wan_params_stay_within_three_seconds_and_model_limits() -> None:
    assert wan.WanParams().num_frames / wan.WanParams().fps <= 3.0
    with pytest.raises(ValueError, match="4n\\+1"):
        wan.WanParams(num_frames=70)
    with pytest.raises(ValueError, match="≤3.0s"):
        wan.WanParams(num_frames=81)
    with pytest.raises(ValueError, match="multiples of 32"):
        wan.WanParams(width=840)


def test_wan_request_keeps_the_still_prompt_and_refuses_photo_real(tmp_path: Path) -> None:
    image = _image(tmp_path, "s1", seed=7)
    request = wan.request_for("s1", image, {"prompt": f"{STYLE} a fox", "seed": 7}, "tails sway")
    assert request.prompt == f"{STYLE} a fox Motion: tails sway" and request.params.seed == 7
    default = wan.request_for("s1", image, None, "", "a fox")
    assert default.prompt.endswith(wan.DEFAULT_MOTION) and default.params.seed == 42
    with pytest.raises(ValueError, match="photoreal"):
        wan.request_for("s1", image, None, "photorealistic tails", "a fox")
    argv = wan.argv(_paths(tmp_path), request, tmp_path / "o.mp4")
    assert argv[1:3] == ["-m", "mlx_video.models.wan_2.generate"]
    assert argv[argv.index("--num-frames") + 1] == "69" and argv[argv.index("--image") + 1] == str(image)
    assert wan.key_for(request, "sha") != wan.key_for(default, "sha")


def test_busy_gate_matches_renders_and_models_but_not_mentions() -> None:
    ps = "\n".join([
        "101 /opt/homebrew/bin/ffmpeg -y -i a.mp4 b.mp4",
        "102 /venv/bin/python -m mlx_video.models.wan_2.generate --prompt fox",
        "103 /flux/bin/python /flux/bin/mflux-generate-z-image-turbo --prompt x",
        "104 grep mflux log.txt",
        "105 python run.py --note ffmpeg mlx_video mflux",
        "106 /opt/homebrew/bin/ffmpeg -i mine.mp4",
    ])
    hits = wan.busy_processes({106}, ps)
    assert [h.split()[0].rsplit("/", 1)[-1] for h in hits] == ["ffmpeg", "python", "python"]
    assert wan.busy_processes(set(), "1 /bin/zsh\n2 python scripts/ai_motion.py bake") == []  # control


def test_bake_refuses_more_than_three_and_generates_only_missing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max 3"):
        motion_bake.wan_shots(_deck("wan", "wan", "wan", "wan"), tmp_path)
    deck = _deck("wan", None, "wan")
    _image(tmp_path, "m0")
    shots = motion_bake.wan_shots(deck, tmp_path)
    assert [(s.slide_id, s.request is not None, s.cached) for s in shots] == [("m0", True, False),
                                                                              ("m2", False, False)]
    calls, gates = [], []

    def fake_generate(paths, run_dir, request, gate):
        gates.append(gate())
        calls.append(request.slide_id)
        return {"seconds": 1.0, "gate_wait_seconds": gates[-1], "reported_peak_gb": 26.0}

    logs: list[str] = []
    records = motion_bake.bake(shots, _paths(tmp_path), lambda: 0.0, log=logs.append, generate=fake_generate)
    assert calls == ["m0"] and len(records) == 1 and gates == [0.0]
    assert any("no still yet" in line for line in logs)


# --- QC / credits / steps ------------------------------------------------------------------

def test_qc_limits_wan_to_three_per_video() -> None:
    channel = load_channel("yokai")
    assert qc.wan_count_findings(_deck("wan", "wan", "wan")) == []
    [finding] = qc.policy_findings(channel, _deck("wan", "wan", "wan", "wan"))
    assert finding.level == "error" and "max 3" in finding.message


def _entry(slide_id: str, move: dict) -> dict:
    return {"kind": "ai_image", "slide_id": slide_id, "ai_label": "AI 示意圖", "model": "z-image-turbo",
            "model_name": "Z-Image-Turbo (4-bit)", "prompt": "ink fox", "seed": 42, "license": "x",
            "motion": move}


def test_qc_checks_motion_records_and_warns_on_fallback(tmp_path: Path) -> None:
    image = _image(tmp_path, "a")
    request = wan.request_for("a", image, None, "", "fox")
    wan_move = wan.credit({"prompt": request.prompt, "params": {"seed": 42}})
    px_move = parallax.credit({"params": {}, "stats": {}})
    ok = qc.ai_image_findings([_entry("a", wan_move), _entry("b", px_move)])
    assert [f.level for f in ok] == ["ok", "ok"] and "parallax, wan" in ok[0].message
    unseeded = qc.ai_image_findings([_entry("a", {**wan_move, "seed": None})])
    assert any(f.level == "error" and "a" in f.message for f in unseeded)
    four = qc.ai_image_findings([_entry(s, wan_move) for s in "abcd"])
    assert any(f.level == "error" and "4 Wan clips" in f.message for f in four)
    fell = qc.ai_image_findings([_entry("a", {**px_move, "requested": "wan", "fallback_reason": "not baked"})])
    assert [f.level for f in fell] == ["warn", "ok"]


def test_credits_text_names_the_motion_model_and_depth_tool() -> None:
    text = credits_text([_entry("a", wan.credit({"params": {}})), _entry("b", parallax.credit({}))])
    assert "Wan2.2-TI2V-5B" in text and "Wan-AI/Wan2.2-TI2V-5B" in text
    assert "Depth Anything V2 Small（工具）" in text and "Z-Image-Turbo" in text


def test_a_baked_wan_clip_reruns_media_but_parallax_cache_does_not() -> None:
    [media] = [step for step in EXPLAINER_STEPS if step.name == "media"]
    assert "assets/ai_motion/*.wan.*" in media.inputs
    assert not any("parallax" in pattern or pattern == "assets/ai_motion/*" for pattern in media.inputs)


# --- ffmpeg --------------------------------------------------------------------------------

def test_motion_loop_fills_the_slot_exactly(tmp_path: Path) -> None:
    src = tmp_path / "src.mp4"
    ffmpeg_ops.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=832x480:rate=24", "-frames:v", "25",
                    "-pix_fmt", "yuv420p", str(src)])
    out = ffmpeg_ops.motion_loop(src, None, tmp_path / "out.mp4", 2.5, retime_fps=24)
    info = ffmpeg_ops.probe(out)
    assert (info["width"], info["height"]) == (1920, 1080)
    frames = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                             "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(out)],
                            capture_output=True, text=True, check=True).stdout.strip()
    assert int(frames) == ffmpeg_ops.frame_count(2.5)  # 25 source frames, ping-ponged past the end
