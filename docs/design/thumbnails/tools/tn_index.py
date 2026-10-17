"""docs/design/thumbnails/index.html: each variant as it would appear on YouTube, at real display sizes.

    python docs/design/thumbnails/tools/tn_index.py <launch_output_dir>

Mocks (approximate, offline, no YouTube assets): phone home feed card (full-width 16:9, ~360 px wide),
desktop home grid card (~320 px wide), and for the Short the Shorts shelf card (~180 x 320).
Titles come from each run's upload/manual/title.txt, durations from script.json.
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(HERE))
from tn_variants import VIDEOS  # noqa: E402

LAYOUT_ZH = {"character": "(a) 角色大表情＋大字", "keyart": "(b) 主視覺＋問句", "compare": "(c) 數字／對比"}

CSS = """
:root{--bg:#f2f2f2;--fg:#0f0f0f;--muted:#606060;--card:#fff;--line:#e5e5e5}
@media (prefers-color-scheme:dark){:root{--bg:#0f0f0f;--fg:#f1f1f1;--muted:#aaa;--card:#181818;--line:#303030}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 Roboto,"PingFang TC","Noto Sans CJK TC",sans-serif}
main{max-width:1280px;margin:0 auto;padding:20px 16px 60px}h1{font-size:22px;margin:0 0 6px}
h2{font-size:19px;margin:36px 0 10px;border-top:1px solid var(--line);padding-top:20px}.note{color:var(--muted);margin:0 0 10px}
.row{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:22px}
.variant{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.vhead{font-weight:700;margin-bottom:8px}.vhead span{color:var(--muted);font-weight:400;margin-left:6px}
.mocks{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start}
.mock{width:340px}.mock.desk{width:320px}.mock.short{width:180px}
.label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.thumb{position:relative;width:100%;aspect-ratio:16/9;border-radius:0;overflow:hidden;background:#000}
.desk .thumb{border-radius:12px}.short .thumb{aspect-ratio:9/16;border-radius:12px}
.thumb img{width:100%;height:100%;object-fit:cover;display:block}
.dur{position:absolute;right:6px;bottom:6px;background:rgba(0,0,0,.8);color:#fff;font-size:12px;font-weight:600;padding:1px 4px;border-radius:4px}
.meta{display:flex;gap:10px;margin-top:10px}.avatar{width:36px;height:36px;border-radius:50%;flex:none;background:#c4302b;
color:#fff;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700}
.desk .avatar{width:36px;height:36px}.title{font-size:15px;font-weight:600;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;
-webkit-box-orient:vertical;overflow:hidden}.short .title{font-size:13px}.chan{color:var(--muted);font-size:13px;margin-top:2px}
.promise{margin-top:10px;font-size:13px;border-top:1px dashed var(--line);padding-top:8px}.promise b{color:#c2185b}
.qc{font-size:12px;color:var(--muted)}a{color:inherit}
@media (max-width:420px){.row{grid-template-columns:1fr}.mock{width:100%}}
"""


def duration(script: dict) -> str:
    total = round(sum(float(s.get("duration_seconds") or 0) for s in script.get("scenes", [])))
    return f"{total // 60}:{total % 60:02d}"


def card(kind: str, img: str, title: str, channel: str, dur: str) -> str:
    label = {"phone": "手機首頁", "desk": "桌機首頁", "short": "Shorts 架"}[kind]
    meta = (f'<div class="meta"><div class="avatar">{escape(channel[:1])}</div><div><div class="title">{escape(title)}</div>'
            f'<div class="chan">{escape(channel)} · 1.2萬次觀看 · 1 天前</div></div></div>') if kind != "short" else \
        f'<div class="title" style="margin-top:6px">{escape(title)}</div><div class="chan">1.2萬次觀看</div>'
    badge = f'<div class="dur">{dur}</div>' if kind != "short" else ""
    return (f'<div class="mock {kind}"><div class="label">{label}</div><div class="thumb"><img src="{escape(img)}" alt="">'
            f'{badge}</div>{meta}</div>')


def main(argv: list[str]) -> int:
    src = Path(argv[0])
    report = json.loads((OUT / "promises.json").read_text(encoding="utf-8"))
    sections = []
    for name, video in VIDEOS.items():
        run = src / video["source"]
        title = (run / "upload/manual/title.txt").read_text(encoding="utf-8").strip()
        dur = duration(json.loads((run / "script.json").read_text(encoding="utf-8")))
        info = report[name]
        cells = []
        for key, v in info["variants"].items():
            kinds = ("short",) if info["vertical"] else ("phone", "desk")
            mocks = "".join(card(k, v["file"], title, info["channel"], dur) for k in kinds)
            promises = "；".join(f"「{p['phrase']}」在 <b>{p['spoken_at_s']:.0f} 秒</b>" if p["spoken_at_s"] is not None
                                else f"「{p['phrase']}」<b>未找到</b>" for p in v["promises"])
            credit = f"<div class='qc'>主視覺：{escape(v['credit'])}</div>" if v["credit"] else ""
            cells.append(f'<div class="variant"><div class="vhead">{name.upper()}-{key.upper()}<span>{LAYOUT_ZH[v["layout"]]}'
                         f'・{v["kb"]} KB</span></div><div class="mocks">{mocks}</div>'
                         f'<div class="promise">承諾對應：{promises}</div>{credit}</div>')
        qc = "；".join(escape(m) for m in info["qc"])
        note = "Shorts 不支援「測試與比較」，三款封面只能人工挑選。" if info["vertical"] else \
            "三款可直接放進 YouTube「測試與比較」（以觀看時間佔比判定勝出）。"
        sections.append(f'<h2>{escape(title)}</h2><p class="note">{escape(info["channel"])}・片長 {dur}・{note}</p>'
                        f'<p class="qc">QC：{qc}</p><div class="row">{"".join(cells)}</div>')
    html = (f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width, initial-scale=1"><title>開台片縮圖</title><style>{CSS}</style></head><body><main>'
            f'<h1>開台片縮圖・每支 3 款</h1><p class="note">按 YouTube 實際顯示尺寸模擬（手機首頁約 340 px 寬、桌機首頁約 320 px、'
            f'Shorts 架約 180 px）；觀看數與日期是示意。每款下方是「承諾對應」：縮圖上的字在片中第幾秒兌現。'
            f'規則見 <a href="rules.md">rules.md</a>。</p>{"".join(sections)}</main></body></html>')
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(OUT / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
