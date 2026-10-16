"""Before/after images for REPORT-launch-fixes.md: python before_after.py <out-dir>

Before = the reviewed renders (cf-real-voice / cf-ai-motion run-dirs, review frames);
after  = this branch's output/. Frames are taken at the middle of the named slide.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WT = Path(__file__).resolve().parents[2]
ROOT = WT.parent
BEFORE = {"cowos": ROOT / "cf-real-voice/output/cowos-chipcat", "cel": ROOT / "cf-real-voice/output/cel-ep1",
          "yokai": ROOT / "cf-ai-motion/output/yokai-kyubi"}
AFTER = {"cowos": WT / "output/cowos-chipcat", "cel": WT / "output/cel-ep1", "yokai": WT / "output/yokai-kyubi-launch"}
REVIEW = Path("/Users/lileon/.claude/jobs/1fbe9ba7/tmp/review-frames")
FONT = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 30)


def slide_mid(run: Path, slide_id: str) -> float:
    deck = json.loads((run / "deck.json").read_text(encoding="utf-8"))
    ids = [s["id"] for sec in deck["sections"] for s in sec["slides"]]
    durations = [s["duration_seconds"] for s in json.loads((run / "script.json").read_text())["scenes"]]
    index = ids.index(slide_id)
    return sum(durations[:index]) + durations[index] * 0.6


def video(run: Path) -> Path:
    for name in ("final.mp4", "draft.mp4"):
        if (run / "assembly" / name).is_file():
            return run / "assembly" / name
    raise FileNotFoundError(run)


def frame(path: Path, at: float) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "f.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(path), "-frames:v", "1",
                        str(out)], check=True)
        return Image.open(out).convert("RGB")


def pair(left: Image.Image, right: Image.Image, title: str, width: int = 960) -> Image.Image:
    def fit(im: Image.Image) -> Image.Image:
        return im.resize((width, round(im.height * width / im.width)))
    a, b = fit(left), fit(right)
    h = max(a.height, b.height)
    canvas = Image.new("RGB", (width * 2 + 30, h + 60), "white")
    canvas.paste(a, (0, 60))
    canvas.paste(b, (width + 30, 60))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 12), f"修正前｜{title}", fill="black", font=FONT)
    draw.text((width + 40, 12), "修正後", fill="black", font=FONT)
    return canvas


def slide_pair(channel: str, before_id: str, after_id: str, title: str) -> Image.Image:
    b = frame(video(BEFORE[channel]), slide_mid(BEFORE[channel], before_id))
    a = frame(video(AFTER[channel]), slide_mid(AFTER[channel], after_id))
    return pair(b, a, title)


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    shots = {
        "cowos_s09_interposer": slide_pair("cowos", "s09", "s09", "CoWoS s09 超級載板 → 中介層"),
        "cowos_s02_card": slide_pair("cowos", "s02", "s02", "CoWoS s02 新聞卡：媒體原標題／本頻道摘要"),
        "cowos_k1_take": slide_pair("cowos", "s23", "k1", "CoWoS 新增 k1（自算＋晶片貓判斷）"),
        "cel_s10_note": slide_pair("cel", "s10", "s10", "cel s10 約 12% 口徑註記"),
        "cel_c1_mappa": slide_pair("cel", "s19", "c1", "cel 新增 c1 MAPPA 自己出資"),
        "yokai_s06_note": slide_pair("yokai", "s06", "s06", "九尾狐 s06 AI 圖註記"),
    }
    for code, before_thumb, run in (("cowos", "thumb_cowos-chipcat.jpg", AFTER["cowos"]),
                                    ("cel", "thumb_cel-ep1.jpg", AFTER["cel"]),
                                    ("yokai", "thumb_yokai-kyubi.jpg", AFTER["yokai"])):
        shots[f"thumb_{code}"] = pair(Image.open(REVIEW / before_thumb).convert("RGB"),
                                      Image.open(run / "thumbnails/thumbnail.png").convert("RGB"), f"{code} 縮圖")
    short_after = WT / "output/chipcat-7722-launch/assembly/final.mp4"
    tiles = [frame(short_after, t).resize((270, 480)) for t in (1.0, 5.0, 10.0, 14.0, 19.5, 23.0)]
    strip = Image.new("RGB", (270 * len(tiles), 480), "white")
    for i, tile in enumerate(tiles):
        strip.paste(tile, (270 * i, 0))
    shots["short_7722"] = pair(Image.open(REVIEW / "grid_short.jpg").convert("RGB"), strip,
                               "7,722 Short（前：審查截圖 4 格；後：1/5/10/14/19.5/23 秒）", width=1200)
    for name, image in shots.items():
        image.save(out / f"{name}.jpg", quality=85)
        print(out / f"{name}.jpg")


if __name__ == "__main__":
    main()
