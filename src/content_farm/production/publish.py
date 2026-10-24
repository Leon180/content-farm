"""Fill ``upload/youtube_meta.json`` from the channel config and the finished run.

Same file and keys ``/prepareupload`` writes (so ``/upload`` reads it
unchanged), plus what that stage leaves to hand-editing:
- ``video_path`` points at the mascot-composited ``assembly/final.mp4``;
- chapter timestamps come from the measured scene durations, not estimates;
- ``credits.json``'s attribution block is appended to the description;
- the description's AI disclosure line (channel ``ai_disclosure``), separate from
  ``contains_synthetic_media`` = Studio's 「變造或合成內容」 checkbox (channel
  ``altered_content_label``, off by default);
- ``publish_at`` (scheduled release, which YouTube only accepts on private videos).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from content_farm.production import voice_source
from content_farm.production.channels import Channel
from content_farm.production.qc import final_video
from content_farm.script_gen.schemas import Script
from content_farm.youtube.meta import _find_relative, _format_timestamp

META_PATH = Path("upload") / "youtube_meta.json"
DISCLOSURE_MARK = "本影片由 AI 輔助製作"
AI_DISCLOSURE_LINE = f"{DISCLOSURE_MARK}（配音為合成語音；部分插圖為 AI 生成）。"
AI_DISCLOSURE_VOICE_LINE = f"{DISCLOSURE_MARK}（配音為合成語音；畫面無 AI 生成圖像）。"
AI_DISCLOSURE_IMAGE_LINE = f"{DISCLOSURE_MARK}（部分插圖為 AI 生成；旁白非合成語音）。"
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


@dataclass(frozen=True)
class SyntheticContent:
    """What in this video is AI-made, as far as the run's own records show."""

    voice: bool
    images: bool

    @property
    def any(self) -> bool:
        return self.voice or self.images


def _deck_media_kinds(run_dir: Path) -> set[str] | None:
    path = run_dir / "deck.json"
    if not path.is_file():
        return None
    deck = json.loads(path.read_text(encoding="utf-8"))
    return {(slide.get("media") or {}).get("kind", "") for section in deck.get("sections", [])
            for slide in section.get("slides", [])}


def uses_ai_images(run_dir: Path, credits: dict | None) -> bool:
    """credits.json lists what the media step actually used (placeholders count); without it the
    deck's plan decides; with neither, assume yes rather than under-disclose."""
    if credits is not None:
        items = [*credits.get("entries", []), *credits.get("pending", [])]
        return any(item.get("kind") == "ai_image" for item in items)
    kinds = _deck_media_kinds(run_dir)
    return True if kinds is None else "ai_image" in kinds


def uses_synthetic_voice(run_dir: Path) -> bool:
    """Every voice provider is TTS. Only a voice log that exists and never records a synthesis
    (audio supplied by hand) counts as a non-synthetic voice; no log at all is assumed synthetic."""
    log = voice_source.voice_run_dir(run_dir) / "logs" / "voice.log"
    return voice_source.last_tts_provider(run_dir) is not None or not log.is_file()


def synthetic_content(run_dir: Path, credits: dict | None) -> SyntheticContent:
    return SyntheticContent(voice=uses_synthetic_voice(run_dir), images=uses_ai_images(run_dir, credits))


def ai_disclosure_line(content: SyntheticContent) -> str | None:
    """The description's disclosure sentence, naming only what the video really contains."""
    if content.voice and content.images:
        return AI_DISCLOSURE_LINE
    if content.voice:
        return AI_DISCLOSURE_VOICE_LINE
    if content.images:
        return AI_DISCLOSURE_IMAGE_LINE
    return None


def build_description(channel: Channel, script: Script, credits: dict | None,
                      content: SyntheticContent | None = None) -> str:
    """Description text; a channel with ``identity`` uses its own header, labels and footer
    (no two channels share a description template — policy review 2026-10 D3)."""
    template = channel.identity.description if channel.identity else None
    total = sum(scene.duration_seconds for scene in script.scenes)
    parts = [template.header.replace("{title}", script.video_title), ""] if template else []
    parts += [*chapter_block(measured_chapters(script), total), script.description, ""]
    if script.sources:
        label = template.sources_label if template else "參考資料："
        parts += [label, *(f"• {src}" for src in script.sources), ""]
    credit_text = (credits or {}).get("description_text", "").strip()
    if credit_text:
        parts += [credit_text, ""]
    audio_text = (credits or {}).get("audio_description_text", "").strip()
    if audio_text:
        parts += [audio_text, ""]
    if template:
        parts.append(template.footer)
    line = ai_disclosure_line(content or SyntheticContent(voice=True, images=True))
    if channel.youtube.ai_disclosure and line:
        parts.append(line)
    parts.append(f"— {channel.name}")
    return "\n".join(parts).strip() + "\n"


def _thumbnail_path(run_dir: Path) -> str:
    """The channel thumbnail (``thumbnails/thumbnail.png`` from thumbnail.json), else any image there
    except the phone-size review copy."""
    from content_farm.production.thumbnail import OUT_FILE, SMALL_FILE

    if (run_dir / OUT_FILE).is_file():
        return OUT_FILE.as_posix()
    found = _find_relative(run_dir, "thumbnails", ("*.png", "*.jpg"))
    return "" if found == SMALL_FILE.as_posix() else found


def build_meta(
    channel: Channel, run_dir: Path, *, publish_at: datetime | None = None,
) -> dict:
    script = Script.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
    credits_path = run_dir / "credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.is_file() else None
    audio_credits = run_dir / "audio" / "mix" / "audio_credits.json"
    if audio_credits.is_file():   # BGM / stinger attribution from the mix step (CC BY etc.)
        audio = json.loads(audio_credits.read_text(encoding="utf-8"))
        credits = {**(credits or {}), "audio_description_text": audio.get("description_text", "")}
    video = final_video(run_dir)
    if video is None:
        raise FileNotFoundError(f"{run_dir}/assembly has no final.mp4 or draft.mp4")
    if publish_at is not None and publish_at.tzinfo is None:
        raise ValueError("publish_at must be timezone-aware")
    total = sum(scene.duration_seconds for scene in script.scenes)
    content = synthetic_content(run_dir, credits)
    return {
        "title": script.video_title,
        "description": build_description(channel, script, credits, content),
        "tags": list(script.tags),
        "privacy_status": "private" if publish_at else channel.youtube.default_privacy,
        "publish_at": publish_at.isoformat() if publish_at else None,
        "contains_synthetic_media": channel.youtube.altered_content_label and content.any,
        "category_id": "27" if channel.pipeline.value in ("explainer", "fable") else "23",  # Education / Comedy
        "made_for_kids": False,
        "default_language": script.language,
        "video_path": video.relative_to(run_dir).as_posix(),
        "thumbnail_path": _thumbnail_path(run_dir),
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
