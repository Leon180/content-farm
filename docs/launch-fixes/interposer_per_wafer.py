"""How many square interposers fit on a 300 mm wafer (3 mm edge exclusion)?

Rows of squares; each row may slide horizontally independently and the whole grid
may slide vertically. Search offsets on a fine step and keep the best count.
A square fits when all four corners are inside the usable circle.
"""
import math

R = 150 - 3.0


def row_count(side: float, y0: float) -> int:
    y1 = y0 + side
    ymax = max(abs(y0), abs(y1))
    if ymax > R:
        return 0
    half = math.sqrt(R * R - ymax * ymax)  # usable half-width at the row's worst edge
    return int((2 * half) // side)


def best(side: float, steps: int = 400) -> int:
    top = 0
    for k in range(steps):
        off = side * k / steps
        y = -R + off
        total = 0
        while y + side <= R:
            total += row_count(side, y)
            y += side
        top = max(top, total)
    return top


for label, area in (("P100 era interposer ~830", 830), ("1x reticle 858", 858), ("3.3x 2831", 2831),
                    ("5.5x 4719", 4719), ("9x 7722", 7722)):
    side = math.sqrt(area)
    print(f"{label:28s} side {side:5.1f} mm -> {best(side)} per wafer")
