"""Longer Wan shots: chain 2.9 s segments into one continuous 6–9 s shot, and text-to-video starts.

A single Wan clip is capped at 69 frames (≈2.9 s; longer costs memory and time, REPORT-ai-video-trial
§5). To get a longer take, each next segment starts from the *last frame* of the previous one and
has its own motion prompt; the segments are then joined, dropping each continuation's first frame
(it repeats the previous last frame). ``media.wan_chain`` lists the extra prompts (≤2 → ≤3 segments
≈ 8.5 s); ``media.wan_t2v`` makes the first segment from the prompt alone.

Every segment is cached on its own (``<slide>.wan.seg<k>.{mp4,json}``, keyed by its start frame,
prompt and parameters), so an interrupted overnight bake resumes at the segment it stopped in.
The joined clip lands where a single clip would (``<slide>.wan.{mp4,json}``).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from content_farm.explainer import wan
from content_farm.explainer.motion_cache import (
    MOTION_DIR,
    MotionPaths,
    cache_key,
    clip_paths,
    file_sha256,
    write_record,
)

FPS = 24
CONCAT_CRF = 12   # near-lossless: the joined clip is only an intermediate before the 1080p upscale


def segment_paths(run_dir: Path, slide_id: str, index: int) -> tuple[Path, Path, Path]:
    """Clip, sidecar and last-frame still of segment ``index`` (0-based)."""
    folder = run_dir / MOTION_DIR
    stem = f"{slide_id}.wan.seg{index}"
    return folder / f"{stem}.mp4", folder / f"{stem}.json", folder / f"{stem}.last.png"


def segment_key(request: wan.WanRequest, index: int, start_sha: str, prompt: str) -> str:
    params = asdict(request.params)
    if not params["negative_prompt"]:
        params.pop("negative_prompt")
    return cache_key(kind="wan-segment", index=index, start=start_sha, prompt=prompt,
                     model=wan.WAN_MODEL["id"], params=params)


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{args[0]} failed: {proc.stderr[-400:]}")


def last_frame(clip: Path, out: Path, num_frames: int) -> Path:
    """The clip's final frame as a PNG (exact index, not a seek that can land one frame short)."""
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), "-vf", f"select=eq(n\\,{num_frames - 1})",
          "-frames:v", "1", "-fps_mode", "passthrough", str(out)])
    if not out.is_file():
        raise RuntimeError(f"no frame {num_frames - 1} in {clip.name}")
    return out


def concat_args(clips: list[Path], out: Path) -> list[str]:
    """ffmpeg arguments joining ``clips``; every clip after the first loses its (repeated) first frame."""
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for clip in clips:
        args += ["-i", str(clip)]
    trims = [f"[{i}:v]{'trim=start_frame=1,' if i else ''}setpts=PTS-STARTPTS,fps={FPS}[v{i}]"
             for i in range(len(clips))]
    joined = "".join(f"[v{i}]" for i in range(len(clips)))
    graph = ";".join([*trims, f"{joined}concat=n={len(clips)}:v=1:a=0[v]"])
    return [*args, "-filter_complex", graph, "-map", "[v]", "-c:v", "libx264", "-crf", str(CONCAT_CRF),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]


def joined_frames(segments: int, num_frames: int) -> int:
    return num_frames + (segments - 1) * (num_frames - 1)


def _read(sidecar: Path) -> dict | None:
    if not sidecar.is_file():
        return None
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _segment(paths: MotionPaths, run_dir: Path, request: wan.WanRequest, index: int, start: Path | None,
             gate: wan.Gate, run: Callable[..., subprocess.CompletedProcess]) -> dict:
    prompt = request.prompt if index == 0 else request.chain[index - 1]
    start_sha = file_sha256(start) if start else "t2v"
    clip, sidecar, last = segment_paths(run_dir, request.slide_id, index)
    key = segment_key(request, index, start_sha, prompt)
    previous = _read(sidecar)
    if previous and previous.get("key") == key and clip.is_file():
        record = {**previous, "from_cache": True, "gate_wait_seconds": 0.0}
    else:
        waited = gate()
        measured = wan.run_segment(paths, request, clip, image=start, prompt=prompt, run=run)
        record = {"key": key, "index": index, "prompt": prompt, "start_sha256": start_sha,
                  "gate_wait_seconds": waited, "from_cache": False, **measured}
        sidecar.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    last_frame(clip, last, request.params.num_frames)
    return record


def generate_chain(paths: MotionPaths, run_dir: Path, request: wan.WanRequest, gate: wan.Gate,
                   run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict:
    """Make (or resume) every segment, join them, and write the joined clip's record."""
    segments: list[dict] = []
    start: Path | None = None if request.t2v else request.image
    for index in range(request.segments):
        record = _segment(paths, run_dir, request, index, start, gate, run)
        segments.append(record)
        start = segment_paths(run_dir, request.slide_id, index)[2]
    out, _ = clip_paths(run_dir, request.slide_id, wan.KIND)
    _run(concat_args([segment_paths(run_dir, request.slide_id, i)[0] for i in range(request.segments)], out))
    frames = joined_frames(request.segments, request.params.num_frames)
    image_sha = file_sha256(request.image)
    peaks = [s["reported_peak_gb"] for s in segments if s.get("reported_peak_gb") is not None]
    record = {"key": wan.key_for(request, image_sha), "kind": wan.KIND, "slide_id": request.slide_id,
              "image": request.image.name, "image_sha256": image_sha, "model": wan.WAN_MODEL,
              "prompt": request.prompt, "params": asdict(request.params), "segments": request.segments,
              "chain_prompts": list(request.chain), "t2v": request.t2v, "frames": frames,
              "seconds": round(sum(s["seconds"] for s in segments if not s.get("from_cache")), 1),
              "segment_seconds": [s["seconds"] for s in segments],
              "gate_wait_seconds": round(sum(s["gate_wait_seconds"] for s in segments), 1),
              "reported_peak_gb": max(peaks) if peaks else None,
              "swap_before_mb": segments[0].get("swap_before_mb"), "swap_after_mb": segments[-1].get("swap_after_mb")}
    write_record(run_dir, request.slide_id, wan.KIND, record)
    return record
