"""``fable.json`` → ``script.json`` (one scene per beat) + ``voice_text.json`` (everything the TTS hears).

Scene titles carry the act (``03 story``), so the script panel, the voice step and the renderer all read the
same file. Measured scene durations written by an earlier voice run are kept when the words did not change.
"""

from __future__ import annotations

import json
from pathlib import Path

from content_farm.explainer.deck import estimate_seconds
from content_farm.production.fable.model import Fable, load
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.types import Orientation, VideoLength

SCRIPT_FILE = "script.json"
VOICE_TEXT_FILE = "voice_text.json"


def to_script(fable: Fable) -> Script:
    """The run's script: scenes in beat order, portrait for a Short, landscape for the mid-length video."""
    scenes = tuple(
        Scene(scene_number=i, title=f"{i:02d} {beat.act}", narration=beat.narration,
              visual_hint=VisualHint(description="; ".join(s.image_prompt or f"reuse {s.reuse}" for s in beat.shots)[:300],
                                     keywords=(beat.act,), style="ai_illustration", source_preference="ai"),
              duration_seconds=estimate_seconds(beat.narration))
        for i, beat in enumerate(fable.beats, start=1))
    short = fable.format == "short"
    return Script(video_title=fable.title, description=_description(fable), scenes=scenes,
                  target_length=VideoLength.SHORT if short else VideoLength.MEDIUM,
                  orientation=Orientation.PORTRAIT if short else Orientation.LANDSCAPE,
                  total_duration_seconds=round(sum(s.duration_seconds for s in scenes), 2),
                  tags=("寓言", fable.concept.domain, "觀念", "科普"), pronunciation_map=dict(fable.pronunciation_map))


def _description(fable: Fable) -> str:
    refs = "\n".join(f"・{r}" for r in fable.concept.references)
    return (f"用一則原創寓言，講一個{fable.concept.domain}的概念。故事結束才揭曉答案。\n"
            + (f"\n延伸閱讀：\n{refs}" if refs else ""))


def voice_text(script: Script) -> str:
    return json.dumps({"narration": [s.narration for s in script.scenes],
                       "pronunciation_map": script.pronunciation_map}, ensure_ascii=False, indent=2) + "\n"


def keep_measured(script: Script, previous: Script | None) -> Script:
    """Carry measured durations over when the words are unchanged (a re-prepare must not forget the voice run)."""
    if previous is None or voice_text(previous) != voice_text(script):
        return script
    scenes = tuple(new.model_copy(update={"duration_seconds": old.duration_seconds})
                   for new, old in zip(script.scenes, previous.scenes))
    return script.model_copy(update={"scenes": scenes, "total_duration_seconds": previous.total_duration_seconds})


def prepare(run_dir: Path) -> Script:
    fable = load(run_dir)
    path = run_dir / SCRIPT_FILE
    previous = Script.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None
    script = keep_measured(to_script(fable), previous)
    path.write_text(script.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / VOICE_TEXT_FILE).write_text(voice_text(script), encoding="utf-8")
    return script
