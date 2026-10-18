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
