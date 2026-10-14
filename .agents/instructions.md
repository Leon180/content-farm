# Antigravity Context: Content-Farm Pipeline

You are Antigravity, an agentic AI coding assistant. This workspace is a highly automated "Content Farm" pipeline that generates short-form videos (YouTube Shorts/Reels/TikToks) from a given topic.

## 核心流程 (Pipeline Stages)
這個專案具備完整且自動化的 7 個執行階段。若使用者要求你執行特定階段，你可以直接調用封裝好的 Python 腳本，無須手寫功能腳本。

指令格式：
`.venv/bin/python scripts/run_stage.py --stage <階段名稱> --run-dir <資料夾路徑>`

1. **Research (研究)**: 針對給定主題進行搜尋，產生具備事實基礎的 `research.md`。
2. **Script (腳本生成)**: 基於研究結果產生 `script.json` 與 `storyboard.txt`。這裡高度要求節奏感與事實根據。
3. **Voice (語音)**: 讀取 `script.json`，透過 TTS (ElevenLabs / Fish Audio 等) 生成旁白，存於 `audio/`。
4. **Visual (視覺)**: 依據腳本的 visual hints，抓取素材或產出底圖，存於 `visual/`。
5. **Subtitle (字幕)**: 根據語音產出時間軸精確的 `subtitles/subtitles.srt`。
6. **Assembly (剪輯合成)**: 使用 FFmpeg 將影像、聲音、字幕合併輸出至 `assembly/`。
7. **Upload (發布)**: 將最終產出的影片自動上傳至 Google Drive 或 YouTube 等。

## 舊版 AI 工具 (Claude Skills) 的繼承
專案根目錄中的 `.claude/skills/` 存放了原先 Claude 使用的技能指引檔案。你可以隨時參考裡面的結構：
- 如果你需要手動幫使用者生腳本，記得先讀 `.claude/skills/script/prompts.md` 與 `hooks.md` 抓腳本語氣。
- 工作目錄的產出皆統一集中在 `output/YYYYMMDD_HHMMSS_<topic>/`。

## Agent 執行守則
1. **先確認狀態**：在執行修改或下一步前，先用 `list_dir` 確認 `output/` 內的進度。
2. **利用現有生態**：專案已經有完整的 tests、scripts 與 src。要除錯時優先使用 pytest 跑對應模組 (`pytest tests/unit/ -v`)。
3. **修改腳本時注意**：如果手動客製化 `script.json`，確保數字轉為國字（如 100 -> 一百）以利 TTS 辨識。
