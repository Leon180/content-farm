---
name: pipeline
description: Run the full content pipeline from topic to uploaded video
allowed-tools: Bash, Read, Write, WebSearch, Glob
argument-hint: "[topic] [--mode materials|full]"
disable-model-invocation: true
---

Run the full content pipeline for: $ARGUMENTS

## Overview

Execute all stages in order. After each stage, report what was created.
Default mode is `materials` (blank background + voice + subtitles).

## Stages

### 1. Research
Use /project:research with the topic to find real sources via web search.
This creates the run directory and `research.md`.

### 2. Script
Use /project:script with the topic and `--run-dir` from step 1.
This generates `script.json` and `storyboard.txt` based on research.

**Checkpoint**: Show the user the storyboard summary and ask if they want to proceed or edit.

### 3. Voice
Use /project:voice with the run directory.
Generates `audio/scene_*.mp3` via TTS API.

### 4. Visual
Use /project:visual with the run directory.
- For materials mode: add `--blank` flag (black background)
- For full mode: sources stock footage from Pexels/Pixabay

### 5. Subtitle
Use /project:subtitle with the run directory.
Generates subtitle timing from script + voice.

### 6. Assembly
Use /project:assembly with the run directory.
- For materials mode: add `--template` flag
- For full mode: standard assembly

### 7. Upload
Use /project:upload with the run directory.
Uploads everything to Google Drive.

## Progress Reporting

After each stage, report:
- What files were created
- Current state of the run directory
- Any warnings or issues

## Error Handling

If any stage fails:
1. Report the error clearly
2. Ask the user: retry, skip, or abort?
3. All completed work is preserved in the run directory
4. Individual stages can be re-run later
