---
name: script
description: Generate a zh-TW video script based on research. Outputs script.json and storyboard.txt. Supports short-form (Claude-written) and long-form (Python-expanded from chapter prescript).
allowed-tools: Read, Write, Glob, Bash
argument-hint: "[topic] [--run-dir path]"
disable-model-invocation: true
---

Generate a video script for: $ARGUMENTS

## Setup

1. Parse arguments: extract topic and optional `--run-dir` path
2. If no `--run-dir` specified, find the most recent run directory in `output/` that matches the topic
3. If no run directory exists, create one: `output/YYYYMMDD_HHMMSS_<safe_topic>/`

## Mode Detection

If `<run_dir>/prescript.json` exists, inspect its shape:

- **Has `chapters[]` (long-form)** → see "Long-Form: Expand Approved Chapters" below.
- **Has `scenes[]` (short-form)** → see "Short-Form: Write From Scene Outline" below.
- **Missing** → see "Short-Form Standalone" below.

## Long-Form: Expand Approved Chapters

The long-form path does **not** use Claude to write the script. The chapter outline was already reviewed in the prescript step; now the Python generator expands every chapter's scenes and narration automatically (cheaper, structured, caches deterministically).

Run:

```bash
cd /Users/lileon/project/content-farm && \
python scripts/generate_script.py --from-prescript <run_dir>
```

Optional flags forwarded to the request:
- `--length long` (auto-detected if omitted — defaults to long when `--from-prescript` is used)
- `--orientation landscape` (default for long-form)
- `--genre knowledge|listicle_ranking|news_analysis|story_mystery` (read from prescript.json if present, otherwise pass explicitly)

After the command completes, `<run_dir>/` will contain:
- `script.json` — full script; `chapters[]` + `scenes[]` each scene expanded with narration, visual_hint, and `b_roll_keywords`
- `script_summary.md` — human-readable review summary (auto-generated only for `--from-prescript` long-form runs)

### ⚠️ REVIEW GATE — STOP HERE BEFORE VOICE

**Do NOT run `/project:voice` yet.** The voice stage calls real TTS and will burn money + time even for broken narration. The user should review the script first.

Tell the user VERBATIM:

> 🛑 Script 生成完成，請先校稿再跑配音：
>
> 1. 打開 `<run_dir>/script_summary.md` 掃一遍整體節奏、章節 hook/payoff
> 2. 發現問題時直接編輯 `<run_dir>/script.json`（`script_summary.md` 只是導覽，不會回讀）
> 3. 特別檢查：
>    - 有沒有捏造的統計/日期/研究名稱（對照 research.md）
>    - 有沒有過度使用「欸」、或出現「狂/絕了」這類會過時的流行語
>    - 每章 hook 第一句能不能真的抓住注意力、payoff 有沒有收住
>    - 總時長是不是落在 5-15 min 範圍
> 4. 校稿完成後再跑 `/project:voice --run-dir <run_dir>`

Do not auto-proceed. Wait for explicit user confirmation before suggesting the next stage.

## Short-Form: Write From Scene Outline

### Read Supporting Files

- For narration style rules and narrative structures, read the [prompts guide](prompts.md)
- For hook formulas and retention data, read the [hooks reference](hooks.md)
- For LLM prompt templates by content type, read the [generation prompts](generation_prompts.md)
- For the exact JSON schema, read the [schema reference](schema.md)
- If `<run_dir>/research.md` exists, read it for factual grounding
- Read `<run_dir>/prescript.json` — use its structure as the skeleton

### Steps

1. **Read prescript.json** — use its structure, scene breakdown, and key points as the skeleton
2. **Read research brief** — ground all facts in `research.md`
3. **Expand narration** — write full narration for each scene based on the outline's direction
4. **Generate visual hints** with English keywords for stock footage
5. **Use the selected title** from prescript.json (or user's edited version)
6. **Set sources** — ONLY real URLs from research.md

## Short-Form Standalone (no prescript.json)

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
