# REPORT — chipcat run2（夜間循環第 3 部）

## TL;DR
（進行中；收工時改寫）

## A. 先修（分支 `worktree-cf-chipcat-run2`，base 9b30efd）
1. **結構性退回 vs article「只准刪改」**
   - 實際成因（讀 log 後修正 run1 的歸因）：script_structure 退回 article 時 gate=`deck`，article-4 那次**沒有任何守門**，整篇重寫、
     產生一堆沒查核的新句；之後 `gate_article` 第 2 輪起套「只准刪改」，agent 為了改新句的「成本／價格」用詞連帶動到沒被點名的句子
     （p16/p26/p33）被拒收、又被「改寫幅度太大」拒收，用掉 article 3 輪。
   - 修法（照任務選「走 `rewrite_reason` 路徑」，沒有移到 topic／outline）：非 article 閘門送回 article 的改稿 = 結構改寫
     （`panel_flow._StructuralArticle`）：可重構、`rewrite_reason` 必填、brief 改用 `ARTICLE_STRUCTURE_REWORK`；
     **事實鎖定**：與最近一次 article 核可版（`review/article.approved.md`）比對，配得上的舊句（相似度 ≥0.5，搬動／改寫都算）
     數字與 `[src:…]` 來源 id 不准變（也不准漏），違反就拒收還原重做（2 次）。
   - 差異查核：通過後寫 `review/article.locked.md`（基準）＋`article.rewrite.json`；下一輪 article 的事實查核員只看標 ★ 的新句
     （`materials.article`），且新句在後續「只准刪改」輪次裡視為可改（`changed_since_lock`）；article 再核可後兩個檔刪除。
   - 理由：結構問題需要重構，無法在「只准刪改」下解；而事實安全靠「舊句數字／來源鎖定＋新句逐句查」守住。
   - 測試：`tests/unit/test_review_structural_article.py` 10 項。
2. **選題篩選**：topic 的 `pro`、`producer` 評審任務加 `SOURCE_RISK`（傳聞為主／報價互相矛盾／主要數字無一手來源 → 分數 ≤4，三項全中 veto）；
   選題 producer agent 的 brief 也要求至少 1 個一手來源、避開此型。測試：`tests/unit/test_review_topic_source_risk.py` 4 項。
3. **`new-cycle --reason`**：必填（≥12 字），不足即拒絕且不搬動任何檔；寫進 `production.log.jsonl` 與 `review/new_cycle.jsonl`。
   規則寫在 help 與 docstring：只用於 clone／舊 run 留下的輪次，或流程缺口修好後重跑；不是在同一份內容上多跑幾輪。
   測試：`test_review_no_mix.py` 增 1 項、舊測試補 reason。本部 B **沒有使用** new-cycle。
- 全套測試：1723 passed／1 skipped／1 failed——失敗的是 `tests/unit/test_multi_provider.py::test_returns_first_provider_results`，
  **在 run1 tip（9b30efd）上同樣失敗**（我沒碰 multi_provider），與本部無關；run1 報告寫 1702 passed，疑似環境差異（🟡 未查）。

## B. 新片（`output/chipcat-run2`）
（進行中）

## 進度紀錄（append）
- 21:46 UTC（2026-10-22）A 三項完成並 commit（本機時間 10-23 05:46）；memory 83% free、無重程序。
- 21:47 UTC 啟動 `produce.py run`（背景）。
