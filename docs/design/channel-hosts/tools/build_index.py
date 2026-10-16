"""Offline review page: docs/design/channel-hosts/index.html (relative paths only, no network).

    python docs/design/channel-hosts/tools/build_index.py
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from concepts import CHANNELS, CONCEPTS, REFERENCE  # noqa: E402

OUT = HERE.parent
BG = {"yokai": "#14110d", "offwork": "#ffd84d", "cel": "#f5f1e8"}

CSS = """
:root { --bg:#16171b; --fg:#e8e6e1; --muted:#9a9890; --card:#202228; --line:#33363e; --accent:#e0a54a; }
@media (prefers-color-scheme: light) { :root { --bg:#f4f2ee; --fg:#1d1e22; --muted:#5d5c58; --card:#ffffff; --line:#dcd8d0; --accent:#a8641a; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.65 "PingFang TC","Noto Sans CJK TC",sans-serif; }
main { max-width:1360px; margin:0 auto; padding:32px 16px 80px; }
h1 { font-size:30px; margin:0 0 6px; } h2 { font-size:24px; margin:56px 0 4px; border-top:1px solid var(--line); padding-top:28px; }
.sub { color:var(--muted); margin:0 0 18px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(400px,1fr)); gap:20px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden; display:flex; flex-direction:column; }
.card header { padding:16px 18px 4px; } .card h3 { margin:0; font-size:21px; }
.badge { display:inline-block; font-size:12px; padding:2px 10px; border-radius:99px; border:1px solid var(--line); color:var(--muted); margin-left:8px; vertical-align:middle; }
.badge.ai { border-color:var(--accent); color:var(--accent); }
.sheet { display:grid; grid-template-columns:repeat(3,1fr); gap:0; }
.sheet figure { margin:0; padding:8px 4px 4px; text-align:center; }
.sheet img { width:100%; height:170px; object-fit:contain; }
.sheet figcaption { font-size:12px; opacity:.8; }
.frame img { width:100%; display:block; cursor:zoom-in; }
dl { margin:0; padding:12px 18px 18px; display:grid; grid-template-columns:5.5em 1fr; gap:6px 10px; font-size:14.5px; }
dt { color:var(--muted); } dd { margin:0; }
.sw { display:inline-flex; align-items:center; gap:4px; margin:0 10px 4px 0; font-size:13px; }
.sw i { width:16px; height:16px; border-radius:4px; display:inline-block; border:1px solid rgba(128,128,128,.5); }
.strip img { width:100%; display:block; }
table { border-collapse:collapse; width:100%; font-size:14px; } th, td { border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; }
.ref { display:grid; grid-template-columns:minmax(0,2fr) minmax(0,1fr); gap:20px; align-items:start; }
@media (max-width:760px) { .ref { grid-template-columns:1fr; } .grid { grid-template-columns:1fr; } dl { grid-template-columns:1fr; } }
a { color:var(--accent); }
"""


def expr_img(c: dict, expr: str) -> str:
    if c["route"] == "向量":
        return f'svg/{c["id"]}_{expr}.svg'
    return f'ai/{c["channel"]}_{expr}.png'


def card(c: dict) -> str:
    figs = "".join(f'<figure><img src="{expr_img(c, e)}" alt="{escape(c["name"])} {escape(label)}" loading="lazy">'
                   f'<figcaption>{escape(label)}</figcaption></figure>' for e, label in c["exprs"])
    swatches = "".join(f'<span class="sw"><i style="background:{hx}"></i>{escape(n)} <code>{hx}</code></span>'
                       for hx, n in c["palette"])
    badge = '<span class="badge ai">AI 點陣・PNGtuber</span>' if c["route"] != "向量" else '<span class="badge">向量・可 rig</span>'
    strip = ""
    if c["route"] != "向量":
        strip = (f'<div class="strip" style="background:{BG[c["channel"]]}"><img src="ai/sheet_{c["channel"]}.png" '
                 f'alt="全部差分與漂移對照" loading="lazy"></div>')
    rows = (("人設", c["persona"]), ("個性", c["traits"]), ("口頭禪", c["catchphrase"]), ("為什麼適合", c["fit"]),
            ("風險", c["risk"]), ("第二階段", c["rig"]))
    dl = "".join(f"<dt>{k}</dt><dd>{escape(v)}</dd>" for k, v in rows)
    return (f'<article class="card" id="{c["id"]}"><header><h3>{c["id"].upper()}　{escape(c["name"])}{badge}</h3></header>'
            f'<div class="sheet" style="background:{BG[c["channel"]]}">{figs}</div>{strip}'
            f'<a class="frame" href="frames/{c["id"]}.jpg"><img src="frames/{c["id"]}.jpg" alt="實景 1920×1080" loading="lazy"></a>'
            f'<dl><dt>配色</dt><dd>{swatches}</dd>{dl}</dl></article>')


def consistency_table() -> str:
    data = json.loads((OUT / "ai" / "consistency.json").read_text(encoding="utf-8"))
    states = ("blink", "talk", "surprised", "smug", "wave", "drift", "alt")
    head = "".join(f"<th>{s}</th>" for s in states)
    body = "".join("<tr><td>" + code + "</td>" + "".join(
        f'<td>{rows[s]["silhouette_iou"]:.3f} / {rows[s]["mean_rgb_diff_in_overlap"]:.0f}</td>' for s in states) + "</tr>"
        for code, rows in data.items())
    return f"<table><tr><th>頻道</th>{head}</tr>{body}</table>"


def main() -> int:
    sections = []
    for code, name, mood in CHANNELS:
        cards = "".join(card(c) for c in CONCEPTS if c["channel"] == code)
        sections.append(f'<h2>{escape(name)}</h2><p class="sub">{escape(mood)}</p><div class="grid">{cards}</div>')
    html = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>頻道主持角色</title><style>{CSS}</style></head>
<body><main>
<h1>三頻道虛擬主持角色・第一階段概念稿</h1>
<p class="sub">每個頻道 3 款：2 款向量（照晶片貓 rig 的部件分層，可以直接進第二階段 rig），1 款 AI 點陣（FLUX.2 klein 4B 本機生成，PNGtuber 差分）。
實景圖都是真模板渲染的第 2 頁投影片，角色固定在右下角，字幕是示意。每張的角色像素都量過：進入字幕帶（x 320–1600, y ≥ 880）和 meta 列（x 120–1520, y 832–872）的像素數都是 0（<code>frames.json</code>）。點實景圖可以看原尺寸。</p>
<h2>對照：晶片貓（現行 rig）</h2>
<div class="ref"><a class="frame" href="frames/chipcat.jpg"><img src="frames/chipcat.jpg" alt="晶片貓實景"></a>
<p>{escape(REFERENCE["persona"])}新角色的實景圖用相同的右下角錨點，高度也接近這隻貓（約 350 px），可以直接比大小和存在感。</p></div>
{''.join(sections)}
<h2>AI 點陣路線：一致性量測</h2>
<p class="sub">每格是「剪影 IoU／重疊區平均 RGB 差」，都是跟定裝圖比。差分是用 klein 多參考圖編輯（以定裝圖當參考）做的；drift 是同一段 prompt、換 seed、不給參考圖。
IoU 越接近 1，換幀時角色越不會跳動。</p>
{consistency_table()}
<p class="sub">設計原始碼：<code>tools/chars_*.py</code>（向量）、<code>tools/ai_gen.py</code>（生圖）、<code>tools/frames.py</code>（實景與禁區量測）、<code>tools/ai_sheet.py</code>（去背與一致性）。</p>
</main></body></html>"""
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(OUT / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
