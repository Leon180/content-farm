"""Fast path for a small deck rework (cf-pipeline-speed, item 3).

A rework that names under 10% of the sentences, needs no new source and touches nothing but narration does not need
a tool-using agent: 九尾狐 deck-6/7/14/15/16 took 35–292 s of 13–62 turns to change 3–9 sentences. Here one
no-tool turn answers ``{id: new text}`` and the program applies it (``deck_patch``) and re-lints. Anything that
does not fit — too many sentences, a title / thumbnail / description fix, a source to look up, an answer naming
an unnamed sentence, a lint failure — returns None and the caller runs the full agent as before. The touch guard
still judges the result afterwards.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from content_farm.review.client import Call, CallResult
from content_farm.review.deck_patch import PatchError, apply_patch
from content_farm.review.sentences import deck_sentences
from content_farm.review.touch_guard import named_in

SMALL_SHARE = 0.10
MAX_SENTENCES = 14
TIMEOUT_S = 600
_NEEDS_TOOLS = re.compile(r"來源|sources\.json|WebFetch|WebSearch|查證|查核員.*無|補上.*出處|出處|新增.{0,6}(句|張|投影片)|拆(成|開)")
PATCH = {"type": "object", "additionalProperties": False, "required": ["replace", "deletes", "summary"],
         "properties": {"replace": {"type": "object", "additionalProperties": {"type": "string"}},
                        "deletes": {"type": "array", "items": {"type": "string"}},
                        "summary": {"type": "string"},
                        "needs_tools": {"type": "boolean", "description": "true when the fix cannot be done without "
                                        "looking something up, adding a source, a sentence or a slide"}}}


def quick_enabled() -> bool:
    """``CF_QUICK_PATCH=0`` always runs the full agent (before / after comparisons)."""
    return os.environ.get("CF_QUICK_PATCH", "1").strip() != "0"


def eligibility(deck: dict[str, Any], plan: dict[str, Any], step: str = "deck") -> tuple[bool, str]:
    """(ok, why not). Small = every fix names sentences, they are < 10% of the script, and none needs a tool."""
    if plan.get("prompt_only"):
        return False, "prompt-only rework (media.prompt, not narration)"
    named = named_in(plan, step)
    if named.open or not named.sentence_ids:
        return False, "a fix names no sentence (structure-level)"
    if named.titles or named.thumbnail or named.description:
        return False, "title / thumbnail / description fix"
    sentences = deck_sentences(deck)
    known = {s.id for s in sentences}
    if not named.sentence_ids <= known:
        return False, "fix names sentences the deck no longer has"
    if len(named.sentence_ids) > min(MAX_SENTENCES, SMALL_SHARE * len(sentences)):
        return False, f"{len(named.sentence_ids)} of {len(sentences)} sentences named (over {SMALL_SHARE:.0%})"
    for fix in (plan.get("steps", {}).get(step) or {}).get("fixes", []):
        if fix.get("rerouted_from") or _NEEDS_TOOLS.search(f"{fix.get('problem', '')} {fix.get('fix', '')}"):
            return False, "a fix needs a source, a new sentence or a rerouted step"
    return True, ""


def _context(sentences: list, wanted: set[str]) -> str:
    rows = []
    for index, sentence in enumerate(sentences):
        if sentence.id not in wanted:
            continue
        before = sentences[index - 1].text if index else "（開頭）"
        after = sentences[index + 1].text if index + 1 < len(sentences) else "（結尾）"
        rows.append(f"- {sentence.id}（{sentence.slide_id}）｜現文：{sentence.text}｜前一句：{before}｜後一句：{after}")
    return "\n".join(rows)


def build_prompt(deck: dict[str, Any], plan: dict[str, Any], *, common: str, rules: str, step: str = "deck") -> str:
    sentences = deck_sentences(deck)
    named = named_in(plan, step).sentence_ids
    fixes = [f"- {', '.join(fix['scope']['sentence_ids']) or '—'}：{fix.get('problem')} → {fix.get('fix')}"
             for fix in (plan.get("steps", {}).get(step) or {}).get("fixes", [])]
    task = ("任務：小幅修改講稿（退回重做）。你沒有任何工具，也不需要讀檔：要改的句子都在下面。只輸出一個 JSON：\n"
            '{"replace": {"句子id": "新的整句（含句末標點）"}, "deletes": ["要刪的句子id"], "summary": "改了什麼", "needs_tools": false}\n'
            "- replace 與 deletes 只能用下面「要改的句子」的 id；沒被點名的句子一個字都不能動。\n"
            "- 一句換一句：不要拆成兩句、不要新增句子；語氣、長度貼近原句，數字與限定詞（據報導、預估、規劃）照修改建議。\n"
            "- 新句子不要引入沒有來源的新說法。如果非得查資料、補來源、加句子或加投影片才改得了，needs_tools 填 true，"
            "replace 與 deletes 留空（會改由有工具的 agent 處理）。")
    return "\n\n".join(p for p in (common, task, rules, "修改清單：\n" + "\n".join(fixes),
                                   "要改的句子（id｜現文｜前後文）：\n" + _context(sentences, set(named))) if p)


def strict_check(run_dir: Path, python: str, repo: Path) -> list[str]:
    """``deck_to_script.py --strict`` — the same gate the agent runs; [] when it passes."""
    done = subprocess.run([python, str(repo / "scripts" / "deck_to_script.py"), "--run-dir", str(run_dir), "--strict"],
                          capture_output=True, text=True, timeout=300, env={**os.environ, "PYTHONPATH": str(repo / "src")})
    return [] if done.returncode == 0 else [(done.stderr or done.stdout).strip()[:300] or f"exit {done.returncode}"]


def quick_deck(run_dir: Path, plan: dict[str, Any], *, call_for: Callable[[str], CallResult],
               common: str, rules: str, verify: Callable[[Path], list[str]]) -> tuple[CallResult | None, str]:
    """(result, "") when applied and verified; (call result or None, why) when the caller must run the full agent."""
    deck_path = run_dir / "deck.json"
    before = deck_path.read_text(encoding="utf-8")
    deck = json.loads(before)
    ok, why = eligibility(deck, plan)
    if not ok:
        return None, why
    result = call_for(build_prompt(deck, plan, common=common, rules=rules))
    if not result.ok or not result.output:
        return result, "quick call failed: " + "; ".join(result.errors)[:200]
    out = result.output
    if out.get("needs_tools"):
        return result, "the answer says it needs tools"
    changes, deletes = dict(out.get("replace") or {}), list(out.get("deletes") or [])
    named = named_in(plan, "deck").sentence_ids
    stray = sorted((set(changes) | set(deletes)) - named)
    if stray or not (changes or deletes):
        return result, f"patch names unnamed sentence(s) {stray}" if stray else "empty patch"
    try:
        patched = apply_patch(deck, changes, deletes)
    except PatchError as exc:
        return result, f"patch refused: {exc}"
    deck_path.write_text(json.dumps(patched.deck, ensure_ascii=False, indent=2), encoding="utf-8")
    problems = verify(run_dir)
    if problems:
        deck_path.write_text(before, encoding="utf-8")
        return result, "deck_to_script --strict failed: " + problems[0]
    receipt = {"files": ["deck.json", "script.json"], "summary": str(out.get("summary", ""))[:300],
               "fixed": sorted(set(changes) | set(deletes))}
    return replace(result, output=receipt), ""


def build_call(rid: str, prompt: str, tier: Any, run_dir: Path) -> Call:
    return Call(rid, prompt, PATCH, tier.model, tier.effort, tools=(), cwd=run_dir, timeout_s=TIMEOUT_S, retries=1)
