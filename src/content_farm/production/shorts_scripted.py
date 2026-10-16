"""Scripted Shorts: a Short with its own narration, not a cut of one long-video slide.

Policy review 2026-10 (C2, D6): a Short re-cut from a long slide opened with an
explanation, never said the answer to its own title, left the lower 40% of the
frame empty and held one card for ~13 s. A scripted Short is written for the
feed instead:

- beat 1 is the hook; some beat says the title's answer out loud;
- every beat has its own visual that keeps changing (a step every <= 3 s);
- the channel mascot sits in the lower part of the frame on every beat.

``short_source.json`` gains ``beats``; ``scripted_script`` turns them into the
run's ``script.json`` for the normal ``voice`` step (paid TTS, same channel
voice), and :mod:`shorts_render` lays the measured audio over one page per beat.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from content_farm.explainer.deck import MascotPose
from content_farm.script_gen.schemas import Scene, Script, VisualHint
from content_farm.types import Orientation, VideoLength

Visual = Literal["number", "grow", "scale", "wafer", "outro"]
MAX_STEP_SECONDS = 3.0          # no visual may hold longer than this (review: 13 s static card)
MIN_BEATS = 3


class ShortBeat(BaseModel):
    """One spoken line and what the screen does meanwhile.

    ``number``  big value (+ unit) counting up, ``note`` as the question bubble;
    ``grow``    ``items`` revealed one by one, each a bigger block (e.g. 1× → 3.3× → 9× reticle);
    ``scale``   a ``side_cm`` square drawn to scale next to a card-sized reference (85.6 × 54 mm);
    ``wafer``   ``count`` squares of ``side_cm`` placed one by one on a 300 mm wafer circle;
    ``outro``   where the full video is.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    narration: str = Field(min_length=6, max_length=80)
    visual: Visual
    pose: MascotPose = "point"
    value: str = Field(default="", max_length=12)
    unit: str = Field(default="", max_length=8)
    note: str = Field(default="", max_length=24)
    items: tuple[str, ...] = Field(default=(), max_length=5)
    side_cm: float = Field(default=0.0, ge=0, le=20)
    count: int = Field(default=0, ge=0, le=12)

    @model_validator(mode="after")
    def _visual_fields(self) -> ShortBeat:
        need = {"number": ("value",), "grow": ("items",), "scale": ("side_cm",), "wafer": ("count", "side_cm")}
        missing = [name for name in need.get(self.visual, ()) if not getattr(self, name)]
        if missing:
            raise ValueError(f"visual {self.visual!r} needs {', '.join(missing)}")
        return self


def check_beats(beats: tuple[ShortBeat, ...], answer: str) -> list[str]:
    """Problems with a beat list (empty = fine): hook first, answer spoken, outro last."""
    problems = []
    if len(beats) < MIN_BEATS:
        problems.append(f"needs >= {MIN_BEATS} beats, has {len(beats)}")
    if beats and beats[0].visual == "outro":
        problems.append("beat 1 must be the hook, not the outro")
    if answer and not any(answer in beat.narration for beat in beats):
        problems.append(f"the title's answer 「{answer}」 is never spoken")
    if beats and beats[-1].visual != "outro":
        problems.append("last beat should point to the full video (visual 'outro')")
    return problems


def scripted_script(long_script: Script, beats: tuple[ShortBeat, ...], *, title: str, description: str,
                    tags: tuple[str, ...], sources: tuple[str, ...]) -> Script:
    """``script.json`` for the voice step: one scene per beat, the long run's pronunciation map."""
    from content_farm.explainer.deck import estimate_seconds

    scenes = tuple(
        Scene(scene_number=index, title=f"{index:02d} {beat.visual}", narration=beat.narration,
              visual_hint=VisualHint(description=beat.visual, keywords=(beat.visual,)),
              duration_seconds=estimate_seconds(beat.narration))
        for index, beat in enumerate(beats, start=1)
    )
    return long_script.model_copy(update={
        "video_title": title, "description": description, "scenes": scenes, "chapters": (),
        "tags": tags, "sources": sources, "target_length": VideoLength.SHORT,
        "orientation": Orientation.PORTRAIT,
        "total_duration_seconds": round(sum(scene.duration_seconds for scene in scenes), 2),
    })
