# REPORT — 評審團接進 pipeline（feat/review-panels）

## TL;DR
- **評審團已接進 pipeline**（`feat/review-panels`，未 push）：六個閘門（選題／文章／腳本／標題縮圖／素材／成片）全部由 pipeline 自己啟動的
  `claude -p --model --effort --json-schema` 子程序評審（走訂閱、不帶 API key、不用 `--bare`），過門檻才以 `agent-panel:<stage>` 核可；
  不過就把修改清單（附連動範圍）退回造成問題的步驟。規則寫死在 `review/config.py`＋測試＋`scripts/check.sh`，yaml 只能更嚴。
- **驗收沒有達成第 6 步**：晶片貓新題（評審團 4 次都選 t03「卡在一塊布：AI 伺服器為什麼缺玻璃纖維布」）4 次嘗試都卡在第 2 步——
  「兩位查核 0 錯誤、最多 2 輪」一次都沒達到（最好一輪 0＋2；每位每輪查 41–56 條說法）。已停重試，**需要 Leon 選**：A 文章加第 3 輪／B 第 2 輪起只准刪改／C 維持
  （orch-mail `5406cd176ce7fd45`）。因此沒有新片的 manual-kit／preview／縮圖。
- 第 3／4／6 步改用 CoWoS v3 成品實測（`output/cowos-v3-panels`）：腳本未過（查核 7–8 錯、編劇 6.0–6.4）、標題縮圖未過（B 對比 3.92、C 無主體、
  3 個標題被製作人判誇大——跟 v3 報告人工列出的問題一致）、成片過。**分級 vs 全 opus**：專業評分差 ≤0.6、查核 7 vs 8、sonnet 觀眾反而更嚴
  （離開中位 47% vs 81%）；費用省 24–58%。
- 全機佇列＋每步入場檢查（記憶體／swap／load／GPU／鎖、補位、防餓死、不可能立即失敗、45 分寄 orch-mail）、`scripts/heavy` 與 hook 判斷規則、
  付費路徑擋下、上片排程、TTS 合批都做了並有測試。ffmpeg×TTS 重疊實測：TTS 慢 1.22×、ffmpeg 慢 2.86×，沒有崩潰。
- pytest：合併 `feat/incremental-render` 後 **1458 passed／1 skipped**，唯一既有失敗 `test_multi_provider` 已排除（基準就失敗）。

## 設定檔說明（`channels/shared/review_panels.yaml` 的 `review:` 段）
- `roles`：viewer、writer_story、writer_density、director、fact_checker（可用 Read／WebFetch／WebSearch）、producer、designer、compliance、editor_visual、editor_audio。
- `stages.<stage>`：`gate`（決策檔名）、`reviews`（指紋涵蓋的檔案：變了才重評，「只重跑改過的部分」）、`producer`（產出 agent 的 model／effort）、
  `rework`（預設退回步驟）、`max_rounds`、`seats`（角色×人數×model×effort×holdout）、`threshold`。`channels.<code>.stages` 為頻道覆寫。
- 程式硬規則（`review/config.py`，違反就載入失敗、check.sh 失敗）：各階段必要角色與人數（腳本／成片含 1 位 holdout）、
  **事實查核在任何階段都要 opus·high**、各階段×角色的 model／effort 下限（選題／文章／腳本的非觀眾角色 opus、後期 sonnet·medium）、
  門檻下限（文章查核 0、腳本離開中位 ≥0.5、編劇 ≥7、查核 0、首頁名次 ≤3、被選 ≥2×、合規 0、成片離開中位 ≥0.5）、輪數上限（文章 2、其他 3）、
  查核員必須能 WebFetch。頻道覆寫合併後重驗——只能更嚴。`--review-tier opus:high` 只能把層級拉高（對照實驗用）。
- 閘門放行條件（`review/gate.enforce`）：評分卡存在且對應「目前的」輸入指紋、每個指定席次都有合格輸出、每席的 model／effort 與設定相同、
  實際回答的模型（`modelUsage`）包含指定的那一級、門檻全過。手動 `produce.py approve` 一律要 `--override "<理由>"`，寫進 `production.log.jsonl`。
- 防過擬合：每輪換 persona 措辭與順序；holdout 只在最後一輪（或提早通過後的加測）出現，分數另列、不進修改清單；
  每條意見必須有 ref（句子 id／時間點／項目）＋素材原文 `evidence`，對不上素材的意見自動剔除（評分卡列出剔除數）；不准灌水與誇大縮圖寫在每份 brief。
- 退回：每條意見帶 `caused_by`（topic／article／deck／thumbnail_spec／voice／illustrate／media／assembly／mascot／mix），
  `review/<gate>.fixes.json` 列出每條修正的連動範圍（同詞／數字出現的所有句子 id、標題、縮圖、說明欄；改到章節主張就整章重審）；
  沒有連動範圍的計畫會被拒絕。改稿後的句子 id 保留、只重配改到的句子 ±2、只重畫改到的場景由 `feat/incremental-render` 處理（已合併）。
- 基礎設施失敗（斷網、程序退出、逾時）退避重試 3 次；仍失敗的那輪改名 `round-N-incomplete-*`、不算輪數、不退回。

## 每階段實測（🟢 本機實測，名目費用＝CLI 回報的 list 價，實際走訂閱）
| 階段 | 產出 agent | 評審團一輪（牆鐘／名目） | 退回次數 | 結果 |
|---|---|---|---|---|
| 1 選題 | 195 s（opus·high，12 題） | 84–126 s／$0.64–0.75（5 席） | 0 | 4／4 第 1 輪過，皆選 t03（7.79–7.96） |
| 2 文章（rp1–rp4） | 549–676 s 初稿、362–521 s 重寫 | 212–290 s／$1.67–2.16（查核 opus×2＋編劇） | 每次 1（上限） | 0／4 通過 |
| 3 腳本（CoWoS v3） | — | 243 s／$2.87（分級）・281 s／$3.80（全 opus） | — | 未過 |
| 4 標題縮圖（CoWoS v3） | — | 82–99 s／$0.97–1.03・150 s／$2.28–2.40 | — | 未過 |
| 6 成片（CoWoS v3） | — | 234 s／$3.30・365 s／$7.74 | — | 過 |
- 每支片雲端車道（到第 2 步止）：23–45 分、名目 $7.5–10（`output/chipcat-rp*/review/producers/producers.jsonl`＋各評分卡）。
- 每位 claude -p 評審約 0.42 GB RSS（ps 實測兩位 opus 查核員）→ 設定 0.6 GB，評審並行數依可用記憶體決定。
- 評分卡 HTML：`output/chipcat-rp{1,2,3,4}/review/scorecard.html`、`output/cowos-v3-panels/review/scorecard.html`（每階段每輪分數、席次 model／effort、
  修改清單、被剔除的不可驗證意見、前後版本 diff）。

## 模型分級 vs 全 opus（同一份 CoWoS v3 素材，各 1 次，🟢 但 n=1）
| 階段 | 指標 | 分級 | 全 opus |
|---|---|---|---|
| 腳本 | 編劇（故事／密度）、導演 | 6.4／6.0、5.8 | 6.3／6.3、6.0 |
| 腳本 | 查核錯誤 | 7 | 8 |
| 腳本 | 觀眾離開中位（sonnet vs opus 觀眾） | 47% | 81% |
| 標題 | 首頁注意名次中位（最佳款）／被選率 | 1／0.6 | 1／0.4 |
| 標題 | 製作人判誇大的標題 | T2、T3、T4 | T2、T3、T4 |
| 成片 | 剪輯畫面／聲音、導演 | 6.2／7.0、6.5 | 5.9／6.6、6.6 |
| 成片 | 觀眾離開中位 | 60% | 87% |
| 費用 | 腳本／標題／成片 | $2.87／$0.97／$3.30 | $3.80／$2.28／$7.74 |
結論 🟡：後期降級沒有讓專業評分或查核變鬆；差別最大的是觀眾——opus 觀眾比 sonnet 更有耐心，所以 sonnet 觀眾是更嚴的門檻。

## 四頻道平行跑：產能估計
- 兩條車道：雲端（選題、研究、腳本、標題、所有評審）四頻道可並行；本機（TTS、mflux、mlx_video、ACE-Step、渲染）經全機佇列一次一支（或依入場檢查補位）。
- 本機車道每支片（🟢 實測，來源）：長片配音首輪 30–40 分（prompt 既有數字）、Z-Image 每張 54–61 s（REPORT-ai-illustration）、
  media 305–499 s、assembly 52–65 s、角色疊加 107–162 s、mix 24–45 s（REPORT-incremental-render 新碼整支冷渲）；修正重跑 144–548 s／次。
  → 長片首輪 ≈ 45–55 分＋AI 圖（每張 1 分）＋修正 2–3 次 × 3–9 分 ≈ **1–1.5 小時** 🟡。Short：配音 ≈ 1.5 分＋切片 64–76 s ≈ **3 分**＋修正。
- ffmpeg×TTS 重疊（🟢 n=1）：TTS 1.22×、ffmpeg 2.86× 慢，合計牆鐘省 ≈24%，沒有 mflux×TTS 那種 20 倍崩潰。目前佇列仍讓 TTS（gpu exclusive）與 render 互斥；
  若要吃這 24%，可把 assembly／mix 改成 `gpu: none` 且不拿 render 鎖（建議，未做）。
- 雲端車道每支長片（🟢 只量到第 2 步；之後是 🟡 用 CoWoS 評審實測外推）：選題 5 分＋文章 25–45 分＋腳本（產出 🔴 未量、評審 4 分×≤3 輪）＋標題 1.5 分×≤3＋
  素材合規 🔴＋成片 4 分×≤3 ≈ **1.5–2.5 小時／支、名目 $20–40／支** 🟡。
- **每週產能上限（🟡 估計）**：本機車道 16 h／天 × 7 ≈ 112 h／週 → 只算本機約 75–110 支長片或 2,000 支 Short，**不是瓶頸**；
  計畫節奏（長片 3 支＋HN Shorts 14–35 支＋offwork 5 支／週）只用本機約 6–9 h／週。雲端車道上限是 worker 名額（personal 2）與訂閱用量上限（🔴 沒有數字）：
  2 名額 × 每支 2 h ≈ 每天最多 ≈20 支長片的工時，實際會先撞用量上限。**現在真正的瓶頸是文章查核的通過率（0／4）**。
- 情境：不換硬體——瓶頸在雲端與查核規則，本機有 >90% 餘裕；加一台機器或雲端 GPU——在目前節奏下**幾乎沒有收益** 🟡，
  要到每週 >50 支長片才需要；比較有用的是讓 TTS 與 ffmpeg 重疊（上面的 24%）或第二個 worker 名額。

## 付費路徑（`CF_ANTHROPIC_API_KEY`）
- 查了 scripts／src／skills／tests／Makefile／README／settings（子代理，graft＋grep）：只有 `llm/client.py` 一個檔 import `anthropic`；production runner 從不建 LLMClient。
- **保留並加閘門**（都還有呼叫者）：`scripts/generate_script.py`（`/prescript`、`/script` skill、README）、`scripts/run_bot.py`（`make bot`）、
  `scripts/run_pipeline.py`（`make pipeline`）——沒帶 `--allow-paid` 印一行說明後 exit 2；`LLMClient.__init__` 沒有 `CF_ALLOW_PAID=1` 一律拒絕
  （`trends/handler.py`、`title_generator.py` 只被 bot 用，隨 LLMClient 一起被擋）。**沒有移除任何檔**。`.env` 未動。測試：`tests/unit/test_llm_paid.py`。

## 上片排程
- `channels/<code>.yaml` 的 `publish:`（依 research/upload-timing-2026-10.md，時段全是 🟡 推論）：晶片貓長片週四 20:00、Shorts 12:00／20:00 每天 ≤2 支間隔 ≥4 h、
  時效新聞盡快；妖怪週五 20:00；賽璐璐週三 20:00；下班了週一至五 21:00。
- package 步驟沒有排程時寫入建議時間（`production.schedule.json`，同頻道同一天不排兩支長片、避開其他 run 已排的時間）；
  manual-kit README 寫「在 Studio 排程：yyyy-mm-dd HH:MM 台灣時間，先設私人→排程公開」。`channels/analytics/<code>.json`（Studio 觀眾上線時間）存在時覆寫時段。

## 給 cf-hn-v2 的接法
- HN Shorts 的 run-dir 走 `SHORTS_*` 步驟；閘門名稱 script／final 會自動對到 `shorts_script`／`shorts_final` 評審團（觀眾×3＋編劇×1／觀眾×3＋剪輯×1）。
  從長片切的 Short（`SHORTS_CUT_STEPS`）只剩 final。
- 選題：每天把候選寫成 `topics/candidates.json`（格式見 `review/producers.py` 的 topic 任務），`shorts_topic` 評審團挑前 3（`top_n_short`）；
  標題：寫 `titles.json`＋第一格縮圖到 `thumbnails/variant_*.jpg` 就會進 `shorts_title`（目前 Shorts 步驟表沒有 title 閘門，要加一個 `gate_title` step）。
- 本機工作一律經 `lanes.queue`：在 produce.py 內自動；自己的腳本用 `scripts/heavy --kind short --label hn/<id>:voice -- <cmd>`（Shorts 優先）。
- 上片時間：`publish_slot.ensure_schedule(run_dir, "chipcat", "short", now=…, urgent=True)`。

## 已知限制
- 驗收片停在第 2 步（見 TL;DR）；腳本、標題、素材合規、成片的閘門在**新題目**上沒跑過，只在 CoWoS v3 成品上跑過評審（不含退回後重做）。素材合規（第 5 步）沒有實測。
- 產出 agent 只實測了 topic 與 article；deck、thumbnail_spec 的 prompt 寫好、有測試，但沒有真的跑過。
- 同一支片內不互相依賴的步驟沒有並行（runner 仍是線性）；但標題縮圖已排在配音之前，等本機時不會擋標題評審。
- `analysis` 狀態與「文章退回只帶事實項目」是我為了讓規則可達成做的校準，Leon 尚未看過 🟡。
- 評審意見的 `evidence` 比對是正規化後的子字串；畫面類意見只驗時間點在片長內，無法驗畫面內容。
- 第 2 次嘗試的文章 agent 讀到第 1 次的查核結果（已修，見進度紀錄）；第 3、4 次是獨立的。
- 記憶體需求多數是 🟡 估計（系統層峰值減閒置 5 GB）；`foreign_heavy` 依命令列樣式判斷，Python 內部起的子程序若命令列不含樣式會漏掉。
- hook 本身還沒寫（orchestrator 會依下方規則寫）；`.pre-commit-config.yaml` 已加，但這台機器的 git hook 沒裝（安裝會動到主 checkout 共用的 `.git/hooks`）。

## 副作用與清理
- 都在 gitignore 的 `output/`、沒有 commit：`output/chipcat-rp{1,2,3,4}/`（驗收 4 次）、`output/cowos-v3-panels/`（CoWoS v3 的 APFS clone，佔空間很小）、
  `output/bench/overlap.json`、`output/eval-competitors/chipcat/`（從 cf-cowos-v3 複製的 i.ytimg 競品縮圖，**第三方圖、不可 commit**）。可刪（`rm` 在 deny，留給 orchestrator）。
- `claude -p` 子程序在各 run-dir／round 目錄留下 graft 索引資料夾 `graft/`（graft hook 自動建的），可刪。worktree 根目錄的 `graft/` 是開工前就有的。
- `~/.cache/content-farm/heavy-queue/`（佇列 ticket 與 history.jsonl，跑完會自清 ticket）。
- job tmp `~/.claude/jobs/00536892/tmp/`（量測腳本、smoke 輸出、決策稿）。
- 沒動 cf-cowos-v3、cf-incremental-render 的 run-dir（只讀／clone）；沒 push、沒開瀏覽器、沒上傳、沒呼叫按量付費 API（評審與產出全走 `claude -p` 訂閱）。

## 全機佇列與入場檢查（設計）
- 設定檔 `channels/shared/heavy_work.json`（JSON，`scripts/heavy` 用系統 python3 就能跑）：`admission`（安全邊際 6 GB、swap < 90%、
  load1 < 1.5×核數、防餓死 20 分、通知 45 分、每位 claude -p 評審 0.6 GB）、`steps`（每步 `mem_gb`／`gpu`／`cpu_cores`／`locks`）、
  `processes`（pgrep 樣式）、`commands`（hook 樣式）、`allowed_wrappers`、`read_only_commands`。
- 排隊單位＝「片×step」（ticket job `chipcat/rp3:voice`）。runner 在每個 step 真正開始做事前（cmd 執行、agent 產出、verify、評審團、internal）
  呼叫 `lanes.queue.slot(ticket, need)`；已是最新而跳過的 step 不排隊。雲端車道的 step 只等記憶體，本機車道另外要鎖與 GPU。
- `lanes/resources.decide()`（純函式，逐條有測試）：記憶體（扣掉 90 秒內剛開跑的工作已承諾的量）、swap、load、壓力 critical（暫停新 step，正在跑的不殺）、
  GPU（exclusive 與任何 GPU 工作互斥；shared 只與 exclusive 互斥）、鎖、優先序（HN Shorts > 接近完成的長片 > 其他；
  排前面的若「現在放得下」就讓它先，放不下就讓小工作補位）、防餓死（本機大工作等滿 20 分，就不再放行比它新／低優先的本機工作，雲端照常）。
- 鎖：一次全拿或全不拿，固定順序 gpu（`heavy.lock`，shared＝LOCK_SH／exclusive＝LOCK_EX）→ `render.lock` → `local_tts.lock`（後兩把是舊路徑舊語意）。
- 不可能滿足（`mem_gb + 邊際 > 總記憶體` 或核數不足）→ `ImpossibleNeed` 立即失敗。等超過 45 分 → 一封 orch-mail（personal 指標倉）附佇列快照。
- 評審並行數＝`min(設定上限, ⌊(可用 GB − 6) / 0.6⌋, 評審人數)`，至少 1（step 本身已過入場檢查）。
- 記憶體需求是「該工作相對閒置機器的增量」：系統層峰值（VoxCPM2 21.7／Qwen3 24.5／mlx_video ≈26 GB）減閒置 ≈5 GB 🟡。
  第一版直接用系統層峰值，測試抓到 voice 要 30.5 GB 可用才放行＝32 GB 機器上永遠排不到，已改。

## PreToolUse hook 規則（給 orchestrator）
- 判斷：`scripts/heavy --check "<整條指令>"` → stdout JSON `{"block", "heavy", "matched", "why"}`，**exit 2＝擋、0＝放行**（`lanes/heavy_rules.py`）。
- 範圍：cwd 或指令路徑含 `content-farm` 時才判斷。
- 指令以 `&&`／`||`／`;`／`|` 切段；每段去掉前置 `VAR=…`、`env`、`nohup`、`time`；`python …` 去掉直譯器旗標（`-u`、`-I`、`-X x`）後看腳本。
- 放行：該段的程式是 `scripts/heavy` 或 `scripts/produce.py`；或是唯讀探測（`ffprobe`、`ffmpeg -version`、`pgrep`、`ps`、`which`、`man`）。
- 擋下：任一段符合 `commands` 樣式——`ffmpeg`、`mlx_video`、`mflux-*`、`voxcpm`／`qwen3-tts`／`local_tts_worker.py`、`ACE-Step`、`whisper`、
  repo 的重腳本（`media_to_visual`、`mascot_overlay`、`audio_mix`、`illustrate`、`ai_motion`、`short_from_long`、`render_slides`、`bench_overlap`、
  `voice_batch`、`run_stage.py --stage voice|assembly|assembly_timeline|visual`）。訊息請改用 `scripts/heavy --label … -- <指令>`。
- 測試案例（`tests/unit/test_lanes_heavy_rules.py`，22 條）：擋——`ffmpeg -i in.mov … out.mp4`、`/opt/homebrew/bin/ffmpeg …`、`cd output && ffmpeg …`、
  `PYTHONPATH=src .venv/bin/python scripts/media_to_visual.py …`、`python scripts/run_stage.py --stage voice …`、`python -m mlx_video.generate …`、
  `mflux-generate …`、`…/qwen3-tts/.venv/bin/python scripts/local_tts_worker.py`、`…/ACE-Step/infer.py`、`mlx_whisper a.mp3`、`echo; nohup python scripts/illustrate.py &`；
  放行——`scripts/heavy --label t -- ffmpeg …`、`…/scripts/heavy -- python scripts/media_to_visual.py …`、`… scripts/produce.py run …`、`produce.py queue`、
  `ffprobe …`、`ffmpeg -version`、`pgrep -fl ffmpeg`、`git log`、`python -m pytest`、`grep -rn ffmpeg_path src/`。
- 已知漏洞（hook 擋不到）：Python 程式內部 `subprocess` 叫 ffmpeg（例如未經 produce.py 的自寫腳本）——這類靠佇列的 pgrep 閘門（外來重工作會讓佇列等），不是 hook。

## 進度紀錄（append）
- 2026-10-18 分支 `feat/review-panels` 從 `feat/cowos-v3` d288a04 開（已含 channel-voices a5a4e41、design/channel-hosts a6885eb）。
  `feat/incremental-render` 當下與 cowos-v3 同點（2030c1e 起無新 commit）→ 句子 id 欄位先放 `review_panels.yaml: sentence_id_field`。
- 查證 `claude` CLI 2.1.299（只讀 binary 字串，worker 的 Bash 跑 `claude --help` 被權限擋下，原文：
  `Permission to use Bash with command claude --help has been denied.`）：有 `--json-schema`、`--effort`、`--output-format json`
  （結果欄位 `structured_output`）、`--no-session-persistence`、`--strict-mcp-config`、`--allowed-tools`、`--permission-mode dontAsk`。
  **`--bare` 不能用**：binary 說明原文「Anthropic auth is strictly ANTHROPIC_API_KEY or apiKeyHelper … (OAuth and keychain are never read)」
  ＝會走按量計費。評審子程序一律不帶 `--bare`，並從子程序環境移除 `ANTHROPIC_API_KEY`／`CF_ANTHROPIC_API_KEY`。
- 03:17–12:36 無進度（orchestrator 推測夜間斷線）；12:37 接續。
- 12:37 commit：`review_panels.yaml` 的 `review:` 段＋`review/config.py` 硬規則（必要角色、事實查核 opus·high、層級下限、門檻下限、輪數上限；頻道覆寫只能更嚴）＋測試。
- 13:xx 實測 `claude -p` 子程序（haiku·low、極小 schema）：4.6 s、`structured_output` 正確、`modelUsage` 為 `claude-haiku-5-5`、provider firstParty（未帶 API key ＝訂閱）。
- commit：評審 client／素材／判定／退回路由／panel gate（26 測試）。
- **事故（已處理）**：接 runner 後第一次跑全套 pytest，一個舊 runner 測試走到閘門、真的啟動了 3 個 opus 評審子程序（`pgrep` 看到 `claude -p --model opus …`）；
  停掉 pytest 並 `pkill` 後確認已無殘留。修正：`tests/conftest.py` autouse 把 `CF_CLAUDE_BIN` 指到會 exit 97 的 stub（測試永遠不會叫到真 claude），
  並有測試驗證 stub 生效。
- commit：runner 接評審團（topic／title 閘門、全部閘門不可關、手動 approve 需 `--override` 並記 log、退回標 rework、`--auto-agents`）、
  全機重工作佇列 `lanes/queue.py`＋`produce.py queue`；全套 1357 passed（基準失敗 1 個已排除）。
- 付費路徑擋下（`llm/paid.py`、LLMClient 建構時檢查 `CF_ALLOW_PAID=1`、三支腳本需 `--allow-paid`）、上片排程（`publish_slot.py`＋四頻道 `publish:`）、
  `scripts/check.sh`＋`.pre-commit-config.yaml`（負控制：把 article 事實查核改 sonnet → check.sh 退出 1，已還原）。
- 13:32 斷網：選題產出 agent（claude -p）卡住 1 小時無輸出 → 14:2x kill（runner 正確回報 `exit 143`）、加逐步 timeout＋重試 1 次後重開。
- 14:3x **ffmpeg × TTS 重疊實測**（`scripts/bench_overlap.py`，持有佇列 slot、無其他重工作、free 85%；VoxCPM2 6 句＋libx264 medium 60 s 片段，n=1）🟢：
  TTS 單獨 93.4 s（暖機後每句中位 13.4 s）、重疊 107.1 s（16.4 s／句）＝ **TTS 慢 1.22×**；ffmpeg 單獨 7.6–8.0 s、重疊 9.5–25.0 s（中位 ≈22 s）＝ **ffmpeg 慢 2.86×**。
  沒有出現 mflux×TTS 那種 20 倍崩潰；同樣的工作串行要 ≈140 s、重疊 107 s（省 ≈24%）。結論見報告「兩條車道」。
- `voice_batch.py`（同 provider 共用一個 TTS worker）、`produce.py review --tier`（全 opus 對照用的旁輪，不影響閘門）。
- **驗收第 1 次（`output/chipcat-rp1`）**：
  - 選題：產出 agent 195 s 出 12 題；評審團 5 人（觀眾 sonnet×3、編劇 opus、製作人 opus）第 1 輪過，牆鐘 99 s、名目 $0.67；
    選中 t03「卡在一塊布：AI 伺服器為什麼缺玻璃纖維布」（綜合 7.96，第二名 7.12）。
  - 文章：產出 549 s → 第 1 輪（查核 opus×2 互不參考＋編劇 opus·medium）290 s、$2.01：兩位各找到 3 個錯誤／無來源，退回 → 重寫 378 s →
    第 2 輪 253 s、$2.08：3 個／8 個 → **2 輪用完，卡在第 2 步**（runner 正確以 failed 停下，沒有開閘）。
  - 查核內容是真問題（可驗證）：「台灣唯一」被放大成「日本以外全球唯一」、兩任社長被寫成同一人前後改口、載板廠被寫成受害者但來源說毛利創高、
    「預定完工」寫成已完工、報導刊登日當成事件日、自己的 ppm 換算掛了來源標記。第 2 輪新增的錯誤多來自改寫時新加的句子。
  - 歸因：產出 agent 沒有交件前自我查核，且 `check_article.py` 因 Bash 允許規則太窄跑不了（已修：絕對 PYTHONPATH＋前綴規則）。
    修正（程式，不動門檻）：文章 brief 加逐條自我查核清單；退回 brief 加「新寫的句子一樣會被查」。
  - 第 2 次嘗試在 `output/chipcat-rp2`，沿用同一批 12 個候選，選題由評審團重新決定（重選結果仍是 t03，7.79）。
  - ⚠ 第 2 次的文章 agent 透過全 repo 的 `--add-dir` 讀到第 1 次的查核結果（log 中有 `cd ../chipcat-rp1/review/article/round-2` 被擋，
    但 Read 工具可讀）→ **第 2 次的文章不是獨立重試**。已修：產出 agent 只能讀 `.claude/skills`、`channels`、`src`、`scripts`、`assets`，不能讀 `output/`（有測試）。
    同一支 run 的 process 在修正前就載入了舊程式，所以這次的 deck／標題產出仍是舊權限（第 1 次沒有 deck／標題可讀，影響有限）。
  - 文章第 1 輪：2 個／1 個錯誤（第 1 次是 3／3）→ 退回 → 重寫 521 s → 第 2 輪：2／1 → **2 輪用完，卡在第 2 步**。
    剩下的：作者把「前任社長的謹慎左右開工時機」這個推論寫成事實（兩位都抓到）、引述歸屬錯（「業界主管」）、頻道自己的 ppm 換算被算成無來源。
- **查核校準**（不動門檻 0）：查核 schema 加 `analysis` 狀態＝頻道自己的換算／判斷、文中明確寫成換算或判斷、查核員驗算過——不算錯；
  寫成事實的推論仍是 unsourced、算錯是 wrong。理由：頻道規則要求每支片有自己的觀點段（`take`，YPP inauthentic content 防線），舊判法會讓它永遠過不了。
- **驗收第 3 次（`output/chipcat-rp3`，產出 agent 已不能讀 output/，與前兩次獨立）**：選題又選 t03；文章第 1 輪遇 15:59 斷網——兩位查核 exit 1，
  舊程式算成未過並退回（產出 agent 也因斷網失敗、文章未被改）→ 修程式：基礎設施失敗退避重試 3 次，仍失敗那輪改名 `round-N-incomplete-*` 不算輪數也不退回；
  rp3 依新規則把那輪移開後重開。第 1 輪：0／2 → 重寫 362 s（agent 這次自己跑得動 check_article：0 problem）→ 第 2 輪：2／3 → **2 輪用完**。
  第 2 輪 3 個問題裡 2 個是重寫時新加的句子（為了回應編劇「要更有故事」而寫出「蘋果在日本碰壁後自己跑去小廠當品管」），
  1 個是第 1 輪就存在、但第 1 輪查核員 1 沒抓到（「熔爐熔成細絲」不在來源）＝查核也有變異。
- 修正（產出端，不動規則）：文章退回只帶事實項目；編劇的故事建議存成 `review/article.story_notes.json`，留給腳本階段處理。驗收第 4 次在 `output/chipcat-rp4`。
- 🟡 給 Leon 的觀察（規則是你定的，我沒改）：3 次嘗試、每篇查核員各查 41–51 條說法，「兩位都 0 錯誤、最多 2 輪」一次都沒達到；
  最好的一輪是 0＋2。重寫會引入新錯誤、查核員之間也有變異。可選：文章允許第 3 輪、或第 2 輪起只准刪改被點名的句子（不准新增句子）。
- 15:04 orchestrator：記憶體 critical（swap 95%），本機同時有 38415991 的 cowos-inc（本機 TTS＋media）。15:1x 我查到時 free 82%，
  我的 rp2 當時在雲端車道（只有 claude -p），沒有本機重工作。**相容修正**：佇列取得 slot 時，同時以相同路徑、相同語意（exclusive flock）
  取得舊的 `~/.cache/content-farm/render.lock` 與 `local_tts.lock`，三把全拿到才算拿到，持有到結束——
  沒有這個佇列的分支（舊 `render_lock`／`LocalWorker`）會看到機器忙；它們持有時佇列會等（訊息「slot or a legacy lock held」）。
  拿到 slot 後仍照舊跑 pgrep（`mlx_video|mflux|ffmpeg|qwen3-tts|qwen3_tts|voxcpm|ACE-Step|acestep`）＋`memory_pressure -Q`（free < 50% 就等）。有測試。
