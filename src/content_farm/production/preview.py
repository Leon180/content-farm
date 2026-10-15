"""Offline ``preview.html``: a YouTube-watch-page look-alike to demo a video before upload.

One self-contained file, no network: the video is a relative path, and the
subtitles are embedded as cues and added with ``addTextTrack`` because Chrome
refuses ``<track src>`` over ``file://``.
"""

from __future__ import annotations

import html
import json
import re

from content_farm.explainer.brands import brand_palette
from content_farm.production.channels import Channel

_SRT_TIME = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")
_CUE_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})")
_CHAPTER = re.compile(r"^(\d+(?::\d{2}){1,2}) (.+)$")


def srt_to_vtt(srt: str) -> str:
    return "WEBVTT\n\n" + _SRT_TIME.sub(r"\1.\2", srt.replace("\r\n", "\n")).strip() + "\n"


def _seconds(stamp: str) -> float:
    h, m, s, ms = (int(x) for x in _CUE_TIME.match(stamp).groups())  # type: ignore[union-attr]
    return h * 3600 + m * 60 + s + ms / 1000


def vtt_cues(vtt: str) -> list[tuple[float, float, str]]:
    cues = []
    for block in vtt.split("\n\n"):
        lines = [line for line in block.strip().splitlines() if line]
        timing = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing is None:
            continue
        start, end = (part.strip().split(" ")[0] for part in lines[timing].split("-->"))
        cues.append((_seconds(start), _seconds(end), "\n".join(lines[timing + 1:])))
    return cues


def _stamp_seconds(stamp: str) -> int:
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return total


def description_html(description: str) -> str:
    """Escaped description; ``M:SS 標題`` lines become seek links like on YouTube."""
    out = []
    for line in description.splitlines():
        match = _CHAPTER.match(line)
        if match:
            out.append(f'<a href="#" data-seek="{_stamp_seconds(match.group(1))}">'
                       f"{html.escape(match.group(1))}</a> {html.escape(match.group(2))}")
        else:
            out.append(html.escape(line))
    return "<br>\n".join(out)


def _safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


_CSS = """
:root { --bg:#0f0f0f; --fg:#f1f1f1; --muted:#aaa; --card:#272727; }
* { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--fg);
  font:15px/1.5 -apple-system,"PingFang TC","Noto Sans TC",sans-serif; }
.status { display:flex; flex-wrap:wrap; gap:8px 18px; padding:8px 16px; background:#1d1d1d;
  border-bottom:3px solid var(--accent); font-size:13px; }
.status b { color:var(--accent); } .warn { color:#ffb74d; } .err { color:#ff5252; }
main { max-width:1100px; margin:0 auto; padding:16px; }
.player video { width:100%; background:#000; border-radius:12px; display:block; }
.player.portrait { max-width:405px; margin:0 auto; }
.player.portrait video { aspect-ratio:9/16; object-fit:contain; }
h1 { font-size:20px; margin:14px 0 8px; }
.channel { display:flex; align-items:center; gap:10px; margin-bottom:12px; }
.avatar { width:40px; height:40px; border-radius:50%; background:var(--accent); }
.channel-name { font-weight:700; color:var(--accent); }
.desc { background:var(--card); border-radius:12px; padding:12px 14px; white-space:normal;
  overflow-wrap:anywhere; }
.desc a { color:#3ea6ff; text-decoration:none; }
.meta-row { display:flex; gap:16px; flex-wrap:wrap; margin:12px 0; align-items:flex-start; }
.thumb img { width:240px; max-width:100%; border-radius:8px; }
.settings { font-size:13px; color:var(--muted); } .tags { color:#3ea6ff; font-size:13px; }
"""

_JS = """
const video = document.getElementById('video');
const track = video.addTextTrack('subtitles', '中文（台灣）', 'zh-TW');
for (const [s, e, t] of CUES) track.addCue(new VTTCue(s, e, t));
track.mode = 'showing';
document.querySelectorAll('[data-seek]').forEach(a => a.addEventListener('click', ev => {
  ev.preventDefault(); video.currentTime = Number(a.dataset.seek); video.play();
  window.scrollTo({top: 0, behavior: 'smooth'});
}));
"""


def _status_bar(qc: dict | None, machine_voice: bool, length_text: str, size_text: str) -> str:
    voice = ("<span class='warn'>配音：macos_say 暫用機器聲</span>" if machine_voice
             else "<span>配音：Fish Audio</span>")
    if qc is None:
        qc_text = "<span class='err'>QC：尚未執行</span>"
    else:
        level = "err" if qc.get("errors") else "warn" if qc.get("warnings") else ""
        qc_text = f"<span class='{level}'>QC：{qc.get('errors', 0)} error／{qc.get('warnings', 0)} warn</span>"
    return (f"<div class='status'><b>上傳前預覽</b>{voice}{qc_text}"
            f"<span>片長 {html.escape(length_text)}</span><span>檔案 {html.escape(size_text)}</span></div>")


def preview_html(channel: Channel, meta: dict, *, video_src: str, thumbnail: str, vtt: str,
                 qc: dict | None, machine_voice: bool, length_text: str, size_text: str) -> str:
    accent = brand_palette(channel.brand).get("accent", "#ff0033")
    portrait = channel.format.aspect == "9:16"
    when = meta.get("publish_at") or "未排程"
    settings = (f"可見度：{html.escape(str(meta.get('privacy_status')))}・排程：{html.escape(str(when))}・"
                f"AI 揭露：{'是' if meta.get('contains_synthetic_media') else '否'}・"
                f"兒童內容：{'是' if meta.get('made_for_kids') else '否'}")
    tags = " ".join(f"#{html.escape(t)}" for t in meta.get("tags", []))
    return f"""<!doctype html>
<html lang="zh-Hant-TW"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>預覽｜{html.escape(meta['title'])}</title>
<style>:root{{--accent:{accent};}}{_CSS}</style></head>
<body>
{_status_bar(qc, machine_voice, length_text, size_text)}
<main>
  <div class="player{' portrait' if portrait else ''}">
    <video id="video" controls preload="metadata" poster="{html.escape(thumbnail)}" src="{html.escape(video_src)}"></video>
  </div>
  <h1>{html.escape(meta['title'])}</h1>
  <div class="channel"><div class="avatar"></div><span class="channel-name">{html.escape(channel.name)}</span></div>
  <div class="meta-row">
    <div class="thumb"><img src="{html.escape(thumbnail)}" alt="縮圖"></div>
    <div><div class="settings">{settings}</div><div class="tags">{tags}</div></div>
  </div>
  <div class="desc">{description_html(meta['description'])}</div>
</main>
<script>const CUES = {_safe_json(vtt_cues(vtt))};{_JS}</script>
</body></html>
"""
