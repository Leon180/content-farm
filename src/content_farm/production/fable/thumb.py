"""Fable thumbnails: a picture composed for the thumbnail, a short hook (not the title), QC at phone size.

``fable.json`` ``thumb`` carries up to three options (hook ≤ 8 characters, a close-up picture prompt, where the
hook sits). Each option is drawn into ``assets/ai_images/thumb_<n>.png`` in the channel's picture-book style,
rendered to ``thumbnails/variant_<a|b|c>.jpg`` (< 2 MB, what YouTube Test & Compare takes) with a 168×94 preview,
and option 1 is also ``thumbnails/thumbnail.png``. Without options the legacy layout (title over the first
story picture) is kept so old runs still render. The channel tag is the channel's name setting, never a literal.

Shorts cannot use Test & Compare and take their cover from a frame of the video: :func:`cover_frame` picks the
most complete story picture before the reveal and writes its time to ``thumbnails/cover_frame.json``.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageFilter

from content_farm.explainer.ai_images import AI_IMAGE_DIR, find_image
from content_farm.explainer.deck import visible_len
from content_farm.explainer.illustrate import AI_LABEL, IllustrationRequest, LocalMflux, sidecar_for
from content_farm.production.channels import Channel
from content_farm.production.fable import images
from content_farm.production.fable.model import Fable, ThumbOption
from content_farm.production.news.visuals import env_with_file
from content_farm.production.qc import Finding
from content_farm.production.thumbnail import save_under_limit

TEMPLATES = Path(__file__).parent / "templates"
SIZE = {"mid": (1280, 720), "short": (1080, 1920)}
DRAW = images.DRAW
OUT_DIR = Path("thumbnails")
KEYS = ("a", "b", "c")
TINY_WIDTH = 168                      # the related-videos sidebar thumbnail on a phone is about 168×94
MIN_TINY_TEXT_PX = 14                 # hook letters must be at least this tall at TINY_WIDTH
MIN_CONTRAST = 3.0                    # WCAG large-text ratio of the hook colour against the picture under it
HOOK_COLOR = (255, 241, 196)
COMPOSITION = ("Close-up thumbnail composition: one clear main subject filling about two thirds of the frame, "
               "simple soft background with few details, strong contrast between subject and background, "
               "open space left for big text, expressive and cute, correct anatomy.")
# where the hook sits, as fractions of the frame (x0, y0, x1, y1): the picture under it is measured for contrast
HOOK_BOX = {"bottom": (0.04, 0.66, 0.96, 0.97), "left": (0.03, 0.22, 0.50, 0.78), "right": (0.50, 0.22, 0.97, 0.78)}
SHADE = {"bottom": "linear-gradient(180deg, rgba(30,18,8,0) 45%, rgba(30,18,8,.72) 100%)",
         "left": "linear-gradient(90deg, rgba(30,18,8,.72) 0%, rgba(30,18,8,0) 62%)",
         "right": "linear-gradient(270deg, rgba(30,18,8,.72) 0%, rgba(30,18,8,0) 62%)"}


def image_id(number: int) -> str:
    return f"thumb_{number}"


def thumb_requests(fable: Fable, channel: Channel) -> list[IllustrationRequest]:
    """One request per option, drawn at the thumbnail frame's shape with seeds apart from the story pictures."""
    cfg = channel.ai_illustration
    width, height = DRAW[fable.format]
    return [IllustrationRequest(image_id(n), f"{cfg.style_prefix.strip()} {o.image_prompt.strip()} {COMPOSITION}",
                                cfg.seed + 1000 + n, width, height) for n, o in enumerate(fable.thumb, 1)]


def draw_thumb_images(run_dir: Path, fable: Fable, channel: Channel, env_file: Path | None = None, provider=None) -> int:
    """Draw the thumbnail pictures still missing (one process at a time, like the story pictures)."""
    folder = run_dir / AI_IMAGE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    todo = [r for r in thumb_requests(fable, channel) if find_image(folder, r.slide_id) is None]
    if todo and provider is None:
        provider = LocalMflux.from_env(channel.ai_illustration.model, env_with_file(env_file))
    for request in todo:
        out = folder / f"{request.slide_id}.png"
        record = {"slide_id": request.slide_id, **provider.generate(request, out), "prompt": request.prompt,
                  "seed": request.seed, "size": [request.width, request.height], "ai_label": AI_LABEL}
        sidecar_for(out).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(todo)


def split_hook(hook: str, lines: int) -> list[str]:
    """One line, or two split after punctuation when there is one (else in the middle)."""
    if lines == 1 or visible_len(hook) <= 4:
        return [hook]
    cut = next((m.end() for m in re.finditer(r"[，、：,]", hook) if 2 <= m.end() < len(hook) - 1), math.ceil(len(hook) / 2))
    return [hook[:cut], hook[cut:]]


def hook_layout(option: ThumbOption, fmt: str) -> dict:
    """Lines, font size, stroke and placement of the hook for the frame."""
    width, _ = SIZE[fmt]
    pad = 50 if fmt == "mid" else 60
    side = option.layout in ("left", "right") and fmt == "mid"
    where = option.layout if side else "bottom"
    lines = split_hook(option.hook, 2 if side else 1)
    longest = max(visible_len(line) for line in lines)
    px = int(min(220, (0.44 * width if side else (width - 2 * pad) * 0.92) / longest))
    css = {"bottom": f"left:{pad}px; right:{pad}px; bottom:{pad}px;",
           "left": f"left:{pad}px; top:50%; transform:translateY(-50%); width:46%;",
           "right": f"right:{pad}px; top:50%; transform:translateY(-50%); width:46%;"}[where]
    return {"hook_lines": lines, "hook_px": px, "stroke": max(6, round(px * 0.09)), "hook_css": css,
            "align": "center" if where == "bottom" else ("left" if where == "left" else "right"),
            "shade": SHADE[where], "where": where}


def thumb_page(fable: Fable, channel: Channel, option: ThumbOption, image_uri: str, *, notext: bool = False) -> str:
    width, height = SIZE[fable.format]
    layout = hook_layout(option, fable.format)
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    return env.get_template("fable_thumb.html.j2").render(
        w=width, h=height, image=image_uri, tag=channel.name, pad=50 if fable.format == "mid" else 60,
        tag_px=30 if fable.format == "mid" else 38, notext=notext, **layout)


def render_options(run_dir: Path, fable: Fable, channel: Channel) -> dict[str, Path]:
    """Render each option (picture + hook) and a text-free copy for the contrast check; returns key → JPEG."""
    from content_farm.explainer.capture import PageCapturer

    work = run_dir / "fable_work"
    work.mkdir(parents=True, exist_ok=True)
    out = run_dir / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    with PageCapturer(size=SIZE[fable.format]) as capturer:
        for key, (number, option) in zip(KEYS, enumerate(fable.thumb, 1), strict=False):
            source = find_image(run_dir / AI_IMAGE_DIR, image_id(number))
            if source is None:
                raise FileNotFoundError(f"thumbnail picture {image_id(number)} was not drawn (fable.py images)")
            for notext, name in ((False, f"thumb_{key}.html"), (True, f"thumb_{key}_bg.html")):
                page = work / name
                page.write_text(thumb_page(fable, channel, option, source.resolve().as_uri(), notext=notext), encoding="utf-8")
                capturer.still(page, work / page.with_suffix(".png").name)
            png = work / f"thumb_{key}.png"
            outputs[key] = save_under_limit(png, out / f"variant_{key}.jpg")
            with Image.open(png) as image:
                small = image.convert("RGB")
                small.resize((TINY_WIDTH, round(TINY_WIDTH * small.height / small.width)), Image.LANCZOS).save(out / f"variant_{key}_tiny.png")
                if key == "a":
                    small.save(out / "thumbnail.png")
    return outputs


def _luminance(rgb: tuple[float, float, float]) -> float:
    def lin(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_under_hook(bg_png: Path, where: str) -> float:
    """WCAG contrast ratio of the hook colour against the (mean) picture under the hook's box."""
    with Image.open(bg_png) as image:
        rgb = image.convert("RGB")
        x0, y0, x1, y1 = HOOK_BOX[where]
        box = rgb.crop((int(x0 * rgb.width), int(y0 * rgb.height), int(x1 * rgb.width), int(y1 * rgb.height)))
        mean = box.resize((1, 1), Image.BOX).getpixel((0, 0))
    light, dark = sorted((_luminance(HOOK_COLOR), _luminance(mean)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def tiny_text_px(option: ThumbOption, fmt: str) -> float:
    """Height of a hook letter at the 168 px preview."""
    return hook_layout(option, fmt)["hook_px"] * TINY_WIDTH / SIZE[fmt][0]


def thumb_findings(run_dir: Path, fable: Fable, channel: Channel) -> list[Finding]:
    """Phone-size legibility (letter height, contrast), the retired-name check and the 2 MB limit."""
    if not fable.thumb:
        return [Finding("fable_thumb", "warn", "fable.json has no thumb options: legacy title-over-picture thumbnail")]
    findings = []
    retired = set(channel.former_names)
    for key, option in zip(KEYS, fable.thumb, strict=False):
        label = f"option {key}「{option.hook}」"
        px = tiny_text_px(option, fable.format)
        if px < MIN_TINY_TEXT_PX:
            findings.append(Finding("fable_thumb_legibility", "error",
                                    f"{label}: letters {px:.1f} px tall at {TINY_WIDTH} px wide, need ≥ {MIN_TINY_TEXT_PX}"))
        hit = [name for name in retired if name in option.hook]
        if hit:
            findings.append(Finding("fable_thumb_name", "error", f"{label}: retired channel name {hit} on the thumbnail"))
        bg = run_dir / "fable_work" / f"thumb_{key}_bg.png"
        if bg.is_file():
            ratio = contrast_under_hook(bg, hook_layout(option, fable.format)["where"])
            if ratio < MIN_CONTRAST:
                findings.append(Finding("fable_thumb_contrast", "error", f"{label}: contrast {ratio:.1f}:1 under the text, need ≥ {MIN_CONTRAST}"))
        jpg = run_dir / OUT_DIR / f"variant_{key}.jpg"
        if not jpg.is_file():
            findings.append(Finding("fable_thumb", "error", f"{jpg.name} not rendered"))
    if channel.name in retired:
        findings.append(Finding("fable_thumb_name", "error", f"channel name {channel.name!r} is listed as retired"))
    return findings or [Finding("fable_thumb", "ok", f"{len(fable.thumb)} options readable at {TINY_WIDTH} px, tag「{channel.name}」")]


def _score(path: Path) -> float:
    """How complete a picture looks: colourfulness times detail (edge energy), both from a small copy."""
    with Image.open(path) as image:
        small = image.convert("RGB").resize((320, 180))
    detail = sum(small.convert("L").filter(ImageFilter.FIND_EDGES).getdata()) / (320 * 180)
    saturation = sum(small.convert("HSV").getdata(1)) / (320 * 180)
    return round(detail * saturation, 2)


def cover_frame(run_dir: Path, fable: Fable, durations: list[float]) -> dict:
    """The best story picture before the reveal: ``{"beat", "shot", "seconds", "timestamp", "score", "image"}``."""
    reveal = fable.reveal_index()
    manifest = images.load_manifest(run_dir)
    best: dict | None = None
    clock = 0.0
    for index, beat in enumerate(fable.beats):
        if reveal is not None and index >= reveal:
            break
        if beat.act == "story":
            parts = max(1, len(beat.shots))
            for number in range(1, parts + 1):
                drawn = manifest["shots"][f"{beat.id}.{number}"]["image_id"]
                path = find_image(run_dir / AI_IMAGE_DIR, drawn)
                score = _score(path) if path else -1.0
                if best is None or score > best["score"]:
                    at = round(clock + durations[index] / parts * (number - 1) + 0.5, 1)
                    best = {"beat": beat.id, "shot": f"{beat.id}.{number}", "seconds": at,
                            "timestamp": f"{int(at // 60)}:{int(at % 60):02d}", "score": score, "image": path.name if path else ""}
        clock += durations[index]
    if best is None:
        raise ValueError("no story picture to suggest as the cover frame")
    return best


def write_cover_frame(run_dir: Path, fable: Fable, durations: list[float]) -> Path:
    frame = cover_frame(run_dir, fable, durations)
    frame["note"] = ("Shorts cannot join Test & Compare; pick this frame as the cover in the upload screen "
                     "(or use it as the custom Shorts thumbnail). Story picture before the reveal, no spoiler.")
    path = run_dir / OUT_DIR / "cover_frame.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(frame, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def metadata_line(frame: dict) -> str:
    """The line for the Short's metadata.md."""
    return f"| 建議封面格 | 影片 {frame['timestamp']}（{frame['shot']}；上傳畫面選此格，插圖最完整且未劇透） |"
