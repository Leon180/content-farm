"""``review/scorecard.html``: every stage, every round — verdict, scores, who reviewed with which
model / effort, time and usage, the routed fix list, and a before / after diff of the reviewed text
(each round folder keeps its own copy of the material). Self-contained, all run text escaped."""

from __future__ import annotations

import difflib
import json
from html import escape
from pathlib import Path
from typing import Any

from content_farm.review.rounds import REVIEW_DIR

STAGE_TITLES = {"topic": "1 選題", "article": "2 研究與文章", "script": "3 腳本（舊：未拆段）",
                "script_structure": "3a 腳本結構", "script_facts": "3b 腳本事實", "title_thumb": "4 標題與縮圖",
                "media": "5 配音與素材", "final": "6 初剪與成片", "shorts_topic": "Shorts 選題",
                "shorts_script": "Shorts 腳本", "shorts_title": "Shorts 標題", "shorts_final": "Shorts 成片"}
DIFFABLE = ("script.txt", "article.md", "titles.txt", "candidates.txt")

_CSS = """:root{--bg:#f5f6f8;--fg:#16191f;--muted:#5d6573;--card:#fff;--line:#d9dde4;--ok:#1b7f3b;--bad:#b3261e;
--add:#e3f5e8;--del:#fbe4e2}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--fg:#e8eaed;--muted:#9aa3ae;--card:#1b1e23;--line:#2c313a;
--ok:#5cc983;--bad:#ff7b72;--add:#17331f;--del:#3a1d1b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,"PingFang TC",
"Noto Sans TC",sans-serif}main{max-width:1100px;margin:0 auto;padding:20px 16px 60px}h1{font-size:22px}
h2{font-size:18px;margin:32px 0 6px}h3{font-size:15px;margin:16px 0 4px}.card{background:var(--card);
border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}.ok{color:var(--ok);font-weight:600}
.bad{color:var(--bad);font-weight:600}.muted{color:var(--muted)}table{border-collapse:collapse;width:100%;font-size:13px}
td,th{border-bottom:1px solid var(--line);padding:5px 7px;text-align:left;vertical-align:top}.wrap{overflow-x:auto}
pre{white-space:pre-wrap;word-break:break-word;font-size:12px;margin:0}.add{background:var(--add)}.del{background:var(--del)}
details{margin:6px 0}summary{cursor:pointer}"""


def _rounds(stage_dir: Path) -> list[Path]:
    found = [p for p in stage_dir.glob("round-*") if (p / "scorecard.json").is_file()]
    return sorted(found, key=lambda p: (int(p.name.split("-")[1]), p.name))


def _table(head: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    h = "".join(f"<th>{escape(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in row) + "</tr>" for row in rows)
    return f"<div class='wrap'><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>"


def _scores(scores: dict[str, Any]) -> str:
    rows = [(k, json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in scores.items()
            if k not in ("ranking", "leave", "columns")]
    out = _table(("指標", "值"), rows)
    if scores.get("ranking"):
        out += _table(("題目", "觀眾", "專業", "綜合", "否決"),
                      [(r["id"], r["viewer"], r["pro"], r["score"], "是" if r["vetoed"] else "") for r in scores["ranking"]])
    if scores.get("columns"):
        out += _table(("客觀欄", "分數", "燈號"), [(k, v.get("score"), v.get("light")) for k, v in scores["columns"].items()])
    return out


def _issues(issues: list[dict[str, Any]]) -> str:
    rows = [((i.get("ref") or {}).get("target"), ",".join((i.get("ref") or {}).get("sentence_ids") or [])
             or (i.get("ref") or {}).get("t") or (i.get("ref") or {}).get("item") or "", i.get("caused_by"),
             i.get("severity"), i.get("problem"), i.get("fix"), i.get("who")) for i in issues]
    return _table(("對象", "位置", "造成的步驟", "嚴重度", "問題", "改法", "評審"), rows) if rows else "<p class='muted'>無</p>"


def _diff(before: Path, after: Path) -> str:
    a = before.read_text(encoding="utf-8").splitlines()
    b = after.read_text(encoding="utf-8").splitlines()
    lines = []
    for line in difflib.unified_diff(a, b, before.parent.name, after.parent.name, lineterm="", n=1):
        cls = "add" if line.startswith("+") and not line.startswith("+++") else \
            "del" if line.startswith("-") and not line.startswith("---") else ""
        lines.append(f"<span class='{cls}'>{escape(line)}</span>")
    return "<pre>" + "\n".join(lines) + "</pre>" if lines else "<p class='muted'>內容沒有變</p>"


def _round(card: dict[str, Any], previous: Path | None, current: Path) -> str:
    verdict = card["verdict"]
    status = "<span class='ok'>通過</span>" if verdict["pass"] else "<span class='bad'>未過</span>"
    reasons = "；".join(verdict.get("reasons", [])) or "—"
    seats = _table(("評審", "角色", "model · effort", "實際模型", "合格", "秒", "保留觀眾"),
                   [(s["rid"], s["role"], f"{s['model']} · {s['effort']}", ",".join(s.get("models_used") or []),
                     "✓" if s["ok"] else "✗ " + "; ".join(s.get("errors", []))[:80], s.get("seconds"),
                     "是" if s.get("holdout") else "") for s in card["seats"]])
    diffs = ""
    if previous is not None:
        for name in DIFFABLE:
            if (previous / name).is_file() and (current / name).is_file():
                diffs += f"<details><summary>前後對照：{escape(name)}（{escape(previous.name)} → {escape(current.name)}）</summary>"\
                         f"{_diff(previous / name, current / name)}</details>"
    dropped = verdict.get("dropped") or []
    return (f"<div class='card'><h3>{escape(card['label'])} · {status}</h3><p>{escape(reasons)}</p>"
            f"<p class='muted'>{card.get('at')} · 牆鐘 {card.get('seconds')} s · 評審合計 {card.get('reviewer_seconds')} s · "
            f"tokens {json.dumps(card.get('tokens'), ensure_ascii=False)} · 名目費用 ${card.get('cost_usd')}（訂閱）</p>"
            f"{_scores(verdict.get('scores', {}))}<details><summary>評審與模型（{len(card['seats'])}）</summary>{seats}</details>"
            f"<details open><summary>修改清單（{len(verdict.get('issues', []))}；不可驗證而剔除 {len(dropped)}）</summary>"
            f"{_issues(verdict.get('issues', []))}</details>{diffs}</div>")


def render(run_dir: Path, title: str) -> Path:
    root = run_dir / REVIEW_DIR
    sections, summary = [], []
    for stage in STAGE_TITLES:
        rounds = _rounds(root / stage)
        if not rounds:
            continue
        cards = [json.loads((p / "scorecard.json").read_text(encoding="utf-8")) for p in rounds]
        regular = [c for c in cards if not c.get("holdout_only")]
        last = regular[-1] if regular else cards[-1]
        summary.append((STAGE_TITLES[stage], len(regular), "通過" if last["verdict"]["pass"] else "未過",
                        round(sum(c.get("seconds") or 0 for c in cards) / 60, 1), sum(len(c["seats"]) for c in cards)))
        body, previous = "", None
        for path, card in zip(rounds, cards):
            body += _round(card, previous, path)
            if not card.get("holdout_only"):
                previous = path
        sections.append(f"<h2>{escape(STAGE_TITLES[stage])}</h2>{body}")
    page = (f"<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>評分卡</title><style>{_CSS}</style></head><body><main>"
            f"<h1>{escape(title)} · 評分卡</h1><p class='muted'>{escape(str(run_dir))}</p>"
            + _table(("階段", "輪數", "結果", "分鐘", "評審次數"), summary) + "".join(sections) + "</main></body></html>")
    out = root / "scorecard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
