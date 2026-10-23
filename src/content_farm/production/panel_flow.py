"""The runner's side of the review panels: which stage reviews a gate, what to do with the
panel's answer (record the approval, or mark the steps a fix list routes back to), and the
producer agents for agent steps when ``--auto-agents`` is on."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from content_farm.production import auto_fix_fallback
from content_farm.production.channels import Gate
from content_farm.production.state import Decision, RunState, StepRecord, fingerprint, now_iso

if TYPE_CHECKING:
    from content_farm.production.runner import RunResult
    from content_farm.production.steps import Context, Step

PRODUCER_STEPS = ("topic", "article", "deck", "thumbnail_spec", "skit_script", "news_script")
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

    return (ctx.channel.format.length == "short" or is_short_cut(ctx.run_dir)
            or (ctx.run_dir / "news_short.json").is_file())      # an HN-style news Short on a long-video channel


def stage_of(ctx: Context, gate: Gate) -> str | None:
    if not ctx.options.panels:
        return None
    from content_farm.review.gate import stage_for_gate

    return stage_for_gate(gate.value, short=_short(ctx))


def review_config(ctx: Context):
    from content_farm.review.config import Tier, load_review

    tier = None
    if ctx.options.review_tier:
        model, effort = ctx.options.review_tier.split(":")
        tier = Tier(model=model, effort=effort)
    return load_review(ctx.channel.code, raise_tier=tier)


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


def over_budget(ctx: Context) -> str | None:
    """Why the cloud lane must stop for this video (``review.budget``), or None. A person raising the allowance
    (``--budget-usd``) is recorded in the run-dir and counts from then on."""
    from content_farm.review import budget

    override = getattr(ctx.options, "budget_usd", None)
    if override is not None:
        budget.record_raise(ctx.run_dir, override)
    return budget.check(ctx.run_dir, configured=review_config(ctx).budget.usd_per_video, override=override)


def _round_due(ctx: Context, step: Step, stage: str) -> bool:
    """Would ``panel_gate`` start reviewers now? False when the stage's last round already judged the current
    inputs (a pass is only recorded; a miss is only turned into a fix list) — those cost nothing."""
    import re

    from content_farm.review.rounds import rounds_of, stage_dir

    config = review_config(ctx)
    wanted = config.stages[stage]
    done = [p for p in rounds_of(ctx.run_dir, stage) if re.fullmatch(r"round-\d+", p.name)]
    if not done:
        return True
    last = json.loads((done[-1] / "scorecard.json").read_text(encoding="utf-8"))
    if last.get("inputs") != fingerprint(ctx.run_dir, wanted.reviews):
        return True
    needs_holdout = any(s.holdout for s in wanted.seats) and not any(s.get("holdout") for s in last["seats"])
    addendum = stage_dir(ctx.run_dir, stage) / f"round-{last['round']}-holdout" / "scorecard.json"
    return bool(last["verdict"]["pass"]) and needs_holdout and not addendum.is_file()


def _budget_stop(ctx: Context, state: RunState, step: Step, message: str,
                 log: Callable[[str], None]) -> tuple[RunState, RunResult]:
    from content_farm.production.runner import Outcome, RunResult

    _event(ctx.run_dir, step=step.name, budget_stop=True, message=message)
    log(f"💸 {step.name}: {message}")
    return state, RunResult(Outcome.FAILED, step.name, message)


def panel_step(ctx: Context, state: RunState, step: Step, stage: str, current: str,
               log: Callable[[str], None]) -> tuple[RunState, RunResult | None]:
    from content_farm.review.gate import panel_gate

    assert step.gate is not None
    if not review_config(ctx).stages[stage].enabled:    # Leon 2026-10-24: switched off in review_panels.yaml
        from content_farm.review import license_rules
        from content_farm.review.gate import GateResult

        problems = license_rules.check(ctx.run_dir) if stage == "media" else []
        result = (GateResult("blocked", f"{stage}：授權程式規則未過：{'；'.join(problems)}") if problems
                  else GateResult("pass", f"{stage}：評審已關閉（enabled: false）"
                                  + ("，授權程式規則通過" if stage == "media" else "，直接放行")))
        return _apply(ctx, state, step, stage, current, result, log)
    if (stopped := over_budget(ctx)) is not None and _round_due(ctx, step, stage):
        return _budget_stop(ctx, state, step, stopped, log)
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
    if (stopped := over_budget(ctx)) is not None:
        return _budget_stop(ctx, state, step, stopped, log)
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
        if step.gate is Gate.ARTICLE and (ctx.run_dir / "article.md").is_file():
            import shutil

            shutil.copy2(ctx.run_dir / "article.md", ctx.run_dir / ARTICLE_APPROVED)
            for stale in (ARTICLE_LOCKED, ARTICLE_REWRITE):     # a structure rewrite's fact check is done
                (ctx.run_dir / stale).unlink(missing_ok=True)
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
        if result.rework.get("prompt_only"):    # regenerate these: illustrate only draws missing images
            from content_farm.review.prompt_rework import reject_images

            _event(ctx.run_dir, step=step.name, rejected_images=reject_images(ctx.run_dir, result.rework["prompt_only"]))
        state = _mark_rework(ctx, state, result.rework, step.gate.value)
        return state, RunResult(Outcome.REWORK, step.name, result.message)
    return state, RunResult(Outcome.FAILED, step.name, result.message)


REWORK_ATTEMPTS = 2     # a rewrite that breaks the delete-or-edit-only rule is refused and asked once more


def rework_gate(note: str) -> str | None:
    """The gate whose fix list a rework record points at (``review/<gate>.fixes.json``)."""
    name = Path(note).name
    return name.removesuffix(".fixes.json") if name.endswith(".fixes.json") else None


RULE_OUTPUTS = {"deck": ("deck.json",), "thumbnail_spec": ("titles.json", "thumbnail.json", "thumbnail_variants.json"),
               "skit_script": ("script.json",)}


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
    if step_name == "skit_script" and (ctx.run_dir / "script.json").is_file():
        from content_farm.production.skit import skit_problems

        try:
            return skit_problems(json.loads((ctx.run_dir / "script.json").read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            return [f"script.json 不是合法 JSON：{exc}"]
    if step_name == "thumbnail_spec":
        from content_farm.production.thumbnail import OUT_FILE, thumbnail_findings

        return [f.message for f in thumbnail_findings(ctx.run_dir, ctx.channel)
                if f.level == "error" and str(OUT_FILE) not in f.message]
    return []


def _prompt_only_violations(ctx: Context, step_name: str, gate: str | None, before: dict[str, str]) -> list[str]:
    """A media-panel rework of AI illustrations may change only the flagged slides' media.prompt, and the
    new prompt must not contradict the channel style prefix or itself (``review.prompt_rework``)."""
    plan_path = ctx.run_dir / "review" / f"{gate}.fixes.json"
    if step_name != "deck" or gate is None or not plan_path.is_file() or "deck.json" not in before:
        return []
    ids = json.loads(plan_path.read_text(encoding="utf-8")).get("prompt_only") or []
    if not ids:
        return []
    from content_farm.review.prompt_rework import prompt_only_problems

    style = (ctx.channel.ai_illustration.style_prefix
             if getattr(ctx.channel, "ai_illustration", None) is not None else "")
    after = json.loads((ctx.run_dir / "deck.json").read_text(encoding="utf-8"))
    return prompt_only_problems(json.loads(before["deck.json"]), after, set(ids), style)


def run_producer(ctx: Context, step_name: str, log: Callable[[str], None], *, gate: str | None = None) -> str | None:
    """``_run_producer``, except that the one automatic fix (``fact_on_fail: auto_fix_then_pass`` / the script review's
    ``script_revise_once``) can never stop the run: when its rewrite fails or is refused, the flagged sentences are
    deleted instead, or, failing that, the failure is recorded and the run goes on (Leon 2026-10-24).
    Only the cost cap still stops."""
    gate_name = gate or step_name
    auto = auto_fix_fallback.is_auto_fix(ctx.run_dir, gate_name)
    guard = _delete_only_guard(ctx.run_dir, step_name, gate_name) if auto else None   # taken before the rewrite
    failure = _run_producer(ctx, step_name, log, gate=gate)
    if failure is None or not auto:
        return failure
    if (stopped := over_budget(ctx)) is not None and failure == stopped:
        return failure
    from content_farm.review.gate import LONG_STAGE_FOR_GATE

    stage = LONG_STAGE_FOR_GATE.get(gate_name, gate_name)
    auto_fix_fallback.apply(ctx.run_dir, gate=gate_name, stage=stage, step_name=step_name, failure=failure,
                            guard=guard, log=log)
    return None


def _run_producer(ctx: Context, step_name: str, log: Callable[[str], None], *, gate: str | None = None) -> str | None:
    """Run the producer agent for ``step_name``; None on success, else why it failed. ``gate``: the
    gate whose fix list sent this rework (default: the step's own gate).

    The output must keep the channel's rules (``channel_rule_violations``, the policy step's checks):
    an output that breaks one is restored and redone once with the broken rules in the brief (not a
    review round); breaking them again stops the step with the output restored."""
    if (stopped := over_budget(ctx)) is not None:
        _event(ctx.run_dir, step=step_name, budget_stop=True, message=stopped)
        return stopped
    before = {name: (ctx.run_dir / name).read_text(encoding="utf-8")
              for name in RULE_OUTPUTS.get(step_name, ()) if (ctx.run_dir / name).is_file()}
    failure = _produce_guarded(ctx, step_name, log, gate=gate)
    for attempt in (1, 2):
        if failure is not None:
            return failure
        broken = channel_rule_violations(ctx, step_name) + _prompt_only_violations(ctx, step_name, gate, before)
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

    guard = (_structural_article_guard(ctx.run_dir, step_name, gate) or _delete_only_guard(ctx.run_dir, step_name, gate)
             or _scoped_guard(ctx.run_dir, step_name, gate))
    extra = rules
    for attempt in range(1, (REWORK_ATTEMPTS if guard else 1) + 1):
        log(f"✎ {step_name}: 產出 agent" + (f"（{guard.label}，第 {attempt} 次）" if guard else ""))
        config = review_config(ctx)
        result = produce(step_name, ctx.run_dir, channel=ctx.channel.code, config=config,
                         python=ctx.options.python, client=ctx.options.review_client, extra=extra, gate=gate)
        _event(ctx.run_dir, step=step_name, producer=result.to_json(), tier_mode=config.tier_mode)
        if not result.ok:
            return f"{step_name} 產出 agent 失敗：{'; '.join(result.errors)[:300]}"
        log(f"✎ {step_name}: {result.seconds}s {(result.output or {}).get('summary', '')[:120]}")
        if guard is None:
            return None
        problems = guard.check() + guard.reason_problems(result.output)
        _event(ctx.run_dir, step=step_name, guard=guard.label, file=guard.path.name, attempt=attempt, problems=problems,
               **guard.facts(result.output))
        if not problems:
            if hasattr(guard, "accept"):
                guard.accept(result.output)
            return None
        guard.restore()
        log(f"✗ {step_name}: 拒收（{guard.label}）：{'；'.join(problems)[:200]}")
        extra = (rules + "\n\n" if rules else "") + (f"上一次的改稿被拒收，{guard.path.name} 已還原成改稿前的版本。原因（程式比對前後版本）：\n- "
                 + "\n- ".join(problems) + "\n" + guard.retry_hint())
    return f"{step_name}：改稿 {REWORK_ATTEMPTS} 次都{guard.phrase}，已還原並停下（見 production.log.jsonl）"


@dataclass(frozen=True)
class _DeleteOnly:
    path: Path
    before: str
    flagged: frozenset[str]
    deck: bool = False          # compare deck narration sentences (stable ids), not article lines
    label: str = "只准刪改"
    phrase: str = "不是只刪改"

    def reason_problems(self, receipt: dict | None) -> list[str]:
        return []

    def facts(self, receipt: dict | None) -> dict:
        return {}

    def retry_hint(self) -> str:
        return ("重新改：只准刪除被點名的句子，或在被點名的句子裡加限定詞、改正數字與歸屬；不准新增句子，"
                "沒被點名的句子一字不動。")

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
        # the fix text may quote a second place that needs the same correction (『一份只針對動畫』 in the opening)
        quotes += [q for f in fixes for text in (f.get("problem"), f.get("fix"))
                   for q in re.findall(r"[『「]([^』」]{4,})[』」]", str(text or ""))]
        flagged = flagged_sentences(quotes, split_article(before)) | changed_since_lock(run_dir, before)
        return _DeleteOnly(target, before, frozenset(flagged))
    ids = {str(i) for f in fixes for i in [*((f.get("ref") or {}).get("sentence_ids") or []),
                                           *(f.get("scope") or {}).get("sentence_ids", [])]}
    return _DeleteOnly(target, before, frozenset(ids), deck=True)


ARTICLE_APPROVED = "review/article.approved.md"       # article at the last panel approval (the fact lock's baseline)
ARTICLE_LOCKED = "review/article.locked.md"           # baseline of a structure rewrite still awaiting its fact check
ARTICLE_REWRITE = "review/article.rewrite.json"       # why that rewrite was needed (rewrite_reason) and how big it was
STRUCTURE_REWRITE_CYCLE_REASON = "結構改寫（script_structure 退回 article）視為新的一份內容，article 輪數重算"


def changed_since_lock(run_dir: Path, current: str) -> set[str]:
    """Ids of the article sentences that are new or reworded since the fact-locked baseline of a structure
    rewrite (empty when none is pending): the only sentences the next fact check has not seen."""
    from content_farm.review.article_diff import normalize, split_article

    locked = run_dir / ARTICLE_LOCKED
    if not locked.is_file():
        return set()
    known = {normalize(s.text) for s in split_article(locked.read_text(encoding="utf-8"))}
    return {s.id for s in split_article(current) if normalize(s.text) not in known}


class _StructuralArticle:
    """The article sent back by the script_structure panel (leave points, story shape; Leon 2026-10-23). It may be
    restructured, but needs a ``rewrite_reason`` and may not change the numbers or source ids of the sentences that
    passed the fact check; the sentences it writes anew are checked by the next article round (and, as they are
    "changed since the lock", they stay editable for that round's fact fixes)."""

    label = "結構改寫（事實鎖定）"
    phrase = "動到已查核句子的數字或來源"

    def __init__(self, run_dir: Path, path: Path, before: str):
        self.run_dir, self.path, self.before = run_dir, path, before
        approved = run_dir / ARTICLE_APPROVED
        self.baseline = approved.read_text(encoding="utf-8") if approved.is_file() else before
        self.fresh: list[str] = []

    def check(self) -> list[str]:
        from content_farm.review.article_diff import check_structural

        after = self.path.read_text(encoding="utf-8") if self.path.is_file() else ""
        problems, self.fresh = check_structural(self.baseline, after)
        return problems

    def reason_problems(self, receipt: dict | None) -> list[str]:
        if not str((receipt or {}).get("rewrite_reason") or "").strip():
            return ["結構退回可以大改，但交件時 rewrite_reason 要說明為什麼要大改、改了哪些結構"]
        return []

    def facts(self, receipt: dict | None) -> dict:
        return {"rewrite_reason": (receipt or {}).get("rewrite_reason"), "new_sentences": len(self.fresh)}

    def accept(self, receipt: dict | None) -> None:
        (self.run_dir / ARTICLE_LOCKED).write_text(self.baseline, encoding="utf-8")
        (self.run_dir / ARTICLE_REWRITE).write_text(json.dumps(
            {"at": now_iso(), "rewrite_reason": (receipt or {}).get("rewrite_reason"), "new_sentences": len(self.fresh)},
            ensure_ascii=False, indent=1), encoding="utf-8")
        # a structure rewrite is a new piece of content: the article panel starts a fresh set of rounds (the spent
        # ones move to cycle-N/); sentences that kept their fact-checked text are not re-checked (ARTICLE_LOCKED)
        new_stage_cycle(self.run_dir, ("article",), reason=STRUCTURE_REWRITE_CYCLE_REASON)

    def restore(self) -> None:
        self.path.write_text(self.before, encoding="utf-8")

    def retry_hint(self) -> str:
        return ("重新改：可以重構段落與順序，但已通過事實查核的句子，數字與 [src:…] 來源 id 要和原句一致；新句子附來源或寫明是判斷；"
                "交件時 rewrite_reason 說明為什麼要大改。")


def _structural_article_guard(run_dir: Path, step_name: str, gate: str | None) -> _StructuralArticle | None:
    """The guard for an article rework that the script panel (not the article panel) asked for, else None."""
    article = run_dir / "article.md"
    if step_name != "article" or gate in (None, "article") or not article.is_file():
        return None
    plan_path = run_dir / "review" / f"{gate}.fixes.json"
    if not plan_path.is_file() or "article" not in json.loads(plan_path.read_text(encoding="utf-8")).get("steps", {}):
        return None
    return _StructuralArticle(run_dir, article, article.read_text(encoding="utf-8"))


class _Scoped:
    """``review.touch_guard.ScopedGuard`` with the interface ``_produce_guarded`` uses."""

    label = "只改被點名的部分"
    phrase = "改到沒被點名的部分"

    def __init__(self, inner):
        self.inner = inner
        self.path = inner.path

    def check(self) -> list[str]:
        return self.inner.check()

    def restore(self) -> None:
        self.inner.restore()

    def reason_problems(self, receipt: dict | None) -> list[str]:
        if self.inner.named.open and not str((receipt or {}).get("rewrite_reason") or "").strip():
            return ["修改清單沒有指到具體句子（整體結構問題）：可以大改，但交件時 rewrite_reason 要說明為什麼要大改"]
        return []

    def facts(self, receipt: dict | None) -> dict:
        return {"named": self.inner.named.to_json(), "rewrite_reason": (receipt or {}).get("rewrite_reason")}

    def retry_hint(self) -> str:
        return ("重新改：只改清單點名的句子 id（與連動範圍）；沒被點名的句子、投影片、標題一字不動，用 Edit 逐句改，不要整份重寫。"
                "若清單沒有指到具體句子（整體結構問題），可以重構，但回報的 rewrite_reason 必須寫明為什麼要大改。")


def _scoped_guard(run_dir: Path, step_name: str, gate: str | None) -> _Scoped | None:
    """The scoped-rework guard for a deck / title rework answering a fix list (``review.touch_guard``);
    None for a first draft, a media prompt-only rework (checked by ``prompt_rework``) or a step with no file to diff."""
    from content_farm.review.touch_guard import scoped_guard

    plan_path = run_dir / "review" / f"{gate}.fixes.json" if gate else None
    if plan_path is None or not plan_path.is_file():
        return None
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("prompt_only") or step_name not in plan.get("steps", {}):
        return None
    inner = scoped_guard(run_dir, step_name, plan)
    return _Scoped(inner) if inner is not None else None


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


NEW_CYCLE_REASON_MIN = 12      # chars: "because" is not a reason


def new_stage_cycle(run_dir: Path, stages: tuple[str, ...], *, reason: str) -> dict[str, str]:
    """``produce.py new-cycle``: the same archiving ``_new_cycle`` does for the script stages, for any panel
    stages whose rounds are used up. Each stage's ``round-*`` folders move to ``cycle-N/`` (N = that stage's
    next number) and its fix list to ``<gate>.fixes.cycle-N.json``, so the next round is number 1. Returns
    ``{stage: "cycle-N"}`` for the stages that had rounds; unknown stages raise.

    Leon 2026-10-23: the article gate allows 3 rounds and 0 errors; a new cycle is **not** a way to run more rounds
    on the same content. It is for rounds left by a clone / an older run-dir, or a re-run after a process gap was
    fixed. ``reason`` (required) says which; it is written to ``review/new_cycle.jsonl`` and the production log
    so the report can list every use."""
    from content_farm.review.config import load_review
    from content_farm.review.rounds import stage_dir

    if len((reason or "").strip()) < NEW_CYCLE_REASON_MIN:
        raise ValueError("new-cycle needs --reason (>= 12 chars): a cloned / older run's leftover rounds, or a re-run after "
                         "a process gap was fixed. It is not for running more rounds on the same content.")
    known = load_review().stages
    unknown = [s for s in stages if s not in known]
    if unknown:
        raise ValueError(f"unknown stage {unknown}; one of {sorted(known)}")
    moved: dict[str, str] = {}
    for stage in stages:
        here = stage_dir(run_dir, stage)
        rounds = sorted(here.glob("round-*")) if here.is_dir() else []
        if not rounds:
            continue
        number = 1 + len(list(here.glob("cycle-*")))
        (here / f"cycle-{number}").mkdir(parents=True)
        for path in rounds:
            path.rename(here / f"cycle-{number}" / path.name)
        plan = run_dir / "review" / f"{known[stage].gate}.fixes.json"
        if plan.is_file():
            plan.rename(plan.with_name(f"{known[stage].gate}.fixes.cycle-{number}.json"))
        moved[stage] = f"cycle-{number}"
    if moved:
        _event(run_dir, step="new_cycle", stages=moved, reason=reason.strip())
        with (run_dir / "review" / "new_cycle.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"at": now_iso(), "stages": moved, "reason": reason.strip()}, ensure_ascii=False) + "\n")
    return moved
