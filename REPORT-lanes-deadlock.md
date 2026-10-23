# REPORT-lanes-deadlock

## TL;DR
- 死結已修：`voice` 缺參考聲時不登記佇列票（新 `Outcome.PREREQ`，exit 3）；票據新增 `needs`/`provides`，等待者的 anti-starvation 預約與 priority 都不再擋住「供給它的」voice-design。🟢（單元測試）
- 入場：`voice` 18→16.7 GB、新增 `voice_design` 19.5 GB（系統峰值 21.7／24.5 − idle 5）；沒有其他本機重工作時 margin 6→3 GB（雲端步驟不變）。32 GB 機器實測 free 22.7–23.7，voice-design 需 19.5+3=22.5，可排進。🟡（門檻靠測試與實測 free 推算，未實跑 Qwen3）
- 等超過 20 分，`reason` 末尾加「，差 X GB」。
- 全套 pytest：1822 通過、1 skip；唯一失敗 `test_multi_provider`（既有）。

## 改了什麼（commit 見 git log，分支 `worktree-cf-lanes-deadlock`，基底 fb74850）
1. 依賴前置
   - [runner.py](src/content_farm/production/runner.py)：`_missing_voice_reference`；本機複製聲（voxcpm2/qwen3）且 `reference.audio` 不存在 → 回 `Outcome.PREREQ`，訊息指向 `scripts/heavy --step voice_design --provides voice-ref:<channel>`，不呼叫 `render_lock`。
   - `Ticket.needs` / `Ticket.provides`（[queue.py](src/content_farm/lanes/queue.py)）→ `Job`；[resources.py](src/content_farm/lanes/resources.py) `decide` 的 anti-starvation 與 priority 兩條規則排除 `waiting.needs == me.provides` 的票。voice 票自帶 `needs=voice-ref:<channel>`（防競態，例如參考聲中途被刪）。
   - [scripts/heavy](scripts/heavy) 新增 `--provides` / `--needs`。
2. 入場：[heavy_work.json](channels/shared/heavy_work.json) `voice` 16.7、`voice_design` 19.5（gpu exclusive、lock local_tts）、`admission.margin_idle_gb: 3`。`decide` 在「本機步驟且沒有其他本機 running job」時用 `min(margin_idle_gb, margin_gb)`；`impossible()` 也用較小 margin（需求 + 3 > 整機才 ImpossibleNeed）。雲端步驟（reviewer 等）仍用 6 GB，且 running 的雲端 job 不算「本機重工作」。
3. `admission.shortfall_after_s: 1200`；`_machine` 在 `now - me.since ≥ 1200` 時於 memory 原因後加「，差 X GB」（= need + margin − (free − promised)）。
4. 既有測試調整：`test_lanes_resources` 的 `CFG` 明確設 `margin_idle_gb=6`（原測的是完整 margin）；`test_voice_spoken_key` 門檻 18→16。

## 測試
新增 9 個：resources 6（feeder 不被預約擋、priority 不擋、idle margin、雲端 running 不算本機、20 分差額、config 數值與上限）、queue 2（needs/provides 進 Job、starving voice 票下 voice-design 能進、陌生票仍被擋）、runner 2（缺參考聲不登記票且不跑、有參考聲票帶 needs）。
全套：`1822 passed, 1 skipped`；`test_multi_provider::test_returns_first_provider_results[asyncio]` 為既有失敗。

## 給 orchestrator / 操作者
- 要跑 voice-design 時務必帶 `--step voice_design --provides voice-ref:<頻道代碼>`（technews 用 `voice-ref:technews`），否則等同舊行為（只靠 runner 不登記票就不會死結，但手動先排的 voice 票仍會預約擋它）。
- 已在跑的 process 不會吃到新設定；娛樂新聞 worker 的佇列票未動。
- 風險：19.5+3=22.5 GB 與實測 free 22.7–23.7 只差 0.2–1.2 GB，若 free 掉到 22.5 以下仍會等；此時 20 分後 `reason` 會直接寫差多少 GB。

## 清理
無暫存檔、無分支殘留；未動其他 worktree 與 output。
