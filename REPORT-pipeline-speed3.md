# REPORT — pipeline-speed3（2026-10-23）

分支 `worktree-cf-pipeline-speed3`（從 `worktree-cf-pipeline-speed2` c9054e8 起，2 個 commit）。未 push、未開瀏覽器、未上傳、未跑真實影片。

## TL;DR
- **三項都做完並 commit：** (1) 拆 render 鎖＋CPU 核數預算＋雲端步驟只看記憶體；(2) 所有非事實關「評一次只記分數」，分數進 `review/score_ledger.json`（views／留存／CTR 欄位留空待填）；(3) `fact_on_fail: auto_fix_then_pass`（預設）＝事實／授權查一次、自動修一次、不重查、往下走，錯誤與修法進 `review/auto_fix.jsonl`；`stop` 可切回。
- pytest 全套 **1805 passed**（`--deselect test_multi_provider`，既有失敗）。
- 估算（🟡）：今天兩支片（九尾狐 v3、cel run2）排隊合計 7256 s，其中「render 鎖造成的 mix／assembly 排隊」1403 s、「雲端步驟被 swap／load 規則擋」2465 s，**上限約 3868 s（53%）可回收**；GPU 互斥的 2645 s 不變。
- 要 Leon／orchestrator 知道：評分關現在不擋任何東西，品質關卡實質關閉，是 Leon 的明示決定；看反應靠 `score_ledger.json`。

## 1. 拆鎖
**改了什麼**（`lanes/resources.py`、`lanes/queue.py`、`channels/shared/heavy_work.json`）
- `heavy_work.json`：illustrate／ai_motion／bgm／media／assembly／mascot／mix／cut／news_render 全部拿掉 `locks: ["render"]`。`heavy_default` 與 `queue.EXCLUSIVE`（沒登記的呼叫者，如 `scripts/ai_motion.py`）維持保守的 render 鎖。死設定 `min_free_pct: 50` 刪除（src／scripts 沒有任何讀取者）。
- `queue._lock_plan`：GPU exclusive 不再**隱含**拿 render 鎖，只有明列的才拿。GPU 類只靠 `heavy.lock`（exclusive／shared）互斥，voice 另有 `local_tts`。
- `Need.local` 加入「cpu_cores ≥ 2 的 CPU 渲染」（assembly 6、mix 2、cut 4、slides 2 → 屬本機車道：要查 swap／load 與非佇列的重程序，也設 `CF_HEAVY_SLOT` 讓子程序不重排）。`Need.light`＝非 local＝雲端步驟。
- `decide`：新增 `_cpu_budget`——已在跑且 ≥1 核的 job 核數＋自己 > 機器核數 → 等；機器閒置時一律放行一個。`_machine` 對 `light` 只看記憶體（`free ≥ mem + margin_gb`，含剛起跑 job 的承諾量），**不看 swap %、load、memory pressure**。
- 「只有真的搶同一輸出檔的才互鎖」：目前沒有任何步驟跨片寫同一個檔（每片有自己的 run 目錄），所以沒有步驟需要 render 鎖；`render` 鎖名保留，要鎖的步驟明列即可。

**取捨（請留意）**
- 舊分支（沒有 queue）用的 `render.lock`：GPU 步驟不再拿它，所以舊程式持有 render 鎖時，新分支的 illustrate 不會被擋。與其他仍在舊 `runner.render_lock` 的分支同時跑時要自己留意（合併後全部走 queue 就沒這問題）。
- 雲端步驟不看 memory pressure critical：照派工「只看 margin_gb」。真的記憶體吃緊時 free 會先掉到 margin 以下而等待。

**測試**：`tests/unit/test_lanes_overlap.py`（7 項）——沒有任何步驟共用 render 鎖；exclusive 不隱含 render；A 在 illustrate（running）時 B 的 assembly 可開、B 的 mix 不因鎖而等、C 的雲端評審照跑；兩個 GPU job 仍互斥；CPU 預算在 8 核機器上擋下 assembly(6)＋cut(4)、閒置時放行；雲端步驟無視 swap 97%／load 40／critical 但記憶體不足仍等；CPU 渲染仍看 swap。`test_lanes_queue.py` 一處更新（原斷言「GPU exclusive 帶 render 鎖」，改成明列 render 的 Need）。

**拆鎖前後估算**（🟡：來源 `timing.events.jsonl` 的 `queue` 事件加總，我只能用「步驟名」歸類原因，沒有每筆的等待原因欄位）

| | 九尾狐 v3 | cel run2 | 合計 |
|---|---|---|---|
| 排隊總計 | 4270 s | 2986 s | 7256 s |
| mix＋assembly（原本 render 鎖，拆鎖後不再等鎖，只受核數／記憶體預算） | 1163 | 240 | **1403** |
| 雲端步驟（deck／article／policy／gate_*／thumbnail_spec…；原本會被 swap／load 擋） | 1182 | 1283 | **2465** |
| GPU 互斥（illustrate／media／mascot／voice；不變） | 1824 | 821 | 2645 |
| 其他（slides／qc／thumbnail*，CPU 預算＋swap 仍管） | 100 | 641 | 741 |

- **上限回收 ≈ 3868 s（53%）**。這是上限不是預期：雲端步驟那 2465 s 有多少是 swap／load 規則、多少是真的記憶體不足，現有事件看不出來。
- 具體案例：九尾狐 v3 的 mix 在 10:09 才起跑（排了 962 s），時間窗正好是 cel 的 illustrate（10:01 起）持有 render 鎖——這一筆拆鎖後兩者可同時（illustrate 2 核＋mix 2 核）。cel 的 assembly 排 240 s 同理。
- 牆鐘（🟡）：九尾狐 v3 最後一輪原本約 50 分（機器實做約 14 分；illustrate 空等已由前一支 worker 的「沒事不排隊」去掉）；再扣掉可回收的 mix 962＋gate_media 220＋gate_deck_facts 160 ≈ 22 分，剩約 28 分（下限是配音 7:13＋media 5:01＋producer agent）。**這是離線估算，沒有跑真實 run。**
- 建議下次真跑時，把等待原因寫進 `queue` 事件（`reason` 欄位現成在票據裡，只是沒進 timing）才能把「上限」變成實測。

## 2. 只記分數
**改了什麼**（`review/config.py`、`review/score_ledger.py`（新）、`review/gate.py`、`review_panels.yaml`）
- `review_panels.yaml` 新增 `review.policy: {score_only: true, fact_on_fail: auto_fix_then_pass}`。
- `load_review` 套用 policy（`_apply_policy`，channel 覆寫合併後再套一次）：非事實關 `max_rounds=1`＋`waive_on_last_round=true`＝評一次，沒過也不退回、不改稿，記成放行（既有的 waiver 機制）；`topic_min_score` 取消，選題仍依分數排序取最高。門檻值保留，用來在評分卡標出「若有門檻會不會過」。
- `review/score_ledger.json`（每次 `write_decision` 更新）：每關 `scores`、`passed_thresholds`、`waived`、`unmet`、`comments`，頂層 `after_upload: {views, retention, ctr}` 全為 null，上片後人工填；後續寫入會保留已填的值。
- 逃生口：`load_review(policy=Policy(...))` 參數，或 `CF_REVIEW_POLICY=legacy` 環境變數（照 yaml 原本的輪數／門檻，供前後對照；測試 conftest 預設設成 legacy，所以舊的輪次測試不用動）。

**每片省多少（🟡 估算）**：先前報告的 timing 加總——九尾狐 v3 的 rework 欄 1 h 51 m（deck producer rework 1 h 42 m ×16）以及 script_structure／final 的重複輪次，在只評一次後不再發生；費用同比例下降（未重算名目費用，需實跑的 usage 才準）。

**測試**：`tests/unit/test_review_policy.py`（8 項）——yaml 預設值與各關 max_rounds／waive、失敗分數記錄後放行且沒有 fixes 檔、ledger 保留手填的 after_upload、真實 yaml 對 4 個頻道載入。

## 3. 事實／授權自動修
**行為**（`fact_on_fail: auto_fix_then_pass`，作用於 `article`、`script_facts`、`media`）
1. 第 1 輪照常查（兩位查核＋仲裁）。通過 → 照常。
2. 未過 → `gate._auto_fix`：產生一般的修改清單（`fixes.json` 加 `auto_fact_fix: true`），退回對應步驟；既有的 delete-or-edit-only 守衛（`DELETE_ONLY_FROM_ROUND`）仍擋「新增句子」，所以只會刪或改寫；media 的授權問題照既有路由換素材（`rework_assets`、credits 缺口改回 deck）。
3. 產出改完（內容指紋變了，或沒改）→ 下一次 `panel_gate` 直接 `_waive` 放行，**不開新輪、不叫任何評審**；`delta_gate`（核可後改句的差異查核）在此模式下也直接沿用核可。
4. 記錄：`review/auto_fix.jsonl` 兩行——`fix_issued`（錯誤原文、fixes 檔路徑、退回步驟）與 `passed_without_recheck`（`content_changed` 真假）；`<gate>.decision.json` 的 `waived.reasons` 帶未過項目；ledger 標 `waived: true`。
5. `stop`：fact 階段 `waive_on_last_round=false`、輪數照 yaml（3），沒過就 `exhausted` 硬停（= 326d03fe2fb7 的舊行為），不寫 auto_fix 記錄。

**限制 🟡**：「修法是否真的只刪改」由既有守衛保證；「改完是否真的正確」依決策不重查，所以 auto_fix.jsonl 是事後稽核的唯一線索。media 的 `fix_issued` 只代表換素材已排入，實際換了哪張在 `media` 步驟的紀錄。

**測試**：同上檔案——錯誤→退回標旗標→改完 pass 且沒有任何新評審呼叫；改了沒變也 pass 並標 `content_changed: false`；查核乾淨不產生記錄；`stop` 三輪後 `exhausted`。

## 4. 怎麼合併到片分支
- 本分支基於 speed2（c9054e8），只動：`lanes/{resources,queue}.py`、`channels/shared/{heavy_work.json,review_panels.yaml}`、`review/{config,gate,delta,score_ledger}.py`、`tests/conftest.py` 與四個測試檔。
- 對片分支：`git merge worktree-cf-pipeline-speed3`（含 speed2 的兩個 commit）或 `git cherry-pick 3010a88 9d3fcfa`（需先有 speed2）。
- 衝突點：`review_panels.yaml`（若片分支也改了 `review:` 開頭）、`heavy_work.json` 的 steps 行。合併後跑 `pytest tests`（`CF_REVIEW_POLICY` 由 conftest 設定，不用另設）。
- 進行中的 run 不受影響，下次 `produce.py run` 才讀新設定；已有的 `*.fixes.json` 與 round-N 目錄原樣沿用。

## 5. 副作用與清理
- 無暫存檔留在 repo；暫存腳本在 `~/.claude/jobs/1f2953bd/tmp/`（job 目錄，隨 job 清）。`graft/` 索引資料夾未加入 git。無背景程序。
- 不改其他 worker 的 worktree 與 output。

## 進度紀錄
- 2026-10-23：1、2、3 完成並 commit；全套 pytest 通過；報告已寫。對話遠低於 30 萬 token。
