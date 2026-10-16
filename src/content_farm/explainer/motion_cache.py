"""Where motion clips for ``ai_image`` slides live, how a cached clip is recognised, and where
the local video tools are.

Clips sit next to the stills: ``assets/ai_motion/<slide_id>.<kind>.mp4`` with a sidecar
``<slide_id>.<kind>.json``. The sidecar's ``key`` is every input that changes the pixels
(image hash, model, parameters, prompt); a clip whose key no longer matches is stale and is
never used. The nightly Wan bake writes here; the render step only reads (for Wan).

Machine paths come from the environment (or ``--env-file``), never from code:
``CF_MLX_VIDEO_HOME`` (holds ``venv/`` and ``models/``), each overridable on its own with
``CF_MLX_VIDEO_PYTHON``, ``CF_DEPTH_MODEL_DIR`` and ``CF_WAN_MODEL_DIR``.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

MOTION_DIR = Path("assets") / "ai_motion"
MAX_MOTION_SECONDS = 3.0
ENV_KEYS = ("CF_MLX_VIDEO_HOME", "CF_MLX_VIDEO_PYTHON", "CF_DEPTH_MODEL_DIR", "CF_WAN_MODEL_DIR")
DEPTH_MODEL_SUBDIR = Path("models") / "depth-anything-v2-small-hf"
WAN_MODEL_SUBDIR = Path("models") / "wan22-ti2v-5b-q8"
VENV_PYTHON_SUBPATH = Path("venv") / "bin" / "python"


def motion_env(env_file: Path | None, env: Mapping[str, str] = os.environ) -> dict[str, str]:
    """The motion keys from the environment, else from ``env_file`` (dotenv)."""
    values = {key: env.get(key, "") for key in ENV_KEYS}
    if all(values.values()) or env_file is None or not env_file.is_file():
        return values
    from dotenv import dotenv_values

    from_file = dotenv_values(env_file)
    return {key: values[key] or (from_file.get(key) or "") for key in ENV_KEYS}


@dataclass(frozen=True)
class MotionPaths:
    python: Path        # interpreter of the mlx-video venv (torch, transformers, mlx_video)
    depth_model: Path   # Depth-Anything-V2-Small-hf snapshot
    wan_model: Path     # Wan2.2-TI2V-5B MLX q8 dir

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> MotionPaths | None:
        """None when nothing is configured (motion then falls back to Ken Burns)."""
        home = Path(env["CF_MLX_VIDEO_HOME"]).expanduser() if env.get("CF_MLX_VIDEO_HOME") else None

        def pick(key: str, sub: Path) -> Path | None:
            if env.get(key):
                return Path(env[key]).expanduser()
            return home / sub if home else None

        python = pick("CF_MLX_VIDEO_PYTHON", VENV_PYTHON_SUBPATH)
        depth = pick("CF_DEPTH_MODEL_DIR", DEPTH_MODEL_SUBDIR)
        wan = pick("CF_WAN_MODEL_DIR", WAN_MODEL_SUBDIR)
        if python is None or depth is None or wan is None:
            return None
        return cls(python, depth, wan)

    def problems(self, *, wan: bool = False) -> list[str]:
        """Missing pieces, as messages (empty = usable)."""
        wanted = [("python", self.python), ("depth model", self.depth_model / "model.safetensors")]
        if wan:
            wanted.append(("Wan model", self.wan_model / "model.safetensors"))
        return [f"{name} not found at {path}" for name, path in wanted if not path.is_file()]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def clip_paths(run_dir: Path, slide_id: str, kind: str) -> tuple[Path, Path]:
    # Not Path.with_suffix: "<slide>.wan" would lose ".wan" and collide with "<slide>.parallax".
    folder = run_dir / MOTION_DIR
    return folder / f"{slide_id}.{kind}.mp4", folder / f"{slide_id}.{kind}.json"


def cache_key(**parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def read_cached(run_dir: Path, slide_id: str, kind: str, key: str) -> tuple[Path, dict] | None:
    """The clip and its record when both exist and the record's key matches."""
    clip, sidecar = clip_paths(run_dir, slide_id, kind)
    if not (clip.is_file() and sidecar.is_file()):
        return None
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError(f"{sidecar}: expected a JSON object")
    return (clip, record) if record.get("key") == key else None


def write_record(run_dir: Path, slide_id: str, kind: str, record: dict) -> Path:
    _, sidecar = clip_paths(run_dir, slide_id, kind)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar
