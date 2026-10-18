"""Scene spans on the video's frame grid, per-scene lip-sync, and per-scene identity.

The mascot is rendered and cached one scene at a time (see ``motion.compose_scene``).
A scene's identity covers everything its frames are computed from; the frame grid
position is deliberately not part of it, so a scene that only moved in time is reused.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from content_farm.explainer.mascot import lipsync
from content_farm.explainer.mascot.cues import SceneCue
from content_farm.explainer.mascot.motion import Frame, SceneSpan, compose_scene
from content_farm.explainer.scene_cache import code_digest, digest, file_digest

MASCOT_DIR = Path(__file__).parent
MASCOT_CACHE_VERSION = 1


def scene_seed(seed: int, slide_key: str) -> int:
    """Idle-motion seed of one scene: stable across runs and independent of its position."""
    return int(hashlib.sha256(f"{seed}:{slide_key}".encode()).hexdigest()[:8], 16)


def spans(cues: Sequence[SceneCue], fps: float, n_frames: int, seed: int,
          keys: Sequence[str] | None = None) -> list[SceneSpan]:
    """Cut ``n_frames`` into one span per cue at the frames nearest the cue starts.
    ``keys`` (one per cue, e.g. slide ids) seed each scene's idle motion."""
    keys = list(keys) if keys is not None else [str(c.index) for c in cues]
    firsts = [min(n_frames, max(0, int(round(c.start * fps)))) for c in cues]
    firsts[0] = 0
    out = []
    for i, cue in enumerate(cues):
        first = firsts[i]
        end = firsts[i + 1] if i + 1 < len(cues) else n_frames
        out.append(SceneSpan(cue=cue, previous_pose=cues[i - 1].pose if i else None, first=first,
                             count=max(0, end - first), offset=round(cue.start - first / fps, 4),
                             seed=scene_seed(seed, keys[i])))
    return out


def scene_mouth(audio: Path | None, span: SceneSpan, fps: float, decode=lipsync.decode_mono) -> np.ndarray:
    """Mouth envelope of one scene: its own audio placed at the cue start (normalised per scene)."""
    if audio is None or not audio.is_file():
        return np.zeros(span.count)
    samples = decode(audio)
    shift = int(round(span.offset * lipsync.SAMPLE_RATE))
    if shift > 0:
        samples = np.concatenate([np.zeros(shift, dtype=samples.dtype), samples])
    elif shift < 0:
        samples = samples[-shift:]
    db = lipsync.frame_rms_db(samples, lipsync.SAMPLE_RATE, fps, span.count)
    return lipsync.mouth_envelope(db)


def scene_frames(span: SceneSpan, audio: Path | None, fps: float, decode=lipsync.decode_mono) -> tuple[Frame, ...]:
    return compose_scene(span, scene_mouth(audio, span, fps, decode), fps)


def renderer_digest() -> str:
    return code_digest(MASCOT_DIR)


def scene_identity(span: SceneSpan, audio: Path | None, fps: float, *, render: str, code: str) -> str:
    """``render`` names the capture settings (tile layout, GPU or not) that shape the pixels."""
    return digest({
        "v": MASCOT_CACHE_VERSION, "code": code, "render": render, "fps": fps, "count": span.count,
        "offset": span.offset, "duration": round(span.cue.duration, 4), "pose": span.cue.pose,
        "previous_pose": span.previous_pose, "say": span.cue.say, "seed": span.seed,
        "audio": file_digest(audio) if audio is not None else None,
    })


