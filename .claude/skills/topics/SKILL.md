---
name: topics
description: Discover trending and engaging video topics for short-form content
allowed-tools: WebSearch, Read, Write
argument-hint: "[category] [--count N]"
---

Find trending video topics. Category: $ARGUMENTS

## Categories

If no category specified, cover all: `science`, `technology`, `psychology`, `history`, `nature`, `trivia`

## Process

1. **Search for trends** — run WebSearch queries:
   - `"trending [category] topics 2026 YouTube shorts"` (English)
   - `"[category] 冷知識 熱門話題"` (zh-TW)
   - `"viral [category] facts most people don't know"`
   - `"Reddit TIL [category]"` for counter-intuitive facts

2. **Filter for short-form potential** — good topics have:
   - A clear hook (surprising fact, counter-intuitive truth, mystery)
   - Explainable in 30-90 seconds
   - Visual potential (can find stock footage)
   - Emotional arc (curiosity → surprise → understanding)

3. **Score each topic** (internal, don't show scores):
   - Hook strength: does it stop scrolling?
   - Shareability: would someone send this to a friend?
   - Visual potential: can we find footage?
   - Uniqueness: not already overdone on YouTube?

4. **Output format** — print a ranked list:

```
## [Category] — 推薦主題

1. **[Topic Title in zh-TW]**
   Hook: [one-sentence hook that would open the video]
   Why: [why this topic works for short-form]
   Keywords: [English keywords for stock footage search]

2. **[Topic Title]**
   ...
```

5. **Save to file** — write the full list to `topics_YYYYMMDD.md` in the project root

## Guidelines

- Aim for 5-8 topics per category
- Topics should be timeless (not news-dependent) unless specifically trending
- Prefer topics with a "wow factor" or counter-intuitive angle
- Avoid topics that require complex visual effects (animation-heavy)
- Each topic should be self-contained (no Part 1/Part 2)
- Consider zh-TW audience interests and cultural relevance
