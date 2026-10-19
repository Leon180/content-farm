---
name: news-weekly
description: Write deck.json for the weekly HN 快報 long video (晶片貓) from weekly_plan.md — one chapter per story, deeper than the Shorts, every fact from the originals that were read. Use for /news-weekly, "寫 HN 週整理", or when `produce.py news weekly` stops at the deck step.
allowed-tools: Read, Write, Edit, Glob, Bash
argument-hint: "--run-dir output/hn-weekly-<YYYY-Www>"
---

Write the weekly HN 快報 deck for: $ARGUMENTS

## Read first

1. `<run_dir>/weekly_plan.md` and `news_weekly.json` — the 3–5 stories, their Shorts, sources and read times.
2. For each story: its cached original (path in the plan). Re-read it — the long video says more than the
   Short did, and every added fact must come from the original (or another primary source you read; add it
   to `deck.sources` with the URL). Discussion threads are leads only.
3. `.claude/skills/deck/SKILL.md` + `writing_rules.md` — the deck schema and writing rules apply unchanged.
4. `src/content_farm/production/news/glossary.yaml` — reuse the analogies; add new terms there.

## Shape

- Section 1「本週重點」: 2–3 slides — the week's thread in one sentence, the list of stories.
- One section per story (= one YouTube chapter), 4–7 slides each, in the plan's order:
  what happened → background → numbers with their scope → the Taiwan angle (or "原文沒有台灣數字") →
  晶片貓觀點 (extend the Short's take with one more reason or counter-argument).
- Last section「下週看什麼」: 1–2 slides; no investment advice.
- Target length from the plan (420–660 s; ≥ 480 s when the material supports it).
- `deck.sources`: each story's read original (same URL as in the plan) + anything else you read.

## Check

```bash
PYTHONPATH=src .venv/bin/python scripts/deck_to_script.py --run-dir <run_dir> --strict
PYTHONPATH=src .venv/bin/python scripts/news.py weekly-check --run-dir <run_dir>
```

Then `python scripts/produce.py news weekly --week <YYYY-Www>` renders slides and stops at the deck gate.
