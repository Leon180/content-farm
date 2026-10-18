"""Run one review round of one stage: materials → roster → parallel ``claude -p`` reviewers →
verdict → ``review/<stage>/round-N/scorecard.json``.

Anti-overfitting: every round re-words each persona and shuffles reviewer order; the holdout
viewer sits only in the last allowed round (or a holdout addendum after an early pass) and never
feeds the verdict or fixes.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_farm.evaluation.panel import load_panels, persona_set, word_persona
from content_farm.production.state import fingerprint
from content_farm.review import materials as mat
from content_farm.review import prompts, verdicts
from content_farm.review.client import Call, CallResult, run_call
from content_farm.review.config import ReviewConfig, Stage, sentence_id_field
from content_farm.review.schemas import schema_for

REVIEW_DIR = Path("review")
VIDEO_STAGES = ("final", "shorts_final")
TITLE_STAGES = ("title_thumb", "shorts_title")


@dataclass(frozen=True)
class Member:
    rid: str
    role: str
    kind: str
    holdout: bool
    model: str
    effort: str
    persona: str = ""


def reviewer_parallel(wanted: int, cap: int) -> int:
    """claude -p reviewers at once: what free memory allows (≈0.6 GB each, 6 GB margin), ≤ cap, ≥ 1
    (the step itself already passed admission, so one always fits)."""
    from content_farm.lanes import resources as res

    try:
        allowed = res.reviewer_parallelism(res.probe_machine(), res.load_config(), wanted)
    except (OSError, ValueError):
        allowed = cap
    return max(1, min(cap, allowed, wanted or 1))


def stage_dir(run_dir: Path, stage: str) -> Path:
    return run_dir / REVIEW_DIR / stage


def rounds_of(run_dir: Path, stage: str) -> list[Path]:
    found = [p for p in stage_dir(run_dir, stage).glob("round-*") if (p / "scorecard.json").is_file()]
    return sorted(found, key=lambda p: (int(p.name.split("-")[1]), p.name))


def roster(config: ReviewConfig, stage_name: str, channel: str, round_no: int, *, with_holdout: bool,
           holdout_only: bool = False) -> list[Member]:
    stage = config.stages[stage_name]
    panels = load_panels()
    people = persona_set(panels, channel)
    regular_people = [p for p in people if not p.holdout]
    held_people = [p for p in people if p.holdout]
    members: list[Member] = []
    for seat in stage.seats:
        role = config.roles[seat.role]
        if role.kind != "viewer":
            if not holdout_only:
                members += [Member(f"{seat.role}-{n}", seat.role, role.kind, False, seat.model, seat.effort)
                            for n in range(1, seat.count + 1)]
            continue
        if not holdout_only:
            for n in range(seat.count - seat.holdout):
                person = regular_people[n % len(regular_people)]
                suffix = f"-{n // len(regular_people) + 1}" if n >= len(regular_people) else ""
                members.append(Member(f"viewer-{person.id}{suffix}", "viewer", "viewer", False, seat.model, seat.effort,
                                      word_persona(panels, person, round_no)))
        if with_holdout or holdout_only:
            members += [Member(f"viewer-{p.id}", "viewer", "viewer", True, seat.model, seat.effort,
                               word_persona(panels, p, round_no)) for p in held_people[: seat.holdout]]
    random.Random(f"order:{stage_name}:{round_no}").shuffle(members)
    return members


def _build_materials(run_dir: Path, out: Path, stage: str, vertical: bool) -> mat.Materials:
    if stage in VIDEO_STAGES:
        from content_farm.review.materials_video import final

        return final(run_dir, out, vertical=vertical)
    return mat.BUILDERS[stage](run_dir, out, id_field=sentence_id_field())


def _feeds(run_dir: Path, out: Path, member: Member, channel_name: str, competitors: Path | None) -> tuple[list[str], dict]:
    from content_farm.review.materials_video import best_title, homepage_feeds, variant_images

    return homepage_feeds(out, member.rid, variant_images(run_dir), best_title(run_dir), channel_name, competitors)


def run_round(run_dir: Path, *, stage_name: str, config: ReviewConfig, channel: str, channel_name: str,
              round_no: int, with_holdout: bool, holdout_only: bool = False, competitors: Path | None = None,
              client: Callable[[Call], CallResult] | None = None, vertical: bool = False,
              judge_context: dict[str, Any] | None = None, suffix: str = "") -> dict[str, Any]:
    """``suffix``: a side round (e.g. ``-opus`` comparison) that never counts for the gate."""
    stage = config.stages[stage_name]
    name = f"round-{round_no}" + ("-holdout" if holdout_only else "") + suffix
    out = stage_dir(run_dir, stage_name) / name
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    materials = _build_materials(run_dir, out, stage_name, vertical)
    members = roster(config, stage_name, channel, round_no, with_holdout=with_holdout, holdout_only=holdout_only)
    keys: dict[str, dict] = {}
    calls = []
    for member in members:
        feeds: list[str] = []
        if member.kind == "viewer" and stage_name in TITLE_STAGES:
            feeds, member_keys = _feeds(run_dir, out, member, channel_name, competitors)
            keys.update(member_keys)
        text = prompts.build(stage_name, config.roles[member.role], materials, channel=channel_name,
                             persona=member.persona, feeds=feeds)
        (out / "prompts").mkdir(exist_ok=True)
        (out / "prompts" / f"{member.rid}.md").write_text(text, encoding="utf-8")
        calls.append(Call(member.rid, text, schema_for(stage_name, member.kind), member.model, member.effort,
                          tools=config.roles[member.role].tools, cwd=out, timeout_s=config.defaults.timeout_s,
                          retries=config.defaults.schema_retries))
    invoke = client or (lambda call: run_call(call, log_dir=out / "raw"))
    parallel = reviewer_parallel(len(calls), config.defaults.max_parallel)
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        results = list(pool.map(invoke, calls))
    (out / "results").mkdir(exist_ok=True)
    for result in results:
        if result.output is not None:
            (out / "results" / f"{result.rid}.json").write_text(
                json.dumps(result.output, ensure_ascii=False, indent=1), encoding="utf-8")
    seats = [verdicts.Seat(m.rid, m.role, m.kind, m.holdout, r.ok, r.output) for m, r in zip(members, results)]
    context = {"corpus": materials.corpus, "sentences": materials.sentences, "duration": materials.duration,
               **materials.extra, **(judge_context or {}), "keys": keys}
    context["items"] = list(context.get("candidate_ids", [])) + list(context.get("title_ids", [])) \
        + list(context.get("variants", []))
    verdict = verdicts.JUDGES[stage_name](stage, seats, **context)
    card = {
        "stage": stage_name, "round": round_no, "label": name, "holdout_only": holdout_only,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": fingerprint(run_dir, stage.reviews), "max_rounds": stage.max_rounds,
        "seats": [{**{"role": m.role, "kind": m.kind, "holdout": m.holdout}, **r.to_json()}
                  for m, r in zip(members, results)],
        "verdict": verdict.to_json(), "seconds": round(time.monotonic() - started, 1),
        "reviewer_seconds": round(sum(r.seconds for r in results), 1),
        "cost_usd": round(sum(r.cost_usd for r in results), 4),
        "tokens": {k: sum(r.tokens.get(k, 0) for r in results) for k in ("input", "output", "cache_read", "cache_write")},
    }
    (out / "scorecard.json").write_text(json.dumps(card, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return card


def expected_seats(stage: Stage, config: ReviewConfig, *, with_holdout: bool) -> dict[str, tuple[int, str, str]]:
    """role → (count, model, effort) the scorecard must show (holdouts counted when present)."""
    out = {}
    for seat in stage.seats:
        count = seat.count if with_holdout else seat.count - seat.holdout
        prev = out.get(seat.role, (0, seat.model, seat.effort))
        out[seat.role] = (prev[0] + count, seat.model, seat.effort)
    return out
