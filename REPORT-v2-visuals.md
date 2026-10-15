# REPORT — v2-C 畫面多樣化（動態投影片／素材庫 B-roll／AI 插圖／新聞標題卡）

## TL;DR

- 七項全部完成。分支 `feat/explainer-v2-visuals`，從 `3332fa4` 開出，共 4 個 commit，**未 push**。🟢
- 驗收：一份 6 張的 deck，四種 media 都有用到。依序跑 voice（macos_say）→ `media_to_visual` → `assembly_timeline`，產出 `draft.mp4`（2:04）。**blackdetect 是 0 段**（對照組：1 秒純黑片段會被偵測到，證明偵測器有效）。🟢
- pytest：基準 `1 failed, 733 passed`，完成後 `1 failed, 827 passed, 1 skipped`。唯一的失敗仍是既有的 `test_multi_provider…test_returns_first_provider_results`；skipped 的是 Pexels 實連測試（環境沒有 key 時跳過），另外用 key 單獨跑過一次，通過。🟢
- **`timeline_assembly.py` 一行都沒改**：它本來就能吃 mp4。改用測試把 PNG 和 Shorts 的行為釘住。`assembly/`、`pipeline/`、`run_stage.py`、`config.py`、`script_gen/` 對基準的 diff 都是空的。🟢
- AI 插圖還沒有實際的圖，所以驗收片裡是紅色的「AI 插圖待補」佔位圖，總覽圖上也有紅框標示。補圖的操作步驟在最後一節。

等級：🟢 本機實測可重跑；🟡 只驗到存在或讀碼推論；🔴 未驗證的判斷或估計。

## 前提偏差

- 派工時 worktree 的 HEAD 在 `6c47dd1`（`chore/wip-baseline-2026-10` 的 tip），不在 `3332fa4`。依共同背景的指示執行 `git checkout -B feat/explainer-v2-visuals 3332fa4`，之後 `git log --oneline -1` 顯示 `3332fa4 docs: macos_say TTS provider report`。🟢

## 位置

- worktree：`/Users/lileon/project/content-farm/.claude/worktrees/cf-v2-visuals`
- 分支：`feat/explainer-v2-visuals`（本機，未 push）

```
docs(explainer): v2 media in deck skill and acceptance example frames
feat(explainer): media_to_visual with animated slides, stock B-roll, AI image slots and title cards
feat(explainer): media field on slides with per-kind validation and lint rules
(+ 本報告與 CLAIMS 的 commit)
```

## 1. schema 的改動（`src/content_farm/explainer/deck.py`）🟢

- `Slide.media: Media | None`，沒有填時視為 `slide`。`Media` 是 frozen 且 `extra="forbid"`，欄位依介面約定：`kind / query / prompt / animation / headline / source_id`。另外加了一個選填的 `summary`，給 title card 放一句摘要用，因為約定的欄位裡沒有地方放這句。
- 每種 kind 的必填欄位由 validator 檢查：`title_card` 要 `source_id`，`stock` 要 `query`，`ai_image` 要 `prompt`，`animated` 要 `animation`。少了就報 `media kind 'stock' requires 'query'`。
- `Deck` 層的交叉檢查：`media.source_id` 必須存在於 `sources`。
- 動畫和版型的相容表 `ANIMATION_LAYOUTS`，不相容就報錯（例如 `count_up` 只能用在 big_number）。每種版型另有預設動畫 `DEFAULT_ANIMATION`，stock 退回時用這個。
- `Source` 新增兩個選填欄位：`publisher`（媒體名）和 `published`（`YYYY-MM[-DD]`），title card 會用到。
- **lint**（`lint.py`）新增三條：
  - `plain-slide-run`：連續 3 張以上是純 `slide`。
  - `footage-share`：`stock` 加 `ai_image` 少於 20%。
  - `title-card-meta`：title card 引用的來源缺少 publisher 或 published。
- **to_script**：media 會帶進 `Scene.visual_hint`，timeline 工具讀得到：
  - `style` 填 media kind（沒有 media 時仍是 `"slide"`，和 v1 相同）。
  - stock 的 query 放進 `keywords`。
  - `source_preference` 填 `stock` 或 `ai`。
  - `description` 維持 `layout:id`，後面加上 `|<動畫名 / prompt / source:id>`。
- `Script` schema 本身沒有改。
- 測試：`tests/unit/test_explainer_media_schema.py`，28 個。

## 2. 四種 media 的做法

整體流程：`scripts/media_to_visual.py` 會呼叫 `explainer/media_run.py`，再由 `explainer/media.py` 依 kind 分派。每張投影片產出的片段長度剛好等於它在時間軸上的 slot（取整到 frame 時往上取，所以只會由 assembly 剪掉多的部分，不會不夠長）。整次執行只開一個 headless Chromium（`explainer/capture.py`）。

### animated（動態投影片）🟢

- 動畫 runtime 是 `templates/animate.js`，**時間是參數，不是時鐘**。頁面載入後停在最終狀態，capturer 對第 i 格呼叫 `__anim.seek(i/30)` 後才截圖，所以機器快慢不影響結果。測試證明：同一個 t 截兩次，像素 md5 相同。
- 只擷取動畫本身的格數（`ceil(動畫秒數×30)+1`），之後用 ffmpeg 的 `tpad=stop_mode=clone` 把最後一格撐到 slot 結束。
- 動畫種類：
  - `count_up`：數字從 0 跳到目標值，支援小數和千分位。
  - `grow_bars`：big_number 下方加一條會長出來的比例條（單位是 % 時填到該比例）；compare 的兩欄由下往上長出；bullets 每一條橫向長出。
  - `reveal_list`：bullets、compare、timeline 的項目逐條淡入上移。
  - `draw_line`：timeline 的線由左往右畫，線畫到哪個事件點，那個事件才出現。
  - `fade_in`：所有版型都能用，title 和 quote 預設用這個。
- 六種版型都有進場動畫可用。動畫最後一格會跑一次原本的溢出檢查，有問題時寫進 report 的 `problems`。

### stock（素材庫 B-roll）🟢

- `explainer/stock.py`：先查 Pexels，沒有合適的再查 Pixabay。
- 「合適」的條件：橫式、長寬比至少 1.6、寬度至少 1280。排序依序是：寬度到 1920 優先 → 長度夠用（只需要剪掉或放慢，不必循環）優先 → 越長越好。
- 檔案版本：Pexels 選「至少 1920 寬」裡最小的那一版，避免抓 4K；Pixabay 的 `large` 通常是 4K，所以改挑 `medium`。
- 長度處理（`ffmpeg_ops.stock_to_clip`）：先 cover-crop 成 1920×1080。素材比 slot 長就剪掉；短但差距在 1.5 倍以內就放慢（`setpts`）；差更多就循環播放（`-stream_loop`）。
- 疊字：用 HTML 截一張透明 PNG 疊上去。內容是上方的頂欄、左下的 lower-third（大標加一行重點，重點和標題相同時省略）、meta 列（來源／資料截至／非投資建議）。全部在 y < 880 的範圍內，不會壓到字幕；吉祥物要用的右下角也空著。
- **快取**：存在 `.cache/explainer_stock/<slug>-<sha1>/{meta.json, video.mp4}`。同一個 query（不分大小寫、空白正規化後相同）不會再查也不會再下載。驗收第二次執行時兩段都顯示 `(cache)`，而且有了快取就不需要 key。
- **使用條款與頻率限制**（2026-10 從兩邊的官方文件讀到的原文，🟢）：
  - Pexels：預設每小時 200 次、每月 2 萬次；要「顯著連結 Pexels、盡量標示創作者」；禁止繞過頻率限制。我們的做法：每次呼叫至少間隔 1 秒；每次執行每個供應商最多 60 次；看到 `X-Ratelimit-Remaining: 0` 或 429 之後，本次執行就不再呼叫該供應商；key 只放在搜尋請求的 `Authorization` header，下載檔案時不帶（有測試）。
  - Pixabay：每 60 秒 100 次；請求必須快取 24 小時；不可永久盜連，要先下載。我們的快取是永久的，檔案也一律下載到本機，`safesearch=true`。
- **退回**：沒有 key、HTTP 錯誤、沒有合適結果、超過頻率或次數上限、ffmpeg 失敗時，都會退回成 animated（用該版型的預設動畫）。原因寫進 `media/media_report.json` 的 `note`（例如 `FALLBACK stock→animated: no footage for 'x' (pexels: …; pixabay: …)`），總覽圖上以紅框加「退回 animated」標示。

### ai_image（AI 插圖）🟢（佔位圖這條路徑）／🟢（Ken Burns 只在測試裡驗證）

- 程式完全不開瀏覽器。`media_to_visual` 每次執行都會寫出：
  - `ai_image_prompts.md`：格式和現有的 `storyboard_prompts.md` 相同，`generate_visuals.py` 的 parser 可以直接讀，有測試證明。
  - `ai_image_prompts.json`：機器讀的版本。
- 檔名規則：`<run_dir>/assets/ai_images/<slide_id>.png`，也接受 `.jpg/.jpeg/.webp`。沒有完全同名的檔案時，取 Gemini 多圖下載的 `<slide_id>_01.png`、`_02.png`… 裡編號最小的。
- 有圖時：用 zoompan 做 Ken Burns，從 1.00 緩慢推近到 1.10。推近前先放大到 2 倍，避免 zoompan 抖動。上面疊和 stock 相同的 lower-third。credits 會記一筆 `kind: ai_image`。
- 沒有圖時：放紅色虛線框的佔位圖，上面寫「AI 插圖待補」、標題、應該放檔案的位置和 prompt。report 標 `placeholder: true`，總覽圖上紅框標示。
- `scripts/generate_visuals.py` 新增 `--storyboard` 和 `--out-dir` 兩個參數，預設值和原本的行為相同。

### title_card（新聞標題卡）🟢

- 模板是 `templates/media/frame.html.j2` 加 `media.css`，配色沿用 deck 的主題 CSS。
- 卡片內容：媒體名（橘色標籤）、日期、標題、一條會畫出來的分隔線、一句摘要、`來源編號 <source_id> · 網域`、「頻道自製重點卡・非新聞截圖」。
- 欄位來源：媒體名取 `source.publisher`，沒有就用網域，再沒有就顯示「媒體待補」；日期取 `source.published`，沒有就顯示「日期待補」；標題取 `media.headline`，沒有就用 `source.title`；摘要取 `media.summary`，沒有就用投影片的重點句。
- 有進場動畫（卡片上浮、分隔線畫出），擷取方式和 animated 相同。**沒有使用任何新聞截圖。**

## 3. 轉場 🟢

- 參數：`--transition crossfade|push|fadeblack|none`，`--transition-seconds`。預設 crossfade、0.4 秒。允許的秒數範圍是 0.1–1.0（驗證失敗會報錯）。建議值 0.3–0.5，寫在 skill 裡。
- 做法（`media_run.apply_transitions`）：取第 N+1 段的第一格，用 xfade 把第 N 段的最後 0.4 秒漸變到這一格。第 N+1 段本來就從這一格開始，所以接縫是連續的，而且每個 slot 長度不變。**因此 assembly 不需要支援 xfade**，這也是 assembly 可以不改的原因。
- 有測試確認三種轉場的長度都不變，且最後一格就是下一段的第一格。
- `none`：完全不做處理。純 `slide` 會維持 PNG，和 `render_slides` 的輸出 md5 完全相同（有測試），等於 v1 的行為。

## 4. assembly 的改動範圍 🟢

- **`src/content_farm/assembly/timeline_assembly.py` 沒有改**。原本的 `_TIMELINE_RE` 和 `_normalize_clip` 就支援 `.mp4`：會剪成目標長度、去掉音軌、縮放到目標尺寸。
- 需要的改動放在 explainer 這一側：
  - `timeline.SlideClip.filename_for(suffix)`
  - `timeline.place_files(clips, sources, visual_dir, replace)`：每個 slot 依來源檔決定副檔名是 `.png` 或 `.mp4`；visual/ 裡已有 timeline 檔時拒絕執行，除非加 `--replace`，規則和 `place_slides` 相同。
  - `place_slides` 改成呼叫 `place_files`。
  - `resolve_durations` 從 `scripts/slides_to_visual.py` 移到 `timeline.py`，兩支 script 共用。
- 新寫 `scripts/media_to_visual.py`。`slides_to_visual.py` 保留，PNG-only 的流程照舊。
- 防止回歸的測試在 `tests/unit/test_assembly_timeline_media.py`：
  - PNG 的 ffmpeg 參數逐字釘死。
  - mp4 的參數。
  - 預設 orientation 仍是直式 1080×1920（Shorts）。
  - 用真的 ffmpeg 組一支「PNG、mp4、PNG」混合的片：總長 3.0 秒、沒有黑幀、沒有產生 gap filler。
- 既有的 assembly、Shorts 測試全部照過。

## 5. 授權紀錄格式（`<run_dir>/credits.json`）🟢

```json
{
  "version": 1,
  "title": "<deck.title>",
  "generated_at": "2026-10-14T17:20:23+00:00",
  "entries": [
    {"slide_id": "s03", "slide_index": 3, "kind": "stock", "query": "factory production line",
     "provider": "pexels", "provider_id": "30288953",
     "source_url": "https://www.pexels.com/video/motorcycle-factory-production-line-overview-30288953/",
     "download_url": "https://videos.pexels.com/video-files/30288953/12984266_1920_1080_25fps.mp4",
     "author": "Emrul Kausar Emon", "author_url": "https://www.pexels.com/@emrulkausar",
     "license": "Pexels License", "license_url": "https://www.pexels.com/license/",
     "resolution": "1920x1080"},
    {"slide_id": "s04", "slide_index": 4, "kind": "ai_image", "file": "s04.png",
     "license": "AI-generated (Gemini) for this channel", "prompt": "…"}
  ],
  "description_text": "影片素材 / Stock footage:\n- Emrul Kausar Emon on Pexels: https://… (Pexels License)\nVideos provided by Pexels — https://www.pexels.com"
}
```

- `description_text` 可以直接貼進影片說明欄。有 Pexels 素材時會附上 Pexels 連結（Pexels 指南要求），有 Pixabay 素材時附上 Pixabay 連結。
- 上面那筆 `ai_image` 是有圖時才會出現的格式。這次驗收片裡沒有 AI 圖，所以實際的 credits 只有兩筆 stock。
- 完整實例：`docs/examples/explainer-v2-visuals/credits.json`。

## 6. 驗收與截圖

驗收用的 deck 是 `docs/examples/explainer-v2-visuals/deck.json`，從 `explainer-tsmc` 複製後替每張配上 media：

| # | 版型 | media | 實際使用 |
|---|---|---|---|
| 1 | title | stock `semiconductor wafer` | stock（pexels:6754834） |
| 2 | big_number | animated `count_up` | animated |
| 3 | compare | stock `factory production line` | stock（pexels:30288953） |
| 4 | bullets | ai_image | ai_placeholder（沒有圖） |
| 5 | timeline | animated `draw_line` | animated |
| 6 | quote | title_card `pledge` | title_card |

執行順序（run_dir 是 `output/v2-visuals-accept`，在 gitignore 裡，沒有 commit）：

```bash
PYTHONPATH=$PWD/src .venv/bin/python scripts/deck_to_script.py --run-dir output/v2-visuals-accept
PYTHONPATH=$PWD/src .venv/bin/python scripts/render_slides.py  --run-dir output/v2-visuals-accept
CF_TTS_PROVIDER=macos_say CF_ANTHROPIC_API_KEY=dummy-unused PYTHONPATH=$PWD/src \
  .venv/bin/python scripts/run_stage.py --stage voice --run-dir output/v2-visuals-accept
PYTHONPATH=$PWD/src .venv/bin/python scripts/media_to_visual.py --run-dir output/v2-visuals-accept \
  --env-file /Users/lileon/project/content-farm/.env
CF_TTS_PROVIDER=macos_say CF_ANTHROPIC_API_KEY=dummy-unused PYTHONPATH=$PWD/src \
  .venv/bin/python scripts/run_stage.py --stage assembly_timeline --run-dir output/v2-visuals-accept
ffmpeg -i output/v2-visuals-accept/assembly/draft.mp4 -vf blackdetect=d=0.05:pix_th=0.10 -an -f null -
```

- blackdetect：`black_start` 出現 **0 次**。對照組：`color=c=black:d=1` → `black_start:0 black_end:0.96`。🟢
- `draft.mp4`：1920×1080，影像 123.77 秒，音訊 124.06 秒。🟢

截圖（從 `draft.mp4` 擷取，每種 kind 一張，加上一張轉場中的畫面），在 `docs/examples/explainer-v2-visuals/`：

| kind | 檔案 | 內容 |
|---|---|---|
| stock | `frame_stock_s03.png` | 工廠產線 B-roll，左下 lower-third，meta 列，燒入的字幕 |
| animated | `frame_animated_s02_countup.png`、`frame_animated_s05_mid.png` | 數字跳到 48（目標 59）；時間軸線畫到一半 |
| ai_image | `frame_ai_image_placeholder_s04.png` | 紅框的「AI 插圖待補」佔位圖 |
| title_card | `frame_title_card_s06.png` | 示意媒體、2026-10、標題、摘要、source_id |
| 轉場 | `frame_transition_s03_s04.png` | stock 畫面淡入佔位圖的中間格 |
| 總覽 | `contact_sheet.png` | 第 4 張有紅框和「AI 圖待補」標籤 |

## 7. 效能 🟢（6 張、片長 2:04、M 系列 Mac）

| 步驟 | 耗時 |
|---|---|
| `media_to_visual`，第一次（含 Pexels 搜尋與下載） | 121.2 s |
| `media_to_visual`，第二次（全部走快取） | 113.9 s |
| └ 每張片段 | stock 8.7 / 12.8 s，animated 7.8 / 11.6 s，佔位圖 6.9 s，title card 8.0 s |
| └ 轉場（5 段 xfade，每段整支重新編碼） | 約 58 s |
| 動畫擷取 | 約 0.1 s/格（1920×1080 PNG 截圖） |
| `assembly_timeline`（沒改） | 63.5 s |
| pytest 新增的測試 | 約 70 s（其中瀏覽器測試 44 s） |

- 推估 25 張、9 分鐘的片：`media_to_visual` 大約 6–8 分鐘（🔴 線性外推）。
- 最大的優化空間在轉場：現在每段都整支重新編碼，其實只要重新編碼最後約 0.5 秒再接回去就好。我沒有做，因為那需要處理 GOP 和 concat 對齊，風險比收益大。

## 8. AI 插圖之後怎麼補齊（給使用者的操作步驟）

1. 先跑一次 `media_to_visual.py`，它會在 run_dir 寫出 `ai_image_prompts.md`。每張 ai_image 投影片對應一個 `### Shot N — \`<slide_id>.png\``，prompt 結尾會自動加上「16:9、不要文字或 logo、下方三分之一保持乾淨」。
2. 照現有的 generate-visuals 流程打開 Chrome：`bash scripts/launch_chrome_debug.sh`，第一次需要登入 Google。
3. 產圖：
   ```bash
   .venv/bin/python scripts/generate_visuals.py --run-dir output/<run> --variant 0 \
     --storyboard ai_image_prompts.md --out-dir assets/ai_images --cdp-port 9222
   ```
   圖會存成 `output/<run>/assets/ai_images/<slide_id>.png`；Gemini 回多張時存成 `_01.png`、`_02.png`…。
4. 挑圖：把要用的那張改名成 `<slide_id>.png`。不改名的話會自動取 `_01`。也可以直接放自己的 `.png/.jpg/.webp`，檔名相同就行。
5. 重跑 `media_to_visual.py --run-dir output/<run> --replace`。stock 會走快取，不會重新下載。接著重跑 `assembly_timeline`。
6. 看 `media/contact_sheet.png`，紅框應該消失；`media/media_report.json` 裡那張的 `used` 會變成 `ai_image`。

> 依共同限制，我沒有開 Chrome，也沒有呼叫 Gemini。Gemini 產出的圖能不能用在有營利的 YouTube 頻道、要怎麼標示，我沒有查證（🔴）。credits 只寫了 `AI-generated (Gemini) for this channel`，發布前請確認 Google 的條款。

## 已知限制與觀察

- 🟡 素材的切題程度要靠 query 寫得好：`semiconductor wafer` 抓回來的是主機板特寫。沒有人工挑片的步驟，替代方式是看總覽圖，不滿意就換 query 再加 `--replace` 重跑。換了 query 才會重新搜尋，因為快取是以 query 為 key。
- 🟡 `full.mp3`（124.06 s）比各段 `scene_NNN.mp3` 加總（123.749 s）長 0.31 s，所以影像比音訊早 0.3 s 結束，播放器會停在最後一格（不是黑畫面）。這是 voice 串接本來就有的狀況，和本任務無關，我沒有去改。
- 🟡 素材庫的畫面不是台灣在地的，產業特寫的題材也有限。適合當氛圍 B-roll，不適合當證據畫面。
- 🔴 新聞卡的標題和摘要是人寫進 deck 的，程式不會檢查內容是否忠於原報導。lint 只檢查 publisher 和 published 有沒有填。
- 和角色 worker 的關係：lower-third 放在左側、y < 820，右下角留給吉祥物；`timeline_assembly.py` 沒動，兩邊不會衝突。

## 清理與副作用

- `output/v2-visuals-accept/`：驗收用的 run，在 gitignore 裡，保留給你看 `draft.mp4`。
- `.cache/explainer_stock/`（worktree 內，在 gitignore 裡）：2 段 Pexels 素材的快取。
- `PROGRESS-v2-visuals.md`：進度紀錄，**沒有 commit**，留在 worktree 裡沒刪（`rm` 是禁止的），可以直接刪掉。
- `/Users/lileon/.claude/jobs/09dd501d/tmp/`：冒煙測試的輸出和小工具腳本，job 刪除時會一起清掉。
- 沒有把 `.env` 複製進 worktree：stock key 是用 `--env-file` 直接讀主 checkout 的 `.env`；voice 用 `CF_ANTHROPIC_API_KEY=dummy-unused`。
- 沒有 push；沒有動 main、`chore/wip-baseline-2026-10`、`feat/explainer-mvp` 和它的 worktree；沒有 commit `.env`、`output/`、`data/curriculum_map/`。
