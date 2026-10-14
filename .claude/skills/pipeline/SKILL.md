---
name: pipeline
description: Full content pipeline from topic to uploaded video (Gemini image workflow)
allowed-tools: Bash, Read, Write, WebSearch, Glob
argument-hint: "[topic]"
disable-model-invocation: true
---

Run the full content pipeline for: $ARGUMENTS

## Overview

Execute all stages in order. After each stage, report what was created.
Default output: portrait 1080×1920 video with Gemini-generated images.

## Stages

### 1. Topics (optional)
Use /project:topics to discover trending topic ideas.

### 2. Prescript
Use /project:prescript with the topic.
Creates the run directory and a `prescript.json` outline for user review.

**Checkpoint**: Show the outline and confirm before proceeding.

### 3. Script
Use /project:script with the run directory from step 2.
Generates `script.json`.

### 4. Voice
Use /project:voice with the run directory.
Generates:
- `audio/scene_*.mp3` via Fish Audio TTS
- `subtitles/subtitles.srt` via Whisper alignment (automatic — no separate subtitle step needed)
- `voice_artifact.json`

### 5. Storyboard
Use /project:storyboard with the run directory.
Reads `script.json` + `subtitles/subtitles.srt` to produce `storyboard_prompts.md`
with 3 visual variants (A/寫實, B/卡通, C/資訊) and Gemini image prompts.

**Checkpoint**: Show variants and let user pick one (A/B/C) before proceeding.

### 6. Generate Visuals
Use /project:generate-visuals with the run directory and chosen variant.
Automates Gemini image generation via browser (Playwright/CDP).
Downloads images to `visual/MM:SS~MM:SS_01.png`, `_02.png`, etc.

**Checkpoint**: Ask user to review `visual/`, pick best image per shot, rename
by removing the index suffix (e.g., `00:03~00:07_01.png` → `00:03~00:07.png`).
Video shots (.mp4) must be sourced manually and placed in `visual/`.

### 7. Assembly (draft review)
Use /project:assembly with the run directory.
Runs `assembly_timeline` stage → outputs `assembly/draft.mp4` (portrait 1080×1920).

**Checkpoint**: Review `assembly/draft.mp4`. Adjust visuals or timing if needed,
then re-run assembly.

### 8. Prepare Upload
Use /project:prepareupload with the run directory.
Generates `upload/youtube_meta.json` and converts video for upload.

**Checkpoint**: Review title, tags, description in `youtube_meta.json` before proceeding.

### 9. Upload to YouTube
Use /project:upload with the run directory.
Uploads to YouTube. Returns video URL.

### 10. Thumbnail
Use /project:thumbnail with the run directory (optional, can run before upload).
Generates thumbnail image.

### 11. Drive backup & cleanup
Use /project:drive with the run directory.
Uploads entire run directory to Google Drive, then **deletes the local run directory**.
Confirm the Drive folder link is accessible before this step — deletion is irreversible.

---

## Error Handling

If any stage fails:
1. Report the error clearly
2. Ask the user: retry, skip, or abort?
3. All completed work is preserved in the run directory until step 11
4. Individual stages can be re-run by invoking the skill directly with `--run-dir`
