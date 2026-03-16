---
name: visual
description: Download candidate stock footage clips for all scenes
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir] [--blank|--timeline]"
disable-model-invocation: true
---

Download visual clips for the video in: $ARGUMENTS

## Prerequisites

- `$0/script.json` must exist

## Execution

Parse arguments:

```bash
# Stock footage mode (default) — downloads multiple candidates per keyword
.venv/bin/python scripts/run_stage.py --stage visual --run-dir "$0"

# Timeline mode — uses subtitles.srt time ranges for clip naming (requires voice first)
.venv/bin/python scripts/run_stage.py --stage visual_timeline --run-dir "$0"

# Blank mode (materials — black background)
.venv/bin/python scripts/run_stage.py --stage blank_visual --run-dir "$0"
```

## Verify

After completion, check:

**Stock mode:**
1. `$0/visual/scene_*_*.mp4` clip files exist (multiple per scene)
2. `$0/visual/clips_manifest.json` was created

**Timeline mode:**
1. `$0/visual/MM:SS~MM:SS_*.mp4` clip files exist (timeline-named candidates)
2. `$0/visual/timeline.md` was created
3. `$0/visual/clips_manifest.json` was created

## Next Step

**Stock mode:** Edit clips_manifest.json, then run `/project:concatscene`
**Timeline mode:** Review timeline.md, rename chosen clips to `MM:SS~MM:SS.mp4` (remove index), then run `/project:assembly`
