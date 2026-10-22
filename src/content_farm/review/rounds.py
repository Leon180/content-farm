"""Run one review round of one stage: materials → roster → parallel ``claude -p`` reviewers →
verdict → ``review/<stage>/round-N/scorecard.json``.

Anti-overfitting: every round re-words each persona and shuffles reviewer order; the holdout
viewer sits only in the last allowed round (or a holdout addendum after an early pass) and never
feeds the verdict or fixes.
"""

from __future__ import annotations

import json
import os
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
from content_farm.review import cache as seat_cache
from content_farm.review import materials as mat
from content_farm.review import prompts, verdicts
from content_farm.review.client import Call, CallResult, call_usage, run_call
from content_farm.review.config import THRESHOLD_NOTE, ReviewConfig, Stage, sentence_id_field
from content_farm.review.schemas import schema_for
from content_farm.review.snapshot import snapshot_reviewed

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


def write_result(round_dir: Path, result: CallResult) -> Path:
    """``results/<rid>.json``: the seat's answer plus ``_usage`` (the CLI's token / cost report). A seat
    without a valid answer still gets a file (``_failed``, ``_errors``) so its usage is never lost."""
    body = dict(result.output) if result.output is not None else {"_failed": True, "_errors": list(result.errors)}
    path = round_dir / "results" / f"{result.rid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**body, "_usage": call_usage(result.to_json())}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


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


def _build_materials(run_dir: Path, out: Path, stage: str, vertical: bool,
                     only: frozenset[str] | None = None) -> mat.Materials:
    if stage in VIDEO_STAGES:
        from content_farm.review.materials_video import final

        return final(run_dir, out, vertical=vertical)
    extra = {"only": only} if only is not None else {}
    return mat.BUILDERS[stage](run_dir, out, id_field=sentence_id_field(), **extra)


def _within(seat: verdicts.Seat, only: frozenset[str]) -> verdicts.Seat:
    """A fact-checker's answer restricted to the sentences under review (delta fact-check)."""
    if seat.kind != "fact" or not seat.ok or seat.output is None:
        return seat

    def hits(item: dict[str, Any]) -> bool:
        ids = item.get("sentence_ids") or (item.get("ref") or {}).get("sentence_ids") or []
        return bool(set(map(str, ids)) & only)

    output = {**seat.output, "claims": [c for c in seat.output.get("claims", []) if hits(c)],
              "issues": [i for i in seat.output.get("issues", []) if hits(i)]}
    return verdicts.Seat(seat.rid, seat.role, seat.kind, seat.holdout, seat.ok, output)


def _feeds(run_dir: Path, out: Path, member: Member, channel_name: str, competitors: Path | None) -> tuple[list[str], dict]:
    from content_farm.review.materials_video import best_title, homepage_feeds, variant_images

    return homepage_feeds(out, member.rid, variant_images(run_dir), best_title(run_dir), channel_name, competitors)


def _delta_view(run_dir: Path, out: Path, stage_name: str, vertical: bool, carry: Any) -> tuple[Path, mat.Materials] | None:
    """The ★-only view fact-checkers get in a carried round (own folder, so their cwd shows nothing else)."""
    if carry is None or not carry.prior_fact or not carry.delta:
        return None
    view = out / "delta"
    view.mkdir(exist_ok=True)
    return view, _build_materials(run_dir, view, stage_name, vertical, carry.delta)


def _kept_result(member: Member, prior: Any, label: str) -> CallResult:
    """A seat that keeps its answer from the earlier round: nothing is called, nothing is billed."""
    seat = prior.seat
    return CallResult(member.rid, True, prior.output, (), member.model, member.effort,
                      tuple(seat.get("models_used") or ()), 0.0, 0.0, {}, 0, carried_from=label,
                      saved_usd=float(seat.get("cost_usd") or 0))


def _merge_facts(run_dir: Path, stage_name: str, members: list[Member], results: list[CallResult],
                 carry: Any) -> list[CallResult]:
    """Fact-checkers of a carried round: new claims about the ★ sentences + earlier claims about the rest."""
    import dataclasses

    from content_farm.review import reuse
    from content_farm.review.article_diff import split_article

    if carry is None or not carry.prior_fact:
        return results
    article = split_article((run_dir / "article.md").read_text(encoding="utf-8")) if stage_name == "article" else None
    out = []
    for member, result in zip(members, results):
        prior = carry.prior_fact.get(member.rid)
        if prior is None or not result.ok or result.output is None:
            out.append(result)
            continue
        fresh = {} if result.carried_from else result.output
        if article is None and fresh:     # deck claims outside the ★ sentences are not this round's business
            ids = carry.delta or frozenset()
            fresh = {**fresh, **{k: [i for i in fresh.get(k, []) if not reuse.claim_ids(i) or set(reuse.claim_ids(i)) & ids]
                                  for k in ("claims", "issues")}}
        merged = reuse.merge_fact(prior.output, fresh, carry, new_article=article)
        out.append(dataclasses.replace(result, output=merged, carried_from=result.carried_from))
    return out


def run_round(run_dir: Path, *, stage_name: str, config: ReviewConfig, channel: str, channel_name: str,
              round_no: int, with_holdout: bool, holdout_only: bool = False, competitors: Path | None = None,
              client: Callable[[Call], CallResult] | None = None, vertical: bool = False,
              judge_context: dict[str, Any] | None = None, suffix: str = "",
              only_sentences: frozenset[str] | None = None, carry: Any = None) -> dict[str, Any]:
    """``suffix``: a side round (e.g. ``-opus`` comparison) that never counts for the gate.
    ``only_sentences``: a delta fact-check (``review.delta``) — reviewers see those sentences with
    their neighbours, and only claims about them are judged. ``carry``: a ``review.reuse.CarryPlan`` — seats that
    keep their earlier answer are not called, fact-checkers re-check only the changed sentences."""
    stage = config.stages[stage_name]
    name = f"round-{round_no}" + ("-holdout" if holdout_only else "") + suffix
    out = stage_dir(run_dir, stage_name) / name
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    snapshot_reviewed(run_dir, out, stage.reviews)
    materials = _build_materials(run_dir, out, stage_name, vertical, only_sentences)
    members = roster(config, stage_name, channel, round_no, with_holdout=with_holdout, holdout_only=holdout_only)
    delta_view = _delta_view(run_dir, out, stage_name, vertical, carry)
    kept: dict[str, CallResult] = {}
    for member in members:
        if carry is not None and member.rid in carry.carried:
            kept[member.rid] = _kept_result(member, carry.carried[member.rid], carry.previous)
        elif carry is not None and member.rid in carry.prior_fact and not carry.delta:
            kept[member.rid] = _kept_result(member, carry.prior_fact[member.rid], carry.previous)   # nothing to re-check
    keys: dict[str, dict] = {}
    calls, call_keys = [], {}
    for member in members:
        if member.rid in kept:
            continue
        feeds: list[str] = []
        if member.kind == "viewer" and stage_name in TITLE_STAGES:
            feeds, member_keys = _feeds(run_dir, out, member, channel_name, competitors)
            keys.update(member_keys)
        view_dir, view = delta_view if delta_view is not None and member.rid in carry.prior_fact else (out, materials)
        role = config.roles[member.role]
        text = prompts.build(stage_name, role, view, channel=channel_name, persona=member.persona, feeds=feeds)
        (out / "prompts").mkdir(exist_ok=True)
        (out / "prompts" / f"{member.rid}.md").write_text(text, encoding="utf-8")
        call = Call(member.rid, text, schema_for(stage_name, member.kind), member.model, member.effort,
                    tools=role.tools, cwd=view_dir, timeout_s=config.defaults.timeout_s,
                    retries=config.defaults.schema_retries)
        calls.append(call)
        if not feeds:       # a homepage viewer's feeds are shuffled per seat: never the same question twice
            call_keys[member.rid] = _seat_key(stage_name, call, member, role, view, view_dir, channel_name)
    live_invoke = client or (lambda call: run_call(call, log_dir=out / "raw"))
    invoke = _cached(run_dir, call_keys, live_invoke, out.name)
    parallel = reviewer_parallel(len(calls), config.defaults.max_parallel)
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        live = dict(zip((c.rid for c in calls), pool.map(invoke, calls)))
    results = _merge_facts(run_dir, stage_name, members, [kept.get(m.rid) or live[m.rid] for m in members], carry)
    (out / "results").mkdir(exist_ok=True)
    for result in results:
        write_result(out, result)
    if keys:   # homepage answer key: outside the round folder, which reviewers can read
        key_dir = run_dir / REVIEW_DIR / ".keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        (key_dir / f"{stage_name}-{name}.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    seats = [verdicts.Seat(m.rid, m.role, m.kind, m.holdout, r.ok, r.output) for m, r in zip(members, results)]
    if only_sentences is not None:
        seats = [_within(seat, only_sentences) for seat in seats]
    arbitration, arbiter = _arbitrate(run_dir, out, stage_name, stage, seats, invoke, config)
    if arbiter is not None:
        members, results = [*members, arbiter[0]], [*results, arbiter[1]]
    context = {"corpus": materials.corpus, "sentences": materials.sentences, "duration": materials.duration,
               **materials.extra, **(judge_context or {}), "keys": keys,
               **({"arbitration": arbitration} if arbitration is not None else {})}
    context["items"] = list(context.get("candidate_ids", [])) + list(context.get("title_ids", [])) \
        + list(context.get("variants", []))
    verdict = verdicts.JUDGES[stage_name](stage, seats, **context)
    card = {
        "stage": stage_name, "round": round_no, "label": name, "holdout_only": holdout_only,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": fingerprint(run_dir, stage.reviews), "max_rounds": stage.max_rounds,
        "tier_mode": config.tier_mode,
        "threshold": stage.threshold.model_dump(exclude_none=True),
        **({"threshold_note": THRESHOLD_NOTE} if stage.threshold.leave_median_pct is not None else {}),
        **({"only_sentences": sorted(only_sentences)} if only_sentences is not None else {}),
        **({"carry": carry.to_json()} if carry is not None else {}),
        "seats": [{**{"role": m.role, "kind": m.kind, "holdout": m.holdout}, **r.to_json()}
                  for m, r in zip(members, results)],
        "verdict": verdict.to_json(), "seconds": round(time.monotonic() - started, 1),
        "reviewer_seconds": round(sum(r.seconds for r in results), 1),
        "cost_usd": round(sum(r.cost_usd for r in results), 4),
        "cache": {"hits": sum(1 for r in results if r.cached), "saved_usd": round(sum(r.saved_usd for r in results), 4),
                  "carried": sum(1 for r in results if r.carried_from)},
        "tokens": {k: sum(r.tokens.get(k, 0) for r in results) for k in ("input", "output", "cache_read", "cache_write")},
    }
    (out / "scorecard.json").write_text(json.dumps(card, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return card


CACHE_ENV = "CF_REVIEW_CACHE"       # "0" turns the per-seat cache off (before / after comparisons)


def cache_enabled() -> bool:
    return os.environ.get(CACHE_ENV, "1").strip() != "0"


def _seat_key(stage_name: str, call: Call, member: Member, role: Any, materials: mat.Materials, out: Path,
              channel_name: str) -> str:
    """The cache key of one seat: its prompt with the persona wording neutralised (the per-round re-wording is
    anti-overfitting, not new information), the content of the files it is shown, model, effort, schema, tools."""
    neutral = prompts.build(stage_name, role, materials, channel=channel_name, persona=f"[{member.rid}]")
    view = materials.visible_to(role.kind)
    content = seat_cache.content_digest(out, view.files, derived=view.derived, override=view.content_key)
    return seat_cache.seat_key(stage=stage_name, rid=member.rid, prompt=neutral, schema=call.schema, tools=call.tools,
                               model=call.model, effort=call.effort, content=content)


def _cached(run_dir: Path, call_keys: dict[str, str], live: Callable[[Call], CallResult],
            label: str) -> Callable[[Call], CallResult]:
    """``live`` with the per-seat cache in front: a seat whose key was answered before gets that answer at no cost;
    a valid live answer is remembered. Calls without a key (and ``CF_REVIEW_CACHE=0``) always run."""
    def invoke(call: Call) -> CallResult:
        key = call_keys.get(call.rid)
        if key is None or not cache_enabled():
            return live(call)
        entry = seat_cache.load(run_dir, key)
        if entry is not None:
            was = entry.get("result") or {}
            return CallResult(call.rid, True, entry["output"], (), call.model, call.effort,
                              tuple(was.get("models_used") or ()), 0.0, 0.0, {}, 0, cached=True,
                              saved_usd=float(was.get("cost_usd") or 0))
        result = live(call)
        if result.ok and result.output is not None:
            seat_cache.save(run_dir, key, output=result.output, result=result.to_json(), label=label)
        return result
    return invoke


def _arbitrate(run_dir: Path, out: Path, stage_name: str, stage: Stage, seats: list[verdicts.Seat],
               invoke: Callable[[Call], CallResult], config: ReviewConfig,
               ) -> tuple[dict[str, Any] | None, tuple[Member, CallResult] | None]:
    """Two fact-checkers disagree → a third (``stage.arbiter``) rules. (None, None) when the stage is
    not arbitrated or a checker has no valid output (the round fails on that anyway)."""
    from content_farm.review import arbitration as arb
    from content_farm.review.article_diff import deck_narration, split_article
    from content_farm.review.config import ARBITRATED_STAGES

    checkers = [s for s in seats if s.kind == "fact" and not s.holdout]
    if stage_name not in ARBITRATED_STAGES or stage.arbiter is None or not all(s.ok for s in checkers):
        return None, None
    if stage_name == "article":
        article = (run_dir / "article.md").read_text(encoding="utf-8") if (run_dir / "article.md").is_file() else ""
        sentences, material = split_article(article), "文章（article.md，來源在 sources.json）"
    else:
        sentences = deck_narration(json.loads((run_dir / "deck.json").read_text(encoding="utf-8")))
        material = "講稿（script.txt 的句子 id，事實依據 article.md，來源在 sources.json）"
    found = arb.split({s.rid: s.output for s in checkers}, sentences)
    if not found["disputes"]:
        return {**found, "upheld": [], "unanswered": [], "ruled": False}, None
    member = Member(f"{arb.ARBITER_ROLE}-1", arb.ARBITER_ROLE, "fact", False, stage.arbiter.model, stage.arbiter.effort)
    text = arb.prompt(found["disputes"], material=material)
    (out / "prompts").mkdir(exist_ok=True)
    (out / "prompts" / f"{member.rid}.md").write_text(text, encoding="utf-8")
    tools = next(r.tools for r in config.roles.values() if r.kind == "fact")
    arbiter_call = Call(member.rid, text, arb.SCHEMA, member.model, member.effort, tools=tools, cwd=out,
                        timeout_s=config.defaults.timeout_s, retries=config.defaults.schema_retries)
    sources = run_dir / "sources.json"
    key = seat_cache.seat_key(stage=stage_name, rid=member.rid, prompt=text, schema=arb.SCHEMA, tools=tools,
                              model=member.model, effort=member.effort,
                              content=seat_cache.file_digest(sources) if sources.is_file() else "")
    result = _cached(run_dir, {member.rid: key}, invoke, out.name)(arbiter_call)
    write_result(out, result)
    upheld, unanswered = arb.upheld(result.output if result.ok else None, found["disputes"])
    return {**found, "upheld": upheld, "unanswered": unanswered, "ruled": result.ok,
            "arbiter_model": stage.arbiter.model, "arbiter_effort": stage.arbiter.effort}, (member, result)


def expected_seats(stage: Stage, config: ReviewConfig, *, with_holdout: bool) -> dict[str, tuple[int, str, str]]:
    """role → (count, model, effort) the scorecard must show (holdouts counted when present)."""
    out = {}
    for seat in stage.seats:
        count = seat.count if with_holdout else seat.count - seat.holdout
        prev = out.get(seat.role, (0, seat.model, seat.effort))
        out[seat.role] = (prev[0] + count, seat.model, seat.effort)
    return out
