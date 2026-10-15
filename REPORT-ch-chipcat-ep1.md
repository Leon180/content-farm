# REPORT — v4-chipcat：CoWoS 長片上架整備＋晶片貓下班了第一支 Shorts

## TL;DR

- CoWoS 長片換掉 3 張 AI 圖佔位：s01、s20 改用 Pexels stock，s04 改成 reveal_list 動態頁。QC 從 1 error 降到 **0 error / 0 warn**。成片 503.2 s、1920×1080、73 MB，停在 **gate_final 等 Leon**。🟢
- Shorts「一個數字：7,722 平方毫米」已切出：9:16、**24.7 s**、QC 0 error，用 offwork 品牌的片頭、數字頁、片尾，停在 gate_final。新增可重複使用的指令 `produce.py short-from-long`（R5）。🟢
- 追加交件：`produce.py manual-kit` 產出 YouTube Studio 手動上傳包和離線 `preview.html`，長片、Short 各一份。目前都標「預覽版（成片閘門未核可）＋暫用機器聲」。🟢
- `channels/backlog/offwork.yaml` 建好，共 7 題。pytest `1 failed, 1051 passed, 1 skipped`，失敗的是基準就有的那支。🟢
- **需要 Leon 決定**：兩支成片閘門；「一個數字」Shorts 要放哪個頻道（派工指定 offwork，但 chipcat 選題池原本把它列為 chipcat 的 Short）；AI 揭露要不要勾；CoWoS 沿用的 10-22 排程。詳見 §6。

等級：🟢 本機實測、可重跑；🟡 只驗到存在或二手資料；🔴 推論。

## 1. 產物位置

| 項目 | 路徑 |
|---|---|
| CoWoS 成片 | `output/cowos-chipcat/assembly/final.mp4`（503.2 s，76,663,142 bytes） |
| CoWoS 審核頁 | `output/cowos-chipcat/review/final.html` |
| CoWoS 上傳包＋預覽頁 | `output/cowos-chipcat/upload/manual/{README.md,preview.html,…}` |
| Short 成片 | `output/offwork-7722/assembly/final.mp4`（24.7 s，1,439,366 bytes，1080×1920） |
| Short 審核頁 | `output/offwork-7722/review/final.html` |
| Short 上傳包＋預覽頁 | `output/offwork-7722/upload/manual/{README.md,preview.html,…}` |
| 截圖（commit） | `docs/examples/ch-chipcat-ep1/`：`cowos_s01_6s.jpg`、`cowos_s04_58s.jpg`、`cowos_s20_395s.jpg`、`offwork_7722_strip.jpg`（片頭／數字頁×2／片尾）、`offwork_7722_12s.jpg` |

上表路徑都相對於 worktree `/Users/lileon/project/content-farm/.claude/worktrees/cf-ch-chipcat-ep1/`。`output/` 在 gitignore 裡，沒有 commit。

核可指令（留給 Leon）：
```
python scripts/produce.py approve --run-dir output/cowos-chipcat --gate final
python scripts/produce.py approve --run-dir output/offwork-7722 --gate final
# 核可後再跑一次 run（產生正式 youtube_meta.json），再跑 manual-kit，README 的「預覽版」警告就會消失
```

## 2. CoWoS 長片

**基準**：開工時 HEAD 是 `6c47dd1`（worktree 預設），依指示執行 `git checkout -b feat/ch-chipcat-ep1 d9749c1`。run-dir 從 `cf-production-workflow/output/cowos-chipcat` 用 rsync 複製過來，**沒有複製 2.4 GB 的 assembly/**；stock 快取也一併複製。

**3 張佔位怎麼換**（改 `docs/examples/explainer-cowos/deck.json`，那是 deck 的正本，再複製進 run-dir）：

| slide | 原本 | 現在 | 過程 |
|---|---|---|---|
| s01 標題 | ai_image | stock `computer processor chip`，keywords `processor/microprocessor/cpu` → Pexels 35977437（CG 晶片＋電路板） | 第 1 次查 `semiconductor wafer cleanroom`，命中**藥廠無塵室**（畫面上有 DISINFECTANT SOLUTION 標示）。第 2 次查 `silicon wafer`，Pixabay 命中 **LED 燈串**（它的 tag 寫 semiconductor）。兩次都離題。之後先用探針腳本直接查 API 看候選，才選定第 3 次的查詢。 |
| s04 封裝/HBM | ai_image | animated reveal_list | — |
| s20 台灣的位置 | ai_image | stock `construction site crane` → Pexels 32636373（夕陽工地吊車） | 是通用工地畫面，**不是 AP7 實景**。疊字已標地名，B-roll 只當氣氛用，deck notes 有註明。 |

- s01 不能只改成動態頁：lint 要求 footage 比例 ≥ 20%，s01 若改成動態頁只剩 4/24（嘗試過，`deck_to_script --strict` 擋下）。現在是 5/24。🟢
- 閘門：gate_deck、gate_media 標記為 `claude-draft`（v4 允許）；gate_final **沒有碰**。gate_article 是沿用上一輪的 `claude-validation`。🟢
- 步驟耗時：voice 18.8 s（全部沿用 mock 音檔，沒有重新合成）、media 355.6 s、assembly 223.6 s、mascot 683.5 s（當時另有 worker 在跑，負載最高到 66）。🟢
- **QC**（`qc/qc_report.json`）：media_policy ok、credits「5 credited assets, none pending」、字幕不壓到貓、1920×1080、503.2 s、音畫差 1.46 s、無黑幀 → **0 error / 0 warn**。🟢
- **說明欄**（manual-kit 預覽版，與 package 用的是同一個 `build_meta`）：
  - 章節 6 個：0:00、0:48、2:01、3:05、5:01、6:50
  - 摘要含「本頻道不提供投資建議」
  - 參考資料 22 條
  - Pexels 授權 5 條
  - AI 揭露、頻道名
  - 標題 `CoWoS 先進封裝：為什麼 AI 晶片卡在這一關`
  - 標籤 7 個

  🟢
- **AI 揭露文字修正**：原本固定寫「配音與部分插圖為合成內容」，但這支片已經沒有 AI 插圖。現在依 credits 決定：有 ai_image 才提插圖，否則寫「本影片由 AI 輔助製作（配音為合成語音）。」（`publish.ai_disclosure_line`，有測試）。🟢
- 晶片貓 rig 沿用現有版本，`mascot/` 沒動（`git diff d9749c1 HEAD -- src/content_farm/explainer/mascot` 為空）。🟢

## 3. 晶片貓下班了 Shorts（R5：short-from-long）

```
python scripts/produce.py short-from-long --from output/cowos-chipcat --slide s09 --channel offwork \
  --run-dir output/offwork-7722 --title "7,722 平方毫米有多大？台積電的超級載板" \
  --number 7,722 --unit "mm²" --caption "台積電規劃的超級載板可用面積" --aside "≈ 8.8 × 8.8 公分的正方形"
```

**設計**
- 只重用長片已核可的內容：s09 的旁白音檔（`audio/scene_009.mp3`）和它的字幕。**沒有重新配音，也沒有說新的事實**，所以長片的 article／deck／media 審核已經涵蓋這支 Short 說的話，Short 只剩成片閘門。
- 指令會檢查長片的 deck 閘門已核可，沒核可就拒絕切。
- 時間軸：片頭卡（1.5 s）疊在旁白開頭上，第一秒不會沒聲音；接著數字頁做 count-up 動畫；旁白結束後是 2.5 s 的片尾卡，用靜音補到片尾。超過 60 s 就拒絕。
- 字幕：取長片字幕中落在 s09 時間窗的 7 條 cue，平移到 0 秒起算，重新斷行成每行 ≤13 字、每條 ≤2 行；太長的 cue 依字數比例拆開時間。用 ASS 燒入：粗墨框白字，對齊 offwork 的漫畫字風格。
- 畫面：offwork 品牌 CSS 套在 1080×1920 的頁面上，PageCapturer 加了 size 參數（預設不變）。數字頁附來源標註「來源：3D InCites（2024-12-24）」。
- runner 整合：run-dir 裡有 `short_source.json` 時改走 `SHORTS_CUT_STEPS`（cut → qc → gate_final → package），**任何頻道都能用**。重跑 `short-from-long` 一定會 `--force cut`，因為長片換成真配音之後，runner 看不到外部 run-dir 的變化。

**驗證過程** 🟢
- 第 1 版 QC 有 1 error：「就像影印機一次只能印一張 A4。」寬 16 字，超出 940 px。原因是 `wrap_text` 允許行尾多 4 個字，好讓句尾停在標點上；9:16 只能容 1 個。改成 `_wrap_strict` 並補回歸測試。這個 QC 檢查本身是新寫的（原本 9:16 只回 warn），它抓到的是真問題，也就是偵測器確實有在作用。
- 第 2 版看截圖發現兩處問題：片尾「想看完整的？」換行後被對話框蓋住，長片標題在詞中斷行。改模板後重切。
- 最終版 QC：字幕「7 cues fit the 9:16 subtitle band」、1080×1920、24.7 s（頻道目標 20–50 s）、音畫差 0.02 s、無黑幀 → 0 error。
- 截圖見 `docs/examples/ch-chipcat-ep1/offwork_7722_strip.jpg`。
- **upload meta**：標題 `… #Shorts`；說明欄含數字、「完整版在『晶片貓』頻道：《…》」、`#Shorts`、來源（IFTLE 615 連結）、AI 揭露；`privacy_status: private`。`upload/youtube_meta.json` 要等 gate_final 核可後由 package 產生；目前內容在 `upload/manual/` 的預覽版裡，產生方式完全相同（`build_meta`）。
- 「≈ 8.8 × 8.8 公分」是我自己算的：√7722 = 87.9 mm。不是來源給的數字。🟢（算式）

## 4. 追加交件：manual-kit＋preview.html（orch-mail aac6218f、911332f5）

`python scripts/produce.py manual-kit --run-dir <dir>` 會在 `upload/manual/` 產出以下檔案：

- **`README.md`**：按 Studio 上傳順序列出每個欄位要填什麼，包括目標頻道、兒童內容＝否、「變造或合成內容」的建議與理由、類別、語言、字幕上傳、播放清單、片尾畫面／資訊卡（Short 改填「相關影片」）、可見度。
  - 機器聲時，最上面加「暫用機器聲，待換 Fish Audio 後重出」。
  - 成片閘門沒核可時，再加一行「預覽版」。
- **`title.txt`／`description.txt`／`tags.txt`／`subtitles.srt`**：純文字，方便直接貼上。
- **`thumbnail.png`**：暫代用的縮圖，品牌縮圖產生器（R2）還沒做。
  - 長片：標題頁投影片縮成 1280×720（約 218 KB）。
  - Short：1080×1920 的片頭頁。Shorts 的自訂縮圖只能在手機 App 換（🟡，依記憶，未查證）。
- **`preview.html`**：單一檔案，不連任何 CDN。
  - 仿 YouTube 觀看頁，Short 用 9:16 版面。
  - `<video>` 用相對路徑 `../../assembly/final.mp4`。
  - 字幕：VTT 內嵌在頁面裡，用 Blob URL 掛到 `<track>`。Chrome 在 file:// 下會拒絕 `<track src>`，所以不能直接引用檔案（🟡：這條限制是依記憶，**我沒開瀏覽器驗證**，依指示留給 orchestrator 開）。
  - 章節時間可以點擊跳轉。
  - 頂部狀態列顯示配音來源、QC error/warn、片長、檔案大小。

這一輪修掉的兩個 bug，都補了回歸測試：
1. 機器聲偵測原本看「最後一次 voice run」。但重跑時 log 只會寫「Reusing existing audio」，結果誤判成真配音（Short 的 kit 第一次產出時沒有警告）。改成看最後一次**實際合成**用的 provider。fish_audio、elevenlabs、macos_say 三家的 log 都有「… TTS」，偵測得到。
2. 舊的 `upload/youtube_meta.json` 會被當成正式版。CoWoS run-dir 裡留著上一輪 override 核可後 package 產出的檔案，指向的是舊成片。改成只有在 final 閘門對**目前**這支成片核可時，才採用 package 的 meta，其他情況一律從現況重建並標成預覽版。

## 5. offwork 選題池

`channels/backlog/offwork.yaml` 共 7 題：
- `cowos-7722`（in_production）
- `pm-yidiandian`
- `box-packaging`（接 CoWoS 的紙箱笑話，可導流長片）
- `friday-deploy`
- `meeting-email`
- `yield-offwork`
- `hbm-stack`（等 HBM 長片做完再用 short-from-long 切）

冷笑話題目要等 R4 的 shorts_skit 渲染器，pm-yidiandian 另外要等 PM 狗的 rig（R11）。用 `produce.py plan --week 2026-W43` 驗證過，三個 offwork 時段都排得到題，但都會警告「only idea」。🟢

順手修了 `produce.py` 的錯誤處理：原本 YAML 語法錯會整段 traceback，現在印一行錯誤訊息。我自己寫的 backlog 第一版就踩到這個問題：`backlog: hbm` 裡的冒號。

## 6. 需要 Leon 決定

1. **兩個成片閘門**：看 `review/final.html` 或 `upload/manual/preview.html` 後 approve。兩支都是機器聲，README 已經寫明「這一版不要公開」。
2. **「一個數字」Shorts 放哪個頻道**：派工指定 offwork，但 `channels/chipcat.yaml` 的 shorts_strategy 和 chipcat 選題池原本都把它列成 chipcat 的 Short。offwork 的定位是冷笑話／上班族，數字解說放在 chipcat 可能比較一致。我先把 chipcat 那題改成 in_production 並加註，避免排片時重複排到。另外，offwork 的 package 會把類別帶成「喜劇」（依頻道 pipeline 決定），這支的內容比較像教育類。
3. **「變造或合成內容」要不要勾**：頻道設定 `ai_disclosure: true`，所以 README 建議勾「是」。但 YouTube 要求揭露的範圍是「看起來像真實」的內容；這支是解說投影片加卡通角色，不勾應該也不違規（🟡，依記憶中的政策，未重新查證）。
4. **CoWoS 的排程**：run-dir 沿用了上一輪驗證時寫的 `publish_at 2026-10-22T19:00+08:00`，README 上顯示的是「排程」。要改就用 `run --publish-at …` 覆寫。
5. s01、s20 的 B-roll 已標 claude-draft；s01 是 CG 渲染畫面，不是實拍晶片。

## 7. 測試

- `PYTHONPATH=<wt>/src .venv/bin/python -m pytest tests -q -p no:cacheprovider` → **1 failed, 1051 passed, 1 skipped**。失敗的是 `test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results`，基準就有（production-workflow 報告記錄的也是同一支）。worktree 裡沒有 `.env`（`ls .env` 回 No such file）；stock 改用 `--env-file` 指向主 checkout 的 .env。🟢
- 新增測試：
  - `test_production_shorts_cut.py` 15 項：時間窗、時間規劃、字幕平移與重排（含 16 字回歸）、SRT 來回轉換、script、spec 預設與未核可時拒切、runner 只走 cut 步驟與 final 閘門、直式字幕 QC（寬、高各有對照）、HTML escape、ASS 格式。
  - `test_production_manual_kit.py` 6 項：VTT、說明欄 escape 與章節連結、機器聲偵測（含 cache 回歸）、合成內容建議、完整 kit 檔案與 1280×720 縮圖、舊 meta 失效。
  - `test_production_qc.py` +1 項：AI 揭露。
- 改了一支既有測試：`test_explainer_brand_plumbing` 原本靠範例 deck 裡要有 ai_image 投影片，現在範例沒有了，改成在測試內自己造一張。
- `ruff check` 本次動到的檔案全部通過。🟢

## 8. 副作用與清理

- `output/cowos-chipcat/`（含 mascot 中間檔，數 GB）、`output/offwork-7722/`、`.cache/explainer_stock/`（從 cf-production-workflow 複製，另新增 3 支下載的 clip）：都在 gitignore 裡，沒有刪（`rm` 在 deny），留給 orchestrator。
- `~/.cache/content-farm/render.lock`：共用的渲染鎖檔，不需要處理。
- job tmp `/Users/lileon/.claude/jobs/802ba0f0/tmp/`：放了 `inspect_deck.py`、`stock_probe.py`（只查 API、不下載；跑第二個 provider 時 Pixabay 握手逾時，traceback 已確認是網路問題），以及幾張截圖原檔。job 刪除時會一起清掉。
- `PROGRESS-ch-chipcat-ep1.md`：進度紀錄，不 commit。
- 呼叫外部服務：只有 Pexels／Pixabay 的免費搜尋與下載（v4 允許）。沒有呼叫付費 TTS，沒有 AI 生圖，沒有開瀏覽器，沒有上傳。
- 沒有 push：分支 `feat/ch-chipcat-ep1` 不在放行的 `feat/LeonLi/*` 範圍內，v3 共同限制也寫了不 push。沒有動 main、`feat/explainer-v2`、`mascot/`。
