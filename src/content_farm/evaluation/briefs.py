"""Brief text for each reviewer (viewer persona or pro), with the JSON they must write."""

from __future__ import annotations

from pathlib import Path

from content_farm.evaluation.panel import Panels, Reviewer

VIEWER_SCHEMA = (
    '{"persona":"<id>","homepage":[{"feed":"<檔名>","noticed":[卡號,卡號,卡號],"picked":卡號,"why":"…"}],'
    '"click":{"A":n,"B":n,"C":n,"why":"…"},'
    '"segments":[{"t":"0:00-0:10","engagement":n,"decision":"stay|leave","why":"…","confusing":["…"],'
    '"hook":"…","audio":"對聲音的反應（可空）"}],'
    '"left_at":"m:ss 或 null","finish":true,"subscribe":false,'
    '"pronunciation":["你覺得念錯或聽起來怪的詞（可空）"],'
    '"top_fixes":[{"t":"m:ss","category":"visual|audio|content|fact","problem":"…","fix":"…"}],"overall":"…"}'
)

PRO_SCHEMA = (
    '{"role":"<editor|director|writer>","score":n,"rubric":{"<項目>":n},'
    '"issues":[{"t":"m:ss","category":"visual|audio|content|fact","severity":"high|med|low","problem":"…","fix":"…"}],'
    '"verdict":"…"}'
)

COMMON_RULES = """規則：
- 這是上線前的品質評審，目的是找出觀眾會流失的地方；不要客氣，不要比真人更有耐心。
- 你看不到動態影像、也聽不到聲音：畫面以截圖表（每 5 秒一格、每張 6 格、左上角是時間戳）呈現，
  聲音以 audio.txt 的每 10 秒描述呈現（語速、語調、BGM、音效、可能念錯的詞），請把它當成你「聽到」的。
- 只讀下面列出的檔案，不要讀這個資料夾以外或 .keys 裡的任何東西，不要修改任何檔案（除了你的結果檔）。
- 修正建議必須具體、可驗證（時間點＋要改什麼）；不要要求灌水內容或誇大縮圖。"""


def _materials(round_dir: Path, sheets: int, duration: str) -> str:
    return (f"素材（都在 {round_dir}/）：\n"
            f"- title.txt、description.txt：你在 YouTube 首頁／觀看頁看到的文字\n"
            f"- thumbnails/variant_*.jpg：這支片的縮圖（A／B／C 三款，YouTube 會輪流顯示）\n"
            f"- sheets/sheet_01.jpg … sheet_{sheets:02d}.jpg：影片畫面，依序讀完全部\n"
            f"- subtitles.srt：旁白逐字稿（含時間）\n"
            f"- audio.txt：每 10 秒的聲音描述\n"
            f"片長 {duration}。")


def viewer_brief(reviewer: Reviewer, round_dir: Path, *, sheets: int, duration: str, channel: str,
                 feeds: list[str], result: Path) -> str:
    feed_list = "\n".join(f"  - feeds/{name}" for name in feeds)
    return f"""{reviewer.description}

你要扮演上面這位觀眾，在 YouTube 上遇到一支「{channel}」頻道的長片，誠實記錄反應。

{_materials(round_dir, sheets, duration)}

做法：
0. 首頁一眼（先做這步，做完前不要看 thumbnails/ 和 title.txt）：依序打開下面每張首頁截圖，每張只「捲動看一眼」，
   不知道哪一張是我們的。每張記下：最先注意到的 3 張卡（卡號）、你最可能點的 1 張、為什麼。
{feed_list}
1. 看縮圖與標題：打開 title.txt 與 thumbnails/variant_A.jpg、variant_B.jpg、variant_C.jpg，各給點擊意願 0–10 與理由。
2. 依時間順序，每 10 秒一段（0:00-0:10、0:10-0:20 …），結合該段畫面、字幕與 audio.txt 的聲音描述，給：
   投入分數 0–10、此刻會不會離開（stay/leave，leave 寫原因）、聽不懂的詞、讓你想繼續的東西、對聲音的反應。
   照你的人設真實反應：若你在某段真的會離開，標出離開時間，之後仍繼續評分但在 why 註明「（若被拉回）」。
3. 最後：整體評價、會不會看完、會不會訂閱、你覺得念錯或聽起來怪的詞、前三個最該改的地方（附時間點、類別與具體改法）。

{COMMON_RULES}

輸出：把結果寫成 JSON 檔到 {result}，格式：
{VIEWER_SCHEMA}
回傳時只回 5 行內摘要（離開時間、最低三段、前三改法）。"""


def pro_brief(reviewer: Reviewer, panels: Panels, round_dir: Path, *, sheets: int, duration: str, channel: str,
              objective: Path, result: Path) -> str:
    pro = panels.pros[reviewer.role]
    rubric = "、".join(pro.rubric)
    return f"""{pro.brief}

你在審一支「{channel}」頻道的長片初剪，替製作團隊找出上片前該改的地方。

{_materials(round_dir, sheets, duration)}
- objective.json：自動量測（節拍、靜止、死區、響度、語速……），可用來佐證，不要只複述它

做法：看完全部素材後，依評分項目（{rubric}）各給 0–10，總分 0–10，列出問題（每條：時間點、類別、嚴重度、問題、具體改法），
最後一句結論。問題要能被驗證（指得出時間點與畫面／字句）。

{COMMON_RULES}

輸出：把結果寫成 JSON 檔到 {result}，格式：
{PRO_SCHEMA}
回傳時只回 5 行內摘要（總分、最嚴重三條）。"""
