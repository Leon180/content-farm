"""Build the offline video gallery (model × shot, autoplay loop) from results.jsonl.

Usage: python build_gallery.py <shots.json> <out_dir> <docs_dir> [docs_model_id ...]
- <out_dir>/gallery.html links the full-size labelled clips in <out_dir>
- <docs_dir>/gallery.html links 640-px re-encodes in <docs_dir>/clips/ (only the listed models, default all)
"""

from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path

COLUMNS = [
    ("parallax", "2.5D 視差（Depth Anything V2 Small＋ffmpeg）",
     "Apache-2.0（Small 才是；Base/Large 為 CC-BY-NC-4.0）"),
    ("wan22-5b", "Wan2.2-TI2V-5B（MLX q8，20 步）", "Apache-2.0"),
    ("fastwan-5b", "FastWan2.2-TI2V-5B（MLX bf16，DMD 3 步）", "Apache-2.0（繼承 Wan2.2；衍生 repo card）"),
]
DOCS_WIDTH, DOCS_CRF = 640, 30


def latest_rows(out_dir: Path) -> dict[tuple[str, str], dict]:
    rows: dict[tuple[str, str], dict] = {}
    path = out_dir / "results.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing — run parallax.py / run_video.py first")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[(row["model"], row["segment"])] = row
    return rows


def shrink(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={DOCS_WIDTH}:-2",
                    "-c:v", "libx264", "-preset", "slow", "-crf", str(DOCS_CRF), "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-an", str(dst)], check=True)


def cell(row: dict | None, href: str | None) -> str:
    if row is None:
        return '<td class="empty">未跑</td>'
    if not row.get("ok"):
        reason = "逾時（>30 分）" if row.get("timed_out") else f"失敗 rc={row.get('returncode')}"
        return f'<td class="empty">{html.escape(reason)}<br><small>{row.get("seconds", "?")} s</small></td>'
    if href is None:
        return '<td class="empty">未收進 docs</td>'
    stats = [f"{row['seconds']} s 生成"]
    if row.get("peak_rss_gb"):
        stats.append(f"RSS 峰值 {row['peak_rss_gb']} GB")
    if row.get("swap_before_mb") is not None:
        stats.append(f"swap {row['swap_before_mb']}→{row.get('swap_max_mb', row['swap_before_mb'])}"
                     f"→{row['swap_after_mb']} MB")
    return (f'<td><video src="{html.escape(href)}" autoplay loop muted playsinline></video>'
            f'<div class="meta">{" · ".join(html.escape(s) for s in stats)}</div></td>')


def page(shots: dict, rows: dict, link_for) -> str:
    entries = [(s["id"], s["use"]) for s in shots["shots"]] + [(shots["t2v"]["id"], shots["t2v"]["use"])]
    head = "".join(f"<th>{html.escape(name)}<br><small>{html.escape(lic)}</small></th>" for _, name, lic in COLUMNS)
    body = []
    for shot_id, use in entries:
        cells = "".join(cell(rows.get((col, shot_id)), link_for(col, shot_id, rows.get((col, shot_id))))
                        for col, _, _ in COLUMNS)
        body.append(f"<tr><th class='row'>{html.escape(shot_id)}<br><small>{html.escape(use)}</small></th>{cells}</tr>")
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 短影片試做</title>
<style>
:root {{ --bg:#f5f3ee; --fg:#222; --muted:#666; --line:#ddd; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1b1b; --fg:#eee; --muted:#aaa; --line:#333; }} }}
body {{ background:var(--bg); color:var(--fg); font-family:-apple-system,"PingFang TC",sans-serif; margin:16px; }}
.wrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; }}
th, td {{ border:1px solid var(--line); padding:6px; vertical-align:top; }}
th.row {{ text-align:left; min-width:120px; }}
video {{ width:384px; max-width:80vw; display:block; background:#000; }}
.meta, small {{ color:var(--muted); font-size:12px; }}
td.empty {{ color:var(--muted); text-align:center; min-width:200px; }}
</style></head><body>
<h1>AI 短影片試做：九尾狐 × 模型對照（≤3 秒）</h1>
<p>起始畫面：FLUX.2 [klein] 4B 試作圖。AI 欄是 832×480、69 影格（2.9 秒 @24fps）；視差欄是 1280×720、72 影格（3 秒）。
每段左上角已燒入「AI 示意圖」。耗時含模型載入；一次只跑一段，生完卸載。詳見 REPORT-ai-video-trial.md。</p>
<div class="wrap"><table><tr><th></th>{head}</tr>{''.join(body)}</table></div>
</body></html>
"""


def main() -> int:
    shots_path, out_dir, docs_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    docs_models = set(sys.argv[4:]) or {c for c, _, _ in COLUMNS}
    shots = json.loads(shots_path.read_text(encoding="utf-8"))
    rows = latest_rows(out_dir)

    def full_link(col: str, shot_id: str, row: dict | None) -> str | None:
        return row["video"] if row and row.get("ok") else None

    def docs_link(col: str, shot_id: str, row: dict | None) -> str | None:
        if not row or not row.get("ok") or col not in docs_models:
            return None
        rel = f"clips/{col}-{shot_id}.mp4"
        shrink(out_dir / row["video"], docs_dir / rel)
        return rel

    (out_dir / "gallery.html").write_text(page(shots, rows, full_link), encoding="utf-8")
    (docs_dir / "gallery.html").write_text(page(shots, rows, docs_link), encoding="utf-8")
    size = sum(p.stat().st_size for p in (docs_dir / "clips").glob("*.mp4")) if (docs_dir / "clips").is_dir() else 0
    print(f"galleries written; docs clips total {size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
