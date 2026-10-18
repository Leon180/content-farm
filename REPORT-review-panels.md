# REPORT — 評審團接進 pipeline（feat/review-panels）

## TL;DR
（進行中，完成後改寫）

## 進度紀錄（append）
- 2026-10-18 分支 `feat/review-panels` 從 `feat/cowos-v3` d288a04 開（已含 channel-voices a5a4e41、design/channel-hosts a6885eb）。
  `feat/incremental-render` 當下與 cowos-v3 同點（2030c1e 起無新 commit）→ 句子 id 欄位先放 `review_panels.yaml: sentence_id_field`。
- 查證 `claude` CLI 2.1.299（只讀 binary 字串，worker 的 Bash 跑 `claude --help` 被權限擋下，原文：
  `Permission to use Bash with command claude --help has been denied.`）：有 `--json-schema`、`--effort`、`--output-format json`
  （結果欄位 `structured_output`）、`--no-session-persistence`、`--strict-mcp-config`、`--allowed-tools`、`--permission-mode dontAsk`。
  **`--bare` 不能用**：binary 說明原文「Anthropic auth is strictly ANTHROPIC_API_KEY or apiKeyHelper … (OAuth and keychain are never read)」
  ＝會走按量計費。評審子程序一律不帶 `--bare`，並從子程序環境移除 `ANTHROPIC_API_KEY`／`CF_ANTHROPIC_API_KEY`。
- 03:17–12:36 無進度（orchestrator 推測夜間斷線）；12:37 接續。
- 12:37 commit：`review_panels.yaml` 的 `review:` 段＋`review/config.py` 硬規則（必要角色、事實查核 opus·high、層級下限、門檻下限、輪數上限；頻道覆寫只能更嚴）＋測試。
- 13:xx 實測 `claude -p` 子程序（haiku·low、極小 schema）：4.6 s、`structured_output` 正確、`modelUsage` 為 `claude-haiku-5-5`、provider firstParty（未帶 API key ＝訂閱）。
- commit：評審 client／素材／判定／退回路由／panel gate（26 測試）。
- **事故（已處理）**：接 runner 後第一次跑全套 pytest，一個舊 runner 測試走到閘門、真的啟動了 3 個 opus 評審子程序（`pgrep` 看到 `claude -p --model opus …`）；
  停掉 pytest 並 `pkill` 後確認已無殘留。修正：`tests/conftest.py` autouse 把 `CF_CLAUDE_BIN` 指到會 exit 97 的 stub（測試永遠不會叫到真 claude），
  並有測試驗證 stub 生效。
- commit：runner 接評審團（topic／title 閘門、全部閘門不可關、手動 approve 需 `--override` 並記 log、退回標 rework、`--auto-agents`）、
  全機重工作佇列 `lanes/queue.py`＋`produce.py queue`；全套 1357 passed（基準失敗 1 個已排除）。
- 付費路徑擋下（`llm/paid.py`、LLMClient 建構時檢查 `CF_ALLOW_PAID=1`、三支腳本需 `--allow-paid`）、上片排程（`publish_slot.py`＋四頻道 `publish:`）、
  `scripts/check.sh`＋`.pre-commit-config.yaml`（負控制：把 article 事實查核改 sonnet → check.sh 退出 1，已還原）。
- 13:32 斷網：選題產出 agent（claude -p）卡住 1 小時無輸出 → 14:2x kill（runner 正確回報 `exit 143`）、加逐步 timeout＋重試 1 次後重開。
- 14:3x **ffmpeg × TTS 重疊實測**（`scripts/bench_overlap.py`，持有佇列 slot、無其他重工作、free 85%；VoxCPM2 6 句＋libx264 medium 60 s 片段，n=1）🟢：
  TTS 單獨 93.4 s（暖機後每句中位 13.4 s）、重疊 107.1 s（16.4 s／句）＝ **TTS 慢 1.22×**；ffmpeg 單獨 7.6–8.0 s、重疊 9.5–25.0 s（中位 ≈22 s）＝ **ffmpeg 慢 2.86×**。
  沒有出現 mflux×TTS 那種 20 倍崩潰；同樣的工作串行要 ≈140 s、重疊 107 s（省 ≈24%）。結論見報告「兩條車道」。
- `voice_batch.py`（同 provider 共用一個 TTS worker）、`produce.py review --tier`（全 opus 對照用的旁輪，不影響閘門）。
- **驗收第 1 次（`output/chipcat-rp1`）**：
  - 選題：產出 agent 195 s 出 12 題；評審團 5 人（觀眾 sonnet×3、編劇 opus、製作人 opus）第 1 輪過，牆鐘 99 s、名目 $0.67；
    選中 t03「卡在一塊布：AI 伺服器為什麼缺玻璃纖維布」（綜合 7.96，第二名 7.12）。
  - 文章：產出 549 s → 第 1 輪（查核 opus×2 互不參考＋編劇 opus·medium）290 s、$2.01：兩位各找到 3 個錯誤／無來源，退回 → 重寫 378 s →
    第 2 輪 253 s、$2.08：3 個／8 個 → **2 輪用完，卡在第 2 步**（runner 正確以 failed 停下，沒有開閘）。
  - 查核內容是真問題（可驗證）：「台灣唯一」被放大成「日本以外全球唯一」、兩任社長被寫成同一人前後改口、載板廠被寫成受害者但來源說毛利創高、
    「預定完工」寫成已完工、報導刊登日當成事件日、自己的 ppm 換算掛了來源標記。第 2 輪新增的錯誤多來自改寫時新加的句子。
  - 歸因：產出 agent 沒有交件前自我查核，且 `check_article.py` 因 Bash 允許規則太窄跑不了（已修：絕對 PYTHONPATH＋前綴規則）。
    修正（程式，不動門檻）：文章 brief 加逐條自我查核清單；退回 brief 加「新寫的句子一樣會被查」。
  - 第 2 次嘗試在 `output/chipcat-rp2`，沿用同一批 12 個候選，選題由評審團重新決定。
