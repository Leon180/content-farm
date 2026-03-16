---
name: concatscene
description: Concatenate user-selected visual clips into scene videos
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir]"
disable-model-invocation: true
---

Concatenate selected clips for: $ARGUMENTS

## Prerequisites

- `$0/visual/clips_manifest.json` must exist (run /project:visual first)
- At least some clips must have `"selected": true` in the manifest
- `$0/visual/scene_*_*.mp4` clip files must exist on disk

## Execution

```bash
.venv/bin/python scripts/run_stage.py --stage concatscene --run-dir "$0"
```

## Verify

After completion, check:
1. `$0/visual/scene_XXX.mp4` files exist (one per scene)
2. `$0/visual_artifact.json` was created/updated
