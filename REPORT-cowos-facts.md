# REPORT — CoWoS 上片版修事實（新評審流程第 3→6 步）

## TL;DR
（進行中，見進度紀錄）

## 進度紀錄（append）
- 2026-10-18 分支 `feat/cowos-facts` 從 `feat/review-panels` 5fd5225 開（worktree `cf-cowos-facts`）。
- 起點：`cf-incremental-render/output/cowos-inc` 以 APFS clone（`cp -c -R`）複製到 `output/cowos-final`。
- 起點的 deck／media／final 是舊流程的人工核可（`claude-incremental-render`、`claude-validation`），新 runner 看到「核可＋指紋相同」會直接跳過評審團。
  用 `produce.py reject --gate deck|media|final --by claude-cowos-facts` 撤銷（只撤不核；article 照任務保留不重跑）。
- 程式修正（不動門檻）：腳本產出 agent 的 brief（`review/producers.py` TASKS["deck"]）原本沒有事實規則（文章 brief 有），
  補上：歸屬與限定詞、過時數字用最新狀態、無來源→補可靠來源進 sources.json 或刪改、推論要標明。
- 啟動：`produce.py run --run-dir output/cowos-final --auto-agents --no-stock --competitors <cf-review-panels>/output/eval-competitors/chipcat`
  （競品縮圖與 cf-review-panels 同一批，只讀）。
