"""``upload/manual/preview.html``: an offline YouTube-like watch page for the pre-upload demo.

One self-contained file: no CDN, no fonts, no network. Every value from the run
goes through Jinja autoescape. Two choices made when the three channel branches
were merged (REPORT-channels-integrate):

- Subtitles are embedded as cue data and added with ``addTextTrack``/``VTTCue``.
  Chrome refuses ``<track src>`` over ``file://``; this way nothing is fetched.
- The video has two ``<source>``s: the relative path (works when the kit and the
  run move together) and an absolute ``file://`` URL (works when only the kit
  directory is copied or written elsewhere with ``--out``).
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from content_farm.explainer.brands import brand_palette
from content_farm.production import voice_source
from content_farm.production.manual_kit import Kit, human_duration, human_size

FALLBACK_ACCENT = "#cc0000"
_STAMP_LINE = re.compile(r"^(\d{1,2}(?::\d{2}){1,2})(?= )", re.MULTILINE)


def stamp_seconds(stamp: str) -> int:
    seconds = 0
    for part in stamp.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def description_html(description: str) -> str:
    """Escaped description; line-leading chapter timestamps become seek links (as on YouTube)."""
    escaped = html.escape(description)
    return _STAMP_LINE.sub(lambda m: f'<a href="#" data-t="{stamp_seconds(m.group(1))}">{m.group(1)}</a>',
                           escaped)


def cues_json(kit: Kit) -> str:
    """Cue list as JSON that cannot close the surrounding ``<script>``."""
    data = [[cue.start, cue.end, cue.text] for cue in kit.subtitles]
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def accent(brand: str) -> str:
    try:
        return brand_palette(brand).get("accent", FALLBACK_ACCENT)
    except (ValueError, OSError):
        return FALLBACK_ACCENT


def build_preview_html(kit: Kit) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                      autoescape=select_autoescape(["html", "j2"]))
    meta = kit.meta
    chapters = [{**ch, "seconds": stamp_seconds(ch["timestamp"])} for ch in meta.get("chapters") or []]
    return env.get_template("preview.html.j2").render(
        kit=kit, meta={**meta, "chapters": chapters},
        voice=voice_source.provider_name(kit.voice_provider),
        length=human_duration(kit.seconds), size=human_size(kit.size_bytes),
        video_uri=kit.video.as_uri(), thumbnail=kit.thumbnail.name if kit.thumbnail else "thumbnail.png",
        description_html=description_html(meta["description"]),
        brand_color=accent(kit.channel.brand), cues=cues_json(kit),
    )
