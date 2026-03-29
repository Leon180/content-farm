---
name: archive
description: Upload completed outputs to Google Drive and delete local copies
allowed-tools: Bash, Read, Glob
argument-hint: "[--dry-run]"
disable-model-invocation: true
---

Archive completed outputs to Google Drive: $ARGUMENTS

## Prerequisites

- Google Drive credentials configured (`CF_DRIVE_CREDENTIALS_PATH`, `CF_DRIVE_FOLDER_ID`)
- At least one `output/*/upload/` directory exists

## Execution

### Dry run (list what would be archived):
```bash
.venv/bin/python scripts/archive_outputs.py --dry-run
```

### Real run:
```bash
.venv/bin/python scripts/archive_outputs.py
```

## What it does

1. Scans `output/` for directories containing an `upload/` subfolder
2. Uploads each to Google Drive (reuses existing Drive uploader)
3. Deletes the local directory after successful upload
4. Prints summary of archived count and freed space
