---
name: assembly
description: Assemble final video from voice + visual + subtitles using FFmpeg
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir] [--template|--timeline]"
disable-model-invocation: true
---

Assemble the video in: $ARGUMENTS

## Prerequisites

- `$0/script.json` must exist
- `$0/audio/scene_*.mp3` must exist

**Standard mode:** `$0/visual/scene_*.mp4` must exist
**Timeline mode:** `$0/visual/MM:SS~MM:SS.mp4` clips must exist + `$0/audio/full.mp3`

## Execution

Parse arguments:

```bash
# Standard assembly (scene-based)
.venv/bin/python scripts/run_stage.py --stage assembly --run-dir "$0"

# Timeline assembly (from timeline-named clips)
.venv/bin/python scripts/run_stage.py --stage assembly_timeline --run-dir "$0"

# Template mode (materials pipeline)
.venv/bin/python scripts/run_stage.py --stage template --run-dir "$0"
```

## Verify

Check `$0/assembly/draft.mp4` (timeline) or `$0/assembly/*.mp4` (standard).
