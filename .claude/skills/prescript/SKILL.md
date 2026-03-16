---
name: prescript
description: Generate a preliminary script outline (大綱初稿) for user review before full script generation
allowed-tools: Read, Write, Glob
argument-hint: "[topic] [--run-dir path]"
---

Generate a preliminary outline for: $ARGUMENTS

## Setup

1. Parse arguments: extract topic and optional `--run-dir` path
2. If no `--run-dir` specified, find the most recent run directory in `output/` that matches the topic
3. If no run directory exists, create one: `output/YYYYMMDD_HHMMSS_<safe_topic>/`

## Read Supporting Files

- Read `<run_dir>/research.md` for factual grounding (required)
- For narration style and structures, read the [prompts guide](../script/prompts.md)

## Generate Outline

Based on research.md, produce a structured outline with:

1. **Title options** — 2-3 title candidates (hook-style, under 25 chars)
2. **Narrative structure** — which type to use:
   - 懸念揭曉型: Hook -> 鋪墊 -> 揭曉
   - 誤導反轉型: Hook -> 展開 -> 反轉
   - 層層遞進型: Hook -> 升級 -> 炸裂
3. **Scene breakdown** — for each scene (2-3 scenes, 30-90s total):
   - Scene purpose (e.g. "Hook: 提出意外事實")
   - Key points to cover (bullet list from research)
   - Rough narration direction (2-3 sentences describing tone/content, NOT full narration)
   - Visual ideas (what footage/images would work)
   - Estimated duration (seconds)
4. **Ending approach** — how to close (call to action, reflection, cliffhanger)

## Output

Write `<run_dir>/prescript.json` with this structure:

```json
{
  "title_options": ["Option A", "Option B", "Option C"],
  "narrative_structure": "層層遞進型",
  "scenes": [
    {
      "scene_number": 1,
      "purpose": "Hook: introduce surprising fact",
      "key_points": ["fact 1", "fact 2"],
      "narration_direction": "Start with a question...",
      "visual_ideas": ["factory interior", "printing press"],
      "duration_seconds": 15
    }
  ],
  "ending_approach": "Reflection on how this invention changed daily life",
  "total_duration_seconds": 50
}
```

## After Output

Tell the user:
1. Review and edit `prescript.json` — adjust structure, reorder scenes, add/remove key points
2. When satisfied, run `/project:script --run-dir <path>` to generate the full script
