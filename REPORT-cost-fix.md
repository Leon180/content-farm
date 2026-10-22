# REPORT — 修正 pipeline 的浪費（feat/cost-fix）

分支 `feat/cost-fix`，從 `feat/yokai-tempo` 開（含 economy 模式與 10-18～19 的全部評審修正）。沒有 push、沒開瀏覽器、沒上傳、沒用付費 API。

## TL;DR
🟡 **程式七項都做完並有測試（pytest 1653 passed／1 skipped，基準就失敗的 `test_multi_provider` 已排除）；驗收的兩次實跑還沒做**——
worker 對話已超過 37 萬 token（用 `scripts/session_guard.py` 量的，370,709），依規則在這個段落邊界交接，建議換新 session 接手實跑。
前後數字目前只有基線（下表）與離線可驗證的部分；實跑清單在最後的「交接」。

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

## 七項改動（程式，已 commit 在 `feat/cost-fix`）
| # | 改動 | 位置 | 測試 |
|---|---|---|---|
| 1 | 除 plan 階段外全 sonnet；effort 預設 low，事實查核與仲裁 medium；離開中位門檻 0.40；硬規則改成「opus 只准出現在 topic 產出 agent」、查核員下限 sonnet·medium；舊 economy 模式併入預設 | `review/config.py`、`channels/shared/review_panels.yaml` | `test_review_tiers.py`、`test_review_config.py` |
| 2 | 每席次結果快取：key＝階段＋席次 id（含 persona id，不含每輪換的措辭）＋去掉 persona 措辭的 prompt（含 brief／rubric／規則）＋該席看到的檔案內容雜湊（JSON 去掉 `generated_at`／`build_seconds`／`reused` 等易變欄位；衍生的 contact sheet 不算；素材階段用每張的 identity＋AI 圖位元組＋credits）＋schema＋tools＋model＋effort。只存合格答案；首頁情境觀眾（feeds 每席洗牌）不快取。`CF_REVIEW_CACHE=0` 關閉 | `review/cache.py`、`review/rounds.py` | `test_review_cache.py` |
| 3 | 只重評需要的席次：上一輪沒過自己門檻的（編劇低於 6.5、提早離開的觀眾）＋它指出的句子被改或在 fix_scope 連動範圍內的 → 重跑；其餘沿用（`carried_from`，不叫用、不計費）。事實查核員只重查改過的句子（★ 差異視圖，自己的 cwd），舊 claims 中沒動到的句子併回。改動超過 25% 句或章節主張變了 → 全部重評。holdout 不沿用。`CF_REVIEW_REUSE=0` 關閉 | `review/reuse.py`、`review/rounds.py`、`review/gate.py` | `test_review_reuse.py` |
| 4 | 產出 agent 只改被點名處：退回 brief 縮成「要改的句子（id＋現文）＋理由」，不再重放整份任務與 skill 文件；程式逐句／逐張投影片／逐標題比對，改到沒被點名的部分就拒收並還原重做（最多 2 次）。清單沒指到任何句子的整體結構問題才准大改，且 receipt 的 `rewrite_reason` 必填並寫進 log | `review/touch_guard.py`、`production/panel_flow.py`、`review/producers.py` | `test_review_touch_guard.py` |
| 5 | 縮短評審輸入：觀眾只拿講稿＋分鏡＋承諾（不拿 sources／article／contact sheet）；查核只拿句子＋article＋sources（不拿分鏡）；導演不拿 article／sources；標題階段觀眾不拿講稿、設計師不拿講稿 | `review/materials.py`（`audience`、`visible_to`） | `test_review_cache.py::test_each_reviewer_is_listed_only_the_files_it_needs` |
| 6 | 對話大小守門：讀自己 transcript 最後一則 assistant 的 usage（prefix token），≥ 30 萬 exit 3；PostToolUse hook 模式；orchestrator 端同一支腳本讀自己的 transcript。配線建議見 `REPORT-session-guard.md`（未套用：在 repo 外） | `scripts/session_guard.py` | `test_session_guard.py` |
| 7 | 每支片雲端車道預算：評審＋產出 agent 的名目 $ 加總（評分卡＋producers.jsonl），預設 $15（`review.budget.usd_per_video`、`CF_BUDGET_USD`、`produce.py run --budget-usd N`，後者寫進 `review/budget.json` 且可帶 `since`）；用完在下一輪評審／下一次產出前停下並寫 `review/budget.stop.json`，不自動繼續 | `review/budget.py`、`production/panel_flow.py` | `test_review_budget.py` |

## 預設設定表（`channels/shared/review_panels.yaml`，🟢 有測試鎖住）
| 階段 | 產出 agent | 席次（人數 model·effort） | 仲裁 | 最大輪 |
|---|---|---|---|---|
| topic | **opus·medium（plan，唯一的 opus）** | 觀眾×3、編劇（故事）、製作人 皆 sonnet·low | — | 2 |
| article | sonnet·low | 查核×2 sonnet·**medium**、編劇（故事）sonnet·low | sonnet·medium | 3 |
| script_structure | sonnet·low | 觀眾×5（含 1 holdout）、編劇×2、導演 皆 sonnet·low；查核×1 sonnet·medium（只列出） | — | 3 |
| script_facts | （共用 deck 產出） | 查核×2 sonnet·medium | sonnet·medium | 3 |
| title_thumb | sonnet·low | 觀眾×5、設計師、製作人 皆 sonnet·low | — | 3 |
| media | — | 合規 sonnet·low | — | 3 |
| final | — | 觀眾×5（含 1 holdout）、剪輯（畫面）、剪輯（聲音）、導演 皆 sonnet·low | — | 3 |
| shorts_* | sonnet·low | 觀眾×3＋編劇／剪輯 皆 sonnet·low | — | 1–3 |
- 離開中位門檻 0.40（script_structure、final、shorts_script、shorts_final）；編劇門檻 6.5；查核 0 錯誤；聚合 agent 仍是 haiku·low（只整理清單，不評審）。
- `--review-tier opus:high` 對照實驗標 `tier_mode: lifted`，放寬 opus 上限，只能把席次拉高。

## 取捨與風險（🟡 要讓 Leon 知道）
- **沿用上一輪答案＝把一次抽樣意見留過一次改稿**。通過的席次不重抽、不過的重抽，所以通過率比「每輪全部重抽」略高；
  緩解：改動 >25% 句整批重評、holdout 只在最後一輪新抽。評分卡 `carry.reasons` 逐席寫了為什麼沿用或重跑。
- **差異查核的邊界**：沒被改到的句子，查核員的舊結論被保留（包括舊的錯誤）；新錯誤只可能出在被改的句子（★）。重寫引入新錯誤正是 10-18 文章 0/4 的主因，邊界和失敗模式吻合。
- **plan 範圍採最窄解讀**（見「範圍決定」）：只有 `topic` 產出 agent 是 opus。把 deck 的大綱規劃也算 plan，需要把 deck 拆成兩次呼叫（outline opus＋script sonnet），未做。
- effort low 的評審品質未實測（Leon 指定）；實跑要順便記分數分布，與 10-19 的 medium 比。

## 進度紀錄（append）
- 2026-10-22 開分支 `feat/cost-fix`（從 `feat/yokai-tempo` 最新；worktree 預設的 `worktree-cf-cost-fix` 在舊點，已切換），寫 `scripts/review_cost_report.py`，量基線。
- commit 順序：模型政策（1）→ 快取＋縮短輸入（2、5）→ 預算（7）→ 只改被點名處（4）→ 只重評需要的席次（3）→ session guard（6）。
- 全套 pytest：1653 passed／1 skipped（`--deselect tests/unit/test_multi_provider.py`）。

### 交接（對話已 37 萬 token，依規則在此交給新 session）
**還沒做的（依序）**
1. 補測試：**article 階段的差異查核**（`materials.article(only=…)`、`article_diff.mark_article`、`reuse.merge_fact` 以引文對應句子）程式寫了，`test_review_reuse.py` 只測了 script_facts；補一個 article round-2 測試。
2. 離線量「縮短輸入」前後差：九尾狐 `output/yokai-kyubi-v2/review/script_structure/round-1/prompts/*.md` 列的檔案＋大小，對照 `Materials.visible_to(kind)` 之後每席列出的檔案位元組數。
3. **驗收實跑一：九尾狐從素材階段起跑到 gate_final**。run-dir 在 `/Users/lileon/project/content-farm/.claude/worktrees/cf-yokai-tempo/output/yokai-kyubi-v2`（ignored）。
   - 先 `cp -c -R` 到本 worktree 的 `output/yokai-kyubi-v2`（APFS clone），刪掉 `review/tier.json`（舊 economy 標記），寫 `review/budget.json`：`{"usd": 15, "since": "<現在 ISO>"}`（舊的 $84.8 不算進新預算）。
   - 指令：`PYTHONPATH=$PWD/src /Users/lileon/project/content-farm/.venv/bin/python scripts/produce.py run --run-dir output/yokai-kyubi-v2 --auto-agents --no-stock --env-file /Users/lileon/project/content-farm/.env`（`.env` 不要複製進 worktree）。本機重工作（illustrate／media／assembly／mascot／mix 約 1–2 小時）經 `lanes.queue` 排隊，記憶體 critical 時會等。
   - 停在 gate_final（留給 Leon），不上傳、不開瀏覽器。
   - 記錄：`python3 scripts/review_cost_report.py output/yokai-kyubi-v2 --json`（名目 $、token、輪數、快取／沿用欄）＋ `production.log.jsonl` 牆鐘。**對照組＝10-19 同階段**：素材 3 輪（$0.67）、成片評審 1 輪 $3.19／194 s、deck 產出 16 次 $31.4（見基線表）。
4. **驗收實跑二：一支新片從頭（選題由評審團挑）**，建議頻道 chipcat，用法見 `REPORT-production-workflow.md`；同樣 `--auto-agents`，記錄總名目費用、總 token、總牆鐘、每階段輪數，對照 `REPORT-review-panels.md`「每階段實測」表（文章 2 輪未過、到第 2 步止 $7.5–10）。預算預設 $15；中途停下就**報告停下點**，不要自己調高。
5. 把實跑數字填進 TL;DR 與新增的「前後數字」表；列「剩下的浪費」（候選：標題階段首頁觀眾每輪全員重評、`final` 階段沒有沿用、deck 產出 agent 的 cache_read 仍隨對話長度成長、media 本機重算 24 分鐘）。
6. 收工：`CLAIMS.jsonl`（已含指向本檔的 `file_exists`）、commit、`orch_mail.py put` 一行指標回報 main。

**驗證過（接手不用重做）**：全套 pytest 綠；`scripts/session_guard.py` 對真 transcript 量到 370,709 token（與手算 369,259＋411 吻合）。
**沒驗證**：沒跑過真的 `claude -p`（所有測試用假 client）；effort low 的評審品質；article 差異查核。

## 副作用與清理
- 本 worktree 內：`graft/`（graft hook 建的索引資料夾，開工前就有，ignored）。job tmp：`~/.claude/jobs/fabede4d/tmp/patch_*.py`（一次性改檔腳本，可刪）。沒動 `output/`、沒 push。
