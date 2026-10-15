# 三條開台分支整合（feat/channels-integrate）

## TL;DR
- `feat/channels-integrate`（從 `d9749c1` 開）依序 merge 了 chipcat、yokai、cel 三條分支。三份報告都保留，CLAIMS 換成本 job 的版本。沒有 push。🟢
- 三份 `produce.py manual-kit` 已合成一份實作，對照表在 §2。三份分支原本的 21 支測試全部保留或併入同一支（去重後 16 支），另新增 4 支，共 20 支，都對同一份實作跑。新增參數 `--out`、`--voice`、`--playlist`、`--thumbnail-at`。🟢
- AI 揭露改成依實際內容產生：AI 圖看 credits，沒有 credits 才看 deck；合成語音看 voice.log。兩樣都沒有時不寫揭露句，`contains_synthetic_media` 也設為 false。cel 那句「部分插圖」已經消失。🟢
- 四份上傳包重新產生在 `output/kit-check/<name>/`，原本的 run-dir 沒有動。影片相對路徑和絕對 `file://` 備援都實測能解析到檔案。🟢
- pytest：1 failed / 1081 passed / 1 skipped。唯一失敗的是基準就有的 `test_multi_provider…returns_first_provider_results`。🟢

## 1. merge 過程與衝突處理

| 步驟 | commit | 衝突 | 處理 |
|---|---|---|---|
| 建分支 | `d9749c1` | — | `git log --oneline -1` → `d9749c1 chore: claims for production workflow`。worktree 原本在 `worktree-cf-channels-integrate`（`6c47dd1`），乾淨，從那裡 `checkout -b` |
| merge chipcat（`8339e4a`） | `2a366e8` | 無 | — |
| merge yokai（`7e0f848`） | `24e13c1` | CLAIMS.jsonl、scripts/produce.py、manual_kit.py（add/add）、publish.py、test_production_manual_kit.py（add/add）、test_production_qc.py | merge commit 先取 chipcat 側。test_production_qc.py 只解衝突那一行，yokai 新增的 artwork 政策測試和揭露測試保留。yokai 的 `preview.py` 照原樣進來，在下一個 commit 併掉 |
| merge cel（`4af1931`） | `a11a71c` | CLAIMS.jsonl、produce.py、manual_kit.py、test_production_manual_kit.py | 同上。cel 的 `manual_readme.py`、`manual_preview.py` 照原樣進來，在下一個 commit 改寫 |
| 合一 | `0a316cd` | — | 見 §2、§3 |

- 三份報告檔名不同，直接並存：`REPORT-ch-chipcat-ep1.md`、`REPORT-ch-yokai-ep1.md`、`REPORT-ch-cel-ep1.md`。
- 其他非 manual-kit 的內容都是自動合併，CLAIMS 裡用 blob_equal 驗證原樣進來：yokai 的 artwork 媒體種類（qc 政策、steps inputs、ffmpeg `artwork_plate`）、Commons 抓圖腳本、chipcat 的 short-from-long／shorts_cut／portrait QC、cel 選題池與 `test_production_schedule` 修正。
- 注意：兩個 merge commit 本身的測試**不是全綠**。那時 yokai 的揭露測試對的是 chipcat 的 publish.py，cel 的 manual_readme 也 import 不到 `KitInfo`。到 `0a316cd` 才一致。如果要 bisect，請跳過這兩個 merge commit。

## 2. manual-kit 三份差異對照表 → 採用

| 項目 | chipcat（8339e4a） | yokai（7e0f848） | cel（4af1931） | 採用 |
|---|---|---|---|---|
| 檔案切分 | manual_kit.py＋jinja `preview.html.j2` | manual_kit.py＋preview.py（f-string） | manual_kit.py＋manual_readme.py＋manual_preview.py | cel 的三檔切分，加上 chipcat 的 jinja 模板（autoescape）。yokai 的 `preview.py` 刪除 |
| meta 來源／預覽版判定 | youtube_meta.json **只在 gate_final 核可「目前」成片（fingerprint 相符）時**採用，否則用 build_meta 產生預覽（有回歸測試） | 有 youtube_meta.json 就用。gate 狀態只看 `status=="approved"`，不比對 fingerprint | 有 youtube_meta.json 就用，不看 gate | **chipcat**。另兩份會把舊 render 留下的 meta 當成正式版 |
| 機器聲偵測 | 看最後一次「實際合成」的 provider（略過 Reusing）；Short 會追到長片的 run（有回歸測試） | log 裡出現 macos_say 字串就判定是機器聲 | 同 yokai，另有 `--voice auto|machine|fish` 覆寫 | chipcat 的偵測（抽成 `voice_source.py`，publish 也會用），加上 cel 的 `--voice` 覆寫。覆寫時狀態列的配音名稱也跟著改 |
| README 欄位 | 依 Studio 順序；標題字數；播放清單（寫死對照表）；章節數；Shorts 專屬的片尾說明；預覽版警告 | 依 Studio 順序；**先切頻道**；成片閘門狀態行；**授權／允許嵌入**；Content ID 有聲明就停 | 依 Studio 順序；狀態區（配音、QC、metadata 來源）；**「先處理」警告區**（標題 >100、標籤 >500、QC error）；章節列表；檔案清單；**提醒字幕已燒入，開 CC 會疊兩層** | 以 cel 的結構為底，加入 yokai 的切頻道、授權、Content ID，以及 chipcat 的 Shorts 分支（相關影片指向 short_source 的長片標題）和預覽版警告。警告區新增「直式 >60 秒」和「沒有 srt」兩項 |
| Studio「變造或合成內容」建議 | 依 flag；說明 YouTube 只要求擬真內容才需揭露 | 依 flag | 依 flag 和配音來源；標 🟡 | chipcat 的說法加上 cel 的 🟡。flag 現在依實際內容而定（§3） |
| 標題超過 100 字 | raise | 截成 100 字 | README 警告 | raise。截斷會默默改掉標題，警告又容易被略過 |
| 縮圖 | Short 用 `short/intro.png`（1080×1920）；長片用 `slides/slide_001.png`；超過 2MB 就 raise | 取影片第 N 秒畫格（`--thumbnail-at`）；PNG 超過 2MB 改存 JPEG | meta.thumbnail_path → slide_001；超過 2MB 先 quantize；附來源說明 | 指定 `--thumbnail-at` 時直接取該秒畫格。否則依序找 meta.thumbnail_path → Short 的 intro.png → slide_001，都沒有才取影片畫格。cover-crop 到 1280×720，直式為 1080×1920。檔案超過 2MB 時依序改成 quantize PNG、再改 JPEG。README 和預覽頁都附來源說明 |
| srt→vtt | 用 parse_cues 重排（丟掉 cue 編號） | 用 regex 換逗號（保留編號） | 同 yokai | regex，不會遺失內容 |
| 字幕在 file:// 下的載入 | VTT 內嵌在頁面，用 Blob URL 掛到 `<track>` | cue 以 JSON 內嵌，用 `addTextTrack`＋`VTTCue` | `<track src="subtitles.vtt">` | **yokai**：完全不需要 fetch。Chrome 在 file:// 下會擋 `<track src>`，所以 cel 的寫法在 Chrome 不會顯示字幕；Blob URL 仍要經過一次 fetch。🟡 沒開瀏覽器驗證（依指示不開），四份頁面內嵌的 cue 數都和 srt 一致（135/150/7/144） |
| 9:16 判定 | `short_source.json` 是否存在 | channel aspect 是否為 9:16 | channel aspect 是否為 9:16 | **用 ffprobe 量實際寬高**。三份的依據都是間接的。probe 失敗時退回「short_source 或 channel aspect」 |
| preview 版面 | 淺／深色跟隨系統；狀態列、章節框、標籤、設定 dl、縮圖 | 深色；縮圖和設定並排；說明欄內的章節可點 | 深色；兩欄 grid；章節框；縮圖來源說明；上傳設定含影片絕對路徑 | chipcat 模板（淺／深色）加上 cel 的兩欄、縮圖說明、播放清單和影片路徑兩列 |
| 狀態列 | 配音、QC、片長、檔案、預覽版 | 同左（片長 M:SS） | 同左，另加 metadata 來源 | 合併。片長同時顯示 M:SS 和秒數；QC 分成 error、warn、ok 三色 |
| 影片路徑 | 相對 | 相對 | 相對 | 相對路徑的 `<source>`，加上絕對 `file://` 的備援 `<source>` |
| 輸出位置 | 固定 `upload/manual/` | 同左 | 同左 | 新增 `--out`，預設不變 |
| 播放清單 | 寫死對照表 | `--playlist` | channel.line | 依序取 `--playlist` → 對照表 → channel.line |
| 影片不存在／不是影片 | ffprobe 例外 | FileNotFoundError | FileNotFoundError；ffprobe 失敗就退回 meta 的片長 | cel |
| tags.txt 分隔 | `,` | `,` | `, ` | `, `（Studio 會去掉空白；cel 的測試有斷言） |

### 測試對照（全部對 `content_farm.production.manual_kit` 同一份實作）

| 原測試 | 現在 |
|---|---|
| chipcat `test_srt_to_vtt` ＋ cel `test_srt_to_vtt` | 併成 `test_srt_to_vtt`（期望值改為保留 cue 編號） |
| chipcat `test_description_html_…` | 保留（改用 `manual_preview.description_html`） |
| chipcat `test_machine_voice_follows_the_last_synthesis…` ＋ yokai `test_voice_is_machine_reads_voice_log` | 併成同一支，對 `voice_source` |
| chipcat `test_synthetic_advice_follows_the_flag` | 保留（`manual_readme.synthetic_advice`） |
| chipcat `test_write_kit_builds_every_file…` ＋ cel `test_kit_writes_every_file_with_title_slide_thumbnail` | 併成同一支（檔案清單、title/description/tags 內容、1280×720） |
| chipcat `test_packaged_meta_counts_only_while_the_final_approval_matches` | 保留。**cel 的 `test_package_meta_is_preferred_over_rebuilding` 由這支取代**：cel 斷言「有 meta 就採用、不是預覽版」，正是 chipcat 修掉的 bug。改成先核可才採用，並在同一支裡斷言 README 不再有預覽警告 |
| yokai `test_kit_files_and_readme` | 保留（另斷言授權、Content ID） |
| cel `test_readme_flags_machine_voice_first…` | 保留（`test_readme_lists_status_and_studio_fields`，另斷言「先處理」區） |
| yokai `test_real_voice_has_no_machine_banner` ＋ cel `test_fish_voice_override_drops_banner` | 併成 `test_fish_voice_has_no_machine_banner` |
| yokai `test_thumbnail_is_1280x720_under_2mb` ＋ cel `test_missing_thumbnail_source_is_an_error` | 拆成兩支：`test_thumbnail_falls_back_to_a_video_frame`（沒有投影片時改取畫格）和 `test_fake_video_without_title_slide_is_an_error`（連畫格都取不到才報錯） |
| yokai `test_preview_is_offline_and_escaped` | 保留 |
| cel `test_preview_is_offline_relative_and_escaped` | 保留（`<track>` 斷言改成章節數、無遠端 `<source>`） |
| yokai `test_shorts_use_portrait_player` | 改成 `test_portrait_video_gets_shorts_player_on_any_channel`：用直式影片配 yokai 頻道，證明判定是看影片本身 |
| cel `test_vertical_channel_gets_vertical_player` | 保留，現在測的是 probe 失敗時的退路 |
| cel `test_no_video_is_an_error` | 保留 |
| 新增 | `test_short_cut_reads_the_voice_of_its_long_run`、`test_thumbnail_at_uses_that_frame`、`test_title_over_100_chars_is_an_error`、`test_out_dir_keeps_the_run_untouched_and_the_video_reachable` |

（`0a316cd` 的 commit 訊息寫成「20 + 3 new」，那是算錯的，以這裡為準。）共 20 支：原有 21 支（chipcat 6、yokai 6、cel 9）去掉 5 組重複後剩 16 支，再加上新增的 4 支（`test_title_over_100…` 是替 chipcat 原有的行為補測試）。`tests/unit/test_production_manual_kit.py` 20 passed。🟢

## 3. AI 揭露修正

- 原本的狀況：chipcat 和 yokai 各自改過 `ai_disclosure_line(credits)`，但寫法不同。credits 不存在時，chipcat 寫「只有配音」，yokai 寫「完整句」；常數名稱也不同。cel 分支沒改，所以 cel 的說明欄寫了「配音與部分插圖為合成內容」，但這支片根本沒有 AI 圖。
- 現在的規則（`publish.synthetic_content` → `SyntheticContent(voice, images)`）：
  - **AI 圖**：看 credits.json 的 entries 和 pending（佔位也算）裡有沒有 `ai_image`。沒有 credits 時看 deck.json 的 media kind。兩者都沒有時視為有，寧可多揭露也不要漏揭露。
  - **合成語音**：voice.log 裡有 TTS provider 合成過，就算合成語音；Short 會追到長片的 log。完全沒有 log 時也視為合成，因為所有 provider 都是 TTS。只有「log 存在、但從沒記錄過合成」（例如手動放入的錄音）才算非合成。
  - 文字依組合決定：
    - 兩者都有：「配音為合成語音；部分插圖為 AI 生成」
    - 只有語音：「配音為合成語音；畫面無 AI 生成圖像」
    - 只有圖：「部分插圖為 AI 生成；旁白非合成語音」
    - 都沒有：不寫揭露句。
  - `contains_synthetic_media` 改成「頻道 `ai_disclosure` 為 true，且內容至少有一項合成」。
- 測試在 `test_production_qc.py`，原本的兩支換成以下四支：credits→deck→預設、voice log、四種組合的文字、cel 情境的 build_meta 整合測試（stock＋macOS say 時只寫語音句；拿掉 TTS 後不寫句子、flag 為 false）。🟢
- 實測四份新上傳包的 description.txt，都是「配音為合成語音；畫面無 AI 生成圖像」。對照組：cel 原 run-dir 的舊上傳包仍有「部分插圖」（grep 命中），新包沒有。🟢
- 措辭是否合適請 Leon 看一眼：例如要不要點名 provider，或「畫面無 AI 生成圖像」要不要寫出來。這屬於品味判斷，沒有可驗證的標準。🟡

## 4. 四份新上傳包

指令：`python scripts/produce.py manual-kit --run-dir <原 run-dir> --out output/kit-check/<name>`。沒有重跑渲染和配音。

| name | 路徑（本 worktree） | 影片 | 播放器 | 縮圖 | 字幕 cue |
|---|---|---|---|---|---|
| cowos-chipcat | `output/kit-check/cowos-chipcat/` | `cf-ch-chipcat-ep1/output/cowos-chipcat/assembly/final.mp4` | 16:9 | 1280×720（標題投影片） | 150/150 |
| offwork-7722 | `output/kit-check/offwork-7722/` | `cf-ch-chipcat-ep1/output/offwork-7722/assembly/final.mp4` | 9:16 | 1080×1920（Short 片頭頁） | 7/7 |
| yokai-kyubi | `output/kit-check/yokai-kyubi/` | `cf-ch-yokai-ep1/output/yokai-kyubi/assembly/draft.mp4` | 16:9 | 1280×720（標題投影片） | 144/144 |
| cel-ep1 | `output/kit-check/cel-ep1/` | `cf-ch-cel-ep1/output/cel-ep1/assembly/draft.mp4` | 16:9 | 1280×720（標題投影片） | 135/135 |

- 四份都標示「成片閘門未核可：預覽版」和「暫用機器聲」。四個 run 的 gate_final 都還沒核可，配音也都是 macOS say。
- **影片路徑**：preview.html 有兩個 `<source>`。第一個是相對路徑，例如 `../../../../cf-ch-cel-ep1/output/cel-ep1/assembly/draft.mp4`；第二個是絕對 `file://` URI。我寫了一支檢查腳本，從各 preview.html 的位置解析這兩條路徑，四份都解析到同一個存在的影片檔。相對路徑只在兩個 worktree 都還在時有效；kit 被搬走時，瀏覽器會自動改用第二個絕對路徑。沒有複製或連結影片。🟢（路徑解析）／🟡（實際在瀏覽器播放沒驗，依指示不開瀏覽器）
- **原 run-dir 沒有被寫入**：用 `find -newer` 查四個 run-dir，零命中。對照組用同一條指令查本 worktree 的 kit-check，有命中，證明這個查法有效。🟢
- `output/` 在 .gitignore 裡，這些檔案沒有 commit。

## 5. 測試結果

`PYTHONPATH=<worktree>/src .venv/bin/python -m pytest -q -p no:cacheprovider tests`（worktree 裡沒有 .env）：

```
FAILED tests/unit/test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results[asyncio]
1 failed, 1081 passed, 1 skipped, 1 warning in 67.89s
```

唯一的失敗是基準就有的那支（`assert 2 == 1`）。🟢

## 6. 還沒整合的東西

- **`feat/mascot-route-a2`（`28bf4e7`）沒有 merge**，依指示也沒碰 `src/content_farm/explainer/mascot/`（CLAIMS 用 blob_equal 驗證 overlay、params、motion 與 d9749c1 相同）。用 `git merge-tree --write-tree HEAD feat/mascot-route-a2` 試合併（不動工作樹），唯一的衝突是 `CLAIMS.jsonl`，程式碼不會衝突。🟢
- `feat/explainer-v2`、`feat/explainer-mvp`、main 都沒有動。
- 這次沒有處理、留給後續的：
  - 品牌縮圖產生器（R2）。四份縮圖目前仍是標題投影片或 Short 片頭頁。
  - Fish Audio 換掉之後，要先重跑 voice 之後的步驟，再重跑 `manual-kit`；也可以用 `--voice fish` 只改標示。
  - 三份分支報告裡要 Leon 決定的事項維持原狀，沒有重新評估：成片閘門、「一個數字」Shorts 放哪個頻道、Studio 的合成內容要不要勾、排程。

## 7. 清理

- 暫存檢查腳本：`~/.claude/jobs/10a0c7b9/tmp/check_kits.py`，在 job tmp 裡，job 刪除時會一起清掉。
- `output/kit-check/` 是交付物，保留，沒有 commit。
- 沒有建立臨時分支，沒有用 stash。
