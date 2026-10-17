"""晶片貓下班了 vector hosts: O1 下班貓＋PM 狗 (晶片貓便服), O2 便利貼精・黏黏."""

from __future__ import annotations

from common import Look, blush, brow, document, eye, group, mouth, sparkles, sweat

# brand tokens (themes/brands/offwork.css): black ink, hard offset shadow, pink punchline, blue = PM 狗
INK, PINK, BLUE, PAPER = "#141414", "#c2185b", "#1a4fd8", "#ffffff"

# ---------------------------------------------------------------- O1 下班貓＋PM 狗
CAT = Look(line=INK, skin="#c7d2e2", hard_shadow=True)
DOG = Look(line=INK, skin="#e8c590", hard_shadow=True)
CAT_BASE, CAT_WHITE, HOODIE = "#c7d2e2", "#f8f5ef", "#3b3f4a"
HEAD = ("M200,74 C264,74 314,110 318,160 C320,180 316,194 330,206 C318,212 318,224 324,232 C304,236 292,248 268,254 "
        "C248,259 226,261 200,261 C174,261 152,259 132,254 C108,248 96,236 76,232 C82,224 82,212 70,206 C84,194 80,180 "
        "82,160 C86,110 136,74 200,74 Z")

DUO_FACES = {
    "front": dict(cat_eyes="half", cat_mouth="cat", dog_eyes="happy", dog_mouth="smile", fx=""),
    "deadpan": dict(cat_eyes="half", cat_mouth="flat", dog_eyes="open", dog_mouth="talk", fx="sweat"),
    "clockout": dict(cat_eyes="happy", cat_mouth="grin", dog_eyes="wide", dog_mouth="o", fx="sparkle"),
}


def _pm_dog(face: dict) -> str:
    """Leans in from the left, above the meta row and subtitle band (checked by frames.py)."""
    ears = (f'<path d="M48,86 C24,92 18,140 34,158 C50,152 58,128 64,104 Z" fill="#8a5a3a"/>'
            f'<path d="M144,86 C168,92 174,140 158,158 C142,152 134,128 128,104 Z" fill="#8a5a3a"/>')
    collar = (f'<path d="M62,150 L130,150 L136,180 L56,180 Z" fill="{BLUE}" stroke="{INK}" stroke-width="4.5" '
              f'stroke-linejoin="round"/><path d="M80,150 L96,166 L112,150" fill="{PAPER}" stroke="{INK}" stroke-width="3.5"/>')
    head = (f'<ellipse cx="96" cy="112" rx="54" ry="48" fill="{DOG.skin}" stroke="{INK}" stroke-width="4.5"/>'
            f'<ellipse cx="96" cy="132" rx="26" ry="18" fill="#f7e6c4"/>'
            f'<ellipse cx="96" cy="122" rx="9" ry="6.5" fill="{INK}"/>')
    face_parts = (group("eyeL", eye(76, 104, face["dog_eyes"], DOG, s=0.8))
                  + group("eyeR", eye(116, 104, face["dog_eyes"], DOG, s=0.8))
                  + group("mouth", mouth(96, 134, face["dog_mouth"], DOG, s=0.75)))
    board = (f'<g transform="rotate(-12 34 118)"><rect x="8" y="78" width="52" height="66" rx="5" fill="#d9b27a" '
             f'stroke="{INK}" stroke-width="4"/><rect x="15" y="88" width="38" height="50" fill="{PAPER}"/>'
             f'<rect x="22" y="72" width="24" height="12" rx="3" fill="{INK}"/>'
             f'<path d="M20,100 h28 M20,112 h28 M20,124 h18" stroke="{BLUE}" stroke-width="3.5"/>'
             f'<path d="M40,121 l5,6 l9,-12" fill="none" stroke="{PINK}" stroke-width="4" stroke-linecap="round"/></g>'
             f'<ellipse cx="58" cy="140" rx="14" ry="12" fill="{DOG.skin}" stroke="{INK}" stroke-width="4"/>')
    # lifted 60 px: on frame the meta row (y 832–872, x ≤ 1520) is the binding limit, not the subtitles
    return group("partner", collar + ears + head + group("dogFace", face_parts) + board, "translate(0 -60)")


def _hoodie_cat(face: dict) -> str:
    hood = group("hood", f'<path d="M60,236 C40,150 96,58 200,54 C304,58 360,150 340,236 Z" fill="{HOODIE}" '
                 f'stroke="{INK}" stroke-width="4.5"/>')
    body = group("body",
                 f'<path d="M200,232 C140,232 106,272 100,326 C94,376 110,408 152,410 L248,410 C290,408 306,376 300,326 '
                 f'C294,272 260,232 200,232 Z" fill="{HOODIE}" stroke="{INK}" stroke-width="4.5"/>'
                 f'<path d="M150,346 Q200,334 250,346 L256,392 Q200,402 144,392 Z" fill="#4a4f5c" stroke="{INK}" '
                 f'stroke-width="4"/>'
                 f'<path d="M184,250 L180,300 M216,250 L220,300" stroke="{PINK}" stroke-width="5" stroke-linecap="round"/>'
                 f'<circle cx="180" cy="304" r="6" fill="{PINK}" stroke="{INK}" stroke-width="2.5"/>'
                 f'<circle cx="220" cy="304" r="6" fill="{PINK}" stroke="{INK}" stroke-width="2.5"/>')
    mug = group("prop", f'<rect x="268" y="292" width="54" height="62" rx="9" fill="{PAPER}" stroke="{INK}" stroke-width="4.5"/>'
                f'<rect x="268" y="306" width="54" height="12" fill="{PINK}"/>'
                f'<path d="M322,306 q24,4 22,22 q-2,16 -22,16" fill="none" stroke="{INK}" stroke-width="7"/>'
                f'<path d="M284,282 q8,-14 0,-28 M304,282 q8,-14 0,-28" fill="none" stroke="{INK}" stroke-width="4" '
                f'stroke-linecap="round" opacity=".55"/>'
                f'<ellipse cx="268" cy="332" rx="20" ry="18" fill="{CAT_WHITE}" stroke="{INK}" stroke-width="4"/>')
    ears = (group("earL", f'<path d="M98,140 C88,98 90,60 104,36 Q110,28 118,34 C140,52 158,72 172,94 Z" fill="{HOODIE}" '
                  f'stroke="{INK}" stroke-width="4.5" stroke-linejoin="round"/>'
                  '<path d="M112,120 C106,94 108,70 116,56 C130,68 142,82 150,96 Z" fill="#f3a3b1"/>')
            + group("earR", f'<path d="M302,140 C312,98 310,60 296,36 Q290,28 282,34 C260,52 242,72 228,94 Z" '
                    f'fill="{HOODIE}" stroke="{INK}" stroke-width="4.5" stroke-linejoin="round"/>'
                    '<path d="M288,120 C294,94 292,70 284,56 C270,68 258,82 250,96 Z" fill="#f3a3b1"/>'))
    face_parts = (blush(124, 216, CAT, opacity=0.55) + blush(276, 216, CAT, opacity=0.55)
                  + f'<ellipse cx="186" cy="216" rx="19" ry="13" fill="{CAT_WHITE}"/>'
                    f'<ellipse cx="214" cy="216" rx="19" ry="13" fill="{CAT_WHITE}"/>'
                  + group("eyeL", eye(150, 176, face["cat_eyes"], CAT, s=1.9, iris="#f4a93a"))
                  + group("eyeR", eye(250, 176, face["cat_eyes"], CAT, s=1.9, iris="#f4a93a"))
                  + f'<path d="M191,204 Q200,199 209,204 Q205,213 200,214 Q195,213 191,204 Z" fill="#e57e95" '
                    f'stroke="{INK}" stroke-width="2.6"/>'
                  + group("mouth", mouth(200, 220, face["cat_mouth"], CAT)))
    marks = ('<path d="M200,82 L200,110 M176,84 L176,94 L166,104 L166,116 M224,84 L224,94 L234,104 L234,116" fill="none" '
             'stroke="#6c7c9a" stroke-width="6.5" stroke-linecap="round"/><g fill="#f2b23e" stroke="#141414" '
             'stroke-width="2.4"><circle cx="200" cy="115" r="5.6"/><circle cx="166" cy="121" r="5.6"/>'
             '<circle cx="234" cy="121" r="5.6"/></g>')
    fx = ""
    if face["fx"] == "sweat":
        fx = sweat(334, 112, CAT)
    elif face["fx"] == "sparkle":
        fx = sparkles([(52, 60), (352, 54)], "#ffd84d", CAT, r=16)
    head = group("head", ears + f'<path d="{HEAD}" fill="{CAT_BASE}" stroke="{INK}" stroke-width="4.5"/>' + marks
                 + group("face", face_parts) + group("fx", fx))
    return hood + body + mug + head


def offwork_duo(expr: str, uid: str) -> str:
    face = DUO_FACES[expr]
    cat = f'<g transform="translate(160 0)">{_hoodie_cat(face)}</g>'
    return document(uid, CAT, "", _pm_dog(face) + cat, width=560, rim_opacity=0.0)


# ---------------------------------------------------------------- O2 便利貼精・黏黏
NOTE = Look(line=INK, skin="#ff9cc2", hard_shadow=True)
NOTE_FACES = {
    "front": dict(eyes="open", mouth="smile", brows=None, curl=0.0, fx=""),
    "later": dict(eyes="half", mouth="smirk", brows=(8, -8), curl=0.0, fx="zzz"),
    "peeled": dict(eyes="wide", mouth="o", brows=(18, -18), curl=1.0, fx="sweat"),
}


def sticky_note(expr: str, uid: str) -> str:
    face = NOTE_FACES[expr]
    legs = group("legs", f'<path d="M168,330 L160,398 M232,330 L240,398" stroke="{INK}" stroke-width="7" '
                 f'stroke-linecap="round"/><ellipse cx="152" cy="404" rx="22" ry="10" fill="{BLUE}" stroke="{INK}" '
                 f'stroke-width="4"/><ellipse cx="248" cy="404" rx="22" ry="10" fill="{BLUE}" stroke="{INK}" '
                 f'stroke-width="4"/>')
    arms = (group("armL", f'<path d="M92,250 Q58,262 52,300" fill="none" stroke="{INK}" stroke-width="7" '
                  f'stroke-linecap="round"/><circle cx="52" cy="304" r="12" fill="{PAPER}" stroke="{INK}" stroke-width="4"/>')
            + group("armR", f'<path d="M308,250 Q342,236 350,200" fill="none" stroke="{INK}" stroke-width="7" '
                    f'stroke-linecap="round"/><circle cx="350" cy="196" r="12" fill="{PAPER}" stroke="{INK}" '
                    f'stroke-width="4"/><path d="M356,192 L382,150" stroke="{BLUE}" stroke-width="9" stroke-linecap="round"/>'
                    f'<path d="M382,150 L390,136" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>'))
    curl_y = 340 - 46 * face["curl"]
    corner = (f'<path d="M300,{curl_y - 10:.0f} L300,342 L{258 - 30 * face["curl"]:.0f},342 Z" fill="#ffd0e2" '
              f'stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>')
    sheet = (f'<path d="M96,104 L304,104 L304,{curl_y - 10:.0f} L{258 - 30 * face["curl"]:.0f},342 L96,342 Z" '
             f'fill="{NOTE.skin}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
             f'<rect x="96" y="104" width="208" height="34" fill="#f27aa8"/>'
             f'<path d="M96,138 L304,138" stroke="{INK}" stroke-width="2.5" opacity=".35"/>')
    todo = ('<g stroke="#141414" stroke-width="3.4" stroke-linecap="round" fill="none" opacity=".75">'
            '<rect x="120" y="282" width="16" height="16" rx="2"/><path d="M146,290 h62"/>'
            '<rect x="120" y="308" width="16" height="16" rx="2"/><path d="M146,316 h44"/>'
            f'<path d="M122,288 l5,6 l10,-12" stroke="{PINK}" stroke-width="4"/></g>')
    body = group("body", f'<g transform="rotate(-3 200 230)">{sheet}{corner}{todo}</g>')
    brows = ""
    if face["brows"]:
        brows = group("brows", brow(160, 176, face["brows"][0], NOTE, s=1.1) + brow(240, 176, face["brows"][1], NOTE, s=1.1))
    fx = ""
    if face["fx"] == "zzz":
        fx = (f'<text x="316" y="96" font-family="Arial Rounded MT Bold, sans-serif" font-size="40" font-weight="900" '
              f'fill="{BLUE}" stroke="{INK}" stroke-width="2" paint-order="stroke">z<tspan dy="-18" font-size="30">z</tspan></text>')
    elif face["fx"] == "sweat":
        fx = sweat(318, 120, NOTE) + sweat(80, 150, NOTE)
    cheek = Look(line=INK, skin=NOTE.skin, blush=PINK)
    facegrp = group("face", blush(140, 236, cheek, opacity=0.5) + blush(260, 236, cheek, opacity=0.5)
                    + group("eyeL", eye(162, 206, face["eyes"], NOTE, s=1.35))
                    + group("eyeR", eye(238, 206, face["eyes"], NOTE, s=1.35)) + brows
                    + group("mouth", mouth(200, 240, face["mouth"], NOTE, s=1.1)))
    return document(uid, NOTE, "", legs + arms + body + facegrp + group("fx", fx), rim_opacity=0.0)


HOSTS = {
    "o1": ("下班貓＋PM 狗", offwork_duo, tuple(DUO_FACES)),
    "o2": ("便利貼精・黏黏", sticky_note, tuple(NOTE_FACES)),
}
