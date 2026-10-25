# REPORT — 晚點你就知道（technews）ep2：3 支 Shorts（2026-10-25）

分支 `worktree-cf-technews-ep2`（自 `worktree-cf-integrate-1025` 44cfccd 快進）。未 push、未上傳、無付費服務、未開瀏覽器（YouTube 配額只用雷達的 `videos.list`，512 單位，免費）。證據：🟢 本機實測／🟡 只驗到存在／🔴 未驗。

## TL;DR
- 3 支 Shorts 成片（53.3／47.3／52.2 秒，1080×1920，每支 5 張 AI 圖＋全部視差＋合成配樂），QC 0 error。上片包在 `output/upload-20261025/`（gitignore，**不在 repo**），`upload_pack.py --dry-run` 無 PROBLEM（3 支、4803 單位）。🟢
- **Wan 鏡頭＝0**：Shorts（news）管線沒有 Wan 路徑；一段 Wan 約 15 分鐘、峰值 26 GB（REPORT-ai-motion），本機這 5 小時 swap 長在 90–96%，連配音都排了 1.5–2 小時。要的話需另開工（見 §9）。
- 新增：`fact_check` 步驟（正確性查核）、news Short 的 `mix` 步驟（配樂）、`news_thumb.py`、`news_pack.py`；全套 pytest 2160 過、1 個既有失敗（`test_multi_provider`，已 deselect）。🟢
- 頻道署名改為「晚點你就知道」（yaml `name`、片頭來源卡、說明欄、播放清單）；無「晶片貓」字樣。

## 1. 選題（雷達＋評審團）
- 雷達：`produce.py radar --channel technews`（2026-10-25，YouTube 512 單位）→ `output/radar/2026-10-25/technews.json`，10 個候選。時效題前三＝HN：Kimi K3.1 Pro（1,068 分，**不在 48 小時的抓取清單內，未入選**）、No signs of AI payoff outside the tech sector（586 分／615 留言，score 71.1）、America has lost 200k jobs…（427 分／454 留言，68.8）、Google 25 萬棵樹（254 分／205 留言，65.1）。
- 評審團：`news daily --auto 4`（19 則候選、20 篇原文已讀；名目 $0.4435，`output/technews-2026-10-25/selection.json`）。平均分：jobs 8.25（判長片，原文 15,257 字）、AI payoff 7.5（判長，被每日長片上限降 Shorts）、Google 樹 7.25、AI 語言難懂 7.25。
- 取捨：取 payoff、Google 樹、jobs 三則（＝雷達時效題的 2–4 名，且評審分 ≥7.25）。jobs 評審判長片，我改做 Shorts（本任務只要 Shorts）；第四名「AI 語言難懂」雷達無熱度證據，不做。jobs 原文是 9/27 的文章，今日才上 HN 熱門（時效較弱，已在 INDEX 標註）。評審自動建的 `technews-long-2026-10-25-hn-50226419` run-dir 沒使用（留在 `output/`，gitignore）。
- 🟡 Kimi 沒進候選是因為它不在 `max_age_hours: 48` 的 HN 抓取名單；沒深查原因。

## 2. 腳本評審與分數（只記分，不擋）
| 片 | 評審一次＋自動改稿一次 | 離開中位 | writer_story |
|---|---|---|---|
| ai-payoff | 改稿後放行 | 12%（<35%） | 4.5/10 |
| finland-trees | 同上 | （未列） | 5/10 |
| creative-jobs | 同上 | （未列） | 3.5/10 |
共同點：寫手席分數偏低（鉤子前 10 秒名詞偏多、結尾缺帶走點）；沿用 run2 同樣的批評。其他關（title／media／final）停用，沒有分數。

## 3. 正確性查核紀錄（新增 `fact_check` 步驟）
- 做法：`news.py factcheck`＝一次 `claude -p`（sonnet·medium、無工具）讀稿＋原文，列出錯誤句與信心度；**信心度 ≥0.5 才算錯**，自動修一次（改寫或刪句），原稿存 `news_script.draft.json`，不重查；紀錄 `review/fact_audit.json`＋`review/auto_fix.jsonl`。放在 `news_prepare` 前，所以腳本評審改稿後（news_script 變動）會對改後稿再查一次，之後不再開新輪。測試 `tests/unit/test_news_fact_check.py`（4）。
- 結果：3 支都是 `clean`（沒有 ≥0.5 的錯）。低信心提醒（<0.5，未計為錯）：payoff 的「七巨頭都靠 AI 賺翻了」（0.4，原文沒把七巨頭獲利歸因 AI）、「AI 最難補上」（0.3，最高級是推論）→ **我手動改稿**（規則不要求，屬編輯判斷）：鉤子改「七巨頭的營收和利潤都在升…報告說：持平」、結尾改「報告提醒…AI 不懂責任與信任」。
- 🟡 查核員是同一個 sonnet 讀同一份原文，沒有第二人複核；單一來源（轉述類如 NY Post→Guardian 沒有讀到衛報原文，片中用「被指」「據美國媒體轉述英國報導」）。

## 4. 發音處理
- 用發音表＋回讀檢查（whisper large-v3-turbo）。成片 15 個場景回讀全部 `ok`（最差 CER 0.085，門檻 0.12），missing_terms 全空。
- 試聽試驗（`pronunciation_trial.py`，technews-ref，2 seed）發現念錯 → **改寫句子**而非加發音表（同音字替換風險高、鳥案教訓）：
  - 「紐約郵報」→回讀「星月／行月郵報」、「衛報」→「未報」：旁白改「據美國媒體轉述英國報導」（來源名在畫面來源卡與說明欄）。
  - 「環評」→「環屏／環平」：旁白一律說「環境影響評估」（試驗回讀 2/2 正確）。
  - 「併購」→「BGO」、「合併」→「合避」：改「企業整合」。
  - 「公頃」→「公空／公控」（4 次重生仍 warn）：旁白拿掉面積，數字 330 公頃只放畫面。
  - 「撐住」→「顫住」：改「頂得住」；「近月」→「靳悅」：改「最近幾個月」；「報導也稱」→「暴導」：刪。
  - token（回讀 Token ✓）、阿波羅 ✓、Google ✓，無需發音表。
- 「鳥」「鷹」：3 支旁白都沒有。發音表**沒有新增條目**。
- 含難字的句子剪成試聽檔：`artifacts/technews-ep2/audio-check/`（7 個 mp3：payoff 阿波羅／token、trees 引述／Google／環評、jobs 整合／頂得住／最近幾個月）。🔴 沒有人耳聽過。
- 🟡 試驗第二輪（公頃、頂得住、最近幾個月的 seed 對照）因機器排隊 >40 分鐘取消，改法是直接重配後看回讀（皆 ok），不是試驗證明。

## 5. 視覺與配樂
- 生圖：15 張（每支 5 張，z-image-turbo 4-bit 本機，1024×944）；視差 15 段（Depth Anything V2 Small）；**Wan 0**。動物：只有一隻狼（站在雪村路邊，有狼身、無手）。無人臉、無人手；圖內無文字。檢查：我逐格看了 3 張每 2 秒一格的格狀圖（見 §7），未見人手、臉變形、錯字。
- 修的問題：英雄數字在圖上用 teal 疊 teal 看不清（「7 vs 493」）→ 圖上數字改琥珀色（`news_short.html.j2`）。🟢 重渲染後看過。
- 瑕疵 🟡：jobs 第 4 段「商業模式」插圖畫面偏空（小攤位在右下）；trees 第 3 段狼被標題字部分遮住；片頭卡「AI 示意圖」徽章小。來源卡下方英文原標題固定顯示（版型既有）。
- 配樂：新增 news Short 的 `mix` 步驟（`channel.audio.enabled` 時才跑；晶片貓不受影響），technews 的 A 小調脈衝＋轉場音，人聲 −23.4 LUFS 不加增益。
- 字幕與縮圖：字幕沿用 9:16 重排（每行 ≤13 字）；封面見 §6。

## 6. 縮圖（thumbnail-v2 規則）與上片資料
- 每支 2 個選項（`scripts/news_thumb.py`，用該片自己的 beat 圖：上 62% 主體、下方深色底板放 4–8 字鉤子、手機 168 px 寬字高 ≥24 px，<2 MB），Shorts 同時給建議封面格（`cover_frame.json`：第 2 秒、第 1 段）。
  - payoff：A「AI 沒賺到錢？」（beat1）／B「493 家持平」（beat2）
  - trees：A「25 萬棵樹」（beat1）／B「先砍後環評」（beat4）
  - jobs：A「20 萬個工作不見」（beat1）／B「AI 的錯嗎？」（beat3）
  圖在 `artifacts/technews-ep2/thumbs/`。🟡 「AI 沒賺到錢？」比原文（只說科技業以外）略強，標題有補上限定；未做 A/B 實測。
- 上片包：`output/upload-20261025/technews-{ai-payoff,finland-trees,creative-jobs}/`（`video.mp4`、`metadata.md`、`pinned-comment.txt`、縮圖選項、`cover_frame.json`），外加 `INDEX.md`。說明欄 1.2–1.3 KB（≤4800）、無角括號、署名「晚點你就知道」、合成內容建議「否」（扁平插畫＋標示，無擬真人臉；理由寫在 metadata）、標籤、置頂留言（完整出處）。`upload_pack.py --dry-run --pack-dir output/upload-20261025`：無 PROBLEM。生成器 `scripts/news_pack.py`。
- 標題：「AI 砸了大錢，七巨頭以外的美國公司還沒看到回報」／「Google 在芬蘭蓋資料中心，被指環評前先砍了約 25 萬棵樹」／「美國創意產業四年少了 20 萬個工作，AI 要負多少責任？」（皆加 #Shorts）。

## 7. 成片、預覽與驗收材料
| 片 | 長度 | 成片（全尺寸） | 540 寬預覽 | 每 2 秒格狀圖 |
|---|---|---|---|---|
| ai-payoff | 53.3 s | `output/technews-2026-10-25-hn-50224463/assembly/release.mp4`（＝上片包 video.mp4） | `artifacts/technews-ep2/ai-payoff-540w.mp4` | `sheet-ai-payoff.jpg` |
| finland-trees | 47.3 s | `…hn-50221676/assembly/release.mp4` | `finland-trees-540w.mp4` | `sheet-finland-trees.jpg` |
| creative-jobs | 52.2 s | `…hn-50226419/assembly/release.mp4` | `creative-jobs-540w.mp4` | `sheet-creative-jobs.jpg` |
（路徑皆在 `artifacts/technews-ep2/`；全尺寸成片在 gitignore 的 `output/`。）

## 8. 費用與牆鐘
- 名目（訂閱額度，無付費 API）：選題評審 $0.4435；稿 producer 約 $0.11／支（腳本評審改稿）；正確性查核約 $0.07／次（共 ≈9 次）；腳本評審 5 席的費用我沒逐項加總 🟡。合計估 <$2，遠低於 $10。
- 牆鐘：約 5 小時（23:20→04:40），**其中約 4 小時在等本機資源**：配音要 22.7 GB 可用記憶體加 GPU 閒置，swap 90–96%，被其他 worker（yokai 配音等）排掉；實際配音 107 s、渲染 472 s（含 5 張圖＋視差）、mix 4 s。因發音修正重配兩輪（trees／jobs 各 2 次，payoff 2 次）。

## 9. 風險與待決
- 🟡 **Wan**：若 Leon 要 Shorts 也有 Wan，需要新做 news 管線的 Wan 鏡頭（`ai_motion.py bake` 夜間批次＋貼進 beat 頁），約 8 段×15 分鐘×3 支；建議只對 1 支做試驗。
- 🟡 jobs 的 hook 圖（空攝影棚）與 beat4 較弱；payoff 評審 writer 分數低（鉤子與結尾），沒有再改。
- 🔴 音訊沒有人耳聽過；請聽 `audio-check/`。
- 🟡 `Kimi K3.1 Pro` 是雷達第一名卻沒入選（見 §1）。
- 🟡 trees 來源是轉述（NY Post→Guardian），已用「被指／據轉述」，仍建議上片前看一眼衛報原文。
- 已知既有：`test_multi_provider` 失敗（與本次無關）。

## 10. 程式變更（commit 內容）
- `src/content_farm/production/news/fact_check.py`（新）、`scripts/news.py`（`factcheck`、`render --env-file`）、`series.py`（`fact_check` 欄位）、`steps.py`（`fact_check`、`mix`、render 帶 `--env-file`）、`channels/technews.yaml`（署名＝晚點你就知道、`fact_check: true`）、`glossary.yaml`（token／環境影響評估／商業模式）、`news_short.html.j2`（圖上數字色）、`scripts/news_thumb.py`、`scripts/news_pack.py`、測試（`test_news_fact_check.py` 新、`test_news_flow.py` 改）。
- 修掉的坑：`news.py render` 原本讀 worktree 自己的設定檔（worktree 沒有）→ 生圖工具路徑找不到；現在 `steps.py` 把 `--env-file` 傳進去。

## 副作用與清理
- `output/`（gitignore）：選題日目錄、3 個 Short run-dir、評審自動建的 `technews-long-2026-10-25-hn-50226419`、`technews-2026-10-25-hn-50223647`（第 4 名，未使用）、`output/radar/`、`output/upload-20261025/`。不能 `rm`，留給 orchestrator。
- 暫存在 job tmp（隨 job 清除）。無殘留程序；pronunciation_trial 第二輪的佇列票已 kill。

## 進度紀錄
- 2026-10-26：3 支成片＋上片包＋縮圖＋報告完成；對話遠低於 30 萬 token。
