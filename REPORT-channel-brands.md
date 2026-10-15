# REPORT — v3-B 四個頻道的品牌系統

分支 `design/channel-brands`（從 `feat/explainer-v2` 91ca15c 開，並 cherry-pick 了 `design/slide-styles-10` 的 style 機制 68a8bce）。未 push。

## TL;DR

- 四個頻道各有一套品牌：①**晶片貓**「拆解報告書」（冷白／墨藍／橘）、②**妖怪溯源所**「夜讀古籍」（墨黑／宣紙／硃砂）、③**晶片貓下班了**「便利貼漫畫」（螢光黃／黑線／粉紅）、④**賽璐璐研究室**「動畫用紙」（米紙／藍格線／紅鉛筆）。
- 四套都用真的 explainer 模板跑出 3 張投影片（`brand=<code>`，新增 `templates/themes/brands/<code>.css`），版面檢查 0 問題、WCAG 對比全過；另有 3 款縮圖、icon、banner、Shorts、片尾。
- 「同一個工作室」的線要有，但只放在片尾版位、字幕系統、來源列和工作室標記；縮圖、配色、片頭都不共用。
- 選稿頁：`docs/design/channel-brands/index.html`；總覽圖：`docs/design/channel-brands/overview.png`。
- 要 Leon 決定：四個頻道名稱、③ 是否把冷笑話 Shorts 和迷因考古合成一個品牌、④ 是否另設新角色「格仔」、工作室名稱。

## 產物位置

| 產物 | 路徑 |
|---|---|
| 選稿頁（可選名稱、按採用／修改／不採用、複製選擇） | `docs/design/channel-brands/index.html` |
| 四品牌並排總覽圖 | `docs/design/channel-brands/overview.png` |
| 每個品牌：3 張投影片、3 張縮圖、icon（含圓形裁切）、banner、Shorts、片尾 | `docs/design/channel-brands/<code>/` |
| 四份提案全文（名稱、定位、語氣、色彩、字體、動畫等） | `docs/design/channel-brands/proposals.json`（選稿頁就是它的渲染結果） |
| 撞名查詢原始結果與對照組 | `docs/design/channel-brands/name-check-*.json` |
| 版面檢查＋對比數字 | `docs/design/channel-brands/measurements.json` |
| 投影片樣式表 | `src/content_farm/explainer/templates/themes/brands/{chipcat,yokai,offwork,cel}.css` |
| 縮圖／icon／banner／Shorts 模板 | `src/content_farm/explainer/templates/brands/<code>/assets.html.j2`、共用片尾 `brands/endcard.html.j2`、工作室標記 `brands/studio_mark.svg`、角色剪影 `brands/silhouettes/*.svg` |

重跑：
```
PYTHONPATH=src .venv/bin/python scripts/render_channel_brands.py
PYTHONPATH=src .venv/bin/python scripts/build_channel_brands_page.py
```

## 四份品牌提案摘要

### ① 台灣科技產業拆解 — 推薦名：**晶片貓**
- 定位：把台灣科技業拆成你聽得懂的零件。個性：精準、好奇、冷靜、有據的嘴砲。
- 口頭禪：「我是晶片貓，今天把〇〇拆給你看。」「先講結論：」「這個數字有來源，放在左下角。」「拆完了，下一顆晶片見。」
- 視覺：**拆解報告書**。左側墨藍裝訂邊（TEARDOWN REPORT）、黃光虛線、尺寸線取代裝飾線、比較頁是 SPEC-A／SPEC-B 規格表、標題頁一片只亮一顆橘色晶粒的晶圓。
- 色彩：底 `#f2f5f8`、墨藍 `#0e1b2a`、晶片貓橘 `#d9480f`（唯一強調色）、矽藍 `#0b5cc2`、黃光 `#ffc21a`（只當裝飾）。
- 動畫：「量測」，等速、無彈跳。轉場：黃光帶掃過畫面。
- 角色：晶片貓本尊；橘色就是角色色。
- Shorts：「一個數字」，用一個巨大的等寬數字講 45 秒。

### ② 神話・怪物溯源 — 推薦名：**妖怪溯源所**
- 定位：替每一隻妖怪查戶口（原典、年代、怎麼變成今天的樣子）。個性：沉穩、考據癖、帶點陰森的幽默、尊重信仰。
- 口頭禪：「今晚要查戶口的是……」「先看出處。」「今日溯源，到此為止。」
- 視覺：**夜讀古籍**。墨黑底、古籍雙線版框、右側版心直排頻道名、朱印「溯源」取代強調線、【注】、楷體引文。標題用魏碑。
- 色彩：墨 `#14110d`、宣紙 `#efe4cb`、硃砂 `#e0503a`、銅綠 `#7fb39b`、燈火金 `#c9a45c`（只當光暈）。
- 動畫：「墨暈」，慢、由模糊到清晰。轉場：捲軸或墨滴。
- 角色：說書貓，也就是晶片貓 rig 換裝（斗笠、斗篷、燈籠）。刻意縮小放在角落，主角是妖怪（館藏 CC0 版畫或非擬真水墨）。
- Shorts：「一分鐘妖怪圖鑑」卡，只當導流。

### ③ 搞笑 — 推薦名：**晶片貓下班了**（冷笑話 Shorts 和迷因考古**合成同一個品牌**）
- 判斷：Shorts 冷笑話小劇場是主力和導流，迷因考古是同一隻貓「下班後」的長片，用簡報 pipeline 做，成本低。兩者都是自製，不會碰到 2026-10 Shorts 對搬運內容的降權。不併進①，因為①要的是可信度。
- 個性：廢、冷、反應快、自嘲、無害。節奏是鋪陳、停 0.6 秒、笑點、「叮」，不解釋笑話。口頭禪：「好，冷。」「下班。」
- 視覺：**便利貼漫畫**。螢光黃加網點、6 px 黑線、硬陰影（不模糊）、對話泡泡、爆炸星 VS、「下班中」貼紙。
- 色彩：黃 `#ffd84d`、墨黑 `#141414`、吐槽粉 `#c2185b`、配角藍 `#1a4fd8`。
- 動畫：pop 彈跳、笑點時畫面抖 2 幀。轉場：硬切加白閃。
- 角色：下班貓（晶片貓穿帽 T、拿馬克杯、半閉眼）加固定配角 PM 狗（垂耳、藍色）。

### ④ 動漫 — 選**動畫產業拆解**，推薦名：**賽璐璐研究室**
- 判斷：動漫調查把它排第一；不需要原片，避開 2026-07 美國法院的判決與 Content ID 風險；拆解手法跟①共用。雜學解說太泛，品牌長不出個性。
- 定位：動畫是一門生意，錢、人、時間，一格一格拆給你看。個性：宅但專業、熱情、細節控、尊重創作者。
- 口頭禪：「一秒二十四格，今天拆第〇格。」「答案在片尾名單裡。」「收工，原畫交出去了。」
- 視覺：**動畫用紙**。米紙加非照相藍格線、頂部定位孔、作画フレーム、CUT 編號框、紅鉛筆圈數字、手寫修正、攝影表式的比較欄。
- 色彩：紙 `#f5f1e8`、鉛筆黑 `#1f2329`、紅鉛筆 `#cc2f2a`、影色藍 `#2a64a8`、格線藍 `#a9c8e8`（只當裝飾）。
- 動畫：「一拍二」，用 steps() 以 12 fps 播，刻意不平滑。轉場：翻紙。
- 角色：**新角色「格仔」**（底片格身體、鉛筆呆毛）。不用晶片貓，免得四個頻道全是貓。
- 避開的名字：「動漫拆解室」已存在（8,800 訂閱）。

### 隱形的「同一個工作室」線（我的判斷：要，但只放在片尾）
四個頻道的觀眾幾乎不重疊，共用外觀只會讓每一個都變模糊；但片尾導流和製作流程需要共同骨架。共用的部分：片尾 20 秒的版位、字幕系統、畫面上的來源列（每個品牌只換前綴）、工作室標記「長了貓耳的方框」，以及「先比喻後定義」這條敘事規則。總覽圖、各頻道的 `endcard.jpg` 都看得到。

### 從 slide-styles-10 怎麼改的（不是換色）
| 品牌 | 借來的風格 | 重新定義成 |
|---|---|---|
| 晶片貓 | cleanroom、datajournal、blueprint | 報告書結構：裝訂邊、頁碼 P.、尺寸線、SPEC 表、量測線 |
| 妖怪溯源所 | editorial、newspaper | 改成暗底；古籍版框、版心、魚尾、朱印、【注】 |
| 晶片貓下班了 | collage、pastel | 漫畫格：黑線、硬陰影、對話泡泡、爆炸星、網點 |
| 賽璐璐研究室 | blueprint、swiss、chalk | 動畫用紙：定位孔、作画フレーム、CUT 框、紅鉛筆、攝影表 |

## 推薦的頻道名稱與撞名查詢

查詢方法：抓 YouTube 頻道搜尋頁（`sp=EgIQAg%3D%3D`，`hl=zh-TW&gl=TW`），解析 `ytInitialData` 裡的 channelRenderer；handle 用 `youtube.com/@handle` 的 HTTP 狀態判斷（404 = 未被佔用）。對照組「老高與小茉」能命中本尊 @laogao（672 萬訂閱）；handle 對照組 @laogao 回 200，亂打的 handle 回 404。腳本在 `scripts/check_channel_names.py`、`scripts/check_channel_handles.py`。

| 頻道 | 推薦 | 備選 | 撞名結果 |
|---|---|---|---|
| ① | 晶片貓 | 晶片貓產業筆記、矽島拆解 | 搜尋無同名頻道；**@chipcat 已被佔用（200）**，@chipcat.tw、@chipcatTW 是 404 |
| ② | 妖怪溯源所 | 妖怪戶口名簿、異獸考 | 前兩個搜尋 0 筆；異獸考有相近的「神话考异录」（81 訂閱）；@yokaisource 是 404 |
| ③ | 晶片貓下班了 | 冷笑話晶片貓、冷貓劇場 | 無同名；「冷貓劇場」跟甜茶貓劇場（2.7 萬）、貓影劇場（1.85 萬）太接近，不推；@chipcatoffwork 是 404 |
| ④ | 賽璐璐研究室 | 二十四格研究所、動畫錢從哪來 | 搜尋 0 筆；**@celluloidlab、@celllab 已被佔用**，handle 要另取（@celluloid.tw 沒查） |

⚠ 搜尋只看前 8 筆。「沒撞名」的意思是「搜尋結果前段沒有」，不代表 YouTube 上完全沒有。🟡

## 需要 Leon 決定

1. **四個頻道名稱**：在選稿頁點選後，按「複製我的選擇」貼回來就好。
2. **③ 合併**：冷笑話 Shorts 和迷因考古做成同一個品牌「晶片貓下班了」（我推薦合併），還是分成兩個頻道？
3. **④ 角色**：另設新角色「格仔」（我推薦，代價是要多做一套 rig），還是用晶片貓換裝？
4. **工作室名稱**：「貓工所」只是暫名。要取正式名稱，還是只留標記、不顯示名字？
5. **字型授權**：魏碑、楷體、翩翩體、圓體是 macOS 系統字型。拿來做 YouTube 影片和縮圖應該可以，但**授權我沒有查**。🔴 若要保險，可以換成開源字型（例如思源宋體、霞鶩文楷）。

## 證據與驗證

| 宣稱 | 等級 | 依據 |
|---|---|---|
| 12 張示範投影片沒有溢出、沒有侵入字幕區 | 🟢 | `render_channel_brands.py` 跑既有的 `_LAYOUT_CHECK_JS`，`measurements.json` 中 problems 全空 |
| 四組色彩對比全部符合 WCAG（內文 ≥ 4.5、強調 ≥ 3） | 🟢 | `brand_contrast_report`，從樣式表的 `:root` 讀值，所以數字不會和實際渲染脫節；有單元測試 |
| 用到的字型 Chromium 都找得到 | 🟢 | 用寬度探針比對 fallback，對照組（假字型）會被標成缺字。原本用的 `document.fonts.check` 對不存在的字型也回 true，已經換掉。檢查時發現 SF Mono 其實沒被用到（實際渲染是 Menlo），已把宣告改成 Menlo |
| 沒設 brand 時，渲染結果和原本一樣 | 🟢 | `test_no_brand_keeps_category_theme` |
| pytest：935 項中 934 過、1 skip、1 fail | 🟢 | 失敗的是 `test_multi_provider::test_returns_first_provider_results`。本分支對 `src/content_farm/visual` 和那支測試的 diff 是空的，所以是 base 帶來的，不是這次新增的。我沒有在 base 上實際重跑確認 🟡 |
| 撞名查詢結果 | 🟡 | 有對照組，但只看搜尋前 8 筆 |
| 「四個品牌放在一起明顯不同」「推薦哪個名字」 | 🔴（判斷） | 設計判斷，沒辦法機器驗證；請看總覽圖 |

## 程式變更（全部是 opt-in，沒傳 `brand=` 就和原本一樣）
- `explainer/brands.py`：品牌註冊表（code → 樣式表、頻道名、角色、從哪些 style 衍生）。
- `pages.theme_css / build_pages`、`cards.overlay_html`：新增 `brand=` 參數，優先於 `style=`。
- `styles.py`：抽出 `palette_from_css`、`contrast_report_for`，讓品牌重用同一套對比檢查。
- 測試：`tests/unit/test_explainer_brands.py`，19 項。

## 限制與沒做的事
- 角色全部是扁平剪影，沒用任何 AI 生圖。妖怪縮圖裡的野獸剪影也只是示意插圖的位置。
- 片頭、轉場、動畫語言只寫了規格，沒做成影片，也沒改 `animate.js`（像④的 12 fps steps 還沒實作）。
- 縮圖和 Shorts 是 HTML mockup，還沒接進 `thumbnail` 模組；deck 也還沒有 `channel` 欄位能自動選品牌。
- 投影片目前只有 `title`、`big_number`、`compare`、`timeline`、`quote` 五種版型有示範；`bullets` 和 media overlay 的樣式有寫，但沒截圖。

## 清理
- 工作目錄 `output/channel-brands/`（中間 HTML，在 gitignore 內，沒 commit）留著方便重跑，可以刪。
- 暫存檔都在 `$CLAUDE_JOB_DIR/tmp`，job 結束會一起清掉。
- 沒有建立其他分支，也沒有動 main 或 `feat/explainer-*`。
