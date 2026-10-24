"""Picture-book pictures for a fable: one local-model image per drawn shot, each moved by 2.5D depth parallax.

``fable.json`` shots with an ``image_prompt`` are drawn (channel style prefix + the prompt) into
``assets/ai_images/b<beat>_<n>.png`` with a sidecar (model, prompt, seed, licence). Every picture then gets a
depth-parallax clip at the video's frame size (``assets/ai_motion``); ``assets/fable/clips.json`` maps each shot id
(``b3.1``, ``reuse`` resolved) to its image and clip. A missing depth tool is an error — a still would pass
for a moving picture otherwise (visual v4 lesson).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from content_farm.explainer.ai_images import AI_IMAGE_DIR, find_image
from content_farm.explainer.illustrate import (
    AI_LABEL,
    IllustrationRequest,
    LocalMflux,
    forbidden_prompt_terms,
    load_record,
    sidecar_for,
)
from content_farm.explainer.motion_cache import MotionPaths
from content_farm.explainer.parallax import ParallaxParams, credit as parallax_credit, ensure_clip
from content_farm.production.channels import Channel
from content_farm.production.fable.model import Fable
from content_farm.production.news.visuals import env_with_file, resolve_paths

MANIFEST = Path("assets") / "fable" / "clips.json"
FRAME = {"short": (1080, 1920), "mid": (1920, 1080)}          # video frame
DRAW = {"short": (720, 1280), "mid": (1280, 720)}             # model size (multiples of 16)
FPS = 30


@dataclass(frozen=True)
class DrawnShot:
    shot_id: str          # "b3.1"
    image_id: str         # "b3_1" (file stem)
    prompt: str


def drawn_shots(fable: Fable) -> list[DrawnShot]:
    return [DrawnShot(f"{b.id}.{n}", f"{b.id}_{n}", s.image_prompt.strip())
            for b in fable.beats for n, s in enumerate(b.shots, 1) if s.image_prompt.strip()]


def resolve(fable: Fable) -> dict[str, str]:
    """Every shot id → the drawn shot id whose picture it shows (itself, or its ``reuse`` target)."""
    mapping = {}
    for b in fable.beats:
        for n, s in enumerate(b.shots, 1):
            mapping[f"{b.id}.{n}"] = s.reuse or f"{b.id}.{n}"
    return mapping


def requests_for(fable: Fable, channel: Channel) -> list[IllustrationRequest]:
    cfg = channel.ai_illustration
    width, height = DRAW[fable.format]
    out = []
    for index, shot in enumerate(drawn_shots(fable)):
        bad = forbidden_prompt_terms(shot.prompt)
        if bad:
            raise ValueError(f"{shot.shot_id}: image_prompt asks for {bad} (rule: 非擬真、不模仿畫家)")
        out.append(IllustrationRequest(shot.image_id, f"{cfg.style_prefix.strip()} {shot.prompt}".strip(),
                                       cfg.seed + index, width, height))
    return out


def draw_missing(run_dir: Path, fable: Fable, channel: Channel, env_file: Path | None = None, provider=None) -> int:
    """Draw every picture still missing, one at a time; returns how many were drawn now."""
    folder = run_dir / AI_IMAGE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    todo = [r for r in requests_for(fable, channel) if find_image(folder, r.slide_id) is None]
    if todo and provider is None:
        provider = LocalMflux.from_env(channel.ai_illustration.model, env_with_file(env_file))
    for request in todo:
        out = folder / f"{request.slide_id}.png"
        record = {"slide_id": request.slide_id, **provider.generate(request, out), "prompt": request.prompt,
                  "seed": request.seed, "size": [request.width, request.height], "ai_label": AI_LABEL}
        sidecar_for(out).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(todo)


def make_clips(run_dir: Path, fable: Fable, paths: MotionPaths, ensure=ensure_clip) -> dict[str, dict]:
    """A parallax clip per drawn picture at the frame size: ``{image_id: {"image", "clip", "motion"}}``."""
    width, height = FRAME[fable.format]
    out: dict[str, dict] = {}
    for index, shot in enumerate(drawn_shots(fable)):
        image = find_image(run_dir / AI_IMAGE_DIR, shot.image_id)
        if image is None:
            raise FileNotFoundError(f"picture {shot.image_id} was not drawn")
        params = ParallaxParams(width=width, height=height, fps=FPS, pan_x=0.02 if index % 2 else -0.02)
        clip, record = ensure(paths, run_dir, shot.image_id, image, params)
        out[shot.image_id] = {"image": image.name, "clip": clip.relative_to(run_dir).as_posix() if clip.is_relative_to(run_dir) else str(clip),
                              "motion": parallax_credit(record)}
    return out


def write_manifest(run_dir: Path, fable: Fable, clips: dict[str, dict]) -> Path:
    shots = {sid: {"draws": drawn, "image_id": drawn.replace(".", "_")} for sid, drawn in resolve(fable).items()}
    path = run_dir / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "format": fable.format, "frame": FRAME[fable.format], "shots": shots,
                                "clips": clips}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / MANIFEST).read_text(encoding="utf-8"))


def build(run_dir: Path, fable: Fable, channel: Channel, env_file: Path | None = None) -> tuple[Path, int]:
    """Pictures and clips for the whole fable; returns (manifest path, pictures drawn now)."""
    paths = resolve_paths(env_file)
    if paths is None:
        raise RuntimeError("depth-parallax tool not configured (CF_MLX_VIDEO_HOME / CF_DEPTH_*): "
                           "refusing to ship still pictures as moving ones")
    drawn = draw_missing(run_dir, fable, channel, env_file)
    return write_manifest(run_dir, fable, make_clips(run_dir, fable, paths)), drawn


def credit_entries(run_dir: Path, fable: Fable, clips: dict[str, dict]) -> list[dict]:
    keep = ("provider", "model", "model_name", "repo", "origin_repo", "license_url", "seed", "steps", "size")
    entries = []
    for number, shot in enumerate(drawn_shots(fable), 1):
        info = clips[shot.image_id]
        record = load_record(run_dir / AI_IMAGE_DIR / info["image"]) or {}
        model = record.get("model_name") or record.get("model")
        licence = (f"AI-generated ({model}; model licence {record['license']}) for this channel"
                   if model and record.get("license") else "AI-generated for this channel (generator unrecorded)")
        entries.append({"slide_id": shot.image_id, "slide_index": number, "kind": "ai_image", "file": info["image"],
                        "license": licence, "ai_generated": True, "ai_label": AI_LABEL,
                        "prompt": record.get("prompt") or shot.prompt, **{k: record[k] for k in keep if k in record},
                        "motion": info["motion"]})
    return entries
