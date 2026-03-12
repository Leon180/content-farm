---
name: upload
description: Upload run directory to Google Drive
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir]"
disable-model-invocation: true
---

Upload to Drive: $ARGUMENTS

## Prerequisites

- Drive credentials configured in `.env` (`CF_DRIVE_CREDENTIALS_PATH`, `CF_DRIVE_FOLDER_ID`)
- Run directory must contain the files to upload

## Execution

```bash
.venv/bin/python scripts/run_stage.py --stage drive --run-dir "$0"
```

## Verify

Check the output for the Drive folder link.
