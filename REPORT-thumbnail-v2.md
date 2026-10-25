## TL;DR
- 不奇而寓中片縮圖做了 3 個選項（A 誰會贏？／B 打還是讓？／C 為什麼沒人贏），新生專為縮圖構圖的特寫圖，字在 168×94 可讀，標籤改「不奇而寓」。拼版：`artifacts/thumbnail-v2/fable-ess-mid-sheet.png`（含舊版對照）。
- 寫進 pipeline：`fable.json` 新增選填 `thumb`（鉤子≤8 字＋縮圖專用圖提示＋版面）；`fable.py images` 畫圖、`render` 出 `variant_a|b|c.jpg`（<2 MB）；QC 檢查小圖字高／對比／舊頻道名；Shorts 產出 `thumbnails/cover_frame.json`（建議封面格）。標籤讀 `channel.name`，不寫死。
- 測試：新增 14 個，全套 2012 過、1 失敗（`test_multi_provider`，stock 影片、我沒碰的檔）。未上傳、未 push。
- 研究的誠實結論：「高對比」「標題互補」「臉」都**沒有**樣本數據支持（見 §1），只有「字少」「單一焦點」有官方或相關性依據；請把 A/B 實測當最後裁判。

## 1. 規則與出處（子代理 2026-10-24 查證，🟡：我只轉錄、未逐條開原文複驗）
Eden＝507,478 支長片、每組約 1,480 張，vidIQ＝500 支爆紅片；**兩者都沒量 CTR**，只比「爆紅 vs 低表現」，差距 <約 2.5 pt 不顯著。

| # | 規則 | 等級 | 出處 |
|---|---|---|---|
| 1 | 大字少字：4–6 詞最常見於爆紅片（30.6% vs 26.5%，最大差距）；7 詞以上反而偏低（29.6% vs 31.1%） | 數據（相關） | eden.so/blog/what-makes-a-good-youtube-thumbnail、vidiq.com/research/youtube-thumbnail-study |
| 2 | 構圖簡潔、單一焦點、字好讀、圖盡量大、三分法 | 官方 | support.google.com/youtube/answer/12340300 |
| 3 | 描述性文字（官方）；但逐字重複標題 6.3% vs 6.8%、完全不同 39.2% vs 39.1%＝無差異。「互補」只是設計習慣，無實證 | 官方＋數據：無差異 | 同上 |
| 4 | 臉：有臉 84.2% vs 82.2%，微笑反而較低（21.2% vs 23.4%），誇張表情只在大頻道明顯；動物／無臉頻道無直接證據 | 數據（相關） | eden、vidIQ、searchenginejournal.com/do-faces-help-youtube-thumbnails-heres-what-the-data-says/563944 |
| 5 | 高對比、高飽和：Eden 量像素，亮度／對比／飽和皆無可測差距 | 數據：無差異 | eden |
| 6 | 手機小圖可讀：各家寫 120／154×86／168 px，皆廠商，無原始出處 | 經驗 | — |
| 7 | 規格 16:9、JPG/PNG、≤2 MB（手機上傳）；官方頁建議 3840×2160、舊頁 1280×720 並存 | 官方 | support.google.com/youtube/answer/72431 |
| 8 | Test & Compare 最多 3 組、以觀看時長（非 CTR）判勝、僅電腦版、Shorts 不適用 | 官方 | support.google.com/youtube/answer/16391400 |
| 9 | Shorts：手機可從影片挑一格當封面；官方 blog 2026-07-24 起 YPP 創作者可在電腦版 Studio 上傳自訂 Shorts 縮圖（9:16） | 官方 | blog.youtube/news-and-events/youtube-studio-custom-thumbnail-updates、answer/72431 |
| 10 | A/B 每組至少約 2,000 次曝光（廠商數字，推導不明） | 經驗 | blog.autonolab.com |

找不到：arXiv／同儕審查研究、MrBeast 備忘錄、Think Media、Les Gray（未納入）。
已併入 `docs/design/thumbnails/rules.md` §5。

## 2. 三個選項（皆 1280×720、<200 KB、同一水彩繪本畫風：頻道 `style_prefix` ＋「特寫構圖」句）
圖片為本機 Z-Image-Turbo（mflux，免費）新生，seed＝頻道 seed+1000+n，一張約 1 分鐘；來源 run 唯讀。
- **A 誰會贏？**（字在底）：兩隻山雀對峙，左隻張翅撲、右隻退讓，中間一顆莓果。最像原需求，主體約佔畫面 70%。
- **B 打還是讓？**（字在左，主體在右）：一隻豎眉鼓起、一隻縮著眼睛擔心，對視。情緒最強；5 字換成兩行「打還是／讓？」略孤字，可改 4 字「打或讓？」。
- **C 為什麼沒人贏**（字在底）：兩隻同時展翅、僵持一顆莓果、雙方力量相當。最貼近片子的結論（「誰也佔不到便宜」）。
- 鉤子與標題互補（標題講現象，鉤子丟衝突／問題）；不含概念名（lint 檢查）；片中第 1 句話就拋出打架與讓路，前 60 秒兌現。
- 標籤「不奇而寓」讀 `channels/fable.yaml` 的 `name`，舊名「寓言學堂」列入 `former_names`。
- QC 結果：3 選項 `[ok]`（字高 ≥14 px @168 寬、字底對比 ≥3:1、無舊名、<2 MB）。
- 🔴 未驗：主體「佔 60% 以上」是用提示詞要求，沒有程式量測，請看拼版目視；哪個選項點擊最高要靠 Test & Compare。
- 拼版內有 168×94 實際大小與 2 倍放大預覽。

## 3. Pipeline 改動
- [model.py](src/content_farm/production/fable/model.py)：`Fable.thumb`（`ThumbOption`：hook／image_prompt／layout，≤3，選填；舊 fable.json 照常載入）。
- [check.py](src/content_farm/production/fable/check.py) `thumb_problems`（加入 `fable.py lint`）：鉤子 ≤8 字、不洩漏概念名／同義詞／英文名（鉤子與圖提示）、不是標題原句、圖提示不得有人物字眼。
- [thumb.py](src/content_farm/production/fable/thumb.py)（新）：`thumb_requests`／`draw_thumb_images`（縮圖專用特寫構圖）、`hook_layout`（字級依字數自動算，描邊）、`render_options`（`variant_a|b|c.jpg`＋`_tiny.png`；`thumbnail.png`＝A）、`thumb_findings`（小圖字高、字底對比、舊名、2 MB）、`cover_frame`／`write_cover_frame`／`metadata_line`。
- 模板 [fable_thumb.html.j2](src/content_farm/production/fable/templates/fable_thumb.html.j2)：新版（大字鉤子＋描邊＋漸層）；沒有 `thumb` 時退回舊版「標題壓底」但標籤也讀頻道名。
- [render.py](src/content_farm/production/fable/render.py) 的 `write_thumbnail` 接新流程；Short 另寫 `thumbnails/cover_frame.json`。[fable.py](scripts/fable.py) `images` 步驟畫縮圖用圖。[qc.py](src/content_farm/production/qc.py) 加 `fable_thumb_findings`。
- `Channel.former_names`（[channels.py](src/content_farm/production/channels.py)）；`channels/fable.yaml` 改名「不奇而寓」、`brands.py` 同步。
- 產出者提示：[SKILL.md](.claude/skills/fable-script/SKILL.md) 新增「縮圖選項」、`review/producers.py` 的 fable_script 提示要求寫 `thumb`。
- **可關**：fable.json 不寫 `thumb` 就是舊行為；QC 只給 warn。
- **Shorts 封面格**：選「揭曉前、story 幕、插圖完整度（邊緣能量×飽和度）最高」的一格，時間＝該鏡頭起點+0.5 s；寫入 `thumbnails/cover_frame.json`，`thumb.metadata_line(frame)` 產生 metadata.md 的表格列（尚未自動寫進 metadata.md，因為該檔由上傳打包步驟手寫；要自動化請另開）。
- 測試：[test_fable_thumb.py](tests/unit/test_fable_thumb.py) 14 個（鉤子字數／洩漏／重複標題、版面小圖字高、舊名、對比、請求、封面格不劇透）。

## 4. 沒做／風險
- 沒把 3 個選項接上 `thumbnail_variants` 上傳流程（任務說不上傳）；`variant_*.jpg` 命名與既有 A/B 流程相容。
- Shorts 的垂直縮圖版面只套 bottom 版型，沒實測（只有中片有實圖）。
- 用到無頭 Playwright 截圖（pipeline 既有 `PageCapturer`），沒有開使用者瀏覽器。
- 全套測試唯一失敗 `tests/unit/test_multi_provider.py::test_returns_first_provider_results`：stock 影片搜尋，我沒改該檔；未在乾淨基線重跑確認是否先前就失敗（🟡）。
- 對話才約 20 萬 token，無需換 session。

## 清理
暫存 run 在 `$CLAUDE_JOB_DIR/tmp/run`（含 3 張 1 MB 原圖，未 commit）；`artifacts/thumbnail-v2/fable-ess-mid.thumb-options.json` 是含選項的 fable.json 複本（20 KB，可刪；我的環境 `rm` 未試）。
