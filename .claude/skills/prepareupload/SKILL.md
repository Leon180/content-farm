---
name: prepareupload
description: Prepare video for YouTube upload (portrait conversion + metadata template)
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir]"
disable-model-invocation: true
---

Prepare YouTube upload for: $ARGUMENTS

## Prerequisites

- `$0/script.json` must exist
- `$0/assembly/*.mp4` must exist (run /project:assembly first)

## Execution

```bash
.venv/bin/python scripts/run_stage.py --stage prepareupload --run-dir "$0"
```

## What it does

1. **Detects orientation** — probes video dimensions
   - Already portrait (h > w): burns title overlay only (`burn_title_overlay`)
   - Landscape: converts to portrait + burns title (`convert_to_portrait`)
2. **Title overlay** — video title from script.json, yellow text, centered in top area
3. **Generates thumbnail** from video keyframe
4. **Creates `youtube_meta.json`** with editable metadata

## Verify

After completion, check:
1. `$0/upload/` directory was created
2. `$0/upload/*_final.mp4` (portrait input) or `*_portrait.mp4` (landscape input) exists
3. `$0/upload/youtube_meta.json` exists with editable fields

## Next Step

Tell the user to review and edit `$0/upload/youtube_meta.json`, then run `/project:upload $0`.
