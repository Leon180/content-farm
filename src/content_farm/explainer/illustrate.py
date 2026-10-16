"""Generate ``ai_image`` slide illustrations with a local open model, one image at a time.

Contract with the media step (unchanged): an image at ``assets/ai_images/<slide_id>.png``.
New here: a sidecar ``<slide_id>.json`` next to it with everything needed to credit and
reproduce the picture (provider, model, origin repo and licence, prompt, seed, steps, size)
plus how the run went (seconds, swap before/after). ``media`` copies it into credits.json.

Providers sit behind :class:`IllustrationProvider` so an API or browser provider can be
added later; today there is ``local_mflux`` (mflux on Apple silicon). Machine paths are
not configuration of a channel: they come from the environment —
``CF_MFLUX_BIN_DIR`` (the venv ``bin/`` holding ``mflux-generate*``) and
``CF_MFLUX_HF_HOME`` (the Hugging Face cache holding the weights; runs offline).

Rules (Leon 2026-10-16, also in the deck skill and QC): every AI frame carries the
「AI 示意圖」 badge; AI images only where no public-domain artwork fits (mood, scene
reconstruction, transitions); illustration or ink wash, never photo-real, never "in the
style of" a living artist.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from content_farm.explainer.ai_images import AI_IMAGE_DIR, find_image
from content_farm.explainer.deck import Deck, MediaKind

logger = logging.getLogger(__name__)

AI_LABEL = "AI 示意圖"
SIDECAR_SUFFIX = ".json"
PRESSURE_WAIT_SECONDS = 30
PRESSURE_MAX_WAIT_SECONDS = 1800
# Prompts asking for photo-realism or a named artist's style break the channel rules.
_FORBIDDEN_PROMPT = re.compile(
    r"photo-?real|hyper-?real|realistic photo|photograph of|\bdslr\b|\b35 ?mm\b|"
    r"in the style of|by artist", re.IGNORECASE)


@dataclass(frozen=True)
class ModelSpec:
    """A local model checked for this channel family (licences read from the origin repo)."""

    id: str
    name: str
    command: str          # mflux entry point
    repo: str             # pre-quantized weights actually loaded
    base_model: str       # mflux built-in the repo is based on
    origin_repo: str
    license: str
    license_url: str
    steps: int


MODELS: dict[str, ModelSpec] = {
    spec.id: spec for spec in (
        ModelSpec("flux2-klein-4b", "FLUX.2 [klein] 4B (q4)", "mflux-generate-flux2",
                  "mflux-community/flux2-klein-4b-mflux-q4", "flux2-klein-4b",
                  "black-forest-labs/FLUX.2-klein-4B", "Apache-2.0",
                  "https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/main/LICENSE.md", 4),
        ModelSpec("z-image-turbo", "Z-Image-Turbo (4-bit)", "mflux-generate-z-image-turbo",
                  "filipstrand/Z-Image-Turbo-mflux-4bit", "z-image-turbo",
                  "Tongyi-MAI/Z-Image-Turbo", "Apache-2.0",
                  "https://github.com/Tongyi-MAI/Z-Image/blob/main/LICENSE", 9),
    )
}


def forbidden_prompt_terms(prompt: str) -> list[str]:
    return sorted({m.group(0).lower() for m in _FORBIDDEN_PROMPT.finditer(prompt)})


@dataclass(frozen=True)
class IllustrationRequest:
    slide_id: str
    prompt: str            # channel style prefix + the slide's prompt
    seed: int
    width: int
    height: int


class IllustrationProvider(Protocol):
    name: str

    def generate(self, request: IllustrationRequest, out: Path) -> dict:
        """Write ``out`` (PNG) and return the generation record (no image bytes)."""
        ...


def _swap_used_mb() -> float | None:
    out = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True)
    match = re.search(r"used = ([\d.]+)M", out.stdout)
    return float(match.group(1)) if match else None


def memory_pressure_level() -> int:
    """macOS ``kern.memorystatus_vm_pressure_level``: 1 normal, 2 warn, 4 critical."""
    out = subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                         capture_output=True, text=True)
    value = out.stdout.strip()
    if out.returncode != 0 or not value.isdigit():
        raise RuntimeError(f"cannot read memory pressure: {out.stderr.strip() or value!r}")
    return int(value)


def wait_for_memory(level: Callable[[], int] = memory_pressure_level,
                    sleep: Callable[[float], None] = time.sleep,
                    max_wait: float = PRESSURE_MAX_WAIT_SECONDS) -> float:
    """Block while pressure is warn or worse (another model may be running). Returns seconds waited."""
    waited = 0.0
    while level() >= 2:
        if waited >= max_wait:
            raise TimeoutError(f"memory pressure stayed at warn+ for {waited:.0f}s; not loading a model")
        logger.info("memory pressure warn+; waiting %ss before loading the model", PRESSURE_WAIT_SECONDS)
        sleep(PRESSURE_WAIT_SECONDS)
        waited += PRESSURE_WAIT_SECONDS
    return waited


@dataclass(frozen=True)
class LocalMflux:
    """mflux CLI, one process per image so the weights are unloaded when it exits."""

    model: ModelSpec
    bin_dir: Path
    hf_home: Path
    name: str = "local_mflux"

    @classmethod
    def from_env(cls, model_id: str, env: Mapping[str, str] = os.environ) -> LocalMflux:
        missing = [key for key in ("CF_MFLUX_BIN_DIR", "CF_MFLUX_HF_HOME") if not env.get(key)]
        if missing:
            raise RuntimeError(f"local_mflux needs {', '.join(missing)} (venv bin dir / HF cache)")
        if model_id not in MODELS:
            raise ValueError(f"unknown model {model_id!r}; known: {', '.join(MODELS)}")
        bin_dir, hf_home = Path(env["CF_MFLUX_BIN_DIR"]), Path(env["CF_MFLUX_HF_HOME"])
        if not (bin_dir / MODELS[model_id].command).is_file():
            raise FileNotFoundError(f"{bin_dir / MODELS[model_id].command} not found")
        return cls(MODELS[model_id], bin_dir, hf_home)

    def argv(self, request: IllustrationRequest, out: Path) -> list[str]:
        spec = self.model
        return [str(self.bin_dir / spec.command), "--model", spec.repo, "--base-model", spec.base_model,
                "--prompt", request.prompt, "--seed", str(request.seed), "--steps", str(spec.steps),
                "--width", str(request.width), "--height", str(request.height), "--output", str(out)]

    def generate(self, request: IllustrationRequest, out: Path) -> dict:
        waited = wait_for_memory()
        swap_before = _swap_used_mb()
        started = time.monotonic()
        proc = subprocess.run(self.argv(request, out), capture_output=True, text=True,
                              env={**os.environ, "HF_HOME": str(self.hf_home), "HF_HUB_OFFLINE": "1"})
        seconds = round(time.monotonic() - started, 1)
        if proc.returncode != 0 or not out.is_file():
            tail = (proc.stderr or proc.stdout)[-800:]
            raise RuntimeError(f"{self.model.command} failed for {request.slide_id} (rc={proc.returncode}): {tail}")
        peak = re.findall(r"Peak MLX memory: ([\d.]+) GB", proc.stdout + proc.stderr)
        spec = self.model
        return {"provider": self.name, "model": spec.id, "model_name": spec.name, "repo": spec.repo,
                "origin_repo": spec.origin_repo, "license": spec.license, "license_url": spec.license_url,
                "steps": spec.steps, "seconds": seconds, "waited_for_memory_seconds": waited,
                "peak_memory_gb": float(peak[-1]) if peak else None,
                "swap_before_mb": swap_before, "swap_after_mb": _swap_used_mb()}


@dataclass(frozen=True)
class Settings:
    model: str
    style_prefix: str
    seed: int
    width: int
    height: int


def sidecar_for(image: Path) -> Path:
    return image.with_suffix(SIDECAR_SUFFIX)


def load_record(image: Path) -> dict | None:
    path = sidecar_for(image)
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return record


def requests_for(deck: Deck, settings: Settings) -> list[IllustrationRequest]:
    return [IllustrationRequest(slide.id, f"{settings.style_prefix.strip()} {slide.media.prompt.strip()}".strip(),
                                settings.seed, settings.width, settings.height)
            for slide in deck.slides if slide.media_kind == MediaKind.AI_IMAGE and slide.media is not None]


def missing_images(deck: Deck, run_dir: Path, settings: Settings, *, replace: bool = False) -> list[str]:
    """Slide ids that :func:`illustrate` would generate."""
    image_dir = run_dir / AI_IMAGE_DIR
    return [r.slide_id for r in requests_for(deck, settings)
            if replace or find_image(image_dir, r.slide_id) is None]


def illustrate(deck: Deck, run_dir: Path, settings: Settings, provider: IllustrationProvider,
               *, replace: bool = False) -> list[dict]:
    """Generate every ai_image slide still missing an image; returns the new records.

    A hand-placed image without a sidecar is left alone (QC flags its missing parameters).
    Prompts are checked before any model loads.
    """
    image_dir = run_dir / AI_IMAGE_DIR
    requests = requests_for(deck, settings)
    for request in requests:
        bad = forbidden_prompt_terms(request.prompt)
        if bad:
            raise ValueError(f"slide {request.slide_id}: prompt asks for {bad} (rule: 非擬真、不模仿畫家)")
    todo = set(missing_images(deck, run_dir, settings, replace=replace))
    image_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for request in requests:
        if request.slide_id not in todo:
            logger.info("slide %s: keeping the existing image", request.slide_id)
            continue
        out = image_dir / f"{request.slide_id}.png"
        record = {"slide_id": request.slide_id, **provider.generate(request, out),
                  "prompt": request.prompt, "seed": request.seed, "size": [request.width, request.height],
                  "ai_label": AI_LABEL}
        sidecar_for(out).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("slide %s: %s %ss", request.slide_id, record["model"], record["seconds"])
        records.append(record)
    return records
