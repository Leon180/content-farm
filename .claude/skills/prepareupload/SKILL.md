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

## Verify

After completion, check:
1. `$0/upload/` directory was created
2. `$0/upload/*_portrait.mp4` exists (portrait 1080x1920 video)
3. `$0/upload/youtube_meta.json` exists with editable fields

## Next Step

Tell the user to review and edit `$0/upload/youtube_meta.json`, then run `/project:upload $0`.
