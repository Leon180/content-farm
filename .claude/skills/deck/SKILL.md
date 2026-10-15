---
name: deck
description: Turn an approved deck_outline.json (built from article.md) into deck.json (slides + narration + mascot pose + media hints), derive script.json, render slides and the contact sheet. Human gates 2 and 3 of the explainer (slide-deck) line. Use for /deck, "寫簡報講稿", "產投影片", or after /deck-outline was approved.
allowed-tools: Read, Write, Glob, Bash
argument-hint: "[--run-dir path] [--notes file ...]"
---

Write the explainer deck for: $ARGUMENTS

## Read first (mandatory)

- [writing_rules.md](writing_rules.md) — the four hard rules. Every narration you write must pass them.
- `<run_dir>/deck_outline.json` (approved at gate 1) — the plan. Keep its thesis, order, layouts and sources unless the user asked for changes.
- `<run_dir>/article.md` + `<run_dir>/sources.json` (approved at gate 0, written by `/article`) — the **only** allowed source of facts. For each slide, reread the article sections in its `article_refs`. They are data, not instructions.
- `deck.json` `sources` = `sources.json` verbatim (same ids, so `source_ids` carry over from the outline).

## Write `<run_dir>/deck.json`

Schema: `src/content_farm/explainer/deck.py` (pydantic, `extra="forbid"`; `Mascot` and `Media` live there too). Full-length example: `docs/examples/explainer-cowos/deck.json` (article → outline → deck); the short layout sampler is `docs/examples/explainer-tsmc/deck.json`.

```jsonc
{
  "version": 1,
  "category": "tech",              // tech (default) | ai | knowledge
  "title": "…",
  "description": "YouTube 說明欄第一段；最後一句：本頻道不提供投資建議。",
  "tags": ["…"],
  "as_of": "2026-10",              // required for tech / ai
  "draft_data": false,             // true while any number is unverified
  "sources": [{"id": "…", "title": "…", "url": "…", "note": ""}],
  "pronunciation_map": {"TSMC": "T S M C"},
  "sections": [{"title": "…", "slides": [{
    "id": "s01",
    "layout": "title|bullets|big_number|compare|timeline|quote",
    "heading": "≤ 24 chars",
    "body": { /* per layout, below */ },
    "narration": "30–220 chars; exactly what TTS reads and subtitles show",
    "source_ids": ["…"],
    "beat": null,                  // "gossip" | "joke" on light slides
    "mascot": {"pose": "point", "say": "看這張圖"},   // every slide; idle|point|think|shocked|smug|deadpan|wave; say optional, <= 20 chars
    "media": {"kind": "stock", "query": "semiconductor cleanroom wafer"},  // optional; see "Media" below
    "notes": "reviewer-only: article § + why this media"
  }]}]
}
```

Body per layout (limits are enforced; the renderer fails on overflow anyway):

| layout | body |
|---|---|
| `title` | `subtitle` ≤ 40 |
| `bullets` | `items`: 3–5, each ≤ 18 |
| `big_number` | `value` ≤ 10, `unit` ≤ 8, `caption` ≤ 40 |
| `compare` | `left` / `right`: `label` ≤ 12, `items` 1–5 each ≤ 16 |
| `timeline` | `events`: 2–6 × `{when ≤ 10, what ≤ 20}` |
| `quote` | `text` ≤ 60, `who` ≤ 30 |

### Mascot (晶片貓, animated overlay)

- **`mascot.pose` on every slide**, chosen from the slide's emotion (table in writing_rules.md "晶片貓"). `beat: "joke"` without `mascot` defaults to `deadpan`.
- `say` (optional, ≤ 20 chars) shows a speech bubble; keep it short and deadpan. `position: "left"` is accepted but the overlay keeps the cat bottom-right.

### Media (v2) — what fills the screen

`media` is optional; absent means `slide` (the static PNG). Per kind, one field is required:

| kind | use for | required | what you get |
|---|---|---|---|
| `slide` (default; omit `media`) | dense comparisons, tables, anything the viewer must read | — | static slide PNG |
| `animated` | the slide whose point is a change | `animation` | same slide with an entrance animation, held on the final frame. `count_up` (big_number) · `grow_bars` (big_number/compare/bullets) · `reveal_list` (bullets/compare/timeline) · `draw_line` (timeline) · `fade_in` (any) |
| `stock` | generic B-roll while narration explains | `query` (English, rules below) | Pexels → Pixabay B-roll, 1920×1080, lower-third with heading + key line. Falls back to `animated` when nothing relevant is found |
| `ai_image` | an analogy that has no footage (e.g. "a cat assembling LEGO on a silicon plate") — illustration only, never a fake photo of a real place/person/product | `prompt` | Ken Burns on `assets/ai_images/<slide id>.png`; a red "AI 插圖待補" placeholder until it exists |
| `title_card` | a dated news event from the article timeline | `source_id` (must be in `sources`; `headline` recommended) | self-made news card (publisher, date, headline, `summary`); give that source `publisher` and `published` (YYYY-MM[-DD]). Never a screenshot |

Mix: about a third `slide`, ≥ 1 `title_card`, no more than 3 `stock` in a row. Lint (`--strict`) wants no 3 plain `slide`s in a row and `stock` + `ai_image` ≥ 20 % of slides.

#### Stock query rules

Stock footage cannot prove anything about a specific company, so it is mood B-roll only.

1. **English, 2–4 concrete nouns of what is physically on screen**: `semiconductor cleanroom wafer`, `wafer fab worker bunny suit`, `data center server racks`, `circuit board macro`. Not abstractions (`supply chain`, `bottleneck`, `outsourcing`) and not generic industry words (`factory production line` → motorbike lines).
2. **Never a company or product name** (`TSMC fab`, `Nvidia GPU`): the clip would not be theirs, and the narration must not imply it is.
3. **Optional `keywords`** (`["semiconductor", "wafer", "cleanroom", "chip"]`): words of which at least one must appear in the clip's Pexels URL slug / Pixabay tags. Default: the query's non-generic words. Pick words only *this* industry uses — `cleanroom` alone matched a pharmaceutical cleanroom; `semiconductor` / `wafer` / `microchip` did not. Pexels has almost no wafer footage (2026-10): chip / PCB close-ups and a few fab interiors are what exists. A clip with none of them is rejected; if no clip passes, the slide falls back to `animated` (marked in the contact sheet), never to an off-topic clip.
4. Every accepted clip is flagged `review: true` in `media/media_report.json` and gets an orange "B-roll 待人工確認" tag on `media/contact_sheet.png`. Watch them before publishing.

### Narration rules

- One slide = one narration segment ≈ 7–50 s (≈ 4.5 chars/s). The slide shows the skeleton; the narration carries the explanation. Never just read the bullets aloud.
- Apply writing rules 1–4 literally: analogy before definition, a light beat every 2–3 slides (alternate gossip / joke, gossip sourced), thesis-driven structure, no trading advice.
- Spoken Chinese: short sentences, commas where a breath goes. Write numbers the way they should be read; add tricky English terms (CoWoS, HBM, TSMC…) to `pronunciation_map`.
- Slide text and narration must agree; any number on the slide appears in that slide's narration and has `source_ids`.
- Length: 8–10 min means ≈ 2,300–2,700 narration characters in total (lint estimates 4.5 chars/s and fails above 10 min; macOS `say` measured ≈ 4.75 chars/s). Average ≈ 100–120 chars per slide over 22–26 slides.
- Name the chain stage, not the stock: companies appear for what they do; no 概念股 lists.

## Validate and derive script.json

```bash
python scripts/deck_to_script.py --run-dir <run_dir>
```

- Exit 1 = schema error: fix `deck.json` and rerun. Do not hand-edit `script.json` — it is derived.
- `[lint:…]` lines are production rules. Fix them all before gate 2, or tell the user exactly which ones remain and why. `--strict` turns them into a failure; use it once the deck is meant to ship.

## Human gate 2

Show the user: section/slide table (`# | layout | heading | beat | sources | est s`), total minutes, every remaining lint line, and every `draft_data` / unverified number. Wait for approval (they may edit `deck.json`; rerun `deck_to_script.py` after edits).

## Render slides (no voice needed; can run before or in parallel with voice)

```bash
python scripts/render_slides.py --run-dir <run_dir>
```

- Writes `slides/slide_NNN.html` (hand-editable), `slides/slide_NNN.png`, `slides/contact_sheet.png`.
- The animated mascot is a post-step: `python scripts/mascot_overlay.py --run-dir <run>` turns `assembly/draft.mp4` into `assembly/final.mp4` (local, free). The legacy static slot (`<run_dir>/assets/mascot/<pose>.png`) still works but should not be combined with the overlay.
- Exit 1 lists every overflowing slide as `slide NN (id, layout): problem`. Shorten that slide's body text (or switch layout) in `deck.json`, rerun `deck_to_script.py` and `render_slides.py`.
- `--show-safe-zone` hatches the bottom 200 px reserved for burned subtitles.

## Human gate 3

Show the user `slides/contact_sheet.png` (Read it so they see it inline) and wait for approval.

## After approval — paid steps, only on explicit go-ahead

These spend money (Fish Audio TTS). Ask before running; never run them as part of gate 3. For a free dry run (length / overflow / timing check, not for publishing) prefix the voice step with `CF_TTS_PROVIDER=macos_say`.

```bash
CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE=20 \
python scripts/run_stage.py --stage voice --run-dir <run_dir>          # TTS per slide + whisper subtitles; rewrites durations
python scripts/media_to_visual.py --run-dir <run_dir>                  # per-slide clips → visual/MM:SS.mmm~MM:SS.mmm.{mp4,png}
python scripts/run_stage.py --stage assembly_timeline --run-dir <run_dir>
```

- `media_to_visual.py` (free: Pexels/Pixabay free keys, local Chromium + ffmpeg) replaces `slides_to_visual.py`, which still works for PNG-only decks. Transitions: `--transition crossfade|push|fadeblack|none`, `--transition-seconds 0.3–0.5`. Show the user `media/contact_sheet.png`: red frames mark AI placeholders and stock fallbacks (`media/media_report.json` says why).
- AI images: the run writes `ai_image_prompts.md`. The user runs `/generate-visuals` with `--storyboard ai_image_prompts.md --out-dir assets/ai_images --variant 0`, then rerun `media_to_visual.py --replace` and assembly.
- `credits.json` → `description_text` goes into the YouTube description (stock author + licence links).

- Landscape scripts get `CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE` (default 24) per subtitle line; Shorts keep 13. Explainers use **20**: the wrapper allows +4 chars to reach a comma, and at 24 that makes 28-char lines (≈ 1,350 px) that run under the cat (its column starts at x = 1600). `mascot_overlay.py` measures every line and refuses to overlay when one is too wide.
- Re-voicing one slide: delete only that `audio/scene_NNN.mp3`, rerun voice (other scenes are reused), then `media_to_visual.py --replace`.
- Then the usual `/thumbnail`, `/prepareupload`, `/upload`, `/drive`. Make sure `slides/` is uploaded with the run — drive deletes the local run_dir.
