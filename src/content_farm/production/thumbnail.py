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


class ThumbnailSpec(_Strict):
    lines: tuple[str, ...] = Field(min_length=1, max_length=2)
    highlight: str = ""                        # a word inside lines drawn in the accent colour
    sub: str = Field(default="", max_length=MAX_SUB_CHARS)
    number: str = Field(default="", max_length=6)   # one circled number (cel), e.g. "6成"
    number_note: str = Field(default="", max_length=8)
    visual: MascotVisual | ImageVisual | BrandVisual = Field(discriminator="kind")
    promise: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _short_text(self) -> ThumbnailSpec:
        chars = visible_len("".join(self.lines))
        if chars > MAX_TEXT_CHARS:
            raise ValueError(f"thumbnail text is {chars} chars; keep it <= {MAX_TEXT_CHARS} (phone legibility)")
        if self.highlight and self.highlight not in "".join(self.lines):
            raise ValueError(f"highlight {self.highlight!r} is not in the lines")
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


def thumbnail_html(spec: ThumbnailSpec, channel: Channel, visual_uri: str) -> str:
    env = Environment(loader=FileSystemLoader([str(TEMPLATES), str(BRAND_ASSET_DIR)]),
                      autoescape=select_autoescape(["html", "j2"]))
    brand_style = env.get_template(f"{channel.brand}/assets.html.j2").module.style()
    return env.get_template("thumbnail.html.j2").render(
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
    if not (run_dir / "script.json").is_file():
        return findings + [Finding("thumbnail_promise", "error", "script.json missing; cannot check promise")]
    scenes = _narration_starts(run_dir)
    early = "".join(text for start, text in scenes if start < PROMISE_WITHIN_SECONDS)
    everything = "".join(text for _, text in scenes)
    late = [p for p in spec.promise if _compact(p) not in early]
    numbers = [n for n in _NUMBER.findall(spec.text + spec.number) if n not in everything]
    if late:
        findings.append(Finding("thumbnail_promise", "error",
                                f"not spoken in the first {PROMISE_WITHIN_SECONDS:.0f}s: {', '.join(late)}"))
    if numbers:
        findings.append(Finding("thumbnail_promise", "error", f"numbers not in the narration: {', '.join(numbers)}"))
    return findings or [Finding("thumbnail", "ok", f"「{spec.text}」+ {spec.visual.kind}; promise paid off "
                                                   f"within {PROMISE_WITHIN_SECONDS:.0f}s")]
