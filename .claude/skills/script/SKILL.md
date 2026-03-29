---
name: script
description: Generate a zh-TW video script based on research. Outputs script.json and storyboard.txt.
allowed-tools: Read, Write, Glob
argument-hint: "[topic] [--run-dir path]"
disable-model-invocation: true
---

Generate a video script for: $ARGUMENTS

## Setup

1. Parse arguments: extract topic and optional `--run-dir` path
2. If no `--run-dir` specified, find the most recent run directory in `output/` that matches the topic
3. If no run directory exists, create one: `output/YYYYMMDD_HHMMSS_<safe_topic>/`

## Read Supporting Files

- For narration style rules and narrative structures, read the [prompts guide](prompts.md)
- For hook formulas and retention data, read the [hooks reference](hooks.md)
- For LLM prompt templates by content type, read the [generation prompts](generation_prompts.md)
- For the exact JSON schema, read the [schema reference](schema.md)
- If `<run_dir>/research.md` exists, read it for factual grounding
- If `<run_dir>/prescript.json` exists, use it as the structural foundation

## Script Generation

### If prescript.json exists (recommended flow):

1. **Read prescript.json** — use its structure, scene breakdown, and key points as the skeleton
2. **Read research brief** — ground all facts in `research.md`
3. **Expand narration** — write full narration for each scene based on the outline's direction
4. **Generate visual hints** with English keywords for stock footage
5. **Use the selected title** from prescript.json (or user's edited version)
6. **Set sources** — ONLY real URLs from research.md

### If no prescript.json (standalone mode):

1. **Read research brief** — use ONLY facts and sources from `research.md`
2. **Choose narrative structure** (from prompts.md):
   - 懸念揭曉型: Hook → 鋪墊 → 揭曉
   - 誤導反轉型: Hook → 展開 → 反轉
   - 層層遞進型: Hook → 升級 → 炸裂
3. **Generate outline** — 2-3 scenes for short-form (30-90s total)
4. **Write full narration** per scene following the rules in prompts.md
5. **Generate visual hints** with English keywords for stock footage
6. **Set sources** — ONLY real URLs from research.md

## Output

Write two files to the run directory:

1. **`script.json`** — Following the exact schema in schema.md
2. **`storyboard.txt`** — Human-readable version with scene timings

## TTS / Subtitle Number Handling

Numbers in narration must be written in **Chinese characters** for correct TTS pronunciation:
- 2031 → 二零三一
- 2028 → 二零二八
- 500克 → 五百克
- 10克 → 十克

Subtitles will be corrected back to Arabic numerals in a separate step before assembly.

## Quality Checklist

- [ ] Hook type selected from hooks.md (Pattern Interrupt+Question / Curiosity Gap / Transformation / Specific Data)
- [ ] First 1s has visual/text interrupt; first 3s has question or curiosity gap
- [ ] Every factual claim has a source from research.md
- [ ] Sources array contains ONLY real URLs from research
- [ ] Narration uses spoken zh-TW, not written Chinese
- [ ] Numbers written in Chinese characters for TTS (二零三一, not 2031)
- [ ] Visual hint keywords are in English
- [ ] Total duration 30-90 seconds for short-form
- [ ] No filler: 「其實」「基本上」「事實上」「總之」「然而」
- [ ] No greetings: 「大家好」「歡迎觀看」
- [ ] Includes at least 1 specific statistic or concrete result
- [ ] No dead zones >5 seconds without new information
