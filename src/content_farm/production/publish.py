"""Fill ``upload/youtube_meta.json`` from the channel config and the finished run.

Same file and keys ``/prepareupload`` writes (so ``/upload`` reads it
unchanged), plus what that stage leaves to hand-editing:
- ``video_path`` points at the mascot-composited ``assembly/final.mp4``;
- chapter timestamps come from the measured scene durations, not estimates;
- ``credits.json``'s attribution block is appended to the description;
- ``contains_synthetic_media`` (AI disclosure) and ``publish_at`` (scheduled
  release, which YouTube only accepts on private videos).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from content_farm.production.channels import Channel
from content_farm.production.qc import final_video
from content_farm.script_gen.schemas import Script
from content_farm.youtube.meta import _find_relative, _format_timestamp

META_PATH = Path("upload") / "youtube_meta.json"
AI_DISCLOSURE_LINE = "本影片由 AI 輔助製作（配音與部分插圖為合成內容）。"
AI_VOICE_ONLY_LINE = "本影片由 AI 輔助製作（配音為合成語音；畫面無 AI 生成圖像）。"


def ai_disclosure_line(credits: dict | None) -> str:
    """Only claim AI illustrations when the credits list one; otherwise say the voice alone is synthetic."""
    entries = (credits or {}).get("entries", [])
    pending = (credits or {}).get("pending", [])
    has_ai_image = any(e.get("kind") == "ai_image" for e in [*entries, *pending])
    return AI_DISCLOSURE_LINE if has_ai_image or credits is None else AI_VOICE_ONLY_LINE
MIN_CHAPTERS = 3
MIN_CHAPTER_SECONDS = 10  # YouTube ignores chapter lists with shorter chapters


def measured_chapters(script: Script) -> list[tuple[float, str]]:
    """(start seconds, title) per chapter, from the scene durations voice wrote back."""
    starts: dict[int, float] = {}
    clock = 0.0
    for scene in script.scenes:
        number = scene.chapter_number or 0
        starts.setdefault(number, clock)
        clock += scene.duration_seconds
    titles = {ch.chapter_number: ch.title for ch in getattr(script, "chapters", ()) or ()}
    return [(starts[n], titles[n]) for n in sorted(starts) if n in titles]


def chapter_block(chapters: list[tuple[float, str]], total_seconds: float) -> list[str]:
    if len(chapters) < MIN_CHAPTERS or chapters[0][0] > 0.5:
        return []
    ends = [start for start, _ in chapters[1:]] + [total_seconds]
    if any(end - start < MIN_CHAPTER_SECONDS for (start, _), end in zip(chapters, ends)):
        return []
    return ["章節：", *(f"{_format_timestamp(start)} {title}" for start, title in chapters), ""]


def build_description(channel: Channel, script: Script, credits: dict | None) -> str:
    total = sum(scene.duration_seconds for scene in script.scenes)
    parts = [*chapter_block(measured_chapters(script), total), script.description, ""]
    if script.sources:
        parts += ["參考資料：", *(f"• {src}" for src in script.sources), ""]
    credit_text = (credits or {}).get("description_text", "").strip()
    if credit_text:
        parts += [credit_text, ""]
    if channel.youtube.ai_disclosure:
        parts.append(ai_disclosure_line(credits))
    parts.append(f"— {channel.name}")
    return "\n".join(parts).strip() + "\n"


def build_meta(
    channel: Channel, run_dir: Path, *, publish_at: datetime | None = None,
) -> dict:
    script = Script.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
    credits_path = run_dir / "credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.is_file() else None
    video = final_video(run_dir)
    if video is None:
        raise FileNotFoundError(f"{run_dir}/assembly has no final.mp4 or draft.mp4")
    if publish_at is not None and publish_at.tzinfo is None:
        raise ValueError("publish_at must be timezone-aware")
    total = sum(scene.duration_seconds for scene in script.scenes)
    return {
        "title": script.video_title,
        "description": build_description(channel, script, credits),
        "tags": list(script.tags),
        "privacy_status": "private" if publish_at else channel.youtube.default_privacy,
        "publish_at": publish_at.isoformat() if publish_at else None,
        "contains_synthetic_media": channel.youtube.ai_disclosure,
        "category_id": "27" if channel.pipeline.value == "explainer" else "23",  # Education / Comedy
        "made_for_kids": False,
        "default_language": script.language,
        "video_path": video.relative_to(run_dir).as_posix(),
        "thumbnail_path": _find_relative(run_dir, "thumbnails", ("*.png", "*.jpg")),
        "subtitle_path": _find_relative(run_dir, "subtitles", ("*.srt", "*.vtt")),
        "chapters": [{"timestamp": _format_timestamp(start), "title": title}
                     for start, title in measured_chapters(script)],
        "channel": channel.code,
        "credentials_env": {  # env var NAMES only; run_stage --stage youtube resolves them
            "client_id": channel.youtube.client_id_env,
            "client_secret": channel.youtube.client_secret_env,
            "refresh_token": channel.youtube.refresh_token_env,
            "channel_id": channel.youtube.channel_id_env,
        },
        "duration_seconds": round(total, 2),
    }


def write_meta(run_dir: Path, meta: dict) -> Path:
    path = run_dir / META_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
