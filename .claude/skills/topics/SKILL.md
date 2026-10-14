---
name: topics
description: Discover trending and engaging video topics for short-form content
allowed-tools: WebSearch, Read, Write
argument-hint: "[category] [--count N]"
---

Find trending video topics. Category: $ARGUMENTS

## Categories

If no category specified, cover all: `science`, `technology`, `psychology`, `history`, `space`, `culture`

## Process

1. **Search for trends** — run WebSearch queries:
   - `"trending [category] topics 2026 YouTube shorts"` (English)
   - `"[category] 冷知識 熱門話題"` (zh-TW)
   - `"viral [category] facts most people don't know"`
   - `"Reddit TIL [category]"` for counter-intuitive facts
   - For `culture` category: also search `"台灣 全球排名"`, `"台灣 世界第一"`, `"台灣冷知識"`
   - For `space` category: also search `"太空 宇宙 最新發現"`, `"NASA 2026"`

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

## Taiwan Localization

- Include at least 1-2 topics per batch with a **Taiwan angle**
- Taiwan angle examples: "台灣全球第X名", "台灣在這件事上領先全球", "台灣人不知道的台灣冷知識"
- Use Taiwan-specific terms (計程車 not 出租車, 捷運 not 地鐵)
- Connect global facts to Taiwan when natural (e.g., "全球只有X個國家做到，台灣是其中之一")

## Guidelines

- Aim for 5-8 topics per category
- Topics should be timeless (not news-dependent) unless specifically trending
- Prefer topics with a "wow factor" or counter-intuitive angle
- Avoid topics that require complex visual effects (animation-heavy)
- Each topic should be self-contained (no Part 1/Part 2)
- Consider zh-TW audience interests and cultural relevance
- Prefer suspense-reveal (懸念揭曉) topics over listicle-style ("X個你不知道的...")
- Best-performing verticals by engagement: science > psychology > tech/AI > history > space
