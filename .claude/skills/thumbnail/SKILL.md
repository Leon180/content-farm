---
name: thumbnail
description: Generate video thumbnail from script
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir]"
disable-model-invocation: true
---

Generate thumbnail for: $ARGUMENTS

## Prerequisites

- `$0/script.json` must exist

## Execution

```bash
.venv/bin/python scripts/run_stage.py --stage thumbnail --run-dir "$0"
```

## Verify

Check `$0/thumbnails/thumbnail.png` exists.
