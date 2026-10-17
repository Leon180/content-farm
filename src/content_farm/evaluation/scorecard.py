"""Scorecard HTML: three columns (視覺／聽覺／內容) with lights, simulated retention curves of every
round (baseline included), engagement heat map, homepage A/B table, common fixes, round table."""

from __future__ import annotations

import html
from pathlib import Path

LIGHT = {"green": "#2f9e44", "yellow": "#f08c00", "red": "#e03131", "gray": "#868e96"}
COLUMN_NAME = {"visual": "視覺", "audio": "聽覺", "content": "內容"}
CURVE_COLOURS = ["#868e96", "#1c7ed6", "#e8590c", "#2f9e44", "#9c36b5"]


def _e(value: object) -> str:
    return html.escape("—" if value is None else str(value))


def _curve_svg(rounds: list[dict]) -> str:
    width, height, pad = 640, 220, 34
    lines, legend = [], []
    for i, rnd in enumerate(rounds):
        curve = (rnd.get("audience") or {}).get("curve") or []
        if not curve:
            continue
        duration = max(len(curve) * 10, 1)
        pts = " ".join(f"{pad + (k * 10) / duration * (width - 2 * pad):.1f},"
                       f"{height - pad - v * (height - 2 * pad):.1f}" for k, v in enumerate(curve))
        colour = CURVE_COLOURS[i % len(CURVE_COLOURS)]
        lines.append(f'<polyline fill="none" stroke="{colour}" stroke-width="2.5" points="{pts}"/>')
        legend.append(f'<span style="color:{colour}">■ {_e(rnd["label"])}</span>')
    axis = (f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" stroke="var(--muted)"/>'
            f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="var(--muted)"/>'
            f'<line x1="{pad}" y1="{height / 2}" x2="{width - pad}" y2="{height / 2}" stroke="var(--muted)" stroke-dasharray="4 4"/>'
            f'<text x="4" y="{pad + 4}" font-size="11" fill="var(--muted)">100%</text>'
            f'<text x="4" y="{height / 2 + 4}" font-size="11" fill="var(--muted)">50%</text>'
            f'<text x="{width - pad - 70}" y="{height - 8}" font-size="11" fill="var(--muted)">片長比例 →</text>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="模擬留存曲線">{axis}'
            f'{"".join(lines)}</svg><div class="legend">{" ".join(legend)}</div>')


def _heat(aud: dict) -> str:
    heat = aud.get("heat") or {}
    if not heat:
        return "<p>（無觀眾結果）</p>"
    rows = []
    for persona, values in heat.items():
        cells = "".join(f'<td title="{k * 10 // 60}:{k * 10 % 60:02d} {v}" style="background:hsl({(v or 0) * 12},70%,{88 - (v or 0) * 3}%)"></td>'
                        for k, v in enumerate(values))
        rows.append(f"<tr><th>{_e(persona)}</th>{cells}</tr>")
    return f'<div class="heatwrap"><table class="heat">{"".join(rows)}</table></div>'


def _checks(checks: list[dict], column: str) -> str:
    rows = [f'<tr><td><span class="dot" style="background:{LIGHT["green" if c["ok"] else ("red" if c["critical"] else "yellow")]}"></span>'
            f'{_e(c["name"])}</td><td>{_e(c["value"])}</td><td>{_e(c["target"])}</td></tr>'
            for c in checks if c["column"] == column]
    return f'<table class="checks"><tr><th>指標</th><th>值</th><th>門檻</th></tr>{"".join(rows)}</table>'


def _round_table(rounds: list[dict]) -> str:
    head = "<tr><th>輪次</th><th>離開中位</th><th>點擊（最佳款）</th><th>平均投入</th><th>視覺</th><th>聽覺</th><th>內容</th><th>首頁注意中位／被選</th><th>達標</th><th>耗時</th></tr>"
    rows = []
    for rnd in rounds:
        aud, cols, home = rnd.get("audience") or {}, rnd.get("columns") or {}, rnd.get("homepage") or {}
        best = min(home.values(), key=lambda h: (h["noticed_median"], -h["pick_rate"])) if home else None
        col = "".join(f'<td><span class="dot" style="background:{LIGHT[cols.get(k, {}).get("light", "gray")]}"></span>'
                      f'{_e(cols.get(k, {}).get("score"))}</td>' for k in ("visual", "audio", "content"))
        ok = (rnd.get("verdict") or {}).get("pass")
        rows.append(f"<tr><td>{_e(rnd['label'])}</td><td>{_e(aud.get('leave_median_pct'))}</td>"
                    f"<td>{_e(aud.get('click_best'))} {_e(aud.get('best_variant'))}</td><td>{_e(aud.get('engagement_mean'))}</td>{col}"
                    f"<td>{_e(best and best['noticed_median'])}／{_e(best and best['pick_rate'])}</td>"
                    f"<td>{'✅' if ok else '—' if ok is None else '❌'}</td><td>{_e(rnd.get('minutes'))}</td></tr>")
    return f'<table class="rounds">{head}{"".join(rows)}</table>'


def _fixes(fixes: list[dict]) -> str:
    rows = [f"<tr><td>{_e(f['t'] // 60 if f['t'] is not None else None)}:{(f['t'] or 0) % 60:02.0f}</td><td>{_e(f['category'])}</td>"
            f"<td>{f['votes']}</td><td>{_e(f['problem'])}<div class='fix'>→ {_e(f['fix'])}</div></td></tr>"
            for f in fixes[:20]]
    return f'<table class="fixes"><tr><th>時間</th><th>類別</th><th>票</th><th>問題／改法</th></tr>{"".join(rows)}</table>'


def _homepage(home: dict) -> str:
    if not home:
        return "<p>（本輪沒有首頁情境）</p>"
    rows = [f"<tr><td>{_e(k)}</td><td>{_e(v['noticed_median'])}</td><td>{v['pick_rate']:.0%}</td>"
            f"<td>{2 * v['chance']:.0%}</td><td>{v['answers']}</td></tr>" for k, v in home.items()]
    return ('<table><tr><th>縮圖</th><th>被注意名次中位（≤3）</th><th>被選比例</th><th>門檻 2/N</th><th>樣本</th></tr>'
            f'{"".join(rows)}</table>')


CSS = """:root{--bg:#fff;--fg:#1d2329;--muted:#6b7480;--card:#f4f6f8;--line:#dfe3e8}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121417;--fg:#e8eaed;--muted:#9aa3ad;--card:#1c2025;--line:#2d333a}}
:root[data-theme=dark]{--bg:#121417;--fg:#e8eaed;--muted:#9aa3ad;--card:#1c2025;--line:#2d333a}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"PingFang TC","Noto Sans TC",sans-serif}
main{max-width:1100px;margin:auto;padding:16px}h1{font-size:22px}h2{font-size:18px;margin-top:28px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.card{background:var(--card);border-radius:10px;padding:12px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}.big{font-size:28px;font-weight:700}
.heatwrap{overflow-x:auto}.heat td{width:9px;height:18px;padding:0;border:none}.heat th{white-space:nowrap;padding-right:8px}
.fix{color:var(--muted)}.legend span{margin-right:12px;font-size:13px}.verdict{padding:10px;border-radius:8px;background:var(--card)}"""


def render(rounds: list[dict], current: dict, title: str, out: Path) -> Path:
    cols = current.get("columns") or {}
    col_cards = "".join(
        f'<div class="card"><h3><span class="dot" style="background:{LIGHT[cols.get(k, {}).get("light", "gray")]}"></span>'
        f'{COLUMN_NAME[k]} <span class="big">{_e(cols.get(k, {}).get("score"))}</span>/10</h3>{_checks(current.get("checks", []), k)}</div>'
        for k in ("visual", "audio", "content"))
    verdict = current.get("verdict") or {}
    holdout = current.get("holdout") or {}
    body = f"""<main><h1>{_e(title)}：上線前評分卡（{_e(current['label'])}）</h1>
<div class="verdict">{'✅ 達標' if verdict.get('pass') else '❌ 未達標：' + _e('；'.join(verdict.get('reasons', [])))}</div>
<h2>三欄指標</h2><div class="cols">{col_cards}</div>
<h2>模擬留存（各輪對照）</h2><div class="card">{_curve_svg(rounds)}</div>
<h2>各輪對照</h2><div class="card">{_round_table(rounds)}</div>
<h2>首頁情境縮圖（A/B/C）</h2><div class="card">{_homepage(current.get('homepage') or {})}</div>
<h2>投入熱度圖（每格 10 秒）</h2><div class="card">{_heat(current.get('audience') or {})}</div>
<h2>Holdout 觀眾（只在最後一輪，不參與修正依據）</h2><div class="card">{_e(holdout) if holdout else '（本輪沒有 holdout）'}</div>
<h2>共同修正清單（非 holdout 觀眾＋專業評審，按票數）</h2><div class="card">{_fixes(current.get('fixes') or [])}</div>
</main>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
                   f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>上線前評分卡</title>'
                   f'<style>{CSS}</style></head><body>{body}</body></html>', encoding="utf-8")
    return out
