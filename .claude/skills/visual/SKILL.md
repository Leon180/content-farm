---
name: visual
description: Source stock footage or generate blank visuals for all scenes
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir] [--blank]"
disable-model-invocation: true
---

Generate visuals for the video in: $ARGUMENTS

## Prerequisites

- `$0/script.json` must exist

## Execution

Parse arguments. If `--blank` is specified, use blank visual stage (for materials mode):

```bash
# Stock footage mode (default)
.venv/bin/python scripts/run_stage.py --stage visual --run-dir "$0"

# Blank mode (materials — black background)
.venv/bin/python scripts/run_stage.py --stage blank_visual --run-dir "$0"
```

## Verify

After completion, check:
1. `$0/visual/scene_*.mp4` files exist
2. `$0/visual_artifact.json` was created
