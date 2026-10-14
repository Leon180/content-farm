---
name: prepareupload
description: Prepare video for YouTube upload — orientation-aware (portrait for shorts, landscape for long-form) + metadata template + chapter markers
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir, optional — defaults to latest run]"
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

1. **Respects declared orientation** — reads `script.json`'s `orientation` field:
   - `landscape` (long-form) → keeps the video as-is (NO portrait conversion)
   - `portrait` (short-form, default) → converts if source is landscape, else copies
2. **Generates thumbnail** from video keyframe
3. **Creates `youtube_meta.json`** with editable metadata, including:
   - `chapters[]` list (empty for short-form, populated for long-form)
   - Description with chapter timestamps pre-pended (long-form only)

## Verify

After completion, check:

1. `$0/upload/` directory was created
2. `$0/upload/*_final.mp4` exists
3. `$0/upload/youtube_meta.json` exists with editable fields

### Short-form validation

- [ ] Video dimensions are 1080×1920 (portrait)
- [ ] `meta["chapters"]` is an empty list `[]`
- [ ] Description does NOT contain `章節：` header

### Long-form validation

- [ ] Video dimensions are 1920×1080 (landscape, NOT converted to portrait)
- [ ] `meta["chapters"]` has at least 3 entries
- [ ] First entry has `timestamp: "0:00"` (YouTube chapter-marker requirement)
- [ ] Description starts with `章節：` block on the first line
- [ ] Chapter timestamps appear on their own lines in ascending order
- [ ] Descriptions longer than 60 minutes use `H:MM:SS` format; shorter use `M:SS`

**If any long-form validation fails:**
- Fewer than 3 chapters → YouTube will not parse any markers; add more chapters in prescript or skip the chapter feature
- First timestamp not 0:00 → edit prescript and rerun `script --from-prescript` (timestamps get normalized)
- Wrong video dimensions → assembly was run with the wrong orientation; delete `assembly/draft.mp4` and re-run `/project:assembly`

## Next Step

Tell the user:
1. Review and edit `$0/upload/youtube_meta.json`
2. For long-form: confirm the chapter titles in description are accurate + match the content
3. Run `/project:upload $0`

On YouTube Studio after upload, the chapter markers will appear below the video progress bar only when: description starts with `0:00` on its own line (with optional preceding label), at least 3 timestamps total, all in ascending order.
