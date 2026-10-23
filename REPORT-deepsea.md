# REPORT — 深海生物頻道（深潛日誌）＋第一支長片＋1 支 Shorts

## TL;DR
（進行中，收工時改寫）

## 進度紀錄
- 2026-10-24：分支 `worktree-cf-deepsea` ff 到 `worktree-cf-visual-v4`（a082593）；頻道設定、品牌、abyss 配樂、評審人設、選題池、測試完成並 commit。
- 聲音設計已送 `scripts/heavy` 佇列（seed 5000–5005），等記憶體（需 19.5 GB＋3 GB 餘裕）。
- 長片 run：`output/deepsea-1`（`--auto-agents --budget-usd 20`），先跑到 `gate_deck_facts`。

## 1. 頻道設定
- code `deepsea`，暫名「深潛日誌」；候選：深潛日誌／深海圖鑑／往下一千公尺。
- 品牌 `deepsea`：深海藍黑底、生物發光青強調、左側深度標尺；無角色（`rig_ready: false`）。
- AI 插圖：`z-image-turbo`（本機，與 cel 同；klein 權重不在離線快取），科學圖鑑風，禁擬真照片、禁指定畫家。
- 配樂：新增 `abyss` 預設（`audio_mix/synth_bgm.py`）：D 小調超低頻持續音＋緩慢和聲＋稀疏聲納鈴音，本機合成、可無縫循環。
- 評審：visual-v4 規則（腳本評審一次＋改稿一次、正確性查核信心度 ≥0.5）；`channels.deepsea` 覆寫事實與授權不放行。
- 測試：test_explainer_brands／test_production_channels／test_synth_bgm／test_review_config 全過。
