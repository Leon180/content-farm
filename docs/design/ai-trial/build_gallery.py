"""Label every trial image 「AI 示意圖」, then build contact_sheet.png and an offline gallery.html.

Usage: python build_gallery.py <prompts.json> <trial_dir> <docs_dir>
- <trial_dir>/labeled/<model>/<segment>.png  full size, label in the top-left corner
- <docs_dir>/img/<model>-<segment>.jpg        768 px wide, for the committed gallery
- contact_sheet.png and gallery.html in both directories (the trial copy links full-size PNGs)
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LABEL = "AI 示意圖"
FONTS = ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
         "/Library/Fonts/Arial Unicode.ttf")
THUMB_WIDTH = 768

LICENSES = {
    "zimage": ("Apache-2.0", "https://github.com/Tongyi-MAI/Z-Image/blob/main/LICENSE",
               "原始 HF repo 沒有 LICENSE 檔，只有 card 的 license: apache-2.0；官方 GitHub repo 的 LICENSE 是 Apache-2.0 全文。"
               "4-bit 衍生 repo 的 card 寫 tongyi-qianwen-license，連結指向一個不存在的檔案。"),
    "klein4b": ("Apache-2.0", "https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/main/LICENSE.md",
                "原始 repo 的 LICENSE.md 是 Apache-2.0 全文（176 行，無附加條款）。q4 衍生 repo card 標 apache-2.0。"),
    "schnell": ("Apache-2.0", "https://github.com/black-forest-labs/flux/blob/main/model_licenses/LICENSE-FLUX1-schnell",
                "官方 GitHub 的 LICENSE-FLUX1-schnell 是 Apache-2.0 全文；HF repo card 標 apache-2.0。q4 衍生 repo card 標 apache-2.0。"),
}


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise FileNotFoundError(f"no CJK font among {FONTS}")


def labelled(image: Image.Image) -> Image.Image:
    """Return a copy with 「AI 示意圖」 in a translucent box at the top-left corner."""
    base = image.convert("RGBA")
    size = max(18, base.height // 28)
    face = font(size)
    pad, margin = size // 2, size
    left, top, right, bottom = face.getbbox(LABEL)
    box = (margin, margin, margin + right - left + 2 * pad, margin + bottom - top + 2 * pad)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(box, radius=pad, fill=(0, 0, 0, 150))
    draw.text((margin + pad - left, margin + pad - top), LABEL, font=face, fill=(255, 255, 255, 235))
    return Image.alpha_composite(base, overlay).convert("RGB")


def load_rows(trial: Path) -> dict[tuple[str, str], dict]:
    rows: dict[tuple[str, str], dict] = {}
    path = trial / "results.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing — run run_trial.py first")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[(row["model"], row["segment"])] = row
    return rows


def contact_sheet(cells: list[list[Image.Image | None]], row_names: list[str], col_names: list[str]) -> Image.Image:
    cell_w, cell_h, head, side = 384, 216, 44, 170
    sheet = Image.new("RGB", (side + cell_w * len(col_names), head + cell_h * len(row_names)), (245, 243, 238))
    draw, face = ImageDraw.Draw(sheet), font(18)
    for c, name in enumerate(col_names):
        draw.text((side + c * cell_w + 8, 12), name, font=face, fill=(40, 40, 40))
    for r, name in enumerate(row_names):
        draw.text((8, head + r * cell_h + cell_h // 2 - 10), name, font=face, fill=(40, 40, 40))
        for c, image in enumerate(cells[r]):
            if image is not None:
                sheet.paste(image.resize((cell_w - 4, cell_h - 4)), (side + c * cell_w + 2, head + r * cell_h + 2))
    return sheet


def figure(row: dict | None, src: str, segment: dict) -> str:
    if row is None or not row.get("ok"):
        reason = "未產出" if row is None else f"失敗（rc={row.get('returncode')}）"
        return f'<figure class="miss"><div>{reason}</div><figcaption>{html.escape(segment["id"])}</figcaption></figure>'
    peak = row["mflux_peak_gb"] if row["mflux_peak_gb"] is not None else "—"
    return (f'<figure><a href="{src}"><img src="{src}" alt="{html.escape(segment["id"])}" loading="lazy"></a>'
            f'<figcaption>{row["seconds"]} s · RSS {row["peak_rss_gb"]} GB · mflux 峰值 {peak} GB · '
            f'swap {row["swap_before_mb"]}→{row["swap_max_mb"]}→{row["swap_after_mb"]} MB</figcaption></figure>')


def page(spec: dict, rows: dict, src_for) -> str:
    models, segments = spec["models"], spec["segments"]
    head = "".join(f"<th>{html.escape(m['name'])}<br><small>{m['steps']} 步 · seed {spec['seed']}</small></th>"
                   for m in models)
    body = "".join(
        f"<tr><th><b>{html.escape(s['id'])}</b><br><small>{html.escape(s['use'])}：{html.escape(s['why'])}</small></th>"
        + "".join(f"<td>{figure(rows.get((m['id'], s['id'])), src_for(m['id'], s['id']), s)}</td>" for m in models)
        + "</tr>" for s in segments)
    prompts = "".join(f"<li><b>{html.escape(s['id'])}</b>（{html.escape(s['slide'])}）<code>{html.escape(s['prompt'])}</code></li>"
                      for s in segments)
    licences = "".join(
        f"<tr><td>{html.escape(m['name'])}</td><td>{html.escape(m['origin_repo'])}</td>"
        f"<td>{LICENSES[m['id']][0]}</td><td><a href=\"{LICENSES[m['id']][1]}\">原文</a></td>"
        f"<td>{html.escape(LICENSES[m['id']][2])}</td></tr>" for m in models)
    return TEMPLATE.format(size=f"{spec['size'][0]}×{spec['size'][1]}", head=head, body=body,
                           prompts=prompts, licences=licences, rule=html.escape(spec["style_rule"]))


TEMPLATE = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 插圖試做</title>
<style>
:root {{ --bg:#f7f5f0; --fg:#222; --muted:#666; --line:#ddd; --card:#fff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16171a; --fg:#e8e6e1; --muted:#9a9a9a; --line:#333; --card:#202226; }} }}
body {{ margin:0; padding:16px; background:var(--bg); color:var(--fg); font:15px/1.6 -apple-system,"PingFang TC",sans-serif; }}
h1 {{ font-size:22px; margin:0 0 4px; }} p.lead {{ color:var(--muted); margin:0 0 16px; }}
.wrap {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; }}
th, td {{ border-top:1px solid var(--line); padding:8px; vertical-align:top; text-align:left; }}
thead th {{ position:sticky; top:0; background:var(--bg); }}
tbody th {{ width:200px; font-weight:normal; }} small {{ color:var(--muted); }}
figure {{ margin:0; min-width:260px; }} img {{ width:100%; border-radius:6px; display:block; }}
figcaption {{ font-size:12px; color:var(--muted); }}
.miss div {{ aspect-ratio:16/9; display:grid; place-items:center; background:var(--card); border-radius:6px; color:var(--muted); }}
code {{ display:block; font-size:12px; color:var(--muted); white-space:pre-wrap; }}
section {{ margin-top:24px; }}
</style></head><body>
<h1>九尾狐：AI 插圖試做（模型 × 段落）</h1>
<p class="lead">{size}，固定 seed，一次只跑一張、每張獨立程序（生完即卸載）。畫面角落的「AI 示意圖」是上片時的固定標籤示範。規則：{rule}。</p>
<div class="wrap"><table><thead><tr><th>段落</th>{head}</tr></thead><tbody>{body}</tbody></table></div>
<section><h2>授權（原始 repo 的 LICENSE 原文）</h2><div class="wrap"><table>
<thead><tr><th>模型</th><th>原始 repo</th><th>授權</th><th>出處</th><th>備註</th></tr></thead><tbody>{licences}</tbody></table></div></section>
<section><h2>Prompt</h2><ul>{prompts}</ul></section>
</body></html>
"""


def main() -> int:
    spec_path, trial, docs = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    rows = load_rows(trial)
    (docs / "img").mkdir(parents=True, exist_ok=True)
    cells: list[list[Image.Image | None]] = []
    for segment in spec["segments"]:
        line: list[Image.Image | None] = []
        for model in spec["models"]:
            raw = trial / model["id"] / f"{segment['id']}.png"
            row = rows.get((model["id"], segment["id"]))
            if not raw.is_file() or row is None or not row.get("ok"):
                line.append(None)
                continue
            image = labelled(Image.open(raw))
            out = trial / "labeled" / model["id"] / raw.name
            out.parent.mkdir(parents=True, exist_ok=True)
            image.save(out)
            thumb = image.resize((THUMB_WIDTH, round(image.height * THUMB_WIDTH / image.width)), Image.LANCZOS)
            thumb.save(docs / "img" / f"{model['id']}-{segment['id']}.jpg", quality=82)
            line.append(image)
        cells.append(line)
    sheet = contact_sheet(cells, [s["id"] for s in spec["segments"]], [m["name"] for m in spec["models"]])
    sheet.save(trial / "contact_sheet.png")
    sheet.save(docs / "contact_sheet.png", optimize=True)
    (docs / "gallery.html").write_text(page(spec, rows, lambda m, s: f"img/{m}-{s}.jpg"), encoding="utf-8")
    (trial / "gallery.html").write_text(page(spec, rows, lambda m, s: f"labeled/{m}/{s}.png"), encoding="utf-8")
    print(f"{sum(c is not None for line in cells for c in line)} images → {docs}/gallery.html, {trial}/gallery.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
