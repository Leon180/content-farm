---
name: skit-script
description: Write script.json for one 晶片貓下班了 冷笑話小劇場 Short (飲水機金魚) — 鋪陳 → 停頓 0.6 秒 → 笑點 → 收尾, 20–50 s, original joke only. Use for /skit-script, "寫冷笑話劇本", or when `produce.py run --channel offwork` stops at the skit_script step.
allowed-tools: Read, Write, Edit, Glob, Bash
argument-hint: "--run-dir output/offwork-<run>"
---

Write the 冷笑話小劇場 script for: $ARGUMENTS

## Read first

1. `channels/offwork.yaml` — the channel: length (20–50 s, 9:16), `topic_categories`, the mascot (飲水機金魚,
   `pngtuber/cooler-goldfish-3d`) and the voice reference text (`voice.reference.text` is the tone: deadpan,
   spoken, 下班族 talk). **Do not add characters, backstory or catchphrases that are not in these files.**
2. `<run_dir>/topic.json` — `chosen[0]` is today's premise (`title`, `hook`, `note`). Write that joke.
3. Optionally `<run_dir>/review/script.fixes.json` — a panel sent the script back; fix only what it names.

## Format (the checker enforces it)

```
鋪陳（1–3 場）  →  停 0.6 秒（靜音，由最後一場鋪陳的 transition 表示）  →  笑點（1 場，≤ 40 字）  →  收尾（0–1 場，可省）
```

`script.json` is the normal script model (the voice step reads it, then rewrites it with real audio lengths, so keep to
these fields). One scene per beat:

```json
{
  "stage": "script_generation",
  "video_title": "週五下午五點的部署",
  "description": "一句話說明。原創冷笑話，角色為 AI 生成。",
  "language": "zh-TW",
  "target_length": "short",
  "orientation": "portrait",
  "ai_disclosure": true,
  "tags": ["冷笑話", "上班族", "#Shorts"],
  "sources": [],
  "scenes": [
    {"scene_number": 1, "title": "01 鋪陳", "narration": "…",
     "visual_hint": {"description": "neutral", "keywords": []}, "duration_seconds": 8, "transition": "pause:0.6"},
    {"scene_number": 2, "title": "02 笑點", "narration": "…",
     "visual_hint": {"description": "smug", "keywords": []}, "duration_seconds": 3, "transition": "cut"}
  ],
  "total_duration_seconds": 12
}
```

- `title` is `"<nn> 鋪陳"`, `"<nn> 笑點"` or `"<nn> 收尾"` — the beat names are how the renderer and the panel find the structure.
- `transition: "pause:0.6"` goes on the **last 鋪陳 scene only**; every other scene is `"cut"`.
- `visual_hint.description` is the goldfish's expression for the scene, one of `neutral` / `surprised` / `smug` / `speechless`
  (layers of the pack). Typical: 鋪陳 `neutral`, 笑點 `smug` or `speechless`. The fish has no mouth; speech shows as bubbles.
- `duration_seconds` and `total_duration_seconds`: estimate ≈ characters ÷ 5.5 (the voice step overwrites them).
- Length: 20–50 s counting the pause → roughly 110–260 spoken characters in all.

## Writing rules

- **The joke has to be original.** No retelling of other creators' skits, memes' exact wording or known joke books; no other
  channel's catchphrases or sign-offs. If the premise resembles a known joke, change the angle until it is yours.
- The setup states the situation plainly and makes a **false expectation** the listener fills in by themselves; the punchline
  (≤ 40 chars) flips it. Do not explain the joke, do not announce "笑點來了", do not repeat it in the tag.
- Voice: deadpan, spoken Taiwanese Mandarin, short sentences, no stage directions in `narration` (it is read aloud).
  Keep 欸 to one or none; no trendy slang (狂、絕了 …) — it dates in months; ordinary internet words are fine.
- Narration is TTS text: write numbers as Chinese where read aloud (「五點」「三十秒」), no emoji, no English abbreviations
  unless the speaker would say them letter by letter.
- No real company, product-incident or person as the butt of the joke; no investment advice; no politics.
- `tags` include `#Shorts`; `sources` stays `[]` (no facts claimed).

## Check, then stop

```
python scripts/check_skit.py --run-dir <run_dir>
```

Fix until `0 problem(s)`. Do not render, upload or edit other files; the panel (`gate_script`) reviews the script next.
