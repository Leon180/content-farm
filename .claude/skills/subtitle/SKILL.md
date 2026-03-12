---
name: subtitle
description: Generate subtitles from script + voice timing
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir]"
disable-model-invocation: true
---

Generate subtitles for: $ARGUMENTS

## Prerequisites

- `$0/script.json` must exist
- `$0/audio/scene_*.mp3` must exist (run /project:voice first)

## Execution

```bash
.venv/bin/python scripts/run_stage.py --stage subtitle --run-dir "$0"
```

## Verify

Check `$0/subtitles/` for `.srt` or `.vtt` files.
