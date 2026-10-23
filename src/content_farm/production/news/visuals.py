"""AI pictures for the HN-style news Shorts (visual v4, Leon 2026-10-24: "不再只有文字卡").

Every Short whose channel allows AI illustration shows at least ``MIN_AI_BEATS`` of its five beats over a picture, and
every picture moves (2.5D depth parallax, the same Depth Anything V2 Small worker the long videos use):

1. ``news_script.json`` beats carry ``image_prompt`` (English, content only; the channel's style prefix is added);
2. :func:`ensure_images` draws the missing ones with the channel's local model, one at a time, into
   ``assets/ai_images/beat<N>.png`` + a sidecar (model, prompt, seed, licence, as for long videos);
3. :func:`ensure_motion` makes a portrait parallax clip per picture (``assets/ai_motion``) and unpacks it into JPEG
   frames under ``short/frames/beat<N>/`` — the beat page swaps frames inside ``__anim.seek`` (ping-pong), so the
   frame-exact page capture needs no ``<video>``;
4. :func:`credit_entries` puts every picture in ``credits.json`` (model, prompt, seed, the 「AI 示意圖」 badge, motion).

Without a configured depth tool a picture falls back to a still (flat zoom in the page) and QC warns.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
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
from content_farm.explainer.motion_cache import MotionPaths, motion_env
from content_farm.explainer.parallax import ParallaxParams, credit as parallax_credit, ensure_clip
from content_farm.production.channels import Channel
from content_farm.production.news import script as ns

MIN_AI_BEATS = 3
PIC_W, PIC_H = 988, 898                  # inside the 1000x910 beat card (6 px border each side)
GEN_W, GEN_H = 1024, 944                 # model size (multiples of 16), cover-cropped to the card
FRAMES_DIR = Path("short") / "frames"
FPS = 30


def resolve_paths(env_file: Path | None = None) -> MotionPaths | None:
    """The depth tool's paths from the environment / dotenv, or None when it is not installed."""
    paths = MotionPaths.from_env(motion_env(env_file))
    return paths if paths is not None and not paths.problems() else None


def env_with_file(env_file: Path | None) -> dict[str, str]:
    """``os.environ`` plus the machine-path keys (CF_MFLUX_*, CF_MLX_*, CF_DEPTH_*, CF_WAN_*) from ``env_file``."""
    import os

    env = dict(os.environ)
    if env_file is not None and env_file.is_file():
        from dotenv import dotenv_values

        for key, value in dotenv_values(env_file).items():
            if value and not env.get(key) and key.startswith(("CF_MFLUX", "CF_MLX", "CF_DEPTH", "CF_WAN")):
                env[key] = value
    return env


def image_id(index: int) -> str:
    """File stem of beat ``index`` (0-based): ``beat1`` … ``beat5``."""
    return f"beat{index + 1}"


def ai_beats(news: ns.NewsScript) -> list[int]:
    return [i for i, beat in enumerate(news.beats) if beat.image_prompt.strip()]


def needs_pictures(channel: Channel) -> bool:
    return bool(channel.media.ai_image) and getattr(channel, "ai_illustration", None) is not None


def problems(news: ns.NewsScript, channel: Channel) -> list[str]:
    """Why this script cannot ship as a picture Short ([] = fine, or the channel shows no AI pictures)."""
    if not needs_pictures(channel):
        return []
    out = []
    if len(ai_beats(news)) < MIN_AI_BEATS:
        out.append(f"news_script.json: {len(ai_beats(news))} beat(s) with image_prompt; need >= {MIN_AI_BEATS} "
                   "(every Short shows at least 3 AI pictures, moved by parallax)")
    for i in ai_beats(news):
        bad = forbidden_prompt_terms(news.beats[i].image_prompt)
        if bad:
            out.append(f"beat {i + 1}: image_prompt asks for {bad} (rule: 非擬真、不模仿畫家)")
    return out


def requests_for(news: ns.NewsScript, channel: Channel) -> list[IllustrationRequest]:
    cfg = channel.ai_illustration
    return [IllustrationRequest(image_id(i), f"{cfg.style_prefix.strip()} {news.beats[i].image_prompt.strip()}".strip(),
                                cfg.seed + i, GEN_W, GEN_H) for i in ai_beats(news)]


def ensure_images(run_dir: Path, news: ns.NewsScript, channel: Channel, provider=None,
                  env_file: Path | None = None) -> list[dict]:
    """Draw every beat picture still missing; returns the new records. Prompts are checked before any model loads."""
    if (bad := problems(news, channel)):
        raise ValueError("; ".join(bad))
    requests = requests_for(news, channel)
    folder = run_dir / AI_IMAGE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    todo = [r for r in requests if find_image(folder, r.slide_id) is None]
    if not todo:
        return []
    if provider is None:
        provider = LocalMflux.from_env(channel.ai_illustration.model, env_with_file(env_file))
    records = []
    for request in todo:
        out = folder / f"{request.slide_id}.png"
        record = {"slide_id": request.slide_id, **provider.generate(request, out), "prompt": request.prompt,
                  "seed": request.seed, "size": [request.width, request.height], "ai_label": AI_LABEL}
        sidecar_for(out).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        records.append(record)
    return records


@dataclass(frozen=True)
class BeatPicture:
    index: int
    image: Path
    frames: tuple[str, ...]          # page-relative JPEG frame paths ("frames/beat1/f001.jpg"); () = still
    motion: dict                     # the credit's ``motion`` block


def _unpack(clip: Path, out_dir: Path, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = run(["ffmpeg", "-y", "-i", str(clip), "-vf", f"scale={PIC_W}:{PIC_H}:force_original_aspect_ratio=increase,"
                f"crop={PIC_W}:{PIC_H}", "-q:v", "4", str(out_dir / "f%03d.jpg")], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg could not unpack {clip.name}: {proc.stderr[-300:]}")
    return sorted(p.name for p in out_dir.glob("f*.jpg"))


def ensure_motion(run_dir: Path, news: ns.NewsScript, *, paths: MotionPaths | None = None,
                  env_file: Path | None = None,
                  ensure: Callable[..., tuple[Path, dict]] = ensure_clip) -> dict[int, BeatPicture]:
    """A parallax clip per picture, unpacked to frames. A missing depth tool or a failed clip leaves the picture
    still (``frames=()``) with ``motion.fallback_reason`` set; nothing here stops the Short."""
    paths = paths if paths is not None else resolve_paths(env_file)   # motion_env reads os.environ, then env_file
    folder = run_dir / AI_IMAGE_DIR
    out: dict[int, BeatPicture] = {}
    for i in ai_beats(news):
        image = find_image(folder, image_id(i))
        if image is None:
            continue
        params = ParallaxParams(width=PIC_W, height=PIC_H, fps=FPS, pan_x=0.02 if i % 2 else -0.02)
        try:
            if paths is None:
                raise RuntimeError("motion tools not configured (CF_MLX_VIDEO_HOME)")
            clip, record = ensure(paths, run_dir, image_id(i), image, params)
            names = _unpack(clip, run_dir / FRAMES_DIR / image_id(i))
            frames = tuple(f"frames/{image_id(i)}/{name}" for name in names)
            motion = parallax_credit(record)
        except (RuntimeError, OSError) as exc:
            frames, motion = (), {"kind": "still", "fallback_reason": str(exc)[:200]}
        out[i] = BeatPicture(i, image, frames, motion)
    return out


def credit_entries(run_dir: Path, news: ns.NewsScript, pictures: dict[int, BeatPicture]) -> list[dict]:
    keep = ("provider", "model", "model_name", "repo", "origin_repo", "license_url", "seed", "steps", "size")
    entries = []
    for i, pic in sorted(pictures.items()):
        record = load_record(pic.image) or {}
        model = record.get("model_name") or record.get("model")
        licence = (f"AI-generated ({model}; model licence {record['license']}) for this channel"
                   if model and record.get("license") else "AI-generated for this channel (generator unrecorded)")
        entries.append({"slide_id": image_id(i), "slide_index": i + 1, "kind": "ai_image", "file": pic.image.name,
                        "license": licence, "ai_generated": True, "ai_label": AI_LABEL,
                        "prompt": record.get("prompt") or news.beats[i].image_prompt,
                        **{k: record[k] for k in keep if k in record}, "motion": pic.motion})
    return entries
