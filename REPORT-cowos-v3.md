# REPORT — CoWoS v3（eval 修正＋留存節拍＋BGM／音效＋上線前 eval 工具）

## TL;DR
- **交件（依 orchestrator 02:45 指示：第 3 輪不論結果直接交，不開第 4 輪）。** 成片 8:30（`output/cowos-v3/assembly/release.mp4`），
  manual-kit＋preview.html＋縮圖 A/B/C 在 `output/cowos-v3/upload/manual/`，評分卡 `output/cowos-v3/eval/scorecard.html`（baseline→r1→r2→r3）。
  gate_final **未核可**（照指示留給 Leon）；未 push。
- **eval 第 3 輪（最後一輪）未全過，唯一未過：點擊意願**（最佳款 A 5.8 < 7）。其他全過：觀眾離開中位 50%（≥50%）、
  holdout 老師 63%；客觀三欄 內容 10🟢／聽覺 10🟢／視覺 8.6🟡（20 處畫面數字與旁白不同步、縮圖 B 對比 3.92、縮圖 C 無主體）。
- **客觀指標 baseline → 第 3 輪**：死區 25 → **0**；鉤子最大間隔 61.9 s → **9.8 s**；第一個鉤子 0.82 s；最長靜止 → **7.25 s**；
  響度 −19.7 LUFS（無 BGM）→ **−14.0 LUFS／TP −2.0 dBTP**、BGM 低於人聲 16.6 dB、ducking 4.3 dB、削波 0；字幕 5.9% 畫面高＋半透明底條、閃現 0。
- **合成觀眾 baseline → r1 → r2 → r3**：離開中位 26% → 29% → 55% → 50%；點擊（最佳款）5.4 → 5.8 → 5.6 → 5.8；
  投入 4.68 → 4.76 → 5.11 → 5.24；專業評審 r3：剪輯 5、導演 5.5、編劇 6。
- **上片前一定要改的事實問題（r3 評審 6/9 人點名）**：5:03「全做 3.3 倍約 200 萬個、9 倍只剩 65 萬個」**沒說「每月」**，
  且算的是**封裝數**不是晶片數——一顆大封裝裡晶片更多，所以標題／縮圖 A 的「晶片不一定翻倍」有誤導之嫌（holdout 老師點出）。
  下一版要改成「封裝數不一定翻倍」或補上單位與假設，並同步改標題與縮圖 A。
- BGM：ACE-Step 1.5 本機生成（程式＋權重 MIT，模型卡明寫輸出可商用），無付費 API、無外部素材。
- 測試：`pytest tests/unit` 1298 passed / 1 skipped（1 個既有失敗 `test_multi_provider` 已排除，非本分支造成）。

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
  - 實際配音時間軸 beat lint：k0／k2／s22 三處 10.4–10.9 s → 拆句加問句（「9 張有多大？」「全做 3.3 倍呢？」「台積電呢？」）→ 最大 9.8 s。
  - 抽格自查後再修（通用程式）：diagram 頁的來源列不再套用「疊在影片上」的陰影（原本糊成一片）；光罩圖掃光改走在「1 次」字下面；
    清單／時間線單元的脈衝底色 0.22 → 0.35（時間線 2023 節點的脈衝人眼看得到、偵測器量不到 → 最長靜止 8.25 s；改後 7.25 s）。
    資料：晶圓圖標籤不再自帶數量（渲染器會自己加，原本變成「62 片：62 片」）。
  - 縮圖：發現 `thumbnail` 步驟只渲染主縮圖，A/B/C 要另跑 `scripts/make_thumbnail.py --variants`（第一次 r3 準備時還是 r2 的圖，已重渲）。
    A 的「晶片沒翻倍？」在色帶裡折行、B 兩行標題壓到大數字 → 改文案（A「產能翻倍／晶片呢？」、B 單行「AI 晶片要等多久？」），
    B 承諾改成講稿原句「訂一批，要等 52 到 78 週」。
- 02:45 orchestrator 轉達 Leon：不再修程式或重渲，這次渲染跑完就跑最後一次評審，不論結果直接交件，未過項目與修正清單寫進 REPORT。已照辦。

## eval 第 3 輪（最後一輪，final stage：5 觀眾＋holdout 老師＋剪輯＋導演＋編劇）
| 指標 | 門檻 | baseline | r1 | r2 | **r3** |
|---|---|---|---|---|---|
| 觀眾離開中位（% 片長） | ≥ 50% | 26% | 29% | 55% | **50% ✓** |
| 點擊意願（最佳款平均） | ≥ 7 | 5.4 | 5.8 | 5.6 | **5.8 ✗**（A 5.8／B 5.4／C 4.6） |
| 投入平均 | — | 4.68 | 4.76 | 5.11 | 5.24 |
| 首頁情境（被選率；注意名次中位） | 選 ≥ 2/N、名次 ≤ 3 | — | A 40%／3 | A 40%／3、C 40%／2 | **A 60%／2**、B 40%／2、C 20%／1 |
| 專業評審 | — | — | 剪輯 5／導演 6 | 6／6 | 剪輯 5、導演 5.5、編劇 6 |
| 客觀：內容／聽覺／視覺 | 全綠 | 🔴🔴🔴 | 🟢🔴🟡 | 🟢🟢🟡 | **🟢 10／🟢 10／🟡 8.6** |
- 觀眾離開：工程師 5:35、通勤 2:45、學生 3:52、長輩 4:15、投資人看完；holdout 老師 5:20（63%）。訂閱 0/6。
- 首頁情境縮圖 A 被選率 60%（機率基準 8.3%），但「看完縮圖、願不願意點」的評分仍只有 5.8——在 feed 裡贏得注意，單看說服力不足。
- 視覺欄未綠的 3 項：畫面數字與旁白不同步 20 處（門檻 ≤3；多數是投影片上的數字比旁白早／晚出現）、縮圖 B 文字對比 3.92（< 4.5）、縮圖 C 主體佔比 0（純數字版型、沒有主角）。
- 「4:50 只剩 VS 的空白頁」（5 人提到）：查 `release.mp4` 4:55 兩側都有字；評審看的截圖表每 5 秒取一格，剛好取到比較頁進場第一瞬間（< 0.3 s）。
  屬取樣假象，但下一版可讓截圖避開換場 0.5 s 內的格。貓遮住「扣邊 3 mm」「3.3 張：16 片」（4:40–4:50）則是真的。
- 發音：輝達 scene_008 仍被 whisper 聽成別字（拼音層級只差聲調），6/6 觀眾都引用了 audio.txt 的標記；另外 CoWoS「扣窩斯」4 人覺得怪，
  AP7、艾克爾（像人名）、The Register、產能利用率／稼動率混用。

## 未過項目與修正清單（給下一支）
依評審票數排序，全部可驗證（時間點對 r3 成片 8:30）。**事實**類先改：
1. **事實（6 人）** 5:03「全做 3.3 倍約 200 萬個、9 倍只剩 65 萬個」→ 補「每月」「假設全部產能只做一種尺寸、未扣良率」，畫面列出算式（13 萬片 × 16、× 5），
   並把「晶片」改成「封裝」——大封裝裡晶片更多，「晶圓翻倍，晶片卻不一定翻倍」會誤導（holdout 老師）。**標題、縮圖 A、0:10 開場句一起改。**
2. **事實** 8:07 回扣說「2016 年台積電自己承認，量太小，沒人會提前蓋廠」：原引述只有「又貴、量又小」，「沒人會提前蓋廠」是推論；且時間線節點標 2016、來源列寫 TSMC 2013-10 → 查證年份、引述與推論分開講。
3. **事實** 0:29「董事長親口說」與卡片上「非逐字引言」矛盾 → 改「據日經報導，董事長表示」。
4. **內容（5 人）** 開場「一倍／九倍大小」沒說是什麼的一倍 → 開場直接用「郵票大 62 個、便利貼大只剩 5 個」，加郵票／便利貼圖示。
5. **內容（3 人）** 全片沒定義 CoWoS／封裝；說明欄寫 HBM 片中沒講 → 0:20 第一次出現就說「CoWoS 是先進封裝：把運算晶片和記憶體接在同一塊底板上裝成一顆」，同時教念法；說明欄同步。
6. **內容（3 人）** 2023–2026 走了三遍、畫面寫「三年」卻列四年 → 時間線當章節目錄，每年點亮時接該年細節。
7. **內容（3 人）** 3:20–4:20 一分鐘丟 8 組數字 → 只留 2024→2026「兩年變四倍」，摩根士丹利 26 萬改小字不念，刪「這些數字可信嗎」。
8. **論點（導演）** 「卡住的是時間，不是技術」和片中最強證據（翹曲、中介層變大＝技術／幾何限制）互相打架，且重講約 5 次 → 改成「技術能做，但做大要時間」之類能涵蓋證據的說法，只講 2 次。
9. **畫面（剪輯）** 0:05–0:23 開場停在晶圓圖 18 秒，「52–78 週」「黃仁勳」沒有對應畫面；5:35 之後 3 分鐘全是白底條列 → 至少換 3 張成流程圖／地圖；4:41 補 16 片中間狀態圖；5:03 把 200 萬 vs 65 萬畫成兩根長條。
10. **畫面** S/L 對照卡停 30 秒（通勤族在 2:45 離開）→ 壓到 12 秒、改剖面示意（整片矽 vs 有機底＋小矽橋）；工程師建議 L 版要講成 RDL＋LSI 才正確。
11. **畫面** 手機上字幕與投影片字太小（字幕約畫面寬 2.5%）→ 下一支評估字幕 1.4 倍（會擠到吉祥物欄，需一起調 clearance）；兩個並排的 2016 節點合併；強調光暈改實色底線。
12. **聲音** 4:40 62/16/5 語速 6.5 字/秒（全片最快）→ 每個數字後停 0.4–0.6 s；BGM 全片同一層級（LRA 2.3 LU）→ 章節間做能量變化。
13. **發音** 輝達（scene_008）、CoWoS 念法、AP7、艾克爾（加「封測廠」）、The Register（改「英國科技媒體」）、產能利用率／稼動率統一。
14. **笑點** 貓砂（「用完就沒了」邏輯不通）、紙箱笑點刪；古文物八卦保留並加插圖。
15. **縮圖** 點擊 5.8 未達 7：A 在 feed 裡最常被選，但承諾要等第 1 項改完才不會誤導；B 對比不足（3.92）；C 沒有主角。
   建議下一支：A 主標改「產能翻倍，封裝呢？」或改以「1 年半」為主承諾，並在 YouTube Studio Test & Compare 用真實觀看時間判勝（README 有步驟）。

## 評審團模組（review panel）擴充點（給 cf-review-panels）
- 設定檔 `channels/shared/review_panels.yaml`：`framings`、各頻道 `personas`（含 `holdout`）、`pros`（editor／director／writer＋rubric）、
  `stages`（目前實作 `rough_cut`、`final`、`shorts`）、`thresholds`。
- 新增 stage（topic／script）：在 yaml 加 stage 條目（reviewers／materials），在 `evaluation/prepare.py` 加對應的素材打包（例如只有講稿與標題、沒有截圖表），
  `evaluation/briefs.py` 依 stage 換 brief 模板；`aggregate.py`／`scorecard.py` 不需改（依結果檔欄位彙整）。`flow.py` 的 `stage_for()` 決定哪一輪用哪個 stage。
- 結果格式：觀眾 `{persona, homepage, click, segments, left_at, finish, subscribe, pronunciation, top_fixes, overall}`；專業 `{role, score, rubric, issues, verdict}`。

## 交付物與位置
- 成片：`output/cowos-v3/assembly/release.mp4`（8:30，1920×1080，−14 LUFS）；混音分軌 `output/cowos-v3/audio/mix/`；QC `output/cowos-v3/qc/qc_report.json`（0 error、1 warning：輝達念錯）。
- 上傳包：`output/cowos-v3/upload/manual/`（README＋Test & Compare 步驟、preview.html、thumbnail_A/B/C.jpg、title、description、srt/vtt、tags）。
  成片閘門未核可 → preview 標「預覽版」，影片檔未放入。
- 評分卡：`output/cowos-v3/eval/scorecard.html`；每輪 `eval/round-*/score.json`；紀錄 `eval/loop.jsonl`（r1–r3）。
- 程式：本分支 `feat/cowos-v3`（未 push）。

## 未驗證／未完成
- 縮圖研究的「別台頻道縮圖樣式表」未取得（需人工截圖補）；設備廠名稱未加入講稿（評審建議點名或刪句，未查證不加）。
- 競品縮圖（`output/eval-competitors/cowos`，i.ytimg.com）只供內部首頁情境評測，未 commit。
- 「200 萬／65 萬」的單位問題是講稿錯誤，成片已含此句；上片前需重配該句（配音＋重渲約 40 分鐘）或接受並在說明欄更正。

## 清理建議
- `output/cowos-v3/` 內 `v2-*`、`r1-*` 舊目錄、`deck.v2.json`／`deck.r1.json`（保留到 Leon 看完成片）。
- `~/.local/share/content-farm-music/`（ACE-Step repo＋venv＋權重約 10.6 GB；BGM 已產出，若不再生成可刪權重）。
- job tmp `~/.claude/jobs/a213de35/tmp/`（腳本與抽格）。
