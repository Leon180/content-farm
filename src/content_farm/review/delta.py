"""Delta fact-check: after the script's fact stage approved, a later edit is checked sentence by sentence.

A later stage's fix (e.g. a title rework routed back to the deck) may trim or qualify narration after
``script_facts`` passed. The fact lock already keeps the structure approval for such edits; here the
fact approval is kept too, once the **edited** sentences pass two fact-checkers (+ arbiter on
disagreement) with 0 confirmed errors. Deleted sentences need no check. A delta round never counts as
one of the stage's rounds (``round-N-delta-K``), and at most ``DELTA_MAX`` delta rounds run against one
baseline (the deck at the last fact approval) before the gate stops. An added sentence is not a delta:
the fact lock reopens both script stages instead (``panel_flow.structure_kept``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from content_farm.production.state import fingerprint
from content_farm.review.article_diff import ArticleSentence, added_sentences, deck_narration, normalize
from content_farm.review.client import Call, CallResult
from content_farm.review.config import ReviewConfig
from content_farm.review.gate import GateResult, _rework, _waive, auto_fix_enabled, enforce, set_aside, write_decision
from content_farm.review.rounds import rounds_of, run_round, stage_dir

DELTA_MAX = 2


def edited_sentences(old: list[ArticleSentence], new: list[ArticleSentence]) -> list[str]:
    """Ids in ``new`` whose text is not in ``old`` — matched by text, not id, because a rework may
    re-id an edited sentence (a deletion is not an edit). Only meaningful once ``added_sentences``
    found no additions: every remaining unmatched sentence is then an edit."""
    before = {normalize(s.text) for s in old}
    return [s.id for s in new if normalize(s.text) not in before]


def baseline_hash(locked_deck: Path) -> str:
    return hashlib.sha256(locked_deck.read_bytes()).hexdigest()[:16]


def _deltas_against(run_dir: Path, stage_name: str, base: str) -> list[dict[str, Any]]:
    cards = []
    for path in sorted(stage_dir(run_dir, stage_name).glob("round-*-delta-*/scorecard.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        if card.get("delta_base") == base:
            cards.append(card)
    return cards


def delta_gate(run_dir: Path, *, gate: str, stage_name: str, config: ReviewConfig, channel: str,
               channel_name: str, locked_deck: Path,
               client: Callable[[Call], CallResult] | None = None) -> GateResult | None:
    """The fact gate's answer for a deck edited after its approval; None = not a delta (sentences
    were added), so the regular rounds decide."""
    locked = deck_narration(json.loads(locked_deck.read_text(encoding="utf-8")))
    now = deck_narration(json.loads((run_dir / "deck.json").read_text(encoding="utf-8")))
    if added_sentences(locked, now):
        return None
    stage = config.stages[stage_name]
    current = fingerprint(run_dir, stage.reviews)
    edited = edited_sentences(locked, now)
    if edited and auto_fix_enabled(config, stage_name):    # checked once; later edits are not re-checked (a53960fc4b1d = A)
        return GateResult("pass", f"{stage_name}：核可後改寫 {len(edited)} 句，依「事實只查一次」不重查，事實段核可沿用")
    if not edited:
        return GateResult("pass", f"{stage_name}：核可後只刪句，沒有改寫的句子，事實段核可沿用")
    base = baseline_hash(locked_deck)
    earlier = _deltas_against(run_dir, stage_name, base)
    if len(earlier) >= DELTA_MAX:
        last = earlier[-1]
        if stage.waive_on_last_round:       # Leon 2026-10-23: the last allowed check does not stop the run
            waiver = _waive(run_dir, gate, stage_name, config, last,
                            current, stage_dir(run_dir, stage_name) / last["label"] / "scorecard.json",
                            f"差異查核 {DELTA_MAX} 次用完")
            if waiver is not None:
                return waiver
        return GateResult("exhausted", f"{stage_name}：差異查核 {DELTA_MAX} 次用完仍未通過："
                          + "；".join(last["verdict"]["reasons"]),
                          stage_dir(run_dir, stage_name) / last["label"] / "scorecard.json")
    done = [p for p in rounds_of(run_dir, stage_name) if re.fullmatch(r"round-\d+", p.name)]
    round_no = int(done[-1].name.split("-")[1]) if done else 1
    card = run_round(run_dir, stage_name=stage_name, config=config, channel=channel, channel_name=channel_name,
                     round_no=round_no, with_holdout=False, client=client,
                     suffix=f"-delta-{len(earlier) + 1}", only_sentences=frozenset(edited))
    card = {**card, "delta_base": base, "delta_sentences": edited}
    card_path = stage_dir(run_dir, stage_name) / card["label"] / "scorecard.json"
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    lost = [s["rid"] for s in card["seats"] if not s.get("ok") and s.get("infra")]
    if lost:
        moved = set_aside(run_dir, stage_name, card["label"])
        return GateResult("blocked", f"{stage_name} 差異查核不算：{', '.join(lost)} 沒有回應，已移到 {moved.name}", None)
    reasons = "；".join(card["verdict"]["reasons"])
    if not card["verdict"]["pass"]:
        plan = _rework(run_dir, gate, stage_name, card, stage.rework)
        return GateResult("rework", f"{stage_name} 差異查核 {len(earlier) + 1} 未過（{reasons}）→ 退回 {plan['restart']}",
                          card_path, plan, card["verdict"]["scores"])
    problems = enforce(card, config, stage_name, current)
    if problems:
        return GateResult("blocked", f"{stage_name}: 差異查核評分卡不符規則：{'；'.join(problems)}", card_path)
    write_decision(run_dir, gate, stage_name, card_path, card, current)
    return GateResult("pass", f"{stage_name} 差異查核 {len(earlier) + 1} 通過（{len(edited)} 句）", card_path,
                      scores=card["verdict"]["scores"])
