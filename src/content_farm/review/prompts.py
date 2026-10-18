"""Reviewer prompts. The output format is enforced by ``--json-schema``; the prompt says what to
judge, which files to read, and the shared rules (verifiable refs, verbatim evidence, the step
that caused each issue, no padding or exaggeration)."""

from __future__ import annotations

from pathlib import Path

from content_farm.review.config import Role
from content_farm.review.materials import Materials

CAUSED_BY = ("caused_by：問題是哪一步造成的——topic（選題）、article（研究文章）、deck（講稿與分鏡）、"
             "thumbnail_spec（標題縮圖）、voice（配音／念錯）、illustrate（AI 插圖）、media（素材／B-roll）、"
             "assembly（剪接／字幕）、mascot（角色疊加）、mix（配樂混音）。")

RULES = f"""共同規則：
- 這是上線前的品質評審，目的是找出觀眾會流失或被誤導的地方；不要客氣，不要比真人更有耐心。
- 只讀下面列出的檔案（都在目前資料夾），不要讀其他地方，不要修改任何檔案。
- 每個問題都要可驗證：ref 指出句子 id（講稿類）、時間點 m:ss（影片類）、或項目 id（候選題、標題 id、縮圖款 A/B/C、素材 id）；
  evidence 必須是素材裡的原文逐字引用（講稿／文章／標題的原句），影片畫面類則寫該時間點畫面上看得到的字。
- {CAUSED_BY}
- 修改建議要具體（要改成什麼），不准要求灌水內容、不准建議誇大標題或縮圖；改動會牽動章節主張時把 claim_change 設為 true。
- 用繁體中文寫。"""


def _files(materials: Materials, extra: list[str] | None = None) -> str:
    lines = [f"- {name}：{materials.notes.get(name, '')}" for name in materials.files]
    lines += [f"- {name}：首頁截圖" for name in extra or []]
    return "素材：\n" + "\n".join(lines)


STAGE_TASK = {
    "topic": {
        "viewer": "你在 YouTube 首頁看到這些題目當標題。每一題給點擊意願 0–10（picks 要涵蓋每個候選 id）與一句理由。",
        "pro": "評每個候選題（scores 涵蓋每個 id）：這題撐不撐得起一支 8–10 分鐘、有起承轉合的故事？0–10。"
               "veto＝撐不起或只是新聞稿。",
        "producer": "評每個候選題（scores 涵蓋每個 id）：跟頻道合不合、有沒有和已做過的題目重複（duplicate_of）、"
                    "來源夠不夠可查、會不會變成投資建議。0–10；不合格就 veto。",
    },
    "article": {
        "fact": "逐條列出文章中所有可查證的說法（數字、日期、引述、因果、八卦），每條回到來源網址查證，填 claims。"
                "status：ok＝來源原文支持；wrong＝來源說的不一樣；unsourced＝沒附來源或來源沒有這件事；"
                "unverifiable＝來源打不開；analysis＝頻道自己的換算、推論或觀點，而且文中明確寫成換算／推論／判斷"
                "（例如「換算起來」「我們的判斷是」），你驗算過數學、邏輯也站得住——寫成事實的推論一律算 unsourced，"
                "算錯算 wrong。source_quote 寫來源原文。錯誤與無來源的也要寫進 issues（caused_by=article）。",
        "pro": "評這篇文章的故事線：論點是否一路推進、開頭是否有鉤子、八卦是否有來源、名詞是否先用比喻。依 rubric 各給 0–10。",
    },
    "script": {
        "viewer": "依序讀講稿，想像這是你在看的影片（每句後面的時間是估計）。每張投影片（slide_id）給投入 0–10 與 stay/leave；"
                  "照你的人設，標出你會離開的那一句（left_at_sentence，看完就 null）。top_fixes 最多 3 條。",
        "pro": "依 rubric 評講稿與分鏡，各項 0–10，總分 score 0–10。問題用句子 id 指認。",
        "fact": "逐條查講稿中的事實說法（數字、單位、日期、引述、因果），對照 article.md 與 sources.json 的原始網址（用 WebFetch），"
                "確認改稿後沒有走樣：單位、基準、「據報導」等限定詞不能掉。claims 的 sentence_ids 寫句子 id。"
                "status：ok／wrong／unsourced／unverifiable；analysis＝頻道自己的換算或判斷、文中明確寫成換算／判斷且你驗算過"
                "（寫成事實的推論算 unsourced，算錯算 wrong）。",
    },
    "title_thumb": {
        "viewer": "先做首頁一眼（做完前不要看 thumbnails/ 和 titles.txt）：依序打開每張首頁截圖，每張只捲過一眼，"
                  "不知道哪一張是我們的；記下最先注意到的 3 張卡號（noticed）、最可能點的 1 張（picked），"
                  "feed 欄位照抄首頁截圖的檔名（含 .jpg）。"
                  "然後打開 titles.txt 給每個標題點擊意願 0–10（titles），再看 thumbnails/ 每款給點擊意願（thumbnails：{\"A\":n,…}）。",
        "designer": "把每款縮圖想像縮到手機首頁 168 px 寬：字讀不讀得到、對比、構圖、主體大小、角色表情、三款差異夠不夠。"
                    "variants 給每款 0–10。",
        "producer": "逐一檢查每個標題 id 與每款縮圖（checks 的 item 寫標題 id 或 A/B/C）：有沒有誇大、跟講稿內容是否一致"
                    "（承諾在講稿裡有兌現嗎）、有沒有投資建議或聳動用語。",
    },
    "media": {
        "compliance": "逐一檢查每張素材（assets 的 asset 寫 slide id 或檔名）：有沒有可讀的公司名或 logo、像不像真人或官方角色、"
                      "credits.json 的授權是否可營利。有問題的寫進 issues（ref.item＝素材 id，caused_by=media 或 illustrate）。",
    },
    "final": {
        "viewer": "看完所有截圖表、字幕與 audio.txt（把聲音描述當成你聽到的），每 10 秒一段給投入 0–10 與 stay/leave；"
                  "標出離開時間 left_at（m:ss，看完就 null）；thumbnail_matches＝縮圖與片中內容一致嗎；"
                  "pronunciation＝聽起來念錯的詞。top_fixes 最多 3 條，影片問題 ref.t 寫時間點。",
        "pro": "依 rubric 評這支成片，各項 0–10，總分 score；問題寫時間點（ref.t）與造成它的步驟。可用 objective.json 佐證，不要只複述它。",
    },
}
STAGE_TASK["shorts_topic"] = STAGE_TASK["topic"]
STAGE_TASK["shorts_script"] = STAGE_TASK["script"]
STAGE_TASK["shorts_title"] = STAGE_TASK["title_thumb"]
STAGE_TASK["shorts_final"] = STAGE_TASK["final"]

STAGE_INTRO = {
    "topic": "你在幫「{channel}」頻道挑下一支片的題目。",
    "article": "你在審「{channel}」頻道一支片的研究文章（之後會改寫成影片講稿）。",
    "script": "你在審「{channel}」頻道一支長片的講稿與分鏡（還沒配音）。",
    "title_thumb": "你在審「{channel}」頻道一支片的標題與縮圖。",
    "media": "你在審「{channel}」頻道一支片用到的素材。",
    "final": "你在審「{channel}」頻道一支片的成片（上片前最後一關）。",
}


BASE_STAGE = {"shorts_topic": "topic", "shorts_script": "script", "shorts_title": "title_thumb",
              "shorts_final": "final", "script_structure": "script", "script_facts": "script"}


def _task(stage: str, kind: str) -> str:
    tasks = STAGE_TASK.get(stage, {})
    return tasks.get(kind) or tasks.get("pro") or ""


def build(stage: str, role: Role, materials: Materials, *, channel: str, persona: str = "",
          feeds: list[str] | None = None) -> str:
    base = BASE_STAGE.get(stage, stage)
    intro = STAGE_INTRO.get(base, STAGE_INTRO["final"]).format(channel=channel)
    if stage.startswith("shorts_"):
        intro += "這是一支 20–60 秒的直式 Short。"
    who = persona if role.kind == "viewer" else f"{role.brief}\n評分項目：{'、'.join(role.rubric)}" if role.rubric \
        else role.brief
    duration = materials.extra.get("duration_text")
    return "\n\n".join(part for part in (
        who, intro, _files(materials, feeds), f"片長 {duration}。" if duration else "",
        "要做的事：" + _task(base, role.kind), RULES,
        "完成後用結構化輸出回傳結果（格式由系統強制）。") if part)


def round_paths(round_dir: Path) -> tuple[Path, Path]:
    return round_dir / "prompts", round_dir / "results"
