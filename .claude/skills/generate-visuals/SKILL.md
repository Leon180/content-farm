---
name: generate-visuals
description: Browser-automated Nano Banana (Gemini) image generation from a storyboard_prompts.md file. Opens Gemini in Chromium, submits each shot prompt, downloads images into visual/ directory with timeline filenames.
allowed-tools: Bash, Read
argument-hint: "[run-dir] [--variant N]"
disable-model-invocation: true
---

Generate Nano Banana images for: $ARGUMENTS

## Purpose

**Step 2 of the visual pipeline** (Step 1 = `/project:storyboard`).

Drives a real Chromium browser (Playwright) to Gemini web chat,
submits each shot prompt from `storyboard_prompts.md`, and downloads
the resulting images into `<run_dir>/visual/` with the correct
`MM:SS~MM:SS.png` filenames so `assembly_timeline` can consume them.

## Prerequisites

- `<run_dir>/storyboard_prompts.md` must exist (run `/project:storyboard` first)
- Playwright + Chromium installed:
  ```bash
  pip install -e ".[browser]"
  playwright install chromium
  ```
- On **first run** you'll need to manually sign in to Google inside the
  Chromium window that opens. Session is persisted at
  `.cache/playwright_gemini/` so subsequent runs skip login.

## Execution

### Recommended: CDP mode (uses your real Chrome session, avoids bot detection)

```bash
# Step 1 — Launch Chrome with remote debugging (one-time per session)
bash scripts/launch_chrome_debug.sh

# Step 2 — Attach script to running Chrome
.venv/bin/python scripts/generate_visuals.py --run-dir "$0" --cdp-port 9222
```

Chrome session is persisted at `~/.cache/chrome_debug/` so you stay logged in.

### Alternative: Playwright mode (fresh Chromium, requires Google login each time)

```bash
.venv/bin/python scripts/generate_visuals.py --run-dir "$0"
```

Arguments:
- `--run-dir <path>` (required) — run directory containing `storyboard_prompts.md`
- `--variant <N>` (optional) — variant index (0=A, 1=B, 2=C). Skips the
  interactive picker if provided.
- `--cdp-port <N>` (optional) — attach to existing Chrome via CDP (recommended)
- `--headless` (optional) — run without UI (NOT recommended for first run)

## What it does

1. Parses `storyboard_prompts.md` → list of variants
2. Prompts you (or uses `--variant`) to pick one variant
3. Opens Chromium → gemini.google.com
4. Waits for you to log in (one-time)
5. For each **image** shot (`.png`):
   - Types the prompt into Gemini
   - Submits
   - Waits for image(s) to render (up to 3 min)
   - Downloads all returned images to `visual/MM:SS~MM:SS.png` (or
     `_01.png`, `_02.png` suffixed if multiple)
   - Sleeps 5s before next prompt (rate-limit courtesy)
6. **Skips video shots (`.mp4`)** — Nano Banana only generates images.
   Handle videos separately (Veo, etc.) or mark the shot in the
   storyboard as an `.mp4` filename that you'll manually produce.
7. On any per-shot failure: logs error, continues with next shot
8. Prints summary of success/failure at the end

## First-run checklist

1. Open Chromium when it launches
2. Sign in to your Google account
3. Confirm you land on gemini.google.com with the chat box visible
4. Make sure Gemini is set to a model that can generate images
   (Nano Banana / Gemini 2.5 Flash Image). You may need to select
   "Create an image" or a similar mode.
5. The script continues automatically as soon as the chat input appears

## Configuration

In `.env` (optional overrides):

```
CF_GEMINI_BROWSER_DELAY_S=5.0            # Seconds between prompts
CF_GEMINI_BROWSER_GENERATION_TIMEOUT_S=180.0  # Wait per image (s)
CF_GEMINI_BROWSER_HEADLESS=false
CF_GEMINI_BROWSER_USER_DATA_DIR=.cache/playwright_gemini
```

## After it finishes

### 1. Review and select images

Open `<run_dir>/visual/` and review the generated images.

For each shot, pick the best candidate and **rename it by removing the index suffix**:
- `00:03~00:07_01.png` → `00:03~00:07.png`
- `00:03~00:07_02.png` — delete or leave (only the no-suffix file is used)

Video shots (`.mp4`) must be placed manually in `visual/` with the correct `MM:SS~MM:SS.mp4` filename.

### 2. Run assembly

Use `/project:assembly` to stitch images + audio into the draft video.

## Troubleshooting

- **"Chat input not found"**: Gemini UI changed. Open an issue / inspect
  the current DOM and update `CHAT_INPUT_SELECTORS` in
  [gemini_browser.py](../../../src/content_farm/visual_gen/gemini_browser.py).
- **Rate-limited**: increase `CF_GEMINI_BROWSER_DELAY_S` (try 10-15s)
- **Multiple images downloaded per prompt**: expected — pick the best one
  and rename it to strip the `_01` suffix, or leave as-is and the
  lowest-suffix file wins during assembly_timeline.
