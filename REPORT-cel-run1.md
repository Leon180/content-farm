# REPORT — cel run1（賽璐璐研究室，夜間循環）

## TL;DR
- **更新（續跑後，最終）**：🔴 仍**未到 gate_final**。orchestrator 允許 new-cycle 續跑後，article 過、deck 的 script_structure 兩輪未過 → 退回 article（結構改寫）→ article 再 3 輪用完（剩「七類」數量說法 1 項）。累計 **$7.03／$20**，牆鐘 45m55s。詳見「續跑」節。以下 TL;DR 為第一階段（cycle-1）狀況：
- 🔴 第一階段停在 `gate_article` 第 3 輪（最後一輪）。累計 **$3.64／$20**，牆鐘 16 分。沒有成片、沒有 540p 預覽。
- 新題（評審團自選）：「重畫不給錢、說取消就取消？日本公平會第一次替動畫業寫了交易規則」（一手來源：公平會指針／報道發表／實態調查，viewer 8.33、pro 9.25）。topic 1 輪過。
- 🟢 實跑逼出 **2 個程式缺口，已修並附測試**（見下）。第 2 個修正是在 round 3 停下**之後**才找到，所以這次 round 3 的結果未被重新計分——**按「最多 3 輪」規則，我沒有 new-cycle、沒有多跑輪次**。
- 🟡 若第 2 個修正早在，round 3 的唯一剩餘項（助手報酬一句）仲裁官其實判了 `ok`，該輪很可能就過了；未驗證，因為重跑只會重放已存的 exhausted 結果（我重跑一次確認過，$0）。

## 續跑（orchestrator 07:00 UTC 指示：`new-cycle --reason` 後續跑，再 3 輪不過就停）
- `new-cycle --stage article --reason "arbiter key bug fixed in 4be4e21; R3 remaining item was ruled ok"`（輪次歸到 `review/article/cycle-1/`）。
- cycle-2：article R1 **未過**但改稿（1 次）後 R2 **過**（仲裁 key 修正生效，不再誤計）→ deck-1 初稿（5m14s）→ **script_structure R1 未過**（離開中位 20%＜40%、writer_density 5.5＜6.5）→ deck 改稿 → **R2 未過**（離開中位 26%、writer_story 6、writer_density 6）→ 退回 article（結構改寫路徑，chipcat run2 A1 **首次實跑**）：
  agent 改寫 2 次，第 1 次被事實鎖定拒收（p16.1／p28.2 已查核句的數字或來源 id 被動），第 2 次通過 → article **R3（cycle-2 的最後一輪）未過**：確認 1 個錯誤（仲裁維持 1）。
- 最後停下點（原文）：`gate_article: article: 第 3 輪（最後一輪）未通過：確認 1 個錯誤或無來源說法（兩位一致 0、仲裁維持 1、仲裁未答 0；門檻 0）`（07:14:01 UTC）。
  該項（仲裁官 wrong）：文章說「七類」，實際「產業鏈」一節列了 8–10 類（結構改寫把章節重排後數量說法對不上）。
- 依指示不再開 cycle，**停在這裡**。沒有成片、沒有 540p 預覽。
- 🟢 A1 結構改寫路徑實跑驗證：事實鎖定真的擋下一次（正確拒收），第二次通過；代價是重排後產生的新句（含數量說法）在僅剩的 article R3 才被查到，沒有修補機會。🟡 建議：結構改寫後的 article 輪不應是 cycle 的最後一輪（給它一輪緩衝），或讓結構改寫通過後 article 輪次計數另算。
- 🟡 本頻道/題目：script_structure 兩輪皆因離開中位（20%、26%）與 writer_density 未過；文章是法規指針型題材，數字密度高、缺人物故事（與 chipcat run1/2 同型卡關：名詞表／數字表堆疊）。

## 最終數字（兩個 cycle 合計，`produce.py usage`／`timing`）
- 費用 **$7.03／$20**（評審 $3.23、產出 $3.80）：topic $1.92、article $2.56（20 次）、script_structure $2.55（18 次）；token：input 342／output 193,123／cache_read 3,759,119／cache_write 906,994。
- 牆鐘：總 45m55s；機器 30m02s（雲端 29m54s、本機 8s）；排隊 8m20s（deck 兩次 3m20s、4m00s，等 lanes.queue）；等人（runner 停下）7m26s。
- 各階段輪數：topic 1；article cycle-1 3 輪（R1 2 項、R2 3 項、R3 1 項＝仲裁誤計）＋cycle-2 3 輪（R1 未過、R2 過、結構改寫後 R3 未過）；deck 1 次初稿＋script_structure 2 輪（皆未過；R2 退回 article）。
- 沿用／quick path／退回點名比例：deck 改稿 1 次（23 句改寫、刪 3 句）；其餘無統計。🔴
- 30／45 分行：06:58 約 30 分（deck 初稿中，$≈3.6）；07:13 約 45 分（article 結構改寫後 R3，$≈7.0）。60 分未到。
- 本機重步驟（voice／media／assembly）**沒跑到**；啟動前 `memory_pressure` 75–76% free（`pgrep` 第二次被權限擋掉，未能確認）。

## 停下點（第一次，原文）
`gate_article: article: 第 3 輪（最後一輪）未通過：確認 1 個錯誤或無來源說法（兩位一致 0、仲裁維持 0、仲裁未答 1；門檻 0）`（06:44:05 UTC）。
該項：fact_checker-1#24「指針例子：為了籌出助手（同為自由工作者）的報酬，把原本委託的自由工作者報酬調低」判 unsourced；
仲裁官 `fact_arbiter-1` 判 **ok**（引原文「助手（フリーランス）」），但 ruling 的 `item` 寫成 `fact_checker-1#24：指針的例子裡有…`，
與 dispute key `fact_checker-1#24` 不完全相等，`arbitration.upheld` 以字串全等比對 → 算成「仲裁未答」→ 依規則計為確認錯誤。

## 修正（分支 `worktree-cf-cel-run1`，base 41d462d）
1. `74196ee` article 只准刪改守門兩處：
   - `split_article` 把句後的 `[src:…]` 切成獨立「句子」，刪掉被點名的句子連同它的引用就算「動了沒被點名的句」（p12.4）；現在 `[src:]` 與其句同一單位。
   - fix 的 problem／fix 文字裡用『』「」引的位置（例：開頭「一份只針對動畫」）也算被點名（原本只用 evidence，agent 照修改清單改開頭卻被拒收，p5.1）。
   - 兩者在 round 1 的 rework 造成連續 2 次拒收、runner 停下；修後 round 2 起正常。測試 `test_review_article_cite_split.py` 3 項。
2. `4be4e21` `arbitration.upheld` 以 dispute key（`name#n`）比對仲裁 ruling，不再要求 `item` 字串全等（仲裁官常整行照抄）。測試 `test_review_arbiter_item_key.py` 2 項。
- 測試：review／article／arbit 相關 247 passed（沒有跑全套）。只動 `article_diff.py`、`panel_flow.py`、`arbitration.py`；開工前 `git log` 看另兩條相關分支，近 3 小時無人改這三個檔。

## 數字
- 費用（名目，`produce.py usage`）：$3.64（評審 $1.45、產出 $2.19）；token：input 180／output 71,814／cache_read 1,762,708／cache_write 428,368。topic $1.92、article $1.72（16 次呼叫）。
- 牆鐘（`produce.py timing`）：總 15m59s；機器 13m06s（雲端 13m06s／本機 0）；排隊 0；等人 0；runner 停下 2m50s。最大塊：topic 產出 4m55s、article 評審 ×3 共 4m07s、article 改稿 ×5 共 2m03s。
- 各階段輪數：topic 1 輪過；article 3 輪皆未過（R1 2 項、R2 3 項、R3 1 項）；之後未到。
- article 輪次細節：R1 另有 writer_story 的 6 項故事建議，依規則 deferred 到 script 階段（`article.story_notes.json`）；R2 剩「約十分之一」「著作權讓渡 1成／3成」等事實項；R3 見上。
- 沿用比例／quick path／退回點名比例：未走到多輪 script 評審，無資料。🔴
- 30／45／60／90 分行：全程 16 分，皆未到。監督 session 未對我送訊息。
- 本機重步驟前閘門：啟動前 `memory_pressure` 76% free、`pgrep` 無重程序；未進入本機步驟。

## 本頻道特有的觀察
- 日文一手來源（公平會指針）＋繁中查核：查核員對譯述（如「同為自由工作者」括號、「製作開始後」vs 原文「製作開始前夕」）很敏感，翻譯用詞是反覆出現的事實項來源；建議 article 產出時對日文原文做更貼近的直譯，或把括號補充移出引號。🟡
- 選題風險篩選（chipcat run2 的 A2）對本題有效：來源全為政府文件，沒有傳聞型。🟢
- 頻道 audio 未啟用，本部未走到 final，無資料。

## 副作用／清理
- `output/cel-run1/`（gitignore）保留供檢視；背景 task output 位於 /tmp（系統清）。無其他暫存。沒上傳、沒開瀏覽器、沒 push、沒付費服務。

## 進度紀錄（append）
- 06:27 UTC 啟動（76% free、無重程序）；06:33 topic 過；06:35 article R1 未過；06:36 rework 2 次被守門拒收，runner 停（修正 1）。
- 06:38 續跑；06:41 R2 未過；06:44 R3 exhausted，停（$3.64）。隨後找到修正 2，重跑一次只重放既有結果。
- （06:44 當時建議）修正 2 已 commit；是否允許重算 round 3 由 orchestrator 決定。
- 06:58 orchestrator 指示 new-cycle（reason 如上）續跑；06:59 啟動，`memory_pressure` 75% free。
- 07:01 cycle-2 article R1 未過→改稿；07:03 R2 過；07:06 deck-1 初稿完（deck 兩次排隊 3m20s／4m00s，lanes.queue）；
  07:08 script_structure R1 未過（離開中位 20%、writer_density 5.5）；07:10 R2 未過（26%、writer_story 6、writer_density 6）→ 退回 article。
- 07:12 結構改寫第 1 次被事實鎖定拒收、第 2 次通過；07:14 article R3 未過（「七類」數量說法 1 項，仲裁維持），**停**（$7.03、45m55s）。依 orchestrator「再 3 輪不過就停」，不再開 cycle。
- 07:2x 監督 session（d6f8dc96）診斷同意：不繞評審、不手改 scorecard／credits，停在這裡交 orchestrator／Leon 決定。

## 根因與建議（流程缺口，交 orchestrator／Leon 決定）
1. **下游退回不重置 article 輪數（根因）**：cycle-2 的 article R2 已 pass，但 script_structure 退回 article 做結構改寫時，rewrite 後的 article 輪沿用 cycle 輪數，直接落在最後一輪（R3/3），沒有重試空間。結構改寫會引入大量新句，本來就最需要第二次機會。建議：結構改寫後的 article 輪另算（新的 3 輪預算，或至少 +1 輪緩衝）；`new-cycle` 規則的「同一份內容不得多跑輪次」不該套在「內容已被結構改寫」之後。（我沒有改程式——這是改輪次政策，不是程式錯。）
2. **規則缺口：結構改寫 prompt 沒要求「清單數量詞與實際條目數一致」**：失敗的那一項是改寫把章節重排／增列後，文中「七類」（第 20、56 行）對不上實際 8–10 個小標。建議在 `ARTICLE_STRUCTURE_REWORK` brief 加一條：改寫後自查所有「N 類／N 項／N 個」等數量詞，須等於實際列出的條目數，或改寫成不含數字的說法；並可加一個 `check_article.py` 的簡單檢查（數量詞後接的粗體小標計數）。🟡 未實作。
3. 其他：script_structure 兩輪離開中位 20%→26% 仍遠低於 40%，題材（法規指針）本質缺人物故事；若要此頻道穩定過關，應在 topic／outline 階段要求至少一條人物或事件主線。🟡
