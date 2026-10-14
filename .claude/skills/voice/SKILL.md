---
name: voice
description: Generate voice narration for all scenes using TTS API
allowed-tools: Bash, Read, Glob
argument-hint: "[run-dir, optional — defaults to latest run]"
disable-model-invocation: true
---

Generate voice audio for the video in: $ARGUMENTS

## Prerequisites

- `$0/script.json` must exist (run /project:script first)
- TTS API key configured in `.env` (`CF_FISH_AUDIO_API_KEY` or `CF_ELEVENLABS_API_KEY`)

## Execution

```bash
.venv/bin/python scripts/run_stage.py --stage voice --run-dir "$0"
```

## Note on Subtitles

Whisper subtitle alignment runs **automatically** as a post-step inside this stage.
No separate `/project:subtitle` step is needed. The subtitle skill has been removed.

## Verify

After completion, check:
1. `$0/audio/scene_*.mp3` files exist (one per scene)
2. `$0/audio/full.mp3` exists (concatenated audio)
3. `$0/subtitles/subtitles.srt` exists (auto-generated via Whisper)
4. `$0/voice_artifact.json` was created
5. No errors in the output

## On Failure

- Missing API key → check `.env` file
- Rate limiting → wait 30s and retry
- Network error → retry
