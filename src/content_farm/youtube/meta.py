"""YouTube upload metadata template — generate, save, and load."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.script_gen.schemas import Script
from content_farm.youtube.schemas import UploadSettings


def generate_meta_template(
    script: Script,
    run_dir: Path,
    portrait_video_path: Path,
) -> dict:
    """Build a youtube_meta dict pre-filled from script data.

    Returns a plain dict so the user can freely edit fields in the JSON file.
    """
    defaults = UploadSettings()

    return {
        "title": script.video_title,
        "description": _build_description(script),
        "tags": list(script.tags),
        "privacy_status": defaults.privacy_status,
        "category_id": defaults.category_id,
        "made_for_kids": defaults.made_for_kids,
        "default_language": script.language,
        "video_path": str(portrait_video_path.relative_to(run_dir)),
        "thumbnail_path": _find_relative(run_dir, "thumbnails", ("*.png", "*.jpg")),
        "subtitle_path": _find_relative(run_dir, "subtitles", ("*.srt", "*.vtt")),
    }


def _find_relative(run_dir: Path, subdir: str, globs: tuple[str, ...]) -> str:
    """Find the first matching file in a subdirectory, return relative path."""
    d = run_dir / subdir
    if not d.is_dir():
        return ""
    for pattern in globs:
        matches = sorted(d.glob(pattern))
        if matches:
            return str(matches[0].relative_to(run_dir))
    return ""


def _build_description(script: Script) -> str:
    """Build YouTube description from script metadata."""
    parts = [script.description, ""]
    if script.sources:
        parts.append("參考資料:")
        for src in script.sources:
            parts.append(f"• {src}")
        parts.append("")
    if getattr(script, "ai_disclosure", False):
        parts.append("本影片由 AI 輔助製作")
    return "\n".join(parts)


def save_meta_template(meta: dict, run_dir: Path) -> Path:
    """Write youtube_meta.json to upload/ directory."""
    upload_dir = run_dir / "upload"
    upload_dir.mkdir(parents=True, exist_ok=True)
    meta_path = upload_dir / "youtube_meta.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta_path


def load_meta_template(run_dir: Path) -> dict:
    """Load the edited youtube_meta.json from upload/ directory."""
    meta_path = run_dir / "upload" / "youtube_meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(
            f"YouTube meta template not found: {meta_path}\n"
            "Run prepareupload first."
        )
    return json.loads(meta_path.read_text(encoding="utf-8"))
