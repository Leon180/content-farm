"""The runner's side of the review panels: which stage reviews a gate, what to do with the
panel's answer (record the approval, or mark the steps a fix list routes back to), and the
producer agents for agent steps when ``--auto-agents`` is on."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from content_farm.production.channels import Gate
from content_farm.production.state import Decision, RunState, StepRecord, fingerprint, now_iso

if TYPE_CHECKING:
    from content_farm.production.runner import RunResult
    from content_farm.production.steps import Context, Step

PRODUCER_STEPS = ("topic", "article", "deck", "thumbnail_spec")
APPROVED_DECK = "review/deck.approved.json"   # same path as feat/incremental-render's runner.APPROVED_DECK
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


def title_auto_checks(run_dir: Path, competitors: Path | None) -> dict[str, list[str]]:
    """Per variant, the automatic checks it fails: 168 px glyph, contrast, subject share,
    hue distance from the competitors (salience), blank blocks / broken image."""
    from content_farm.evaluation.flow import thumbs_for
    from content_farm.evaluation.homepage import CONTRAST_MIN, HUE_DISTANCE_MIN, SMALL_GLYPH_MIN, SUBJECT_MIN

    failed: dict[str, list[str]] = {}
    for key, m in thumbs_for(run_dir, competitors).items():
        out = []
        if (m.get("glyph_px_at_168") or 0) < SMALL_GLYPH_MIN:
            out.append(f"168px 字高 {m.get('glyph_px_at_168')} < {SMALL_GLYPH_MIN:g}")
        if (m.get("contrast") or 0) < CONTRAST_MIN:
            out.append(f"對比 {m.get('contrast')} < {CONTRAST_MIN}")
        if (m.get("subject_share") or 0) < SUBJECT_MIN:
            out.append(f"主體佔比 {m.get('subject_share')} < {SUBJECT_MIN}")
        if m.get("hue_distance") is not None and m["hue_distance"] < HUE_DISTANCE_MIN:
            out.append(f"與競品色相差 {m['hue_distance']}° < {HUE_DISTANCE_MIN:g}°")
        blank = blank_share(run_dir / "thumbnails" / f"variant_{key.lower()}.jpg")
        if blank > 0.35:
            out.append(f"空白方塊 {blank:.0%}")
        failed[key] = out
    return failed


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
            return {"auto": title_auto_checks(run_dir, competitors)}
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
    from content_farm.production.runner import Outcome, RunResult
    from content_farm.review.gate import PANEL_BY, panel_gate

    assert step.gate is not None
    competitors = competitors_for(ctx)
    log(f"⚖ {step.name}: 評審團 {stage}")
    result = panel_gate(ctx.run_dir, gate=step.gate.value, stage_name=stage, config=review_config(ctx),
                        channel=ctx.channel.code, channel_name=ctx.channel.name, competitors=competitors,
                        vertical=_short(ctx), judge_context=_judge_context(ctx, stage, competitors),
                        client=ctx.options.review_client)
    _event(ctx.run_dir, step=step.name, panel=stage, status=result.status, message=result.message,
           scorecard=result.scorecard)
    from content_farm.review.scorecard_html import render

    render(ctx.run_dir, ctx.channel.name)
    log(f"⚖ {step.name}: {result.message}")
    if result.status == "pass":
        note = f"{result.message}; {result.scorecard}"
        decision = Decision(step.gate.value, "approved", current, now_iso(), by=PANEL_BY + stage, note=note)
        record = StepRecord("approved", decision.at, inputs=current, note=f"by {decision.by}")
        if step.gate is Gate.DECK and (ctx.run_dir / "deck.json").is_file():
            # the baseline the next edit is diffed against (feat/incremental-render scripts/fix_scope.py)
            import shutil

            shutil.copy2(ctx.run_dir / "deck.json", ctx.run_dir / APPROVED_DECK)
        return state.with_decision(decision).with_step(step.name, record), None
    record = StepRecord("waiting", now_iso(), inputs=current, note=result.message)
    state = state.with_step(step.name, record)
    if result.status == "rework" and result.rework is not None:
        state = _mark_rework(ctx, state, result.rework, step.gate.value)
        return state, RunResult(Outcome.REWORK, step.name, result.message)
    return state, RunResult(Outcome.FAILED, step.name, result.message)


def run_producer(ctx: Context, step_name: str, log: Callable[[str], None]) -> str | None:
    """Run the producer agent for ``step_name``; None on success, else why it failed."""
    from content_farm.review.producers import produce

    log(f"✎ {step_name}: 產出 agent")
    result = produce(step_name, ctx.run_dir, channel=ctx.channel.code, config=review_config(ctx),
                     python=ctx.options.python, client=ctx.options.review_client)
    _event(ctx.run_dir, step=step_name, producer=result.to_json())
    if not result.ok:
        return f"{step_name} 產出 agent 失敗：{'; '.join(result.errors)[:300]}"
    log(f"✎ {step_name}: {result.seconds}s {(result.output or {}).get('summary', '')[:120]}")
    return None
