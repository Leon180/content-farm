"""Producer agents (topic, article, deck, titles & thumbnails) as ``claude -p`` subprocesses that
write their files into the run-dir. model / effort come from the stage's ``producer`` tier in
review_panels.yaml. A rework call gets the routed fix list (``review/<gate>.fixes.json``) and
must touch only what the fixes and their linked scope name.

Each call returns a tiny JSON receipt (``RECEIPT``) so the result is schema-checked like a review.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from content_farm.review import quick_patch
from content_farm.review.brief import article_brief, channel_rules_text, deck_brief
from content_farm.review.quick_patch import quick_enabled
from content_farm.review.client import Call, CallResult, run_call
from content_farm.review.config import ReviewConfig, Tier
from content_farm.topic_radar.brief import radar_brief

REPO = Path(__file__).resolve().parents[3]
RECEIPT = {"type": "object", "additionalProperties": False, "required": ["files", "summary"],
           "properties": {"files": {"type": "array", "items": {"type": "string"}}, "summary": {"type": "string"},
                          "fixed": {"type": "array", "items": {"type": "string"}},
                          "rewrite_reason": {"type": "string", "description": "why a structure-level rewrite was needed "
                                                                              "(only when the fix list names no sentence)"}}}
TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch")   # + Bash scoped to the repo python

SCRIPTS = ("check_article.py", "deck_to_script.py", "apply_deck_patch.py", "make_thumbnail.py", "render_slides.py",
           "check_skit.py", "news.py")
TIMEOUT_S = {"topic": 1500, "article": 2700, "deck": 3600, "thumbnail_spec": 1800, "skit_script": 900,
             "news_script": 900}

# step → (stage whose producer tier applies, gate whose fixes apply)
STEP_STAGE = {"topic": ("topic", "topic"), "article": ("article", "article"), "deck": ("script_structure", "deck"),
              "thumbnail_spec": ("title_thumb", "title"), "skit_script": ("shorts_script", "script"),
              "news_script": ("shorts_script", "script")}
# a short channel's topic step is the shorts_topic stage (sonnet producer, not the long videos' opus plan stage)
SHORT_TOPIC_STAGE = "shorts_topic"

COMMON = """你是 content-farm（繁中 YouTube 內容工廠）的製作 agent，工作目錄就是這支片的 run-dir：{run_dir}
頻道設定：{repo}/channels/{channel}.yaml（讀它：品牌、角色、片長、規則）。既定規則：艱深名詞先用國高中程度比喻再給定義；
八卦和冷笑話穿插、八卦必須有來源；不給投資建議；不用別人影片的原片；不誇大標題縮圖。
只在 run-dir 內寫檔。不要 git commit、不要上傳任何東西、不要呼叫付費 API。"""

TASKS = {
    "topic": """任務：選題候選。從趨勢、Hacker News、新聞、頻道待辦清單（{repo}/channels/backlog/{channel}.yaml）整理 8–12 個候選，
排除 topics/channel_history.txt 裡已做過的題目。寫 topics/candidates.json：
{{"candidates":[{{"id":"t01","title":"標題草案","hook":"一句鉤子","minutes":8,"sources":["可查的來源網址"],"note":"為何適合這頻道"}}]}}
每題至少 2 個可公開查證的來源網址（用 WebSearch／WebFetch 確認存在），其中至少 1 個是一手來源（公司公告、財報、法說會、官方統計、論文）。
避開以傳聞為主、各家報價互相矛盾、主要數字沒有一手來源的題目（例如只靠媒體轉述的晶圓報價）：評審會直接扣分或淘汰。""",
    "article": """任務：研究與文章。題目在 topic.json 的 chosen[0]。照 {repo}/.claude/skills/article/SKILL.md 的做法（不要停下來等人審），
寫 article.md 與 sources.json。每個數字和八卦都附來源 id，來源要是你實際打開過的網址。
交出前逐條自我查核（兩位事實查核員會各自回頭查每個來源，任何一條錯誤或無來源就整篇退回）：
- 每個 [src:] 標記後面的那句話，來源原文要真的這樣說；你的推論、比喻、換算不要掛來源，寫成「換算起來」「也就是說」；
- 保留來源的限定詞：「據報導」「預定」「據稱」「估計」「規劃」「最先端用」等不能拿掉，範圍（台灣唯一≠全球唯一）不能放大；
- 報導刊登日≠事件發生日；說話的人要寫對（不同時期的社長是不同人），轉述媒體要寫轉述自誰（例如「日經報導、9to5Mac 轉述」）；
- 打不開或抽不出文字的來源（PDF、付費牆）不要當唯一依據；查不到就刪掉那句。
- 論點核心的因果（「因為 A 所以 B」）若來源沒有直接說，就寫成頻道自己的判斷（「我們的判斷是」「看起來」），不要寫成事實；
  引述要歸屬給來源裡真的說話的人（報導本身的敘述不是「業界主管說」）。
- 寫完跑 `{python} {repo}/scripts/check_article.py --run-dir {run_dir} --require-spine`，有問題改到 0 problem(s)。""",
    "deck": """任務：腳本。依 article.md，照 {repo}/.claude/skills/deck-outline/SKILL.md 與 {repo}/.claude/skills/deck/SKILL.md 的規則
（不要停下來等人審），直接寫 deck.json（可先寫 deck_outline.json），並寫 promise.txt：一句「這支片答應觀眾什麼」。
若有 review/article.story_notes.json（編劇對文章故事線的建議），在講稿裡處理，但不能新增文章沒有的事實。
寫完跑 `{python} {repo}/scripts/deck_to_script.py --run-dir {run_dir} --strict`，有錯就改到通過。
開場 15 秒內要有鉤子；每 5–10 秒要有留人的點；內容要撐得起片長，不要灌水。
事實（腳本的事實查核員會回到 sources.json 的網址逐條查）：
- 每個數字、日期、引述、因果都要能在 sources.json 的來源原文找到；歸屬寫對（報導是誰發的、話是誰說的），來源的限定詞（據報導、預估、規劃）不能拿掉；
- 文章或來源已過時的數字，用來源裡最新的狀態並寫出時間點；
- 查核員說「無來源」時：能找到可靠來源（官方、財報、主要媒體、論文，用 WebFetch 打開確認原文）就把它加進 sources.json
  （沿用既有欄位格式，新 id 不和舊的重複），投影片的來源列也一起改；找不到就刪掉或改寫成既有來源支持的說法；
- 頻道自己的推論、換算、判斷要在句子裡標明（「我們的判斷是」「換算起來」「看起來」），不能寫成來源或當事人的話。""",
    "thumbnail_spec": """任務：標題與縮圖。依 deck.json 與 promise.txt：
1. 寫 titles.json：{{"titles":[{{"id":"T1","text":"…"}}, …]}}，5–6 個標題（中文開頭、不誇大、承諾在講稿裡有兌現）。
2. 寫 thumbnail.json（主縮圖）與 thumbnail_variants.json（3 款：A 角色大表情、B 主視覺問句、C 數字對比），格式見
   {repo}/src/content_farm/production/thumbnail.py（ThumbnailSpec／ThumbnailVariants）；promise 必須是講稿前 60 秒內的原句。
3. 跑 `{python} {repo}/scripts/make_thumbnail.py --run-dir {run_dir} --channel {channel} --variants` 確認能渲染。""",
    "skit_script": """任務：冷笑話小劇場劇本。題目在 topic.json 的 chosen[0]（title、hook、note）。照 {repo}/.claude/skills/skit-script/SKILL.md 的格式與規則
（不要停下來等人審）寫 script.json：鋪陳 → 停 0.6 秒（最後一場鋪陳的 transition 填 pause:0.6）→ 笑點（≤ 40 字）→ 可省的收尾；總長 20–50 秒。
角色只有頻道設定裡的飲水機金魚（{repo}/channels/{channel}.yaml），不新增角色或設定；笑話必須原創，不搬運他人段子、不用其他頻道的口頭禪。
寫完跑 `{python} {repo}/scripts/check_skit.py --run-dir {run_dir}`，改到 0 problem(s)。""",
    "news_script": """任務：科技新聞 Short 稿（news_script.json）。這則的原文已讀過並快取：news_short.json（題目、來源、讀取時間、text_path 指到原文快取）。
照 {repo}/.claude/skills/news-short/SKILL.md 的五段格式與 lint 規則寫 news_script.json（不要停下來等人審）；頻道是「{channel}」：
讀 {repo}/channels/{channel}.yaml 的 identity 與 series.news。沒有角色（稿裡不要出現晶片貓或任何主持角色，pose 欄位留空）、
第五段是頻道自己的原創評論（標籤見 series.news.take_label，要看得出是觀點）、台灣中文口語、新聞感：結論先行、句子短、數字有單位。
只能用 text_path 裡實際讀到的原文當事實來源（討論串只當線索）；原文沒有台灣資料就照實說，不自己補數字。
sources 的 read_at 抄 news_short.json 的 read.read_at。寫完跑 `{python} {repo}/scripts/news.py lint --run-dir {run_dir}`，改到通過。""",
}
# Entertainment news (channel ent, series.news.claims_audit): the same five-beat Short, but every sentence of fact carries a
# claim the program checks against the page that was read (production/news/claims.py).
TASK_NEWS_CLAIMS = """任務：娛樂新聞 Short 稿（news_script.json）。這則的原文已讀過並快取：news_short.json（題目、read.url、read.read_at、read.text_path 指到原文快取）。
照 {repo}/.claude/skills/news-short/SKILL.md 的五段格式與 lint 規則寫 news_script.json（不要停下來等人審），頻道是「{channel}」，讀
{repo}/channels/{channel}.yaml 的 identity 與 series.news。本頻道的差異：沒有角色（pose 欄位留空）；第 3 段 why 是「背景脈絡」；
第 4 段 analogy 是「各方說法」（已證實的 vs 媒體報導的，term 填空字串，不需要比喻）；第 5 段 take 是頻道自己的原創編輯觀點（意見，不是事實）。
護欄——程式會逐句查，違反的句子會被自動刪掉或改寫，所以一開始就寫對：
1. 前四段（hook／what／why／analogy）的每一句事實，都要在該段的 claims 陣列有一筆 {{"sentence","source","status","evidence","confirmed_by"}}：
   sentence 與旁白那一句逐字相同；source＝news_short.json 的 read.url（只能引用這一頁）；evidence＝從 text_path 原文逐字複製的一段（至少 6 個字，
   原文是日文或英文就貼原文，不要翻譯、不要改字）。
2. status 只有兩種：confirmed＝當事人本人、經紀公司或官方自己說的（evidence 要是他們說話或發布聲明的那段，confirmed_by 寫是誰，且這個稱呼要出現在句子裡，
   例如「經紀公司證實…」）；其他一律 reported，句子必須寫成「據{{媒體名}}報導，…」（媒體名用 channels/{channel}.yaml series.news.feeds 的 name，例如「據自由時報報導」）。
   未經當事人或經紀公司證實的內容絕對不能直接講成事實。
3. 只能用這一篇原文的內容，不寫原文沒有的事、不加推測、不猜動機；不確定的句子就刪掉。
4. 不碰：未成年人、性醜聞細節、病情與死因臆測、私人住址與家人。題材碰到這些就停止，在回報裡說明做不下去，不要硬寫。
5. sources 只放白名單媒體（channels/{channel}.yaml series.news.feeds 的 domains），read_at 抄 read.read_at。
6. take（編輯觀點）不需要 claims，但不可斷言新的事實、不可指控或評論任何人的私生活。
台灣中文口語、新聞感：結論先行、句子短。寫完跑 `{python} {repo}/scripts/news.py lint --run-dir {run_dir}`，改到通過（句子的出處由後面的 audit 步驟再查一次）。"""
TASK_NEWS_CLAIMS_REWORK = """任務：娛樂新聞 Short 稿退回重做。news_script.json 已經存在；依下面的修改清單改被點名的句子
（句子 id c<場>.<序>，場＝第幾段 beat，從 1 起），其他段與 sources 不動。每一句事實仍要有 claims 裡逐字相同的一筆（source＝read.url、
evidence 從原文快取逐字複製）；傳聞一律寫成「據{{媒體名}}報導，…」，只有當事人／經紀公司／官方自己說的才標 confirmed 並在句子裡點名是誰。
改完跑 `{python} {repo}/scripts/news.py lint --run-dir {run_dir}`，改到通過。"""
# A short joke channel's topic step: jokes need no sources, only premises the single character can act out.
TASK_SKIT_TOPIC = """任務：冷笑話選題候選。讀 {repo}/channels/{channel}.yaml（topic_categories、角色飲水機金魚、規則）與
{repo}/channels/backlog/{channel}.yaml（kind: short、status 不是 dropped／published 的題目可沿用或改寫），整理 8–10 個原創冷笑話題目，
排除 topics/channel_history.txt 裡已做過的。不需要上網查資料。寫 topics/candidates.json：
{{"candidates":[{{"id":"t01","title":"標題草案（≤ 14 字，不爆雷）","hook":"一句話寫出：鋪陳 → 笑點","minutes":0.5,"sources":[],"note":"類別（topic_categories 之一）＋為何好笑"}}]}}
每題要能只靠一隻飲水機金魚在 20–50 秒內演完（鋪陳 → 停 0.6 秒 → 笑點）；不搬運他人段子、不改編既有梗圖或知名笑話的原句、
不拿真實公司事故或個人開玩笑、不講時事政治。題目之間類別要分散。"""


TASKS_REWORK = {
    "article": """任務：文章退回重做。article.md 與 sources.json 已經存在（不要重寫、不要重讀 skill 文件）；只依下面的修改清單處理被點名的句子。
改完跑 `{python} {repo}/scripts/check_article.py --run-dir {run_dir}`，有問題改到 0 problem(s)。""",
    "deck": """任務：腳本退回重做。deck.json 已經存在（不要整份重寫、不要重讀 skill 文件）；用 Edit 逐句改下面「要改的句子」，
其他句子、投影片、標題、說明欄一字不動（程式會逐句比對前後版本，改到沒被點名的部分就整份拒收並還原）。
改完跑 `{python} {repo}/scripts/deck_to_script.py --run-dir {run_dir} --strict`，有錯就改到通過。
事實規則同初稿：每個數字、日期、引述、因果要能在 sources.json 的來源原文找到；限定詞（據報導、預估、規劃）不能拿掉；
頻道自己的推論、換算要在句子裡標明；要補來源時沿用 sources.json 的欄位格式、新 id 不重複。
交件：receipt 的 fixed 列出處理了哪些句子 id；清單沒有指到任何具體句子（整體結構問題）時才可以重構，並在 rewrite_reason 寫明為什麼。""",
    "thumbnail_spec": """任務：標題與縮圖退回重做。titles.json、thumbnail.json、thumbnail_variants.json 已經存在；
只改清單點名的標題與縮圖款，沒被點名的標題一字不動（程式會比對）。
改完跑 `{python} {repo}/scripts/make_thumbnail.py --run-dir {run_dir} --channel {channel} --variants` 確認能渲染。""",
    "skit_script": """任務：冷笑話劇本退回重做。script.json 已經存在；依下面的修改清單改被點名的句子（句子 id c<場>.<序>），不要換題、不要換笑點的梗，
其他場景不動。結構（鋪陳／笑點／收尾 的 title、最後一場鋪陳的 transition pause:0.6、金魚表情）不能破壞。
整體問題（例如鋪陳太長、笑點沒翻轉）才可以重寫該場景。改完跑 `{python} {repo}/scripts/check_skit.py --run-dir {run_dir}`，改到 0 problem(s)。""",
    "news_script": """任務：科技新聞 Short 稿退回重做。news_script.json 已經存在；依下面的修改清單改被點名的句子
（句子 id c<場>.<序>，場＝第幾段 beat，從 1 起），改 beats[].narration／screen，其他段與 sources 不動，事實只能來自原文快取（news_short.json 的 text_path）。
改完跑 `{python} {repo}/scripts/news.py lint --run-dir {run_dir}`，改到通過；總長仍要在 lint 的秒數範圍內。""",
}
# Article sent back by the script_structure panel (Leon 2026-10-23): a structure-level rewrite, not a fact fix.
ARTICLE_STRUCTURE_REWORK = """任務：文章結構退回重做。腳本評審指出文章的結構問題（例如名詞表／時間軸堆疊、缺留人點、論點不推進）；article.md 與 sources.json 已經存在。
可以重構：調整段落與順序、改寫句子、加上懸念與過場、把表格改成敘事。限制（程式會比對改稿前後，違反就拒收並還原）：
- 已通過事實查核的句子（沿用原句或改寫後仍是同一句話的），數字與 [src:…] 來源 id 一個字都不能改、不能漏；
- 新寫的每一句都會被事實查核逐句查：有數字或八卦就附你實際打開過的來源 id，推論與換算要寫明「換算起來」「我們的判斷是」，不要新增沒查證的說法；
- 不准為了留人點編造情節、引述或數字。
改寫後同步更新 story_spine.json（鉤子、貫穿主線、每個轉折落在哪個章節）。
改完跑 `{python} {repo}/scripts/check_article.py --run-dir {run_dir} --require-spine`，有問題改到 0 problem(s)。
交件：receipt 的 rewrite_reason 必須寫明為什麼要大改、改了哪些結構（必填）。"""
NAMED_LIMIT = 14        # sentences quoted per rework brief


def _named_sentences(run_dir: Path, plan: dict, step: str) -> str:
    """The sentences the fix list names, with their current wording: the agent edits these and nothing else."""
    deck_path = run_dir / ("script.json" if step == "skit_script" else "deck.json")
    if step not in ("deck", "skit_script") or not deck_path.is_file():
        return ""
    from content_farm.review.sentences import deck_sentences, script_sentences
    from content_farm.review.touch_guard import named_in

    named = named_in(plan, step)
    if not named.sentence_ids:
        return ""
    read = script_sentences if step == "skit_script" else deck_sentences
    by_id = {s.id: s for s in read(json.loads(deck_path.read_text(encoding="utf-8")))}
    rows = [f"- {i}（{by_id[i].slide_id}）｜{by_id[i].text}" for i in sorted(named.sentence_ids) if i in by_id]
    more = f"\n（另有 {len(rows) - NAMED_LIMIT} 句見修改清單的連動範圍）" if len(rows) > NAMED_LIMIT else ""
    return "\n要改的句子（id｜現文）：\n" + "\n".join(rows[:NAMED_LIMIT]) + more


def _fixes_text(run_dir: Path, gate: str) -> str:
    path = run_dir / "review" / f"{gate}.fixes.json"
    if not path.is_file():
        return ""
    plan = json.loads(path.read_text(encoding="utf-8"))
    lines, deferred = [], []
    for step, slot in plan.get("steps", {}).items():
        for fix in slot["fixes"]:
            if gate == "article" and not is_fact(fix):
                deferred.append(fix)      # story notes: the script stage tells the story, the article stays facts
                continue
            scope = fix["scope"]
            frozen = (f"（原屬 {fix['rerouted_from']}，該步驟本次凍結不重做：在這一步處理——補可靠來源進 sources.json，"
                      "或刪掉／改寫成既有來源支持的說法）") if fix.get("rerouted_from") else ""
            lines.append(f"- [{step}]{frozen} {fix.get('problem')} → {fix.get('fix')}（指認：{json.dumps(fix.get('ref'), ensure_ascii=False)}；"
                         f"連動要一起改：句子 {', '.join(scope['sentence_ids']) or '—'}；標題 {', '.join(scope['titles']) or '—'}；"
                         f"縮圖 {'是' if scope['thumbnail'] else '否'}；說明欄 {'是' if scope['description'] else '否'}）")
    reasons = "；".join(plan.get("reasons", []))
    if deferred:
        (run_dir / "review" / "article.story_notes.json").write_text(
            json.dumps(deferred, ensure_ascii=False, indent=1), encoding="utf-8")
    delete_only = ""
    if gate in ("article", "deck_facts"):
        what = "旁白的每一句（句子 id）" if gate == "deck_facts" else "每一句"
        delete_only = (f"\n只准刪改（Leon 規則，程式會比對改稿前後{what}，違反就拒收並還原）：只能刪除被點名的句子，"
                       "或在被點名的句子裡加限定詞（「據報導」「估計」等）、改正數字與歸屬；不准新增句子、不准把一句拆成兩句、"
                       "沒被點名的句子一字不動。可以在 sources.json 補來源。")
    if gate == "deck_facts":
        delete_only += "這是講稿的事實段：結構已經核可，不要改章節、順序、比喻或笑點。"
    if plan.get("prompt_only"):
        delete_only += (f"\n這次只改 AI 插圖的提示詞（素材評審點名）：只准改投影片 {', '.join(plan['prompt_only'])} 的 "
                        "media.prompt，旁白、標題、條列、其他投影片與其他欄位一字不動（程式會比對，違反就拒收並還原）。"
                        "提示詞不能自相矛盾：頻道風格前綴已經寫了 no text, no seal 這類禁令，提示詞裡就不能再要求印章、"
                        "文字、題字等同一樣東西；被點名的舊圖已經移走，改完會換 seed 重畫。")
    return (f"\n這是退回重做（第 {plan.get('round')} 輪評審未過：{reasons}）。修改清單（{path}）：\n" + "\n".join(lines)
            + "".join(_named_sentences(run_dir, plan, step) for step in plan.get("steps", {}))
            + "\n只改清單與連動範圍列出的地方，其他句子一字不動（沒改到的句子 id 要保持不變）；"
              "改寫時不要新增沒查證過的說法——新寫的每一句一樣會被查核；"
              "不准為了分數灌水或誇大。fixed 欄位列出你處理了哪些。" + delete_only)


def is_fact(fix: dict) -> bool:
    """Article reworks carry only fact items (2026-10-18: in attempts 2 and 3 the rewrite for the
    story editor's notes added the new unsourced claims that failed the last round)."""
    return fix.get("category") == "fact" or str(fix.get("who", "")).startswith("fact_checker")


def is_skit_channel(channel: str) -> bool:
    """A 冷笑話小劇場 channel (pipeline ``shorts_skit``): its topic and script steps have their own tasks."""
    from content_farm.production.channels import Pipeline, load_channel

    try:
        return load_channel(channel).pipeline is Pipeline.SHORTS_SKIT
    except (FileNotFoundError, ValueError):     # an unknown channel code (tests, ad-hoc runs): the long-video tasks
        return False


def is_claims_channel(channel: str) -> bool:
    """An entertainment-news channel: its Short script carries sourced claims (series.news.claims_audit)."""
    from content_farm.production.channels import load_channel

    try:
        return bool((load_channel(channel).series.get("news") or {}).get("claims_audit"))
    except (FileNotFoundError, ValueError):
        return False


def producer_tier(config: ReviewConfig, step: str, *, skit: bool = False) -> Tier:
    stage, _ = STEP_STAGE[step]
    if skit and step == "topic":
        stage = SHORT_TOPIC_STAGE
    tier = config.stages[stage].producer
    return tier or Tier(model="sonnet", effort="medium")


def _log(log_dir: Path, step: str, **fields: object) -> None:
    with (log_dir / "producers.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "step": step, **fields},
                                ensure_ascii=False) + "\n")


def _quick(run_dir: Path, gate: str, channel: str, config: ReviewConfig, python: str,
           client: Callable[[Call], CallResult] | None, log_dir: Path, common: str) -> CallResult | None:
    """The small-rework fast path (``quick_patch``); the result when it applied and passed, else None (caller runs the agent)."""
    plan_path = run_dir / "review" / f"{gate}.fixes.json"
    if not plan_path.is_file() or not (run_dir / "deck.json").is_file():
        return None
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    rid = f"deck-{len(list(log_dir.glob('deck-*.prompt.md'))) + 1}"

    def call_for(prompt: str) -> CallResult:
        (log_dir / f"{rid}.prompt.md").write_text(prompt, encoding="utf-8")
        run = client or (lambda c: run_call(c, log_dir=log_dir))
        return run(quick_patch.build_call(rid, prompt, producer_tier(config, "deck"), run_dir))

    result, why = quick_patch.quick_deck(
        run_dir, plan, call_for=call_for, common=common, rules=channel_rules_text(channel),
        verify=lambda rd: quick_patch.strict_check(rd, python, REPO))
    if result is None:     # no call was made, so no usage row: producers.jsonl is read by the cost / budget code
        with (log_dir / "quick.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rid": rid,
                                     "skipped": why}, ensure_ascii=False) + "\n")
        return None
    _log(log_dir, "deck", quick=True, quick_ok=not why, quick_why=why, **result.to_json(), receipt=result.output)
    return None if why else result


def produce(step: str, run_dir: Path, *, channel: str, config: ReviewConfig, python: str,
            client: Callable[[Call], CallResult] | None = None, extra: str = "", gate: str | None = None) -> CallResult:
    """``extra``: appended to the brief (e.g. why the previous rewrite was refused). ``gate``: whose fix
    list this rework answers (the deck step serves both ``deck`` and ``deck_facts``)."""
    if step not in TASKS:
        raise ValueError(f"no producer agent for step {step!r}")
    gate = gate or STEP_STAGE[step][1]
    fmt = {"run_dir": run_dir, "repo": REPO, "channel": channel, "python": python}
    fixes = _fixes_text(run_dir, gate)
    skit = is_skit_channel(channel)
    task = TASKS_REWORK[step] if fixes and step in TASKS_REWORK else TASKS[step]     # a rework is a diff, not a redo
    if skit and step == "topic":
        task = TASK_SKIT_TOPIC
    if step == "news_script" and is_claims_channel(channel):
        task = TASK_NEWS_CLAIMS_REWORK if fixes else TASK_NEWS_CLAIMS
    if step == "article" and fixes and gate != "article":      # sent back by the script panel: a structure rewrite
        task = ARTICLE_STRUCTURE_REWORK
    guide = (deck_brief(config, channel, python, str(REPO), rework=task is TASKS_REWORK[step])
             if step == "deck" else "")          # rubric + channel rules + Bash, from the first call
    if step == "article" and (task is TASKS["article"] or task is ARTICLE_STRUCTURE_REWORK):
        guide = article_brief(config)            # narrative spine + the script panel's rubric (not for a fact-fix rework)
    radar = radar_brief(run_dir, channel) if step == "topic" and not fixes else ""   # first pass only: a rework is a diff
    prompt = "\n\n".join(part for part in (COMMON.format(**fmt), task.format(**fmt), radar, guide, fixes,
                                           extra, "完成後用結構化輸出回報寫了哪些檔。") if part)
    tier = producer_tier(config, step, skit=skit)
    log_dir = run_dir / "review" / "producers"
    log_dir.mkdir(parents=True, exist_ok=True)
    if step == "deck" and fixes and quick_enabled():       # a small rework: one no-tool turn, the program applies it
        done = _quick(run_dir, gate, channel, config, python, client, log_dir, COMMON.format(**fmt))
        if done is not None:
            return done
    rid = f"{step}-{len(list(log_dir.glob(f'{step}-*.prompt.md'))) + 1}"
    (log_dir / f"{rid}.prompt.md").write_text(prompt, encoding="utf-8")
    # Claude Code matches Bash prefixes word by word, so each allowed script is named (a "scripts/" prefix never matched).
    tools = (*TOOLS, *(f"Bash({python} {REPO}/scripts/{name}:*)" for name in SCRIPTS))
    # Read access: the repo's rules and code, never output/ (2026-10-18: an attempt-2 agent read attempt 1's
    # reviewer results through a repo-wide --add-dir).
    dirs = tuple(REPO / d for d in (".claude/skills", "channels", "src", "scripts", "assets"))
    call = Call(rid, prompt, RECEIPT, tier.model, tier.effort, tools=tools, cwd=run_dir, add_dirs=dirs,
                env=(("PYTHONPATH", str(REPO / "src")),),
                timeout_s=TIMEOUT_S[step], retries=1, write_tools=True,   # one retry: network drops (2026-10-18)
                trace=os.environ.get("CF_PRODUCER_TRACE", "1") != "0")   # per-step trace → <rid>.trace1.json
    result = (client or (lambda c: run_call(c, log_dir=log_dir)))(call)
    with (log_dir / "producers.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "step": step,
                                 **result.to_json(), "receipt": result.output}, ensure_ascii=False) + "\n")
    return result
