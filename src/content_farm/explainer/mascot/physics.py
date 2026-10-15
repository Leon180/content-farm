"""Spring–damper secondary motion (ears, tail, chip pendant).

A follower ``x`` is pulled toward a drive signal; what the rig shows is the
*lag* ``x - drive``, so an ear swings the opposite way when the head turns and
settles afterwards. Fixed-step semi-implicit Euler: the same inputs always
give the same output, independent of render speed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Spring:
    stiffness: float  # 1/s^2
    damping: float    # 1/s

    @property
    def damping_ratio(self) -> float:
        return self.damping / (2 * self.stiffness ** 0.5)


EAR = Spring(stiffness=220.0, damping=11.0)    # quick, a little floppy
TAIL = Spring(stiffness=40.0, damping=5.0)     # slow, heavy
TAIL_TIP = Spring(stiffness=60.0, damping=6.0)
CHIP = Spring(stiffness=90.0, damping=4.0)     # pendant, barely damped
TWITCH = Spring(stiffness=500.0, damping=16.0)  # ear flick, returns to rest
SUBSTEPS = 8


def follow(
    drive: Sequence[float],
    spring: Spring,
    dt: float,
    kicks: Mapping[int, float] | None = None,
) -> tuple[float, ...]:
    """Position of a damped follower of ``drive``; ``kicks`` add velocity at frame i."""
    if dt <= 0:
        raise ValueError("dt must be positive")
    kicks = kicks or {}
    out: list[float] = []
    x = drive[0] if drive else 0.0
    v = 0.0
    h = dt / SUBSTEPS  # stiff springs need a finer step than one video frame
    for i, target in enumerate(drive):
        v += kicks.get(i, 0.0)
        for _ in range(SUBSTEPS):
            a = spring.stiffness * (target - x) - spring.damping * v
            v += a * h
            x += v * h
        out.append(x)
    return tuple(out)


def lag(drive: Sequence[float], spring: Spring, dt: float) -> tuple[float, ...]:
    """``follow(...) - drive``: the swing a loosely attached part shows."""
    return tuple(x - d for x, d in zip(follow(drive, spring, dt), drive))
