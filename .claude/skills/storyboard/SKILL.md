---
name: storyboard
description: Generate storyboard prompt variants from script.json, optimized for retention. Short-form → 3 variants × 8-14 portrait shots. Long-form → 1-2 variants × 40-60 landscape shots with chapter alignment.
allowed-tools: Read, Write, Glob
argument-hint: "[run-dir, optional — defaults to latest run]"
---

Generate storyboard prompts for: $ARGUMENTS

## Purpose

產 Nano Banana 分鏡稿，為「觀眾留存率」優化的 shot 序列。不是每句字幕一個 shot，而是根據內容節奏和情感弧線設計。

**自動偵測模式（讀 script.json）：**
- `orientation == "portrait"` OR `target_length == "short"` → 短影片模式（3 variants × 8-14 shots × 1080×1920）
- `orientation == "landscape"` AND `target_length in {medium, long}` → 長影片模式（1-2 variants × 40-60 shots × 1920×1080 × chapter-aware）

未偵測到上述欄位預設走短影片模式（舊 script.json 向後相容）。

## Prerequisites

- `<run_dir>/script.json` 必須存在
- `<run_dir>/subtitles/subtitles.srt` 必須存在（用來取得時間軸）
- 建議已經跑過 voice stage（這樣有精準的音檔時間）

## Read Supporting Files

1. **script.json** — 內容、敘事結構、每場景時長
2. **subtitles/subtitles.srt** — 每個字幕段的時間點
3. **[style_palette.md](style_palette.md)** — 可用風格清單（**必讀**）
4. 若存在：`research.md`（補充視覺靈感的事實細節）

## Shot Design Principles（設計分鏡時必遵守）

### 0. Shot 邊界必須對齊字幕時間軸（CRITICAL）
**所有 shot 的開始/結束時間必須是 `subtitles.srt` 裡某個字幕的開始或結束時間點。**
不可以亂切時間（例如 `00:03.5` 是憑空編出來的），必須查 SRT 對齊。

正確流程：
1. 先讀 `subtitles.srt`，把每個字幕段的 start/end 時間列出來
2. 決定哪些連續字幕段要合併成一個 shot
3. shot 的 start = 第一個合併字幕的 start
4. shot 的 end = 最後一個合併字幕的 end
5. 檔名用 `MM:SS.ms~MM:SS.ms.png` 格式（小數點精確到字幕的時間）

範例：若字幕 5 是 00:08.680→00:11.220，字幕 6 是 00:11.360→00:13.900，
要合併成一個 shot 時，檔名為 `00:08.68~00:13.9.png`。

### 1. Shot 數量

**短影片模式（portrait）：**
- 目標 **8-14 個 shot** per 變體（不是每句字幕都要一個）
- 合併相關的字幕段成一個 shot（一個畫面撐 3-6 秒）
- 例外：**Hook 前 3 秒**要 2-3 個快速切換的 shot（pattern interrupt）

**長影片模式（landscape）：**
- 目標 **40-60 個 shot** per 變體（10 分鐘影片 = 每 10-15 秒換畫面）
- 每 2-3 秒切畫面在長片裡太頻繁會視覺疲勞；但超過 15 秒同畫面會失去注意力
- **Chapter 邊界**強制換 shot，且該 shot 應有明顯的視覺重置（換風格/換配色/換主體）
- Hook 前 5 秒仍要 3-4 個快速 shot（pattern interrupt 原則不變）
- Rehook 點（每 60-90 秒）要有強烈畫面變化

### 2. 影片 vs 圖片
- **預設都是圖片**（.png）
- 每個變體**最多 2 個影片**（.mp4），且只用在：
  - Hook 的開場（需要動感抓住觀眾）
  - 關鍵動作時刻（物體移動、人物動作）
  - 情感高峰（讓觀眾停留的瞬間）
- 其他所有 shot 都用圖片（nano banana 更擅長）

### 2.5 科學/真實素材（嚴格禁用 AI 生圖）

當 shot 要呈現以下內容時，**必須**使用 `stock_real` 類別（不用 AI 生成）：
- fMRI / MRI / CT / X-ray / 超音波 等醫學影像
- 特定論文引用的數據圖表
- 歷史事件照片、真實人物（科學家、研究團隊）
- 考古文物、博物館藏品實拍
- 天文觀測影像（NASA/JWST/哈伯/ESA）
- 顯微鏡/電子顯微鏡實拍
- 新聞事件、社會運動現場

**理由：** AI 可以輕易「偽造」看起來專業的 fMRI 掃描或研究圖，但這是**誤導觀眾**。
知識型頻道的信任度建立在真實性上，偽造科學素材嚴重損害頻道可信度。

**輸出規則：** `stock_real` shot **不產生 Nano Banana prompt**，改為提供：
- 搜尋主題 + 英文關鍵字
- 建議來源清單（從 research.md 裡的論文 URL / 新聞 URL 找）
- Attribution overlay 文字（「來源: Nature」等，影片上要顯示）

**什麼可以用 AI：** 概念性/風格化/通用場景仍用 AI：
- 骨導示意圖（Ghibli 風格化的頭骨）✓ AI OK
- 人在聽錄音（通用生活場景）✓ AI OK
- 歷史場景的藝術重現（明確標示為 illustration）✓ AI OK（建議加「illustration」水印）

### 3. 留存率優化
- **0-3 秒**：最強烈、最意外的視覺（pattern interrupt）
- **3-10 秒**：視覺變化頻率高（每 2-3 秒換畫面），維持注意力
- **Rehook 點**（大約 15-20 秒、30-35 秒）：畫面要有明顯變化（換風格、換視角、換顏色）
- **情感/數據高峰**：用 close-up、特寫、或強對比畫面強化印象
- **結尾 5-8 秒**：回扣開頭的視覺主題，或用一個讓人想重播/分享的畫面

### 4. 風格混搭策略
從 [style_palette.md](style_palette.md) 選 shot 風格，**同一變體可混搭多種風格**：
- Hook 用 `cinematic_doc` 或 `vintage_cartoon`（選驚嘆/好笑）
- 原理解釋用 `textbook_diagram` 或 `infographic`
- 情感段用 `cinematic_doc` 或 `japanese_anime`
- 幽默段用 `vintage_cartoon` 或 `pixar_3d`
- 數據展示用 `infographic`

## Variant Strategy

### 短影片模式 — 產 3 個變體

產出 **3 個變體**，敘事邏輯一致但視覺風格不同：

- **Variant A — 寫實情緒向**：以 `cinematic_doc` + `japanese_anime` 為主，少量 diagram。適合嚴肅、情感型主題。
- **Variant B — 卡通輕鬆向**：以 `vintage_cartoon` + `pixar_3d` 為主，適合幽默、反差型主題。
- **Variant C — 資訊教育向**：以 `textbook_diagram` + `infographic` 為主，適合科普、解釋原理。

每個變體的 shot 時間切分可以不同。

### 長影片模式 — 產 1-2 個變體

長片 40-60 shot × 3 variants = 180 shots，生成成本與挑選成本過高。長片只產：

- **Variant A — 主風格混搭**（必產）：依 `genre` 挑主風格組合
  - `knowledge` → `textbook_diagram` + `cinematic_doc` + `infographic`
  - `listicle_ranking` → `vintage_cartoon` + `pixar_3d` + `infographic`
  - `news_analysis` → `cinematic_doc` + `stock_real` + `infographic`
  - `story_mystery` → `cinematic_doc` + `japanese_anime` + `vintage_cartoon`
- **Variant B — 備選替代風格**（可選，若主題適合）：挑一組視覺上明顯不同的風格組合

長影片的 shot 設計必須 **chapter-aware**：
- 每 chapter 開頭 1 個 pattern-interrupt shot（對應 chapter.hook）
- 章節中段用 B-roll 堆疊資訊（可用 `scene.b_roll_keywords` 當視覺線索）
- 每 chapter 收尾 1 個 payoff shot（對應 chapter.payoff）
- 章節轉換時明顯換視覺調性

## Output Format

寫到 `<run_dir>/storyboard_prompts.md`，格式如下：

```markdown
# Storyboard Prompts — <video_title>

**Total duration:** XX.X seconds
**Source script:** <run_dir>/script.json

---

## Variant A — 寫實情緒向

**主軸風格：** cinematic_doc + japanese_anime
**Shot 數：** 10
**影片 (.mp4) 數：** 2（Hook + 情感高峰）

### Shot 1 — `00:00~00:02.5.mp4`
**字幕對應：** 「剛聽完自己的語音訊息...」
**風格：** cinematic_doc
**目的：** Hook — 觀眾代入感
**Prompt:**
(pre-populated full Nano Banana prompt here, ready to paste)

### Shot 2 — `00:02.5~00:05.png`
...

---

## Variant B — 卡通輕鬆向
...

---

## Variant C — 資訊教育向
...
```

### 每個 Shot 的 Prompt 格式

Prompt 要直接可以貼到 Gemini / Nano Banana，格式：

**短影片（portrait）：**
```
[scene description]
[shot-specific style suffix from style_palette.md]
portrait 9:16 aspect ratio, 1080x1920 resolution
```

**長影片（landscape）：**
```
[scene description]
[shot-specific style suffix from style_palette.md]
landscape 16:9 aspect ratio, 1920x1080 resolution
```

**aspect ratio 結尾必須寫對**，否則 Nano Banana 會產出錯誤比例的圖，assembly 階段會被填黑邊。

For video shots (.mp4), 加一句動作描述，例如：
```
camera slowly zooms in over 3 seconds
```
或
```
subject walks from left to right across frame
```

## Execution Steps

1. 解析 `$ARGUMENTS` 取得 `run_dir`
2. 讀 `script.json`, `subtitles.srt`, `style_palette.md`, 可選 `research.md`
3. **偵測模式**：檢查 `script.json` 的 `orientation` 與 `target_length` 欄位
   - 長片 → 1-2 variants × 40-60 shots × landscape 16:9
   - 短片（或沒有欄位）→ 3 variants × 8-14 shots × portrait 9:16
4. 長片模式額外讀 `script.json` 的 `chapters[]` 跟每個 scene 的 `chapter_number`、`b_roll_keywords`
5. 規劃 shot breakdown（不是每句字幕一個 shot）
6. 每個 shot 從 style_palette.md 挑選適合的風格
7. 產出具體的 Nano Banana prompt（含 style suffix 與對應 aspect ratio）
8. 依字幕時間軸給每個 shot 檔名（`MM:SS~MM:SS.png/.mp4`）
9. 寫到 `storyboard_prompts.md`
10. 告訴使用者：「產出變體在 storyboard_prompts.md，請挑選一個變體並編輯調整，確認後再開始生成圖片」

## Quality Checklist

**共用：**
- [ ] Hook 段落（0-5 秒）至少有 2 個 shot，pattern interrupt 明顯
- [ ] Shot 時間總和覆蓋整個影片長度（無空隙）
- [ ] 檔名格式正確：`MM:SS~MM:SS.png` 或 `MM:SS~MM:SS.mp4`
- [ ] **科學/醫學/研究相關圖像標記為 `stock_real`，提供來源 URL（不用 AI 生）**
- [ ] `stock_real` shot 的來源 URL 來自 research.md（優先）或搜尋建議的可信來源
- [ ] 其他 AI-generated shot 的 prompt 包含 style_palette.md 的完整 style suffix
- [ ] AI prompts 全英文（Nano Banana 對英文 prompt 理解最好）
- [ ] 每個變體**最多 2 個 .mp4**（長片可放寬到 3-4 個 .mp4）

**短影片：**
- [ ] 3 個變體，每個 8-14 個 shot
- [ ] 每個 prompt 結尾包含 `portrait 9:16 aspect ratio`
- [ ] 三個變體風格明顯不同（寫實 vs 卡通 vs 圖表）

**長影片：**
- [ ] 1-2 個變體，每個 40-60 個 shot
- [ ] 每個 prompt 結尾包含 `landscape 16:9 aspect ratio`
- [ ] 每個 chapter 邊界有視覺 reset（換風格/換配色/換主體）
- [ ] 每個 chapter 開頭 shot 對應 `chapter.hook`
- [ ] 每個 chapter 收尾 shot 對應 `chapter.payoff`
- [ ] 每 60-90 秒有一次 rehook 級的視覺變化
