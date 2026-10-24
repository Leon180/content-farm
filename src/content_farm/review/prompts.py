"""Reviewer prompts. The output format is enforced by ``--json-schema``; the prompt says what to
judge, which files to read, and the shared rules (verifiable refs, verbatim evidence, the step
that caused each issue, no padding or exaggeration)."""

from __future__ import annotations

from pathlib import Path

from content_farm.review.config import Role
from content_farm.review.materials import Materials

CAUSED_BY = ("caused_by：問題是哪一步造成的——topic（選題）、article（研究文章）、deck（講稿與分鏡）、"
             "thumbnail_spec（標題縮圖）、voice（配音／念錯）、illustrate（AI 插圖）、media（素材／B-roll）、"
             "assembly（剪接／字幕）、mascot（角色疊加）、mix（配樂混音）；冷笑話小劇場的劇本問題（鋪陳、笑點、停頓、用字）填 skit_script，不要填 deck。")

# Topic rubric (cf-chipcat-run2, from run1: a 3 nm wafer-price topic lived on rumour and conflicting quotes, and its
# fact items kept coming back). Applies to the pro and producer topic seats.
SOURCE_RISK = ("來源風險（扣分項）：題目的主要數字或主張若以傳聞為主、各家報價互相矛盾、或沒有一手來源（公司公告、財報、法說會、"
               "官方統計、論文），分數壓到 4 以下（score ≤ 4）；三項全中或整題靠單一傳聞就 veto。"
               "候選題的 sources 全是轉述報導、沒有一手來源，也算沒有一手來源。")

# Topic radar (topic_radar/): candidates may carry evidence, competitors and viewer_questions. A ranking aid, never a gate.
RADAR_EVIDENCE = ("候選題若附 evidence（需求數字＋來源網址）、competitors（同類影片前 5 名觀看數）、viewer_questions（留言裡觀眾在問的），"
                  "把它們當排序依據：需求數字高、近一年的同類影片少、觀眾有明確提問的題目加分。沒有 evidence 的題目不扣分、不設門檻；"
                  "evidence 的數字與網址不可信時（對不上題目、看不出出處）才扣分。")

RULES = f"""共同規則：
- 這是上線前的品質評審，目的是找出觀眾會流失或被誤導的地方；不要客氣，不要比真人更有耐心。
- 只讀下面列出的檔案（都在目前資料夾），不要讀其他地方，不要修改任何檔案。
- 每個問題都要可驗證：ref 指出句子 id（講稿類）、時間點 m:ss（影片類）、或項目 id（候選題、標題 id、縮圖款 A/B/C、素材 id）；
  evidence 必須是素材裡的原文逐字引用（講稿／文章／標題的原句），影片畫面類則寫該時間點畫面上看得到的字。
- {CAUSED_BY}
- 修改建議要具體（要改成什麼），不准要求灌水內容、不准建議誇大標題或縮圖。
- 只列「不改就會讓觀眾流失、被誤導或事實錯」的問題；偏好、可改可不改的潤飾不要列，寧可少列不要湊數。
  每位評審最多 8 個問題（觀眾 top_fixes 最多 3 個），依嚴重度由重到輕；分數 ≥ 8 的評分項目不要列問題。
- sentence_ids 只放「必須改寫或刪除的句子」，每個問題最多 4 句；同一類毛病出現在很多處時，放最嚴重的 4 句，其餘寫在 problem 的「同型：」文字裡。
- 講稿類問題一定要有 sentence_ids。真的是全片性問題、縮不到具體句子時，才設 ref.scope="global"，並在 ref.why_global 寫一句為什麼縮不下來。
- claim_change=true 只在這個修改會推翻整章結論時才設，並把受影響的投影片 id 填進 affected_slides（最多 3 張）；程式只要求改那幾張。
- 用繁體中文寫。"""


def _files(materials: Materials, extra: list[str] | None = None) -> str:
    lines = [f"- {name}：{materials.notes.get(name, '')}" for name in materials.files]
    lines += [f"- {name}：首頁截圖" for name in extra or []]
    return "素材：\n" + "\n".join(lines)


STAGE_TASK = {
    "topic": {
        "viewer": "你在 YouTube 首頁看到這些題目當標題。每一題給點擊意願 0–10（picks 要涵蓋每個候選 id）與一句理由。",
        "pro": "評每個候選題（scores 涵蓋每個 id）：這題撐不撐得起一支 8–10 分鐘、有起承轉合的故事？0–10。"
               "veto＝撐不起或只是新聞稿。" + SOURCE_RISK + RADAR_EVIDENCE,
        "producer": "評每個候選題（scores 涵蓋每個 id）：跟頻道合不合、有沒有和已做過的題目重複（duplicate_of）、"
                    "來源夠不夠可查、會不會變成投資建議。0–10；不合格就 veto。" + SOURCE_RISK + RADAR_EVIDENCE,
    },
    "article": {
        "fact": "逐條列出文章中所有可查證的說法（數字、日期、引述、因果、八卦），每條回到來源網址查證，填 claims。"
                "status：ok＝來源原文支持；wrong＝來源說的不一樣；unsourced＝沒附來源或來源沒有這件事；"
                "unverifiable＝來源打不開；analysis＝頻道自己的換算、推論或觀點，而且文中明確寫成換算／推論／判斷"
                "（例如「換算起來」「我們的判斷是」），你驗算過數學、邏輯也站得住——寫成事實的推論一律算 unsourced，"
                "算錯算 wrong。source_quote 寫來源原文。每條都填 confidence（0–1）：你有多確定它是錯誤或無來源，ok／analysis 填你有多確定它沒問題的反面即可（填 0）；低於 0.5 只記錄不修，所以沒把握就誠實填低。錯誤與無來源的也要寫進 issues（caused_by=article）。",
        "pro": "評這篇文章的故事線：論點是否一路推進、開頭是否有鉤子、八卦是否有來源、名詞是否先用比喻。依 rubric 各給 0–10。",
    },
    "script": {
        "viewer": "依序讀講稿，想像這是你在看的影片（每句後面的時間是估計）。每張投影片（slide_id）給投入 0–10 與 stay/leave；"
                  "照你的人設，標出你會離開的那一句（left_at_sentence，看完就 null）。top_fixes 最多 3 條；"
                  "有離開時第一條的 sentence_ids 第一個必須是 left_at_sentence，後面最多再放 3 句造成離開的原因，不要列整頁或整章。",
        "pro": "依 rubric 評講稿與分鏡，各項 0–10，總分 score 0–10。問題用句子 id 指認。",
        "fact": "逐條查講稿中的事實說法（數字、單位、日期、引述、因果），對照 article.md 與 sources.json 的原始網址（用 WebFetch），"
                "確認改稿後沒有走樣：單位、基準、「據報導」等限定詞不能掉。claims 的 sentence_ids 寫句子 id。"
                "status：ok／wrong／unsourced／unverifiable；analysis＝頻道自己的換算或判斷、文中明確寫成換算／判斷且你驗算過"
                "（寫成事實的推論算 unsourced，算錯算 wrong）。每條都填 confidence（0–1）：你有多確定它是錯誤或無來源；低於 0.5 只記錄不修。",
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
        "viewer": "看完所有截圖表與字幕，每 10 秒一段給投入 0–10 與 stay/leave；"
                  "標出離開時間 left_at（m:ss，看完就 null）；thumbnail_matches＝縮圖與片中內容一致嗎；"
                  "pronunciation 填空陣列。不評聲音（配音、語速、配樂、音效、響度都不在評審範圍）。top_fixes 最多 3 條，影片問題 ref.t 寫時間點。",
        "pro": "依 rubric 評這支成片，各項 0–10，總分 score；問題寫時間點（ref.t）與造成它的步驟。可用 objective.json 佐證（沒有聲音欄，聲音不在評審範圍），不要只複述它。",
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
    materials = materials.visible_to(role.kind)     # a reviewer is listed only the files it needs
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
