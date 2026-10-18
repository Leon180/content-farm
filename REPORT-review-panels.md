# REPORT — 評審團接進 pipeline（feat/review-panels）

## TL;DR
（進行中，完成後改寫）

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
  - 文章第 1 輪：2 個／1 個錯誤（第 1 次是 3／3）→ 退回 → 重寫 521 s → 第 2 輪進行中。
- 15:04 orchestrator：記憶體 critical（swap 95%），本機同時有 38415991 的 cowos-inc（本機 TTS＋media）。15:1x 我查到時 free 82%，
  我的 rp2 當時在雲端車道（只有 claude -p），沒有本機重工作。**相容修正**：佇列取得 slot 時，同時以相同路徑、相同語意（exclusive flock）
  取得舊的 `~/.cache/content-farm/render.lock` 與 `local_tts.lock`，三把全拿到才算拿到，持有到結束——
  沒有這個佇列的分支（舊 `render_lock`／`LocalWorker`）會看到機器忙；它們持有時佇列會等（訊息「slot or a legacy lock held」）。
  拿到 slot 後仍照舊跑 pgrep（`mlx_video|mflux|ffmpeg|qwen3-tts|qwen3_tts|voxcpm|ACE-Step|acestep`）＋`memory_pressure -Q`（free < 50% 就等）。有測試。
