"""YouTube upload metadata template — generate, save, and load."""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.script_gen.schemas import ChapterOutline, Script
from content_farm.youtube.schemas import UploadSettings


def generate_meta_template(
    script: Script,
    run_dir: Path,
    portrait_video_path: Path,
) -> dict:
    """Build a youtube_meta dict pre-filled from script data.

    Returns a plain dict so the user can freely edit fields in the JSON file.
    For long-form scripts with ``chapters[]``, includes a ``chapters`` list
    of ``{timestamp, title}`` objects for human review + edit.
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
        "chapters": [
            {"timestamp": _format_timestamp(ch.start_timestamp), "title": ch.title}
            for ch in getattr(script, "chapters", ()) or ()
        ],
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


def _format_timestamp(seconds: float) -> str:
    """Format seconds as ``H:MM:SS`` or ``M:SS`` — YouTube's chapter-parse format.

    YouTube accepts either ``0:00`` (M:SS) or ``0:00:00`` (H:MM:SS).
    We pick the shorter form when under 1 hour.
    """
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_chapter_block(chapters: tuple[ChapterOutline, ...]) -> list[str]:
    """Build the lines YouTube parses as chapter markers.

    YouTube requires: first timestamp ``0:00``, at least 3 entries total,
    each on its own line in ascending timestamp order. Format:
    ``MM:SS title`` (or ``H:MM:SS title`` for >1hr videos).

    Places a short 「章節」 label line BEFORE the timestamps so viewers
    see a human-readable heading; YouTube's parser ignores non-timestamp
    lines and still picks up the timestamps that follow.

    Returns an empty list if the chapter set does not meet YouTube's
    minimums — better to skip than to emit broken markers.
    """
    if len(chapters) < 3:
        return []
    if abs(chapters[0].start_timestamp) > 0.5:
        return []  # must start at 0:00

    lines = ["章節："]
    for ch in chapters:
        lines.append(f"{_format_timestamp(ch.start_timestamp)} {ch.title}")
    lines.append("")
    return lines


def _build_description(script: Script) -> str:
    """Build YouTube description from script metadata.

    Long-form videos with ``chapters[]`` get the chapter marker block at the
    very top (YouTube's parser scans from the top for the first ``0:00``
    timestamp). Short-form scripts skip the chapter block entirely.
    """
    parts: list[str] = []

    chapter_lines = _build_chapter_block(getattr(script, "chapters", ()) or ())
    if chapter_lines:
        parts.extend(chapter_lines)

    parts.append(script.description)
    parts.append("")

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
