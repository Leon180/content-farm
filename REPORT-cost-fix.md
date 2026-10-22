# REPORT — 修正 pipeline 的浪費（feat/cost-fix）

分支 `feat/cost-fix`，從 `feat/yokai-tempo` 開（含 economy 模式與 10-18～19 的全部評審修正）。沒有 push、沒開瀏覽器、沒上傳、沒用付費 API。

## TL;DR
（收工時填）

## 範圍決定（實作前寫明，Leon 2026-10-22「除了 plan 階段外都用 sonnet」）
- **plan 階段＝選題產出 agent（`topic`：決定這支片講什麼）**。這是我採用的最窄解讀，只有它可以用 opus。
- 文章、**deck 產出 agent（含 deck-outline 的分段結構）**、標題縮圖、素材、成片，以及所有評審席次（含選題評審團的席次）一律 sonnet。
  理由：`deck` 是一次呼叫同時寫大綱與講稿，無法在不增加一次呼叫的前提下拆開；Leon 的原話把「腳本撰寫」列在 sonnet。
  若要把「大綱／結構規劃」也算 plan，做法是把 deck 拆成 outline（opus）＋script（sonnet）兩次呼叫——**未做，需要 Leon 決定**。
  程式裡只有一個常數 `PLAN_PRODUCER_STEPS = ("topic",)`，改它就改範圍。
- effort：預設 low；事實查核與仲裁 medium；plan 產出 agent medium（plan 是唯一用 opus 的地方，不再疊 high）。
- 觀眾離開中位門檻用 sonnet 尺度 0.40（原 0.5；之前 economy 的 ×0.8），由 cf-pipeline-speed 之後校正。

## 基線（舊設定，九尾狐 `output/yokai-kyubi-v2`，`scripts/review_cost_report.py` 從評分卡與 producers.jsonl 算出，🟢）
| 階段 | 輪數 | 席次 | 名目 $ | 牆鐘 s | 新輸入 token／席（中位） |
|---|---|---|---|---|---|
| script（舊單段，已被兩段取代） | 3 | 25 | 9.08 | 1013 | ~24k |
| script_structure（含舊循環） | 8 | 51 | 18.52 | 2049 | 26k |
| script_facts | 7 | 19 | 11.80 | 2027 | 46k |
| title_thumb | 8 | 56 | 7.68 | 788 | 22.6k |
| media | 6 | 6 | 1.09 | 213 | 31.9k |
| final | 1 | 7 | 3.19 | 194 | 84.7k |
| **評審合計** | 33 | 164 | **50.36** | 6284 | |
| 產出 deck（16 次） | | | **31.40** | 6794 | cache_read 4,198 萬 |
| 產出 thumbnail_spec（6 次） | | | 2.06 | 543 | |
| **評審＋產出合計** | | | **≈ $83.8** | | |

- opus·high 占評審 $27.6（55%），而只占席次 ~25%。
- deck 產出 agent 16 次（平均 $1.96、424 s）：多為整份重寫；cache_read 4,198 萬 token 是長對話重讀。
- 同一個階段內「新輸入 token／席」中位 22–46k：觀眾拿到 sources.json、article.md、contact_sheet 等用不到的檔。

## 進度紀錄（append）
- 2026-10-22 開分支 `feat/cost-fix`（從 `feat/yokai-tempo` 6ea…最新），寫 `scripts/review_cost_report.py`，量基線。
