---
name: research
description: Research a topic using web search to find real sources for video script preparation. Scales source depth based on --video-length.
allowed-tools: WebSearch, Read, Write, Glob
argument-hint: "[topic] [--video-length short|medium|long] [--genre knowledge|listicle_ranking|news_analysis|story_mystery]"
---

Research the topic: $ARGUMENTS

## Argument Parsing

- Positional: topic
- `--video-length <short|medium|long>` — default `short`; controls source depth
- `--genre <...>` — long-form only; influences search angle coverage

## Source Depth Targets

| `--video-length` | Minimum sources | Notes |
|------------------|------------------|-------|
| `short` (default) | 5-8 | Enough to ground a 50-65s hook-body-payoff |
| `medium` | 12-18 | Covers 4-6 chapter angles |
| `long` | 18-25 | Covers 5-8 chapter angles plus counter-evidence |

Long-form videos are punished by the 2026 YouTube algorithm if they are thin/generic. More sources means more specificity, more real data points, more editorial leverage — not more filler. **Prefer fewer high-quality sources over padding.**

## Process

### 1. Search broadly

Run WebSearch queries with different angles:

- **Core factual question** (in English for better results)
- **Research / studies / statistics** on the topic
- **Counter-intuitive angles** — what the common understanding gets wrong
- **Taiwan connection** — local data, local experts, local examples
- For long-form: add **opposing views**, **historical context**, **expert disagreements**, **real-world applications**

Scale query count with video length: short = 3-5 queries; medium = 6-10; long = 10-15.

### 2. Extract key facts

From search results, collect:

- Specific numbers, dates, statistics
- Named studies, papers, official reports
- Expert quotes / established consensus
- Surprising or counter-intuitive angles
- **For long-form**: timeline of events (if relevant), named stakeholders, opposing interpretations

### 3. Verify cross-references

If a claim appears in only one source, flag it as unverified. **For long-form, the threshold bumps to 2 sources** — higher stakes demand tighter sourcing.

### 4. Create run directory

`output/YYYYMMDD_HHMMSS_<safe_topic>/` if one doesn't already exist.

### 5. Write research brief

Save to `<run_dir>/research.md`:

```markdown
# Research: [topic]

## Key Facts
- [fact 1] — Source: [URL]
- [fact 2] — Source: [URL]
...

## Verified Sources
1. [Title] — [URL]
2. [Title] — [URL]
...

## Potential Angles
- [angle 1]: [why it works on video]
- [angle 2]: [why it works]

## Unverified Claims (use hedging language if included)
- [claim] — only found in [source]
```

### 6. Long-form only — write chapter-angle mapping

If `--video-length medium|long`, also produce `<run_dir>/research_chapters.md`:

```markdown
# Chapter Angles: [topic]

_Used by the prescript step to anchor each chapter in verified material._

## Proposed Chapter 1: [title]
**Angle:** [what this chapter argues]
- Key source: [URL] — [fact supporting this chapter]
- Supporting: [URL] — [fact]
- Counter-evidence: [URL] — [opposing fact, if relevant]

## Proposed Chapter 2: [title]
...
```

Target 2-3 angles per planned chapter. Chapter count comes from genre:
- `knowledge`: 5-7 chapters (problem → myth → principle → example → application → reflection)
- `listicle_ranking`: matches list size (Top 5 = 5 items + intro/outro)
- `news_analysis`: 4-6 chapters (event → stakeholders → mechanism → Taiwan impact → forecast)
- `story_mystery`: 5-7 chapters (cold open → background → clues → misdirection → reveal → epilogue)

If no `--genre` is passed, infer from topic or default to `knowledge`.

### 7. Report

Print:
- Run directory path
- Source count (vs minimum target)
- For long-form: chapter-angle count, any gaps flagged

## Important

- **NEVER fabricate sources.** Every URL must come from actual search results.
- Prefer academic, governmental, or established media sources.
- English search queries get better results; the script itself will be in zh-TW.
- The run directory path will be used by `/project:prescript`, `/project:script`, etc.
