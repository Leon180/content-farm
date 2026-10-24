"""Wall-clock ledger of one run: what the machine did, what it waited for, what people kept it waiting for.

Everything is derived from files a run already leaves behind, so old runs can be back-filled with
the same code the new runs use:

- ``production.log.jsonl``: a step's ``seconds`` (``at`` is its end); ``outcome`` events mark the moment the
  runner stopped and handed the run to a person; ``gate``/``verdict`` events are the decisions;
- ``review/**/scorecard.json``: one review round (``at`` is its end, ``seconds`` its wall clock);
- ``review/producers/producers.jsonl``: one producer-agent call (``at`` end, ``seconds``);
- ``timing.events.jsonl`` (new runs): queue waits and run start/stop, written by the runner;
- the machine-wide queue's ``history.jsonl`` (back-fill of queue waits for old runs).

Two clocks (Leon 2026-10-23): *machine time* is the union of every span where the run was doing work
(cloud and local lanes overlap in parallel runs, so it is a union, not a sum); *wait time* is the rest of
the wall clock, split into queue (the run waited for the machine), decision (the runner had stopped for a
person), away (a gap of three hours or more: night, sleep) and unattributed.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENTS_FILE = "timing.events.jsonl"
TIMING_FILE = "timing.json"
LOG_FILE = "production.log.jsonl"
PRODUCERS_FILE = "review/producers/producers.jsonl"

CLOUD_STEPS = frozenset({"topic", "article", "deck", "thumbnail_spec", "skit_script", "news_script", "fable_script"})
MIN_GAP_S = 30.0          # shorter gaps between spans are bookkeeping, not waiting
AWAY_S = 3 * 3600.0       # a gap this long is night or sleep: reported, never counted as waiting for a decision
MAX_QUEUE_LOOKBACK = 6 * 3600.0


@dataclass(frozen=True)
class Span:
    lane: str                 # cloud | local
    kind: str                 # step | round | producer | queue
    name: str
    start: float              # epoch seconds
    end: float
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def seconds(self) -> float:
        return max(self.end - self.start, 0.0)


def _epoch(text: str) -> float:
    return datetime.fromisoformat(text).astimezone(timezone.utc).timestamp()


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def record_event(run_dir: Path, **fields: Any) -> None:
    """Append one runtime event (queue wait, run start/stop) to ``timing.events.jsonl``."""
    run_dir.mkdir(parents=True, exist_ok=True)
    row = {"at": iso(datetime.now(timezone.utc).timestamp()), **fields}
    with (run_dir / EVENTS_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _step_spans(run_dir: Path) -> list[Span]:
    spans = []
    for row in _jsonl(run_dir / LOG_FILE):
        seconds = row.get("seconds")
        if "step" not in row or seconds is None or row.get("exit_code") is None or not row.get("at"):
            continue
        name = str(row["step"])
        lane = row.get("lane") or ("cloud" if name in CLOUD_STEPS or name.startswith("gate_") else "local")
        end = _epoch(row["at"])
        spans.append(Span(lane, "step", name, end - float(seconds), end, {"exit_code": row["exit_code"]}))
    return spans


def _round_spans(run_dir: Path) -> list[Span]:
    spans = []
    for path in sorted((run_dir / "review").glob("**/scorecard.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        end = _epoch(card["at"])
        seats = card.get("seats", [])
        live = [s for s in seats if not s.get("cached") and not s.get("carried_from")]
        verdict = card.get("verdict") or {}
        label = str(path.parent.relative_to(run_dir / "review"))
        spans.append(Span("cloud", "round", label, end - float(card.get("seconds") or 0), end, {
            "stage": card.get("stage"), "round": card.get("round"), "pass": verdict.get("pass"),
            "seats": len(seats), "live_seats": len(live), "reviewer_seconds": card.get("reviewer_seconds"),
            "cost_usd": card.get("cost_usd"), "peak_parallel": card.get("peak_parallel"),
            "parallel_cap": card.get("parallel_cap"), "arbitration_seconds": card.get("arbitration_seconds")}))
    return spans


def _producer_end(run_dir: Path, row: dict[str, Any]) -> float | None:
    """When the call finished: its ``at``, or (producers.jsonl lines before 2026-10-20 had none) the time its
    last raw answer file was written."""
    if row.get("at"):
        return _epoch(row["at"])
    raw = sorted((run_dir / "review" / "producers").glob(f"{row.get('rid')}.attempt*.json"))
    return max(p.stat().st_mtime for p in raw) if raw else None


def _producer_spans(run_dir: Path) -> list[Span]:
    spans, seen = [], defaultdict(int)
    for row in _jsonl(run_dir / PRODUCERS_FILE):
        step = str(row.get("step"))
        seen[step] += 1
        end = _producer_end(run_dir, row)
        if end is None:
            continue
        tokens = row.get("tokens") or {}
        spans.append(Span("cloud", "producer", str(row.get("rid", step)), end - float(row.get("seconds") or 0), end, {
            "step": step, "nth": seen[step], "rework": seen[step] > 1, "ok": row.get("ok"),
            "model": row.get("model"), "effort": row.get("effort"), "cost_usd": row.get("cost_usd"),
            "output_tokens": tokens.get("output"), "thinking_tokens": row.get("thinking_tokens"),
            "turns": row.get("turns")}))
    return spans


def _queue_spans(run_dir: Path, channel: str, queue_history: Path | None) -> list[Span]:
    spans = [Span("local", "queue", str(r.get("step", "?")), _epoch(r["at"]) - float(r["waited_s"]), _epoch(r["at"]),
                  {"reason": r.get("reason", "")})
             for r in _jsonl(run_dir / EVENTS_FILE) if r.get("event") == "queue" and float(r.get("waited_s") or 0) >= 1]
    if spans or queue_history is None:     # new runs record their own waits; old ones are back-filled from the queue log
        return spans
    prefix = f"{channel}/{run_dir.name}:"
    for row in _jsonl(queue_history):
        waited = float(row.get("seconds") or 0)
        if row.get("event") == "start" and str(row.get("job", "")).startswith(prefix) and waited >= 1:
            end = _epoch(row["at"])
            spans.append(Span("local", "queue", str(row["job"])[len(prefix):], end - waited, end, {"source": "queue-history"}))
    return spans


def _stops(run_dir: Path) -> list[tuple[float, str]]:
    """Moments the runner handed the run to a person (a gate, a missing agent file, a failure)."""
    stops = [(_epoch(r["at"]), f"{r.get('step')}:{r['outcome']}") for r in _jsonl(run_dir / LOG_FILE) if r.get("outcome")]
    stops += [(_epoch(r["at"]), f"{r.get('step')}:budget_stop") for r in _jsonl(run_dir / LOG_FILE) if r.get("budget_stop")]
    stops += [(_epoch(r["at"]), f"run_end:{r.get('outcome')}") for r in _jsonl(run_dir / EVENTS_FILE)
              if r.get("event") == "run_end" and r.get("outcome") != "complete"]
    return sorted(stops)


def union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(i for i in intervals if i[1] > i[0]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _overlap(window: tuple[float, float], blocks: list[tuple[float, float]]) -> float:
    return sum(max(min(window[1], b[1]) - max(window[0], b[0]), 0.0) for b in blocks)


def classify_gaps(busy: list[tuple[float, float]], queue: list[tuple[float, float]],
                  stops: list[tuple[float, str]]) -> list[dict[str, Any]]:
    """Every gap between busy blocks, split into queue / decision / away / unattributed seconds."""
    gaps = []
    for (_, left_end), (right_start, _) in zip(busy, busy[1:]):
        length = right_start - left_end
        if length < MIN_GAP_S:
            continue
        queued = min(_overlap((left_end, right_start), queue), length)
        rest = length - queued
        stop = next((label for at, label in stops if left_end - 60 <= at <= right_start), "")
        if rest >= AWAY_S:
            kind = "away"
        elif stop:
            kind = "decision"
        else:
            kind = "unattributed"
        gaps.append({"start": iso(left_end), "end": iso(right_start), "seconds": round(length, 1),
                     "queue_s": round(queued, 1), "kind": kind, "after": stop, "rest_s": round(rest, 1)})
    return gaps


def rework_rows(spans: list[Span]) -> list[dict[str, Any]]:
    """Each producer re-run, with the round that sent the work back (the last failed round before it)."""
    failed = sorted((s for s in spans if s.kind == "round" and s.detail.get("pass") is False), key=lambda s: s.end)
    rows = []
    for span in (s for s in spans if s.kind == "producer" and s.detail.get("rework")):
        cause = next((f for f in reversed(failed) if f.end <= span.start + 5), None)
        rows.append({"producer": span.name, "seconds": round(span.seconds, 1), "cost_usd": span.detail.get("cost_usd"),
                     "caused_by": cause.name if cause else "", "start": iso(span.start)})
    return rows


def category(span: Span) -> str:
    if span.kind == "producer":
        return f"producer:{span.detail['step']}:{'rework' if span.detail['rework'] else 'first'}"
    if span.kind == "round":
        return f"round:{span.detail.get('stage')}"
    return f"{span.kind}:{span.name}"


def step_split(spans: list[Span]) -> list[dict[str, Any]]:
    """Per local step: seconds spent queued for the machine vs. seconds actually executing (Leon 2026-10-23,
    so a slow run shows whether it was slow work or waiting behind another video)."""
    rows: dict[str, dict[str, float]] = defaultdict(lambda: {"runs": 0, "execute_s": 0.0, "queue_s": 0.0, "queued_runs": 0})
    for span in spans:
        if span.kind == "step" and span.lane == "local":
            rows[span.name]["runs"] += 1
            rows[span.name]["execute_s"] += span.seconds
        elif span.kind == "queue":
            name = span.name.rsplit(":", 1)[-1]
            rows[name]["queue_s"] += span.seconds
            rows[name]["queued_runs"] += 1
    return sorted(({"step": name, "runs": int(v["runs"]), "execute_s": round(v["execute_s"], 1),
                    "queue_s": round(v["queue_s"], 1), "queued_runs": int(v["queued_runs"]),
                    "queue_share": round(v["queue_s"] / (v["queue_s"] + v["execute_s"]), 3)
                    if v["queue_s"] + v["execute_s"] else 0.0}
                   for name, v in rows.items()), key=lambda r: -(r["execute_s"] + r["queue_s"]))


def build(run_dir: Path, *, channel: str = "", queue_history: Path | None = None,
          since: str = "", until: str = "") -> dict[str, Any]:
    """The whole ledger of one run-dir as a JSON-ready dict. ``since``/``until`` (ISO) keep only the spans
    inside that window: a run-dir can hold older attempts (a design iteration) that are not this video's cost."""
    low = _epoch(since) if since else float("-inf")
    high = _epoch(until) if until else float("inf")
    spans = sorted([s for s in [*_step_spans(run_dir), *_round_spans(run_dir), *_producer_spans(run_dir),
                                *_queue_spans(run_dir, channel, queue_history)] if s.end > low and s.start < high],
                   key=lambda s: (s.start, s.end))
    work = [s for s in spans if s.kind != "queue" and s.seconds >= 1.0]
    queue = [s for s in spans if s.kind == "queue"]
    busy = union([(s.start, s.end) for s in work])
    gaps = classify_gaps(busy, union([(s.start, s.end) for s in queue]), _stops(run_dir))
    lanes = {lane: round(sum(e - b for b, e in union([(s.start, s.end) for s in work if s.lane == lane])), 1)
             for lane in ("cloud", "local")}
    by_cat: dict[str, dict[str, float]] = defaultdict(lambda: {"seconds": 0.0, "count": 0})
    for span in work:
        by_cat[category(span)]["seconds"] += span.seconds
        by_cat[category(span)]["count"] += 1
    machine = sum(e - b for b, e in busy)
    wait = {kind: round(sum(g["rest_s"] for g in gaps if g["kind"] == kind), 1)
            for kind in ("decision", "away", "unattributed")}
    wall = (max(s.end for s in spans) - min(s.start for s in spans)) if spans else 0.0
    return {
        "run": run_dir.name, "channel": channel, "generated_at": iso(datetime.now(timezone.utc).timestamp()),
        "first_start": iso(min(s.start for s in spans)) if spans else "", "wall_s": round(wall, 1),
        "machine_s": round(machine, 1), "lane_s": lanes,
        "queue_s": round(sum(g["queue_s"] for g in gaps) or sum(s.seconds for s in queue), 1),
        "wait_s": wait, "gaps": gaps,
        "categories": sorted(({"category": k, "seconds": round(v["seconds"], 1), "count": int(v["count"]),
                               "share_of_machine": round(v["seconds"] / machine, 3) if machine else 0.0}
                              for k, v in by_cat.items()), key=lambda c: -c["seconds"]),
        "rework": rework_rows(spans),
        "steps": step_split([s for s in spans if s.seconds >= 1.0 or s.kind == "queue"]),
        "spans": [{**asdict(s), "start": iso(s.start), "end": iso(s.end), "seconds": round(s.seconds, 1)} for s in spans],
    }


def write(run_dir: Path, *, channel: str = "", queue_history: Path | None = None,
          since: str = "", until: str = "") -> dict[str, Any]:
    data = build(run_dir, channel=channel, queue_history=queue_history, since=since, until=until)
    (run_dir / TIMING_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data
