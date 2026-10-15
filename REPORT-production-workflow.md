# REPORT — v3-C 多頻道影片生產流程

## TL;DR

- 新指令 `scripts/produce.py run --channel <code> --run-dir <dir>` 會把一支片從文章一路跑到 `upload/youtube_meta.json`。它只在四種情況停下：人工閘門、Claude 還沒寫的東西、未授權的付費 TTS、步驟失敗。停下時會產生一頁 `review/<gate>.html` 審核頁，並印出 approve 指令。重跑同一條指令就從中斷處接續，只要輸入的指紋沒變就跳過該步驟。🟢
- 四個頻道各有一份設定檔 `channels/{chipcat,yokai,offwork,cel}.yaml`，每份引用自己的 brand。YouTube 和 TTS 欄位只填環境變數名，填成值的話驗證器會擋下。搞笑頻道沒有文章階段，神話頻道的 artwork 需要授權，動漫頻道不能用原片，這三項差異都寫進了 schema 和步驟表。🟢
- 驗證：CoWoS 用 mock 配音、chipcat 品牌，交給 runner 從頭重跑。四個閘門依序停下並核可（核可人標記為 `claude-validation`，不是 Leon），產出 1920×1080、503.2 s 的成片。QC 抓到 3 張 AI 圖佔位，並擋下成片核可，加上 `--override` 才放行。重步驟合計約 16 分鐘。另外用 yokai、cel 品牌重新渲染同一份 deck 的截圖，確認品牌切換有效。🟢
- 已 merge `design/channel-brands`（`ab84f74`），唯一的衝突在 `CLAIMS.jsonl`。pytest 結果 `1 failed, 1029 passed, 1 skipped`，失敗的是基準就有的那一支。🟢
- 需要 Leon 決定：發片頻率（預設方案估每週 5–6 小時審核）、每週能投入多少審核時間、文章和 deck 兩個閘門要不要合併、要不要放行真配音跑一支片來量實際成本，以及四個頻道的 refresh token 要你本人登入各頻道後取得。

等級：🟢 本機實測、可重跑；🟡 只驗到存在或二手資料；🔴 推論或估計。

## 1. 基準與合併

- 開工時 `git log --oneline -1` 是 `6c47dd1`（worktree 預設分支），所以依指示執行 `git checkout -b feat/production-workflow 8907817`，確認 `8907817 docs: subtitle line-break fix …`。🟢
- 合併 `ab84f74`（`design/channel-brands`），產生 merge commit `17af078`。
  - 唯一的衝突是 `CLAIMS.jsonl`，先取 ours，最後由本報告的 CLAIMS 整份取代。
  - 我用 merge，沒用 cherry-pick。理由是 `brands.py` import 了 `styles.palette_from_css` 和 `contrast_report_for`，而這兩個函式來自 slide-styles 那個 commit（`f566092`），單獨 cherry-pick 品牌那個 commit 會缺依賴。
  - 因此 `themes/styles/` 的 10 種試作風格也跟著進來了。保留的理由：`styles.py` 本身要留，`test_explainer_styles.py` 的對比測試會讀這些 CSS；它們全是 opt-in，沒有傳 `style=` 就不會用到。要拿掉也可以，但要連 `test_explainer_styles.py` 一起處理。
  - `docs/design/channel-brands/`（約 8 MB 圖檔與選稿頁）也一起進來了。
- 沒碰 `.claude/worktrees/cf-channel-brands`，也沒改 `src/content_farm/explainer/mascot/`（`git diff 8907817 HEAD -- src/content_farm/explainer/mascot` 為空）。🟢

## 2. 現況盤點（摘要，全表在提案第 1 節）

| 步驟 | 自動或人工 | 耗時（實測） | 付費 | 常見失敗 | 閘門 |
|---|---|---|---|---|---|
| 選題 | 人 | — | 否 | 沒有 backlog | 人 |
| 文章 `/article` | Claude | 未計 | Claude 用量 | 二手來源、八卦無出處 | 文章審稿 |
| 大綱、deck `/deck-outline` `/deck` | Claude | 0.3 s（轉換） | Claude 用量 | lint 擋來源欄位 | 大綱、講稿 |
| 投影片 | 自動 | 4–6 s | 否 | 溢出 | contact sheet |
| 配音＋字幕 | 自動 | 28–33 s（mock） | **Fish Audio** | 忘帶 `=20` 導致字幕壓到貓 | 付費前要放行 |
| media | 自動＋人（AI 圖手動） | 199–425 s | 否 | 離題 B-roll、有 logo、AI 圖缺 | 原本沒有正式閘門 |
| 合成 | 自動 | 110–173 s | 否 | 黑幀（已自動補） | — |
| 晶片貓疊加 | 自動 | 397–409 s | 否 | 字幕過寬會拒絕執行 | — |
| QC | 原本手動 | 8 s（現在） | 否 | 原本沒做就上 | — |
| 上傳資料 | 自動＋人 | 數秒 | 否 | **影片指向 draft.mp4**、credits 要手貼、章節用估算時間 | 手改 meta |
| 上傳／歸檔 | 自動 | — | API 配額 | 無排程、無 AI 揭露、只支援單一頻道 token；drive 會刪本機檔案 | 人 |

## 3. 架構摘要

詳見 `docs/proposals/production-workflow.md`。

- **頻道設定檔**（`production/channels.py`）：包含 pipeline、brand、角色（`rig_ready` 為 false 時跳過疊加）、聲線（只放環境變數名）、題材、片長、頻率（可設小數）、Shorts 策略、素材政策、閘門、YouTube（共用 OAuth client，各頻道一個 refresh token 的變數名）。
- **選題池與排程**（`production/schedule.py`、`channels/backlog/<code>.yaml`、`produce.py plan --week`）：
  - 頻率 0.5 代表隔週發一支。
  - 挑題排序是 ready > researching > idea，同級再比 deadline，最後比 priority。
  - 開工日已過的時段只接受 ready 的題目。
- **Runner**（`production/runner.py`、`steps.py`、`state.py`）：
  - 步驟分四種：agent、cmd、internal、gate。
  - 狀態寫在 `production.json`，事件記在 `production.log.jsonl`，每步的 log 在 `logs/<step>.log`。
  - 核可會綁定審核當下那些檔案的 sha256 指紋，檔案之後若有變動，會重新停在該閘門。
- **審核**（`production/review.py`）：每個閘門產生一頁自足的 HTML，支援亮暗色和手機，內容是檢查清單、可複製的指令和該閘門的素材。另寫一份 `review/<gate>.decision.json` 給面板 inbox 用，`produce.py inbox` 會列出待審項目。面板的介面設計在提案第 4 節，面板本身沒改。
- **並行**：重步驟（media、assembly、mascot）共用一把全機的 `flock` 渲染鎖，所以同時只會有一支片在渲染。`--max-load` 會在負載過高時等待。
- **QC**（`production/qc.py`）檢查以下項目：
  - 素材政策
  - credits 是否完整、是否還有 pending
  - artwork 是否可營利
  - 字幕安全區
  - 解析度、片長、音畫差
  - blackdetect

  QC 有 error 時，成片閘門必須帶 `--override "理由"` 才能核可。
- **上傳資料**（`production/publish.py`）的變更：
  - 改用 `final.mp4`。
  - 章節時間改用實測時長。
  - 自動附上 credits。
  - 加上 AI 揭露（`containsSyntheticMedia`）和 `publishAt`。
  - 依頻道帶入 refresh token 的變數名。
  - 上傳端（`google_provider.py`、`run_stage.py`）也一併支援這些欄位。

## 4. 實作了什麼（四項）

1. 頻道設定檔、選題池、排程。
2. 一鍵 runner：可續跑，支援指紋失效、付費閘、渲染鎖。
3. 審核頁、decision json、inbox。QC 與上傳資料是 runner 的最後兩步，一起完成。
4. `--brand` 串到 `render_slides.py` 和 `media_to_visual.py`。原本這兩支都沒有 brand 參數，品牌只能在設計腳本裡用。現在 overlay、title card、AI 佔位圖、動態投影片頁都會吃到品牌。

另外更新了 `.claude/skills/deck/SKILL.md`，加了一段「One-command alternative」。

## 5. 測試結果

### CoWoS 重跑（chipcat、mock 配音）🟢

run-dir：`output/cowos-chipcat/`（gitignore）。輸入的 article、sources、deck 從 `docs/examples/explainer-cowos/` 複製。stock 快取從 `cf-v2-integrate` worktree 複製，所以**沒有呼叫任何 Pexels API**（log 裡三支 stock 都標 `(cache)`）。

| 步驟 | 結果 | 耗時 |
|---|---|---|
| article（check_article） | 0 problem | 0.1 s |
| gate_article | 停下，核可 | — |
| deck（deck_to_script --strict） | 通過 | 0.2 s |
| policy | 24 張都符合頻道政策 | — |
| slides（`--brand chipcat`） | 24 張無溢出 | 4.4 s |
| gate_deck | 停下；看過 contact sheet 確認是 chipcat 的報告書風格，核可 | — |
| voice（macos_say，字幕 20 字） | 完成 | 28.3 s |
| media（`--brand chipcat --require-measured`） | 3 支 stock（快取）、3 張 AI 佔位、title card 與 overlay 都套 chipcat 品牌 | 424.7 s |
| gate_media | 停下，核可 | — |
| assembly | 完成 | 109.5 s |
| mascot（2 workers） | 字幕守門通過 | 397.5 s |
| qc | **1 error**（s01、s04、s20 是 AI 佔位），其餘通過：1920×1080、503.2 s、音畫差 1.46 s、無黑幀、字幕不壓到貓 | 8.0 s |
| gate_final | 不帶 override 執行 approve 會被拒（`QC has 1 error(s)…`），帶 `--override` 後核可 | — |
| package（`--publish-at 2026-10-22T19:00+08:00`） | meta 正確，見下 | — |

- 重步驟合計約 16 分鐘。voice 之前量到的 1 分鐘負載約 12；assembly 之後的負載沒有記錄（`--max-load 40` 沒有觸發等待）。
- 續跑驗證：完成後再執行一次 `run`，只會重跑 `policy`（每次都跑，毫秒級），其他步驟全部跳過。
- `upload/youtube_meta.json` 的內容：
  - `video_path: assembly/final.mp4`
  - `privacy_status: private`
  - `publish_at: 2026-10-22T19:00:00+08:00`
  - `contains_synthetic_media: true`
  - `category_id: 27`
  - 6 個章節，時間用實測時長算出（0:00、0:48、2:01、3:05、5:01、6:50）
  - 說明欄依序是章節、摘要、22 條參考資料、Pexels 授權區塊、AI 揭露、頻道名
  - `credentials_env.refresh_token: CF_YT_CHIPCAT_REFRESH_TOKEN`
- 截圖：
  - 成片：`docs/examples/production-workflow/cowos_chipcat_final_{22s,112s}.jpg`
  - 審核頁：`review_final.jpg`、`review_media_phone.jpg`（手機寬度 390 px）
- 驗證過程中修掉的 bug：閘門核可後，`status` 仍顯示 waiting。現在通過的閘門會記成 `approved`，並補了測試。

### 品牌切換 🟢

同一份 CoWoS deck 用 `render_slides.py --brand yokai` 和 `--brand cel` 各渲染 24 張，都沒有溢出。截圖在 `docs/examples/production-workflow/brand-switch/`，s09 和 s14 各有 chipcat、yokai、cel 三版：
- yokai：墨黑底，古籍版框，右側版心直排「妖怪溯源所」，標題用魏碑，【注】用硃砂色。
- cel：米紙底，藍格線，有定位孔、CUT 14/24 框和紅鉛筆底線。
- chipcat：左側墨藍裝訂邊，SPEC-A／SPEC-B 規格表，橘色強調。

`test_explainer_brand_plumbing.py` 會比對 overlay、title card、佔位圖、動態頁的 HTML，確認有品牌時含品牌 CSS 特有的那一行，沒品牌時不含。

### pytest 🟢

```
PYTHONPATH=<wt>/src /Users/lileon/project/content-farm/.venv/bin/python -m pytest tests -q -p no:cacheprovider
→ 1 failed, 1029 passed, 1 skipped
```

- 失敗的是 `test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results`。merge brands 之後、寫新功能之前我跑過一次，結果是同一支失敗＋988 passed；v2 報告記錄 `8907817` 時也是這一支。所以不是本分支新增的。
- 新增 41 項：
  - `test_production_channels` 10
  - `test_production_schedule` 7
  - `test_production_runner` 9（用假執行器，涵蓋完整閘門流程、續跑、改 deck 後重新開閘、付費閘、失敗後重試、缺 agent 產出、退回、HTML escape、頻道不符）
  - `test_production_qc` 11（含 blackdetect 對照組：1.5 s 純黑片必須被抓到）
  - `test_explainer_brand_plumbing` 3
  - `test_youtube_google` +1
- `ruff check` 新檔全過。worktree 裡沒有 `.env`（`ls .env` 回 No such file）。

## 6. Roadmap（摘要，全表在提案第 11 節）

R1 skill 讀頻道設定 → R2 縮圖套品牌 → R3 deck 加 `artwork` 種類與博物館抓圖 → R4 shorts_skit 渲染器（晶片貓下班了目前跑不出片）→ R5 從長片切「一個數字」Shorts → R6 夜間批次 → R7 清中間檔 → R8 片尾接 assembly → R9 面板 inbox → R10 AI 圖自動化 → R11 三個新角色 rig（另一支 worker 負責）→ R12 真配音實測成本 → R13 各頻道 refresh token。

## 7. 需要 Leon 決定

1. **發片頻率**：設定檔目前填的是提案預設：
   - 晶片貓：每週 1 長片＋2 短片
   - 妖怪溯源所：隔週 1 長片＋每週 1 短片
   - 晶片貓下班了：每週 3 短片
   - 賽璐璐研究室：隔週 1 長片＋每週 1 短片

   我估計你每週要花 **5–6 小時**審核（🔴 估計）。若改成每頻道每週 1 長片＋3 短片，約 10 小時；每頻道每天 1 支則超過 30 小時，不可行。
2. **每週可投入的審核時間**：決定 1 之後，用 `production.log.jsonl` 實測 4 週再調整。
3. **要不要減少閘門**：例如把文章和 deck 合成一個閘門，每支約省 10 分鐘，代價是論點出問題要到 deck 才看得到。成片閘門已在 schema 層禁止移除。
4. **放行一次真配音**（Fish Audio 付費），量出實際費用與時長。成本表裡的 TTS 目前是 🔴。
5. **YouTube token**：每個頻道要用該頻道身分跑一次 `scripts/get_youtube_token.py`（會開瀏覽器），把結果填進 `.env` 的 `CF_YT_<CODE>_REFRESH_TOKEN`。
6. **配額**：四個頻道共用一個 GCP 專案時，一天大約只能上傳 6 支（🟡，數字沒有重新查證）。要不要分專案？

## 8. 副作用與清理

- `output/cowos-chipcat/`：驗證用的 run-dir（gitignore），內含 `assembly/mascot.mov` 約 2 GB 的中間檔。`output/brand-check/{yokai,cel}/` 是品牌截圖的來源。兩者都可以刪；`rm` 在 deny 清單，留給 orchestrator 處理。
- `.cache/explainer_stock/`：從 cf-v2-integrate 複製過來的 Pexels 快取（gitignore）。
- `~/.cache/content-farm/render.lock`：渲染鎖檔，空檔案，可留著。
- `PROGRESS-production-workflow.md`：進度紀錄，沒有 commit。
- job tmp（`/Users/lileon/.claude/jobs/bd7508a5/tmp/`）裡有 `shot_review.py`（headless 截圖用）和截圖原檔，job 刪除時會一起清掉。
- 沒有 push（共同限制）。沒動 main、`feat/explainer-v2`、`feat/explainer-mvp`、mascot/、cf-channel-brands worktree，也沒 commit `.env`、`output/`、`data/curriculum_map/`。沒呼叫付費 API；Pexels 也沒打，全部走快取。
- `docs/` 在 `.gitignore` 裡，所以 `docs/proposals/production-workflow.md` 和 `docs/examples/production-workflow/` 是用 `git add -f` 加入的，與先前分支處理 docs 的方式相同。
