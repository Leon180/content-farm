"""One self-contained HTML review page per gate (``review/<gate>.html``) and a
machine-readable decision item (``review/<gate>.decision.json``) that a panel
inbox can list without parsing HTML.

The page shows exactly what the gate's fingerprint covers, a short checklist
of what a human must judge, and the approve / reject commands to paste.
Everything from run files is HTML-escaped.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Callable
from html import escape
from pathlib import Path

from content_farm.production.channels import Channel, Gate

REVIEW_DIR = "review"

CHECKLISTS: dict[Gate, tuple[str, ...]] = {
    Gate.TOPIC: ("題目撐得起一支片、跟頻道合、沒重複、來源可查（通常由選題評審團核可）",),
    Gate.TITLE: ("標題縮圖不誇大、承諾在講稿前 60 秒兌現、縮到手機首頁讀得到（通常由評審團核可）",),
    Gate.ARTICLE: (
        "論點站得住；每個數字、八卦都有 sources.json 裡的來源",
        "艱深名詞先用國高中程度的比喻，再給精確定義",
        "沒有投資建議；沒有照抄現代譯注（神話頻道）",
    ),
    Gate.DECK: (
        "contact sheet 每張都讀得懂、沒有溢出",
        "講稿口語、節奏對；冷笑話不尷尬",
        "media 配比合理（stock＋AI 圖不連續缺席）",
    ),
    Gate.DECK_FACTS: ("講稿每個數字、日期、引述、因果都有 sources.json 的來源；推論標明是判斷（通常由事實段評審團核可）",),
    Gate.SCRIPT: ("笑點成立、不冒犯", "20–50 秒內講完"),
    Gate.MEDIA: (
        "每支 B-roll 整段看過：沒有可讀的公司名／logo、主題相關",
        "AI 圖沒有近似真人或官方角色；artwork 授權是 CC0／公共領域且可營利",
        "credits.json 的 pending 為空，或已決定接受佔位圖",
    ),
    Gate.FINAL: (
        "整片看一次：配音、字幕、畫面同步，角色不擋字",
        "QC 報告沒有 error；有 error 時 approve 要寫 --override 理由",
        "標題與縮圖之後在 upload/youtube_meta.json 再看一次",
    ),
}

_CSS = """
:root{--bg:#f6f7f9;--fg:#15181d;--muted:#5b6472;--card:#fff;--line:#d9dee5;--ok:#1b7f3b;
--warn:#a35b00;--err:#b3261e;--accent:#0b5cc2}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--fg:#e8eaed;--muted:#9aa3ae;--card:#1b1e23;
--line:#2c313a;--ok:#5cc983;--warn:#f0a440;--err:#ff7b72;--accent:#7cb4ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,"PingFang TC","Noto Sans TC",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}
.muted{color:var(--muted)}.card{background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:14px 16px;margin:12px 0}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid var(--line);
padding:6px 8px;text-align:left;vertical-align:top}img,video{max-width:100%;border-radius:8px}
pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);padding:10px;border-radius:8px;
font-size:13px}.ok{color:var(--ok)}.warn{color:var(--warn)}.error{color:var(--err);font-weight:600}
.cmd{display:flex;gap:8px;align-items:flex-start}.cmd pre{flex:1;margin:4px 0}
button{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:6px;
padding:6px 10px;cursor:pointer}ul{padding-left:20px}
"""

_COPY_JS = """document.querySelectorAll('button[data-copy]').forEach(b=>b.addEventListener('click',()=>{
const t=document.getElementById(b.dataset.copy).textContent;
navigator.clipboard.writeText(t).then(()=>{b.textContent='已複製';setTimeout(()=>b.textContent='複製',1500)})}))"""


def _read_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _image(run_dir: Path, rel: str, label: str) -> str:
    if not (run_dir / rel).is_file():
        return f'<p class="error">缺少 {escape(rel)}</p>'
    return f'<h2>{escape(label)}</h2><a href="../{escape(rel)}"><img src="../{escape(rel)}" alt="{escape(label)}"></a>'


def _article_section(run_dir: Path) -> str:
    article = (run_dir / "article.md").read_text(encoding="utf-8") if (run_dir / "article.md").is_file() else ""
    sources = _read_json(run_dir / "sources.json")
    items = sources.get("sources", sources) if isinstance(sources, dict) else (sources or [])
    rows = [(s.get("id", ""), s.get("title", ""), s.get("publisher", ""), s.get("url", ""))
            for s in items if isinstance(s, dict)]
    return (f"<h2>文章（{len(article)} 字）</h2><div class='card'><pre>{escape(article)}</pre></div>"
            f"<h2>來源（{len(rows)}）</h2>" + _table(("id", "標題", "出處", "網址"), rows))


def _deck_section(run_dir: Path) -> str:
    deck = _read_json(run_dir / "deck.json") or {}
    rows = []
    for section in deck.get("sections", []):
        for slide in section.get("slides", []):
            media = (slide.get("media") or {}).get("kind", "slide")
            rows.append((slide.get("id"), slide.get("heading"), media,
                         ",".join(slide.get("source_ids", [])), slide.get("narration", "")))
    return (_image(run_dir, "slides/contact_sheet.png", "投影片 contact sheet")
            + f"<h2>講稿（{len(rows)} 張）</h2>" + _table(("id", "標題", "media", "來源", "旁白"), rows))


def _media_section(run_dir: Path) -> str:
    report = _read_json(run_dir / "media" / "media_report.json") or {}
    clips = report.get("slides", []) if isinstance(report, dict) else []
    rows = [(c.get("slide_id"), c.get("requested"), c.get("used"),
             "要看" if c.get("review") else "", c.get("note", "")) for c in clips if isinstance(c, dict)]
    credits = _read_json(run_dir / "credits.json") or {}
    entries = [(e.get("slide_id"), e.get("kind"), e.get("author", ""), e.get("license", ""),
                e.get("source_url", e.get("file", ""))) for e in credits.get("entries", [])]
    pending = [(p.get("slide_id"), p.get("kind"), p.get("reason", "")) for p in credits.get("pending", [])]
    pending_html = (f"<h2 class='error'>尚未補上的素材（{len(pending)}）</h2>"
                    + _table(("slide", "kind", "原因"), pending)) if pending else "<p class='ok'>沒有 pending 素材</p>"
    return (_image(run_dir, "media/contact_sheet.png", "media contact sheet（橘框＝B-roll 待確認，紅框＝佔位／退回）")
            + f"<h2>每張用了什麼（{len(rows)}）</h2>" + _table(("slide", "要求", "實際", "人工", "備註"), rows)
            + f"<h2>授權紀錄 credits.json（{len(entries)}）</h2>"
            + _table(("slide", "kind", "作者", "授權", "來源"), entries) + pending_html)


def _final_section(run_dir: Path) -> str:
    video = next((f"assembly/{n}" for n in ("release.mp4", "final.mp4", "draft.mp4") if (run_dir / "assembly" / n).is_file()), None)
    player = (f'<h2>成片 {escape(video)}</h2><video controls preload="metadata" src="../{escape(video)}"></video>'
              if video else "<p class='error'>沒有成片</p>")
    qc = _read_json(run_dir / "qc" / "qc_report.json") or {}
    rows = "".join(f"<tr><td>{escape(f['check'])}</td><td class='{escape(f['level'])}'>{escape(f['level'])}"
                   f"</td><td>{escape(f['message'])}</td></tr>" for f in qc.get("findings", []))
    summary = (f"<p class='{'error' if qc.get('errors') else 'ok'}'>QC：{qc.get('errors', '?')} error、"
               f"{qc.get('warnings', '?')} warning</p>")
    return "<h2>自動品質檢查</h2>" + summary + f"<table><tbody>{rows}</tbody></table>" + player


def _script_section(run_dir: Path) -> str:
    script = _read_json(run_dir / "script.json") or {}
    rows = [(s.get("scene_number"), s.get("narration", "")) for s in script.get("scenes", [])]
    return f"<h2>{escape(str(script.get('video_title', '')))}</h2>" + _table(("#", "旁白"), rows)


def _json_section(*names: str) -> Callable[[Path], str]:
    def section(run_dir: Path) -> str:
        parts = []
        for name in names:
            path = run_dir / name
            text = path.read_text(encoding="utf-8") if path.is_file() else "（缺）"
            parts.append(f"<h2>{escape(name)}</h2><pre>{escape(text)}</pre>")
        return "".join(parts)
    return section


SECTIONS = {Gate.TOPIC: _json_section("topics/candidates.json"),
            Gate.TITLE: _json_section("titles.json", "thumbnail_variants.json"),
            Gate.ARTICLE: _article_section, Gate.DECK: _deck_section, Gate.DECK_FACTS: _deck_section,
            Gate.MEDIA: _media_section,
            Gate.FINAL: _final_section, Gate.SCRIPT: _script_section}


def commands(run_dir: Path, gate: Gate) -> tuple[str, str]:
    base = f"python scripts/produce.py {{}} --run-dir {shlex.quote(str(run_dir))} --gate {gate.value}"
    return base.format("approve"), base.format("reject") + ' --note "要改什麼"'


def write_review(
    run_dir: Path, channel: Channel, gate: Gate, title: str, fingerprint: str, status: str = "pending",
) -> Path:
    approve, reject = commands(run_dir, gate)
    checklist = "".join(f"<li>{escape(item)}</li>" for item in CHECKLISTS[gate])
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(channel.name)} 審核</title>
<style>{_CSS}</style></head><body><main>
<p class="muted">{escape(channel.name)} · {escape(run_dir.name)} · 指紋 {escape(fingerprint)}</p>
<h1>人工閘門：{escape(title)}</h1>
<div class="card"><strong>要判斷的事</strong><ul>{checklist}</ul>
<div class="cmd"><pre id="ap">{escape(approve)}</pre><button data-copy="ap">複製</button></div>
<div class="cmd"><pre id="rj">{escape(reject)}</pre><button data-copy="rj">複製</button></div>
<p class="muted">核可綁定上面的指紋；之後若這些檔案被改動，runner 會再停在這裡。</p></div>
{SECTIONS[gate](run_dir)}
</main><script>{_COPY_JS}</script></body></html>"""
    out_dir = run_dir / REVIEW_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{gate.value}.html"
    path.write_text(page, encoding="utf-8")
    decision = {"version": 1, "kind": "production_gate", "channel": channel.code, "run_dir": str(run_dir),
                "gate": gate.value, "title": title, "fingerprint": fingerprint, "status": status,
                "review_page": str(path), "approve_cmd": approve, "reject_cmd": reject,
                "checklist": list(CHECKLISTS[gate])}
    (out_dir / f"{gate.value}.decision.json").write_text(json.dumps(decision, ensure_ascii=False, indent=2),
                                                        encoding="utf-8")
    return path
