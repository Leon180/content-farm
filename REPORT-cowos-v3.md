# REPORT — CoWoS v3（eval 修正＋留存節拍＋BGM／音效＋上線前 eval 工具）

## TL;DR
（進行中，收工前改寫）

## 進度紀錄（append）
- 2026-10-17 分支 `feat/cowos-v3` 從 `feat/channel-voices` a5a4e41 開，merge `design/channel-hosts` a6885eb。
  衝突：`channels/{yokai,cel,offwork}.yaml`（mascot 取 hosts、voice 取 voices；依 Leon 決策 offwork/cel 用 `-3d` 包、yokai 用平面包）、
  `CLAIMS.jsonl`（換成本分支自己的）。`test_production_channels.py` 的 cel 包斷言同步改成 `paint-bottle-3d`。
- 合併後 pytest：1 失敗 `test_multi_provider.py::test_returns_first_provider_results`——該檔與 `visual/multi_provider.py`
  最後修改在 dc3f094（遠早於本分支），屬既有失敗，非本分支造成。
- Leon 追加（任務中）：「影片封面有點太弱，建議上網研究別人怎麼做」→ 派研究子代理，產出 `docs/research/thumbnails-2026-10.md`。
  結果：Test & Compare 機制 🟢（最多 3 款、以觀看時間占比判勝、最長 2 週、僅桌機、Shorts 不適用）；
  **別台頻道縮圖樣式未取得**（搜尋只拿到泛用頁，表格標「未取得」，需人工截圖補）。新 3 款規格：共用淺底 #F0F4F8／深藍 #0F1B2D／橘 #D9480F，
  左上固定「台積電 · CoWoS」標籤；A「晶片不一定翻倍？」＋驚訝貓、B「卡在封裝？」＋自繪剖面圖、C「一片晶圓 70→5」。
- orchestrator 轉達（已 ack）：db043ed0a7b81988 — pypinyin 可裝進 TTS venv（`~/.local/share/qwen3-tts/.venv`），念錯檢查升拼音層級；
  不代核 gate_final；不動 yokai run-dir。6b6b317b40f064bb — 念錯政策：speech_check 單段 warn 只記錄，
  只有合成觀眾點名發音問題才回配音步驟（加發音表＋重生該段）。
- 已提交 3fd…（見 git log）：retention/、audio_mix/、QC 死區、`mix` 步驟、字幕 60px 半透明底條。
- 已提交：投影片「依旁白逐條出現＋強調脈衝」（stage_cues，s18 試渲最長靜止 26.8→5.3 s）；eval 工具（評審團設定檔、
  首頁情境縮圖、評分卡、`produce.py eval-loop`）。baseline 已匯入 `output/cowos-v3/eval/baseline/`：
  觀眾（8:12 版）離開中位 26%、點擊 5.4、投入 4.68；客觀（9:49 版）視覺 6.2🔴／聽覺 6.7🔴（-19.7 LUFS、無 BGM）／內容 2.0🔴（死區 25、最大間隔 61.9 s）。
- 下一步：CoWoS 內容修正（deck）→ 縮圖 3 款 → 重渲 → eval 第 1 輪。
- 21:40 deck v3 寫好（27 張，beat lint 預估最大間隔 10.0 s、約 10:00）、deck gate 核可（by claude-cowos-v3，附修正摘要）；
  縮圖 3 款（A 角色／B 自繪剖面 panel／C 62→5）渲染並通過承諾檢查；舊 audio/visual/assembly/subtitles 移到 `v2-*`。
- 21:47 配音開跑；發現與 ACE-Step 子代理的資源閘門互鎖（它的等待迴圈字串含 pattern，被 `pgrep -f` 當成忙碌）→ 結束該迴圈、修 `busy_pids` 忽略 shell。
- 拼音層級念錯檢查完成（pypinyin 0.55.0 只裝在 TTS venv）；v2 音檔：平均 CER 0.048 → 拼音 0.016，s22 CoPoS 0.153 → 0。
- ACE-Step 1.5 授權已核：程式 MIT、權重 MIT、模型卡明寫輸出可商用（`~/.local/share/content-farm-music/chipcat/LICENSE-NOTE.md`）。
- 22:20–22:45 實際配音時間軸 beat lint：7 處 10–12 s → 改 8 句句型重配 → 最大間隔 10.0 s；發現字幕對齊塌縮（s13 兩句 0.3 s／0.0 s、前面 9.5 s 無字幕），
  修 `subtitle/repair.py` 並在客觀指標加「字幕閃現」→ 0；舞台時間配對修正（帶數字的標籤只認說出該數字的句子）。
- **22:50 中斷**：「voice 重對齊＋media」背景執行被 Claude Code 以「系統記憶體嚴重不足」停止（非指令錯誤；當下 free 回到 82%）。
  依該通知「不得自行重啟、等指示」，已回報 orchestrator，等候指示。ACE-Step 尚未產出任何 BGM（等待無 ffmpeg 的空窗）。
  續作指令：`PYTHONPATH=src .venv/bin/python scripts/produce.py run --run-dir output/cowos-v3 --env-file <main>/.env --until media`
- **事件與處置**：22:50 我的 media 與 ACE-Step 的 VAE 解碼（MLX 峰值 16.7 GB、峰值 footprint 41 GB）同時跑 → Claude Code 以記憶體不足同時停掉兩者。
  orchestrator 22:5x 核可重跑，條件：**重工作一律串行**（ACE-Step／media／TTS／mlx_video／mflux／ffmpeg 一次一支），每支開始前跑
  pgrep 閘門＋`memory_pressure -Q`（free < 50% 就等）。之後全部照此執行：bgm_main 146 s → bgm_alt 112 s → stinger 48 s（各自閘門檢查，free 83–85%）。
- BGM（ACE-Step 1.5，seed 20261017/18/19）：bgm_main 141.9 s −17.4 LUFS；bgm_alt 120 s −14.2 LUFS；stinger 裁 2.2 s −15.7 LUFS；皆無削波。
  `channels/chipcat.yaml` 加 `audio:`（main 為預設床、alt 用於第 4 章「需求爆發」、stinger 為章節轉場）。
- **eval 第 1 輪**（5 觀眾＋剪輯＋導演）：離開中位 29%（baseline 26%）、點擊 A 5.8／B 4.4／C 4.0（baseline 5.4）、投入 4.76（4.68）；
  首頁情境 A 被選 40%（門檻 2/12＝16.7%）、注意名次中位 3；導演 6／剪輯 5。客觀：內容 10🟢、視覺 7.6🟡、聽覺 8.9🔴（BGM 低於人聲 18.6 dB）。
  未達標 → 第 2 輪修正（全部是清單裡可驗證的項目）：
  - 程式（通用）：diagram 自帶標題、拿掉蓋住長條的下三分之一框；剖面圖動畫（逐層／翹曲）；晶圓計數直接顯示最終值；光罩格不再標 A4；
    首個要點與換頁同時出現；脈衝只打在關鍵元素、整頁不再上橘色；轉場 0.25 s；音效只放揭曉點、間隔 ≥18 s；BGM +2 dB；
    字幕 64 px（5.9%）、每行 ≤14 字、句號優先斷句。
  - 講稿：開場改 62→5 鉤子、名詞三張併成一張剖面動畫、需求章單一時間線且 S/L 問完立刻答、Blackwell 翹曲圖＋回扣論點、
    古文物／外包只講一次、來源措辭修正、光罩比喻改郵票、收尾約 1 分鐘＋下集預告、標題中文開頭；輝達依念錯政策加發音（揮達）。
  - 縮圖：A 小字改「產能翻倍了」、C 拿掉「光罩」改「以前 62 → 以後 5」。
- 已寫：`src/content_farm/retention/{timing,beats}.py`（句子時間軸、鉤子分類與節拍 lint）。下一步：畫面／聲音探測、死區、混音。
- **eval 第 2 輪**（8:19）：離開中位 **55% ✓**（工程師看完、投資人 6:15、通勤 4:35、學生 2:35、長輩 1:55）、
  點擊 A 5.4／B 4.6／C 5.6 ✗（門檻 7）、投入 5.11；首頁情境 A 被選 40%／注意 3、B 20%／4、C 40%／2；剪輯 6、導演 6。
  客觀：視覺 8.1🟡、聽覺 10🟢、內容 10🟢；QC 0 error、死區 0、最大鉤子間隔 10.0 s、最長靜止 8.0 s、−14.0 LUFS／TP −2.1 dBTP。
  唯一未過：點擊。觀眾點名的事實問題（都可驗證、已改）：A4 比喻錯（858 mm² ≈ 郵票）、The Register 與日經措辭混用、
  「51%」分母不清、欣興月報沒有稼動率、9 倍是「規劃」不是「以後」、「基板與面板」對不上畫面。
- 第 3 輪（最後一輪，含 holdout 老師）修正：
  - 程式（通用）：比較頁兩側同時出現、講到哪側脈衝哪側；字幕「L 版」不拆行；占比圖可不顯示百分比。
  - 講稿：開場改「一倍大小排得下 62 個；規劃中的九倍只剩 5 個」；英文型號／機構名改中文描述；需求章重排（缺口→原因→產能）；
    新增「算盤」章（郵票比喻→每片顆數→換算成晶片數 200 萬 vs 65 萬）；「據報導，超過台積電全年產能的一半」；結論回扣 62→5。
  - 縮圖：A「產能翻倍／晶片沒翻倍？」、B 單一數字「52–78 週交期」＋「AI 晶片要等一年半？」、C 標籤誠實化「1 倍尺寸 → 9 倍（規劃）」。
  - 配音：場景重排後，沿用文字未變的段落（把 raw take 與 identity 搬到新編號），其餘串行重配。
