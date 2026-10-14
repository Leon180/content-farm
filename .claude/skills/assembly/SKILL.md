---
name: assembly
description: Assemble final video from voice + visual + subtitles using FFmpeg
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir] [assembly_timeline|assembly|template]"
disable-model-invocation: true
---

Assemble the video in: $ARGUMENTS

## Prerequisites

- `$0/script.json` must exist
- `$0/audio/scene_*.mp3` must exist

**Standard mode:** `$0/visual/scene_*.mp4` must exist
**Timeline mode:** `$0/visual/MM:SS~MM:SS.mp4` clips must exist + `$0/audio/full.mp3`

## Execution

Parse arguments:

```bash
# Timeline assembly (default — portrait 1080x1920)
.venv/bin/python scripts/run_stage.py --stage assembly_timeline --run-dir "$0"

# Standard assembly (scene-based, legacy)
.venv/bin/python scripts/run_stage.py --stage assembly --run-dir "$0"

# Template mode (materials pipeline)
.venv/bin/python scripts/run_stage.py --stage template --run-dir "$0"
```

**Default is timeline assembly.** Use `assembly_timeline` unless explicitly asked for standard mode.

## Output Format

- **Portrait (1080x1920)** — default output for YouTube Shorts
- Landscape source images/videos are centered with black bars top/bottom
- Portrait sources used as-is

## Subtitles

- Rendered via SRT→ASS conversion with `PlayResX:1080` / `PlayResY:1920`
- `Alignment=5` (center of screen), `FontSize=78`, Bold
- Max ~13 Chinese characters per line to avoid overflow
- Line breaks must be at punctuation or semantic boundaries, never mid-word/number
- Numbers like 2031, 2028, 500克 must stay on the same line

## Pre-Assembly Checklist

Before running assembly, verify subtitles:
- [ ] Subtitle timing matches audio (generate a draft check video if needed)
- [ ] Numbers in narration are written in Chinese for TTS (二零三一) but Arabic in subtitles (2031)
- [ ] Lines are short enough (~13 chars) for portrait display at FontSize=78

## Verify

Check `$0/assembly/draft.mp4` (timeline) or `$0/assembly/*.mp4` (standard).
