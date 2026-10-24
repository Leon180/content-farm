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

import json
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
MAX_WAN_PER_VIDEO = 3      # visual v4 (Leon 2026-10-24): 2–3 key shots per long video (Deck.wan_budget raises it)
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
    negative_prompt: str = ""   # empty = the model's own default; kept out of the cache key when empty

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
    chain: tuple[str, ...] = ()   # prompts of the extra segments (each starts from the previous last frame)
    t2v: bool = False             # first segment from the prompt alone; ``image`` is only the fallback still

    @property
    def segments(self) -> int:
        return 1 + len(self.chain)


def max_shots(deck) -> int:
    """How many Wan key shots a deck may ask for (3 unless it sets ``wan_budget``)."""
    return getattr(deck, "wan_budget", None) or MAX_WAN_PER_VIDEO


def build_prompt(image_prompt: str, motion_prompt: str) -> str:
    """The still's own prompt (keeps the style) plus what should move."""
    return f"{image_prompt.strip()} Motion: {(motion_prompt or DEFAULT_MOTION).strip()}".strip()


def run_limit(run_dir: Path | None) -> int:
    """The run's Wan shot limit, read straight from its deck.json (3 when absent / unreadable)."""
    try:
        value = json.loads((run_dir / "deck.json").read_text(encoding="utf-8")).get("wan_budget") if run_dir else None
    except (OSError, ValueError, AttributeError):
        value = None
    return value if isinstance(value, int) and 1 <= value <= 10 else MAX_WAN_PER_VIDEO


def policy_for(run_dir: Path):
    """The run's channel Wan policy (default policy when the run has no readable channel)."""
    from content_farm.production.channels import WanPolicy, load_channel
    from content_farm.production.state import read_channel_code

    try:
        return load_channel(read_channel_code(run_dir)).wan
    except (OSError, ValueError, KeyError):
        return WanPolicy()


def request_for(slide_id: str, image: Path, image_record: dict | None, motion_prompt: str,
                fallback_prompt: str = "", policy=None, *, chain: tuple[str, ...] = (),
                t2v: bool = False) -> WanRequest:
    record = image_record or {}
    if policy is not None and policy.motion_only:
        prompt = (motion_prompt or DEFAULT_MOTION).strip()
    else:
        prompt = build_prompt(str(record.get("prompt") or fallback_prompt), motion_prompt)
    for text in (prompt, *chain):
        bad = forbidden_prompt_terms(text)
        if bad:
            raise ValueError(f"slide {slide_id}: Wan prompt asks for {bad} (rule: 非擬真、不模仿畫家)")
    seed = record.get("seed")
    negative = policy.negative_prompt if policy is not None else ""
    return WanRequest(slide_id, image, prompt,
                      WanParams(seed=seed if isinstance(seed, int) else 42, negative_prompt=negative),
                      tuple(c.strip() for c in chain), t2v)


def key_for(request: WanRequest, image_sha: str) -> str:
    params = asdict(request.params)
    if not params["negative_prompt"]:
        params.pop("negative_prompt")        # keep the keys of clips baked before the field existed
    extra = {}                               # likewise: single image-to-video clips keep their old keys
    if request.chain:
        extra["chain"] = list(request.chain)
    if request.t2v:
        extra["t2v"] = True
        image_sha = "t2v"
    return cache_key(kind=KIND, image=image_sha, model=WAN_MODEL["id"], prompt=request.prompt, params=params,
                     **extra)


def cached(run_dir: Path, request: WanRequest) -> tuple[Path, dict] | None:
    if not request.image.is_file():
        return None
    return read_cached(run_dir, request.slide_id, KIND, key_for(request, file_sha256(request.image)))


def argv(paths: MotionPaths, request: WanRequest, out: Path, *, image: Path | None = None,
         prompt: str | None = None) -> list[str]:
    """``image``/``prompt`` override the request's for a chained segment (its start frame, its prompt)."""
    p = request.params
    start = image or (None if request.t2v else request.image)
    return [str(paths.python), "-m", "mlx_video.models.wan_2.generate", "--model-dir", str(paths.wan_model),
            "--prompt", prompt or request.prompt, *(["--image", str(start)] if start else []),
            "--width", str(p.width),
            "--height", str(p.height), "--num-frames", str(p.num_frames), "--steps", str(p.steps),
            "--guide-scale", str(p.guide_scale), "--tiling", p.tiling, "--seed", str(p.seed),
            "--output-path", str(out), *(["--negative-prompt", p.negative_prompt] if p.negative_prompt else [])]


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
            "upscaled_to": [1920, 1080], "segments": record.get("segments", 1),
            "chain_prompts": record.get("chain_prompts", []), "t2v": record.get("t2v", False)}


Gate = Callable[[], float]


def run_segment(paths: MotionPaths, request: WanRequest, out: Path, *, image: Path | None = None,
                prompt: str | None = None, run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                ) -> dict:
    """One Wan process (blocking, ~15 min): the clip at ``out`` plus its timing / memory numbers."""
    out.parent.mkdir(parents=True, exist_ok=True)
    swap_before, started = _swap_used_mb(), time.monotonic()
    proc = run(argv(paths, request, out, image=image, prompt=prompt), capture_output=True, text=True,
               timeout=GENERATE_TIMEOUT_SECONDS, env={**os.environ, "HF_HUB_OFFLINE": "1"})
    seconds = round(time.monotonic() - started, 1)
    log = (proc.stdout or "") + (proc.stderr or "")
    out.with_suffix(".log").write_text(log, encoding="utf-8")
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError(f"Wan failed for {request.slide_id} (rc={proc.returncode}): {log[-600:]}")
    peak = _PEAK.findall(log)
    return {"seconds": seconds, "reported_peak_gb": float(peak[-1]) if peak else None,
            "swap_before_mb": swap_before, "swap_after_mb": _swap_used_mb()}


def generate(paths: MotionPaths, run_dir: Path, request: WanRequest, gate: Gate,
             run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict:
    """Make one clip (blocking, ~15 min per segment). ``gate`` waits until the machine is free and
    returns the seconds waited; it must be called inside the render lock. A request with chained
    segments or text-to-video goes through :mod:`wan_chain`."""
    missing = paths.problems(wan=True)
    if missing:
        raise FileNotFoundError("; ".join(missing))
    if request.segments > 1 or request.t2v:
        from content_farm.explainer import wan_chain

        return wan_chain.generate_chain(paths, run_dir, request, gate, run)
    image_sha = file_sha256(request.image)
    out, _ = clip_paths(run_dir, request.slide_id, KIND)
    waited = gate()
    measured = run_segment(paths, request, out, run=run)
    record = {"key": key_for(request, image_sha), "kind": KIND, "slide_id": request.slide_id,
              "image": request.image.name, "image_sha256": image_sha, "model": WAN_MODEL,
              "prompt": request.prompt, "params": asdict(request.params), "seconds": measured["seconds"],
              "gate_wait_seconds": waited, "reported_peak_gb": measured["reported_peak_gb"],
              "swap_before_mb": measured["swap_before_mb"], "swap_after_mb": measured["swap_after_mb"]}
    write_record(run_dir, request.slide_id, KIND, record)
    return record
