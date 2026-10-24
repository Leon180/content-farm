"""The radar as input to the topic stage: a compact brief for the topic producer agent.

The producer cannot read ``output/`` (producers.py limits its read access), so the radar file is copied
into the run-dir as ``topics/radar.json`` and the numbers are also written into the prompt.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from content_farm.topic_radar.store import default_root, latest_for

MAX_CANDIDATES = 12


def _line(candidate: dict) -> str:
    evidence = "；".join(f"{e['metric']} {e['value']:g} <{e['url']}>" for e in candidate["evidence"][:3])
    rivals = "、".join(f"{c['views']:,}" for c in candidate.get("competitors", [])[:5])
    asks = "；".join(f"「{q['text']}」" for q in candidate.get("viewer_questions", [])[:2])
    parts = [f"- {candidate['id']} 《{candidate['title_draft']}》建議 {candidate['format']}，提示分 {candidate['score']}",
             f"  需求證據：{evidence or '（無）'}"]
    if rivals:
        parts.append(f"  競爭影片前 5 名觀看數：{rivals}")
    if asks:
        parts.append(f"  觀眾在問：{asks}")
    return "\n".join(parts)


def radar_brief(run_dir: Path, channel: str, today: date | None = None, root: Path | None = None) -> str:
    """Copy today's (or the newest, <= 7 days old) radar file into ``run_dir/topics/radar.json`` and return the
    prompt section; an empty string when the channel has no recent radar (the topic stage then works as before)."""
    path = latest_for(root or default_root(), channel, today or date.today())
    if path is None:
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    target = run_dir / "topics" / "radar.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [_line(c) for c in data["candidates"][:MAX_CANDIDATES]]
    return ("選題雷達（{date}，topics/radar.json 有完整內容）：以下是用官方公開來源整理的候選與需求證據。\n"
            "請把適合頻道、且能查到一手來源的雷達候選放進 candidates.json，沿用 id 當 radar_id，並把它的 evidence、competitors、"
            "viewer_questions 原樣複製進該題（數字與網址不可自編、不可改寫）；標題為外文原題的要改寫成繁中標題。"
            "不合適的雷達候選可以不用，雷達以外你自己找的題目照舊可以加；每題仍要有 sources。\n{body}"
            ).format(date=data["date"], body="\n".join(lines))
