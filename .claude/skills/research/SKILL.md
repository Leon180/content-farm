---
name: research
description: Research a topic using web search to find real sources for video script preparation
allowed-tools: WebSearch, Read, Write, Glob
argument-hint: "[topic]"
---

Research the topic: $ARGUMENTS

## Goal

Find 5-8 real, verifiable sources for a zh-TW short-form video script about this topic.

## Process

1. **Search broadly** — run 3-5 WebSearch queries with different angles:
   - The core factual question (in English for better results)
   - "research study" or "statistics" + topic keywords
   - Counter-intuitive facts related to the topic
   - Real-world examples or case studies

2. **Extract key facts** — from search results, collect:
   - Specific numbers, dates, statistics
   - Named studies, papers, or official reports
   - Expert quotes or established scientific consensus
   - Surprising or counter-intuitive angles

3. **Verify cross-references** — if a claim appears in only one source, flag it as unverified

4. **Create run directory** — `output/YYYYMMDD_HHMMSS_<safe_topic>/`

5. **Write research brief** — save to `<run_dir>/research.md` with this format:

```
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
- [angle 1]: [why it's interesting for a short video]
- [angle 2]: [why it's interesting]

## Unverified Claims (use hedging language if included in script)
- [claim] — only found in [source]
```

6. **Report** — Print the run directory path and a summary of findings

## Important

- NEVER fabricate sources. Every URL must come from actual search results.
- Prefer academic, governmental, or established media sources.
- English search queries get better results; the script itself will be in zh-TW.
- The run directory path will be used by subsequent skills (/project:script, /project:voice, etc.)
