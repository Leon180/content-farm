# REPORT — CoWoS 上片版修事實（新評審流程第 3→6 步）

## TL;DR
- **目前（交接時）**：依 Leon 7afa95870a4e＝A 改用腳本兩段（commit 06772a1）重跑；結構段第 1、2 輪未過（離開 32.9%／29.8%、密度編劇 6.3／6.4，
  故事編劇已 7.0），runner 正在背景做退回 2 → 結構段第 3 輪（最後）。接手方法見「CoWoS 用兩段規則重跑」。下面是舊單段腳本評審的結果：
- **舊單段腳本評審停在第 3 步**：腳本評審團 3 輪用完仍未過，依任務規則停下、門檻沒動。最後一輪：觀眾離開中位 42.4%（< 50%，holdout 老師 73.6%）、
  編劇故事 6.9／密度 6.3（< 7）、查核 **4 錯**（第 1 輪 8 → 第 2 輪 2 → 第 3 輪 4；4 條裡 2 條是第 3 輪改寫新寫的句子，
  另 2 條第 2 輪稿就有、第 2 輪查核沒抓到＝查核變異）。
- 第 1 輪點名的 8 條事實錯誤**全部修掉**（摩根士丹利→經濟日報、2016 推論改回台積電簡報原話、3.3／5.5／9 改成 2026 最新狀態並標時間、扛錯句刪除、
  翹曲／SemiAnalysis 刪除、S／L 版補 EDN Asia 來源、韓媒 vs 鏡報分開、CoWoS 產能基準）；但第 4–6 步、release.mp4、manual-kit、縮圖**都沒有重產**。
- 程式（`feat/cowos-facts`，未 push）：腳本 brief 加事實規則；`production.frozen.json`（凍結文章：問題改派給腳本、不重做／不重驗、閘門沿用核可）；
  **Leon 59fdefb32bd7＝D 文章查核新規則**（3 輪、第 2 輪起只准刪改＋逐句 diff、opus·high 仲裁）。pytest 1480 passed（僅既有 `test_multi_provider` 失敗）。
- 要 Leon 決定：腳本第 4 輪（目前硬上限 3）或把剩下 4 條事實＋結構問題交人改，之後再從第 3 步重跑。

## 腳本拆兩段（Leon 決策 7afa95870a4e＝A；commit 06772a1）🟢 單元測試
| 規則 | 實作 | 測試（`tests/unit/test_review_script_stages.py` 等） |
|---|---|---|
| 結構段 `script_structure`（gate `deck`） | 觀眾 5（含 holdout 最後一輪）、編劇故事／密度、導演、查核 1；門檻離開中位 ≥50%、編劇 ≥7；3 輪；查核結果記在 `fact_errors_advisory`、事實項以 `advisory: true` 進修改清單，**不擋** | 結構段事實錯不擋、不過時只因觀眾／編劇 |
| 事實段 `script_facts`（新 gate `deck_facts`、步驟 `gate_deck_facts` 在 gate_deck 之後） | 查核 opus·high ×2＋仲裁（同文章規則，以旁白句子 id＋evidence 配對）、0 確認錯誤、3 輪 | 結構段沒過時事實段不跑；兩段都過；一致的錯誤→退回 deck 且 note 指向 `deck_facts.fixes.json` |
| 事實段只准刪改 | 退回改稿以旁白句子（穩定 id）逐句 diff，被點名＝事實項的 ref＋連動範圍句子 id；違反就還原、重做 1 次、再違反就停；brief 加「結構已核可，不改章節、順序、比喻、笑點」 | 新增句被拒、改未點名句被拒並還原、結構段的退回不受限 |
| 事實鎖定 | 兩段任一核可時存 `review/deck.locked.json`；之後 deck 變動若只刪改旁白→結構段沿用核可（只重跑事實段）；新增句子（或改寫幅度 <0.5）→結構段核可失效，兩段舊輪次移到 `cycle-N/`、從第 1 輪重走 | 鎖定後加限定詞只重審事實段；鎖定後新寫一句→兩段重走、舊輪次在 cycle-1 |
- 硬規則（`review/config.py`）：兩段都在 `REQUIRED_ROLES`／`TIER_FLOOR`／`THRESHOLD_FLOOR`／`MAX_ROUNDS`（各 3），事實段必須剛好 2 位查核＋≥ opus·high 仲裁；yaml 只能更嚴。
- 🟡 我的解讀：(1)「重新走兩段」＝新一輪循環，輪數從 1 重算（舊輪次保留在 cycle-N/）；否則結構段 3 輪用完後永遠無法重走。
  (2) 只檢查旁白句子；投影片上的標題、條列、圖說改動不在逐句比對內（事實段查核員仍會讀整份講稿與總覽圖）。
- 全套 pytest 1491 passed／1 skipped，唯一失敗仍是既有的 `test_multi_provider`；`scripts/check.sh` 過。

## CoWoS 用兩段規則重跑（2026-10-18 22:4x 開始，用量已過 21:40 重置）
- 起點＝上一次第 3 輪後的 deck（第 1 輪 8 條已修、剩第 3 輪 4 條）；舊的單段 `review/script/` 三輪保留不動（不算新兩段的輪數）。
  舊的 `review/deck.fixes.json`（舊單段第 2 輪）改名 `deck.fixes.legacy-script.json`，避免新結構段第 2 輪誤用同輪號的舊清單。

| 結構段 | 離開中位（≥50%） | 編劇故事／密度（≥7） | 導演 | 查核（只列不擋） | 牆鐘／名目 |
|---|---|---|---|---|---|
| 第 1 輪 | 32.9%（23.3／42.4／61.5／19.9） | 7.0／**6.3** | 6.0 | 2 | 318.8 s／$3.08 |
| 改寫 1（產出 agent） | — | — | — | — | 970.3 s（27 張／7 章、估 9.9 分） |
| 第 2 輪 | 29.8%（17.9／41.8／17.9／43.3） | 7.0／**6.4** | 6.8 | 4 | 346.6 s／$2.95 |

- **交接點（Token 規則，對話約 30 萬 token）**：2026-10-18 約 23:3x，結構段第 2 輪未過、runner 已自動退回 deck（rework 2）並啟動腳本產出 agent；
  之後會自動跑結構段**第 3 輪（最後一輪，含 holdout）**。`produce.py run` 仍在背景跑（pid 85151，由本 session 的背景 shell 啟動；
  本 session 結束時可能一併被終止）。
- **接手的人**：
  1. `pgrep -fl "produce.py run"` 看 85151 還在不在；在就等它結束（看 `output/cowos-final/production.log.jsonl` 的最後幾行，不要輪詢）。
  2. 不在了（或結束了）：`env PYTHONPATH=<worktree>/src <venv python> scripts/produce.py status --run-dir output/cowos-final`；
     若 gate_deck 停在 rework／waiting 且第 3 輪還沒跑，重跑同一條 `produce.py run --run-dir output/cowos-final --auto-agents --no-stock --competitors <cf-review-panels>/output/eval-competitors/chipcat`
     （runner 會從斷點續：deck 產出 → policy → slides → 結構段第 3 輪）。
  3. 結構段第 3 輪沒過＝依任務第 4 點停在結構段回報；過了就自動進事實段（`gate_deck_facts`，最多 3 輪）→ 標題縮圖 → 素材合規 → 配音／渲染（本機車道，經全機佇列）→ 成片。
  4. 凍結檔 `output/cowos-final/production.frozen.json`（article、gate_article）要保留；gate_final 留給 Leon，不要人工核可任何閘門。
- 觀察 🟡：結構段兩輪都卡在同一處——觀眾在 k 章（3:30–5:30 的郵票／乘法段）與商業段離開、資訊密度編劇 6.3–6.4（重講與數字牆）；
  故事編劇已到 7.0。

## 卡在哪——舊的單段腳本評審（第 3 步腳本，`output/cowos-final/review/script/round-3/scorecard.json`）🟢
| 指標 | 門檻 | 第 1 輪 | 第 2 輪 | 第 3 輪（最後） |
|---|---|---|---|---|
| 觀眾離開中位 | ≥ 50% | 30.6% | 19.7% | **42.4%**（commuter 16.6、investor 42.4、student 42.4、engineer 100；holdout teacher 73.6） |
| 編劇（故事） | ≥ 7 | 6.4 | 6.3 | **6.9** |
| 編劇（密度） | ≥ 7 | 5.8 | 6.2 | **6.3** |
| 導演（不計門檻） | — | 6.0 | 6.8 | 6.6 |
| 事實查核（opus·high） | 0 | 8 | 2 | **4** |
| 評審牆鐘／名目費用 | — | 286.7 s／$2.99 | 281.5 s／$2.99 | 319.0 s／$3.06 |
| 送出意見／被剔除（對不上素材） | — | 89 條 | 41／16 | 57／6 |

剩下的事實問題（第 3 輪）：
- s02.5「缺口要再約 18 個月才補得上」(wrong)：來源說新增產能約一年半內開始上線，不是缺口補平。
- k6.1「5.5 張的 2026 年**才**在量產」(unsourced)：來源只說 2026-04 已在生產；3D InCites 給的時程是 2025–2026。
- s20.15「一期延到 2027 年量產、二期 2026 先量產」(wrong)：一期原排 2028（TrendForce 2024-06），來源只說一期延誤、二期提前。
- s25.4「這段時間大部分發生在台灣」(unsourced)：沒有台灣占比的來源，是推論寫成事實。

剩下的非事實問題（摘要，原文見 results/）：「62→8」講三次、「蓋廠時間」論點講六次（密度：無灌水重講 5.5）；承諾提到「良率爬坡」但全片沒有證據；
章節預告的年份順序跟實際播放不一致；k1「先猜」的答案已印在投影片上；k2/k6「全做 3.3 張」不是真的下界；3:32–5:30 的郵票／乘法段是 3 位觀眾離開處；
商業段（9:28 後）老師離開。片長從 8:31 變成估 10.0 分（第 2 次改寫加了內容）。
- 🟢 4 條的來歷（對照 `round-2/script.txt`）：s02.5、s25「大部分發生在台灣」（第 2 輪稿是 s25.3）**第 2 輪就在**、第 2 輪查核沒列；
  k6.1、s20.15 是第 3 輪改寫新加的。
- 🟡 觀察：第 1→2 輪修掉 6 條舊錯；第 2→3 輪為了回應編劇／觀眾意見改寫結構，新加 2 條錯，另有 2 條是查核員之間的變異——
  跟文章階段 rp1–rp4 的形狀一樣（改寫會帶進新錯、單一查核會漏）。
  文章階段的新規則（第 2 輪起只准刪改）就是針對這個；腳本階段沒有這條規則，Leon 可考慮是否比照。

## 每條事實修正前後（起點 `cowos-inc/deck.json` → 最後 `cowos-final/deck.json`）
| 第 1 輪問題 | 修正前 | 修正後 | 連動 |
|---|---|---|---|
| 26 萬片歸屬 (wrong) | s12.7「摩根士丹利估 2028 年底，每月 26 萬片。」 | s22.11「經濟日報報導，CoWoS 2028 年底可能到每月 26 萬片；」 | 只此一處 |
| 2016 推論寫成台積電的話 (wrong) | s24.2「2016 年台積電自己承認，量太小，沒人會提前蓋廠。」 | s07.13「據當年的會議報導，台積電 2016 年在簡報裡說：CoWoS 在雲端…有穩定需求，在手機市場還沒找到位置。」；「沒人提前蓋廠」改成頻道論點（密度編劇指出講了 3 次） | s07、s24 |
| 3.3／5.5／9 過時 (wrong) | k0.5「量產 3.3 張、承諾 5.5 張、規劃 9 張。」；s01.3「規劃中的九倍大小，只剩 5 個。」 | k0.12「據報導，台積電 2026 年說，5.5 張的已經在量產，2028 年要做到 14 張。」；k0.14「據 3D InCites 2024 年底的報導，當時已經做到 3.3 張。」；開場改 62→8（5.5 張） | 開場 s01、k0–k2、k6、結尾 s24、**片名與縮圖待第 4 步**（舊縮圖仍寫 62→5） |
| 客戶替工廠扛錯 (unsourced，方向相反) | s13.2「客戶替代工廠扛錯，很少見吧？」 | 刪除；s13.10「他說這百分之百是輝達的錯，是台積電幫他們從良率問題裡救回來。」 | s13 |
| 翹曲／SemiAnalysis (unsourced) | s13w.5「封裝裡的材料熱脹冷縮不一致…整片竟然翹了起來。」（投影片 REF SemiAnalysis） | 翹曲段刪除；s13.5「黃仁勳證實，是設計瑕疵讓良率偏低。」 | s13w 整張 |
| S／L 版結構 (unsourced) | s14.2「舊的 S 版，是一整片矽做的底板…」 | s14.14「據電子業媒體 EDN 報導，舊的 S 版，中介層是一整片矽…」；**sources.json 新增 `ednasia-2025-02`**（EDN Asia 2025-02-11），第 2、3 輪查核未再列為錯 | s14 |
| 輝達訂走「台積電全年產能」一半 (wrong) | s15.4「據報導，超過台積電全年產能的一半。」 | s15.8「…超過台積電 **CoWoS** 全年產能的一半。」、s03.9 同步 | s03、s15 |
| 韓媒 vs 鏡報 (wrong) | s17.6「據韓媒報導，竟然連前段也開始外包，日月光和矽品正在蓋前段產線；」 | s17.10「據韓媒報導，台積電擴大把前段外包給封測廠；」＋s17.13「另有媒體報導，日月光和矽品在 AMD 支持下…蓋自己的前段產線。」 | s17、k4 |
| 群創舊廠包 AI 晶片 (unsourced) | s19.4 | 第 2、3 輪未再列為錯 | s19 |
| 「親口說：」轉述當直接引語（評審意見） | s02.2「…台積電董事長親口說：」 | 「親口」全片移除 | s01、s02、s13 |
- 起點 s01 的 62→5（9 倍）改成 62→8（5.5 張）並標「晶片貓粗算」；**標題、縮圖 A、說明欄仍是舊說法**（第 4 步沒跑到）。

## 耗時（🟢 production.log.jsonl／scorecard）
| 項目 | 牆鐘 |
|---|---|
| 腳本評審第 1／2／3 輪 | 286.7／281.5／319.0 s |
| 腳本產出 agent 退回 1／2（opus·high） | 1011.0／1164.5 s |
| policy＋slides（每次） | 3–5 s |
| 合計（雲端車道，不含我停下修程式的時間） | ≈ 51 分 |
沒有進入本機車道（配音、media、合成都沒跑），所以「只重配改到的句子 ±2、只重畫改到的場景」**這次沒有實測**。
腳本兩次改寫都是大幅改寫（24→27 張、多數句子改），即使往下跑，增量渲染能省的也有限 🟡。

## 交件路徑（都**不是**修正版，不能上片）
- `output/cowos-final/assembly/release.mp4`：起點（cowos-inc）的舊成片，內容與現在的 deck.json 不一致。
- `output/cowos-final/thumbnails/variant_{a,b,c}.jpg`：舊縮圖（第 4 步沒跑）。manual-kit：沒有產生。gate_final：未到。
- 現在的講稿：`output/cowos-final/deck.json`、`script.json`；評分卡 HTML：`output/cowos-final/review/scorecard.html`；三輪結果 `review/script/round-{1,2,3}/`。

## 文章查核新規則（Leon 決策 59fdefb32bd7＝D；commit 2f3a07e）🟢 單元測試
| 規則 | 實作 | 測試（`tests/unit/test_review_article_rules.py`、`test_review_config.py`） |
|---|---|---|
| 文章 3 輪（其他不變） | `config.MAX_ROUNDS["article"]=3`、yaml `max_rounds: 3`；4 仍被拒 | `test_rounds_capped`、`test_third_round_is_the_last` |
| 第 2 輪起只准刪改 | `review/article_diff.py`：文章逐行逐句切（`p<段>.<句>`），被點名句＝修改清單裡事實項 evidence 原文對到的句子；difflib 以文字對齊前後版本：新增句（含一拆二）、改到沒被點名的句、被點名句改寫幅度過大（相似度 < 0.5）一律拒收。`panel_flow.run_producer`：改稿前存 `review/article.before-round-N.md`，違反就還原、把原因附進 brief 重做 1 次，仍違反就還原並停在 article（failed） | 新增句被拒、拆句被拒、加限定詞／改歸屬放行、刪被點名句放行、偷改未點名句被拒、改寫過大被拒、拒收→還原→重做通過、兩次都違反→停且文章是原版、初稿不受限 |
| 仲裁 | `review/arbitration.py`＋`rounds._arbitrate`：兩位查核的錯誤說法以 evidence 對到的文章句子配對；兩位都判錯＝直接算錯；只有一位判錯（另一位 ok／analysis 或沒列）＝爭議，交第 3 位（`stage.arbiter`，硬規則 ≥ opus·high、可 WebFetch，prompt 附雙方判定、理由與來源）；仲裁維持才算錯，**仲裁沒回答的爭議算錯**（保守）。門檻仍 0。只有確認的錯誤進修改清單。`gate.enforce` 驗仲裁席的 model／effort／實際回答模型 | 意見一致不仲裁、不一致仲裁、仲裁推翻→通過、仲裁維持→退回且清單只有那條、未答算錯、兩位都錯直接算、少了仲裁席或仲裁降級→enforce 拒絕、yaml 拿掉／降級 arbiter 或查核不是 2 位→載入失敗 |
- 🟡 我的解讀：「不一致」包含「另一位沒列出這條」（不只 ok／analysis），因為漏列等於沒判錯；evidence 對不到文章原文的錯誤說法不會被配對，一律送仲裁。
- 🟡 「第 2 輪起」解讀為：第 2、3 輪要審的稿（＝每一次退回重寫）都受限；第 1 輪前的初稿不受限。
- 腳本階段只有 1 位查核，不走仲裁；本支 CoWoS 不受影響（`ARBITRATED_STAGES=("article",)`）。全套 pytest 1480 passed／1 skipped，唯一失敗是既有的 `test_multi_provider`；`scripts/check.sh` 過。
- 沒有用真的 claude 跑過新文章規則（rp5 由 orchestrator 另派）。

## 進度紀錄（append）
- 2026-10-18 分支 `feat/cowos-facts` 從 `feat/review-panels` 5fd5225 開（worktree `cf-cowos-facts`）。
- 起點：`cf-incremental-render/output/cowos-inc` 以 APFS clone（`cp -c -R`）複製到 `output/cowos-final`。
- 起點的 deck／media／final 是舊流程的人工核可（`claude-incremental-render`、`claude-validation`），新 runner 看到「核可＋指紋相同」會直接跳過評審團。
  用 `produce.py reject --gate deck|media|final --by claude-cowos-facts` 撤銷（只撤不核；article 照任務保留不重跑）。
- 程式修正（不動門檻）：腳本產出 agent 的 brief（`review/producers.py` TASKS["deck"]）原本沒有事實規則（文章 brief 有），
  補上：歸屬與限定詞、過時數字用最新狀態、無來源→補可靠來源進 sources.json 或刪改、推論要標明。
- 啟動：`produce.py run --run-dir output/cowos-final --auto-agents --no-stock --competitors <cf-review-panels>/output/eval-competitors/chipcat`
  （競品縮圖與 cf-review-panels 同一批，只讀）。
- **腳本第 1 輪**（`review/script/round-1/scorecard.json`）🟢：未過。觀眾離開中位 30.6%（4 位：5.5／17.9／43.3／50.2%）、編劇故事 6.4、
  資訊密度 5.8、導演 6.0、查核 8 錯（42 條說法：ok 22、analysis 6、wrong 5、unsourced 3、unverifiable 2）。牆鐘 286.7 s、名目 $2.99。
  查核 8 條：s24.2「台積電承認…沒人會提前蓋廠」(wrong)、s13w.3/5 翹曲／SemiAnalysis (unsourced)、s14.2/4 S／L 版結構 (unsourced)、
  s15.2/4「超過台積電全年產能一半」應為 CoWoS 產能 (wrong)、s12.7 摩根士丹利→經濟日報 (wrong)、k0.5/k1.5/k1.6/k2.4 3.3／5.5／9 過時 (wrong)、
  s17.6 韓媒 vs 鏡報、擴大 vs 開始 (wrong)、s19.4 群創舊廠包 AI 晶片 (unsourced)。
- **事故（已處理）**：第 1 輪的修改清單有 2 條 `caused_by: article`（S／L 版結構、AP7 二期不是 CoWoS），routing 取最早的步驟 → `restart: article`，
  runner 接著啟動了文章產出 agent。我在看到事件後停掉 run；子程序隨即結束，`article.md`／`sources.json` 與起點逐位元相同（cmp／shasum 驗過），沒有被改。
  修正（程式，commit 96268f5）：`production.frozen.json`（每支 run 的凍結步驟）——凍結步驟造成的問題改派到下一個未凍結步驟（這裡是 deck），
  修改清單標 `rerouted_from`，brief 會告訴產出 agent「在這一步補 sources.json 或刪改」；runner 不重做凍結步驟（測試 4 條；全套 1462 passed，
  唯一失敗仍是既有的 `test_multi_provider`）。用 panel_gate＋「呼叫評審就 raise」的 stub 重做修改清單（沒有開新一輪）：89 條全部在 deck，2 條改派自 article。
- 腳本產出 agent（退回 1）：1011 s，27 張／8 章、估 9.0 分，`deck_to_script --strict` 過；sources.json 新增 1 筆 `ednasia-2025-02`
  （EDN Asia 2025-02-11，CoWoS-S／L 結構——對應第 1 輪 S／L 版 unsourced）。
- **腳本第 2 輪** 🟢：未過。離開中位 19.7%（93.7／21.2／14.0／18.1%，比第 1 輪差）、編劇故事 6.3、密度 6.2、導演 6.8、查核 **2 錯**
  （34 條：ok 27、analysis 4、unsourced 1、wrong 1、unverifiable 1）。281.5 s、$2.99。剩：s07.8「2016 輝達資料中心晶片用上 CoWoS」(unsourced，
  事實為真但 sources.json 無支持)、s22.2「載板材料 2027 才紓解」(wrong：來源是 T-glass 玻纖布、最快 2026 下半年)。
- 第 2 輪退回後，runner 跑了凍結文章的 verify（`check_article.py`：`[article] source 'ednasia-2025-02' is never cited`，exit 1）——
  sources.json 是文章步驟的輸出，腳本補來源讓它的指紋變了。修正（commit b3f2389）：凍結步驟不重做也不重驗，凍結閘門沿用先前核可、
  指紋變動寫進 log；凍結閘門沒有先前核可就停。run 的凍結清單改為 `article`＋`gate_article`。
- Leon 決策 59fdefb32bd7＝D（orchestrator 轉達，已對照 prompt 檔「追加」一節）：文章查核新規則實作，commit 2f3a07e（見上方「文章查核新規則」）。
- run 3：凍結生效（`❄ article`、`❄ gate_article 沿用 2026-10-16 核可`）→ 腳本產出 agent（退回 2）1164.5 s、27 張、估 10.0 分 →
  **腳本第 3 輪（最後一輪，含 holdout）未過** → runner 以 failed 停在 gate_deck（`exhausted`）。依任務第 4 點停下，沒有放寬門檻、沒有人工核可任何閘門。

## 副作用與清理
- `output/cowos-final/`（gitignore，未 commit；起點是 cowos-inc 的 APFS clone）：含 `production.frozen.json`、三輪評審、兩次產出 agent log、
  `review/deck.fixes.json`。`production.json` 的 deck／media／final 決策是我以 `produce.py reject --by claude-cowos-facts` 撤銷的（log 有紀錄）。
- 各 round 目錄裡 claude -p 子程序留下的 `graft/` 索引資料夾，可刪。worktree 根目錄 `graft/` 是開工前就有的。
- job tmp `~/.claude/jobs/7ce577a7/tmp/`（`replan.py`、`facts_before_after.py`）。沒有殘留的 `claude -p` 程序（pgrep 無結果）。
- 沒動 cf-incremental-render、cf-review-panels 的 run-dir（只讀；競品縮圖只讀）；沒 push、沒開瀏覽器、沒上傳、沒用付費 API（評審與產出全走 `claude -p` 訂閱）。
- `rm` 在 deny，以上可刪的留給 orchestrator。
