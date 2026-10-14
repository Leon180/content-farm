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
- TTS API key configured in `.env` (`CF_FISH_AUDIO_API_KEY` or `CF_ELEVENLABS_API_KEY`),
  **or** `CF_TTS_PROVIDER=macos_say` (free, no key — see below)

## Execution

```bash
.venv/bin/python scripts/run_stage.py --stage voice --run-dir "$0"
```

### Free dry run: `CF_TTS_PROVIDER=macos_say`

Uses the macOS built-in `say` voice + ffmpeg. Free, no API key, no network for TTS.
**Development and testing only — the voice is robotic; never publish a video narrated with it.**

```bash
CF_TTS_PROVIDER=macos_say .venv/bin/python scripts/run_stage.py --stage voice --run-dir "$0"
```

- Voice: `CF_MACOS_SAY_VOICE` (default `Flo (Chinese (Taiwan))`; list installed voices with `say -v '?'`).
- Rate: `CF_MACOS_SAY_RATE` (optional, words per minute, same as `say -r`).
- ffmpeg: `CF_FFMPEG_PATH`.
- Whisper alignment still runs, so subtitles and `script.json` durations are real.

Full free explainer run (deck already written):

```bash
python scripts/deck_to_script.py --run-dir output/<run>
python scripts/render_slides.py  --run-dir output/<run>
CF_TTS_PROVIDER=macos_say python scripts/run_stage.py --stage voice --run-dir output/<run>
python scripts/slides_to_visual.py --run-dir output/<run>
python scripts/run_stage.py --stage assembly_timeline --run-dir output/<run>
```

Use this to check timing, subtitles and slide cuts; re-run voice with Fish Audio before publishing
(`slides_to_visual.py --replace` to re-place slides on the new durations).

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
- `macos_say` errors name what is missing: not macOS, `say`/ffmpeg not found, or voice not installed
  (macOS `say` silently falls back to the default voice, so the provider checks `say -v '?'` first)
- Rate limiting → wait 30s and retry
- Network error → retry
