# REPORT — 分段增量渲染＋角色疊加加速

## TL;DR
（進行中，收工前改寫）

## 進度紀錄（append）
- 2026-10-18 分支 `feat/incremental-render` 從 `feat/cowos-v3` 2030c1e 開（worktree `cf-incremental-render`）。
- 讀過：`production/steps.py`（deck → voice → media → assembly → mascot → mix）、`media_run.py`／`media.py`（每張 12–29 s，
  24 張合計約 425 s＋轉場／縮圖約 80 s）、`mascot/*`（向量 rig 用 Playwright 逐格截圖；15k 格全部 unique，2 workers 約 490–630 s，
  overlay 42–73 s）、`voice/generator.py`（已有逐場景 identity 快取，單位是「整張投影片的旁白」，不是句子）。
- 角色動作目前依賴全片時間（眨眼／頭部事件／物理彈簧都以整支 duration 與全域 t 計算）→ 要逐場景快取，必須先改成場景本地時間。
