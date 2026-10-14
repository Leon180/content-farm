---
name: drive
description: Upload run directory to Google Drive, then delete local copy
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir, optional — defaults to latest run]"
disable-model-invocation: true
---

Upload to Drive and remove local files for: $ARGUMENTS

## Prerequisites

- Drive credentials configured in `.env` (`CF_DRIVE_CREDENTIALS_PATH`, `CF_DRIVE_FOLDER_ID`)
- Run `/project:upload` (YouTube) first — this is the final cleanup step

## Warning

**This stage deletes the local run directory after a successful upload.**
It is irreversible. Confirm the Drive folder link is accessible before running.

## Execution

```bash
.venv/bin/python scripts/run_stage.py --stage drive --run-dir "$0"
```

## Verify

1. Check the output for the Drive folder link
2. Open the link and confirm files are present in Google Drive
3. Local run directory will no longer exist after completion
