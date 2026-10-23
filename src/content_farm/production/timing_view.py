"""Text views of ``timing.json``: one run's timeline (a text Gantt chart), its top bottlenecks, and a
side-by-side table of several runs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_farm.production import timing

BAR_SECONDS = 30      # one block per 30 s of a span (at least one)
BAR_MAX = 60


def fmt(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{secs:02d}s"


def _clock(epoch_iso: str) -> str:
    return datetime.fromisoformat(epoch_iso).astimezone(timezone.utc).strftime("%m-%d %H:%M")


def gantt(data: dict[str, Any]) -> str:
    """Chronological lines; every gap between work becomes a marker line saying what it was."""
    pending = sorted(data["gaps"], key=lambda g: g["end"])
    lines = [f"{data['run']}  wall {fmt(data['wall_s'])}  machine {fmt(data['machine_s'])}  "
             f"(cloud {fmt(data['lane_s']['cloud'])} / local {fmt(data['lane_s']['local'])})"]
    for span in data["spans"]:
        if span["seconds"] < 1.0 and span["kind"] != "queue":
            continue
        while pending and pending[0]["end"] <= span["start"]:
            gap = pending.pop(0)
            lines.append(f"{'':>11}  ··· {gap['kind']} {fmt(gap['seconds'])}"
                         + (f" (queue {fmt(gap['queue_s'])})" if gap["queue_s"] else "")
                         + (f" after {gap['after']}" if gap["after"] else ""))
        bar = "▇" * max(1, min(BAR_MAX, round(span["seconds"] / BAR_SECONDS)))
        detail = span["detail"]
        mark = "✗" if detail.get("pass") is False else ("↺" if detail.get("rework") else " ")
        lines.append(f"{_clock(span['start']):>11}  {span['lane'][:5]:<5} {span['kind']:<8}{mark}"
                     f"{span['name'][:34]:<34} {fmt(span['seconds']):>7} {bar}")
    return "\n".join(lines)


def lanes_table(data: dict[str, Any]) -> str:
    """Local steps with queue wait and execution time side by side (``steps`` of timing.json)."""
    rows = data.get("steps") or []
    if not rows:
        return f"{data['run']}: no local steps"
    out = [f"{data['run']}: local steps, waiting for the machine vs. running",
           f"  {'step':<22}{'runs':>5}{'running':>10}{'queued':>10}{'queued%':>9}"]
    for row in rows:
        out.append(f"  {row['step'][:21]:<22}{row['runs']:>5}{fmt(row['execute_s']):>10}{fmt(row['queue_s']):>10}"
                   f"{row['queue_share']:>9.0%}")
    total_queue = sum(r["queue_s"] for r in rows)
    total_run = sum(r["execute_s"] for r in rows)
    out.append(f"  {'total':<22}{sum(r['runs'] for r in rows):>5}{fmt(total_run):>10}{fmt(total_queue):>10}"
               f"{(total_queue / (total_queue + total_run) if total_queue + total_run else 0):>9.0%}")
    return "\n".join(out)


def bottlenecks(data: dict[str, Any], top: int = 5) -> str:
    rows = [("machine", c["category"], c["seconds"], c["count"]) for c in data["categories"]]
    waits = [("wait", "queue (waiting for the machine)", data["queue_s"], 0),
             ("wait", "decision (runner stopped for a person)", data["wait_s"]["decision"], 0),
             ("wait", "unattributed gap", data["wait_s"]["unattributed"], 0),
             ("away", "away (≥3h: night, sleep)", data["wait_s"]["away"], 0)]
    ranked = sorted([r for r in (*rows, *waits) if r[2] > 0 and r[0] != "away"], key=lambda r: -r[2])[:top]
    machine = data["machine_s"] or 1.0
    out = [f"{data['run']}: top {top} (machine or wait; away excluded)"]
    for i, (kind, name, seconds, count) in enumerate(ranked, 1):
        share = f"{seconds / machine:>4.0%} of machine" if kind == "machine" else "wait"
        out.append(f"  {i}. {name:<46} {fmt(seconds):>7}  x{count or '-':<3} {share}")
    if data["wait_s"]["away"]:
        out.append(f"  (away, not ranked: {fmt(data['wait_s']['away'])})")
    rework = data["rework"]
    if rework:
        out.append(f"  rework: {len(rework)} producer re-runs, {fmt(sum(r['seconds'] for r in rework))} — "
                   + ", ".join(sorted({r['caused_by'] or '?' for r in rework}))[:150])
    return "\n".join(out)


def compare(items: list[dict[str, Any]]) -> str:
    header = f"{'run':<24}{'wall':>8}{'machine':>9}{'cloud':>8}{'local':>8}{'queue':>8}{'decide':>8}{'away':>8}{'rework':>14}  top bottleneck"
    lines = [header, "-" * len(header)]
    for d in items:
        top = d["categories"][0] if d["categories"] else {"category": "-", "seconds": 0}
        rework = d["rework"]
        lines.append(f"{d['run'][:23]:<24}{fmt(d['wall_s']):>8}{fmt(d['machine_s']):>9}{fmt(d['lane_s']['cloud']):>8}"
                     f"{fmt(d['lane_s']['local']):>8}{fmt(d['queue_s']):>8}{fmt(d['wait_s']['decision']):>8}"
                     f"{fmt(d['wait_s']['away']):>8}{len(rework):>3}x {fmt(sum(r['seconds'] for r in rework)):>8}  "
                     f"{top['category']} {fmt(top['seconds'])}")
    return "\n".join(lines)


def run_dirs_under(root: Path) -> list[Path]:
    """``root`` itself, or every child directory that holds a production log or a review folder."""
    def is_run(path: Path) -> bool:
        return (path / timing.LOG_FILE).is_file() or (path / "review").is_dir()
    if is_run(root):
        return [root]
    return sorted(child for child in root.iterdir() if child.is_dir() and is_run(child))
