# REPORT — 外部免費／公有領域影片進片＋版權影片只放說明欄連結（深海大王烏賊示範）

分支 `worktree-cf-stock-footage`（自 `worktree-cf-deepsea` 23773ef fast-forward）。未 push、未付費服務、未開瀏覽器、未上傳。等級：🟢 本機實測 ／ 🟡 有保留 ／ 🔴 未驗。

## TL;DR
- 🟢 新媒體種類 `stock_video`：Wikimedia Commons／NASA／NOAA 頁面／Pexels／Pixabay 五個來源，授權白名單（PD、CC0、CC BY、CC BY-SA、Pexels、Pixabay）寫進程式；NC／ND／未知一律拒收；缺 sidecar 或缺畫面標示 QC 直接 error。
- 🟢 Pexels、Pixabay 金鑰實測有效（各一次真實搜尋回 HTTP 200，未印出金鑰）。
- 🟢 示範 `output/deepsea-1-stock`：6 段換成 NOAA 公有領域／CC0 深海影片，成片 597.8 s → 540p 兩段 12.64／12.56 MB。QC dead zones **15 → 8**，still_frames 超 8 秒 **10 → 3**；新規則 `footage_license` ok。
- 🟢 說明欄：credits 下方有「外部影像素材」與「延伸觀看」（2012 年 Discovery／NHK、2019 年 NOAA 墨西哥灣）；草稿 `artifacts/deepsea-stock/description.txt`。
- 🟡 沒有人看過整支成片，只抽 11 格；沒有人耳聽過。雲端費用 $0（沒跑 `claude -p`）。

## 1. Provider 與授權規則
| 來源 | 做法 | 收什麼 |
|---|---|---|
| Wikimedia Commons | MediaWiki API 搜尋或指定檔案頁；記作者（Artist 去 HTML）、授權名稱／網址、原始頁 | 只收 PD／CC0／CC BY／CC BY-SA；原檔 >150 MB 改抓 transcode |
| NASA Image and Video Library | images-api.nasa.gov 搜尋＋asset manifest；描述含 copyright／©／permission／Getty／非 NASA 的 courtesy 即拒收 | 「公有領域（NASA 媒體使用準則）」 |
| NOAA Ocean Exploration | 無搜尋 API，只收指定頁面（noaa.gov）；`scan_page` 要求頁面明確 NOAA 出處且沒有其他 "courtesy of／©／copyright／permission" | 公有領域（美國政府著作） |
| Pexels／Pixabay | 沿用既有 `StockClient`（rate limit、每次 run 上限、查詢快取） | 各自授權；畫面標作者 |

- 共同：每秒 ≤1 次請求、一次一個、描述性 User-Agent（Commons 先前用舊 UA 回 403，改後正常）、搜尋結果與檔案快取於 `.cache/footage/`、候選先 `screen`（授權、作者、原始頁、避臉）才下載。
- 授權規則 `review/license_rules.py`：`classify_license`（白名單，含 URL 判 NC）、`footage_problems`（sidecar 欄位 provider／author／license／source_url／retrieved_at、畫面標示 `label`＋`label_burned`、CC BY／BY-SA 必須列在說明欄、sidecar 檔存在）；`stock_video` 加進 `allowed_kinds`；`qc.footage_findings` 接進 QC。頻道須 `media.stock_video: true` 才可用（deepsea 已開；`source_footage` 仍鎖 false）。
- 🟡 避臉：venv 沒有人臉偵測（無 cv2），只做標題／說明／標籤的字詞篩（人、潛水員、科學家等拒收）＋每段標 `review`＋我人工看過成片抽格。指定 URL 的片段略過字詞篩（人工挑的；字詞篩會把「說明提到 scientists 的空海床」也擋掉）。
- 🟡 CC BY-SA：數秒片段算「改作」，授權要求改作依原授權散布；整支片通常視為集合著作，法律上未定論。示範沒用到 BY／BY-SA 片段，只在單元測試走過這條路。
- 實際被規則擋掉的例子（🟢）：2019 年 NOAA 墨西哥灣大王烏賊影片頁標「Video courtesy of Edie Widder and Nathan Robinson」→ `scan_page` 拒收，改放說明欄連結。

## 2. 剪輯
`media.kind: stock_video`＋`query`（必填）／`url`（指定 Commons 檔案頁、images.nasa.gov/details/、noaa.gov 頁）／`start`／`end`（避開片頭片尾字卡）／`frame`（lower、panel_left、panel_right）／`footage_note`（例「深海生物示意」）。自動挑 3–8 秒片段（每秒畫面差分挑動作多的窗口、互不重疊、時間順序）、靜音、cover 縮放 1920×1080、左上角燒入「影像：作者 / 來源（CC 授權）｜備註」；來源不夠長則 ≤1.5 倍慢放，否則循環。找不到合格素材退回動畫投影片並記原因。每段標 `review`（媒體聯絡表橘框）。

## 3. 說明欄連結
`deck.reference_links`（title＋url＋note，三欄必填）→ `credits.json` 的 `description_text`，接在 credits 下方 →package 帶進說明欄。示範四條：Discovery／NHK 新聞稿（2012）、Smithsonian Magazine 報導、NOAA 2019 Here Be Monsters、NOAA 2019 影片頁。
🟡 Discovery 新聞稿網址檢查時回 503（搜尋結果列有該網址），沒能確認頁面內容；Smithsonian Ocean 原頁對機器回 403 所以改放 Smithsonian Magazine。**上傳前請人點一次這四條。**

## 4. 示範：每段使用素材
全部來自 Wikimedia Commons，作者 NOAA／NOAA OER，畫面標「影像：NOAA … / Wikimedia Commons｜深海生物示意」。**都不是大王烏賊**（找不到合格的深海烏賊影片），所以畫面備註「深海生物示意」。

| 投影片 | 素材（頁面） | 授權 | 剪輯 |
|---|---|---|---|
| s06 名詞三：深度 | Okeanos Explorer PR and USVI Dive 8 – Psychedelic Medusa（commons File:Okeanos_Explorer_PR_and_USVI_Dive_8-_Psychedelic_Medusa-NOAA-1280x720.webm） | Public domain | 6–60 s，2 刀×7.2 s |
| s11 第二棒：誘餌與相機 | Ex1402-dive11 fish（File:Ex1402-dive11_fish.webm） | CC0 | 0–14 s，循環 |
| s13 約 4 小時的連拍 | Bathynomus giganteus ROV Deep Discoverer, Gulf of Mexico 2017（File:Bathynomus_giganteus_as_seen_by_remotely_operated_vehicle_(ROV)_Deep_Discoverer_…webm） | Public domain | 5–55 s，2 刀×7.5 s |
| s16 傳說中的怪物是獵人 | Ex1402-dive06 red animal（File:Ex1402-dive06_red_animal.webm） | CC0 | 4 刀×6.9 s |
| s21 為什麼是小笠原 | 0501-hydrothermal-vents-640x360（File:0501-hydrothermal-vents-640x360.webm） | Public domain | 4–58 s，4 刀×8 s |
| s25 潛航員的筆記 | First footage of Duobrachium Sparksae（File:First_footage_of_Duobrachium_Sparksae.webm） | Public domain | 0–28 s，循環（35 s 時段） |

sidecar：`output/deepsea-1-stock/assets/footage/<slide>.sidecar.json`（含取用日期 2026-10-24）。
🟡 內容對應只是氛圍（水母配「越走越暗」、等待的水母配「改成等牠來」）；s11、s25 因來源只有 14／28 s、時段 22／35 s 會循環播放，看起來有重複感。
🟡 解析度：多支原片 640×360 或 960×540 放大到 1080p（成片 540p 看不出，若要 1080p 發布需換更高畫質來源）。

## 5. Dead zones 處理前後（🟢 `qc/qc_report.json`）
- 前（cf-deepsea）：15 段 >10 s；still_frames 超 8 s 者 10 處。
- 後：**8 段** >10 s（67–83、116–128、152–171、177–192、249–280、350–367 s …）；still_frames 超 8 s 者 3 處（最長 27.25 s）。QC 仍是 1 error（dead_zones）、3 warn（speech_check 沿用舊配音的 2 場誤讀、beat_gap、still_frames）。
- 🟡 沒有清零：只換 6 段（任務要求 3–5，多換 1）；剩餘多是 AI 圖視差 >14 s 的長段（s04、s07、s09、s10、s14、s19…）。要清零需更多合格素材或讓長段內部拆成「圖＋影片」兩半（未做）。

## 6. 費用與牆鐘
- 雲端 `claude -p`：**$0**（閘門都沿用核可、事實查核差異檢查「沒有改寫的句子」）；金鑰檢查與素材下載皆免費額度。
- 本機：media 365.9 s（等 GPU／swap 約 9 分）、assembly 241.5 s、mix 29.7 s、540p 兩段約 2 分、一堆下載與試看；開發＋測試＋等待總牆鐘約 3 小時（🟡 未逐筆計秒）。

## 7. 測試與提交
- `tests/unit/test_footage.py` 36 項（授權白名單／拒收、篩選、各 provider 解析、NOAA 頁面掃描、片段規劃、sidecar／標示／說明欄檢查、ffmpeg 靜音與長度、client 以 MockTransport 驗證下載一次＋快取＋拒收）。全套 `1958 passed, 1 skipped`（排除既有失敗的 test_multi_provider）。
- 新增腳本：`scripts/check_stock_keys.py`、`scripts/deepsea_stock_deck.py`、`scripts/encode_540p_parts.py`。

## 8. 產物與清理
- `output/deepsea-1-stock/`（gitignore）、`artifacts/deepsea-stock/deepsea-stock-part{1,2}.mp4`（未 commit）、`description.txt`（commit）。快取 `.cache/footage/`（約數百 MB，gitignore）。
- 暫存在 `~/.claude/jobs/f59b927c/tmp`（隨 job 清）；worktree 內 `graft/` 為未追蹤索引目錄，沒動。
- 沒清掉：`output/deepsea-1-stock` 與 `.cache/footage`（rm 不在白名單，交 orchestrator）。

## 9. 需要 Leon 確認
1. 成片是否接受「泛深海生物」當大王烏賊旁白的 B-roll（畫面已標「深海生物示意」）。
2. 說明欄四條連結上傳前人工點一次（見 §3）。
3. 要不要做「長段拆成圖＋影片」以清掉剩餘 dead zones。

## 進度紀錄
- 2026-10-24：全部完成；對話遠低於 30 萬 token。
