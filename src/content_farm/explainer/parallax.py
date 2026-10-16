"""2.5D parallax: the default motion for every ``ai_image`` slide (decision 2bacb8a2b8b0).

One ≤3 s clip per still, built by ``scripts/motion_parallax_worker.py`` in the mlx-video venv
(Depth Anything V2 **Small**, Apache-2.0, ~1.6 GB peak, ~3–5 s per clip) and cached in
``assets/ai_motion/<slide>.parallax.{mp4,json}``. The worker's thin-object mitigation is on
by default; see its docstring. The media step then ping-pongs the clip over the slot.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from content_farm.explainer.motion_cache import (
    MAX_MOTION_SECONDS,
    MotionPaths,
    cache_key,
    clip_paths,
    file_sha256,
    read_cached,
    write_record,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKER = REPO_ROOT / "scripts" / "motion_parallax_worker.py"
KIND = "parallax"
WORKER_TIMEOUT_SECONDS = 300
DEPTH_TOOL = {
    "name": "Depth Anything V2 Small",
    "repo": "depth-anything/Depth-Anything-V2-Small-hf",
    "license": "Apache-2.0",
    "license_url": "https://github.com/DepthAnything/Depth-Anything-V2#license",
}

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class ParallaxParams:
    """Lower than the trial (zoom 0.12 / pan 0.06): thin shapes stretched there."""

    seconds: float = MAX_MOTION_SECONDS
    zoom: float = 0.06
    pan_x: float = 0.02
    pan_y: float = 0.0
    thin_px: int = 31          # near structures narrower than this ride with the background
    max_shift_px: float = 18.0  # cap on depth-dependent movement at 1920 wide
    width: int = 1920
    height: int = 1080
    fps: int = 30

    def __post_init__(self) -> None:
        if not 0 < self.seconds <= MAX_MOTION_SECONDS:
            raise ValueError(f"parallax clip must be ≤{MAX_MOTION_SECONDS}s, got {self.seconds}")


def params_for(slide_index: int) -> ParallaxParams:
    """Alternate the drift direction from slide to slide so consecutive stills do not all slide
    the same way."""
    return ParallaxParams(pan_x=0.02 if slide_index % 2 else -0.02)


def argv(paths: MotionPaths, image: Path, out: Path, params: ParallaxParams) -> list[str]:
    return [str(paths.python), str(WORKER), "--image", str(image), "--out", str(out),
            "--depth-model", str(paths.depth_model), "--width", str(params.width),
            "--height", str(params.height), "--fps", str(params.fps), "--seconds", str(params.seconds),
            "--zoom", str(params.zoom), "--pan-x", str(params.pan_x), "--pan-y", str(params.pan_y),
            "--thin-px", str(params.thin_px), "--max-shift-px", str(params.max_shift_px)]


def key_for(image_sha: str, params: ParallaxParams) -> str:
    return cache_key(kind=KIND, image=image_sha, depth=DEPTH_TOOL["repo"], params=asdict(params))


def ensure_clip(paths: MotionPaths, run_dir: Path, slide_id: str, image: Path, params: ParallaxParams,
                run: Runner | None = None) -> tuple[Path, dict]:
    """The cached clip, or a new one. Raises RuntimeError when the worker fails."""
    image_sha = file_sha256(image)
    key = key_for(image_sha, params)
    cached = read_cached(run_dir, slide_id, KIND, key)
    if cached is not None:
        return cached[0], {**cached[1], "from_cache": True}
    out, _ = clip_paths(run_dir, slide_id, KIND)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = (run or subprocess.run)(argv(paths, image, out, params), capture_output=True, text=True,
                   timeout=WORKER_TIMEOUT_SECONDS, env=_offline_env())
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"parallax worker failed to run: {exc}") from exc
    stats = _last_json(proc.stdout)
    if proc.returncode != 0 or stats is None or not out.is_file():
        tail = (proc.stderr or proc.stdout or "")[-600:]
        raise RuntimeError(f"parallax worker exit {proc.returncode}: {tail}")
    record = {"key": key, "kind": KIND, "slide_id": slide_id, "image": image.name, "image_sha256": image_sha,
              "depth_model": DEPTH_TOOL, "params": asdict(params), "stats": stats}
    write_record(run_dir, slide_id, KIND, record)
    return out, {**record, "from_cache": False}


def credit(record: dict) -> dict:
    """What credits.json keeps: the tool (not a source) and the parameters."""
    stats = record.get("stats", {})
    return {"kind": KIND, "tool": DEPTH_TOOL["name"], "tool_repo": DEPTH_TOOL["repo"],
            "tool_license": DEPTH_TOOL["license"], "tool_license_url": DEPTH_TOOL["license_url"],
            "params": record.get("params", {}), "clip_seconds": stats.get("seconds"),
            "depth_strength": stats.get("depth_strength"), "thin_share": stats.get("thin_share")}


def _offline_env() -> dict[str, str]:
    return {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}


def _last_json(stdout: str) -> dict | None:
    for line in reversed((stdout or "").strip().splitlines()):
        if line.startswith("{"):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                return None
            return value if isinstance(value, dict) else None
    return None
