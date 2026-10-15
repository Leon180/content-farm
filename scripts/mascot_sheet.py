"""Character overview: every pose on the three theme backgrounds, labelled.

Usage:
    python scripts/mascot_sheet.py docs/examples/mascot/character_sheet.png
"""
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from content_farm.explainer.mascot.motion import Frame
from content_farm.explainer.mascot.params import PARAM_DEFAULTS, POSES, pose_vector
from content_farm.explainer.mascot.render import capture_pngs

OUT = Path(sys.argv[1])
BGS = [("tech", "#15171c", "#f2f2f0"), ("ai", "#0b1020", "#e8ecf5"), ("knowledge", "#f6f1e7", "#23201c")]
SAY = {"point": "看這張圖", "deadpan": "這個數字其實是…", "smug": "早就說了"}


def frame(pose: str) -> Frame:
    v = pose_vector(pose)
    p = {**PARAM_DEFAULTS,
         "ParamAngleX": v["AngleX"], "ParamAngleY": v["AngleY"], "ParamAngleZ": v["AngleZ"],
         "ParamBodyAngleX": v["BodyAngleX"], "ParamBodyY": v["BodyY"],
         "ParamEyeLOpen": v["EyeOpen"], "ParamEyeROpen": v["EyeOpen"],
         "ParamEyeLSmile": v["EyeSmile"], "ParamEyeRSmile": v["EyeSmile"],
         "ParamEyeBallX": v["EyeBallX"], "ParamEyeBallY": v["EyeBallY"], "ParamPupil": v["Pupil"],
         "ParamMouthForm": v["MouthForm"], "ParamMouthO": v["MouthO"],
         "ParamEarL": v["EarBase"], "ParamEarR": v["EarBase"], "ParamTailPuff": v["TailPuff"],
         "ParamArmR": v["ArmR"], "ParamArmRWave": v["WaveAmp"] * 0.6, "ParamBreath": 0.5,
         "ParamTail": 0.3, "ParamTail2": -0.2,
         "ParamBubble": 1.0 if pose in SAY else 0.0}
    return Frame(params=p, say=SAY.get(pose))


extra = [("talking", Frame(params={**PARAM_DEFAULTS, "ParamMouthOpenY": 0.8, "ParamAngleY": 2}, say=None)),
         ("blink", Frame(params={**PARAM_DEFAULTS, "ParamEyeLOpen": 0, "ParamEyeROpen": 0}, say=None))]
items = [(p, frame(p)) for p in POSES] + extra
pngs = [Image.open(io.BytesIO(b)).convert("RGBA") for b in capture_pngs([f for _, f in items])]
crop = (40, 120, 620, 540)
w, h = crop[2] - crop[0], crop[3] - crop[1]
label_h = 46
sheet = Image.new("RGB", (w * len(items), (h + label_h) * len(BGS)), "#ffffff")
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 26)
draw = ImageDraw.Draw(sheet)
for r, (theme, bg, fg) in enumerate(BGS):
    y = r * (h + label_h)
    for c, ((name, _), im) in enumerate(zip(items, pngs)):
        tile = Image.new("RGBA", (w, h + label_h), bg)
        tile.alpha_composite(im.crop(crop), (0, label_h))
        sheet.paste(tile.convert("RGB"), (c * w, y))
        draw.text((c * w + 14, y + 10), f"{name} · {theme}", fill=fg, font=font)
sheet.save(OUT, optimize=True)
print(OUT, sheet.size)
