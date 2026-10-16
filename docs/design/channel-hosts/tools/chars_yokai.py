"""妖怪溯源所 vector hosts: Y1 說書貓・阿燈 (晶片貓換裝), Y2 小豸 (獬豸守門獸)."""

from __future__ import annotations

from common import Look, blush, brow, document, eye, group, mouth, sparkles, sweat

# brand tokens (src/content_farm/explainer/templates/themes/brands/yokai.css)
CINNABAR, VERDIGRIS, GOLD, PAPER, INK = "#e0503a", "#7fb39b", "#c9a45c", "#efe4cb", "#14110d"

# ---------------------------------------------------------------- Y1 說書貓
# head / ears / body / tail copied from the live rig so the costume sits on the same cat
CAT = Look(line="#222a3f", skin="#c7d2e2")
CAT_BASE, CAT_SHADE, CAT_WHITE = "#c7d2e2", "#9eadc5", "#f8f5ef"
HEAD = ("M200,74 C264,74 314,110 318,160 C320,180 316,194 330,206 C318,212 318,224 324,232 C304,236 292,248 268,254 "
        "C248,259 226,261 200,261 C174,261 152,259 132,254 C108,248 96,236 76,232 C82,224 82,212 70,206 C84,194 80,180 "
        "82,160 C86,110 136,74 200,74 Z")
BODY = ("M200,234 C150,234 116,272 108,322 C100,370 112,406 152,410 L248,410 C288,406 300,370 292,322 "
        "C284,272 250,234 200,234 Z")

CAT_FACES = {
    "front": dict(eyes="open", mouth="cat", brows=None, fx=""),
    "tell": dict(eyes="half", mouth="talk", brows=(-8, 8), fx="glow"),
    "spooked": dict(eyes="wide", mouth="o", brows=(14, -14), fx="sweat"),
}


def _cat_ears() -> str:
    return (group("earL", f'<path d="M98,140 C88,98 90,60 104,36 Q110,28 118,34 C140,52 158,72 172,94 Z" fill="{CAT_BASE}" '
                  f'stroke="{CAT.line}" stroke-width="4.5" stroke-linejoin="round"/>'
                  '<path d="M110,122 C104,94 106,68 114,52 C130,66 144,82 154,96 Z" fill="#f3a3b1"/>')
            + group("earR", f'<path d="M302,140 C312,98 310,60 296,36 Q290,28 282,34 C260,52 242,72 228,94 Z" '
                    f'fill="{CAT_BASE}" stroke="{CAT.line}" stroke-width="4.5" stroke-linejoin="round"/>'
                    '<path d="M290,122 C296,94 294,68 286,52 C270,66 256,82 246,96 Z" fill="#f3a3b1"/>'))


def _cat_hat() -> str:
    """斗笠 tipped back; the ears are drawn after it so they poke through."""
    weave = "".join(f'<path d="M200,34 L{x},{100 + abs(200 - x) * 0.04:.1f}" stroke="#8a6a3a" stroke-width="2.4"/>'
                    for x in (96, 132, 166, 234, 268, 304))
    return group("hat", f'<path d="M58,104 L200,30 L342,104 Q200,90 58,104 Z" fill="#c8a468" stroke="{CAT.line}" '
                 f'stroke-width="4.5" stroke-linejoin="round"/>{weave}'
                 f'<path d="M64,102 Q200,88 336,102" fill="none" stroke="{CINNABAR}" stroke-width="5"/>')


def _cat_lantern(lit: bool) -> str:
    glow = ('<circle cx="52" cy="318" r="74" fill="url(#y1glow)"/>' if lit
            else '<circle cx="52" cy="318" r="56" fill="url(#y1glow)" opacity="0.6"/>')
    return group("prop", glow
                 + f'<path d="M128,300 L52,262" stroke="#5b4630" stroke-width="7" stroke-linecap="round"/>'
                 + f'<path d="M52,262 L52,280" stroke="{CAT.line}" stroke-width="3"/>'
                 + f'<rect x="34" y="278" width="36" height="9" rx="3" fill="{CINNABAR}" stroke="{CAT.line}" stroke-width="3"/>'
                 + f'<ellipse cx="52" cy="318" rx="28" ry="33" fill="#f2c96b" stroke="{CAT.line}" stroke-width="4"/>'
                 + f'<path d="M52,286 L52,350 M36,292 Q28,318 36,344 M68,292 Q76,318 68,344" fill="none" '
                   f'stroke="#c58a2e" stroke-width="2.6"/>'
                 + f'<rect x="34" y="348" width="36" height="9" rx="3" fill="{CINNABAR}" stroke="{CAT.line}" stroke-width="3"/>'
                 + f'<path d="M52,358 L52,374" stroke="{CINNABAR}" stroke-width="4" stroke-linecap="round"/>')


def storyteller_cat(expr: str, uid: str) -> str:
    face = CAT_FACES[expr]
    defs = (f'<radialGradient id="y1glow"><stop offset="0" stop-color="#ffd98a" stop-opacity="0.75"/>'
            f'<stop offset="1" stop-color="#ffd98a" stop-opacity="0"/></radialGradient>'
            f'<clipPath id="{uid}-head"><path d="{HEAD}"/></clipPath>')
    tail = group("tail", '<path d="M262,394 C314,396 340,352 330,304 C324,276 308,262 294,268" fill="none" '
                 f'stroke="{CAT.line}" stroke-width="34" stroke-linecap="round"/>'
                 '<path d="M262,394 C314,396 340,352 330,304 C324,276 308,262 294,268" fill="none" '
                 f'stroke="{CAT_BASE}" stroke-width="25" stroke-linecap="round"/>')
    body = group("body", f'<path d="{BODY}" fill="{CAT_BASE}" stroke="{CAT.line}" stroke-width="4.5"/>'
                 f'<ellipse cx="200" cy="338" rx="46" ry="66" fill="{CAT_WHITE}"/>')
    cape = group("cape",
                 f'<path d="M118,262 Q160,246 192,256 L180,410 Q118,414 72,404 Z" fill="#2f4a42" stroke="{CAT.line}" '
                 f'stroke-width="4.5" stroke-linejoin="round"/>'
                 f'<path d="M282,262 Q240,246 208,256 L220,410 Q282,414 328,404 Z" fill="#2f4a42" stroke="{CAT.line}" '
                 f'stroke-width="4.5" stroke-linejoin="round"/>'
                 f'<path d="M186,262 L176,404 M214,262 L224,404" stroke="{GOLD}" stroke-width="3"/>'
                 f'<path d="M96,330 Q120,326 150,338 M304,330 Q280,326 250,338" fill="none" stroke="#24382f" stroke-width="3"/>')
    knot = group("collar", f'<path d="M176,258 Q200,276 224,258 L214,280 Q200,288 186,280 Z" fill="{CINNABAR}" '
                 f'stroke="{CAT.line}" stroke-width="4" stroke-linejoin="round"/>'
                 f'<rect x="188" y="282" width="24" height="20" rx="4" fill="{CAT.line}"/>'
                 f'<rect x="195" y="287" width="10" height="10" rx="2" fill="#f2b23e"/>')
    arm = group("armL", f'<path d="M136,290 Q120,296 118,304" stroke="{CAT.line}" stroke-width="0"/>'
                f'<ellipse cx="124" cy="302" rx="20" ry="19" fill="{CAT_WHITE}" stroke="{CAT.line}" stroke-width="4"/>')
    marks = ('<g clip-path="url(#' + uid + '-head)"><path d="M176,104 L166,116 M224,104 L234,116 M76,176 L100,176 L108,168 '
             'M80,192 L102,192 M324,176 L300,176 L292,168 M320,192 L298,192" fill="none" stroke="#6c7c9a" '
             'stroke-width="6.5" stroke-linecap="round"/><g fill="#f2b23e" stroke="#222a3f" stroke-width="2.4">'
             '<circle cx="166" cy="121" r="5.6"/><circle cx="234" cy="121" r="5.6"/></g></g>')
    faces = blush(124, 216, CAT, s=1.05, opacity=0.55) + blush(276, 216, CAT, s=1.05, opacity=0.55)
    faces += (f'<ellipse cx="186" cy="216" rx="19" ry="13" fill="{CAT_WHITE}"/>'
              f'<ellipse cx="214" cy="216" rx="19" ry="13" fill="{CAT_WHITE}"/>')
    eyes = group("eyeL", eye(150, 176, face["eyes"], CAT, s=1.9, iris="#f4a93a")) + \
        group("eyeR", eye(250, 176, face["eyes"], CAT, s=1.9, iris="#f4a93a"))
    brows = ""
    if face["brows"]:
        brows = group("brows", brow(150, 132, face["brows"][0], CAT, s=1.3) + brow(250, 132, face["brows"][1], CAT, s=1.3))
    nose = (f'<path d="M191,204 Q200,199 209,204 Q205,213 200,214 Q195,213 191,204 Z" fill="#e57e95" '
            f'stroke="{CAT.line}" stroke-width="2.6"/>')
    whisk = (f'<path d="M118,222 L80,214 M118,230 L82,236 M282,222 L320,214 M282,230 L318,236" stroke="{CAT.line}" '
             f'stroke-width="2.2" stroke-linecap="round" opacity="0.5"/>')
    fx = sweat(338, 118, CAT) if face["fx"] == "sweat" else ""
    head = group("head", f'<path d="{HEAD}" fill="{CAT_BASE}" stroke="{CAT.line}" stroke-width="4.5"/>' + marks
                 + group("face", faces + eyes + brows + nose + group("mouth", mouth(200, 220, face["mouth"], CAT)) + whisk)
                 + _cat_hat() + _cat_ears() + group("fx", fx))
    parts = tail + body + cape + knot + _cat_lantern(face["fx"] == "glow") + arm + head
    return document(uid, CAT, defs, parts, rim=GOLD, rim_opacity=0.55)


# ---------------------------------------------------------------- Y2 小豸
BEAST = Look(line="#1d1813", skin=PAPER, blush="#e8907a")
MANE = "#2a241c"
BEAST_FACES = {
    "front": dict(eyes="open", mouth="smile", brows=(-6, 6), fx=""),
    "doubt": dict(eyes="squint", mouth="flat", brows=(16, 16), fx="question"),
    "found": dict(eyes="happy", mouth="grin", brows=(-14, 14), fx="sparkle"),
}


def _mane() -> str:
    tufts = [(94, 120, 34), (82, 168, 32), (92, 214, 30), (122, 92, 32), (164, 76, 30), (236, 76, 30),
             (278, 92, 32), (306, 120, 34), (318, 168, 32), (308, 214, 30), (130, 246, 30), (270, 246, 30),
             (200, 258, 32)]
    curls = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{MANE}"/>' for x, y, r in tufts)
    hooks = "".join(f'<path d="M{x - r * .4},{y + r * .1} q{r * .35},{-r * .55} {r * .6},0" fill="none" '
                    f'stroke="#5b4e3c" stroke-width="3.2" stroke-linecap="round"/>' for x, y, r in tufts)
    return group("mane", curls + hooks)


def guardian_beast(expr: str, uid: str) -> str:
    face = BEAST_FACES[expr]
    tail = group("tail", f'<path d="M270,380 C338,380 362,330 344,290 C332,262 302,262 300,286 C298,304 320,308 326,296" '
                 f'fill="none" stroke="{MANE}" stroke-width="30" stroke-linecap="round"/>'
                 f'<path d="M318,262 q14,-24 34,-20 M352,300 q22,-6 30,8" stroke="{MANE}" stroke-width="12" '
                 f'stroke-linecap="round" fill="none"/>')
    body = group("body",
                 f'<path d="M200,236 C140,236 112,290 112,340 C112,384 132,410 168,410 L232,410 C268,410 288,384 288,340 '
                 f'C288,290 260,236 200,236 Z" fill="{PAPER}" stroke="{BEAST.line}" stroke-width="4.5"/>'
                 f'<path d="M130,330 q16,-10 30,0 q14,10 28,0 M212,330 q14,-10 28,0 q16,10 30,0" fill="none" '
                 f'stroke="#b9a782" stroke-width="3"/>'
                 f'<rect x="146" y="352" width="42" height="58" rx="18" fill="{PAPER}" stroke="{BEAST.line}" stroke-width="4"/>'
                 f'<rect x="212" y="352" width="42" height="58" rx="18" fill="{PAPER}" stroke="{BEAST.line}" stroke-width="4"/>'
                 f'<path d="M150,404 q10,-10 17,0 q8,-10 17,0 M216,404 q10,-10 17,0 q8,-10 17,0" fill="{MANE}" '
                 f'stroke="{MANE}" stroke-width="4" stroke-linejoin="round"/>')
    seal = group("seal", f'<g transform="rotate(-6 200 300)"><rect x="180" y="280" width="40" height="40" rx="5" '
                 f'fill="{CINNABAR}" stroke="{BEAST.line}" stroke-width="3.5"/>'
                 f'<rect x="185" y="285" width="30" height="30" rx="2" fill="none" stroke="{PAPER}" stroke-width="2"/>'
                 f'<text x="200" y="309" text-anchor="middle" font-family="Songti TC, serif" font-weight="700" '
                 f'font-size="22" fill="{PAPER}">真</text></g>')
    horn = group("horn", f'<path d="M184,92 Q186,44 222,12 Q212,52 216,94 Z" fill="{VERDIGRIS}" stroke="{BEAST.line}" '
                 f'stroke-width="4.5" stroke-linejoin="round"/><path d="M192,72 L212,66 M190,56 L214,46" '
                 f'stroke="#4d7a66" stroke-width="3" stroke-linecap="round"/>')
    ears = (group("earL", f'<path d="M104,150 C70,150 58,190 76,214 C92,206 104,186 112,166 Z" fill="{MANE}"/>')
            + group("earR", f'<path d="M296,150 C330,150 342,190 324,214 C308,206 296,186 288,166 Z" fill="{MANE}"/>'))
    cheeks = (f'<path d="M108,214 q14,-14 28,0 q-14,6 -28,0 M292,214 q-14,-14 -28,0 q14,6 28,0" fill="none" '
              f'stroke="#b9a782" stroke-width="3"/>')
    eyes = (group("eyeL", eye(152, 178, face["eyes"], BEAST, s=1.55, iris=GOLD))
            + group("eyeR", eye(248, 178, face["eyes"], BEAST, s=1.55, iris=GOLD)))
    brows = group("brows", f'<g stroke-width="9">{brow(150, 136, face["brows"][0], BEAST, s=1.4)}'
                  f'{brow(250, 136, -face["brows"][1] if face["brows"][0] == face["brows"][1] else face["brows"][1], BEAST, s=1.4)}</g>')
    snout = (f'<ellipse cx="200" cy="222" rx="44" ry="28" fill="#f7efdc"/>'
             f'<path d="M186,206 Q200,200 214,206 Q208,218 200,219 Q192,218 186,206 Z" fill="{MANE}"/>')
    fx = ""
    if face["fx"] == "question":
        fx = (f'<text x="330" y="96" font-family="Songti TC, serif" font-weight="700" font-size="64" fill="{CINNABAR}" '
              f'stroke="{BEAST.line}" stroke-width="3" paint-order="stroke">？</text>')
    elif face["fx"] == "sparkle":
        fx = sparkles([(62, 92), (344, 70), (330, 136)], GOLD, BEAST, r=14)
    head = group("head", _mane() + ears + f'<ellipse cx="200" cy="172" rx="112" ry="92" fill="{PAPER}" '
                 f'stroke="{BEAST.line}" stroke-width="4.5"/>' + horn
                 + group("face", cheeks + blush(116, 200, BEAST, opacity=0.45) + blush(284, 200, BEAST, opacity=0.45)
                         + eyes + brows + snout + group("mouth", mouth(200, 236, face["mouth"], BEAST)))
                 + group("fx", fx))
    return document(uid, BEAST, "", tail + body + seal + head, rim=GOLD, rim_opacity=0.6)


HOSTS = {
    "y1": ("說書貓・阿燈", storyteller_cat, tuple(CAT_FACES)),
    "y2": ("小豸", guardian_beast, tuple(BEAST_FACES)),
}
