# REPORT — explainer v2 整合：CoWoS 完整成片（晶片貓＋B-roll＋動態投影片）

## TL;DR

- 分支 `feat/explainer-v2`（從 `3332fa4`），依序合併 visuals → mascot → research，衝突全部解掉；本機 commit，**未 push**。🟢
- 成片：`/Users/lileon/project/content-farm/.claude/worktrees/cf-v2-integrate/output/explainer-cowos-v2/assembly/final.mp4`，1920×1080、影像 503.2 s（8:23）、音訊 504.6 s；blackdetect **0 段**（對照組 1 s 純黑可偵測）。🟢
- 已知問題 1（B-roll 不切題）：stock 加了關鍵字相關性篩選＋人工確認標記，查詢詞規則寫進 deck skill。實跑時篩選擋掉機車／不相關片，但「cleanroom」放行了藥廠無塵室、唯一的晶圓廠片上有真實公司名 → 兩支都換掉。**結論：篩選擋得住離題，擋不住「有品牌」，人工審 B-roll 仍是上線前必要步驟。** 🟢
- 已知問題 2（字幕壓到貓）：實測最長字幕 28 字、右緣 x=1634，越過貓的欄位（x≥1600）。解法是講解片字幕每行上限改 20（含標點容差最多 24 字，右緣 ≤1587），mascot_overlay 加量測守門，太寬就拒絕疊加。**沒有動貓的位置或字幕模板。** 🟢
- **追加（Leon 11:26，經 orchestrator 轉達）字幕斷行**：數字＋單位、百分比、年份、英數詞不再被拆開（行內與字幕段之間都修）。CoWoS 字幕從 **6 處拆開 → 0**，片子已重跑字幕與合成（配音沿用、其他素材未重產）。見第 11 節。🟢
- media 分布：slide 6、animated 8、title_card 4、stock 3、ai_image 3（全為佔位圖）。stock+ai_image = 25%（以槽位計），連續純 slide 最長 1 張。實際有畫面的 footage 只有 stock 3 張＝12.5%，要等 AI 插圖補上才到 25%。pytest `1 failed, 940 passed, 1 skipped`（失敗的是基準既有那一個）。🟢

等級：🟢 本機實測可重跑；🟡 只驗到存在或推論；🔴 未驗證的判斷。

## 1. 基準與合併

- 派工時 worktree HEAD 在 `6c47dd1`（不是 `3332fa4`），依指示 `git checkout -B feat/explainer-v2 3332fa4`。🟢
- 合併順序與結果：

| 順序 | 分支（tip） | merge commit | 衝突 |
|---|---|---|---|
| 1 | `feat/explainer-v2-visuals`（`a6edf64`） | `3423b2b` | 無 |
| 2 | `feat/explainer-v2-mascot`（`b9f3877`） | `d615732` | `.claude/skills/deck/SKILL.md`（deck.json 範例的 mascot／media 兩行） |
| 3 | `feat/explainer-v2-research`（`3a762a8`） | `c80784d` | `deck/SKILL.md`、`deck/writing_rules.md`、`explainer/deck.py`、`explainer/media.py`（add/add）、`tests/unit/test_explainer_media.py`（add/add） |

### 衝突解法

- **media schema 以 visuals 為準**：visuals 把 `Media` 放在 `deck.py`，`media.py` 是各 kind 的分派器；research 的 `media.py`（schema）、`deck.py` 裡的 `from content_farm.explainer.media import Media` 與它的 3 行交叉檢查全部丟掉，`tests/unit/test_explainer_media.py` 取 visuals 版（research 那份測的是被丟掉的 schema）。`deck.py` 的 `Mascot` 用 mascot 版（7 種 pose 封閉集合＋`say`／`position`）。🟢
- **CoWoS deck.json 對 visuals schema**：schema 本身一次就過；`--strict` lint 擋在 `title-card-meta`（4 張 title card 的來源缺 `publisher`／`published`）。research 把這兩項寫在 `note` 裡（`publisher=…; published=…`），我把它們提升成 v2 `Source` 欄位，`deck.json` 與 `sources.json` 同步（`publisher` 去掉括號裡的「citing …」以符合 40 字上限）。之後 `deck_to_script --strict` 0 警告、`check_article.py` 0 問題。🟢（`5031bc7`）
- **skill 文件合成一份**：`deck/SKILL.md` 的 deck.json 範例同時有 `mascot.say` 與 `media`；兩份 media 表（visuals 的「what you get」與 research 的「use for」）合成一張；新增〈Mascot〉與〈Stock query rules〉小節；拿掉 research 寫的「media 在 media.py」與「等 schema 有 say 再加」這兩句過期說明。`writing_rules.md`：晶片貓一段改成「每張都要寫 pose＋可選 say」並保留 research 的 pose 對照表與「畫面：media」一節。`deck-outline/SKILL.md`：media 配比改成和 lint 一致（stock+ai_image ≥ 20%、不連續 3 張純 slide）。🟢
- 各分支帶進來的 `REPORT-v2-*.md` 保留；visuals 的 `CLAIMS.jsonl` 被本報告的 CLAIMS 取代。

## 2. 已知問題 1：B-roll 跟主題對不上

### 做法（`0a66cf8`、`a0b4196`、`39e0afe`）

- **相關性篩選**（`explainer/stock.py`）：
  - 每支候選的「描述」＝Pexels 頁面網址的 slug（例如 `motorcycle-factory-production-line-overview-30288953`）＋Pixabay／Pexels 的 tags。
  - 相關詞＝`media.keywords`（新欄位，小寫英文、最多 8 個）；沒填就取 query 裡**非籠統**的字。`GENERIC_WORDS` 收了 factory、production、line、manufacturing、worker、close、up… 這類詞——原本那支 `factory production line` 三個字全是籠統詞，所以**根本不會去搜**，直接退回 animated。
  - 比對支援複數（wafers→wafer）與相鄰兩字合成（clean room→cleanroom）。
  - 排序先看命中幾個相關詞，再看解析度、長度。沒有任何候選命中 → 該供應商記一條「N 支可用、沒有一支提到 …」，兩家都沒有就退回 animated（`media_report.json` 的 note 寫明原因，contact sheet 紅框）。
  - 快取：同 query 的舊快取若不符合新的關鍵字，會重新搜尋。
- **人工確認標記**：每支被採用的 stock 都在 `media_report.json` 標 `review: true`、note 附上命中字與 slug；`contact_sheet.png` 上加橘框＋「B-roll 待人工確認」；CLI 輸出 `[review]`。
- **查詢詞規則**寫進 `deck/SKILL.md`〈Stock query rules〉與 `writing_rules.md`：英文、2–4 個畫面上看得到的具體名詞；不寫公司或產品名；`keywords` 選只有這個產業會用的字；有可讀的公司名／logo 的片一律不用。
- visuals 驗收 deck（`docs/examples/explainer-v2-visuals/deck.json`）的 s03 `factory production line` 也改成 `semiconductor cleanroom wafer`＋關鍵字。
- 測試：`test_explainer_stock.py` 新增 7 個（籠統詞不算、slug／tags／複數比對、機車產線被跳過改選相關片〔重現原 bug〕、全部離題時退回並列原因、純籠統 query 不打 API、keywords 覆蓋 query、舊快取不符新關鍵字時重搜），`test_explainer_media_schema.py` 1 個。🟢

### 實跑時發生的事（這段是重點）🟢

| 輪次 | 投影片 | query → 結果 | 處置 |
|---|---|---|---|
| 1 | s16 | `silicon wafer cleanroom` → Pexels 15 支、Pixabay 5 支，**沒有一支提到 wafer/silicon**，退回 animated | 篩選正確運作。另跑一次探查（4 個 query，4 次 API）確認 Pexels 幾乎沒有晶圓片，只有晶片／PCB 特寫和少數廠房 → 改 `electronic chip close up` |
| 1 | s22 | `semiconductor cleanroom wafer` → 只命中 `cleanroom`，選到 `pharmaceutical-cleanroom-hygiene-protocol` | 單一字「cleanroom」不夠專屬 → keywords 改成只收 `semiconductor`/`wafer` |
| 2 | s22 | `semiconductor manufacturing facility` → `modern-semiconductor-manufacturing-facility-32386530`，**畫面上清楚看到「捷泰科技 JIETAI TECHNOLOGY」** | 違反「stock 不能代表特定公司」→ 換成 `motherboard components close up` |
| 3 | s16／s18／s22 | 晶片 BGA 特寫／PCB 特寫／主機板特寫，逐張看過畫面，無可讀品牌 | 採用 |

→ 關鍵字篩選能擋「主題離題」（機車、藥廠），但擋不住「主題對、有品牌」。後者只有人看得出來，所以 `review` 標記是必要的，不是裝飾。B-roll 的題材也因此偏向「電子零件特寫」，和 CoWoS（封裝）的連結是氛圍等級，不是證據畫面。🟡

## 3. 已知問題 2：晶片貓與字幕位置

- **量測**（第一次 voice，landscape 預設每行 24 字）：170 行字幕裡最長 28 字。用燒字幕同一支字型（STHeiti Medium，52 pt、外框 3）量寬度，最寬 1349 px、右緣 x=1634；有 2 行越過 x=1600（`mascot/overlay.py` 的字幕禁區右緣，貓的像素都在 x≥1600）。🟢
- **原因**：`subtitle/line_wrap.py` 為了斷在標點，允許超出上限 4 字；24 字上限實際會出 28 字的行。mascot worker 推算字幕寬度時用的是「≤24 字」。🟢
- **選擇：縮字幕寬度，不動貓。**
  - 講解片的 voice 改用 `CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE=20`（含容差最多 24 字 ≈ 1254 px，右緣 ≤1587）。只是環境變數，**`config.py` 預設值、`timeline_assembly.py` 都沒改**，所以 Shorts（13 字）和其他橫式長片的行寬不受影響（符合短／長片並存規則）。（`line_wrap.py` 之後因第 11 節的斷行修正而改動，那是共用的改善，不是為了避開貓。）
  - 不移貓的理由：左下角會壓到 meta 列（mascot 報告已說明）；把貓縮小或往右推會讓牠出框或太小；把字幕整體左移要改 `timeline_assembly.py` 的共用樣式。
  - **守門**：新增 `explainer/mascot/clearance.py`，`mascot_overlay.py` 疊加前量測 `subtitles/subtitles.srt` 每一行，任何一行右緣超過 x=1600 就報錯並拒絕執行（`--allow-subtitle-overlap` 可強制）。測試 4 個，含「24 字上限會產生超寬行（對照組，偵測器會響）／20 字上限不會」與「字型大小與 LANDSCAPE_PRESET 一致」。另外在 CLI 層用假 run-dir 實測失敗路徑：exit 1，訊息 `subtitle line 1349px wide reaches x=1635 …`。🟢
- **改後實測**：第二次 voice（20 字）170 行、最長 24 字、最寬 1254 px、右緣 x=1587，0 行越界；mascot_overlay 守門通過。截圖可見字幕與貓之間有空隙。🟢
- 副作用（已修，見第 11 節）：20 字的斷點曾落在「2025 / 年」這種數字與單位之間。
- 補充 🟡：Pillow 的字級是 em 大小，libass 依 ascender+descender 定字級，CJK 字型通常 ≥1 em，所以量測應該偏寬（保守）。截圖上字幕右端都離貓有一段空隙，但我沒有逐像素量實際燒入的寬度。

## 4. 成片

- 路徑：`/Users/lileon/project/content-farm/.claude/worktrees/cf-v2-integrate/output/explainer-cowos-v2/assembly/final.mp4`（`output/` 在 gitignore，未 commit）
- 規格（ffprobe）：video 1920×1080、503.17 s；audio 504.63 s。🟢
  - 音訊比影像長 1.46 s：`full.mp3` 比各段 scene mp3 加總長，visuals 報告已記錄的既有現象，最後停在末格（不是黑畫面）。
- blackdetect（`d=0.05:pix_th=0.10`）：final.mp4 **0 段**；draft.mp4 也是 0 段。對照組 `color=black:d=1` → `black_start:0 black_end:0.96`。轉場是 0.4 s crossfade，所以連轉場處都沒有黑幀。🟢
- 流程與指令（run-dir `output/explainer-cowos-v2`，deck 從 `docs/examples/explainer-cowos/deck.json` 複製）：

```bash
PYTHONPATH=$PWD/src .venv/bin/python scripts/deck_to_script.py --run-dir output/explainer-cowos-v2 --strict
PYTHONPATH=$PWD/src .venv/bin/python scripts/render_slides.py  --run-dir output/explainer-cowos-v2
CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE=20 CF_TTS_PROVIDER=macos_say CF_ANTHROPIC_API_KEY=dummy-unused \
  PYTHONPATH=$PWD/src .venv/bin/python scripts/run_stage.py --stage voice --run-dir output/explainer-cowos-v2
PYTHONPATH=$PWD/src .venv/bin/python scripts/media_to_visual.py --run-dir output/explainer-cowos-v2 \
  --env-file /Users/lileon/project/content-farm/.env [--replace]
CF_TTS_PROVIDER=macos_say CF_ANTHROPIC_API_KEY=dummy-unused PYTHONPATH=$PWD/src \
  .venv/bin/python scripts/run_stage.py --stage assembly_timeline --run-dir output/explainer-cowos-v2
PYTHONPATH=$PWD/src .venv/bin/python scripts/mascot_overlay.py --run-dir output/explainer-cowos-v2 --workers 2
```

- `.env` 沒有複製進 worktree：stock key 用 `--env-file` 讀主 checkout，voice 用 dummy key（macos_say 不用）。
- `credits.json`（`output/explainer-cowos-v2/credits.json`）：3 筆 Pexels（作者、頁面、下載網址、授權、解析度）＋`description_text` 可直接貼說明欄。**新增 `pending` 欄位**列出沒有素材的槽位（s01／s04／s20 的 ai_image 佔位），讓「完整」可以檢查：有素材的全部有 credit，沒素材的明列待補（`9fe5d7d`，有測試）。🟢

## 5. media 分布（每張實際使用）🟢

| # | id | 版型 | 要求 | 實際 | 秒數 |
|---|---|---|---|---|---|
| 1 | s01 | title | ai_image | ai_placeholder | 14.35 |
| 2 | s02 | big_number | title_card | title_card | 15.36 |
| 3 | s03 | quote | slide | slide | 18.29 |
| 4 | s04 | bullets | ai_image | ai_placeholder | 29.63 |
| 5 | s05 | compare | slide | slide | 22.20 |
| 6 | s06 | bullets | animated | animated（reveal_list） | 21.56 |
| 7 | s07 | timeline | animated | animated（draw_line） | 21.38 |
| 8 | s08 | big_number | animated | animated（count_up） | 20.14 |
| 9 | s09 | big_number | animated | animated（count_up） | 22.15 |
| 10 | s10 | big_number | title_card | title_card | 13.32 |
| 11 | s11 | timeline | animated | animated（draw_line） | 24.33 |
| 12 | s12 | bullets | animated | animated（grow_bars） | 19.54 |
| 13 | s13 | quote | title_card | title_card | 21.77 |
| 14 | s14 | compare | slide | slide | 18.35 |
| 15 | s15 | big_number | animated | animated（count_up） | 18.73 |
| 16 | s16 | big_number | stock | stock（pexels 6755158 晶片特寫） | 17.43 |
| 17 | s17 | compare | slide | slide | 23.51 |
| 18 | s18 | bullets | stock | stock（pexels 6754819 PCB 特寫） | 24.37 |
| 19 | s19 | big_number | title_card | title_card | 19.26 |
| 20 | s20 | bullets | ai_image | ai_placeholder | 24.84 |
| 21 | s21 | compare | slide | slide | 23.07 |
| 22 | s22 | bullets | stock | stock（pexels 6754834 主機板特寫） | 23.29 |
| 23 | s23 | big_number | animated | animated（count_up） | 22.27 |
| 24 | s24 | quote | slide | slide | 23.95 |

- 合計：slide 6、animated 8、title_card 4、stock 3、ai_image 3（佔位）。
- stock + ai_image：**6/24 = 25%**（≥20% ✅，以槽位計）；扣掉佔位圖、只算真的有影像的：3/24 = 12.5%。
- 連續純 slide 最長 **1 張**（≤3 ✅）。
- 和 research 原始建議的差異：s16 從 slide 改成 stock（讓 footage 從 20.8% 提到 25%，留緩衝）；三張 stock 的 query／keywords 重寫。

## 6. 代表性截圖（`docs/examples/explainer-cowos/frames/`，從 final.mp4 擷取）🟢

| 要求 | 檔案 | 時間 | 內容 |
|---|---|---|---|
| 晶片貓說話 | `mascot_talking_s01.png` | 6.2 s | wave、嘴張開，背景是 s01 的 AI 佔位圖 |
| point | `mascot_point_s06.png` | 112.0 s | s06 reveal_list 完成後，抬爪 |
| deadpan | `mascot_deadpan_s19.png` | 366.9 s | 半瞇眼，s19 title card「台積電買下群創台南廠」 |
| stock | `stock_s22.png`（另有 `stock_s16.png`） | 448.0 s／310.0 s | 主機板／晶片特寫＋lower-third＋meta 列 |
| animated | `animated_s12_grow_bars.png` | 224.0 s | 第 4 條正在長出 |
| title card | `title_card_s02.png` | 22.0 s | The Register 2023-09-08「只能滿足約八成需求」 |

- 觀察 🟡：`grow_bars` 在 bullets 上，正在長出的那一條連文字一起被水平壓扁（截圖第 04 條），長完就正常。屬於 visuals 的動畫做法，本輪沒改。
- 觀察 🔴（主觀）：point 姿勢看起來仍像招手，mascot 報告已提過。

## 7. 各階段耗時（10 核 Mac）🟢

全程 1 分鐘平均負載在 **18.6–36.3**（開工時 22.9），超過 15 → mascot 從預設 4 workers 降到 **2 workers**；其他步驟本來就是單程序（media_to_visual 只開一個 Chromium），沒有再加平行。

| 階段 | 耗時（real） | 備註 |
|---|---|---|
| deck_to_script | 0.3 s | |
| render_slides | 5.6 s | 24 張 |
| voice（macos_say＋whisper 對齊） | 33.2 s | 第二次（改 20 字、音檔沿用）18.5 s |
| media_to_visual | 330.3 s（首跑，含 Pexels 下載） | 第二次 254.4 s、第三次 199.1 s（stock 大多走快取） |
| assembly_timeline | 120.9 s | 第二次 116.8 s |
| mascot_overlay（2 workers） | 409.4 s | 參數 1.7 s、渲染 329.2 s、疊加 78.1 s；15,095 幀 |
| **一條龍合計（首跑）** | **≈ 900 s ≈ 15 分** | 0.3+5.6+33+330+121+409 |

因為 B-roll 換片，media→assembly→mascot 實際跑了 3／2／2 輪，牆鐘總計約 40 分鐘。

## 8. 測試

```
PYTHONPATH=<wt>/src /Users/lileon/project/content-farm/.venv/bin/python -m pytest tests -q -p no:cacheprovider
```

結果（第 11 節修正後重跑）：**`1 failed, 940 passed, 1 skipped`**（83.9 s）＝下面的 886 ＋ `test_subtitle_atoms.py` 54 個。修正前一輪：`1 failed, 886 passed, 1 skipped`（41.5 s）。🟢
- 唯一失敗是基準既有的 `test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results`，沒有新增失敗。skipped 是 Pexels 實連測試（環境沒有 key 時跳過）。
- 數量核對：visuals 分支 827 passed → ＋mascot 36 ＋research `test_check_article` 11（research 的 media schema 測試 16 個隨被丟棄的 schema 一起移除）＋本輪 12 ＝ 886。

- worktree 內沒有 `.env`（`ls -a .env` → No such file）。
- 本輪新增／修改的測試：`test_explainer_stock.py`（+7，並把既有 fixture 的 slug 改成有內容的字，否則相關性篩選會把它們全擋掉）、`test_explainer_media_schema.py`（+1）、`test_mascot_clearance.py`（新，4）、`test_explainer_media_browser.py`（credits `pending` 斷言）。

## 9. 上線前還缺什麼

1. **真配音**：目前是 macOS `say`。正式版要 Fish Audio（付費，需要 Leon 放行）；換配音後所有時長會變，media→assembly→mascot 要重跑。research 標的「扣窩斯」發音也還沒驗。
2. **AI 插圖 3 張**（s01、s04、s20）：照 visuals 報告第 8 節的步驟走 Chrome＋Gemini（共同限制不准我開 Chrome）。補上後 footage 實際占比才到 25%。Gemini 圖用在營利頻道的條款沒查。
3. **人工審 B-roll**：3 支都標了 `review`。我逐張看過一幀、沒看到品牌，但只看了代表幀，**整支片段沒有逐秒看**。另外題材都是「電子零件特寫」，和 CoWoS 的關係只到氛圍等級。
4. ~~字幕斷行：數字和單位分在兩行~~ → 已修（第 11 節）。仍未處理的：投影片 lower-third 的重點句是 `…` 截斷（例如 s16「先進封裝占 2025 營收約 …」），那是畫面模板，不是字幕。
5. 研究報告留下的 🟡：Q2 2026 法說只有二手報導、產能數字全是估計（講稿已口播）。2026 Q3 法說（10 月中）出來後要更新。
6. 主觀檢查（🔴，需要人看）：晶片貓像不像 VTuber、point 姿勢、整片節奏；`grow_bars` 文字壓扁要不要改。
7. `draft_data: false`、strict lint 0 警告，但標題卡的標題與摘要是人寫的，程式不會檢查是否忠於原報導（visuals 報告已提）。

## 10. 副作用與清理

- `output/explainer-cowos-v2/`：本輪 run（gitignore）。`assembly/mascot.mov` 是 ProRes 中間檔（2.2 GB，可刪）；`assembly/final.mp4` 是成品。
- `.cache/explainer_stock/`（worktree 內，gitignore）：5 個 query 的 Pexels 快取（含被換掉的藥廠片與捷泰廠房片）。
- Pexels API 用量：media 三輪實際搜尋 Pexels 6 次、Pixabay 1 次（快取命中不打）＋探查 Pexels 4 次，下載 5 支；遠低於每小時 200 次。
- `PROGRESS-explainer-v2.md`：進度紀錄，**未 commit**，可刪（`rm` 在 deny）。
- job tmp（`/Users/lileon/.claude/jobs/9aa249bd/tmp/`）：輔助腳本（lift_source_meta、set_stock_media、probe_pexels、subtitle_widths、grab、media_dist、add_pending）、log、候選截圖、`guardrun/` 假 run-dir；job 刪除時一起清掉。
- 沒有 push；沒有動 main、`chore/wip-baseline-2026-10`、`feat/explainer-mvp` 及其 worktree、三條來源分支；沒有 commit `.env`、`output/`、`data/curriculum_map/`。

## 11. 追加：字幕斷行不拆數字＋單位、英數詞

來源：Leon 11:26 打在本 session 輸入框但沒送出，由 orchestrator（orch-personal）轉達。要求：數字與單位、百分比、年份同一行（「3 奈米」「59%」「2026 年」「CoWoS-L」「HBM3E」），英數詞不從中間斷；補測試；只重跑字幕與合成；確認沒有新增違規。

### 原因 🟢

字幕有兩個地方會切字：
- **行內**（`subtitle/line_wrap.py`）：在空白處斷行時會斷在「2025␣年」的空白；硬斷點會切在「CoWoS」中間。
- **字幕段之間**（`subtitle/estimation.py::_split_text`，whisper 對齊也用它）：斷點集合包含 `,` 和 `.`，所以「7,722」會在千分位逗號被切、「3.2」會在小數點被切。

### 修法（`fix(subtitle): never split a number from its unit or a Latin word`）

- 新模組 `subtitle/atoms.py`：定義「不可拆的原子」＝英數詞（含 `-`、`.`、`,`、`–`、`/` 連接，如 `CoWoS-L`、`HBM3E`、`3.2–3.5`、`1,000`、`59%`），數字後面再黏上可選空白＋單位（年、月、奈米、平方毫米、萬片、億元、%、倍、片…約 50 個，長的優先），可選前綴 `US$`／`NT$`／`第`。
- `is_safe_break(text, i)`：切點落在任何原子內部就不安全。`line_wrap` 的四種候選（強標點、弱標點、空白、硬斷）和 `_split_text` 的三種候選全部先問它；硬斷點往回移到原子前面。比一整行還長的原子保持完整（那一行會超長，比拆字好）。
- 沒有原子的純中文文字，斷點選擇和舊演算法**完全相同**（每個切點都安全時邏輯等價）。
- **Shorts 的影響**：`line_wrap` 和 `_split_text` 是共用的，Shorts（每行 13 字）同樣受惠；行寬上限與容差都沒變。測試涵蓋 13／20／24 三種寬度。

### 測試 🟢

- `tests/unit/test_subtitle_atoms.py`，54 個：Leon 列的例子都被認成一個原子；純中文沒有原子；單位只黏在數字後面；真實的 CoWoS 句子在 13／20／24 字下行內與字幕段都不拆；行長仍在 max+4 內；硬斷點會退到「CoWoS」前；千分位逗號與小數點不當斷點；`broken_atoms` 偵測器本身的正反例。
- **對照組**：把 `3332fa4` 版的 `line_wrap.py` 載進來跑同樣的句子，舊版拆了 4 處（`2025 年`@13、`CoWoS`@13、`2025 年`@20、`2026 年`@20），新版 0 處。證明測試抓得到原本的錯。
- 全套：`1 failed, 940 passed, 1 skipped`，失敗的是基準既有那個。

### 重跑 CoWoS 片 🟢

| 步驟 | 耗時 | 備註 |
|---|---|---|
| voice（macos_say，`CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE=20`） | 11.4 s | `scene_*.mp3` 修改時間不變（沿用，沒重新合成語音）；只重做 whisper 對齊與字幕 |
| assembly_timeline | 172.5 s | 重新燒字幕；`visual/` 片段沒有重產 |
| mascot_overlay（2 workers，負載 42） | 399.8 s | 參數 1.4 s、渲染 332.0 s、疊加 66.0 s |

- **違規數：修正前 6 → 修正後 0。** 量法：把 SRT 的每一行依序對回 script.json 的旁白，檢查每個原子是否被行界或字幕段界切開（共 140 個原子、171 行）。修正前被拆的 6 個：`7,722 平方毫米`、`2025 年`、`2026 年`×2、`171.4 億元`、`4.5 萬片`。
- 字幕寬度守門仍通過：最長 24 字、右緣 x=1587（<1600），0 行越界。
- final.mp4 規格不變：1920×1080、影像 503.17 s、音訊 504.63 s；blackdetect 0 段。
- 截圖：`docs/examples/explainer-cowos/frames/subtitle_fix_2025_year_s16.png`（「先進封裝在 2025 年大約占台積電營收／的 10%。」）、`subtitle_fix_7722_mm2_s09.png`（「可用面積 7,722 平方毫米。」）。其他 7 張截圖是修正前擷取的，字幕斷行可能不同，畫面其餘部分相同。
- 檢查腳本（job tmp，未 commit）：`audit_srt_atoms.py`（run 級稽核）、`old_wrap_control.py`（對照組）。

### 還沒做的

- 「2028 年月產能 4 萬到 / 4.5 萬片」這類範圍會在兩個原子之間換行（「4 萬到」與「4.5 萬片」各自完整），符合規則但讀起來仍斷。要把「X 到 Y 單位」當成一個原子，會讓很多行超長，沒做。🟡
- 單位表是列舉的；表外的量詞（例如「架」「艘」）不會被黏住。🟡
