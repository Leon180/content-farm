"""A PNGtuber character pack: base.png + face patches + manifest.json, all on one canvas.

    packs/<id>/manifest.json   {"id", "name", "size": [w, h], "layers": [...], "pose_map": {...}, ...}
    packs/<id>/base.png        the whole character, transparent background (mouth closed, eyes open)
    packs/<id>/<layer>.png     a face patch on the same canvas (transparent everywhere else)

Layers: blink, mouth_half, mouth_open (swapped by voice level) and the expressions surprised,
smug, speechless (chosen by the slide's mascot pose through ``pose_map``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

PACK_ROOT = Path(__file__).parent / "packs"
MOUTH_LAYERS = ("mouth_half", "mouth_open")
# frames: generated talking mouths; none: the mouth never moves (the talk bounce still shows speech);
# small_o: mouth layers are a small drawn 'o' over the original mouth (build.apply_mouth_mode)
MOUTH_MODES = ("frames", "none", "small_o")
EXPRESSIONS = ("neutral", "surprised", "smug", "speechless")
LAYERS = ("blink", *MOUTH_LAYERS, *EXPRESSIONS[1:])
# rig poses (explainer.mascot.cues.POSES) → expression; gestures the stills cannot do stay neutral
DEFAULT_POSE_MAP = {"idle": "neutral", "point": "neutral", "wave": "neutral", "think": "speechless",
                    "shocked": "surprised", "smug": "smug", "deadpan": "speechless"}


class PackError(ValueError):
    """The pack is missing, malformed, or its images do not share one canvas."""


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    base: Image.Image
    layers: dict[str, Image.Image]
    pose_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_POSE_MAP))
    mouth_mode: str = "frames"
    # 2.5D: a depth map (0 far .. 1 near, same canvas) turns on the depth-driven head turn / nod,
    # ground shadow and talk squash (manifest "motion": "2.5d" + depth.png from host_depth_worker.py)
    depth: np.ndarray | None = None
    # speech effect drawn by the renderer, e.g. {"kind": "bubbles", "emit": [x, y], "surface_y": y,
    # "x_range": [x0, x1]} in canvas px: bubbles rise from ``emit`` while the host speaks
    speech_fx: dict | None = None

    def expression_for(self, pose: str) -> str:
        return self.pose_map.get(pose, "neutral")


def pack_dir(ref: str, root: Path = PACK_ROOT) -> Path:
    """``pngtuber/<id>`` (channels yaml) or a bare ``<id>``."""
    pack_id = ref.split("/", 1)[1] if ref.startswith("pngtuber/") else ref
    if not pack_id or "/" in pack_id or pack_id.startswith("."):
        raise PackError(f"bad pack ref {ref!r}")
    return root / pack_id


def load_pack(ref: str, root: Path = PACK_ROOT) -> Pack:
    folder = pack_dir(ref, root)
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise PackError(f"no PNGtuber pack at {folder}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = [name for name in ("base", *LAYERS) if not (folder / f"{name}.png").is_file()]
    if missing:
        raise PackError(f"pack {folder.name} is missing {', '.join(missing)}")
    base = Image.open(folder / "base.png").convert("RGBA")
    layers = {name: Image.open(folder / f"{name}.png").convert("RGBA") for name in LAYERS}
    odd = [name for name, img in layers.items() if img.size != base.size]
    if odd:
        raise PackError(f"pack {folder.name}: {', '.join(odd)} not on the base canvas {base.size}")
    pose_map = {**DEFAULT_POSE_MAP, **manifest.get("pose_map", {})}
    bad = sorted({v for v in pose_map.values() if v not in EXPRESSIONS})
    if bad:
        raise PackError(f"pack {folder.name}: unknown expressions in pose_map: {bad}")
    mouth_mode = manifest.get("mouth_mode", "frames")
    if mouth_mode not in MOUTH_MODES:
        raise PackError(f"pack {folder.name}: mouth_mode {mouth_mode!r} not in {MOUTH_MODES}")
    depth = None
    if manifest.get("motion") == "2.5d":
        depth_path = folder / "depth.png"
        if not depth_path.is_file():
            raise PackError(f"pack {folder.name} asks for 2.5d motion but has no depth.png")
        depth = np.asarray(Image.open(depth_path), dtype=np.float32) / 65535.0
        if depth.shape != (base.height, base.width):
            raise PackError(f"pack {folder.name}: depth.png {depth.shape} not on the base canvas {base.size}")
    speech_fx = manifest.get("speech_fx")
    if speech_fx is not None:
        missing = [k for k in ("emit", "surface_y", "x_range") if k not in speech_fx]
        if speech_fx.get("kind") != "bubbles" or missing:
            raise PackError(f"pack {folder.name}: speech_fx must be kind 'bubbles' with emit, surface_y, x_range")
    return Pack(id=manifest.get("id", folder.name), name=manifest.get("name", folder.name), base=base,
                layers=layers, pose_map=pose_map, mouth_mode=mouth_mode, depth=depth, speech_fx=speech_fx)
