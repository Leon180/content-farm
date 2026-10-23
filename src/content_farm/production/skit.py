"""The 冷笑話小劇場 (``shorts_skit``) script format and its lint.

``script.json`` is the ordinary :class:`~content_farm.script_gen.schemas.Script` (the voice step reads it and
rewrites it with the measured audio lengths, so nothing outside that model survives). The skit structure
therefore lives in fields the model keeps:

- ``scene.title`` = ``"<nn> <beat>"`` with beat 鋪陳 (setup) / 笑點 (punchline) / 收尾 (tag);
- ``scene.transition`` = ``"pause:0.6"`` on the last setup scene: the renderer holds that long, in silence,
  before the punchline (Leon: 鋪陳 → 停 0.6 秒 → 笑點 → 收尾);
- ``scene.visual_hint.description`` = the goldfish's expression for that scene (a layer of its pngtuber pack).

Shape: 1–3 setup scenes, exactly one punchline, an optional tag last; 20–50 s including the pause.
"""

from __future__ import annotations

import re
from typing import Any

from content_farm.explainer.deck import estimate_seconds

SETUP, PUNCHLINE, TAG = "鋪陳", "笑點", "收尾"
BEATS = (SETUP, PUNCHLINE, TAG)
PAUSE_PREFIX = "pause:"
PAUSE_SECONDS = 0.6
PAUSE_RANGE = (0.4, 0.8)
LENGTH_RANGE = (20.0, 50.0)          # seconds, channels/offwork.yaml format.target_seconds
MAX_SETUP_SCENES = 3
MAX_PUNCHLINE_CHARS = 40             # the laugh is short; a long punchline explains itself
MAX_TITLE_CHARS = 30
# cooler-goldfish-3d manifest ``expressions`` (tests keep this in step with the pack)
EXPRESSIONS = ("neutral", "surprised", "smug", "speechless")
# Leon's script-tone memory: trendy slang dates fast, 欸 is overused
TRENDY_WORDS = ("狂", "絕了")
MAX_FILLER = 1                       # 欸 per script

_TITLE = re.compile(r"^\s*(\d+)\s+(\S+)\s*$")


def beat_of(scene: dict[str, Any]) -> str:
    match = _TITLE.match(str(scene.get("title", "")))
    return match.group(2) if match else ""


def pause_after(scene: dict[str, Any]) -> float:
    """Seconds of silence the scene asks for after its line (0 when none)."""
    transition = str(scene.get("transition", "cut"))
    if not transition.startswith(PAUSE_PREFIX):
        return 0.0
    try:
        return float(transition[len(PAUSE_PREFIX):])
    except ValueError:
        return 0.0


def estimated_seconds(script: dict[str, Any]) -> float:
    """Spoken length by character count plus the pauses (what the lint judges the 20–50 s window on)."""
    scenes = script.get("scenes", [])
    return round(sum(estimate_seconds(str(s.get("narration", ""))) + pause_after(s) for s in scenes), 1)


def _structure_problems(scenes: list[dict[str, Any]]) -> list[str]:
    beats = [beat_of(s) for s in scenes]
    problems = [f"scene {s.get('scene_number')}: title {s.get('title')!r} must read '<nn> 鋪陳|笑點|收尾'"
                for s, beat in zip(scenes, beats) if beat not in BEATS]
    if problems:
        return problems
    first_punch = beats.index(PUNCHLINE) if PUNCHLINE in beats else -1
    if beats.count(PUNCHLINE) != 1:
        problems.append(f"needs exactly one {PUNCHLINE} scene, has {beats.count(PUNCHLINE)}")
    if beats.count(TAG) > 1 or (TAG in beats and beats[-1] != TAG):
        problems.append(f"{TAG} is optional, at most one, and last")
    setups = beats[:first_punch] if first_punch > 0 else []
    if not setups or any(b != SETUP for b in setups):
        problems.append(f"the scenes before {PUNCHLINE} must all be {SETUP} (at least one)")
    if first_punch >= 0 and any(b != TAG for b in beats[first_punch + 1:]):
        problems.append(f"after the {PUNCHLINE} only an optional {TAG} may follow")
    if len(setups) > MAX_SETUP_SCENES:
        problems.append(f"at most {MAX_SETUP_SCENES} {SETUP} scenes, has {len(setups)}")
    return problems


def _pause_problems(scenes: list[dict[str, Any]]) -> list[str]:
    beats = [beat_of(s) for s in scenes]
    if PUNCHLINE not in beats or beats.index(PUNCHLINE) == 0:
        return []
    before = beats.index(PUNCHLINE) - 1
    problems = []
    for index, scene in enumerate(scenes):
        seconds = pause_after(scene)
        if index == before:
            if not PAUSE_RANGE[0] <= seconds <= PAUSE_RANGE[1]:
                problems.append(f"scene {scene.get('scene_number')}: the last {SETUP} must set transition "
                                f"'{PAUSE_PREFIX}{PAUSE_SECONDS}' (the beat before the laugh), has {scene.get('transition')!r}")
        elif seconds:
            problems.append(f"scene {scene.get('scene_number')}: only the beat before the {PUNCHLINE} pauses")
    return problems


def _text_problems(script: dict[str, Any], scenes: list[dict[str, Any]]) -> list[str]:
    problems = []
    text = "".join(str(s.get("narration", "")) for s in scenes)
    for word in TRENDY_WORDS:
        if word in text:
            problems.append(f"narration uses the trendy word 「{word}」 (dates fast; use a lasting phrase)")
    if text.count("欸") > MAX_FILLER:
        problems.append(f"「欸」 appears {text.count('欸')} times (max {MAX_FILLER})")
    for scene in scenes:
        if beat_of(scene) == PUNCHLINE and len(str(scene.get("narration", ""))) > MAX_PUNCHLINE_CHARS:
            problems.append(f"scene {scene.get('scene_number')}: the {PUNCHLINE} is over {MAX_PUNCHLINE_CHARS} characters")
        expression = str((scene.get("visual_hint") or {}).get("description", ""))
        if expression not in EXPRESSIONS:
            problems.append(f"scene {scene.get('scene_number')}: visual_hint.description {expression!r} is not a goldfish "
                            f"expression {EXPRESSIONS}")
        if not str(scene.get("narration", "")).strip():
            problems.append(f"scene {scene.get('scene_number')}: empty narration")
    title = str(script.get("video_title", "")).strip()
    if not title or len(title) > MAX_TITLE_CHARS:
        problems.append(f"video_title must be 1–{MAX_TITLE_CHARS} characters")
    if not str(script.get("description", "")).strip():
        problems.append("description is empty")
    if script.get("ai_disclosure") is not True:
        problems.append("ai_disclosure must be true (the character is AI-generated)")
    return problems


def skit_problems(script: dict[str, Any]) -> list[str]:
    """Everything wrong with a skit ``script.json`` (empty = fine): structure, pause, length, tone, schema."""
    from pydantic import ValidationError

    from content_farm.script_gen.schemas import Script

    try:
        Script.model_validate(script)
    except ValidationError as exc:
        return [f"not a valid script.json: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}"]
    scenes = list(script.get("scenes", []))
    problems = _structure_problems(scenes)
    if problems:
        return problems
    problems = _pause_problems(scenes) + _text_problems(script, scenes)
    seconds = estimated_seconds(script)
    if not LENGTH_RANGE[0] <= seconds <= LENGTH_RANGE[1]:
        problems.append(f"estimated length {seconds:g} s is outside {LENGTH_RANGE[0]:g}–{LENGTH_RANGE[1]:g} s "
                        f"(by characters, plus the pause)")
    return problems
