"""Prompt templates for script generation. Pure functions, no side effects."""

from __future__ import annotations

from content_farm.script_gen.schemas import ScriptRequest
from content_farm.types import VideoLength

LANGUAGE_NAMES: dict[str, str] = {
    "zh-TW": "Traditional Chinese (繁體中文)",
    "zh-CN": "Simplified Chinese (简体中文)",
    "en": "English",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
}

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
    "- If uncertain about a fact, use hedging language (「據研究」「目前認為」)"
)

VIDEO_LENGTH_SCENE_MAP: dict[str, tuple[int, int]] = {
    "short": (2, 3),
    "medium": (6, 10),
    "long": (10, 18),
}


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
    "- Total video: 30-90 seconds. Each scene: 15-30 seconds MAX\n"
    "- Pick ONE narrative structure:\n"
    "  A) 懸念揭曉型: Hook(拋出驚人事實) → 鋪墊(為什麼？) → 揭曉(意想不到的答案)\n"
    "  B) 誤導反轉型: Hook(引導觀眾往A想) → 展開(加強A的印象) → 反轉(其實是B！)\n"
    "  C) 層層遞進型: Hook(小驚喜) → 升級(更大的驚喜) → 炸裂(最震撼的事實)\n"
    "- 第一句話 = 停止滑動的武器。用以下任一技巧：\n"
    "  · 反直覺事實：「飛機窗戶以前是方的」\n"
    "  · 挑戰認知：「你每天做的這件事，居然是錯的」\n"
    "  · 懸念問句：「為什麼日本的水溝蓋這麼美？」\n"
    "- 每個場景結尾要留一個「開放迴圈」——讓觀眾想知道下一步\n"
    "- 最後一個場景必須有「頓悟時刻」，讓人想分享\n"
    "- 不要 CTA（訂閱、按讚），用一個讓人「哦！」的結尾"
)


# ---------------------------------------------------------------------------
# Short-form narration guides
# ---------------------------------------------------------------------------

_SHORT_FORM_NARRATION_GUIDE = (
    "\n\nSHORT-FORM NARRATION RULES:\n"
    "- 字數限制：50-80 個中文字（約 15-25 秒口語速度）\n"
    "- 每句話 ≤ 15 字。長短交替製造節奏感\n"
    "- 句型要多變：問句、驚嘆句、斷句、陳述句交替\n"
    "- 用口語，不是書面語。想像在跟朋友聊天\n"
    "- 禁止廢話：每一句都必須帶新資訊或情緒轉折\n"
    "- 情緒弧線：好奇 → 驚訝 → 恍然大悟（或其他起伏）\n"
    "- 用「開放迴圈」技巧：丟出問題 → 延遲解答 → 製造懸念\n"
    "- 語氣助詞自然使用：「欸」「啦」「吧」「耶」「天啊」"
)

_SHORT_FORM_OPENING = (
    "\n開場 Hook 技巧（選一個）：\n"
    "- 好奇缺口：丟出一個讓人「蛤？」的事實，但先不解釋\n"
    "  例：「1950年代的飛機，窗戶竟然是方的。然後人就死了。」\n"
    "- 挑戰認知：否定觀眾以為正確的事\n"
    "  例：「你以為XX是因為OO？錯。完全相反。」\n"
    "- 畫面描述：描述一個戲劇性場景\n"
    "  例：「想像你在三萬英尺高空，窗戶突然裂開...」\n"
    "- 前 3 秒必須完成 hook，沒有任何前置鋪墊"
)

_SHORT_FORM_CLOSING = (
    "\n結尾技巧：\n"
    "- 反轉結尾：最後一句推翻前面的認知\n"
    "- 回扣開頭：呼應第一場景丟出的問題，形成閉環\n"
    "- 餘韻結尾：留下一個讓人繼續想的問題\n"
    "  例：「所以下次你搭飛機看著那個圓窗戶，記得——它救了你的命。」\n"
    "- 不要用 CTA（訂閱、按讚、留言）\n"
    "- 不要用總結句（「所以說」「總而言之」）\n"
    "- 最後一句要有力量，讓人想分享給朋友"
)

_SHORT_FORM_BODY = (
    "\n中段展開技巧：\n"
    "- 用「開放迴圈」：解答上一個問題的同時，拋出新的懸念\n"
    "- 加入情緒轉折：從好奇轉為震驚、從震驚轉為理解\n"
    "- 每 5-7 秒引入新元素（新事實、新角度、新情緒）\n"
    "- 避免平鋪直敘，要有「原來如此→等等不對→天啊」的節奏"
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


def build_outline_prompt(request: ScriptRequest) -> str:
    """Build the prompt for generating a scene outline (cheap model)."""
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
        elif scene_number == total_scenes:
            base += _SHORT_FORM_CLOSING
        else:
            base += _SHORT_FORM_BODY
        base += _SHORT_FORM_EXAMPLE

    return base + _language_instruction(language)
