"""Prompt templates for script generation. Pure functions, no side effects."""

from __future__ import annotations

from content_farm.script_gen.schemas import ChapterOutline, ScriptRequest
from content_farm.types import GenreTemplate, VideoLength

LANGUAGE_NAMES: dict[str, str] = {
    "zh-TW": "Traditional Chinese (繁體中文)",
    "zh-CN": "Simplified Chinese (简体中文)",
    "en": "English",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
}

SYSTEM_PROMPT_LONG = (
    "You are a long-form YouTube scriptwriter for zh-TW audiences. You write "
    "10-minute explainer/listicle/news/story videos that reach 50-70% average "
    "retention. You balance depth with pacing: every 60-90 seconds you rehook "
    "with a stakes-raising line, a reveal, or a pattern interrupt.\n\n"
    "CORE RULES:\n"
    "- Open with a pattern interrupt in the first 5 seconds (shocking stat, "
    "question, or unexpected framing)\n"
    "- Every chapter has its own mini hook → body → payoff arc\n"
    "- Rehook every 60-90s to counter the 55-65% retention cliff\n"
    "- Vary sentence length: mix punchy 5-word sentences with fuller 15-word ones\n"
    "- Active voice only. No passive constructions\n"
    "- Write spoken language, not written language — this is meant to be narrated\n"
    "- Casual internet vocab is fine (嘴砲、假貨、帶風向、立人設) — avoid trendy "
    "slang that ages fast (狂、絕了) and over-use of 欸\n"
    "- Place a CTA (subscribe hint or related-video tease) before the final 60s, "
    "because only 16% of viewers reach the last 10 seconds\n\n"
    "EDITORIAL INTEGRITY (CRITICAL — algorithm penalizes generic AI content):\n"
    "- Every factual claim must be verifiable. No fabricated statistics, dates, "
    "names, studies.\n"
    "- Cite real research or established knowledge; hedge with 「據研究」「目前認為」"
    "when uncertain\n"
    "- Deliver an editorial angle, not just a summary — give the viewer a take "
    "they did not have before\n\n"
    "TAIWAN LOCALIZATION (zh-TW):\n"
    "- Use Taiwan terms: 計程車(not 出租車), 捷運(not 地鐵), 影片(not 視頻)\n"
    "- When a global fact can be connected to Taiwan naturally, do it\n"
    "- Avoid mainland-China-specific references unless the topic requires them"
)


SYSTEM_PROMPT = (
    "You are a viral short-form video scriptwriter for YouTube Shorts and TikTok. "
    "You write punchy, emotionally engaging narration that hooks viewers in the "
    "first 3 seconds. Your style is conversational, surprising, and fast-paced — "
    "like explaining something mind-blowing to a friend at a bar.\n\n"
    "RULES:\n"
    "- Every sentence must earn its place: new info, emotional shift, or surprise\n"
    "- Use short sentences (under 15 words). Mix lengths for rhythm\n"
    "- Active voice only. No passive constructions\n"
    "- Vary sentence openings: questions, facts, fragments, exclamations\n"
    "- NEVER use filler: 「其實」「基本上」「事實上」「總之」「然而」\n"
    "- NEVER use greetings: 「大家好」「歡迎觀看」「哈囉」\n"
    "- Write spoken language, NOT written language. Use 「超」「根本」「欸」"
    "「啦」「吧」「耶」 naturally\n\n"
    "SCIENTIFIC VERIFICATION (CRITICAL):\n"
    "- Every factual claim MUST be accurate and verifiable\n"
    "- Do NOT fabricate statistics, dates, names, or studies\n"
    "- If the topic involves science, cite real research or established knowledge\n"
    "- When mentioning studies or experiments, use real ones, not made-up ones\n"
    "- Prefer well-documented facts over sensational but unverifiable claims\n"
    "- If uncertain about a fact, use hedging language (「據研究」「目前認為」)\n\n"
    "TAIWAN LOCALIZATION (zh-TW):\n"
    "- Use Taiwan-specific terms: 計程車(not 出租車), 捷運(not 地鐵), 影片(not 視頻)\n"
    "- When a global fact can be connected to Taiwan, connect it naturally\n"
    "- Use Taiwan references: population 2300萬, familiar landmarks, local examples\n"
    "- Avoid mainland China-specific references unless the topic requires it\n\n"
    "ANTI-LISTICLE RULE:\n"
    "- NEVER create listicle-style content (「X個你不知道的...」「前N名...」)\n"
    "- Always build a narrative arc with setup, tension, and payoff\n"
    "- One cohesive story, not a list of disconnected facts"
)

VIDEO_LENGTH_SCENE_MAP: dict[str, tuple[int, int]] = {
    "short": (2, 3),
    "medium": (6, 10),
    "long": (10, 18),
}

# Chapter-count targets for long-form; scenes are derived per-chapter
VIDEO_LENGTH_CHAPTER_MAP: dict[str, tuple[int, int]] = {
    "medium": (4, 6),  # 5-10 min total, 4-6 chapters
    "long": (5, 8),    # 10-20 min total, 5-8 chapters
}

# Target total duration in seconds (used to budget chapter durations)
VIDEO_LENGTH_DURATION_TARGET: dict[str, tuple[int, int]] = {
    "short": (50, 65),
    "medium": (300, 600),    # 5-10 min
    "long": (600, 900),      # 10-15 min (algorithm sweet spot)
}

# Target seconds per scene inside a chapter (long-form)
LONG_FORM_SCENE_DURATION_RANGE: tuple[int, int] = (20, 40)


def _language_instruction(language: str) -> str:
    """Build the language instruction for prompts."""
    lang_name = LANGUAGE_NAMES.get(language, language)
    return (
        f"\n\nIMPORTANT: Write ALL output content (video_title, description, "
        f"narration, scene titles, tags) in {lang_name}. "
        f"The narration must sound natural when spoken aloud in {lang_name}."
    )


# ---------------------------------------------------------------------------
# Short-form outline guide
# ---------------------------------------------------------------------------

_SHORT_FORM_OUTLINE_GUIDE = (
    "\n\nSHORT-FORM VIDEO RULES (CRITICAL):\n"
    "- Total video: 50-65 seconds (sweet spot for completion rate). Each scene: 17-22 seconds\n"
    "- Pick ONE narrative structure (ordered by proven completion rate):\n"
    "  A) 懸念揭曉型 [推薦,完看率65-75%]: Hook(拋出驚人事實) → 鋪墊(為什麼？) → 揭曉(意想不到的答案)\n"
    "  B) 誤導反轉型 [完看率60-70%]: Hook(引導觀眾往A想) → 展開(加強A的印象) → 反轉(其實是B！)\n"
    "  C) 層層遞進型 [完看率55-65%]: Hook(小驚喜) → 升級(更大的驚喜) → 炸裂(最震撼的事實)\n"
    "- Default to 懸念揭曉型 unless the topic specifically benefits from a twist or escalation\n"
    "- 第一句話 = 停止滑動的武器（前3秒決定70-80%的觀眾去留）。用以下任一技巧：\n"
    "  · 反直覺事實：「飛機窗戶以前是方的」\n"
    "  · 挑戰認知：「你每天做的這件事，居然是錯的」\n"
    "  · 懸念問句：「為什麼日本的水溝蓋這麼美？」\n"
    "  · 台灣角度：「台灣在這件事上，居然是全球第一」\n"
    "- 每個場景結尾要留一個「開放迴圈」——讓觀眾想知道下一步\n"
    "- 最後一個場景必須有「頓悟時刻」，讓人想分享\n"
    "- 不要 CTA（訂閱、按讚），用一個讓人「哦！」的結尾"
)


# ---------------------------------------------------------------------------
# Short-form narration guides
# ---------------------------------------------------------------------------

_SHORT_FORM_NARRATION_GUIDE = (
    "\n\nSHORT-FORM NARRATION RULES:\n"
    "- 字數限制：55-70 個中文字（約 17-22 秒口語速度，3場景 = 50-65秒最佳完看率區間）\n"
    "- 每句話 ≤ 15 字。長短交替製造節奏感\n"
    "- 句型要多變：問句、驚嘆句、斷句、陳述句交替\n"
    "- 用口語，不是書面語。想像在跟朋友聊天\n"
    "- 禁止廢話：每一句都必須帶新資訊或情緒轉折\n"
    "- 情緒弧線：好奇 → 驚訝 → 恍然大悟（或其他起伏）\n"
    "- 用「開放迴圈」技巧：丟出問題 → 延遲解答 → 製造懸念\n"
    "- 語氣助詞自然使用：「欸」「啦」「吧」「耶」「天啊」"
)

_SHORT_FORM_OPENING = (
    "\n開場 Hook 技巧（前2秒內完成，不要鋪墊）：\n"
    "- 直接炸事實（最有效）：第一句話就是最強的數據或反直覺聲明\n"
    "  例：「超市擺24種果醬，只有3%的人會買。擺6種？30%。」\n"
    "  例：「你的鼻子能分辨一兆種氣味——比眼睛看到的顏色多一百倍。」\n"
    "- 好奇缺口：丟出讓人「蛤？」的事實，但先不解釋\n"
    "  例：「1950年代的飛機，窗戶竟然是方的。然後人就死了。」\n"
    "- 挑戰認知：否定觀眾以為正確的事\n"
    "  例：「你以為XX是因為OO？錯。完全相反。」\n"
    "- NEVER use 鋪墊式開場：「你有沒有想過...」「你有沒有這種經驗...」\n"
    "  這些開場到第3-4秒才進重點，70%觀眾已經滑走\n"
    "- 前 2 秒必須完成 hook，不要任何鋪墊、問候、設定"
)

_SHORT_FORM_HOOK_TEMPLATES = (
    "\n\n各主題領域 Hook 範例：\n"
    "- 科學/冷知識：「你知道[日常事物]其實[驚人事實]嗎？」「[聽起來錯但正確的事實]——科學家花了X年才證實。」\n"
    "- 心理學：「你每天都在做這件事，但你的大腦在騙你。」「[普遍行為]不是你以為的那樣——心理學家發現了真正原因。」\n"
    "- 科技/AI：「AI已經可以[驚人能力]。」「你的手機正在[意想不到的事]，你完全不知道。」\n"
    "- 歷史：「[現代事物]的發明者其實是[意想不到的人/文化]。」「[X]年前，[文化]就已經在做[現代事物]了。」\n"
    "- 太空/宇宙：「在[星球]上，[地球事物]會變成[外星結果]。」「NASA剛發現[驚人事實]，改寫了我們的認識。」\n"
)

_SHORT_FORM_CLOSING = (
    "\n結尾技巧：\n"
    "- 回扣開頭（最有效）：呼應第一句話，形成閉環，驅動重播\n"
    "  例：「所以下次你搭飛機看著那個圓窗戶，記得——它救了你的命。」\n"
    "- 反轉結尾：最後一句推翻前面的認知\n"
    "- 留言驅動問句：留一個讓觀眾想回答的問題，驅動互動\n"
    "  例：「你的那個味道是什麼？」「你覺得呢？」\n"
    "- 不要用 CTA（訂閱、按讚）\n"
    "- 不要用總結句（「所以說」「總而言之」）\n"
    "- 最後一句要有力量，讓人想分享或留言"
)

_SHORT_FORM_BODY = (
    "\n中段展開技巧：\n"
    "- 用「開放迴圈」：解答上一個問題的同時，拋出新的懸念\n"
    "- 加入情緒轉折：從好奇轉為震驚、從震驚轉為理解\n"
    "- 每 2-3 秒引入新元素（新事實、新角度、新情緒）\n"
    "- 避免平鋪直敘，要有「原來如此→等等不對→天啊」的節奏\n"
    "- REHOOK（注意力重置）：每 7-10 秒插入一次\n"
    "  用「但更扯的是」「等等」「重點來了」「你沒聽錯」重新抓住注意力\n"
    "  觀眾在 15-20 秒會自然分心，rehook 是防止中段流失的關鍵\n"
    "- 句子要短、斷句要多，讓剪輯可以每 2-3 秒切畫面"
)

# ---------------------------------------------------------------------------
# Few-shot example for short-form narration style
# ---------------------------------------------------------------------------

_SHORT_FORM_EXAMPLE = (
    "\n\n好的短影音旁白範例（風格參考）：\n"
    "---\n"
    "主題：為什麼飛機窗戶是圓的？\n"
    "場景1（Hook）：\n"
    "「1950年代，有一種飛機叫彗星客機。超美、超先進。\n"
    "但它有個致命的設計——方形窗戶。\n"
    "結果？兩架飛機，空中解體。」\n\n"
    "場景2（展開）：\n"
    "「方形窗戶的四個角，會集中所有壓力。\n"
    "飛到高空，金屬疲勞，裂縫就從角落開始。\n"
    "一裂開？整架飛機像氣球一樣炸開。」\n\n"
    "場景3（反轉結尾）：\n"
    "「所以工程師把窗戶改成圓的。沒有角，壓力均勻分散。\n"
    "就這麼一個小改變，從此再也沒有因為窗戶而墜機。\n"
    "你每次搭飛機看到那個圓窗戶——它救了你的命。」\n"
    "---"
)


_LONG_FORM_OUTLINE_GUIDE = (
    "\n\nLONG-FORM VIDEO RULES (CRITICAL for algorithm performance):\n"
    "- Target retention curve: 50-70% average across the full video\n"
    "- First 5 seconds = pattern interrupt, not preamble — state the most "
    "surprising claim or question up front\n"
    "- 0:00-0:30: clarify what the viewer will learn + raise stakes\n"
    "- Each chapter needs its own hook (first 5s) and payoff (last 5s)\n"
    "- Rehook every 60-90s inside long chapters to counter the 55-65% drop cliff\n"
    "- Chapters must form a coherent arc — not a disconnected list (unless "
    "listicle genre). Use chapter payoffs to tee up the next chapter's hook\n"
    "- Place a soft CTA/related-video tease in the second-to-last chapter, "
    "not at the very end (only 16% reach the final 10s)\n"
    "- Each chapter duration should be 60-180s. Total video 8-15 minutes.\n"
    "- start_timestamp of chapter 1 MUST be 0.0 (YouTube requires for chapter markers)\n"
    "- Subsequent chapters' start_timestamp = previous chapter's start + duration\n"
    "- hook field = a one-sentence line that opens the chapter\n"
    "- payoff field = the takeaway line the viewer should remember"
)


_GENRE_GUIDES: dict[GenreTemplate, str] = {
    GenreTemplate.KNOWLEDGE: (
        "\n\nGENRE: 知識解說型 (science / history / psychology explainer)\n"
        "- Chapter arc template: 1) 拋問題/反直覺事實 → 2) 釐清迷思 → "
        "3) 建立原理 → 4) 具體例子 → 5) 現實應用 → 6) 留白/反思\n"
        "- Each chapter: pick ONE sub-claim; do not jam 3 ideas into one chapter\n"
        "- Show, then tell: lead with a concrete example, then explain the principle\n"
        "- Use 「據研究」「目前認為」for uncertain claims — be intellectually honest\n"
        "- End with a question that invites the viewer to apply the framework to "
        "their own life"
    ),
    GenreTemplate.LISTICLE_RANKING: (
        "\n\nGENRE: 懶人包 / 排行榜型 (Top N)\n"
        "- Structure: Frame (0:00-0:30) → Count-up with escalating stakes → #1 payoff\n"
        "- Number in reverse (Top 5, Top 4 ... Top 1). Save the best for last\n"
        "- Each item needs: setup → surprise twist → why it matters\n"
        "- Escalate the 「扯度」 as you climb — earlier items can be mild, later must hit harder\n"
        "- End with a reveal about #1 that recontextualizes the earlier items"
    ),
    GenreTemplate.NEWS_ANALYSIS: (
        "\n\nGENRE: 時事分析 / 新聞解讀型\n"
        "- Structure: 事件概述 → 利害關係人 → 機制分析 → 台灣 / 個人影響 → 預測 / 立場\n"
        "- Present multiple angles fairly but land an editorial take\n"
        "- Use hedging for forecasts: 「有可能」「目前看起來」\n"
        "- Include a verifiable timeline of events — dates must be real\n"
        "- Connect to Taiwan context explicitly in at least one chapter"
    ),
    GenreTemplate.STORY_MYSTERY: (
        "\n\nGENRE: 故事 / 解謎型\n"
        "- Structure: Cold open (扔線索，不解釋) → 背景 → 線索堆疊 → 誤導 → 揭曉 → 尾聲\n"
        "- Withhold the key piece of information until 60-70% mark\n"
        "- Plant small details early that will pay off in the reveal\n"
        "- Each chapter should end with a new question, not a full answer"
    ),
}


_LONG_FORM_NARRATION_GUIDE = (
    "\n\nLONG-FORM NARRATION RULES:\n"
    "- Target duration: hit within ±10% of the given duration_seconds\n"
    "- zh-TW speaking rate ≈ 3.3 chars/sec → characters ≈ duration * 3.3\n"
    "- Sentence length: mix 5-word punchy lines with 15-20 word fuller ones\n"
    "- Every 20-25 seconds, insert a rehook phrase: 「但更扯的是」「等等」"
    "「這邊有個轉折」「重點來了」\n"
    "- Casual internet vocab is fine (嘴砲、假貨、帶風向、立人設、潛水)\n"
    "- Reduce 欸 usage; avoid trendy slang (狂、絕了)\n"
    "- b_roll_keywords: provide 2-3 DISTINCT English keyword queries per scene "
    "for B-roll variety. Stock providers work best with English.\n"
    "  example: ['taipei night market crowd', 'neon signs close up', 'street food vendor']"
)


def build_outline_prompt(request: ScriptRequest) -> str:
    """Build the prompt for generating a scene outline (short-form path, cheap model).

    For long-form, call build_chapter_outline_prompt instead.
    """
    min_s, max_s = VIDEO_LENGTH_SCENE_MAP[request.video_length.value]
    keywords_str = ", ".join(request.keywords) if request.keywords else "none specified"
    is_short = request.video_length == VideoLength.SHORT

    base = (
        f"Create a scene-by-scene outline for a {request.video_length.value}-length "
        f"YouTube video about: {request.topic}\n\n"
        f"Keywords to incorporate: {keywords_str}\n"
        f"Tone: {request.tone.value}\n"
        f"Number of scenes: between {min_s} and {max_s}\n\n"
        f"For each scene provide: scene_number, title, a brief summary of what "
        f"the narration should cover, and estimated duration_seconds.\n"
        f"Also provide a video_title, description, and relevant tags.\n\n"
        f"SOURCES: Set 'sources' to an empty list []. "
        f"Do NOT fabricate references — we will add verified sources separately."
    )

    if is_short:
        base += _SHORT_FORM_OUTLINE_GUIDE

    return base + _language_instruction(request.language)


def build_chapter_outline_prompt(request: ScriptRequest) -> str:
    """Build prompt for long-form chapter outline (cheap model).

    Returns a prompt that produces ChapterOutlineList with start_timestamp
    already set and chapter 1 at 0.0.
    """
    chap_min, chap_max = VIDEO_LENGTH_CHAPTER_MAP[request.video_length.value]
    dur_min, dur_max = VIDEO_LENGTH_DURATION_TARGET[request.video_length.value]
    keywords_str = ", ".join(request.keywords) if request.keywords else "none specified"

    base = (
        f"Create a CHAPTER-LEVEL outline for a {request.video_length.value} "
        f"YouTube video about: {request.topic}\n\n"
        f"Keywords to incorporate: {keywords_str}\n"
        f"Tone: {request.tone.value}\n"
        f"Orientation: {request.orientation.value}\n"
        f"Number of chapters: between {chap_min} and {chap_max}\n"
        f"Total video duration target: {dur_min}-{dur_max} seconds\n\n"
        f"For each chapter provide: chapter_number, title, summary (2-3 "
        f"sentences on what this chapter covers), duration_seconds, key_points "
        f"(3-5 bullet insights), hook (1-sentence opener), payoff (1-sentence "
        f"takeaway), and start_timestamp.\n\n"
        f"CRITICAL timestamp rule: chapter 1 start_timestamp = 0.0. "
        f"Each subsequent chapter's start_timestamp = previous chapter's "
        f"start_timestamp + its duration_seconds. YouTube chapter markers "
        f"require the first entry at exactly 0:00.\n\n"
        f"Also provide a video_title (click-worthy, 30-60 chars), description "
        f"(2-3 sentence YouTube description), and 8-15 relevant tags.\n\n"
        f"SOURCES: Set 'sources' to an empty list []. "
        f"Verified sources come from a separate research step."
    )

    base += _LONG_FORM_OUTLINE_GUIDE
    if request.genre is not None and request.genre in _GENRE_GUIDES:
        base += _GENRE_GUIDES[request.genre]

    return base + _language_instruction(request.language)


def build_chapter_scene_breakdown_prompt(
    *,
    request: ScriptRequest,
    chapter: ChapterOutline,
    total_chapters: int,
) -> str:
    """Build prompt to break ONE chapter into 2-5 scene outlines.

    Called once per chapter during long-form generation. Output validates
    against SceneOutlineList (reusing the existing schema).
    """
    min_s, max_s = LONG_FORM_SCENE_DURATION_RANGE
    scene_count_min = max(2, int(chapter.duration_seconds // max_s))
    scene_count_max = max(scene_count_min + 1, int(chapter.duration_seconds // min_s))

    base = (
        f"Break chapter {chapter.chapter_number}/{total_chapters} of the video "
        f"'{request.topic}' into a scene list.\n\n"
        f"Chapter title: {chapter.title}\n"
        f"Chapter summary: {chapter.summary}\n"
        f"Chapter hook: {chapter.hook}\n"
        f"Chapter payoff: {chapter.payoff}\n"
        f"Key points to cover: {'; '.join(chapter.key_points)}\n"
        f"Target duration: {chapter.duration_seconds:.0f} seconds\n\n"
        f"Produce {scene_count_min}-{scene_count_max} scenes. Each scene "
        f"{min_s}-{max_s} seconds. Scene durations must sum to the chapter "
        f"duration (±10%).\n\n"
        f"For each scene provide: scene_number (restart from 1 within this "
        f"chapter — we will renumber globally later), title, summary of what "
        f"the narration should cover, and duration_seconds.\n\n"
        f"Leave video_title as the chapter title, description as the chapter "
        f"summary, tags and sources as empty lists."
    )

    if request.genre is not None and request.genre in _GENRE_GUIDES:
        base += _GENRE_GUIDES[request.genre]

    return base + _language_instruction(request.language)


def build_scene_narration_prompt(
    *,
    topic: str,
    tone: str,
    language: str,
    scene_title: str,
    scene_summary: str,
    scene_number: int,
    total_scenes: int,
    duration_seconds: int,
    is_short_form: bool = False,
    is_long_form: bool = False,
    genre: GenreTemplate | None = None,
    chapter_number: int | None = None,
    chapter_title: str | None = None,
    is_chapter_opener: bool = False,
    is_chapter_closer: bool = False,
) -> str:
    """Build prompt for expanding a single scene's narration (expensive model)."""
    if scene_number == 1:
        position = "opening hook"
    elif scene_number == total_scenes:
        position = "closing/CTA"
    else:
        position = "body"

    base = (
        f"Write the full narration for scene {scene_number}/{total_scenes} "
        f"of a YouTube video about '{topic}'.\n\n"
        f"Scene title: {scene_title}\n"
        f"Scene summary: {scene_summary}\n"
        f"Target duration: {duration_seconds} seconds\n"
        f"Tone: {tone}\n"
        f"Position in video: {position}\n\n"
        f"Write natural, spoken narration that fits the target duration. "
        f"No stage directions. Include a visual_hint object describing what "
        f"the viewer should see on screen, with a description, style "
        f"(stock_footage/animation/text_overlay), and relevant keywords. "
        f"Keywords MUST be in English (stock video providers work best with English queries)."
    )

    if is_short_form:
        base += _SHORT_FORM_NARRATION_GUIDE
        if scene_number == 1:
            base += _SHORT_FORM_OPENING
            base += _SHORT_FORM_HOOK_TEMPLATES
        elif scene_number == total_scenes:
            base += _SHORT_FORM_CLOSING
        else:
            base += _SHORT_FORM_BODY
        base += _SHORT_FORM_EXAMPLE
    elif is_long_form:
        if chapter_number is not None and chapter_title is not None:
            base += (
                f"\n\nChapter context: you are writing for chapter "
                f"{chapter_number} titled '{chapter_title}'. "
            )
            if is_chapter_opener:
                base += (
                    "This is the chapter OPENER — deliver the chapter hook in "
                    "the first sentence."
                )
            elif is_chapter_closer:
                base += (
                    "This is the chapter CLOSER — land the chapter payoff and "
                    "tee up the next chapter."
                )
            else:
                base += "This is a mid-chapter body scene."
        base += _LONG_FORM_NARRATION_GUIDE
        if genre is not None and genre in _GENRE_GUIDES:
            base += _GENRE_GUIDES[genre]

    return base + _language_instruction(language)
