"""Wan2.2-TI2V-5B image-to-video for key shots (``media.motion: wan``, at most 2 per video).

A Wan clip is ~15 minutes and ~26 GB peak on a 32 GB M-series Mac (REPORT-ai-video-trial §3),
so it is never made inside a render: ``scripts/ai_motion.py bake`` makes them beforehand
(overnight), one at a time, only while no other render / mflux / mlx_video process runs, and
caches them in ``assets/ai_motion/<slide>.wan.{mp4,json}``. The media step only reads that
cache; a missing or stale clip falls back to parallax (QC warns).

Clip: 832×480, 69 frames @24 fps (2.875 s ≤ 3 s), 20 UniPC steps, guide 5.0, aggressive VAE
tiling (the trial's settings); upscaled to 1920×1080 when placed on the timeline.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from content_farm.explainer.illustrate import _swap_used_mb, forbidden_prompt_terms
from content_farm.explainer.motion_cache import (
    MAX_MOTION_SECONDS,
    MotionPaths,
    cache_key,
    clip_paths,
    file_sha256,
    read_cached,
    write_record,
)

KIND = "wan"
MAX_WAN_PER_VIDEO = 2
GENERATE_TIMEOUT_SECONDS = 1800
ESTIMATED_MINUTES_PER_CLIP = 15  # trial: 12.6–17.7 min per 69-frame clip
WAN_MODEL = {
    "id": "wan22-ti2v-5b-q8",
    "name": "Wan2.2-TI2V-5B (MLX q8)",
    "repo": "Anes1032/Wan2.2-TI2V-5B-mlx-q8",
    "origin_repo": "Wan-AI/Wan2.2-TI2V-5B",
    "license": "Apache-2.0",
    "license_url": "https://github.com/Wan-Video/Wan2.2/blob/main/LICENSE.txt",
}
DEFAULT_MOTION = "the scene comes to life with gentle, subtle natural motion, mist drifting, static camera"
# Executables / scripts that mean someone else is rendering or running a local model.
RENDER_EXECUTABLES = ("ffmpeg", "remotion")
MODEL_MARKERS = ("mflux", "mlx_video")
_PEAK = re.compile(r"[Pp]eak[^\n]*?([\d.]+)\s*GB")


@dataclass(frozen=True)
class WanParams:
    width: int = 832
    height: int = 480
    num_frames: int = 69   # 4n+1
    fps: int = 24
    steps: int = 20
    guide_scale: float = 5.0
    tiling: str = "aggressive"
    seed: int = 42

    def __post_init__(self) -> None:
        if (self.num_frames - 1) % 4:
            raise ValueError("Wan num_frames must be 4n+1")
        if self.num_frames / self.fps > MAX_MOTION_SECONDS:
            raise ValueError(f"Wan clip must be ≤{MAX_MOTION_SECONDS}s")
        if self.width % 32 or self.height % 32:
            raise ValueError("Wan width/height must be multiples of 32")


@dataclass(frozen=True)
class WanRequest:
    slide_id: str
    image: Path
    prompt: str
    params: WanParams


def build_prompt(image_prompt: str, motion_prompt: str) -> str:
    """The still's own prompt (keeps the style) plus what should move."""
    return f"{image_prompt.strip()} Motion: {(motion_prompt or DEFAULT_MOTION).strip()}".strip()


def request_for(slide_id: str, image: Path, image_record: dict | None, motion_prompt: str,
                fallback_prompt: str = "") -> WanRequest:
    record = image_record or {}
    prompt = build_prompt(str(record.get("prompt") or fallback_prompt), motion_prompt)
    bad = forbidden_prompt_terms(prompt)
    if bad:
        raise ValueError(f"slide {slide_id}: Wan prompt asks for {bad} (rule: 非擬真、不模仿畫家)")
    seed = record.get("seed")
    return WanRequest(slide_id, image, prompt, WanParams(seed=seed if isinstance(seed, int) else 42))


def key_for(request: WanRequest, image_sha: str) -> str:
    return cache_key(kind=KIND, image=image_sha, model=WAN_MODEL["id"], prompt=request.prompt,
                     params=asdict(request.params))


def cached(run_dir: Path, request: WanRequest) -> tuple[Path, dict] | None:
    if not request.image.is_file():
        return None
    return read_cached(run_dir, request.slide_id, KIND, key_for(request, file_sha256(request.image)))


def argv(paths: MotionPaths, request: WanRequest, out: Path) -> list[str]:
    p = request.params
    return [str(paths.python), "-m", "mlx_video.models.wan_2.generate", "--model-dir", str(paths.wan_model),
            "--prompt", request.prompt, "--image", str(request.image), "--width", str(p.width),
            "--height", str(p.height), "--num-frames", str(p.num_frames), "--steps", str(p.steps),
            "--guide-scale", str(p.guide_scale), "--tiling", p.tiling, "--seed", str(p.seed),
            "--output-path", str(out)]


def busy_processes(own_pids: set[int], ps_output: str | None = None) -> list[str]:
    """Command lines of other renders / local models (the gate's ``pgrep -f
    'mflux|mlx_video|ffmpeg'``, matched on the executable and script so a process that merely
    mentions those words in an argument does not block)."""
    if ps_output is None:
        ps_output = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True,
                                   check=True).stdout
    hits = []
    for line in ps_output.splitlines():
        pid_text, _, command = line.strip().partition(" ")
        if not pid_text.isdigit() or int(pid_text) in own_pids:
            continue
        if _program(command.split()).startswith((*RENDER_EXECUTABLES, *MODEL_MARKERS)):
            hits.append(command[:160])
    return hits


def _program(tokens: list[str]) -> str:
    """What a command line really runs: the executable, or for an interpreter the script it
    runs or its ``-m`` module (mflux runs as ``python …/bin/mflux-generate…``)."""
    names = [token.rsplit("/", 1)[-1] for token in tokens[:3]]
    if not names:
        return ""
    if not names[0].startswith("python") or len(names) < 2:
        return names[0]
    return names[2] if names[1] == "-m" and len(names) > 2 else names[1]


def credit(record: dict) -> dict:
    return {"kind": KIND, "model": WAN_MODEL["id"], "model_name": WAN_MODEL["name"], "repo": WAN_MODEL["repo"],
            "origin_repo": WAN_MODEL["origin_repo"], "license": WAN_MODEL["license"],
            "license_url": WAN_MODEL["license_url"], "prompt": record.get("prompt", ""),
            "seed": record.get("params", {}).get("seed"), "params": record.get("params", {}),
            "upscaled_to": [1920, 1080]}


Gate = Callable[[], float]


def generate(paths: MotionPaths, run_dir: Path, request: WanRequest, gate: Gate,
             run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict:
    """Make one clip (blocking, ~15 min). ``gate`` waits until the machine is free and returns
    the seconds waited; it must be called inside the render lock."""
    missing = paths.problems(wan=True)
    if missing:
        raise FileNotFoundError("; ".join(missing))
    image_sha = file_sha256(request.image)
    out, _ = clip_paths(run_dir, request.slide_id, KIND)
    out.parent.mkdir(parents=True, exist_ok=True)
    waited = gate()
    swap_before, started = _swap_used_mb(), time.monotonic()
    proc = run(argv(paths, request, out), capture_output=True, text=True, timeout=GENERATE_TIMEOUT_SECONDS,
               env={**os.environ, "HF_HUB_OFFLINE": "1"})
    seconds = round(time.monotonic() - started, 1)
    log = (proc.stdout or "") + (proc.stderr or "")
    out.parent.joinpath(f"{request.slide_id}.{KIND}.log").write_text(log, encoding="utf-8")
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError(f"Wan failed for {request.slide_id} (rc={proc.returncode}): {log[-600:]}")
    peak = _PEAK.findall(log)
    record = {"key": key_for(request, image_sha), "kind": KIND, "slide_id": request.slide_id,
              "image": request.image.name, "image_sha256": image_sha, "model": WAN_MODEL,
              "prompt": request.prompt, "params": asdict(request.params), "seconds": seconds,
              "gate_wait_seconds": waited, "reported_peak_gb": float(peak[-1]) if peak else None,
              "swap_before_mb": swap_before, "swap_after_mb": _swap_used_mb()}
    write_record(run_dir, request.slide_id, KIND, record)
    return record

