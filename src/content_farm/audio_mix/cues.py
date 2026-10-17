"""Where stingers and SFX go: chapter starts and some narration hooks, never crowded."""

from __future__ import annotations

from dataclasses import dataclass

from content_farm.retention.beats import Hook
from content_farm.retention.timing import Scene

SFX_FOR_HOOK = {"reversal": "ding", "gossip": "ding", "joke": "pop", "tease": "whoosh"}   # v3: not on every question
SFX_MIN_SPACING = 18.0      # s between two SFX (v3 eval: 33 evenly scattered cues read as noise)
STINGER_CLEAR = 4.0         # no SFX this close to a stinger
STINGER_LEAD = 0.4          # the stinger starts just before the new chapter's first word


@dataclass(frozen=True)
class Cue:
    t: float
    kind: str          # stinger | whoosh | pop | ding
    reason: str


def stinger_cues(scenes: list[Scene]) -> list[Cue]:
    cues = []
    for prev, scene in zip(scenes, scenes[1:]):
        if scene.chapter != prev.chapter:
            cues.append(Cue(round(max(scene.start - STINGER_LEAD, 0.0), 2), "stinger", f"第 {scene.chapter} 章"))
    return cues


def sfx_cues(hooks: list[Hook], stingers: list[Cue]) -> list[Cue]:
    cues: list[Cue] = []
    for hook in hooks:
        kind = SFX_FOR_HOOK.get(hook.kind)
        if kind is None:
            continue
        # a punchline / reversal lands at the end of its sentence; a tease opens with the swoosh
        t = round(hook.end if kind in ("pop", "ding") and hook.end else hook.t, 2)
        if cues and t - cues[-1].t < SFX_MIN_SPACING:
            continue
        if any(abs(t - s.t) < STINGER_CLEAR for s in stingers):
            continue
        cues.append(Cue(t, kind, f"{hook.kind}：{hook.text[:18]}"))
    return cues


def plan(scenes: list[Scene], hooks: list[Hook], *, sfx: bool = True) -> list[Cue]:
    stingers = stinger_cues(scenes)
    extra = sfx_cues(hooks, stingers) if sfx else []
    return sorted([*stingers, *extra], key=lambda c: c.t)
