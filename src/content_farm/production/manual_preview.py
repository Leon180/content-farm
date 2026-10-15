"""``upload/manual/preview.html``: an offline YouTube-like watch page for the pre-upload demo.

One self-contained file: no CDN, no fonts, no network. The video and captions
are referenced by relative path from ``upload/manual/`` so ``file://`` works.
Shorts (9:16) get a vertical player. Every value from the run is HTML-escaped.
"""

from __future__ import annotations

from html import escape

from content_farm.explainer.brands import brand_palette
from content_farm.production.manual_kit import KitInfo, human_duration, human_size

_FALLBACK = {"bg": "#f5f5f5", "fg": "#111111", "muted": "#555555", "accent": "#cc0000", "card": "#ffffff"}

_CSS = """
:root{--bg:%(bg)s;--fg:%(fg)s;--muted:%(muted)s;--accent:%(accent)s;--card:%(card)s}
*{box-sizing:border-box}
body{margin:0;background:#0f0f0f;color:#f1f1f1;font:15px/1.5 -apple-system,"PingFang TC","Noto Sans TC",sans-serif}
.status{display:flex;flex-wrap:wrap;gap:8px 18px;padding:8px 16px;background:#202020;font-size:13px;border-bottom:1px solid #333}
.status b{font-weight:600}.status .bad{color:#ff6b6b}.status .warn{color:#ffd166}.status .ok{color:#6ee7a8}
main{max-width:1280px;margin:0 auto;padding:16px}
.player{background:#000;border-radius:12px;overflow:hidden}
.player video{display:block;width:100%%;height:auto;max-height:80vh}
.vertical .player{max-width:405px;margin:0 auto}
h1{font-size:20px;margin:14px 0 8px}
.channel{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.avatar{width:40px;height:40px;border-radius:50%%;background:var(--accent);color:var(--card);display:grid;place-items:center;font-weight:700}
.channel .name{font-weight:600;color:var(--accent);background:var(--bg);padding:2px 8px;border-radius:6px}
.box{background:#272727;border-radius:12px;padding:12px 14px;margin-bottom:14px}
.box h2{font-size:14px;margin:0 0 8px;color:#aaa}
.desc{white-space:pre-wrap;word-break:break-word;margin:0;font:inherit}
.chapters a{color:#3ea6ff;text-decoration:none;font-variant-numeric:tabular-nums;margin-right:8px}
.chapters li{list-style:none;padding:2px 0}.chapters ul{margin:0;padding:0}
.tags span{display:inline-block;background:#3a3a3a;border-radius:12px;padding:2px 10px;margin:0 6px 6px 0;font-size:13px}
.thumb{width:320px;max-width:100%%;border-radius:8px;display:block}
.grid{display:grid;grid-template-columns:1fr;gap:0 14px}
@media(min-width:900px){.grid{grid-template-columns:2fr 1fr}}
dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:4px 12px}dt{color:#aaa}dd{margin:0}
"""

_JS = """
document.querySelectorAll('[data-t]').forEach(function(a){
  a.addEventListener('click',function(e){e.preventDefault();var v=document.getElementById('v');
    v.currentTime=parseFloat(a.dataset.t);v.play();window.scrollTo({top:0,behavior:'smooth'});});
});
"""


def _seconds(stamp: str) -> int:
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return total


def _palette(brand: str) -> dict[str, str]:
    try:
        return {**_FALLBACK, **brand_palette(brand)}
    except (ValueError, OSError):
        return dict(_FALLBACK)


def _status_bar(info: KitInfo) -> str:
    voice = ('<span class="warn">macOS say（暫用，待換 Fish Audio 後重出）</span>' if info.machine_voice
             else '<span class="ok">Fish Audio</span>')
    if info.qc_errors is None:
        qc = '<span class="warn">未跑</span>'
    else:
        cls = "bad" if info.qc_errors else ("warn" if info.qc_warnings else "ok")
        qc = f'<span class="{cls}">{info.qc_errors} error / {info.qc_warnings} warn</span>'
    meta_src = "" if info.meta_from_package else '<span class="warn">metadata 臨時生成（成片閘門未核可）</span>'
    return (f'<div class="status"><span><b>配音</b> {voice}</span><span><b>QC</b> {qc}</span>'
            f'<span><b>片長</b> {human_duration(info.duration_seconds)}</span>'
            f'<span><b>檔案</b> {human_size(info.size_bytes)}</span>{meta_src}</div>')


def _settings(info: KitInfo) -> str:
    meta = info.meta
    rows = {
        "目標頻道": f"{info.channel_name}（{info.channel_code}）",
        "可見度": meta.get("privacy_status") or "private",
        "排程": meta.get("publish_at") or "—",
        "AI 揭露": "是（合成內容）" if meta.get("contains_synthetic_media") else "否",
        "兒童內容": "否",
        "影片檔": str(info.video_abs),
    }
    return "".join(f"<dt>{escape(k)}</dt><dd>{escape(str(v))}</dd>" for k, v in rows.items())


def build_preview_html(info: KitInfo, brand: str, has_subs: bool) -> str:
    meta = info.meta
    css = _CSS % _palette(brand)
    track = ('<track kind="captions" src="subtitles.vtt" srclang="zh-TW" label="中文（台灣）" default>'
             if has_subs else "")
    chapters = "".join(
        f'<li><a href="#" data-t="{_seconds(c["timestamp"])}">{escape(c["timestamp"])}</a>{escape(c["title"])}</li>'
        for c in meta.get("chapters") or [])
    tags = "".join(f"<span>#{escape(t)}</span>" for t in meta.get("tags") or [])
    initial = escape(info.channel_name[:1])
    return f"""<!doctype html>
<html lang="zh-Hant-TW"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(meta["title"])} — 上傳前預覽</title>
<style>{css}</style></head>
<body class="{'vertical' if info.vertical else 'landscape'}">
{_status_bar(info)}
<main>
<div class="player"><video id="v" controls preload="metadata" poster="thumbnail.png" src="{escape(info.video_rel)}">{track}</video></div>
<h1>{escape(meta["title"])}</h1>
<div class="channel"><div class="avatar">{initial}</div><span class="name">{escape(info.channel_name)}</span></div>
<div class="grid"><div>
<div class="box"><h2>說明</h2><pre class="desc">{escape(meta["description"])}</pre></div>
</div><div>
<div class="box chapters"><h2>章節（點擊跳轉）</h2><ul>{chapters or "<li>（無）</li>"}</ul></div>
<div class="box"><h2>縮圖</h2><img class="thumb" src="thumbnail.png" alt="縮圖"><p>{escape(info.thumbnail_note)}</p></div>
<div class="box tags"><h2>標籤</h2>{tags or "（無）"}</div>
<div class="box"><h2>上傳設定</h2><dl>{_settings(info)}</dl></div>
</div></div>
</main>
<script>{_JS}</script>
</body></html>
"""
