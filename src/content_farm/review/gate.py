"""Panel-approved gates. The runner calls ``panel_gate`` instead of waiting for a person.

The gate opens only when ``enforce`` finds nothing wrong with the scorecard: it exists for the
current inputs, every configured seat answered with a schema-valid output from the configured
model / effort, and the verdict passed. A failed round writes a fix list routed to the step that
caused each issue; after ``max_rounds`` the stage is exhausted and the run stops with the gap.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content_farm.production.state import fingerprint, now_iso
from content_farm.review import routing
from content_farm.review.client import Call, CallResult, model_matches
from content_farm.review.config import ReviewConfig
from content_farm.review.freeze import frozen_steps
from content_farm.review.narrow import narrow
from content_farm.review.rounds import VIDEO_STAGES, expected_seats, rounds_of, run_round, stage_dir
from content_farm.review.sentences import deck_sentences, script_sentences

PANEL_BY = "agent-panel:"
# Stages whose rework only goes to their own producing step (the title / thumbnail spec); fixes the panel
# pins on earlier steps (script, media) are listed under the plan's ``advisory`` and change nothing
# (orchestrator decision 2026-10-19: a title round had rewritten the script and broken the channel opening).
TITLE_ONLY_STAGES = ("title_thumb", "shorts_title")
LONG_STAGE_FOR_GATE = {"topic": "topic", "article": "article", "deck": "script_structure",
                       "deck_facts": "script_facts", "title": "title_thumb", "media": "media", "final": "final"}
SHORT_STAGE_FOR_GATE = {"topic": "shorts_topic", "script": "shorts_script", "title": "shorts_title",
                        "final": "shorts_final"}


@dataclass(frozen=True)
class GateResult:
    status: str                    # pass | rework | exhausted | blocked
    message: str
    scorecard: Path | None = None
    rework: dict[str, Any] | None = None
    scores: dict[str, Any] | None = None


def stage_for_gate(gate: str, *, short: bool) -> str | None:
    return (SHORT_STAGE_FOR_GATE if short else LONG_STAGE_FOR_GATE).get(gate)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def enforce(card: dict[str, Any] | None, config: ReviewConfig, stage_name: str, current_inputs: str) -> list[str]:
    """Why this scorecard may NOT open the gate ([] = it may)."""
    if card is None:
        return ["no scorecard"]
    problems = []
    if card.get("stage") != stage_name:
        problems.append(f"scorecard is for {card.get('stage')!r}, not {stage_name!r}")
    if card.get("inputs") != current_inputs:
        problems.append("reviewed inputs changed since the scorecard")
    stage = config.stages[stage_name]
    seats = [s for s in card.get("seats", []) if not s.get("holdout")]
    for role, (count, model, effort) in expected_seats(stage, config, with_holdout=False).items():
        mine = [s for s in seats if s["role"] == role]
        if len(mine) < count:
            problems.append(f"{role}: {len(mine)}/{count} reviewers")
        for seat in mine:
            if not seat.get("ok"):
                problems.append(f"{seat['rid']}: no valid output ({'; '.join(seat.get('errors', []))[:120]})")
            if seat.get("model") != model or seat.get("effort") != effort:
                problems.append(f"{seat['rid']}: ran {seat.get('model')} · {seat.get('effort')}, config {model} · {effort}")
            if seat.get("models_used") and not model_matches(model, tuple(seat["models_used"])):
                problems.append(f"{seat['rid']}: answered by {seat['models_used']}, not {model}")
    disputes = ((card.get("verdict") or {}).get("scores") or {}).get("disputes") or 0
    arbiters = [s for s in card.get("seats", []) if s.get("role") == "fact_arbiter"]
    if disputes and (stage.arbiter is None or not arbiters):
        problems.append(f"{disputes} disputed fact claim(s) but no arbiter seat")
    for seat in arbiters:
        if stage.arbiter is None or seat.get("model") != stage.arbiter.model or seat.get("effort") != stage.arbiter.effort:
            problems.append(f"{seat['rid']}: ran {seat.get('model')} · {seat.get('effort')}, config "
                            f"{stage.arbiter.label() if stage.arbiter else 'none'}")
        if not seat.get("ok"):
            problems.append(f"{seat['rid']}: no valid output")
        if stage.arbiter and seat.get("models_used") and not model_matches(stage.arbiter.model, tuple(seat["models_used"])):
            problems.append(f"{seat['rid']}: answered by {seat['models_used']}, not {stage.arbiter.model}")
    if not (card.get("verdict") or {}).get("pass"):
        problems.append("verdict: " + "；".join((card.get("verdict") or {}).get("reasons", [])))
    return problems


def _texts(run_dir: Path) -> routing.Texts:
    sentences = []
    if (run_dir / "deck.json").is_file():
        sentences = deck_sentences(_load(run_dir / "deck.json"))
    elif (run_dir / "script.json").is_file():
        sentences = script_sentences(_load(run_dir / "script.json"))
    titles = {}
    if (run_dir / "titles.json").is_file():
        data = _load(run_dir / "titles.json")
        titles = {str(t["id"]): str(t["text"]) for t in (data["titles"] if isinstance(data, dict) else data)}
    thumb = (run_dir / "thumbnail.json").read_text(encoding="utf-8") if (run_dir / "thumbnail.json").is_file() else ""
    description = ""
    if (run_dir / "deck.json").is_file():
        description = str(_load(run_dir / "deck.json").get("description", ""))
    return routing.Texts(sentences, titles, thumb, description)


def _rework(run_dir: Path, gate: str, stage_name: str, card: dict[str, Any], default_step: str) -> dict[str, Any]:
    verdict = card["verdict"]
    issues = list(verdict.get("issues", []))
    for asset in verdict.get("rework_assets", []):
        issues.append({"ref": {"target": "media", "item": asset}, "category": "compliance", "severity": "high",
                       "problem": f"素材 {asset} 合規未過", "fix": "換素材或重生這一張", "evidence": asset,
                       "caused_by": "media"})
    advisory: list[dict[str, Any]] = []
    prompt_only = _ai_image_ids(run_dir, issues) if stage_name == "media" else []
    if prompt_only:   # the picture comes from deck.json's media.prompt: the deck agent rewrites only those
        issues = [{**i, "caused_by": "deck", "prompt_only": True}
                  if (i.get("ref") or {}).get("item") in prompt_only and i.get("caused_by") in (None, "illustrate", "media")
                  else i for i in issues]
    if stage_name == "media":   # a credits / licence gap on a live slide's card: re-running media cannot fix it
        live = _deck_slide_ids(run_dir)
        issues = [{**i, "caused_by": "deck"}
                  if i.get("category") == "compliance" and (i.get("ref") or {}).get("item") in live
                  and (i.get("ref") or {}).get("item") not in prompt_only
                  and i.get("caused_by") in (None, "illustrate", "media") else i for i in issues]
    if stage_name in VIDEO_STAGES and any(i.get("caused_by") == "mix" for i in issues):
        from content_farm.review.materials_video import audio_mix_enabled

        if not audio_mix_enabled(run_dir):   # no mix step on this channel: a mix fix has nothing to run — a config matter
            advisory += [{**i, "caused_by": "channel-config"} for i in issues if i.get("caused_by") == "mix"]
            issues = [i for i in issues if i.get("caused_by") != "mix"]
    if stage_name in TITLE_ONLY_STAGES:   # a title panel never sends the script (or media) back: listed only
        advisory = [i for i in issues if (i.get("caused_by") or default_step) != default_step]
        issues = [i for i in issues if (i.get("caused_by") or default_step) == default_step]
    if not issues:   # failed on numbers alone (e.g. leave median): the producing step reworks
        issues = [{"ref": {"target": "script"}, "category": "content", "severity": "high",
                   "problem": "；".join(verdict.get("reasons", [])), "fix": "依評分卡改善", "evidence": "",
                   "caused_by": default_step}]
    texts = _texts(run_dir)
    issues, deferred, narrowing = narrow(issues, texts.sentences) if narrow_enabled() else (issues, [], None)
    plan = routing.plan(issues, texts, stage=stage_name, round_no=card["round"], default_step=default_step,
                        frozen=frozen_steps(run_dir))
    if narrowing is not None:
        plan["narrowing"] = narrowing
        plan["deferred"] = [{k: i.get(k) for k in ("ref", "category", "severity", "problem", "who")} for i in deferred]
    if prompt_only:
        plan["prompt_only"] = prompt_only
    if advisory:
        plan["advisory"] = [{k: i.get(k) for k in ("ref", "category", "problem", "fix", "who", "caused_by")}
                            for i in advisory]
    plan["reasons"] = verdict.get("reasons", [])
    plan["scorecard"] = str(stage_dir(run_dir, stage_name) / card["label"] / "scorecard.json")
    routing.write(run_dir, gate, plan)
    return plan


def _deck_slide_ids(run_dir: Path) -> set[str]:
    if not (run_dir / "deck.json").is_file():
        return set()
    return {str(s["id"]) for sec in _load(run_dir / "deck.json").get("sections", []) for s in sec.get("slides", [])}


def _ai_image_ids(run_dir: Path, issues: list[dict[str, Any]]) -> list[str]:
    """Slides the media panel flagged whose picture is a generated ``ai_image`` (prompt in deck.json)."""
    if not (run_dir / "deck.json").is_file():
        return []
    deck = _load(run_dir / "deck.json")
    generated = {s["id"] for sec in deck.get("sections", []) for s in sec.get("slides", [])
                 if (s.get("media") or {}).get("kind") == "ai_image"}
    flagged = {str((i.get("ref") or {}).get("item")) for i in issues
               if i.get("caused_by") in (None, "illustrate", "media")}
    return sorted(flagged & generated)


def _after_pass(run_dir: Path, stage_name: str, card: dict[str, Any]) -> None:
    verdict = card["verdict"]
    if stage_name in ("topic", "shorts_topic"):
        data = _load(run_dir / "topics" / "candidates.json")
        candidates = {c["id"]: c for c in (data["candidates"] if isinstance(data, dict) else data)}
        chosen = [candidates[c] for c in verdict.get("chosen", []) if c in candidates]
        (run_dir / "topic.json").write_text(json.dumps({"chosen": chosen, "ranking": verdict["scores"]["ranking"]},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    if stage_name in ("title_thumb", "shorts_title"):
        (run_dir / "review" / "title.choice.json").write_text(json.dumps(
            {"best_title": verdict["scores"].get("best_title"), "titles": verdict["scores"].get("titles"),
             "homepage": verdict["scores"].get("homepage")}, ensure_ascii=False, indent=1), encoding="utf-8")


def write_decision(run_dir: Path, gate: str, stage_name: str, card_path: Path, card: dict[str, Any],
                   fingerprint_now: str) -> dict[str, Any]:
    data = {"version": 1, "kind": "production_gate", "gate": gate, "status": "approved",
            "by": PANEL_BY + stage_name, "decided_at": now_iso(), "decided_fingerprint": fingerprint_now,
            "scorecard": str(card_path), "round": card["round"], "scores": card["verdict"]["scores"],
            "seats": [{k: s.get(k) for k in ("rid", "role", "model", "effort", "models_used", "ok", "seconds")}
                      for s in card["seats"]]}
    path = run_dir / "review" / f"{gate}.decision.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return data


def set_aside(run_dir: Path, stage_name: str, label: str) -> Path:
    """Rename a round whose seats failed for infrastructure reasons so it never counts."""
    from datetime import datetime

    source = stage_dir(run_dir, stage_name) / label
    target = source.with_name(f"{label}-incomplete-{datetime.now():%H%M%S}")
    source.rename(target)
    return target


def _has_holdout(config: ReviewConfig, stage_name: str) -> bool:
    return any(s.holdout for s in config.stages[stage_name].seats)


def _carry(run_dir: Path, gate: str, stage_name: str, config: ReviewConfig, channel: str, number: int,
           last: dict[str, Any] | None, done: list[Path]):
    """Which seats of the round about to start keep their answer from the failed round before it
    (``review.reuse``); None on round 1, when the inputs were never reworked, or when a big change voids it."""
    from content_farm.review import reuse
    from content_farm.review.rounds import roster

    if last is None or number < 2 or last["verdict"]["pass"] or not reuse_enabled():
        return None
    plan_path = run_dir / "review" / f"{gate}.fixes.json"
    fixes = _load(plan_path) if plan_path.is_file() else None
    if fixes is not None and fixes.get("round") != last["round"]:
        fixes = None
    members = roster(config, stage_name, channel, number, with_holdout=number == config.stages[stage_name].max_rounds)
    return reuse.plan_carry(run_dir, stage_name=stage_name, stage=config.stages[stage_name], config=config,
                            members=members, previous_dir=done[-1], fixes=fixes)


def narrow_enabled() -> bool:
    """``CF_REVIEW_NARROW=0`` sends every issue back as before (before / after comparisons)."""
    import os

    return os.environ.get("CF_REVIEW_NARROW", "1").strip() != "0"


def reuse_enabled() -> bool:
    """``CF_REVIEW_REUSE=0`` re-runs every seat every round (before / after comparisons)."""
    import os

    return os.environ.get("CF_REVIEW_REUSE", "1").strip() != "0"


def panel_gate(run_dir: Path, *, gate: str, stage_name: str, config: ReviewConfig, channel: str,
               channel_name: str, client: Callable[[Call], CallResult] | None = None,
               competitors: Path | None = None, vertical: bool = False,
               judge_context: Callable[[Path], dict[str, Any]] | None = None) -> GateResult:
    stage = config.stages[stage_name]
    current = fingerprint(run_dir, stage.reviews)
    done = [p for p in rounds_of(run_dir, stage_name) if re.fullmatch(r"round-\d+", p.name)]   # no addenda / side rounds
    last = _load(done[-1] / "scorecard.json") if done else None
    if last is None or last.get("inputs") != current:
        number = (last["round"] + 1) if last else 1
        if number > stage.max_rounds:
            return GateResult("exhausted", f"{stage_name}: {stage.max_rounds} 輪用完仍未通過："
                              + "；".join(last["verdict"]["reasons"]) if last else "", done[-1] / "scorecard.json")
        last = run_round(run_dir, stage_name=stage_name, config=config, channel=channel, channel_name=channel_name,
                         round_no=number, with_holdout=number == stage.max_rounds, competitors=competitors,
                         client=client, vertical=vertical,
                         judge_context=judge_context(run_dir) if judge_context else None,
                         carry=_carry(run_dir, gate, stage_name, config, channel, number, last, done))
        lost = [s["rid"] for s in last["seats"] if not s.get("ok") and s.get("infra")]
        if lost:   # the plumbing failed, not the work: this round does not count and sends nothing back
            moved = set_aside(run_dir, stage_name, last["label"])
            return GateResult("blocked", f"{stage_name} 第 {number} 輪不算：{', '.join(lost)} 沒有回應（網路／程序失敗），"
                              f"已移到 {moved.name}；網路恢復後重跑 run 會重開這一輪", None)
    card_path = stage_dir(run_dir, stage_name) / last["label"] / "scorecard.json"
    if not last["verdict"]["pass"]:
        reasons = "；".join(last["verdict"]["reasons"])
        if last["round"] >= stage.max_rounds:
            return GateResult("exhausted", f"{stage_name}: 第 {last['round']} 輪（最後一輪）未通過：{reasons}", card_path,
                              scores=last["verdict"]["scores"])
        plan_path = run_dir / "review" / f"{gate}.fixes.json"
        old = _load(plan_path) if plan_path.is_file() else {}
        reuse = old.get("round") == last["round"] and old.get("frozen", []) == sorted(frozen_steps(run_dir))
        plan = old if reuse else _rework(run_dir, gate, stage_name, last, stage.rework)
        return GateResult("rework", f"{stage_name} 第 {last['round']} 輪未過（{reasons}）→ 退回 {plan['restart']}",
                          card_path, plan, last["verdict"]["scores"])
    if _has_holdout(config, stage_name) and not any(s.get("holdout") for s in last["seats"]):
        addendum = stage_dir(run_dir, stage_name) / f"round-{last['round']}-holdout" / "scorecard.json"
        if not addendum.is_file():
            run_round(run_dir, stage_name=stage_name, config=config, channel=channel, channel_name=channel_name,
                      round_no=last["round"], with_holdout=True, holdout_only=True, competitors=competitors,
                      client=client, vertical=vertical,
                      judge_context=judge_context(run_dir) if judge_context else None)
    problems = enforce(last, config, stage_name, current)
    if problems:
        return GateResult("blocked", f"{stage_name}: 評分卡不符規則：{'；'.join(problems)}", card_path)
    _after_pass(run_dir, stage_name, last)
    write_decision(run_dir, gate, stage_name, card_path, last, current)
    return GateResult("pass", f"{stage_name} 第 {last['round']} 輪通過", card_path, scores=last["verdict"]["scores"])
