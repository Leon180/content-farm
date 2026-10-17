"""Round 2 review wall: round2/img/<id>.jpg, round2/contact_<channel>.png, round2/index.html.

    python docs/design/channel-hosts/tools/r2_wall.py <raw_dir>

review.json (hand-written after looking at every image) adds per id: "top" (rank 1–10 within its
channel), "out" (eliminated: why), "diff" (how it differs from the famous IPs it sits nearest to).
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
R2 = HERE.parent / "round2"
NAMES = {"yokai": "妖怪溯源所", "offwork": "晶片貓下班了", "cel": "賽璐璐研究室"}
try:
    from content_farm.assembly.drawtext import find_cjk_font
    FONT = find_cjk_font()
except ImportError:  # run without PYTHONPATH=src: labels are latin ids only
    FONT = None


def images(raw: Path, rows: list[dict]) -> None:
    (R2 / "img").mkdir(parents=True, exist_ok=True)
    for row in rows:
        src = raw / f"{row['id']}.png"
        if src.is_file():
            Image.open(src).convert("RGB").resize((640, 640), Image.LANCZOS).save(R2 / "img" / f"{row['id']}.jpg", quality=84)


def contact(rows: list[dict], code: str) -> None:
    items = [r for r in rows if r["channel"] == code and (R2 / "img" / f"{r['id']}.jpg").is_file()]
    cell = 320
    sheet = Image.new("RGB", (cell * 5, cell * ((len(items) + 4) // 5)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT, 30) if FONT else ImageFont.load_default(30)
    for i, r in enumerate(items):
        x, y = (i % 5) * cell, (i // 5) * cell
        sheet.paste(Image.open(R2 / "img" / f"{r['id']}.jpg").resize((cell, cell)), (x, y))
        draw.text((x + 8, y + 6), r["id"], font=font, fill="#d0021b")
    sheet.save(R2 / f"contact_{code}.png", optimize=True)


CSS = """
:root{--bg:#f6f4ef;--fg:#1d1e22;--muted:#66645e;--card:#fff;--line:#e2ded5;--top:#c2185b;--out:#8a8a8a}
@media (prefers-color-scheme:dark){:root{--bg:#141518;--fg:#ecebe6;--muted:#9a988f;--card:#1f2126;--line:#33363d;--top:#ff6fa5;--out:#777}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 "PingFang TC","Noto Sans CJK TC",sans-serif}
main{max-width:1400px;margin:0 auto;padding:20px 16px 64px}h1{font-size:24px;margin:0 0 6px}
h2{font-size:21px;margin:36px 0 10px;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:2;border-bottom:1px solid var(--line)}
.sub{color:var(--muted);margin:0 0 10px}nav a{margin-right:14px;color:var(--top)}
.wall{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
@media (max-width:520px){.wall{grid-template-columns:repeat(2,1fr);gap:8px}}
.c{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;position:relative}
.c img{width:100%;aspect-ratio:1;display:block;background:#fff}
.c .t{padding:8px 10px 10px}.id{font:700 18px/1 "SF Mono",Menlo,monospace}
.st{font-size:12px;color:var(--muted);margin-left:6px}.n{font-size:14px;margin-top:4px}
.d{font-size:12.5px;color:var(--muted);margin-top:6px;border-top:1px dashed var(--line);padding-top:6px}
.c.top{border:2px solid var(--top)}.rank{position:absolute;top:8px;left:8px;background:var(--top);color:#fff;font:700 13px/1 sans-serif;padding:5px 8px;border-radius:99px}
.c.out img{opacity:.35;filter:grayscale(1)}.c.out .n{text-decoration:line-through;color:var(--out)}
.outtag{position:absolute;top:8px;right:8px;background:#333;color:#fff;font-size:12px;padding:4px 8px;border-radius:99px}
"""


def card(r: dict, rv: dict) -> str:
    cls, badges, diff = "c", "", ""
    if rv.get("top"):
        cls += " top"
        badges += f'<span class="rank">前十 #{rv["top"]}</span>'
    if rv.get("out"):
        cls += " out"
        badges += '<span class="outtag">淘汰</span>'
        diff = f'<div class="d">淘汰：{escape(rv["out"])}</div>'
    elif rv.get("diff"):
        diff = f'<div class="d">相似度把關：{escape(rv["diff"])}</div>'
    if rv.get("note"):
        diff += f'<div class="d">{escape(rv["note"])}</div>'
    return (f'<div class="{cls}" id="{r["id"]}">{badges}<a href="img/{r["id"]}.jpg"><img src="img/{r["id"]}.jpg" '
            f'alt="{r["id"]}" loading="lazy"></a><div class="t"><span class="id">{r["id"]}</span>'
            f'<span class="st">{escape(r["style_zh"])}</span><div class="n">{escape(r["note"])}</div>{diff}</div></div>')


def page(rows: list[dict], review: dict) -> str:
    sections = []
    for code, name in NAMES.items():
        cards = "".join(card(r, review.get(r["id"], {})) for r in rows if r["channel"] == code)
        sections.append(f'<h2 id="{code}">{escape(name)}</h2><div class="wall">{cards}</div>')
    nav = "".join(f'<a href="#{c}">{n}</a>' for c, n in NAMES.items())
    return (f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width, initial-scale=1"><title>主持角色第二輪</title><style>{CSS}</style></head><body><main>'
            f'<h1>主持角色・第二輪候選牆（75 張）</h1>'
            f'<p class="sub">直接回編號就好，例如「Y07、O12、C03」。粉框是我挑的各頻道前十，灰色是相似度把關淘汰的。'
            f'點圖可以看大圖。全部由本機 FLUX.2 klein 4B 生成，提示詞只用設計原則描述，沒有寫任何 IP 名'
            f'（見 <a href="principles.md">principles.md</a>、<a href="prompts.json">prompts.json</a>）。</p>'
            f'<nav>{nav}</nav>{"".join(sections)}</main></body></html>')


def main(argv: list[str]) -> int:
    rows = json.loads((R2 / "prompts.json").read_text(encoding="utf-8"))
    review_path = R2 / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else {}
    if argv:
        images(Path(argv[0]), rows)
        for code in NAMES:
            contact(rows, code)
    (R2 / "index.html").write_text(page(rows, review), encoding="utf-8")
    print(R2 / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
