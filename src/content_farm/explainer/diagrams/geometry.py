"""Geometry behind the channel's own estimate: how many square interposers fit on a 300 mm wafer.

A square of side √A on a square grid; the grid offset is searched so the count is the best one
(within ``OFFSET_STEPS``²). Edge exclusion default 3 mm. This is a geometric rough estimate
(本頻道幾何粗估), not TSMC's yield or layout figure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

WAFER_MM = 300.0
EDGE_MM = 3.0
OFFSET_STEPS = 24
RETICLE_MM = (26.0, 33.0)              # max exposure field: 858 mm²
RETICLE_AREA = RETICLE_MM[0] * RETICLE_MM[1]


@dataclass(frozen=True)
class Packing:
    side_mm: float
    count: int
    squares: tuple[tuple[float, float], ...]   # lower-left corners, mm, wafer centre at (0, 0)


def _fits(x: float, y: float, side: float, radius: float) -> bool:
    corners = ((x, y), (x + side, y), (x, y + side), (x + side, y + side))
    return all(cx * cx + cy * cy <= radius * radius for cx, cy in corners)


def pack(area_mm2: float, *, wafer_mm: float = WAFER_MM, edge_mm: float = EDGE_MM) -> Packing:
    side = math.sqrt(area_mm2)
    radius = wafer_mm / 2 - edge_mm
    best: tuple[tuple[float, float], ...] = ()
    n = int(2 * radius // side) + 2
    for i in range(OFFSET_STEPS):
        for j in range(OFFSET_STEPS):
            ox, oy = side * i / OFFSET_STEPS, side * j / OFFSET_STEPS
            squares = tuple((ox + a * side - radius - side, oy + b * side - radius - side)
                            for a in range(n + 1) for b in range(n + 1)
                            if _fits(ox + a * side - radius - side, oy + b * side - radius - side, side, radius))
            if len(squares) > len(best):
                best = squares
    return Packing(side, len(best), best)


def reticle_multiple(area_mm2: float) -> float:
    return round(area_mm2 / RETICLE_AREA, 2)
