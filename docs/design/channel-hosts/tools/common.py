"""Shared pieces for the host concept SVGs.

Conventions copied from the 晶片貓 rig (src/content_farm/explainer/mascot/assets/rig.html):
a 400x440 character box, floor anchor (200,410), one sticker filter (outer line + light rim +
shadow) on the whole character, and named part groups so phase 2 can drive them with the same
Live2D-style parameters: body, head, earL/earR (or hair), eyeL/eyeR, brows, mouth, armL/armR,
tail, prop, fx. Every expression is the same drawing with only eyes / brows / mouth / fx swapped.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Look:
    line: str                 # outline / ink colour
    skin: str                 # face fill, used by eyelids that cover an eye
    mouth_in: str = "#6e2236"
    tongue: str = "#f0899b"
    blush: str = "#f3a3b1"
    hard_shadow: bool = False  # offwork: hard offset shadow, no blur, ever


def sticker_filter(uid: str, look: Look, rim: str = "#ffffff", rim_opacity: float = 0.4) -> str:
    if look.hard_shadow:
        shadow = (f'<feOffset in="SourceAlpha" dx="8" dy="8" result="o"/><feMorphology in="o" operator="dilate" '
                  f'radius="3" result="od"/><feFlood flood-color="{look.line}"/><feComposite in2="od" operator="in" '
                  f'result="shadow"/>')
    else:
        shadow = ('<feGaussianBlur in="SourceAlpha" stdDeviation="6" result="b"/><feOffset in="b" dy="6" result="o"/>'
                  '<feFlood flood-color="#000" flood-opacity="0.3"/><feComposite in2="o" operator="in" result="shadow"/>')
    return (f'<filter id="st-{uid}" x="-20%" y="-20%" width="140%" height="140%">'
            f'<feMorphology in="SourceAlpha" operator="dilate" radius="3" result="line"/>'
            f'<feFlood flood-color="{look.line}"/><feComposite in2="line" operator="in" result="outline"/>'
            f'<feMorphology in="SourceAlpha" operator="dilate" radius="6" result="rimA"/>'
            f'<feFlood flood-color="{rim}" flood-opacity="{rim_opacity}"/><feComposite in2="rimA" operator="in" result="rim"/>'
            f'{shadow}<feMerge><feMergeNode in="shadow"/><feMergeNode in="rim"/><feMergeNode in="outline"/>'
            f'<feMergeNode in="SourceGraphic"/></feMerge></filter>')


def document(uid: str, look: Look, defs: str, parts: str, *, width: int = 400, height: int = 440,
             rim: str = "#ffffff", rim_opacity: float = 0.4) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" overflow="visible">'
            f'<defs>{sticker_filter(uid, look, rim, rim_opacity)}{defs}</defs>'
            f'<g id="host" filter="url(#st-{uid})">{parts}</g></svg>')


def eye(cx: float, cy: float, state: str, look: Look, *, s: float = 1.0, iris: str | None = None) -> str:
    """Round mascot eye. states: open, closed (blink), happy (^), wide, half (lid), squint, look_up."""
    ln, rx, ry = look.line, 13 * s, 16 * s
    if state == "closed":
        return (f'<path d="M{cx - 14 * s},{cy} Q{cx},{cy + 9 * s} {cx + 14 * s},{cy}" fill="none" '
                f'stroke="{ln}" stroke-width="{5 * s}" stroke-linecap="round"/>')
    if state == "happy":
        return (f'<path d="M{cx - 14 * s},{cy + 5 * s} Q{cx},{cy - 12 * s} {cx + 14 * s},{cy + 5 * s}" fill="none" '
                f'stroke="{ln}" stroke-width="{5 * s}" stroke-linecap="round"/>')
    if state == "wide":
        return (f'<circle cx="{cx}" cy="{cy}" r="{17 * s}" fill="#ffffff" stroke="{ln}" stroke-width="{3.5 * s}"/>'
                f'<circle cx="{cx}" cy="{cy}" r="{6 * s}" fill="{ln}"/>')
    dy = -5 * s if state == "look_up" else 0
    body = f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{ln}"/>'
    if iris:
        body += f'<ellipse cx="{cx}" cy="{cy + dy}" rx="{rx * 0.72}" ry="{ry * 0.75}" fill="{iris}"/>' \
                f'<ellipse cx="{cx}" cy="{cy + dy}" rx="{rx * 0.32}" ry="{ry * 0.5}" fill="{ln}"/>'
    body += (f'<circle cx="{cx - 4 * s}" cy="{cy - 6 * s + dy}" r="{4.6 * s}" fill="#fff"/>'
             f'<circle cx="{cx + 4.5 * s}" cy="{cy + 6 * s + dy}" r="{2 * s}" fill="#fff"/>')
    if state in ("half", "squint"):
        top = cy - ry - 3 * s
        edge = cy - 2 * s if state == "half" else cy + 3 * s
        body += (f'<path d="M{cx - rx - 4 * s},{top} L{cx + rx + 4 * s},{top} L{cx + rx + 4 * s},{edge} '
                 f'L{cx - rx - 4 * s},{edge} Z" fill="{look.skin}"/>'
                 f'<path d="M{cx - rx - 3 * s},{edge} L{cx + rx + 3 * s},{edge}" stroke="{ln}" '
                 f'stroke-width="{4.5 * s}" stroke-linecap="round"/>')
    if state == "squint":
        bottom = cy + ry + 3 * s
        body += (f'<path d="M{cx - rx - 4 * s},{bottom} L{cx + rx + 4 * s},{bottom} L{cx + rx + 4 * s},{cy + 9 * s} '
                 f'L{cx - rx - 4 * s},{cy + 9 * s} Z" fill="{look.skin}"/>')
    return body


def brow(cx: float, cy: float, angle: float, look: Look, *, s: float = 1.0) -> str:
    return (f'<path d="M{cx - 11 * s},{cy} L{cx + 11 * s},{cy}" stroke="{look.line}" stroke-width="{4.5 * s}" '
            f'stroke-linecap="round" transform="rotate({angle} {cx} {cy})"/>')


def mouth(cx: float, cy: float, state: str, look: Look, *, s: float = 1.0) -> str:
    """states: smile, cat (ω), talk, grin, flat, o, smirk, wobble, frown."""
    ln, w = look.line, 3.6 * s
    stroke = f'fill="none" stroke="{ln}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"'
    if state == "smile":
        return f'<path d="M{cx - 12 * s},{cy} Q{cx},{cy + 11 * s} {cx + 12 * s},{cy}" {stroke}/>'
    if state == "cat":
        return (f'<path d="M{cx - 16 * s},{cy - 1 * s} Q{cx - 8 * s},{cy + 9 * s} {cx},{cy} '
                f'Q{cx + 8 * s},{cy + 9 * s} {cx + 16 * s},{cy - 1 * s}" {stroke}/>')
    if state in ("talk", "grin"):
        wd, dp = (13 * s, 22 * s) if state == "talk" else (19 * s, 18 * s)
        return (f'<path d="M{cx - wd},{cy} Q{cx},{cy + 4 * s} {cx + wd},{cy} Q{cx + wd - 1},{cy + dp} {cx},{cy + dp + 2 * s} '
                f'Q{cx - wd + 1},{cy + dp} {cx - wd},{cy} Z" fill="{look.mouth_in}" stroke="{ln}" stroke-width="{3.2 * s}" '
                f'stroke-linejoin="round"/><ellipse cx="{cx}" cy="{cy + dp - 4 * s}" rx="{7 * s}" ry="{4 * s}" '
                f'fill="{look.tongue}"/>')
    if state == "flat":
        return f'<path d="M{cx - 11 * s},{cy + 3 * s} L{cx + 11 * s},{cy + 3 * s}" {stroke}/>'
    if state == "o":
        return (f'<ellipse cx="{cx}" cy="{cy + 6 * s}" rx="{7 * s}" ry="{9 * s}" fill="{look.mouth_in}" '
                f'stroke="{ln}" stroke-width="{3 * s}"/>')
    if state == "smirk":
        return f'<path d="M{cx - 12 * s},{cy + 4 * s} Q{cx + 2 * s},{cy + 9 * s} {cx + 15 * s},{cy - 5 * s}" {stroke}/>'
    if state == "wobble":
        return (f'<path d="M{cx - 14 * s},{cy + 5 * s} Q{cx - 7 * s},{cy - 1 * s} {cx},{cy + 5 * s} '
                f'Q{cx + 7 * s},{cy + 11 * s} {cx + 14 * s},{cy + 5 * s}" {stroke}/>')
    if state == "frown":
        return f'<path d="M{cx - 11 * s},{cy + 7 * s} Q{cx},{cy - 3 * s} {cx + 11 * s},{cy + 7 * s}" {stroke}/>'
    raise ValueError(f"unknown mouth {state!r}")


def blush(cx: float, cy: float, look: Look, *, s: float = 1.0, opacity: float = 0.6) -> str:
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{15 * s}" ry="{8 * s}" fill="{look.blush}" opacity="{opacity}"/>'


def sweat(x: float, y: float, look: Look) -> str:
    return (f'<path d="M{x},{y} C{x - 10},{y + 18} {x - 12},{y + 30} {x},{y + 32} C{x + 12},{y + 30} {x + 10},{y + 18} '
            f'{x},{y} Z" fill="#8fd3ff" stroke="{look.line}" stroke-width="3"/>')


def sparkles(points: list[tuple[float, float]], colour: str, look: Look, *, r: float = 12) -> str:
    out = []
    for x, y in points:
        out.append(f'<path d="M{x},{y - r} Q{x + r * .18},{y - r * .18} {x + r},{y} Q{x + r * .18},{y + r * .18} {x},{y + r} '
                   f'Q{x - r * .18},{y + r * .18} {x - r},{y} Q{x - r * .18},{y - r * .18} {x},{y - r} Z" fill="{colour}" '
                   f'stroke="{look.line}" stroke-width="2.4" stroke-linejoin="round"/>')
    return "".join(out)


def group(gid: str, inner: str, transform: str = "") -> str:
    t = f' transform="{transform}"' if transform else ""
    return f'<g id="{gid}"{t}>{inner}</g>'
