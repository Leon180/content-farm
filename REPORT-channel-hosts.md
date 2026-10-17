# REPORT：三頻道虛擬主持角色（第一階段概念稿）

分支 `design/channel-hosts`，從 `feat/launch-fixes` 的 `48e2f70` 開出。**rig 沒有做**，等 Leon 選稿。

- **第二輪**（最新）候選牆：`docs/design/channel-hosts/round2/index.html`，手機也能看。編號用兩位數：Y01–Y25、O01–O25、C01–C25。
- 第一輪選稿頁：`docs/design/channel-hosts/index.html`。編號用一位數（Y1、O1…），跟第二輪不同，不要混用。

## TL;DR（第四輪：3D 質感＋2.5D、金魚、縮圖，2026-10-17）

- **3D 版角色包**：`frog-scribe-3d`、`cooler-goldfish-3d`、`paint-bottle-3d`。
  - 用 klein 參考圖編輯，把平面版重畫成軟膠玩具質感，再用 3D 定裝重生 6 個狀態。
  - 剪影 IoU：差分 0.983–0.998，其中 3 張低於 0.99；3D 定裝對平面定裝是 0.92 左右，因為畫風本身就改變了外形。
- **2.5D 動作**：用深度圖做轉頭、點頭，加上落地陰影和說話時的 squash。角色包設 `motion: 2.5d` 就會啟用。
- **並排試片 3 支**（平面版 vs 3D＋2.5D，各 20 秒）在 `output/channel-hosts-r4/compare_{yokai,cel,offwork}_20s.mp4`。共 3,600 格，禁區像素都是 0 🟢。
- **O25 金魚**：
  - 所有臉都已經沒有嘴（定裝、眨眼和各表情都移除），說話時改成水瓶冒泡泡，泡泡依音量變化；3D 版也套用。
  - 移嘴前後剪影 IoU 1.0。
- **C09**：說話時在原嘴位換成小 o；有表情時保留表情本身的嘴，所以不會出現殘影。
- **單張圖轉 3D 調查**：`round4/image-to-3d-research.md`。結論是授權乾淨的模型品質不夠，Hunyuan3D 2.1 不適用歐盟、英國、南韓；**建議維持 2D 路線**。
- **縮圖**：四支開台片各 3 款（角色／主視覺／數字），共 12 張，每張都通過「60 秒內兌現」檢查；選稿頁 `docs/design/thumbnails/index.html`。產生器已擴充，支援 3 種版型、A/B 變體和 Short 直式封面。

## 第四輪：3D 質感＋2.5D

### 4-1. 做法

1. **3D 重畫**（`tools/r4_gen.py`）：
   - 平面版定裝 → klein 編輯，prompt 寫「軟膠玩具／黏土 3D 渲染、柔光、邊緣光、柔和陰影，保持同一角色」，不含任何 IP 名，送出前跑禁字檢查。
   - 3D 定裝對平面定裝的門檻設在 IoU ≥ 0.97，三個角色的最佳值都落在 0.92 左右，所以都沒過，我取各自的最佳值並目視確認。差距來自 3D 化本身的外形變化（變圓、加厚、模型畫了地面陰影），不是換了角色。
   - 再從 3D 定裝生 6 個狀態，門檻 ≥ 0.99，最多試 3 個 seed。
2. **去背**：3D 圖會被模型畫上一層淡灰地面陰影。去背門檻從 38 調到 100 才去得掉，同時確認顏料瓶白色的身體沒有被吃掉。
3. **角色包**（`tools/r4_pack.py`）：
   - 嘴型和泡泡的位置都重新在 3D 定裝上量：金魚四種嘴位、顏料瓶的小 o。
   - 深度圖由 `scripts/host_depth_worker.py` 產生，在 mlx-video venv 裡跑 Depth Anything V2 Small（Apache-2.0），每張不到 1 秒。
4. **2.5D 渲染**（`pngtuber/render.py`）：
   - 深度 warp：越近的像素平移越多，產生轉頭、點頭的效果，用 premultiplied alpha 避免邊緣出黑邊。
   - 加柔和落地陰影，說話抬升時陰影會變淡。
   - 說話時做 squash（變寬變矮，最多 3.5%）。
   - 為了替轉頭留邊距，2.5D 角色的尺寸會縮小約 7%，所以並排試片裡 3D 版看起來稍小。

### 4-2. 結果 🟢（`round4/packs.json`、`round4/trials.json`）

| 角色包 | 差分 IoU（blink／嘴／驚訝／得意／無言） | 深度圖 | 備註 |
|---|---|---|---|
| frog-scribe-3d | 0.996／0.994–0.995／0.994／0.996／**0.983** | 0.7 s | 無言那張眼睛的凸起被壓平了（模型行為）；得意的頭有點歪 |
| cooler-goldfish-3d | 0.998／0.998／0.999／0.998／0.995 | 0.7 s | 水瓶變成實心軟膠，看不到水，泡泡仍在藍色瓶身裡上升 |
| paint-bottle-3d | 0.998／0.998／0.998／0.998／0.996 | 0.7 s | 原始最佳 0.987（無言）；去背改進後重算是 0.996 |

| 並排試片（各 20 秒） | 平面版禁區 | 3D 版禁區 | 3D 渲染時間 |
|---|---|---|---|
| `output/channel-hosts-r4/compare_yokai_20s.mp4` | 0／600 格 | 0／600 格 | 10.0 s |
| `output/channel-hosts-r4/compare_cel_20s.mp4` | 0／600 格 | 0／600 格 | 6.4 s |
| `output/channel-hosts-r4/compare_offwork_20s.mp4`（9:16） | 0／600 格 | 0／600 格 | 9.5 s |

截圖在 `round4/trial_compare_*.jpg`。我的判斷 🟡：3D 版的立體感明顯，但三個角色都會變得更「玩具」，青蛙的水墨感、金魚瓶的透明水感都消失了。要不要換，是風格選擇，請 Leon 看並排片決定。換的方式只要把頻道 yaml 的 ref 改成 `pngtuber/<id>-3d`。

### 4-3. 金魚：嘴巴全部移除，改成冒泡泡（Leon 2026-10-17 兩次指示）

- `speech_fx: bubbles`：說話時，泡泡從嘴邊往上飄，在水面消失。產生率和大小跟音量成正比，靜默時每秒約 0.3 顆。泡泡位置是確定性的（固定 seed）。
- `erase_mouth`：四種表情的嘴各畫在不同位置，所以對每個位置各用一塊羽化的身體色蓋掉，定裝和每個差分都蓋。移除後定裝剪影 IoU 1.0，各表情合成後也是 1.0（無言 0.993，是汗滴的關係）。
- 9:16 試片：`output/channel-hosts-r3/trial_offwork_cooler-goldfish_9x16_bubbles.mp4`，730 格禁區 0。

### 4-4. 生圖閘門

- 加入 `qwen3-tts｜voxcpm2`。比對的是執行檔或腳本路徑，有反例測試：只在參數裡提到 voxcpm2 的 shell 不會被擋。
- 這一輪 TTS 連續佔用超過 1 小時，3D 批次兩次等到逾時（30 分鐘）。後來 orchestrator 核可「與 TTS 並行，但一次一張、可用記憶體 ≥ 35% 且 pressure 不是 warn」，用 `CF_GATE_ALLOW_TTS=1` 跑完。閘門實際有因為 pressure warn 停下來等過一次。

## 縮圖重做（orchestrator d699d146b06f637c）

- **規則**：`docs/design/thumbnails/rules.md`。
  - 6 條硬規則：每個字、每個數字都要在 60 秒內兌現；不承諾片中沒有的東西；聳動程度不超過內容；不用他人的肖像或品牌；AI 主視覺要記 credits；不直接拿標題投影片。
  - 7 條有效手法（🟡，要以 A/B 數據為準）。
  - **Shorts 不支援「測試與比較」**（🟢 政策審查引文）。
- **產生器**（`production/thumbnail.py`）：
  - 新增 `layout`：character、keyart、compare，以及 `compare` 數值。
  - `thumbnail_variants.json` 可以一次出最多 3 款，自動壓成 2 MB 以下的 JPEG；設 `vertical: true` 就出 1080×1920 的 Short 封面。
  - QC 的 `variant_findings` 會逐款檢查承諾。
  - CLI：`make_thumbnail.py --variants`。
- **修了兩個既有 bug**：
  - (1) 數字比對時旁白被壓縮掉「.」，所以 8.8、34.5 永遠比對不到。已加回歸測試和反例。
  - (2) 晶片貓品牌的 `.hl` 是 accent 色塊，但模板又把文字設成 accent 色，結果反白字消失，原本的晶片貓縮圖模板也受影響。
- **12 款**：`docs/design/thumbnails/{cowos,short7722,kyubi,cel}/variant_{a,b,c}.jpg`，每張 61–201 KB，全部通過承諾檢查。每一款的兌現秒數記在 `promises.json`，最晚的是九尾狐的「九條尾巴」，在 53.9 秒。
  - 主視覺：
    - CoWoS、7,722、cel 用 klein 生成（`*/keyart.json` 記錄模型、授權、prompt、seed）；
    - 九尾狐用北齋〈九尾狐〉（CC0，沿用原片 credits）。
  - cel 主視覺的第一版在紙上畫出了少女速寫，違反 cel「不得出現角色畫」的規則，已經改 prompt 重生（`cel_v2`）。
  - 7,722 的比對物原本是一張具名交通卡，縮圖改用「8.8 公分的中介層」，避免出現品牌名，也避免把中介層講成「晶片」。
  - CoWoS c 原本是「80% vs 18」，兩個不可比的數字放在一起，改成單一數字加副標「新產能等 18 個月」。
- **選稿頁**：`docs/design/thumbnails/index.html`，模擬手機首頁、桌機首頁和 Shorts 架的實際尺寸，附標題、片長徽章和每款的承諾秒數。手機寬度沒有水平捲動，壞圖 0 張。
- 測試：`tests/unit/test_thumbnail_variants.py` 共 18 項。全套 1 failed（基準既有）／1212 passed／1 skipped 🟢。

## TL;DR（第三輪：選定與 PNGtuber，2026-10-17）

- Leon 選定 **Y14 青蛙書記（妖怪）、O25 飲水機金魚（下班）、C09 顏料瓶老師傅（賽璐璐）**。三張都做過相似度把關，**沒有明顯撞臉**（🟡 目視判斷，見 §3-1），所以直接做角色包，沒有停下重生。
- 三個 **PNGtuber 角色包** 已接進 pipeline：
  - 每包有定裝、閉嘴、張嘴 2 段、眨眼、驚訝、得意、無言；
  - 18 張差分的剪影 IoU 是 0.989–0.998，其中 17 張 ≥0.99 🟢；
  - 疊加器支援呼吸、擺動、依音量換嘴型、隨機眨眼，並依 deck 的 mascot pose 換表情。
- 三個頻道的設定都改成 `host: pngtuber`、`rig_ready: true`；晶片貓維持向量 rig。
  - 橫式：固定右下角。
  - 直式（offwork）：放左下、字幕帶下方。scripted Short 的渲染器已改成真正走這條路。
- 試片 3 支：九尾狐 20 秒、cel-ep1 20 秒、7,722 Short 整支 24.3 秒（9:16）。**逐格檢查共 1,930 格，角色進入禁區的像素都是 0** 🟢。路徑見 §3-4。
- pytest：1 failed（基準既有的 multi_provider）／1184 passed／1 skipped 🟢。
- **要注意**：九尾狐 deck 的 29 張投影片都沒有 mascot pose，所以重跑時 policy 會報 `mascot_presence` error；之後的妖怪 deck 要寫 pose。完整清單見 §3-6。

## 第三輪：選定與 PNGtuber

### 3-1. 相似度把關（Y14／O25／C09）🟡

| 編號 | 最接近的知名角色類型 | 差異 | 結論 |
|---|---|---|---|
| Y14 青蛙書記 | ① 某日本文具公司的大眼青蛙（白眼球加黑瞳、紅臉頰、常穿衣服）；② 網路迷因青蛙（厚唇、下垂眼皮、寫實比例）；③ 外星青蛙軍曹動畫（帽子、星星） | 我們的是小黑點眼、沒有白眼球，薄荷綠配米白肚，沒有衣服、沒有厚唇，手拿毛筆 | 沒有撞臉。缺點是造型很通用，辨識度要靠毛筆和個性撐。如果要加強，最小修改可以是頭頂一點硃砂，或一頂書生小帽（這次沒做，等 Leon 決定） |
| O25 飲水機金魚 | ① 動畫電影的金魚女孩（紅色、有人臉）；② 海洋動畫的小丑魚（橘白條紋）；③ 遊戲裡的橘紅鯉魚（有鬍鬚、大嘴） | 橘色圓魚、皺眉，裝在藍色飲水機桶裡。「桶中魚」這個組合是招牌 | 沒有撞臉。角色本體小，表情只佔畫面一小塊 |
| C09 顏料瓶老師傅 | 療癒系的白色圓團、麻糬角色（Leon 的參考類型之一） | 藍色顏料瓶蓋加滴落的顏料是招牌部件；身體是瓶身輪廓，上窄下寬 | 沒有撞臉，但拿掉瓶蓋就是通用白團。白身體在 cel 的米白底上對比偏弱，靠黑外框撐 |

### 3-2. 角色包（`src/content_farm/explainer/pngtuber/packs/{frog-scribe,cooler-goldfish,paint-bottle}/`）

- **生成方式**（`docs/design/channel-hosts/tools/r3_gen.py`）：
  - Leon 選的圖當參考圖，用 klein 多參考編輯生成 6 個狀態；
  - 每張都驗剪影 IoU，≥0.99 才收，不到就換 seed 重生，最多 3 個 seed；
  - 生圖閘門跟第二輪相同。
- **IoU 結果** 🟢（`round3/packs.json`）：

  | 角色 | blink | mouth_half | mouth_open | surprised | smug | speechless |
  |---|---|---|---|---|---|---|
  | 青蛙書記 | 0.998 | 0.998 | 0.998 | 0.997 | 0.995 | **0.989** |
  | 飲水機金魚 | 0.998 | 0.998 | 0.998 | 0.998 | 0.998 | 0.990 |
  | 顏料瓶 | 0.998 | 0.998 | 0.997 | 0.998 | 0.998 | 0.998 |

  - Y14 的定裝圖先做了一次清理：原圖蛙腿後面有一根多出來的灰棒，我用編輯移除，所以對原圖的 IoU 是 0.982。這是刻意造成的剪影改變，不是漂移。
  - **IoU 量不到「臉畫錯」**：青蛙的 speechless 第一版 IoU 0.996，但眼睛整個不見了。是我看圖抓到的，改了 prompt（明寫「兩條平線眼」）重生。新版 0.989，略低於 0.99，原因是加在身體外面的兩滴汗。我判定可接受 🟡。
- **組裝方式**（`pngtuber/build.py`）：
  - 生成的整張圖之間會有線條抖動，直接換整張會閃。
  - 所以每個圖層只保留自己「顯著改變的區域」：差值門檻＋opening 去除抖動，再用百分位數去掉離群點，取 bbox 加邊距。區域內整塊換上，邊緣羽化；兩段嘴型共用張嘴的區域。
  - 第一版用的是整臉大框，「得意＋說話」時會疊出殘影（`round3/sheet_*.png` 已是修正版）。
- **審稿圖**：`docs/design/channel-hosts/round3/sheet_<pack>.png`。第一列是生成的原圖，第二列是渲染器實際組出來的樣子，包含「得意＋說話」的組合。

### 3-3. 接進 pipeline

| 檔案 | 改了什麼 |
|---|---|
| `explainer/pngtuber/`（新） | `pack.py`：格式、載入、驗證、pose→表情對照。`build.py`：角色包組裝。`motion.py`：逐格狀態；嘴型有 2 格遲滯，避免閃動；眨眼、呼吸沿用 rig 的 `idle`。`render.py`：placement、合成、ProRes 4444 alpha。`run.py`：draft→final。`still.py`：縮圖用的單張。`cutout.py`：去白底 |
| `production/channels.py` | `Mascot.host: rig｜pngtuber`（預設 rig）。設成 pngtuber 時，ref 必須是 `pngtuber/<id>` |
| `production/steps.py` | mascot 步驟遇到 pngtuber 頻道時多傳 `--pngtuber <ref>` |
| `scripts/mascot_overlay.py` | 新增 `--pngtuber`。字幕寬度檢查照舊先跑 |
| `explainer/mascot/overlay.py` | `overlay()` 多一個 `origin` 參數，預設值不變，晶片貓行為不變 |
| `production/thumbnail.py` | 縮圖選 MascotVisual 時，pngtuber 頻道用角色包，不再畫晶片貓 |
| `production/shorts_scripted_render.py` | pngtuber 頻道的 Short：beat 裡的貓位留空，渲完後用 beat 的 pose 疊角色（直式 placement） |
| `channels/{yokai,cel,offwork}.yaml` | `host: pngtuber`、`rig_ready: true`、ref 指向對應角色包 |

- **pose→表情**：
  - shocked→驚訝、smug→得意、deadpan／think→無言；
  - idle、point、wave→中性。靜態圖做不出手勢，這三個 pose 只會換嘴型。
  - 驚訝時不眨眼，因為中性的眨眼圖層蓋不住瞪大的眼睛。
- **placement**：
  - **橫式**：沿用 rig 的 620×540 畫布和 overlay 原點，角色高約 352 px 靠右下。
  - **直式 9:16**：畫布 560×520，原點 (0,1400)，角色高約 440 px 靠左下，位於燒入字幕帶（y 1220–1420）下方、Shorts 右側按鈕的左邊。這是 scripted Short 原本放貓的位置。
  - 禁區：橫式是 meta 列和字幕帶，直式是字幕帶。單元測試用最壞情況（最大呼吸、最大擺動、說話抬升）驗過，**而且有反例測試**：故意左移時，偵測器確實會抓到。

### 3-4. 試片 🟢（`docs/design/channel-hosts/round3/trials.json`）

| 試片 | 路徑 | 長度 | 逐格禁區像素 | 渲染時間 |
|---|---|---|---|---|
| 九尾狐＋青蛙書記 | `output/channel-hosts-r3/trial_yokai_frog-scribe_20s.mp4` | 20 s／600 格 | meta 0、字幕 0 | 6.7 s |
| cel-ep1＋顏料瓶 | `output/channel-hosts-r3/trial_cel_paint-bottle_20s.mp4` | 20 s／600 格 | meta 0、字幕 0 | 7.4 s |
| 7,722 Short＋金魚（9:16） | `output/channel-hosts-r3/trial_offwork_cooler-goldfish_9x16.mp4` | 24.3 s／730 格 | 字幕 0 | — |

- 路徑相對於本 worktree，在 `output/` 底下（gitignore，不 commit）。截圖 `round3/trial_*.jpg` 每支 4 張，有 commit。
- 素材取自 `cf-launch-fixes/output/` 的三個 run。橫式試片用 symlink 唯讀引用；Short 是把小檔複製到 job tmp 再跑，因為 renderer 會改寫 `subtitles.srt`。**沒有動到 launch-fixes 的任何檔案**。
- 九尾狐的 deck 沒有 mascot pose，所以這支只會看到中性表情加眨眼、說話；換表情的效果請看 cel 和 Short。

### 3-5. 測試

- 新增 18 項測試：`tests/unit/test_pngtuber.py` 17 項，加上 `test_production_channels.py` 的 `test_mascot_step_passes_the_pngtuber_pack` 1 項。用合成角色測：組包、載入錯誤、pose 對照、嘴型遲滯、驚訝不眨眼、兩種 placement 的禁區，加上禁區反例、快取，以及 channel 的 host 驗證。
- 改了 3 項既有測試，它們原本把 cel 當成「沒有角色的頻道」：`test_production_channels`、`test_launch_rules`（兩處）。改成明確建一個 `rig_ready: false` 的頻道當對照，原本的測試意義保留。
- 全套：1 failed（`test_multi_provider…returns_first_provider_results`，基準既有，十幾份報告都記過）／1184 passed／1 skipped 🟢。基準 launch-fixes 是 1166 passed。

### 3-5b. 嘴型修正（Leon 看完試片後，2026-10-17）

- **問題**：
  - C09 原本的嘴是眼睛下方那條小橫線（Leon 說的小 u），但生成的張嘴圖把嘴畫在更下面，說話時嘴跑位。
  - O25 生成的張嘴跟角色不搭。
- **做法**：每個角色包新增 `mouth_mode` 設定，三種值：
  - `frames`：用生成的嘴，Y14 維持這個；
  - `none`：嘴不動，只靠說話時的輕微彈跳；
  - `small_o`：說話時，用周圍顏色（羽化邊緣）蓋掉原本的嘴，再在**同一個中心點**畫一個小「o」，半開和全開只差大小。這是程式畫的，不靠生成，所以不會再跑位。
- C09、O25 改成 `small_o`。嘴的中心點是在 base 上實際量的：C09 是 (386,378)，O25 是 (393,430)，記錄在 `tools/r3_pack.py` 的 `MOUTHS`。
- 重渲兩支試片（覆蓋原檔，路徑不變）：
  - cel 20 秒：600 格，meta 0、字幕 0；
  - Short 24.3 秒：730 格，字幕 0。
  - 截圖已更新 🟢。
- 測試：新增 3 項，包括「o 的重心落在原嘴中心 ±2 px」、`none` 時張嘴與閉嘴的合成結果完全相同、模式驗證。PNGtuber 測試共 20 項全過 🟢。
- 已知殘留：放大看時，O25 舊嘴角兩端有極淡的痕跡；在影片尺寸下看不出來 🟡。

### 3-6. 已知限制與需要 Leon 決定的事

1. **妖怪 deck 要開始寫 mascot pose**：九尾狐 deck 是 0/29，yokai 一開 rig_ready，policy 就會報 `mascot_presence` error，門檻是 80%。cel-ep1 是 24/28，沒問題。我**沒有改**九尾狐的 deck。
2. **說話疊在表情上會有小接縫**：例如青蛙「得意＋說話」時，臉頰紅暈會在嘴框邊緣被切掉。要完全消除，得為每個表情各做一組嘴型，每角色多 6 張差分。這次沒做。
3. **靜態圖沒有手勢**：point、wave 只會換嘴型。如果要指圖表，要另外生成「指」的整張姿勢圖，並接受剪影會跳一下。
4. **9:16 的左下角**跟 YouTube Shorts 的標題、頻道名疊層重疊。這是原本晶片貓就在的位置，我沿用；如果要更保險，可以往上移到字幕帶和 UI 之間，但空間很擠。
5. **mascot 步驟沒有加 identity**：加了的話，所有已完成的晶片貓 run 都會被判定要重渲。代價是頻道換角色包時不會自動重跑，要手動刪 `assembly/final.mp4` 或強制重跑那一步。
6. **著作權**：角色本體是純 AI 產出，可能不受著作權保護，品牌保護較弱。角色包的 `manifest.json` 有記錄來源模型和授權（klein 4B，Apache-2.0）。三個頻道的 `ai_disclosure` 本來就是 true。
7. 角色包圖檔共 5.4 MB，放在 `src/` 底下，會 commit 進 public repo。

## TL;DR（第二輪，2026-10-17）

- Leon 覺得第一輪「好醜」，所以改做法：先寫設計原則（`round2/principles.md`），再用本機 FLUX.2 klein 4B 每頻道生 25 張，共 **75 張**，全部成功 🟢。
- **提示詞裡沒有任何 IP、角色或作者名**：每次生圖前跑禁字檢查（43 個詞），檢查器自己也測過反例，確定抓得到違規 🟢。完整提示詞在 `round2/prompts.json`。
- 每頻道挑了前十（牆上的粉框），每張寫了跟知名 IP 的差異。**淘汰 4 張**：Y24、Y17 像遊戲裡的直立水系烏龜，O18 像知名動畫倉鼠，C14 生成了金髮 Q 版女孩。另外 Y08、Y19、C19、O13 標了相似度提醒。
- 我的首推 🟡：**Y10 說書貓（死魚眼加斗笠）、O05 珍奶上班族、C05 鉛筆刺蝟**。最貼 Leon 舉例的「台式吐槽感＋招牌部件」。
- 請 Leon 直接回編號。選定後再決定要直接用 AI 角色做 PNGtuber 差分（第一輪已驗證可行），還是委託繪師依選定版重繪。

## 第二輪：做法與結果

### 1. 原則先行

`round2/principles.md` 逐一分析三類參考 IP 的輪廓、頭身比、眼睛、配色數、線條、表情誇張度、個性和可延伸性，整理成 P1–P10 共 10 條原則，每條都附上對應的英文提示詞片段。全文是設計分析 🟡，沒有引用一手資料。另外有一段「第一輪為什麼醜」的對照：
- 直瞳、琥珀眼太兇；
- 一隻角色 5–7 色；
- 線寬有三種；
- 道具把剪影吃掉。

### 2. 生成

- 提示詞＝6 種畫風描述 × 每頻道 25 個物種或物件。畫風包括：療癒圓團、台式死魚眼手繪、粗框招牌剪影、水墨筆線、動畫原畫鉛筆、漫畫貼紙。每張配一句一行人設。全部寫在 `tools/r2_prompts.py`；生成時固定每張的 seed，可以重跑。
- 禁字檢查：`check_prompts()` 比對 43 個詞，包括 IP 名、角色名、作者名、出版社、「in the style of」「style of」「inspired by」，以及中文的 IP 名。檢查器內建兩個反例（英文、中文各一），反例沒被抓到就直接報錯 🟢。
- 生圖閘門：每張生成前檢查兩件事：
  - 有沒有 ffmpeg、remotion、mflux、mlx_video 程序在跑。用 `wan.busy_processes`，比對的是執行檔，不是其他程序參數裡的文字。我拿一條假的 ps 輸出驗過：真的 mflux 程序會擋，`grep mflux` 不會擋 🟢。
  - `memory_pressure -Q` 的 free 是否 ≥25%。
  - 一次只生一張。
- 實測 🟢：75 張的 rc 全部是 0，每張 10.8–16.4 s（平均 13.2 s），等待 0 s，峰值 5.77 GB。

### 3. 前十與相似度把關（摘要，完整在 `round2/review.json`，牆上每張卡片也有）

| 頻道 | 前十（依序） | 淘汰 | 提醒 |
|---|---|---|---|
| 妖怪溯源所 | Y10 說書貓、Y05 印章仔、Y16 古籍頁鬼、Y04 符紙精、Y02 獬豸幼獸、Y13 羅盤精、Y07 貓頭鷹、Y11 蠟燭精、Y21 山羊、Y03 書蟲 | Y24、Y17（直立卡通烏龜） | Y08、Y19（黑團加白眼，會聯想到煤灰精靈）；Y02 和首爾獬豸吉祥物的比對 🔴 未查證 |
| 晶片貓下班了 | O05 珍奶、O08 豆腐、O01 下班貓、O24 泡麵、O20 吐司、O06 融化史萊姆、O14 仙人掌、O09 水豚、O04 河豚、O03 便利貼 | O18（橘白倉鼠） | O13 癱平海豹（風險低） |
| 賽璐璐研究室 | C05 鉛筆刺蝟、C01 底片格、C06 章魚原畫師、C18 研究員貓、C20 攝影表、C22 河狸、C16 廢稿紙團、C23 碼錶、C15 熊貓會計、C21 青蛙 | C14（變成 Q 版人類女孩） | C19（淺藍圓鳥，會聯想到社群平台的藍鳥） |

相似度判斷都是我看圖的結果 🟡，沒有做以圖搜圖（不開瀏覽器）。前十之外，**淘汰和提醒只代表「我看得出來的」**；生成模型會往常見造型靠攏，正式選定前最好再請人看一次。

prompt 沒有照做的（另外標在卡片上）：
- Y01 沒畫出燈籠；
- Y25 皮影戲偶沒成形；
- Y21 單角變成雙角；
- O11、C12 變成人形；
- Y17 石碑沒畫出來。

### 4. 下一步要 Leon 決定

1. **回編號**：每頻道 1 款，或「A 的造型＋B 的道具」這種合併指示。
2. 選定後走哪條路：
   - (a) **直接用 AI 角色**：PNGtuber 差分，第一輪已驗證，用定裝圖當參考做表情編輯，剪影 IoU 0.997–0.999。每角色約 0.5 天，共用疊加器約 1–1.5 天；沒有著作權。
   - (b) **委託繪師依選定版重繪**：可以拿到著作權，部件也能照 rig 規格交付。預算參考 mascot-quality 報告的 NT$1–3 萬 🟡。
3. 晶片貓本體要不要照原則修：改點點眼、砍色數、砍電路紋。principles.md §3 有方向，這輪沒有動。

### 5. 第二輪的副作用

- 原圖（768 px PNG）和紀錄在 `~/.claude/jobs/a7f5fad7/tmp/r2-raw/`（75 張＋`runs.jsonl`），會隨 job 刪除。repo 裡只 commit 640 px JPEG（`round2/img/`，連同頁面共 5.2 MB）。
- 手機寬度（390 px）的 headless 檢查：75 張卡片、壞圖 0、沒有水平捲動 🟢。

---

# 第一輪（2026-10-17 稍早）

## TL;DR（第一輪）

- 9 款概念都做完了：每頻道 2 款向量（部件照晶片貓 rig 分層，可以直接 rig）＋1 款 AI 點陣（PNGtuber）。每款都有定裝圖＋2 個表情，也都有一張 1920×1080 實景圖。另做一張晶片貓實景當對照，用的是真 rig＋真 motion 截圖。🟢
- 10 張實景圖都量過：角色像素進入字幕帶和 meta 列的數量全部是 0 🟢（`frames.json`）。O1 第一版的 PM 狗壓到 meta 列 1229 px，是量測抓到的，已經修正。
- AI 路線（klein 4B，用定裝圖當參考圖做編輯）的一致性比預期好：表情差分的剪影 IoU 是 0.997–0.999，不給參考圖時只剩 0.73–0.87 🟢。只換臉的 PNGtuber 可行；換姿勢會掉到 0.91–0.93，而且開始出現瑕疵。
- 建議首選：**妖怪＝Y2 小豸**（先比對首爾 Haechi，必要時退 Y1）、**下班＝O1 下班貓＋PM 狗**、**賽璐璐＝C1 格仔**。三款都走向量。AI 路線適合「先上片、之後再重繪」，不適合當長期 IP 定稿（著作權、動作能力）。
- 要 Leon 決定：選哪 3 款、AI 角色要不要進正式片、offwork 的 9:16 角色位置、可疑的相似風險（Y2／Y3／C2）要不要先做人工比對。

## 1. 做了什麼、在哪裡

| 產物 | 路徑（都在 `docs/design/channel-hosts/`） |
|---|---|
| 選稿頁 | `index.html`：三頻道各 3 款，有定裝、實景、人設、配色、風險和 rig 估計；另附晶片貓對照和 AI 一致性表 |
| 向量原檔 | `svg/<id>_<表情>.svg`（18 張）、`png/`（2x 透明）、`sheet_vector.png`（品牌底色總覽） |
| AI 差分 | `ai/<頻道>_<狀態>.png`：已去背、512 px，狀態有 base／blink／talk／surprised／smug／wave／drift／alt。另有 `ai/sheet_<頻道>.png`、`ai/consistency.json` |
| 實景圖 | `frames/{y1..c3,chipcat}.jpg`、`frames.json`（每張的角色 bbox 和禁區像素數） |
| 產生器 | `tools/`：`common.py`、`chars_{yokai,offwork,cel}.py`（向量）、`render_svgs.py`、`ai_gen.py`（生圖）、`cutout.py`、`ai_sheet.py`、`frames.py`、`concepts.py`、`build_index.py` |

重跑方式（都在 worktree 根目錄執行，`PYTHONPATH=<worktree>/src`，python 用 `.venv`）：

```
python docs/design/channel-hosts/tools/render_svgs.py
python docs/design/channel-hosts/tools/ai_gen.py base|edits|drift <raw_dir> [yokai=23 offwork=11 cel=23]
python docs/design/channel-hosts/tools/ai_sheet.py <raw_dir>
python docs/design/channel-hosts/tools/frames.py <raw_dir> <work_dir>
python docs/design/channel-hosts/tools/build_index.py
```

**向量的畫法規格**跟晶片貓 rig 一致：
- 400×440 角色框，地面錨點 (200,410)；
- 整隻角色共用一個 sticker filter，負責外框線、亮邊和陰影；offwork 改成硬投影、不模糊，照品牌規則；
- 部件分組命名：`body/head/earL/earR/eyeL/eyeR/brows/mouth/armL/armR/tail/prop/fx`；
- 換表情時只換 eyes／brows／mouth／fx，其他部件不動，所以第二階段可以直接沿用 `params.py` 的參數命名。
- Y1、O1 的貓是把 `rig.html` 的頭、耳、身體、尾巴路徑原樣搬過來再加衣服，確定是同一隻貓。

**實景圖**：
- 背景用真的 explainer 模板（`build_pages`，brand=<頻道>，`docs/examples/brands/<頻道>.json` 第 2 頁）乾淨重拍，沒有剪影佔位；
- 角色錨在右下角 (1908,1072)，高度約 352 px，晶片貓本體在畫面上約 356 px，兩者相近；
- 字幕是 52 pt 的示意字。
- 晶片貓對照圖是真的 `compose_frames`＋`rig.html` 截圖，貼在 production overlay 的原點 `ORIGIN`。

## 2. 九款概念

詳細人設、個性、口頭禪、配色和理由都在 `index.html` 和 `tools/concepts.py`，這裡只列摘要。

| id | 頻道 | 路線 | 名字 | 一句人設 | 口頭禪 | 第二階段估計 | 主要風險 |
|---|---|---|---|---|---|---|---|
| Y1 | 妖怪 | 向量 | 說書貓・阿燈 | 晶片貓換上斗笠、斗篷、提燈，到古書堆打工 | 「燈先點上——我們從最早的那一本講起。」 | **0.5–1 天**：套現有 rig，加 3 個圖層 | 頻道辨識全靠道具；三個頻道同一隻貓 |
| Y2 | 妖怪 | 向量 | 小豸（獬豸） | 能辨是非的獨角神獸，專門頂翻查無出處的說法 | 「出處呢？」 | **2–3 天**：新 rig，結構和貓相同 | 首爾市吉祥物 Haechi 也是 Q 版獬豸 🔴 待比對 |
| Y3 | 妖怪 | AI | 蠹先生 | 住在古籍裡幾百年的書蟲學究 | 「這一版我吃過，味道不對。」 | PNGtuber：每角色 0.5 天，外加共用疊加器 1–1.5 天 | 剪影像龍貓 🟡；沒有著作權 |
| O1 | 下班 | 向量 | 下班貓＋PM 狗 | 帽 T 貓捧馬克杯；PM 狗下班前五分鐘探頭 | 「……我已經下班了。」／「這個應該很快吧？」 | **2.5–3.5 天**：貓 0.5–1 天、狗 1–1.5 天、雙角色 cue 1 天 | 佔畫面；9:16 的位置要另外定 |
| O2 | 下班 | 向量 | 便利貼精・黏黏 | 被貼在螢幕邊三年的待辦便利貼 | 「這件事……明天再說。」 | **1–1.5 天** | 跟晶片貓 IP 脫鉤 |
| O3 | 下班 | AI | 河豚上班族・氣氣 | 一被交辦就氣到膨脹 | 「我沒有生氣，我只是……有點腫。」 | PNGtuber；「膨脹」要另外生成差分 | 招牌動作靠 AI 重生，不一定是同一隻 |
| C1 | 賽璐璐 | 向量 | 格仔 | 從舊底片剪下來的一格，幫研究室對帳 | 「一秒 24 格，這一格是我。」 | **1–1.5 天** | 親和力比人形角色低 |
| C2 | 賽璐璐 | 向量 | 芮秒研究員 | Q 版研究員，抱著攝影表對帳 | 「這筆帳，對不起來。」 | **3–4 天**（頭髮、眼鏡、手勢） | Q 版人類很難保證「不像任何角色」🔴 |
| C3 | 賽璐璐 | AI | 透透 | 被遺忘在倉庫的賽璐璐片 | 「我那個年代，一張一張都是手塗的。」 | PNGtuber | 接近通用的床單幽靈，辨識度低；沒畫出透明感 |

估計天數都是 🟡，是我照 Route A 的經驗推估，沒有實測。估計範圍是「接進現有 motion／overlay、跑出姿勢 stills」，不含繪師級的修稿。

## 3. 向量 vs AI 點陣（orchestrator 追加的比較）

| 面向 | 向量（Y1/Y2/O1/O2/C1/C2） | AI 點陣・PNGtuber（Y3/O3/C3） |
|---|---|---|
| **一致性** | 完全一致：同一組部件，換的只是 eyes／mouth 🟢 | 用定裝圖當參考圖做表情差分：剪影 IoU **0.997–0.999**，重疊區 RGB 差 5–14 🟢。換姿勢（wave）：IoU **0.906–0.931**，而且 Y3 揮手時卷軸不見了、C3 多出一條雜線。不給參考圖（同 prompt 換 seed）：IoU **0.73–0.87**、RGB 差 26–65，就是「同品種的另一隻」 🟢 |
| **動作能力** | 參數連續：頭部轉向、呼吸、眨眼、嘴型 0–1 連續、耳朵物理、指圖表手臂，現有 motion 全部能用 | 只能換幀：開口／閉口兩格、眨眼一格、表情幾格；再用整張的呼吸縮放和左右擺動。沒有轉頭，手勢要另外生成，而且每張都可能有瑕疵 |
| **嘴型** | `ParamMouthOpenY` 連續，跟現有 lipsync 直接接 | 二值（張／閉），看起來是 PNGtuber 的跳動感。差分整張重生時，身體紋理會微微閃（RGB 差 5–14），建議只把臉部區域貼回 base |
| **製作時間** | 一款概念（3 表情）約 1–2 小時手寫 SVG；第二階段 rig 0.5–4 天 | 生圖本身很快：base 平均 **12.5 s**、編輯平均 **28.4 s**，峰值 5.84 GB，等待記憶體 0 s 🟢。一個角色 base 加 5 張差分約 3 分鐘。但挑圖、去背、修邊每角色約 0.5 天，PNG 疊加器（三角色共用）約 1–1.5 天 🟡 |
| **畫面質感** | 乾淨的 Q 版向量，到不了手繪質感 | 質感比較好，特別是水墨（Y3）。品牌細節不一定照做，例如 O3 沒有硬投影 |
| **著作權／品牌保護** | 人類創作，可以受保護，也能申請商標 🟡 | 純 AI 輸出可能**沒有著作權** 🔴（USCO 2025-01 和日本文化庁的立場，見 `design/mascot-quality` 報告 §1，二手）。品牌保護弱：別人可以照抄，我們很難主張權利 |
| **相似風險** | 可控，因為每條線都是自己畫的 | 模型會往常見造型靠攏：Y3 的剪影像龍貓、C3 是通用幽靈。prompt 裡寫的「not resembling…」沒有約束力 🟡 |
| **授權** | 無 | klein 4B 是 Apache-2.0 🟢（`REPORT-ai-trial.md` 讀過 LICENSE 原文）。生成紀錄在 `ai-raw/runs.jsonl`（job tmp），正式用要寫進 `credits.json` |

結論 🟡（判斷，不是可驗證的宣稱）：AI 點陣路線可以快速做出「會眨眼、會張嘴的主持人」，一致性也夠拿來換幀。但動作上限低，做不出指圖表、轉頭這類動作，而且沒有著作權。適合兩種用途：(a) 頻道開台前的過渡；(b) 當造型參考，再由人重繪成向量。不適合當長期 IP 的定稿。

## 4. 建議首選

| 頻道 | 首選 | 理由 | 備選 |
|---|---|---|---|
| 妖怪溯源所 | **Y2 小豸**（先比對 Haechi） | 角色本身就是東亞神話，「出處呢？」直接是頻道的招牌提問。胸前的「真」字硃砂印跟頻道印章同一個視覺系統。換一隻非晶片貓的角色，也降低政策審查 D3 說的「跨頻道模板」相似度 | **Y1**：最快（0.5–1 天）、IP 連貫。如果 Haechi 比對結果太像就選這款 |
| 晶片貓下班了 | **O1 下班貓＋PM 狗** | 照品牌註記。雙人相聲是冷笑話的天然結構，晶片貓 IP 延續；品牌的 accent-2 藍本來就是保留給 PM 狗的 | **O2**：最便宜，也最貼品牌視覺 |
| 賽璐璐研究室 | **C1 格仔** | 照 `cel.yaml`。三款中著作權和相似風險最低，這個頻道最怕「像官方角色」。rig 也便宜 | C2 親和力最高，但相似風險和 rig 成本都最高 |

三款首選的第二階段合計約 **5.5–8 天** 🟡。如果妖怪改選 Y1，約 4–5.5 天。

## 5. 需要 Leon 決定的事

1. **選稿**：每頻道選 1 款，或是指定要合併的元素（例如 Y1 的提燈給 Y2）。
2. **AI 角色要不要進正式片**：要的話，需要另外做 PNG 疊加器（約 1–1.5 天），而且要接受沒有著作權、不能指圖表。我建議只當過渡或造型參考。
3. **相似性人工比對**：Y2 vs 首爾 Haechi、Y3 vs 龍貓、C2 vs 常見動畫研究員角色。這三項我只能標風險，無法自己排除（不開瀏覽器）。
4. **offwork 的 9:16**：這個頻道主力是 Shorts。這次照任務做的是 16:9 右下角；Shorts 裡角色要放在下三分之一的中間，還是維持角落，需要決定。
5. **兒童內容風險**：政策審查 A6 指出，下班 Shorts 和妖怪圖鑑卡在視覺上最像兒童內容。Q 版角色會再加重這一點。主題和用語要維持成人向，並把理由寫進 yaml。

## 6. 證據等級

- 🟢 本機可重跑：
  - 向量 SVG 和 PNG 輸出；
  - 10 張實景圖的禁區像素數（`frames.json`；偵測器有實際抓到 O1 的 1229 px 和 64 px，**不是只會回 0**）；
  - AI 生圖的耗時和記憶體（`runs.jsonl` 共 24 筆，rc 全 0）；
  - IoU 和 RGB 差（`ai/consistency.json`），其中 drift／alt 是對照組，數值明顯較差，證明這個量測分得出差異；
  - `index.html` 引用的 40 個檔案全部存在，headless 截圖顯示壞圖 0 張。
- 🟡 判斷或推估：rig 天數、首選建議、「像龍貓」、AI 路線適合過渡。
- 🔴 未驗：
  - Haechi 的實際造型（沒有查證）；
  - AI 輸出的著作權地位（二手）；
  - C2 是否像特定角色。
  - 這三項不能當決策依據，要先做人工比對或查原文。

## 7. 副作用與清理

- 生圖原圖和紀錄放在 job tmp：`~/.claude/jobs/a7f5fad7/tmp/ai-raw/`（24 張＋`runs.jsonl`）、`frames-work/`（渲染中間檔）、`index_shot.png`，會隨 job 刪除。repo 裡只 commit 縮小後的去背版。
- mflux venv 和 klein 權重沿用 `d3bbd556`、`f9ab0177` 兩個 job 的 tmp，只讀，沒有搬動。**它們仍然只寄放在別人的 job tmp**，前兩份報告已經提醒過要搬到持久位置。
- 沒有動 `src/`、`tests/`、`.env`、`main`、`feat/explainer-v2`；沒有 push。
- `docs/` 在 `.gitignore` 裡，所以設計檔用 `git add -f` 加入，跟前幾支設計分支的做法相同。
- 沒有跑 pytest：沒有改 `src/` 或 `tests/`。
- `CLAIMS.jsonl`：分支繼承了 `feat/launch-fixes` 的版本，我換成本 job 的版本。原檔完整保留在 `48e2f70`，merge 回去時要留意。
- worktree 裡有未追蹤的 `graft/`（開工時就在，是 graft 索引，不是我產生的），沒有 commit 也沒有刪。
- 沒有開瀏覽器（Chromium 只用 headless 渲染投影片和 SVG，跟 pipeline 的做法相同）；沒有用付費 API。
