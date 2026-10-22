# REPORT — chipcat run2（夜間循環第 3 部）

## TL;DR
- 🟢 A 三項修好並附測試（結構退回走 `rewrite_reason`＋事實鎖定、選題來源風險扣分、`new-cycle --reason` 必填）。
- 🔴 B **沒有跑到 gate_final**：停在 `gate_deck`（script_structure）第 3 輪（最後一輪）未過——觀眾離開中位 36% < 40%、writer_story 6/10 < 6.5。
  累計 $6.56／$20，機器牆鐘 18m05s（目標 ≤60 分，未逼近）。沒有成片、沒有 540p 預覽。
- 新題（評審團重挑）：「0.7 奈米是真的嗎：晶片製程的名字為什麼不是尺寸」（IBM 新聞稿類來源，非價格傳聞型）。article 2 輪過（0 錯）。
- 這次 script_structure 三輪都是退回 **deck**（不是 article），A1 的結構退回路徑**沒被實跑驗證**（只有單元測試）🟡。

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
- 起 21:46:51 UTC（2026-10-22）；停 22:04 UTC。指令：`produce.py run --channel chipcat --run-dir output/chipcat-run2 --auto-agents --no-stock --budget-usd 20`（含 env-file 參數）。
- 費用（名目，`produce.py usage`）：**$6.56**（評審 $3.38、產出 $3.18）；token：input 308／output 187,616／cache_read 3,605,508／cache_write 829,295。
  topic $1.72、article $1.13、script_structure $3.71（29 次呼叫）。
- 牆鐘（`produce.py timing`）：總 18m05s；機器 18m01s（雲端 17m54s、本機 8s）；排隊 0；等人 0。最大塊：topic 產出 3m48s、deck 初稿 3m16s、
  script_structure 評審 ×3 共 2m48s、deck 改稿 ×3 共 2m37s。本機重步驟（voice／media／assembly）沒跑到；`memory_pressure` 83% free、`pgrep` 無重程序（啟動前查）。
- 各階段輪數：topic 1 輪過；article 2 輪（第 1 輪 2 個事實項，「只准刪改」改稿 19 秒後第 2 輪過）；script_structure 3 輪皆未過
  （deck 初稿 1＋改稿 3 次，其中 1 次被 touch guard 拒收、第 2 次過）；之後階段未到。
- script_structure 各輪：R1 離開中位 28%、writer_story 5.5、writer_density 6.3；R2 36%、writer_story 5.5；R3 36%、writer_story 6.0。逐輪進步但差門檻（40%／6.5）一點。
- 沿用比例／quick path／退回點名比例：沒有統計（原始資料在 `output/chipcat-run2/review/`，gitignore）。🔴
- 30／45／60／90 分行：全程 18 分，皆未到。監督 session 未對我送任何訊息。
- 成片、預覽（`artifacts/chipcat-run2/`）：**無**。沒上傳、沒開瀏覽器、沒 push。

## 卡關與停下點
- 停下點：`gate_deck` script_structure R3：`觀眾離開中位 36% < 40%；writer_story-1 6/10 < 6.5`；production.log 最後 `[failed]`。
- 沒有用 `new-cycle` 續跑：同一份內容不得多跑輪次（A3 規則）；開了也只是再燒 ~$3.7，沒有修任何流程缺口。
- 現象：writer_story 一直 5.5–6、離開中位卡 36%——文章／講稿的故事張力問題；本輪由 deck 自己改。
  建議（🟡 未驗）：離開中位長期卡在門檻邊緣時，讓 script_structure 退回 article（A1 路徑），或在 outline 階段先設計留人點。
- 測試環境：`test_multi_provider` 1 項失敗，在 run1 tip 同樣失敗，與本部無關。

## 副作用 / 清理
- `output/chipcat-run2/`（gitignore）保留供檢視；`/Users/lileon/.claude/jobs/3fa54f05/tmp/patch_a1.py` 為暫存（job 刪除時一併清）。無其他暫存。

## 進度紀錄（append）
- 21:46 UTC（2026-10-22）A 三項完成並 commit（本機時間 10-23 05:46）；memory 83% free、無重程序。
- 21:47 UTC 啟動 `produce.py run`（背景）。
- 21:55 article 第 2 輪通過；21:59 script_structure R1 未過；22:01 R2 未過；22:04 R3 未過，停（$6.56）。
