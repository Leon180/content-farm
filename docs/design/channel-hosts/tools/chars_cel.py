"""賽璐璐研究室 vector hosts: C1 格仔 (底片格身體＋鉛筆呆毛), C2 芮秒研究員 (Q 版研究員)."""

from __future__ import annotations

from common import Look, blush, brow, document, eye, group, mouth, sparkles, sweat

# brand tokens (themes/brands/cel.css): animation paper, red pencil, shadow blue, non-photo-blue guides
PAPER, INK, RED, BLUE, GUIDE = "#f5f1e8", "#1f2329", "#cc2f2a", "#2a64a8", "#a9c8e8"

# ---------------------------------------------------------------- C1 格仔
FRAME = Look(line=INK, skin="#fffaf0", blush="#f2a29b")
FRAME_FACES = {
    "front": dict(eyes="open", mouth="smile", brows=None, fx=""),
    "think": dict(eyes="look_up", mouth="wobble", brows=(-10, 4), fx="dots"),
    "cut": dict(eyes="happy", mouth="grin", brows=(-12, 12), fx="sparkle"),
}


def film_frame(expr: str, uid: str) -> str:
    face = FRAME_FACES[expr]
    pencil = group("ahoge", '<g transform="rotate(14 200 150)">'
                   f'<rect x="191" y="62" width="18" height="92" rx="2" fill="{RED}" stroke="{INK}" stroke-width="4"/>'
                   f'<rect x="191" y="62" width="18" height="12" fill="#e9b6b3" stroke="{INK}" stroke-width="3"/>'
                   f'<path d="M191,154 L200,176 L209,154 Z" fill="#e9c79a" stroke="{INK}" stroke-width="3.5" '
                   f'stroke-linejoin="round"/><path d="M196,166 L200,176 L204,166 Z" fill="{INK}"/></g>')
    holes = "".join(f'<rect x="{x}" y="{y}" width="16" height="22" rx="4" fill="{PAPER}"/>'
                    for x in (102, 282) for y in (184, 226, 268, 310))
    body = group("body",
                 f'<rect x="88" y="164" width="224" height="210" rx="22" fill="#2b3038" stroke="{INK}" stroke-width="4.5"/>'
                 + holes
                 + f'<rect x="128" y="182" width="144" height="174" rx="8" fill="{FRAME.skin}" stroke="{INK}" stroke-width="3"/>'
                   f'<path d="M136,198 v-8 h8 M264,198 v-8 h-8 M136,340 v8 h8 M264,340 v8 h-8" fill="none" '
                   f'stroke="{BLUE}" stroke-width="2.6" opacity=".7"/>'
                   f'<text x="138" y="348" font-family="DIN Condensed, Avenir Next Condensed, sans-serif" font-size="18" '
                   f'fill="{BLUE}" opacity=".75">C-24</text>')
    legs = group("legs", f'<rect x="148" y="368" width="28" height="40" rx="12" fill="#2b3038" stroke="{INK}" stroke-width="4"/>'
                 f'<rect x="224" y="368" width="28" height="40" rx="12" fill="#2b3038" stroke="{INK}" stroke-width="4"/>')
    arms = (group("armL", f'<path d="M90,262 Q56,276 58,312" fill="none" stroke="{INK}" stroke-width="18" stroke-linecap="round"/>'
                  f'<path d="M90,262 Q56,276 58,312" fill="none" stroke="#2b3038" stroke-width="10" stroke-linecap="round"/>')
            + group("armR", f'<path d="M310,262 Q344,276 342,312" fill="none" stroke="{INK}" stroke-width="18" '
                    f'stroke-linecap="round"/><path d="M310,262 Q344,276 342,312" fill="none" stroke="#2b3038" '
                    f'stroke-width="10" stroke-linecap="round"/>'))
    brows = ""
    if face["brows"]:
        brows = group("brows", brow(172, 228, face["brows"][0], FRAME, s=0.9) + brow(228, 228, face["brows"][1], FRAME, s=0.9))
    fx = ""
    if face["fx"] == "dots":
        fx = "".join(f'<circle cx="{x}" cy="120" r="7" fill="{BLUE}"/>' for x in (300, 324, 348))
    elif face["fx"] == "sparkle":
        fx = sparkles([(64, 170), (338, 150), (352, 212)], RED, FRAME, r=13)
    facegrp = group("face", blush(156, 290, FRAME, opacity=0.6) + blush(244, 290, FRAME, opacity=0.6)
                    + group("eyeL", eye(172, 262, face["eyes"], FRAME, s=1.25))
                    + group("eyeR", eye(228, 262, face["eyes"], FRAME, s=1.25)) + brows
                    + group("mouth", mouth(200, 300, face["mouth"], FRAME, s=0.95)))
    return document(uid, FRAME, "", legs + arms + pencil + body + facegrp + group("fx", fx), rim_opacity=0.9)


# ---------------------------------------------------------------- C2 芮秒研究員
SKIN = "#f6dcc6"
HUMAN = Look(line=INK, skin=SKIN, blush="#f2a29b")
HAIR, HAIR_HI = "#34405a", "#4d5d7d"
HUMAN_FACES = {
    "front": dict(eyes="open", mouth="smile", brows=(-4, 4), fx=""),
    "explain": dict(eyes="open", mouth="talk", brows=(-14, 2), fx="point"),
    "audit": dict(eyes="squint", mouth="frown", brows=(14, -14), fx="sweat"),
}


def _timesheet() -> str:
    grid = "".join(f'<path d="M120,{y} h76" stroke="{GUIDE}" stroke-width="2"/>' for y in range(318, 380, 12))
    cols = "".join(f'<path d="M{x},306 v76" stroke="{GUIDE}" stroke-width="2"/>' for x in (140, 160, 180))
    return group("prop", f'<g transform="rotate(-8 158 344)"><rect x="112" y="298" width="92" height="92" rx="5" '
                 f'fill="#fffdf6" stroke="{INK}" stroke-width="4"/>{grid}{cols}'
                 f'<path d="M126,330 l40,24 M150,320 l28,40" stroke="{RED}" stroke-width="3.5" stroke-linecap="round"/>'
                 f'<rect x="140" y="290" width="36" height="12" rx="3" fill="{BLUE}" stroke="{INK}" stroke-width="3"/></g>')


def researcher(expr: str, uid: str) -> str:
    face = HUMAN_FACES[expr]
    back_hair = group("hairBack", f'<path d="M92,170 C92,90 140,62 200,62 C260,62 308,90 308,170 L314,262 '
                      f'Q276,276 254,250 L146,250 Q124,276 86,262 Z" fill="{HAIR}" stroke="{INK}" stroke-width="4.5" '
                      f'stroke-linejoin="round"/>')
    coat = group("body",
                 f'<path d="M140,256 L260,256 L292,404 Q200,416 108,404 Z" fill="{PAPER}" stroke="{INK}" stroke-width="4.5" '
                 f'stroke-linejoin="round"/><path d="M176,256 L200,300 L224,256 Z" fill="{BLUE}" stroke="{INK}" '
                 f'stroke-width="3.5" stroke-linejoin="round"/><path d="M200,300 L200,404" stroke="{INK}" stroke-width="3"/>'
                 f'<path d="M108,404 Q200,416 292,404" fill="none" stroke="{GUIDE}" stroke-width="6"/>'
                 f'<rect x="236" y="316" width="34" height="28" rx="3" fill="none" stroke="{INK}" stroke-width="3"/>'
                 f'<path d="M244,318 L248,292" stroke="{RED}" stroke-width="6" stroke-linecap="round"/>'
                 f'<rect x="164" y="404" width="22" height="8" rx="3" fill="{INK}"/><rect x="214" y="404" width="22" '
                 f'height="8" rx="3" fill="{INK}"/>')
    point = face["fx"] == "point"
    arm_r = (f'<path d="M262,274 Q312,250 330,206" fill="none" stroke="{INK}" stroke-width="30" stroke-linecap="round"/>'
             f'<path d="M262,274 Q312,250 330,206" fill="none" stroke="{PAPER}" stroke-width="21" stroke-linecap="round"/>'
             f'<circle cx="332" cy="196" r="12" fill="{SKIN}" stroke="{INK}" stroke-width="3.5"/>'
             f'<path d="M336,186 L346,160" stroke="{SKIN}" stroke-width="9" stroke-linecap="round"/>'
             f'<path d="M336,186 L346,160" stroke="{INK}" stroke-width="2" stroke-linecap="round" opacity="0"/>') if point else \
        (f'<path d="M262,274 Q290,320 268,356" fill="none" stroke="{INK}" stroke-width="30" stroke-linecap="round"/>'
         f'<path d="M262,274 Q290,320 268,356" fill="none" stroke="{PAPER}" stroke-width="21" stroke-linecap="round"/>'
         f'<circle cx="266" cy="362" r="12" fill="{SKIN}" stroke="{INK}" stroke-width="3.5"/>')
    arms = (group("armL", f'<path d="M140,274 Q112,312 150,340" fill="none" stroke="{INK}" stroke-width="30" '
                  f'stroke-linecap="round"/><path d="M140,274 Q112,312 150,340" fill="none" stroke="{PAPER}" '
                  f'stroke-width="21" stroke-linecap="round"/>') + _timesheet()
            + f'<circle cx="160" cy="342" r="12" fill="{SKIN}" stroke="{INK}" stroke-width="3.5"/>'
            + group("armR", arm_r))
    neck = f'<rect x="186" y="236" width="28" height="26" fill="{SKIN}" stroke="{INK}" stroke-width="4"/>'
    head_shape = f'<ellipse cx="200" cy="166" rx="86" ry="84" fill="{SKIN}" stroke="{INK}" stroke-width="4.5"/>'
    bangs = group("hairFront", f'<path d="M110,170 C104,104 146,76 200,76 C254,76 296,104 290,170 C276,140 262,126 246,118 '
                  f'L240,138 L222,116 L196,138 L184,114 L160,136 L156,118 C136,128 120,146 110,170 Z" fill="{HAIR}" '
                  f'stroke="{INK}" stroke-width="4.5" stroke-linejoin="round"/>'
                  f'<path d="M150,96 Q190,84 236,92" fill="none" stroke="{HAIR_HI}" stroke-width="6" stroke-linecap="round"/>'
                  f'<path d="M206,78 C210,50 236,40 248,52 C232,52 222,60 216,78 Z" fill="{HAIR}" stroke="{INK}" '
                  f'stroke-width="4" stroke-linejoin="round"/>')
    clip = group("hairclip", f'<rect x="250" y="112" width="40" height="12" rx="6" fill="{PAPER}" stroke="{INK}" '
                 f'stroke-width="3" transform="rotate(28 270 118)"/><circle cx="262" cy="113" r="3" fill="{INK}"/>'
                 f'<circle cx="278" cy="122" r="3" fill="{INK}"/>')
    glasses = group("glasses", f'<circle cx="164" cy="184" r="30" fill="#ffffff" fill-opacity=".18" stroke="#5a96d6" '
                    f'stroke-width="5"/><circle cx="236" cy="184" r="30" fill="#ffffff" fill-opacity=".18" '
                    f'stroke="#5a96d6" stroke-width="5"/><path d="M194,182 Q200,176 206,182" fill="none" '
                    f'stroke="#5a96d6" stroke-width="5"/>')
    brows = group("brows", brow(164, 142, face["brows"][0], HUMAN, s=0.95) + brow(236, 142, face["brows"][1], HUMAN, s=0.95))
    fx = sweat(300, 150, HUMAN) if face["fx"] == "sweat" else ""
    facegrp = group("face", blush(144, 218, HUMAN, opacity=0.55) + blush(256, 218, HUMAN, opacity=0.55)
                    + group("eyeL", eye(164, 186, face["eyes"], HUMAN, s=1.15, iris="#2a64a8"))
                    + group("eyeR", eye(236, 186, face["eyes"], HUMAN, s=1.15, iris="#2a64a8"))
                    + glasses + group("mouth", mouth(200, 222, face["mouth"], HUMAN, s=0.85)))
    head = group("head", head_shape + facegrp + bangs + brows + clip + group("fx", fx))
    return document(uid, HUMAN, "", back_hair + coat + arms + neck + head, rim_opacity=0.9)


HOSTS = {
    "c1": ("格仔", film_frame, tuple(FRAME_FACES)),
    "c2": ("芮秒研究員", researcher, tuple(HUMAN_FACES)),
}
