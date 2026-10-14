---
name: prescript
description: Generate a preliminary script outline (大綱初稿) for user review before full script generation. Supports both short-form and long-form videos.
allowed-tools: Read, Write, Glob, Bash
argument-hint: "[topic] [--run-dir path] [--video-length short|medium|long] [--genre knowledge|listicle_ranking|news_analysis|story_mystery]"
---

Generate a preliminary outline for: $ARGUMENTS

## Argument Parsing

Parse these flags from $ARGUMENTS (positional topic, the rest as flags):

- `--run-dir <path>` — run directory (if absent, find or create one)
- `--video-length <short|medium|long>` — default `short` if unspecified
- `--genre <...>` — long-form only; ignored for short
- `--orientation <portrait|landscape>` — default `portrait` for short, `landscape` for long/medium

## Setup

1. If no `--run-dir`, find the most recent `output/` run matching the topic, or create `output/YYYYMMDD_HHMMSS_<safe_topic>/`
2. If `<run_dir>/research.md` exists, read it for factual grounding (required)

---

## Short-Form Mode (default: `--video-length short`)

### Read Supporting Files

- `<run_dir>/research.md` (required)
- For narration style and structures: read [../script/prompts.md](../script/prompts.md)

### Generate Outline

Produce:

1. **Title options** — 2-3 candidates (hook-style, under 25 chars)
2. **Narrative structure** — one of:
   - 懸念揭曉型: Hook → 鋪墊 → 揭曉
   - 誤導反轉型: Hook → 展開 → 反轉
   - 層層遞進型: Hook → 升級 → 炸裂
3. **Scene breakdown** — 2-3 scenes totaling 30-90s. Each scene:
   - `purpose` (e.g. "Hook: 提出意外事實")
   - `key_points` (bullets from research)
   - `narration_direction` (2-3 sentences on tone/content — not full narration)
   - `visual_ideas`
   - `duration_seconds`
4. **Ending approach** — CTA / reflection / cliffhanger

### Output JSON (short-form)

Write `<run_dir>/prescript.json`:

```json
{
  "topic": "...",
  "title_options": ["...", "...", "..."],
  "narrative_structure": "層層遞進型",
  "scenes": [
    {
      "scene_number": 1,
      "purpose": "Hook",
      "key_points": ["..."],
      "narration_direction": "...",
      "visual_ideas": ["..."],
      "duration_seconds": 15
    }
  ],
  "ending_approach": "...",
  "total_duration_seconds": 50,
  "research_sources": ["..."]
}
```

### After Output (short-form)

Tell the user:
1. Review and edit `prescript.json` — adjust structure, reorder scenes, add/remove key points
2. When satisfied, run `/project:script --run-dir <path>` to generate the full script

---

## Long-Form Mode (`--video-length medium|long`)

Long-form videos use **chapter-level outlines** instead of scene-level. This is an explicit editorial gate: you review/edit chapters (structure, order, timings, hooks) **before** Claude spends money expanding every scene.

### Read Supporting Files

- `<run_dir>/research.md` (required — should have 18+ sources for long-form)
- `<run_dir>/research_chapters.md` if present (chapter-angle mapping)

### Generate Chapter Outline via Python

Long-form prescript uses the Python generator's cheap chapter-outline phase. **Run this command:**

```bash
cd /Users/lileon/project/content-farm && \
python -c "
import asyncio, json
from pathlib import Path
from content_farm.config import Settings
from content_farm.llm.cache import FileCache
from content_farm.llm.client import LLMClient
from content_farm.script_gen.generator import ScriptGenerator
from content_farm.script_gen.schemas import ScriptRequest
from content_farm.types import GenreTemplate, Orientation, Tone, VideoLength

async def run():
    settings = Settings()
    llm = LLMClient(api_key=settings.anthropic_api_key.get_secret_value())
    gen = ScriptGenerator(llm=llm, cache=FileCache(settings.cache_dir), settings=settings)
    req = ScriptRequest(
        topic='<TOPIC>',
        keywords=<KEYWORDS_TUPLE>,
        video_length=VideoLength.<LONG or MEDIUM>,
        tone=Tone.EDUCATIONAL,
        orientation=Orientation.LANDSCAPE,
        genre=GenreTemplate.<GENRE>,
    )
    outline = await gen.generate_chapter_outline_only(req)
    await llm.close()
    payload = outline.model_dump()
    payload['topic'] = req.topic
    payload['mode'] = 'chapter_outline'
    payload['orientation'] = req.orientation.value
    payload['genre'] = req.genre.value
    Path('<RUN_DIR>/prescript.json').write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    print(f\"Chapters: {len(outline.chapters)}\")

asyncio.run(run())
"
```

Fill in `<TOPIC>`, `<KEYWORDS_TUPLE>`, `<LONG/MEDIUM>`, `<GENRE>`, `<RUN_DIR>` from parsed arguments.

Alternatively, use the helper script for a cleaner invocation:

```bash
python scripts/try_chapter_outline.py \
  --topic "<topic>" \
  --keywords <kw1> <kw2> \
  --length long --genre <genre>
```

Then persist the output to `<run_dir>/prescript.json`.

### Output JSON (long-form chapter outline)

The Python generator produces this shape:

```json
{
  "topic": "...",
  "mode": "chapter_outline",
  "orientation": "landscape",
  "genre": "knowledge",
  "video_title": "...",
  "description": "...",
  "chapters": [
    {
      "chapter_number": 1,
      "title": "...",
      "summary": "...",
      "duration_seconds": 75,
      "key_points": ["...", "...", "..."],
      "hook": "...",
      "payoff": "...",
      "start_timestamp": 0.0
    }
  ],
  "tags": ["..."],
  "sources": []
}
```

**Rules (enforced by the generator but worth knowing when editing):**
- Chapter 1 `start_timestamp` must be `0.0` (YouTube chapter markers require this)
- Each subsequent chapter's `start_timestamp` = previous `start_timestamp + duration_seconds`
- If you manually reorder or retime chapters, recompute timestamps — the script stage will re-normalize but warnings are nicer when the file is already correct

### After Output (long-form)

Tell the user:

1. **Review `prescript.json`**:
   - Are the chapters in the right order? Merge / split / reorder as needed.
   - Are the hooks punchy? Does each payoff actually pay something off?
   - Are the durations balanced? (60-180s per chapter is the target)
   - Does the total duration sit in 8-15 min? (algorithm sweet spot)
2. **Edit freely.** After editing, if you changed durations or reordered, recompute `start_timestamp` values.
3. When satisfied, expand to full script:
   ```bash
   python scripts/generate_script.py --from-prescript <run_dir>
   ```
   This writes `<run_dir>/script.json` with every scene's full narration and `b_roll_keywords`.

---

## Mode Detection (for downstream skills)

Other skills tell short-form vs long-form prescript apart by structure:

- Has `scenes[]` (no `chapters`) → short-form, handled by Claude-level `/project:script` flow
- Has `chapters[]` → long-form, expand via `python scripts/generate_script.py --from-prescript`
