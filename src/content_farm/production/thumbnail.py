"""Channel thumbnails (roadmap R2): ``thumbnail.json`` → ``thumbnails/thumbnail.png``.

A thumbnail is the channel's character or artwork, one short line of big text
and at most one number — never the title slide. The spec lives in the run-dir
so a person can edit the copy and re-render without touching code:

    {"lines": ["CoWoS", "卡住 AI？"], "highlight": "CoWoS", "sub": "瓶頸不在晶片",
     "visual": {"kind": "mascot", "pose": "shocked"},
     "promise": ["卡住出貨", "八成"]}

``promise`` are narration excerpts that pay off what the thumbnail says; QC
(:func:`thumbnail_findings`) checks they are spoken within the first 60 seconds
and that every number on the thumbnail is in the narration (YouTube spam policy:
no misleading thumbnails). Layout per brand lives in ``templates/thumbnail.html.j2``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from content_farm.explainer.brands import BRAND_ASSET_DIR, brand_css_path
from content_farm.explainer.deck import MascotPose, visible_len
from content_farm.production.channels import Channel
from content_farm.production.qc import Finding

SPEC_FILE = "thumbnail.json"
OUT_DIR = Path("thumbnails")
OUT_FILE = OUT_DIR / "thumbnail.png"
SMALL_FILE = OUT_DIR / "thumbnail_phone.png"   # how it looks in a phone feed (review aid)
SIZE = (1280, 720)
PHONE_SIZE = (320, 180)
MAX_TEXT_CHARS = 10        # big text, all lines together (Leon: ≤ 8–10 字、手機看得清)
MAX_SUB_CHARS = 12
PROMISE_WITHIN_SECONDS = 60.0
TEMPLATES = Path(__file__).parent / "templates"
_NUMBER = re.compile(r"\d[\d,.]*")


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MascotVisual(_Strict):
    kind: Literal["mascot"]
    pose: MascotPose = "point"


class ImageVisual(_Strict):
    kind: Literal["image"]
    path: str = Field(min_length=1)           # relative to the run-dir (artwork, AI image, brand art)
    credit: str = Field(default="", max_length=80)
    focus: str = Field(default="center", pattern=r"^(left|center|right)$")


class BrandVisual(_Strict):
    kind: Literal["brand"]                     # the channel's key visual (icon art), no character


class CompareSide(_Strict):
    value: str = Field(min_length=1, max_length=9)   # the big number, e.g. "7,722" or "九"
    label: str = Field(default="", max_length=8)     # what it counts, e.g. "mm²" or "條尾巴"


# docs/design/thumbnails/rules.md: (a) character + big text, (b) full-bleed key art + question,
# (c) one or two big numbers. All three keep the same promise rule (spoken within 60 s).
Layout = Literal["character", "keyart", "compare"]


class ThumbnailSpec(_Strict):
    lines: tuple[str, ...] = Field(min_length=1, max_length=2)
    highlight: str = ""                        # a word inside lines drawn in the accent colour
    sub: str = Field(default="", max_length=MAX_SUB_CHARS)
    number: str = Field(default="", max_length=6)   # one circled number (cel), e.g. "6成"
    number_note: str = Field(default="", max_length=8)
    visual: MascotVisual | ImageVisual | BrandVisual = Field(discriminator="kind")
    promise: tuple[str, ...] = Field(min_length=1)
    layout: Layout = "character"
    compare: tuple[CompareSide, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def _short_text(self) -> ThumbnailSpec:
        chars = visible_len("".join(self.lines))
        if chars > MAX_TEXT_CHARS:
            raise ValueError(f"thumbnail text is {chars} chars; keep it <= {MAX_TEXT_CHARS} (phone legibility)")
        if self.highlight and self.highlight not in "".join(self.lines):
            raise ValueError(f"highlight {self.highlight!r} is not in the lines")
        if self.layout == "compare" and not self.compare:
            raise ValueError("layout 'compare' needs one or two compare values")
        if self.layout == "keyart" and not isinstance(self.visual, ImageVisual):
            raise ValueError("layout 'keyart' needs an image visual (artwork or key art)")
        return self

    @property
    def text(self) -> str:
        return "".join(self.lines)


def load_spec(run_dir: Path) -> ThumbnailSpec:
    return ThumbnailSpec.model_validate_json((run_dir / SPEC_FILE).read_text(encoding="utf-8"))


def _root_tokens(brand: str) -> str:
    css = brand_css_path(brand).read_text(encoding="utf-8")
    start = css.index(":root")
    return css[start: css.index("}", start) + 1]


def thumbnail_html(spec: ThumbnailSpec, channel: Channel, visual_uri: str, *, vertical: bool = False) -> str:
    env = Environment(loader=FileSystemLoader([str(TEMPLATES), str(BRAND_ASSET_DIR)]),
                      autoescape=select_autoescape(["html", "j2"]))
    brand_style = env.get_template(f"{channel.brand}/assets.html.j2").module.style()
    template = "thumbnail_vertical.html.j2" if vertical else (
        "thumbnail.html.j2" if spec.layout == "character" else "thumbnail_layouts.html.j2")
    return env.get_template(template).render(
        spec=spec, brand=channel.brand, channel_name=channel.name, root=_root_tokens(channel.brand),
        brand_style=brand_style, visual_uri=visual_uri)


def _visual_file(run_dir: Path, spec: ThumbnailSpec, work: Path, channel: Channel) -> Path | None:
    if isinstance(spec.visual, MascotVisual):
        if channel.mascot.host == "pngtuber":
            from content_farm.explainer.pngtuber.still import pose_still

            return pose_still(channel.mascot.ref, spec.visual.pose, work / f"host_{spec.visual.pose}.png")
        from content_farm.explainer.mascot.still import pose_png

        return pose_png(spec.visual.pose, work / f"cat_{spec.visual.pose}.png")
    if isinstance(spec.visual, ImageVisual):
        path = (run_dir / spec.visual.path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"thumbnail visual {spec.visual.path} not found in {run_dir}")
        return path
    return None


def render_thumbnail(run_dir: Path, channel: Channel) -> Path:
    """Write ``thumbnails/thumbnail.png`` (1280x720) and a phone-size preview next to it."""
    from content_farm.explainer.capture import PageCapturer

    spec = load_spec(run_dir)
    work = run_dir / OUT_DIR / ".work"
    work.mkdir(parents=True, exist_ok=True)
    visual = _visual_file(run_dir, spec, work, channel)
    html = work / "thumbnail.html"
    html.write_text(thumbnail_html(spec, channel, visual.resolve().as_uri() if visual else ""), encoding="utf-8")
    out = run_dir / OUT_FILE
    with PageCapturer(size=SIZE) as capturer:
        capturer.still(html, out)
    with Image.open(out) as image:
        image.convert("RGB").resize(PHONE_SIZE, Image.LANCZOS).save(run_dir / SMALL_FILE)
    return out


VARIANTS_FILE = "thumbnail_variants.json"
VERTICAL_SIZE = (1080, 1920)
MAX_BYTES = 2 * 1024 * 1024      # YouTube custom thumbnail limit
JPEG_QUALITIES = (92, 86, 80, 72, 64)


class ThumbnailVariants(_Strict):
    """Up to three specs for YouTube Test & Compare (landscape). ``vertical``: Shorts covers
    (1080x1920); Test & Compare is not available for Shorts, so those are picked by hand."""
    vertical: bool = False
    variants: dict[str, ThumbnailSpec] = Field(min_length=1, max_length=3)


def load_variants(run_dir: Path) -> ThumbnailVariants:
    return ThumbnailVariants.model_validate_json((run_dir / VARIANTS_FILE).read_text(encoding="utf-8"))


def save_under_limit(png: Path, out: Path, limit: int = MAX_BYTES) -> Path:
    """Re-encode the capture as JPEG at the best quality that fits under ``limit`` bytes."""
    with Image.open(png) as image:
        rgb = image.convert("RGB")
    for quality in JPEG_QUALITIES:
        rgb.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        if out.stat().st_size <= limit:
            return out
    raise ValueError(f"{out.name} is {out.stat().st_size} bytes even at quality {JPEG_QUALITIES[-1]}")


def render_variants(run_dir: Path, channel: Channel) -> dict[str, Path]:
    """Write ``thumbnails/variant_<key>.jpg`` (< 2 MB) plus a phone-size preview for each variant."""
    from content_farm.explainer.capture import PageCapturer

    spec_set = load_variants(run_dir)
    size = VERTICAL_SIZE if spec_set.vertical else SIZE
    phone = (PHONE_SIZE[1], PHONE_SIZE[1] * 16 // 9) if spec_set.vertical else PHONE_SIZE
    work = run_dir / OUT_DIR / ".work"
    work.mkdir(parents=True, exist_ok=True)
    pages = {}
    for key, spec in spec_set.variants.items():   # visuals first: the cat pose opens its own browser
        visual = _visual_file(run_dir, spec, work, channel)
        pages[key] = work / f"variant_{key}.html"
        pages[key].write_text(thumbnail_html(spec, channel, visual.resolve().as_uri() if visual else "",
                                             vertical=spec_set.vertical), encoding="utf-8")
    outputs = {}
    with PageCapturer(size=size) as capturer:
        for key, html in pages.items():
            png = work / f"variant_{key}.png"
            capturer.still(html, png)
            outputs[key] = save_under_limit(png, run_dir / OUT_DIR / f"variant_{key}.jpg")
            with Image.open(png) as image:
                image.convert("RGB").resize(phone, Image.LANCZOS).save(run_dir / OUT_DIR / f"variant_{key}_phone.png")
    return outputs


def variant_findings(run_dir: Path, channel: Channel) -> list[Finding]:
    """Every variant must keep its promise, not only the one that wins the test."""
    if not (run_dir / VARIANTS_FILE).is_file():
        return []
    try:
        spec_set = load_variants(run_dir)
    except ValueError as exc:
        return [Finding("thumbnail_variants", "error", f"{VARIANTS_FILE} invalid: {exc}")]
    findings = [f for key, spec in spec_set.variants.items() for f in promise_findings(run_dir, spec, f"variant {key}")]
    big = [p.name for p in (run_dir / OUT_DIR).glob("variant_*.jpg") if p.stat().st_size > MAX_BYTES]
    if big:
        findings.append(Finding("thumbnail_variants", "error", f"over 2 MB: {', '.join(sorted(big))}"))
    return findings or [Finding("thumbnail_variants", "ok", f"{len(spec_set.variants)} variants keep their promise")]


def _compact(text: str) -> str:
    return re.sub(r"[\s，。、：；！？「」『』（）,.:;!?()]", "", text)


def _narration_starts(run_dir: Path) -> list[tuple[float, str]]:
    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    clock, out = 0.0, []
    for scene in script.get("scenes", []):
        out.append((clock, _compact(scene.get("narration", ""))))
        clock += float(scene.get("duration_seconds") or 0)
    return out


def thumbnail_findings(run_dir: Path, channel: Channel) -> list[Finding]:
    """The spec is valid, the image exists, the cat is on a mascot channel's thumbnail, and every
    word and number on it is paid off by the narration (promise within the first 60 s)."""
    if not (run_dir / SPEC_FILE).is_file():
        return [Finding("thumbnail", "error", f"{SPEC_FILE} missing: no channel thumbnail (not the title slide)")]
    try:
        spec = load_spec(run_dir)
    except ValueError as exc:
        return [Finding("thumbnail", "error", f"{SPEC_FILE} invalid: {exc}")]
    findings = []
    if not (run_dir / OUT_FILE).is_file():
        findings.append(Finding("thumbnail", "error", f"{OUT_FILE} not rendered (run make_thumbnail.py)"))
    if channel.mascot.rig_ready and not isinstance(spec.visual, MascotVisual):
        findings.append(Finding("thumbnail", "error", f"{channel.mascot.name} must be on the thumbnail"))
    findings += promise_findings(run_dir, spec)
    return findings or [Finding("thumbnail", "ok", f"「{spec.text}」+ {spec.visual.kind}; promise paid off "
                                                   f"within {PROMISE_WITHIN_SECONDS:.0f}s")]


def promise_findings(run_dir: Path, spec: ThumbnailSpec, label: str = "") -> list[Finding]:
    """Errors when a promise is not spoken within PROMISE_WITHIN_SECONDS, or a number on the
    thumbnail (big text, circled number, compare values) is not in the narration at all."""
    prefix = f"{label}: " if label else ""
    if not (run_dir / "script.json").is_file():
        return [Finding("thumbnail_promise", "error", f"{prefix}script.json missing; cannot check promise")]
    scenes = _narration_starts(run_dir)
    early = "".join(text for start, text in scenes if start < PROMISE_WITHIN_SECONDS)
    everything = "".join(text for _, text in scenes)
    shown = spec.text + spec.number + "".join(side.value for side in spec.compare)
    late = [p for p in spec.promise if _compact(p) not in early]
    # the narration is compacted (punctuation, including '.' and ',', removed), so compact the number too:
    # "8.8" must match the spoken "8.8 公分", "7,722" the spoken "7722"
    numbers = [n for n in _NUMBER.findall(shown) if _compact(n.rstrip(".,")) not in everything]
    findings = []
    if late:
        findings.append(Finding("thumbnail_promise", "error",
                                f"{prefix}not spoken in the first {PROMISE_WITHIN_SECONDS:.0f}s: {', '.join(late)}"))
    if numbers:
        findings.append(Finding("thumbnail_promise", "error",
                                f"{prefix}numbers not in the narration: {', '.join(numbers)}"))
    return findings
