# REPORT — HN 中文版每日 Shorts＋週長片（晶片貓系列）

（施工中。進度紀錄，完成後改寫成正式報告。）

## 進度
- [x] 分支 `feat/hn-daily` 自 `9e7de1d` 建立（2026-10-16）
- [x] 讀完 v3-common、hn-chinese 調查、policy review、produce.py／steps／runner／shorts_render／manual_kit
- 設計：`src/content_farm/production/news/`；run-dir 以 `news_short.json`／`news_weekly.json` 標記，steps_for 分派（同 short_from_long 模式）
- 發現：repo 內沒有既有「名詞表」檔（git log -S 名詞表／glossary 全分支 0 命中），新建 `production/news/glossary.yaml`
