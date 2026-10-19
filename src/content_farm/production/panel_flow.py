"""The runner's side of the review panels: which stage reviews a gate, what to do with the
panel's answer (record the approval, or mark the steps a fix list routes back to), and the
producer agents for agent steps when ``--auto-agents`` is on."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from content_farm.production.channels import Gate
from content_farm.production.state import Decision, RunState, StepRecord, fingerprint, now_iso

if TYPE_CHECKING:
    from content_farm.production.runner import RunResult
    from content_farm.production.steps import Context, Step

PRODUCER_STEPS = ("topic", "article", "deck", "thumbnail_spec")
APPROVED_DECK = "review/deck.approved.json"   # same path as feat/incremental-render's runner.APPROVED_DECK
LOCKED_DECK = "review/deck.locked.json"       # deck at the last structure / facts approval (the fact lock's baseline)
FACTS_LOCKED_DECK = "review/deck_facts.locked.json"   # deck at the last fact-stage approval (delta fact-check baseline)
SCRIPT_STAGES = ("script_structure", "script_facts")
EVENTS = "production.log.jsonl"


def _event(run_dir: Path, **fields: object) -> None:
    with (run_dir / EVENTS).open("a", encoding="utf-8") as log:
        log.write(json.dumps({"at": now_iso(), **fields}, ensure_ascii=False, default=str) + "\n")


def _short(ctx: Context) -> bool:
    from content_farm.production.shorts_cut import is_short_cut

    return ctx.channel.format.length == "short" or is_short_cut(ctx.run_dir)


def stage_of(ctx: Context, gate: Gate) -> str | None:
    if not ctx.options.panels:
        return None
    from content_farm.review.gate import stage_for_gate

    return stage_for_gate(gate.value, short=_short(ctx))


def review_config(ctx: Context):
    from content_farm.review.config import Tier, economy_requested, load_review

    tier = None
    if ctx.options.review_tier:
        model, effort = ctx.options.review_tier.split(":")
        tier = Tier(model=model, effort=effort)
    return load_review(ctx.channel.code, raise_tier=tier, economy=economy_requested(ctx.run_dir))


def competitors_for(ctx: Context) -> Path | None:
    if ctx.options.competitors is not None:
        return ctx.options.competitors
    guess = ctx.run_dir.parent / "eval-competitors" / ctx.channel.code
    return guess if (guess / "competitors.json").is_file() else None


def title_auto_checks(run_dir: Path, competitors: Path | None) -> dict[str, dict[str, list[str]]]:
    """Per variant, the automatic checks it fails: ``blocking`` (168 px glyph, contrast, subject share,
    blank blocks / broken image) and ``advisory`` (hue distance from the competitors — listed on the
    scorecard but gating only with ``threshold.hue_blocks``; Leon 31134b307b3e=A)."""
    from content_farm.evaluation.flow import thumbs_for
    from content_farm.evaluation.homepage import CONTRAST_MIN, HUE_DISTANCE_MIN, SMALL_GLYPH_MIN, SUBJECT_MIN

    failed: dict[str, list[str]] = {}
    advisory: dict[str, list[str]] = {}
    for key, m in thumbs_for(run_dir, competitors).items():
        out = []
        advisory[key] = ([f"與競品色相差 {m['hue_distance']}° < {HUE_DISTANCE_MIN:g}°"]
                         if m.get("hue_distance") is not None and m["hue_distance"] < HUE_DISTANCE_MIN else [])
        if (m.get("glyph_px_at_168") or 0) < SMALL_GLYPH_MIN:
            out.append(f"168px 字高 {m.get('glyph_px_at_168')} < {SMALL_GLYPH_MIN:g}")
        if (m.get("contrast") or 0) < CONTRAST_MIN:
            out.append(f"對比 {m.get('contrast')} < {CONTRAST_MIN}")
        if (m.get("subject_share") or 0) < SUBJECT_MIN:
            out.append(f"主體佔比 {m.get('subject_share')} < {SUBJECT_MIN}")
        blank = blank_share(run_dir / "thumbnails" / f"variant_{key.lower()}.jpg")
        if blank > 0.35:
            out.append(f"空白方塊 {blank:.0%}")
        failed[key] = out
    return {"blocking": failed, "advisory": advisory}


def blank_share(image_path: Path) -> float:
    """Share of 40 px tiles that are flat pure white / black (a missing image or empty box)."""
    import numpy as np
    from PIL import Image

    if not image_path.is_file():
        return 1.0
    with Image.open(image_path) as raw:
        pixels = np.asarray(raw.convert("L").resize((320, 180)), dtype=float)
    tiles = [pixels[y:y + 20, x:x + 20] for y in range(0, 180, 20) for x in range(0, 320, 20)]
    flat = [t for t in tiles if t.std() < 1.5 and (t.mean() > 250 or t.mean() < 5)]
    return round(len(flat) / len(tiles), 3)


def _judge_context(ctx: Context, stage: str, competitors: Path | None) -> Callable[[Path], dict[str, Any]]:
    def build(run_dir: Path) -> dict[str, Any]:
        if stage in ("title_thumb",):
            checks = title_auto_checks(run_dir, competitors)
            return {"auto": checks["blocking"], "auto_advisory": checks["advisory"]}
        if stage in ("topic", "shorts_topic"):
            return {"short": _short(ctx)}
        if stage in ("final", "shorts_final"):
            from content_farm.evaluation.flow import thumbs_for

            return {"thumbs": thumbs_for(run_dir, competitors)}
        return {}
    return build


def _mark_rework(ctx: Context, state: RunState, plan: dict[str, Any], gate: str) -> RunState:
    from content_farm.production.steps import steps_for

    by_name = {s.name: s for s in steps_for(ctx.channel, ctx.run_dir)}
    note = f"review/{gate}.fixes.json"
    for name in plan["steps"]:
        step = by_name.get(name)
        if step is None:
            continue
        inputs = fingerprint(ctx.run_dir, step.outputs) if step.kind == "agent" else ""
        state = state.with_step(name, StepRecord("rework", now_iso(), inputs=inputs, note=note))
    return state


def panel_step(ctx: Context, state: RunState, step: Step, stage: str, current: str,
               log: Callable[[str], None]) -> tuple[RunState, RunResult | None]:
    from content_farm.review.gate import panel_gate

    assert step.gate is not None
    competitors = competitors_for(ctx)
    log(f"⚖ {step.name}: 評審團 {stage}")
    result = panel_gate(ctx.run_dir, gate=step.gate.value, stage_name=stage, config=review_config(ctx),
                        channel=ctx.channel.code, channel_name=ctx.channel.name, competitors=competitors,
                        vertical=_short(ctx), judge_context=_judge_context(ctx, stage, competitors),
                        client=ctx.options.review_client)
    return _apply(ctx, state, step, stage, current, result, log)


def facts_delta(ctx: Context, state: RunState, step: Step, current: str,
                log: Callable[[str], None]) -> tuple[RunState, RunResult | None] | None:
    """The delta fact-check (``review.delta``) when the fact stage approved an earlier deck and the deck
    only lost or edited sentences since; None = the regular fact rounds decide."""
    from content_farm.review.delta import delta_gate
    from content_farm.review.gate import PANEL_BY

    assert step.gate is not None
    decision = state.decisions.get(step.gate.value)
    locked = _facts_baseline(ctx.run_dir)
    if (decision is None or decision.verdict != "approved" or not decision.by.startswith(PANEL_BY)
            or locked is None or not (ctx.run_dir / "deck.json").is_file()):
        return None
    log(f"⚖ {step.name}: 差異查核（事實段已核可，只審核可後改寫的句子）")
    result = delta_gate(ctx.run_dir, gate=step.gate.value, stage_name="script_facts", config=review_config(ctx),
                        channel=ctx.channel.code, channel_name=ctx.channel.name, locked_deck=locked,
                        client=ctx.options.review_client)
    if result is None:
        return None
    return _apply(ctx, state, step, "script_facts", current, result, log, delta=True)


def _facts_baseline(run_dir: Path) -> Path | None:
    """The deck the fact stage last approved: ``FACTS_LOCKED_DECK``, or — for an approval recorded before
    that file existed — the snapshot kept by the approving round. None when neither exists (e.g. a new
    cycle moved the rounds aside)."""
    locked = run_dir / FACTS_LOCKED_DECK
    if locked.is_file():
        return locked
    decision = run_dir / "review" / f"{Gate.DECK_FACTS.value}.decision.json"
    if not decision.is_file():
        return None
    card = json.loads(decision.read_text(encoding="utf-8")).get("scorecard")
    snapshot = Path(card).parent / "snapshot" / "deck.json" if card else None
    return snapshot if snapshot is not None and snapshot.is_file() else None


def _apply(ctx: Context, state: RunState, step: Step, stage: str, current: str, result: Any,
           log: Callable[[str], None], *, delta: bool = False) -> tuple[RunState, RunResult | None]:
    from content_farm.production.runner import Outcome, RunResult
    from content_farm.review.gate import PANEL_BY

    assert step.gate is not None
    _event(ctx.run_dir, step=step.name, panel=stage, status=result.status, message=result.message,
           scorecard=result.scorecard, tier_mode=review_config(ctx).tier_mode, **({"delta": True} if delta else {}))
    from content_farm.review.scorecard_html import render

    render(ctx.run_dir, ctx.channel.name)
    log(f"⚖ {step.name}: {result.message}")
    if result.status == "pass":
        note = f"{result.message}; {result.scorecard}"
        decision = Decision(step.gate.value, "approved", current, now_iso(), by=PANEL_BY + stage, note=note)
        record = StepRecord("approved", decision.at, inputs=current, note=f"by {decision.by}")
        if step.gate in (Gate.DECK, Gate.DECK_FACTS) and (ctx.run_dir / "deck.json").is_file():
            # the baselines the next edit is diffed against: feat/incremental-render's fix scope
            # (scripts/fix_scope.py) and the fact lock (structure_kept)
            import shutil

            shutil.copy2(ctx.run_dir / "deck.json", ctx.run_dir / APPROVED_DECK)
            shutil.copy2(ctx.run_dir / "deck.json", ctx.run_dir / LOCKED_DECK)
            if step.gate is Gate.DECK_FACTS:
                shutil.copy2(ctx.run_dir / "deck.json", ctx.run_dir / FACTS_LOCKED_DECK)
        return state.with_decision(decision).with_step(step.name, record), None
    record = StepRecord("waiting", now_iso(), inputs=current, note=result.message)
    state = state.with_step(step.name, record)
    if result.status == "rework" and result.rework is not None:
        state = _mark_rework(ctx, state, result.rework, step.gate.value)
        return state, RunResult(Outcome.REWORK, step.name, result.message)
    return state, RunResult(Outcome.FAILED, step.name, result.message)


REWORK_ATTEMPTS = 2     # a rewrite that breaks the delete-or-edit-only rule is refused and asked once more


def rework_gate(note: str) -> str | None:
    """The gate whose fix list a rework record points at (``review/<gate>.fixes.json``)."""
    name = Path(note).name
    return name.removesuffix(".fixes.json") if name.endswith(".fixes.json") else None


RULE_OUTPUTS = {"deck": ("deck.json",), "thumbnail_spec": ("titles.json", "thumbnail.json", "thumbnail_variants.json")}


def channel_rule_violations(ctx: Context, step_name: str) -> list[str]:
    """The channel's own rules a producer's output breaks (the same checks as the policy step, run
    before the output is accepted): deck → opening / sign-off / take / host share; thumbnail_spec →
    the host on the main thumbnail and its promise paid off (rendering is checked later)."""
    if step_name == "deck" and (ctx.run_dir / "deck.json").is_file():
        from pydantic import ValidationError

        from content_farm.explainer.deck import load_deck
        from content_farm.production import qc

        try:
            deck = load_deck(ctx.run_dir / "deck.json")
        except (ValidationError, ValueError):   # not a valid deck: the deck step's own verify (--strict) reports it
            return []
        return [f.message for f in qc.deck_findings(ctx.channel, deck) if f.level == "error"]
    if step_name == "thumbnail_spec":
        from content_farm.production.thumbnail import OUT_FILE, thumbnail_findings

        return [f.message for f in thumbnail_findings(ctx.run_dir, ctx.channel)
                if f.level == "error" and OUT_FILE not in f.message]
    return []


def run_producer(ctx: Context, step_name: str, log: Callable[[str], None], *, gate: str | None = None) -> str | None:
    """Run the producer agent for ``step_name``; None on success, else why it failed. ``gate``: the
    gate whose fix list sent this rework (default: the step's own gate).

    The output must keep the channel's rules (``channel_rule_violations``, the policy step's checks):
    an output that breaks one is restored and redone once with the broken rules in the brief (not a
    review round); breaking them again stops the step with the output restored."""
    before = {name: (ctx.run_dir / name).read_text(encoding="utf-8")
              for name in RULE_OUTPUTS.get(step_name, ()) if (ctx.run_dir / name).is_file()}
    failure = _produce_guarded(ctx, step_name, log, gate=gate)
    for attempt in (1, 2):
        if failure is not None:
            return failure
        broken = channel_rule_violations(ctx, step_name)
        _event(ctx.run_dir, step=step_name, channel_rules=broken, attempt=attempt)
        if not broken:
            return None
        for name, text in before.items():
            (ctx.run_dir / name).write_text(text, encoding="utf-8")
        log(f"✗ {step_name}: 拒收（違反頻道規則）：{'；'.join(broken)[:200]}")
        if attempt == 2:
            break
        failure = _produce_guarded(ctx, step_name, log, gate=gate, rules=(
            "上一次的改稿違反頻道規則，已還原成改稿前的版本。頻道規則優先於評審意見；以下規則一條都不能破：\n- "
            + "\n- ".join(broken) + "\n照修改清單重改，但保留上面這些頻道規則要求的內容。"))
    return f"{step_name}：改稿兩次都違反頻道規則，已還原並停下：{'；'.join(broken)[:300]}"


def _produce_guarded(ctx: Context, step_name: str, log: Callable[[str], None], *, gate: str | None = None,
                     rules: str = "") -> str | None:
    """One producer run, with the delete-only guard (a rework under DELETE_ONLY_FROM_ROUND — the article
    from round 2, the script's fact stage — must only delete or edit the flagged sentences
    (``review.article_diff``): a rewrite that breaks it is restored and redone, at most
    ``REWORK_ATTEMPTS`` times in all)."""
    from content_farm.review.producers import produce

    guard = _delete_only_guard(ctx.run_dir, step_name, gate)
    extra = rules
    for attempt in range(1, (REWORK_ATTEMPTS if guard else 1) + 1):
        log(f"✎ {step_name}: 產出 agent" + (f"（只准刪改，第 {attempt} 次）" if guard else ""))
        config = review_config(ctx)
        result = produce(step_name, ctx.run_dir, channel=ctx.channel.code, config=config,
                         python=ctx.options.python, client=ctx.options.review_client, extra=extra, gate=gate)
        _event(ctx.run_dir, step=step_name, producer=result.to_json(), tier_mode=config.tier_mode)
        if not result.ok:
            return f"{step_name} 產出 agent 失敗：{'; '.join(result.errors)[:300]}"
        log(f"✎ {step_name}: {result.seconds}s {(result.output or {}).get('summary', '')[:120]}")
        if guard is None:
            return None
        problems = guard.check()
        _event(ctx.run_dir, step=step_name, delete_only=guard.path.name, attempt=attempt, problems=problems)
        if not problems:
            return None
        guard.restore()
        log(f"✗ {step_name}: 拒收（不是只刪改）：{'；'.join(problems)[:200]}")
        extra = (rules + "\n\n" if rules else "") + (f"上一次的改稿被拒收，{guard.path.name} 已還原成改稿前的版本。原因（程式比對前後版本）：\n- "
                 + "\n- ".join(problems)
                 + "\n重新改：只准刪除被點名的句子，或在被點名的句子裡加限定詞、改正數字與歸屬；不准新增句子，"
                   "沒被點名的句子一字不動。")
    return f"{step_name}：改稿 {REWORK_ATTEMPTS} 次都不是只刪改，已還原並停下（見 production.log.jsonl）"


@dataclass(frozen=True)
class _DeleteOnly:
    path: Path
    before: str
    flagged: frozenset[str]
    deck: bool = False          # compare deck narration sentences (stable ids), not article lines

    def check(self) -> list[str]:
        from content_farm.review.article_diff import check_rework, check_sentences, deck_narration

        after = self.path.read_text(encoding="utf-8") if self.path.is_file() else ""
        if not self.deck:
            return check_rework(self.before, after, set(self.flagged))
        try:
            new = deck_narration(json.loads(after))
        except json.JSONDecodeError as exc:
            return [f"deck.json 不是合法 JSON：{exc}"]
        return check_sentences(deck_narration(json.loads(self.before)), new, set(self.flagged))

    def restore(self) -> None:
        self.path.write_text(self.before, encoding="utf-8")


def _delete_only_guard(run_dir: Path, step_name: str, gate: str | None = None) -> _DeleteOnly | None:
    """The guard for a rework whose next round falls under DELETE_ONLY_FROM_ROUND, else None.
    Flagged sentences: the article sentences the fact items' quotes point at, or the deck sentence ids
    the fact items and their linked scope name."""
    from content_farm.review.article_diff import flagged_sentences, split_article
    from content_farm.review.config import DELETE_ONLY_FROM_ROUND
    from content_farm.review.producers import is_fact

    gate = gate or step_name
    start = DELETE_ONLY_FROM_ROUND.get(gate)
    target = run_dir / ("article.md" if step_name == "article" else "deck.json")
    plan_path = run_dir / "review" / f"{gate}.fixes.json"
    if start is None or not target.is_file() or not plan_path.is_file():
        return None
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if int(plan.get("round", 0)) + 1 < start:
        return None
    before = target.read_text(encoding="utf-8")
    fixes = [f for slot in plan.get("steps", {}).values() for f in slot.get("fixes", []) if is_fact(f)]
    snapshot = run_dir / "review" / f"{target.stem}.before-{gate}-round-{int(plan['round']) + 1}{target.suffix}"
    snapshot.write_text(before, encoding="utf-8")
    if step_name == "article":
        quotes = [str(f.get("evidence") or "") for f in fixes]
        return _DeleteOnly(target, before, frozenset(flagged_sentences(quotes, split_article(before))))
    ids = {str(i) for f in fixes for i in [*((f.get("ref") or {}).get("sentence_ids") or []),
                                           *(f.get("scope") or {}).get("sentence_ids", [])]}
    return _DeleteOnly(target, before, frozenset(ids), deck=True)


def structure_kept(ctx: Context, state: RunState, current: str, log: Callable[[str], None]) -> RunState | None:
    """The fact lock (7afa95870a4e = A). The structure stage's approval survives a deck change that only
    deletes or edits narration sentences (the fact stage's fixes, or a later stage's trims): the state
    with the gate kept approved. A change that adds sentences voids it — both script stages start a new
    cycle (their earlier rounds move to ``cycle-N/``) — and None is returned so the panel runs again."""
    from content_farm.review.article_diff import added_sentences, deck_narration
    from content_farm.review.gate import PANEL_BY

    decision = state.decisions.get(Gate.DECK.value)
    locked, deck = ctx.run_dir / LOCKED_DECK, ctx.run_dir / "deck.json"
    if (decision is None or decision.verdict != "approved" or not decision.by.startswith(PANEL_BY)
            or not locked.is_file() or not deck.is_file()):
        return None
    added = added_sentences(deck_narration(json.loads(locked.read_text(encoding="utf-8"))),
                            deck_narration(json.loads(deck.read_text(encoding="utf-8"))))
    if added:
        moved = _new_cycle(ctx.run_dir)
        log(f"🔓 gate_deck: 講稿新增句子，結構段核可失效、兩段重走（{len(added)} 處；舊輪次移到 {moved}）")
        _event(ctx.run_dir, step="gate_deck", fact_lock="reopened", added=added[:20], moved=moved)
        return None
    _event(ctx.run_dir, step="gate_deck", fact_lock="kept", approved_fingerprint=decision.fingerprint, inputs_now=current)
    record = StepRecord("approved", decision.at, inputs=current, note=f"structure kept (only deletes/edits); by {decision.by}")
    return state.with_step("gate_deck", record)


def _new_cycle(run_dir: Path) -> str:
    """Move both script stages' rounds (and the lock baseline) aside so the next rounds start at 1."""
    from content_farm.review.rounds import stage_dir

    root = stage_dir(run_dir, SCRIPT_STAGES[0])
    number = 1 + len(list(root.glob("cycle-*"))) if root.is_dir() else 1
    for stage in SCRIPT_STAGES:
        here = stage_dir(run_dir, stage)
        rounds = sorted(here.glob("round-*")) if here.is_dir() else []
        if rounds:
            (here / f"cycle-{number}").mkdir(parents=True, exist_ok=True)
            for path in rounds:
                path.rename(here / f"cycle-{number}" / path.name)
    for gate in (Gate.DECK.value, Gate.DECK_FACTS.value):
        plan = run_dir / "review" / f"{gate}.fixes.json"
        if plan.is_file():
            plan.rename(plan.with_name(f"{gate}.fixes.cycle-{number}.json"))
    (run_dir / LOCKED_DECK).rename(run_dir / f"review/deck.locked.cycle-{number}.json")
    if (run_dir / FACTS_LOCKED_DECK).is_file():
        (run_dir / FACTS_LOCKED_DECK).rename(run_dir / f"review/deck_facts.locked.cycle-{number}.json")
    return f"cycle-{number}"
