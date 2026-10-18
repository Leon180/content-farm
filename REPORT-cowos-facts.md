# REPORT — CoWoS 上片版修事實（新評審流程第 3→6 步）

## TL;DR
（進行中，見進度紀錄）

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
- Leon 決策 59fdefb32bd7＝D（orchestrator 轉達，已對照 prompt 檔「追加」一節）：文章查核新規則實作，commit 2f3a07e（見下方「文章查核新規則」）。
