#!/usr/bin/env python3
"""Build docs/design/channel-brands/index.html (選稿頁) from proposals.json + measurements.json.

    PYTHONPATH=src python scripts/build_channel_brands_page.py

Run ``scripts/render_channel_brands.py`` first; the page only links the images it wrote.
Choices made on the page stay in the viewer's browser (localStorage) and can be
copied out as plain text for the decision thread.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jinja2 import Environment, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design" / "channel-brands"

TEMPLATE = r"""<!doctype html>
<html lang="zh-Hant-TW"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>頻道品牌選稿</title>
<style>
:root { --bg:#f6f6f4; --fg:#1b1d21; --muted:#5d636d; --line:#d9dbe0; --card:#fff; --pick:#1a7f4b; --no:#b3261e; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#121417; --fg:#eceef1; --muted:#9aa1ab; --line:#2a2e35; --card:#1a1d22; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.65 "Noto Sans CJK TC","PingFang TC",sans-serif; }
main { max-width:1180px; margin:0 auto; padding:32px 16px 96px; }
h1 { font-size:30px; margin:0 0 6px; } h2 { font-size:26px; margin:0; } h3 { font-size:17px; margin:22px 0 8px; }
p.lead { color:var(--muted); margin:0 0 20px; }
img { max-width:100%; display:block; border-radius:6px; }
a.img { display:block; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:22px; margin:26px 0; }
.brand-head { display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
.brand-head img { width:72px; height:72px; border-radius:50%; }
.sub { color:var(--muted); }
.grid3 { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
.grid2 { display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }
.shorts { display:grid; grid-template-columns:240px 1fr; gap:16px; align-items:start; }
@media (max-width:760px) { .grid3,.grid2,.shorts { grid-template-columns:1fr; } }
table { border-collapse:collapse; width:100%; font-size:15px; }
td, th { border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }
.sw { display:inline-block; width:22px; height:22px; border-radius:4px; border:1px solid var(--line); vertical-align:middle; margin-right:6px; }
.chips span { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 12px; margin:0 6px 6px 0; }
.names label { display:block; border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin:8px 0; cursor:pointer; }
.names input { margin-right:8px; }
.rec { font-size:12px; background:var(--pick); color:#fff; border-radius:4px; padding:1px 6px; margin-left:6px; }
.verdict { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
.verdict button { border:1px solid var(--line); background:var(--bg); color:var(--fg); border-radius:8px; padding:8px 14px; cursor:pointer; font:inherit; }
.verdict button[aria-pressed="true"] { background:var(--pick); color:#fff; border-color:var(--pick); }
.verdict button.no[aria-pressed="true"] { background:var(--no); border-color:var(--no); }
textarea { width:100%; min-height:64px; margin-top:10px; font:inherit; background:var(--bg); color:var(--fg); border:1px solid var(--line); border-radius:8px; padding:8px; }
.ok { color:var(--pick); } .bad { color:var(--no); }
#summary { position:fixed; right:16px; bottom:16px; }
#summary button { background:var(--fg); color:var(--bg); border:0; border-radius:999px; padding:12px 20px; font:inherit; cursor:pointer; }
pre#out { white-space:pre-wrap; background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px; display:none; }
</style></head><body><main>
<h1>四個頻道的品牌系統（選稿）</h1>
<p class="lead">以頻道為單位，不以單支影片為單位。每個品牌都用自己的樣式跑過真正的 explainer 模板（<code>brand=&lt;code&gt;</code>）。角色一律是剪影佔位；點圖看原尺寸。在每個品牌下方選名稱、按「採用／修改／不採用」，最後按右下角複製選擇。</p>
<a class="img" href="overview.png"><img src="overview.png" alt="四個品牌並排總覽"></a>

<section class="card">
<h2>隱形的同一條線：要，但只放在片尾</h2>
<p>{{ studio.decision }}</p><p class="sub">{{ studio.why }}</p>
<ul>{% for e in studio.elements %}<li>{{ e }}</li>{% endfor %}</ul>
<p><strong>待決定：</strong>{{ studio.name }}</p>
</section>

{% for b in brands %}{% set m = measurements[b.code] %}
<section class="card" id="{{ b.code }}" data-code="{{ b.code }}">
<div class="brand-head"><a href="{{ b.code }}/icon_circle.png"><img src="{{ b.code }}/icon.png" alt="頻道 icon（點開看圓形裁切與小尺寸）"></a>
<div><h2>{{ b.line }}　{{ b.recommend }}</h2><div class="sub">{{ b.positioning }}</div></div></div>
{% if b.decision %}<p><strong>判斷：</strong>{{ b.decision }}</p>{% endif %}

<h3>頻道名稱（YouTube 撞名查詢 2026-10-15）</h3>
<div class="names">{% for n in b.names %}
<label><input type="radio" name="name-{{ b.code }}" value="{{ n.name }}"{% if n.name == b.recommend %} checked{% endif %}>
<strong>{{ n.name }}</strong>{% if n.name == b.recommend %}<span class="rec">推薦</span>{% endif %}
<div class="sub">{{ n.why }}</div><div class="sub">撞名：{{ n.check }}</div></label>{% endfor %}
{% if b.avoid_name %}<p class="sub">⚠ {{ b.avoid_name }}</p>{% endif %}</div>

<h3>個性、語氣、口頭禪</h3>
<div class="chips">{% for p in b.personality %}<span>{{ p }}</span>{% endfor %}</div>
<p>{{ b.voice.tone }}</p>
<ul>{% for c in b.voice.catchphrases %}<li>「{{ c }}」</li>{% endfor %}</ul>
<p class="sub">不做：{{ b.voice.avoid | join("；") }}</p>

<h3>角色方向（美術另由 mascot worker 處理）</h3><p>{{ b.character }}</p>

<h3>示範投影片（真模板渲染，3 張）</h3>
<div class="grid3">{% for i in [1,2,3] %}<a class="img" href="{{ b.code }}/slide_0{{ i }}.jpg"><img src="{{ b.code }}/slide_0{{ i }}.jpg" alt="slide {{ i }}" loading="lazy"></a>{% endfor %}</div>
<p class="sub">版面檢查：{% if m.problems %}<span class="bad">{{ m.problems }}</span>{% else %}<span class="ok">無溢出、無侵入字幕區</span>{% endif %}</p>
<p class="sub">從 slide-styles-10 怎麼改：{{ b.derived }}</p>

<h3>縮圖（3 款）</h3>
<div class="grid3">{% for i in [1,2,3] %}<a class="img" href="{{ b.code }}/thumb_{{ i }}.jpg"><img src="{{ b.code }}/thumb_{{ i }}.jpg" alt="thumbnail {{ i }}" loading="lazy"></a>{% endfor %}</div>
<table><tr><th>構圖</th><td>{{ b.thumbnail.composition }}</td></tr><tr><th>字級</th><td>{{ b.thumbnail.type_size }}</td></tr>
<tr><th>色彩</th><td>{{ b.thumbnail.color }}</td></tr><tr><th>角色位置</th><td>{{ b.thumbnail.character }}</td></tr></table>

<h3>色彩（WCAG 對比由樣式表實算）</h3>
<table>{% for c in b.colors %}<tr><td><span class="sw" style="background:{{ c.hex }}"></span><code>{{ c.hex }}</code></td><td>{{ c.role }}</td><td>{{ c.use }}</td></tr>{% endfor %}</table>
<p class="sub">{% for r in m.contrast %}{{ r.pair }} {{ r.ratio }}{% if r.ok %} ✓{% else %} ✗{% endif %}{% if not loop.last %}；{% endif %}{% endfor %}</p>

<h3>字體、版型、動畫、轉場</h3>
<table>{% for t in b.type %}<tr><th>{{ t.role }}</th><td>{{ t.font }}{% if t.note %}<span class="sub">（{{ t.note }}）</span>{% endif %}</td></tr>{% endfor %}
<tr><th>版型語言</th><td>{{ b.layout }}</td></tr><tr><th>動畫語言</th><td>{{ b.motion }}</td></tr><tr><th>轉場</th><td>{{ b.transition }}</td></tr>
<tr><th>片頭</th><td>{{ b.intro }}</td></tr><tr><th>片尾</th><td>{{ b.outro }}</td></tr></table>

<h3>Shorts 與長片</h3>
<div class="shorts"><a class="img" href="{{ b.code }}/shorts.jpg"><img src="{{ b.code }}/shorts.jpg" alt="Shorts" loading="lazy"></a><p>{{ b.shorts_vs_long }}</p></div>

<h3>頻道 icon、banner、片尾</h3>
<div class="grid2"><a class="img" href="{{ b.code }}/banner.jpg"><img src="{{ b.code }}/banner.jpg" alt="banner" loading="lazy"></a>
<a class="img" href="{{ b.code }}/endcard.jpg"><img src="{{ b.code }}/endcard.jpg" alt="end card" loading="lazy"></a></div>
<p class="sub">Icon：{{ b.icon }}　Banner：{{ b.banner }}</p>

<div class="verdict" role="group" aria-label="判定">
<button data-v="採用">採用</button><button data-v="要修改">要修改</button><button class="no" data-v="不採用">不採用</button></div>
<textarea placeholder="意見（選填）"></textarea>
</section>{% endfor %}

<pre id="out"></pre>
<div id="summary"><button type="button" id="copy">複製我的選擇</button></div>
</main>
<script>
const KEY = 'channel-brands-v1';
const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } };
const save = s => { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* private mode: page still works */ } };
const state = load();
document.querySelectorAll('section[data-code]').forEach(sec => {
  const code = sec.dataset.code, s = state[code] || (state[code] = {});
  if (s.name) sec.querySelectorAll('input[type=radio]').forEach(r => { r.checked = r.value === s.name; });
  sec.querySelectorAll('input[type=radio]').forEach(r => r.addEventListener('change', () => { s.name = r.value; save(state); }));
  const buttons = sec.querySelectorAll('.verdict button');
  const paint = () => buttons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.v === s.verdict)));
  buttons.forEach(b => b.addEventListener('click', () => { s.verdict = b.dataset.v; save(state); paint(); }));
  paint();
  const ta = sec.querySelector('textarea'); ta.value = s.note || '';
  ta.addEventListener('input', () => { s.note = ta.value; save(state); });
});
document.getElementById('copy').addEventListener('click', () => {
  const lines = [...document.querySelectorAll('section[data-code]')].map(sec => {
    const code = sec.dataset.code, s = state[code] || {};
    const name = s.name || sec.querySelector('input[type=radio]:checked')?.value || '';
    return `${code}: 名稱=${name}｜${s.verdict || '未判定'}${s.note ? '｜' + s.note : ''}`;
  });
  const text = lines.join('\n'), out = document.getElementById('out');
  out.textContent = text; out.style.display = 'block';
  navigator.clipboard?.writeText(text).catch(() => {});
});
</script>
</body></html>"""


def main() -> int:
    proposals = json.loads((OUT / "proposals.json").read_text(encoding="utf-8"))
    measurements = json.loads((OUT / "measurements.json").read_text(encoding="utf-8"))
    missing = [b["code"] for b in proposals["brands"] if b["code"] not in measurements]
    if missing:
        print(f"render first, no measurements for: {missing}", file=sys.stderr)
        return 1
    env = Environment(autoescape=select_autoescape(default=True))
    html = env.from_string(TEMPLATE).render(studio=proposals["studio"], brands=proposals["brands"],
                                            measurements=measurements)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(OUT / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
