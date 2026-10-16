"""Launch fixes for the kyubi deck (policy review 2026-10, C3): python edit_yokai_deck.py <run-dir>

Idempotent: reads deck.before.json (written on first run) and rewrites deck.json. No narration
changes, so no re-voicing.
- s06: the AI picture says 「九尾」 but shows ~4 tails. Seven re-generations (Z-Image seeds
  1/2/3/7/11/23/42) drew 5–7 tails, never nine, so the picture stays (its baked Wan motion is
  reused) and the screen says so next to the 「AI 示意圖」 badge.
- s25/s26: marked as the channel's own reading (take).
"""
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
before = run / "deck.before.json"
if not before.is_file():
    before.write_text((run / "deck.json").read_text(encoding="utf-8"), encoding="utf-8")
deck = json.loads(before.read_text(encoding="utf-8"))
slides = {s["id"]: s for sec in deck["sections"] for s in sec["slides"]}
slides["s06"]["media"]["ai_note"] = "尾數為示意，原典記載九尾"
for slide_id in ("s25", "s26"):
    slides[slide_id]["take"] = True
(run / "deck.json").write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("ok")
