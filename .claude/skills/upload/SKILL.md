---
name: upload
description: Upload video to YouTube using prepared metadata template
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir]"
disable-model-invocation: true
---

Upload to YouTube: $ARGUMENTS

## Prerequisites

- `$0/upload/youtube_meta.json` must exist (run /project:prepareupload first)
- `$0/upload/*_portrait.mp4` must exist
- YouTube credentials configured in `.env` (`CF_YOUTUBE_CLIENT_ID`, `CF_YOUTUBE_CLIENT_SECRET`, `CF_YOUTUBE_REFRESH_TOKEN`)

## Pre-flight Check

Read `$0/upload/youtube_meta.json` and show the user:
- Title
- Privacy status
- Tags

Confirm before proceeding.

## Execution

```bash
.venv/bin/python scripts/run_stage.py --stage youtube --run-dir "$0"
```

## Verify

Check the output for:
1. YouTube video URL (https://youtu.be/...)
2. Video ID
3. Privacy status confirmation
