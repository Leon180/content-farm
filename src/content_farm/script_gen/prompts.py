"""Prompt templates for script generation. Pure functions, no side effects."""

from __future__ import annotations

from content_farm.script_gen.schemas import ScriptRequest

LANGUAGE_NAMES: dict[str, str] = {
    "zh-TW": "Traditional Chinese (繁體中文)",
    "zh-CN": "Simplified Chinese (简体中文)",
    "en": "English",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
}

SYSTEM_PROMPT = (
    "You are an expert YouTube scriptwriter. You produce engaging, well-structured "
    "video scripts optimized for viewer retention. Every script has a hook in the "
    "first 10 seconds, clear scene breaks, and a strong call-to-action ending."
)

VIDEO_LENGTH_SCENE_MAP: dict[str, tuple[int, int]] = {
    "short": (3, 5),
    "medium": (6, 10),
    "long": (10, 18),
}


def _language_instruction(language: str) -> str:
    """Build the language instruction for prompts."""
    lang_name = LANGUAGE_NAMES.get(language, language)
    return (
        f"\n\nIMPORTANT: Write ALL output content (video_title, description, "
        f"narration, scene titles, tags) in {lang_name}. "
        f"The narration must sound natural when spoken aloud in {lang_name}."
    )


def build_outline_prompt(request: ScriptRequest) -> str:
    """Build the prompt for generating a scene outline (cheap model)."""
    min_s, max_s = VIDEO_LENGTH_SCENE_MAP[request.video_length.value]
    keywords_str = ", ".join(request.keywords) if request.keywords else "none specified"

    return (
        f"Create a scene-by-scene outline for a {request.video_length.value}-length "
        f"YouTube video about: {request.topic}\n\n"
        f"Keywords to incorporate: {keywords_str}\n"
        f"Tone: {request.tone.value}\n"
        f"Number of scenes: between {min_s} and {max_s}\n\n"
        f"For each scene provide: scene_number, title, a brief summary of what "
        f"the narration should cover, and estimated duration_seconds.\n"
        f"Also provide a video_title, description, and relevant tags."
        + _language_instruction(request.language)
    )


def build_scene_narration_prompt(
    *,
    topic: str,
    tone: str,
    language: str,
    scene_title: str,
    scene_summary: str,
    scene_number: int,
    total_scenes: int,
    duration_seconds: int,
) -> str:
    """Build prompt for expanding a single scene's narration (expensive model)."""
    if scene_number == 1:
        position = "opening hook"
    elif scene_number == total_scenes:
        position = "closing/CTA"
    else:
        position = "body"

    return (
        f"Write the full narration for scene {scene_number}/{total_scenes} "
        f"of a YouTube video about '{topic}'.\n\n"
        f"Scene title: {scene_title}\n"
        f"Scene summary: {scene_summary}\n"
        f"Target duration: {duration_seconds} seconds\n"
        f"Tone: {tone}\n"
        f"Position in video: {position}\n\n"
        f"Write natural, spoken narration that fits the target duration. "
        f"No stage directions. Include a visual_hint object describing what "
        f"the viewer should see on screen, with a description, style "
        f"(stock_footage/animation/text_overlay), and relevant keywords."
        + _language_instruction(language)
    )
