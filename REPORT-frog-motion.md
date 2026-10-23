# REPORT — 青蛙書記講話動作診斷與三個替代版本

## TL;DR
- 「怪」的主因有三個，都是數字能證明的：**講話時嘴有 90% 的時間是張到最大的大 O 嘴**（half 只佔 9%）；**嘴部貼片是矩形，會蓋掉 smug／speechless／surprised 表情**（60% 的畫格是這三種表情，嘴型與表情互相打架，smug 的腮紅被切一半）；**身體以腳為軸整隻剛體搖擺＋每格跟包絡跳**。
- 做了 3 個可切換的 motion profile：`calm`、`nod`、`beat`，預設仍是 `legacy`（現行），其他頻道不受影響。
- 推薦 **`nod`**（只動頭、身體不晃，最像「講解員」）；`beat` 是較活潑的備案。我只看了逐格與數字，沒有親眼看影片播放，最後請 Leon 看對照片定。
- 沒有重畫任何東西。嘴部貼片本身的問題（矩形邊緣、表情×嘴型不相容）靠程式只能繞開，**真正的解法是重生表情×嘴型貼片，那是美術決定，等 Leon 說**。

## 診斷（證據等級：🟢 本機實測可重跑）
來源：`yokai-kyubi-v2/assembly/host.mov`（成片的 alpha 層，30fps，20460 格）與同一支包絡（`mouth_for_run`）。重跑腳本：[diag.py](artifacts/frog-motion/diagnosis/diag.py)（路徑寫死在 cf-cost-accept）。

| # | 項目 | 證據 | 判斷 |
|---|---|---|---|
| 1 | 嘴型分佈 🟢 | 講話格中 closed 1%／half 9%／open **90%**（全片 21／8／71%）。包絡中位數 0.78，`MOUTH_OPEN_AT=0.45` 幾乎一直超過 | 主因。嘴大張的「尖叫臉」是常態，沒有節奏可言 |
| 2 | 嘴型切換 🟢 | 每講話秒 3.0 次切換；**41% 的嘴型只停 ≤2 格**（中位 5 格） | 一邊長時間張著、一邊 1–2 格閃爍，兩極 |
| 3 | 嘴型本身 🟢 | [faces.png](artifacts/frog-motion/diagnosis/faces.png)：closed 是寬扁的微笑線，open 是窄圓大 O，位置與形狀都不是同一條嘴張開；half 是偏下的小舌頭嘴 | closed→half→open 不是連續的張合，切換像換貼圖 |
| 4 | 貼片蓋掉表情 🟢 | [expr_grid.png](artifacts/frog-motion/diagnosis/expr_grid.png)：`Composer.face` 對所有表情都疊 mouth 貼片（`render.py` face()）；smug 的腮紅被矩形切掉、speechless 半瞇眼配大 O。全片畫格的表情分佈：speechless 41%、neutral 39%、smug 11%、surprised 9% | 約 60% 的時間嘴與表情不一致 |
| 5 | 貼片矩形邊緣 🟢 | mouth 貼片 262×124 px 羽化矩形（對照 faces.png 第 3 張），貼片內臉部膚色／肚皮交界與底圖略有色差，張嘴格可見淡淡方塊 | 美術問題，程式無法修 |
| 6 | 身體搖擺 🟢 | `SWAY_DEG=1.4°`、週期 5.3s，以腳為軸整隻旋轉：頭部左右位移 12px（x 311→323，2 秒內），腳不動 | 像倒單擺，青蛙站著不該這樣 |
| 7 | 彈跳 🟢 | `lift = 6px × 包絡`，逐格跟：頭頂 y 在 170–179 之間每格 ±1–3px 抖（`[176,178,178,…,175,174,174,175,174…]`），每格 lift 變化 p95 1.56px、最大 3.9px | 抖動而非彈跳；與呼吸（頭頂 6px）、搖擺疊加後方向不一致 |
| 8 | 逐格重取樣 🟢 | 每格對整張圖 BILINEAR 縮放＋BICUBIC 旋轉（`render.py` canvas()） | 輪廓線會微糊、閃；梯度均值 6.1–7.1，無明顯崩壞，🟡 影響小 |
| 9 | 2.5D 變形 | frog-scribe 是平面包，沒有 depth.png，`depth is None` | **不是原因**（診斷時排除） |
| 10 | 眨眼 🟢 | 佔 2% 的格；blink 貼片（245–529×174–261）會改到眼球外輪廓 | 小問題，未動 |
| 11 | 身體完全不動 | 手與筆是底圖的一部分，無法單獨動 | 受限於素材；`nod`／`beat` 用「頭部位移、腳釘住」模擬 |

知識庫（只讀）：`motion-design-skill`、`claude-motion-design` 兩則都只是狀態「待評估」的外部 skill 摘要，沒有可直接套用的角色動畫規則（前者對象是 UI 動效、後者未實測）。這裡用的原則（動作要跟聲音的節奏而非每格振幅、次要動作要小於主要動作、重心／腳要有支點）是通用動畫常識，不是從知識庫的實測來的 🟡。

## 三個版本（皆不換造型；`src/content_farm/explainer/pngtuber/profiles.py`）
| profile | 嘴型 | 身體／頭 | 其他 |
|---|---|---|---|
| `legacy`（現行） | half 0.12／open 0.45，hold 2 | 彈跳 6px×包絡、搖擺 1.4°、呼吸 1.8% | 預設，數值與先前逐項相同 |
| `calm` | half 0.40／open 0.84，hold 4，大嘴最多連續 6 格後回 half | 包絡平滑 9 格，彈跳 2.5px，搖擺 0.5°，呼吸 1.2% | 非 neutral 表情不套嘴貼片（保留表情自己的臉） |
| `nod` | 同 calm | **身體剛性不動**；頭部（腳釘住）隨聲音下點最多 5px，慢速左右漂移 3px（週期 6.1s） | 同 calm 的嘴規則 |
| `beat` | 同 calm | 每個聲音起音（約 1.9 次／講話秒）一次 7 格的緩動小跳 7px＋拉伸 3%，落地 4 格壓扁；頭下點 2.5px、漂移 2px | 無連續彈跳、無搖擺 |

講話格的嘴型分佈（calm／nod／beat，neutral 且講話時）：closed 6%／half 63%／**open 30%**，約 5.4 次切換／秒，沒有 ≤2 格的閃爍。

新增程式：
- `profiles.py`（新）：`MotionProfile`、`legacy/calm/nod/beat`、`get_profile`。
- `motion.py`：`mouth_levels` 增加 `half_at/open_at/open_max` 參數（預設＝舊值）；新增 `smooth`、`beat_track`；`HostFrame` 增 `head_dx/head_dy`；`host_frames(profile=LEGACY)`。
- `render.py`：抽出 `remap`（`depth_warp` 改呼叫它，輸出不變），新增 `head_warp`（權重 (1−y/h)²，腳不動）。
- 切換方式：`scripts/mascot_overlay.py --pngtuber pngtuber/frog-scribe --motion-profile nod`；或 channel yaml 的 `mascot.motion_profile: nod`（`channels.py` 驗證名稱、`steps.py` 轉成旗標）。**預設與 `channels/yokai.yaml` 都沒改**，等 Leon 選。
- 測試：`tests/unit/test_pngtuber.py` 新增 5 條（legacy 數值、open_max、beat_track、head_warp 腳釘住、channel 驗證）；`pytest tests/unit/test_pngtuber.py tests/unit/test_production_channels.py` 43 passed，另跑 `-k "step or mascot or shorts or channel or host"` 168 passed。未跑全套（約 1700 條）。

## 對照片（540p，每支 < 400 KB，含原配音）
`artifacts/frog-motion/`，裁切 620×540 的主持人區域（即成片右下角，1:1 = 540p 高）。兩個窗口各 10 秒、各 4 版：
- `frog-think-to-point-{legacy,calm,nod,beat}.mp4`：36–46s，speechless→neutral（表情切換處，看貼片蓋表情的差別）
- `frog-smug-{legacy,calm,nod,beat}.mp4`：58–68s，point→smug（看腮紅被切）
- 逐格對照：[cmp_sheet.png](artifacts/frog-motion/diagnosis/cmp_sheet.png)（上到下 legacy／calm／nod／beat，0.4 秒間隔 ~3fps）。
- 重新渲染：`compare.py` 在 job tmp，沒進 repo；要重做告訴我。

## 推薦：`nod`
理由：問題 6、7 的根源（整隻剛體搖擺、逐格跟包絡跳）被拿掉，只留頭部的小位移，講解類長片（7–10 分鐘）看久不累；`beat` 對 Shorts 或較活潑的段落可能更好，但 10 分鐘長片每秒 2 次跳可能太忙。這是 🟡：我沒有播放影片看實際觀感，請 Leon 看兩組對照片。若覺得「講話嘴沒動」不夠生動（smug／speechless 表情時嘴是固定的），那是設計取捨，要解決就得重生表情貼片。

## 需要美術決定（我沒有做）
1. mouth 貼片的矩形邊緣色差與表情不相容（診斷 4、5）。若要根治：以 smug／speechless／surprised 各自為底，重生 half／open 嘴貼片（或把嘴部改成可縮放的獨立向量嘴）。
2. blink 貼片改到眼球外輪廓（診斷 10）。

## 對其他頻道 PNGtuber 的影響
- 預設 `legacy` 與先前程式路徑數值相同（`LEGACY` 的常數就是 `motion.py` 原常數的來源，有測試鎖住）；offwork（飲水機金魚）、cel（顏料瓶）的 2.5D 包不變。
- `render.py` 的 `depth_warp` 重構為 `remap` 的薄包裝，公式未改；沒有逐像素比對舊輸出（🟡），僅靠既有測試與未變動的 2.5D 路徑。
- `nod`／`beat` 的頭部位移對任何包都能用（不需 depth）；但 2.5D 包用 `calm/nod/beat` 時仍會有 2.5D 的 yaw／nod／squash（那三個沒被 profile 調過）。若想給 2.5D 包用，要另外定 profile。

## 清理
- 暫存都在 `$CLAUDE_JOB_DIR/tmp`，渲染用的 alpha .mov 已刪；沒有殘留測試檔／分支。worktree 裡 `graft/` 是未追蹤的既有索引，沒碰。
- 分支 `worktree-cf-frog-motion` 以 `git merge --ff-only` 快轉到 `worktree-cf-chipcat-run2`（41d462d）再提交；未 push。

## 進度紀錄（交接用）
全部子項完成：診斷 → 3 個 profile → 對照片 → 測試 → 報告。待 Leon 選定後：把選定值寫進 `channels/yokai.yaml` 的 `mascot.motion_profile`（或改 `legacy` 預設），其餘 profile 可刪。
