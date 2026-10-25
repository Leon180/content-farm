"""The one automatic slideshow fix at the deck step (quality v5).

After the deck producer has written ``deck.json`` (and it kept the channel rules), score the pages
(``explainer.slideshow_risk``). If too many read like a slide show, hand the producer a short request list ONCE
(``review/slideshow_risk.json`` records that it happened); if the redo fails or breaks a rule, the first deck is
restored. Either way the run goes on: this never blocks (Leon 2026-10-24: 不擋 run，自動修一次).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from content_farm.explainer.deck import Deck
from content_farm.explainer.slideshow_risk import DeckRisk, producer_note, score_deck

REPORT = Path("review") / "slideshow_risk.json"


def report_path(run_dir: Path) -> Path:
    return run_dir / REPORT


def _load(run_dir: Path) -> dict:
    path = report_path(run_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _write(run_dir: Path, data: dict) -> None:
    path = report_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _score(run_dir: Path) -> DeckRisk | None:
    path = run_dir / "deck.json"
    if not path.is_file():
        return None
    try:
        return score_deck(Deck.model_validate_json(path.read_text(encoding="utf-8")))
    except ValueError:
        return None      # an invalid deck is the schema check's problem, not ours


def maybe_redo(run_dir: Path, *, enabled: bool, produce: Callable[[str], str | None],
               violations: Callable[[], list[str]], log: Callable[[str], None]) -> None:
    """Score ``deck.json``; when over the limit and no request was made yet, run ``produce(note)`` once.
    ``produce`` returns a failure text or None; ``violations`` lists channel-rule breaks of the new deck."""
    if not enabled:
        return
    risk = _score(run_dir)
    if risk is None:
        return
    previous = _load(run_dir)
    data = {**previous, "before": previous.get("before") or risk.to_json(), "latest": risk.to_json()}
    note = producer_note(risk)
    if not note or previous.get("requested"):
        _write(run_dir, data)
        return
    deck_path = run_dir / "deck.json"
    original = deck_path.read_text(encoding="utf-8")
    data = {**data, "before": risk.to_json(), "requested": True, "request": note}
    log(f"✎ deck: 投影片感 {len(risk.risky)} 頁超標（平均 {risk.mean_score:.0f} 分）→ 請 agent 修一次")
    failure = produce(note)
    broken = violations() if failure is None else []
    after = _score(run_dir) if failure is None and not broken else None
    if failure is not None or broken or after is None:
        deck_path.write_text(original, encoding="utf-8")        # keep the first deck
        data = {**data, "outcome": "restored", "why": failure or "；".join(broken) or "deck 不合法"}
        log(f"✗ deck: 投影片感修改作廢，還原（{data['why'][:120]}）")
    else:
        data = {**data, "outcome": "fixed" if after.mean_score < risk.mean_score else "unchanged",
                "after": after.to_json(), "latest": after.to_json()}
        log(f"✓ deck: 投影片感 {risk.mean_score:.0f} → {after.mean_score:.0f} 分，超標頁 {len(risk.risky)} → {len(after.risky)}")
    _write(run_dir, data)
