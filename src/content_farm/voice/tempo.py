"""Channel narration tempo (``voice.tempo``): speed up / slow down without changing pitch.

With tempo 1.0 the synthesized take *is* ``audio/scene_NNN.mp3`` (the layout
every run had before). With any other tempo the take lives in
``audio/raw/scene_NNN.mp3`` and ``audio/scene_NNN.mp3`` is derived from it
with ffmpeg ``atempo``, so changing the tempo never re-synthesizes. Which
tempo each scene file carries is recorded in ``audio/tempo.json`` (absent =
1.0).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TEMPO_FILE = "tempo.json"
RAW_DIR = "raw"


def load_applied(audio_dir: Path) -> dict[str, float]:
    path = audio_dir / TEMPO_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Ignoring unreadable %s; every scene is re-timed", path)
        return {}
    return {str(k): float(v) for k, v in data.items()} if isinstance(data, dict) else {}


def applied(audio_dir: Path, filename: str) -> float:
    return load_applied(audio_dir).get(filename, 1.0)


def record_applied(audio_dir: Path, filename: str, tempo: float) -> None:
    path = audio_dir / TEMPO_FILE
    updated = {**load_applied(audio_dir), filename: tempo}
    path.write_text(json.dumps(updated, indent=2, sort_keys=True), encoding="utf-8")


def place_take(audio_dir: Path, filename: str, tempo: float) -> Path:
    """Where this scene's synthesized take belongs for ``tempo``; moves an existing take there.

    1.0 → the scene file itself; otherwise ``raw/``. A take made at 1.0 (scene file whose
    applied tempo is 1.0) moves into ``raw/`` when a tempo is set, and back when it is removed."""
    out, raw = audio_dir / filename, audio_dir / RAW_DIR / filename
    if tempo == 1.0:
        if raw.is_file():
            raw.replace(out)
            record_applied(audio_dir, filename, 1.0)
        return out
    if not raw.is_file() and out.is_file() and applied(audio_dir, filename) == 1.0:
        raw.parent.mkdir(parents=True, exist_ok=True)
        out.replace(raw)
    raw.parent.mkdir(parents=True, exist_ok=True)
    return raw


async def retime(ffmpeg: str, raw: Path, out: Path, tempo: float) -> None:
    """Write ``out`` = ``raw`` played at ``tempo`` (pitch kept, ffmpeg atempo 0.5–2.0)."""
    if not 0.5 <= tempo <= 2.0:
        raise ValueError(f"voice tempo must be within 0.5–2.0, got {tempo}")
    proc = await asyncio.create_subprocess_exec(
        ffmpeg, "-loglevel", "error", "-y", "-i", str(raw), "-filter:a", f"atempo={tempo}",
        "-codec:a", "libmp3lame", "-b:a", "192k", str(out),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not out.is_file():
        detail = stderr.decode("utf-8", "replace").strip() or "(no stderr)"
        raise RuntimeError(f"ffmpeg atempo={tempo} failed for {raw.name}: {detail}")
    logger.info("Re-timed %s at %.2fx -> %s", raw.name, tempo, out)
