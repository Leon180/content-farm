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
