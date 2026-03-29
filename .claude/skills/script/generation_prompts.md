# LLM Prompts for Viral Script Generation

**Ready-to-use prompts for Claude, GPT-4, or your script generation pipeline**

---

## META PROMPT (Use This First to Prime Model)

```
You are an expert YouTube Shorts and TikTok script writer specializing in viral short-form content.

Your task is to create scripts that:
1. Grab attention in the first 3 seconds with a pattern interrupt (unexpected visual/text) + question
2. Hold viewer attention by delivering specific, actionable value
3. Achieve 60%+ completion rates through clear structure and pacing
4. Follow the "Pre-Hook → Question → Deliver" framework

Success metrics:
- Intro retention >70% (first 3 seconds must stop scrolls)
- Completion rate >60% (viewers watch to end)
- Engagement rate >10% for zh-TW knowledge content
- No vague promises; include specific metrics/results

Output format:
- [SECONDS 0-1] PRE-HOOK: [Visual/text interrupt]
- [SECONDS 1-3] QUESTION: [Engagement statement]
- [SECONDS 3-50] BODY: [Value delivery in clear steps]
- [SECONDS 50-60] CTA: [Call-to-action]

Tone: Conversational, authoritative, timeless (avoid trendy slang like 「狂」「絕了」).
For zh-TW content: Use 痛點法, 數據法, or 反轉期待 hooks.
```

---

## PROMPT 1: Knowledge Content (Most Common Use Case)

```
Create a viral YouTube Shorts/zh-TW knowledge video script for topic: [TOPIC]

Target audience: [SPECIFIC DEMOGRAPHIC]

Required hook type: [CHOOSE: 痛點法/數據法/反轉期待/秘訣揭露]

Pain point to address: [WHAT PROBLEM DOES THIS SOLVE?]

Structure:
1. PRE-HOOK (0-1s): Start with text overlay or visual that contradicts audience expectations
   - Should make viewers stop and ask "why?"
2. QUESTION (1-3s): Pose a specific question that creates curiosity gap
   - Example: "Did you know [counterintuitive fact]?"
3. BODY (3-45s): Deliver 2-3 concrete, specific insights (not vague)
   - Include at least one statistic, metric, or concrete example
   - Use numbered structure (Step 1, Step 2, etc.)
4. CTA (45-60s): End with specific action
   - Example: "留言+1領完整教學" or "追蹤看下集"

Requirements:
- Total time: 45-60 seconds when spoken at natural pace
- Every sentence should be under 15 words
- Include 1 surprising statistic or concrete result
- Minimize filler words (avoid excessive 「欸」「嗯」)
- Use timeless phrasing (no trendy slang)

Output: Present in [SECONDS X-Y] format with voiceover text
```

---

## PROMPT 2: Transformation/Before-After Content

```
Create a viral transformation reveal script for: [TOPIC/TRANSFORMATION]

Transformation type: [VISUAL BEFORE/AFTER / SKILL PROGRESSION / PROBLEM→SOLUTION]

Key metrics:
- Starting point: [DESCRIBE "BEFORE"]
- End point: [DESCRIBE "AFTER"]
- Results achieved: [SPECIFIC NUMBERS/METRICS]

Script structure:
1. PRE-HOOK (0-1s): Show "before" state visually with text overlay
   - Should trigger "wow, this is broken/wrong" response
2. SETUP QUESTION (1-3s): Ask "What if you could change this?"
   - Make viewer want to see what happens next
3. TRANSFORMATION (3-40s): Show the 2-3 step process or reveal
   - Quick cuts/pacing to maintain energy
   - Clear cause → effect relationships
4. RESULTS REVEAL (40-55s): Show "after" state with specific metrics
   - "I gained X in Y days" / "Increased by X%"
5. CTA (55-60s): Soft call-to-action (Follow / Save for later)

Requirements:
- Pacing: Cut every 3-5 seconds for visual interest
- One surprising twist or "wow" moment
- Specific before/after numbers (not vague)
- Completion rate target: 70%+ (viewers want to see final result)

Output: Scene-by-scene breakdown with timing and voiceover
```

---

## PROMPT 3: Contrarian/Challenging Beliefs

```
Create a contrarian short-form script that challenges: [COMMON BELIEF]

The truth you want to reveal: [WHAT THE AUDIENCE GETS WRONG]

Target audience objection: [WHY THEY BELIEVE THE FALSE THING]

Correct information: [THE REAL FACTS/DATA]

Script structure:
1. PRE-HOOK (0-1s): State the popular belief in question form
   - "You probably think [COMMON BELIEF]... right?"
2. CONTRARIAN CLAIM (1-3s): Introduce the challenge
   - "Here's what's actually true..."
   - Create cognitive dissonance (brain wants to resolve)
3. PROOF (3-45s): Provide 2-3 pieces of evidence
   - Use specific examples, not abstractions
   - Include at least one statistic or expert reference
   - Show why people believe the wrong thing
4. PRACTICAL APPLICATION (45-55s): How viewer should act differently now
   - Concrete next step they can take today
5. CTA (55-60s): "Drop a comment if you believed this before"

Requirements:
- First 3 seconds MUST create disagreement from some viewers (engagement)
- Tone: Confident but not condescending
- Avoid attacking viewers; instead say "we were all taught this wrong"
- Include 1 surprising statistic that proves the point
- Keep sentences short and punchy

Output: Full script with voiceover and visual cues
```

---

## PROMPT 4: zh-TW Specific Knowledge Content

```
為以下主題創建一個病毒式的YouTube Shorts腳本：[主題]

目標觀眾：[具體人群]

使用的Hook類型：[痛點法/數據法/反轉期待/秘訣揭露 - 選一個]

視頻結構（三層3法則）：

**開頭3秒：THE HOOK**
- [0-1秒] 文字或視覺中斷：吸引停留
- [1-3秒] 提問或數據：創造好奇心

**中段3個亮點：VALUE DELIVERY**
- [3-30秒] 第1點：[具體洞見]
- [30-45秒] 第2點：[具體洞見]
- [45-55秒] 第3點：[具體洞見]
  提示：使用前後對比、實測過程、個人真實感受

**結尾3個以內CTA：ENGAGEMENT**
- [55-60秒] 清晰的行動呼籲
  選項：「留言+1領教學」/ 「追蹤看下集」/ 「按讚開啟通知」

要求：
- 每句話少於15個字
- 包含至少1個驚人的統計數據
- 避免過度使用「欸」、「嗯」等語氣詞
- 使用經久不衰的措辭（避免「狂」「絕了」等時髦用語）
- 文字風格：口語化、有節奏、前後呼應
- 總長度：50-60秒（自然語速）

輸出格式：[秒數 X-Y] [內容描述] / [配音文本]
```

---

## PROMPT 5: Quick Hook A/B Variants

```
For topic: [TOPIC]

Create 3 different hook variants (first 3 seconds only) and rank by predicted effectiveness:

VARIANT A - Pattern Interrupt + Question:
[SCRIPT]
Predicted engagement: [WHY THIS WORKS]

VARIANT B - Curiosity Gap:
[SCRIPT]
Predicted engagement: [WHY THIS WORKS]

VARIANT C - Specific Result + Data:
[SCRIPT]
Predicted engagement: [WHY THIS WORKS]

Recommendation: Variant [X] for this topic because [REASONING BASED ON AUDIENCE/CONTENT TYPE]

Testing approach:
- Create all 3 with identical body/CTA
- Test with minimum 1,000 impressions each
- Measure: click-through rate, average view duration, completion rate
- Winner should have >70% intro retention and <20% swipe-away rate
```

---

## PROMPT 6: Multi-Part Series Hook

```
You're creating episode 1 of a [NUMBER]-part series on: [TOPIC]

Part structure:
- Part 1: [WHAT IS DELIVERED]
- Part 2: [WHAT IS DELIVERED]
- Part 3: [WHAT IS DELIVERED]

Episode 1 script with cliffhanger:

1. PRE-HOOK (0-1s): Hook for entire series premise
   - Must make viewer want to see all parts
2. QUESTION (1-3s): Setup the problem/mystery
3. BODY (3-45s): Deliver 1 valuable insight from Part 1
   - Save the best for Parts 2-3
4. CLIFFHANGER (45-55s): Tease what's coming
   - "Part 2: [bigger insight that's coming]"
5. CTA (55-60s): "Follow for Part 2 tomorrow"

Requirements:
- Completion rate should be high because series creates commitment
- First hook must tease all 3 parts
- End on cliffhanger, not complete resolution
- Each part can be 45-60 seconds

Output: Full Part 1 script + brief outline of Parts 2-3
```

---

## PROMPT 7: Visual Pacing Notes

Add this to any of the above prompts to get detailed pacing/cut instructions:

```
Additionally, for each [SECONDS X-Y] section, provide:
- Visual cue: [What's on screen? Text overlay? B-roll? Close-up?]
- Cut type: [Quick cut / Slow pan / Text animation?]
- Energy level: [Rising / Maintained / Peak / Wind-down]
- Audio: [Background music style if applicable]

This helps the video editing team execute exactly as intended.
```

---

## EXAMPLE: Complete Prompt With All Elements

```
Create a viral YouTube Shorts script on: "Why you're buying the wrong productivity app"

Target audience: Remote workers, freelancers, indie creators (18-40)
Hook type: 痛點法 (Pain Point)
Video length: 50 seconds
Platform: YouTube Shorts / zh-TW audience

Structure (Pre-Hook → Question → Deliver):

[0-1s] PRE-HOOK - TEXT OVERLAY + VISUAL INTERRUPT
- Text: "你花的時間...都在找正確的App"
- Visual: Quick flash of confused person scrolling apps
- Purpose: Stop the scroll by creating immediate recognition of pain

[1-3s] QUESTION - ENGAGEMENT HOOK
- Voiceover: "我測試了50個生產力App，發現一個致命問題..."
- Visual: Quick cuts of different app icons
- Purpose: Create curiosity gap - what's the problem?

[3-35s] BODY - VALUE DELIVERY (3 points)
1. [3-15s] 第1亮點：The mistake everyone makes
   - Specific: "大多數人選App看介面，不看自己的習慣"
   - Visual evidence: Before/after comparison

2. [15-25s] 第2亮點：The metric most miss
   - Specific: "只有3個功能會被長期使用，其他99%是浪費"
   - Visual: Data graphic or screen recording

3. [25-35s] 第3亮點：The solution framework
   - Specific: "用這個3步驟選App：1)檢視自己工作流程 2)測試7天不卸載 3)對比用前用後的時間節省"
   - Visual: Checklist on screen

[35-50s] RESULTS REVEAL
- "我用這個方法選了Notion，省了5小時每週"
- Visual: Screen recording of user's actual workspace
- Specific metric: Hours saved per week

[50-60s] CTA
- "留言告訴我你用什麼生產力App？我測試最多人推薦的"
- Visual: Call-to-comment graphic
- Purpose: High engagement signal to algorithm

Requirements met:
✓ Pattern interrupt + question in first 3 seconds
✓ 3 specific value points (not vague)
✓ Concrete metrics included
✓ Cliffhanger for viewer interaction
✓ zh-TW pain-point hook format
✓ 50-60 second pacing
✓ No trendy slang; conversational but authoritative
```

---

## WHEN TO USE WHICH PROMPT

| Situation | Use Prompt |
|-----------|-----------|
| Standard knowledge/educational video | Prompt 1 |
| Before-after, transformation, results-driven | Prompt 2 |
| Challenging false beliefs, misconceptions | Prompt 3 |
| zh-TW Chinese audience, knowledge content | Prompt 4 |
| Need to A/B test multiple hook approaches | Prompt 5 |
| Building a series to keep audience coming back | Prompt 6 |
| Need detailed visual pacing for editor | Prompt 7 |
| Complex topic requiring everything above | Use Example at end |

---

## INTEGRATION INTO YOUR PIPELINE

**Recommended workflow:**

1. Select appropriate prompt above based on topic/content type
2. Fill in [BRACKETED] variables with topic details
3. Send to LLM (Claude, GPT-4, or script generation model)
4. Receive script in format with [SECONDS X-Y] timing
5. Pass to voice generation stage with specific timing codes
6. Visual team uses visual cues to source/cut appropriate B-roll
7. A/B test first 3 seconds with metrics from Part 4 of main guide

---

**Version:** 1.0 | Framework: Pre-Hook → Question → Deliver | March 2026
