"""Which sentences of a scene take to re-voice after an edit (sentence windows).

Compares the sentences the take was voiced from with the scene's sentences now. Every
changed block (rewritten, inserted or deleted sentences) grows by ``radius`` unchanged
neighbours on each side — never past the scene — and overlapping windows merge.
"""

from __future__ import annotations

import difflib
from collections.abc import Sequence
from dataclasses import dataclass

# Re-voicing more than this share of a scene's sentences is a re-take, not a patch.
MAX_WINDOW_SHARE = 0.75


@dataclass(frozen=True)
class Window:
    old_first: int   # inclusive range in the old take's sentences
    old_last: int
    new_first: int   # inclusive range in the scene's sentences now
    new_last: int


def plan(old: Sequence[str], new: Sequence[str], radius: int) -> list[Window] | None:
    """Windows to re-voice, [] when nothing changed, None when the scene needs a full take
    (no old sentences, radius < 0, or the windows would cover most of the scene)."""
    if radius < 0 or not old or not new:
        return None
    blocks = [(i1, i2, j1, j2) for tag, i1, i2, j1, j2 in
              difflib.SequenceMatcher(a=list(old), b=list(new), autojunk=False).get_opcodes() if tag != "equal"]
    if not blocks:
        return []
    windows: list[Window] = []
    for i1, i2, j1, j2 in blocks:
        grow = max(radius, 1 if i1 == i2 else 0)   # a pure insertion needs an old sentence to replace
        lo = min(grow, i1, j1)
        hi = min(grow, len(old) - i2, len(new) - j2)
        window = Window(i1 - lo, i2 + hi - 1, j1 - lo, j2 + hi - 1)
        if window.old_last < window.old_first:       # nothing old to replace (inserted into an empty edge)
            return None
        if windows and window.old_first <= windows[-1].old_last + 1:
            prev = windows.pop()
            window = Window(prev.old_first, window.old_last, prev.new_first, window.new_last)
        windows.append(window)
    covered = sum(w.old_last - w.old_first + 1 for w in windows)
    if covered > MAX_WINDOW_SHARE * len(old):
        return None
    return windows
