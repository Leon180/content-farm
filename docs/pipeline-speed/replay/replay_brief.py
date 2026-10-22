"""Offline replay of items 1-3 on 九尾狐: brief length / ids, expected output, quick-path eligibility. No LLM."""
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/Users/lileon/project/content-farm/.claude/worktrees/cf-pipeline-speed-2/src")
sys.path.insert(0, "/Users/lileon/.claude/jobs/669f978c/tmp")
from content_farm.review import producers, quick_patch, routing  # noqa: E402
from content_farm.review.brief import deck_brief  # noqa: E402
from content_farm.review.config import load_review  # noqa: E402
from content_farm.review.narrow import narrow  # noqa: E402
from content_farm.review.sentences import Sentence  # noqa: E402

BASE = Path("/Users/lileon/project/content-farm/.claude/worktrees/cf-yokai-tempo/output/yokai-kyubi-v2/review")
LINE = re.compile(r"^\[([^\]]+)\] ~\d+:\d+ (.*)$")
IDS = re.compile(r"s\d+[a-z]?\.\d+")
CONFIG = load_review()
PY = "/Users/lileon/project/content-farm/.venv/bin/python"


def sentences_of(rel: str) -> list[Sentence]:
    out, section = [], ""
    for line in (BASE / rel / "script.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif (m := LINE.match(line)):
            out.append(Sentence(m.group(1), m.group(1).rsplit(".", 1)[0], section, m.group(2), True))
    return out


def deck_of(sentences: list[Sentence]) -> dict:
    slides: dict[str, dict] = {}
    for s in sentences:
        slide = slides.setdefault(s.slide_id, {"id": s.slide_id, "narration": "", "sentence_ids": [], "_sec": s.section})
        slide["narration"] += s.text
        slide["sentence_ids"].append(s.id)
    sections: dict[str, list] = {}
    for slide in slides.values():
        sections.setdefault(slide.pop("_sec"), []).append(slide)
    return {"title": "t", "sections": [{"title": k, "slides": v} for k, v in sections.items()]}


def new_brief(rel: str, kept: list[dict], sentences: list[Sentence]) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        (run_dir / "deck.json").write_text(json.dumps(deck_of(sentences), ensure_ascii=False), encoding="utf-8")
        plan = routing.plan(kept, routing.Texts(sentences), stage="script_structure", round_no=1, default_step="deck")
        plan["reasons"] = ["replay"]
        routing.write(run_dir, "deck", plan)
        fmt = {"run_dir": run_dir, "repo": producers.REPO, "channel": "yokai", "python": PY}
        guide = deck_brief(CONFIG, "yokai", PY, str(producers.REPO), rework=True)
        return "\n\n".join(p for p in (producers.COMMON.format(**fmt), producers.TASKS_REWORK["deck"].format(**fmt), guide,
                                       producers._fixes_text(run_dir, "deck"), "完成後用結構化輸出回報寫了哪些檔。") if p)


print("== A. deck-1..5 brief (old = real prompt file; new = rebuilt from narrowed issues, rework brief)")
SEQ = {"deck-1": "script/round-1", "deck-2": "script/round-2", "deck-3": "script_structure/cycle-1/round-1",
       "deck-4": "script_structure/cycle-1/round-2", "deck-5": "script_structure/cycle-2/round-1"}
OUT = {"deck-1": 59574, "deck-2": 79542, "deck-3": 92224, "deck-4": 109206, "deck-5": 88654}
for name, rel in SEQ.items():
    sentences = sentences_of(rel)
    old_text = (BASE / "producers" / f"{name}.prompt.md").read_text(encoding="utf-8")
    old_ids = set(IDS.findall(old_text.split("這是退回重做", 1)[-1]))
    issues = json.loads((BASE / rel / "scorecard.json").read_text(encoding="utf-8"))["verdict"]["issues"]
    kept, deferred, stat = narrow(issues, sentences)
    text = new_brief(rel, kept, sentences)
    known = {s.id for s in sentences}
    ids = set(IDS.findall(text.split("這是退回重做", 1)[-1])) & known
    ratio = len(ids) / max(len(old_ids & known), 1)
    print(f"{name}: brief chars {len(old_text)} -> {len(text)} ({len(text) / len(old_text):.0%}); "
          f"distinct ids {len(old_ids & known)} ({len(old_ids & known) / len(sentences):.0%}) -> {len(ids)} ({len(ids) / len(sentences):.0%}); "
          f"issues {len(issues)} -> {len(kept)}; proportional output {OUT[name]} -> {int(OUT[name] * ratio)} tok (assumption: output ∝ ids)")

print("\n== B. quick path on the small reworks (script_facts rounds)")
CALLS = {"deck-6": ("script_facts/cycle-2/round-1", 292, 24525), "deck-7": ("script_facts/cycle-2/round-2", 133, 13083),
         "deck-14": ("script_facts/round-1", 35, 2982), "deck-15": ("script_facts/round-2", 54, 6821),
         "deck-16": ("script_facts/round-2", 153, 5332)}
for name, (rel, secs, out_tok) in CALLS.items():
    path = BASE / rel
    if not (path / "scorecard.json").is_file():
        print(name, "no scorecard", rel)
        continue
    sentences = sentences_of(rel)
    issues = json.loads((path / "scorecard.json").read_text(encoding="utf-8"))["verdict"]["issues"]
    if not issues:
        print(name, rel, "no issues")
        continue
    plan = routing.plan(issues, routing.Texts(sentences), stage="script_facts", round_no=1, default_step="deck")
    deck = deck_of(sentences)
    ok, why = quick_patch.eligibility(deck, plan)
    named = routing.plan  # noqa
    from content_farm.review.touch_guard import named_in
    n = len(named_in(plan, "deck").sentence_ids)
    avg = sum(len(s.text) for s in sentences) / len(sentences)
    patch_tok = n * (avg / 1.75 + 12) + 60
    lo, hi = 3.3 + (patch_tok + 300) / 108 + 1, 3.3 + (patch_tok + 1500) / 108 + 1
    print(f"{name} ({rel}): issues {len(issues)}, named {n}/{len(sentences)} = {n / len(sentences):.0%}, eligible={ok} {why}; "
          f"actual {secs}s / {out_tok} tok; quick est {lo:.0f}-{hi:.0f}s / ~{int(patch_tok + 300)}-{int(patch_tok + 1500)} tok")
