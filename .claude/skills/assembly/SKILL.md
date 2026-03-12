---
name: assembly
description: Assemble final video from voice + visual + subtitles using FFmpeg
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir] [--template]"
disable-model-invocation: true
---

Assemble the video in: $ARGUMENTS

## Prerequisites

- `$0/script.json` must exist
- `$0/audio/scene_*.mp3` must exist
- `$0/visual/scene_*.mp4` must exist

## Execution

Parse arguments. If `--template` is specified, use template mode (blank bg + credits):

```bash
# Standard assembly
.venv/bin/python scripts/run_stage.py --stage assembly --run-dir "$0"

# Template mode (materials pipeline)
.venv/bin/python scripts/run_stage.py --stage template --run-dir "$0"
```

## Verify

Check `$0/assembly/` for the output `.mp4` file.
