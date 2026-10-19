# REPORT — feat/integrate（分支整合＋上線前收尾）

## TL;DR
- `feat/integrate` 從 `feat/cowos-facts` 4b0120d 開。合了 `feat/yokai-tempo`（3f10fa5）和 `feat/hn-daily`（3d1374e）。其他 5 支都不合：Route A 第一輪與 slide-styles 的程式碼早就 cherry-pick 進來了，剩下的是試作或已否決的第二輪。
- 測試隔離：新增 `content_farm/paths.py`，所有全機共用路徑在呼叫時才解析，都能用環境變數覆寫。`tests/conftest.py` 的 autouse fixture 把這些路徑全部導到 tmp；audit hook 只要看到測試寫真實共用路徑就讓該測試失敗。對照組：舊 src 加新 guard 跑全套，0 次寫入。
- 用量記錄：每席評審的 `results/<rid>.json` 都多一個 `_usage` 欄位；producers.jsonl 每行加 `at`；評分卡 HTML 有每輪小計、每階段小計和整支片總計；新增 `produce.py usage --run-dir …`，只讀、不寫檔。
- heavy hook：補上 hn-daily 的 `news.py render`，以及 6 支先前漏掉、會跑 ffmpeg 或 mlx 的腳本。⚠️ 主 checkout 目前**沒有** `scripts/heavy`，所以 hook 裝上之前，主 checkout 必須先切到含本分支的版本（見 §4）。
- 測試 🟢：全套 `pytest tests`（含 integration）**1565 passed／1 skipped**，排除的只有基準就失敗的 `test_multi_provider…[asyncio]`；`scripts/check.sh` 188 passed；`check.sh --full` 1565 passed。

## 1. 合併清單 🟢
| 分支 | 合／不合 | 理由 |
|---|---|---|
| `feat/yokai-tempo` 3f10fa5 | **合**（5b66e92） | 必合。改動是 yokai tempo 1.29 和測試；REPORT 裡說的 pose 腳本 `docs/yokai-tempo/add_frog_poses.py` 在 gitignore 裡，本來就不在分支上 |
| `feat/hn-daily` 3d1374e | **合**（efbc5b8） | 必合，HN 快報 Shorts＋週整理 |
| `feat/mascot-route-a` 83b4e3c | 不合 | Route A 第一輪已經在：本分支的 a12b68b 是 301bd21 的 cherry-pick（commit 訊息相同）；`git diff 301bd21 HEAD -- rig.html params.py` 沒有差異；motion.py 是後來的改動 |
| `feat/mascot-route-a2` 28bf4e7 | 不合 | Route A 第二輪 Leon 不採用（任務 prompt 轉述的決定；memory `content-farm-explainer-line` 在本機 memory 目錄裡找不到，🟡）|
| `design/mascot-quality` 5ab4226 | 不合 | 設計試作：route A/B/C 圖稿和研究筆記，全在 `docs/design/mascot-quality/`。可上線的 rig 已經以 a12b68b 的形式進來 |
| `design/chipcat-10` a263a75 | 不合 | 10 款晶片貓 SVG 試作與選擇頁，沒有被採用的程式 |
| `design/slide-styles-10` 3f42c30 | 不合 | 程式部分（68a8bce）已經以 f566092 cherry-pick 進來，之後又繼續演進：本分支的 `styles.py`／`cleanroom.css` 比試作版還新。剩下的只有試作頁和報告 |

## 2. 衝突處理 🟢
- `CLAIMS.jsonl`（兩次）：保留本分支版本，收工時整份換成本任務的 claims。
- `channels/chipcat.yaml`：兩邊都留。`publish:` 是 cowos-facts 的上片時段，`series.hn` 是 hn-daily 的；兩者是不同的鍵，沒有重複。
- `scripts/produce.py`：兩邊都留。說明文字、子命令（`review`／`queue`／`eval-loop` 加上 `news`）和 handler 表都合併了。
- `src/content_farm/production/steps.py`：
  - `EXPLAINER_SUBTITLE_MAX` 用本分支的 `"14"`（v3：64 px 字幕）。hn-daily 的 `"20"` 是較舊的 explainer-v2 值，不用；News 常數保留。
  - `steps_for`：保留 scripted-shorts 分流，再接上 news daily／weekly 分流。
  - 合併後的修正 1：News Short 的 `voice` 改用 `_voice_paid`／`heavy_if=_voice_local`。hn-daily 原本寫的是 `paid=not mock_voice`，在 chipcat 改用本機 VoxCPM2 之後，這會把它誤判成付費，也不會排進重工作佇列。
  - 合併後的修正 2：`news_weekly_steps` 的尾段改成排除 `TOPIC_STEPS`。週整理沒有選題階段，hn-daily 寫的時候 EXPLAINER_STEPS 還沒有 topic 這兩步。
- 🟡 尚未處理、留給 Leon：hn-daily 的 Short 只有 `gate_final`（成片審看）。本分支的閘門由評審團核可，`shorts_final` 階段有評審設定，但 news Short 有沒有接上評審團我沒有驗證（沒有跑 production run）。

## 3. 測試隔離 🟢
**改了什麼**
- 新增 `src/content_farm/paths.py`：`cache_root`（`CF_CACHE_ROOT`）、`heavy_queue_dir`（`CF_HEAVY_QUEUE_DIR`）、`render_lock_path`、`local_tts_lock_path`（`CF_LOCAL_TTS_LOCK_PATH`）、`orch_mail_script`（`CF_ORCH_MAIL`）、`orch_mail_dir`（`CF_ORCH_MAIL_DIR`）。全部在呼叫時才解析，預設值和原本一樣。
- `lanes/queue.py`：拿掉 import 時就固定下來的 `QUEUE_DIR`／`ORCH_MAIL`／`ORCH_MAIL_DIR`。原本的寫法是預設參數在 import 時就綁定，測試換環境變數也改不到。現在 `queue_dir=None` 時呼叫 `default_queue_dir()`；`legacy_locks()` 和 `orch_mail()` 改走 `paths`。
- `scripts/heavy`、`scripts/produce.py queue`：改用 `default_queue_dir()`。
- `voice/local_worker.py` `GateConfig.lock_path`：改成 `default_factory=paths.local_tts_lock_path`。
- `production/runner.py` `LOCK_PATH`：改由 `paths` 產生（這個常數本來就沒人用，只有測試在 monkeypatch 它）。
- `tests/conftest.py`：
  - autouse fixture `_shared_paths_to_tmp` 把上面所有路徑，以及 `ORCH_MAIL_DIR`，都設到 `<basetemp>/shared/…`；orch_mail 指向一個不存在的檔案，所以不會寄信。
  - `tests/_shared_path_guard.py` 用 `sys.addaudithook` 攔截以下動作：寫入模式的 `open`／`os.open`、`mkdir`、`rename`／`replace`、`remove`、`rmdir`、`symlink`、`link`、`truncate`、`chmod`、`utime`、`shutil.copyfile`／`copytree`／`move`／`rmtree`，以及 `subprocess.Popen` 參數裡的路徑。
  - 受保護的根目錄：`~/.cache/content-farm`、`~/.claude`、`~/orchestrator`、`~/.local/share`、主 checkout 的 `output/`、本 repo 的 `output/`。temp 目錄一律放行。
  - 動作在發生前就被擋（`SharedPathWrite` 不是 OSError，`except OSError` 吞不掉），而且會記錄下來，teardown 時讓該測試失敗。
  - pytest 自己的報告（`--junitxml` 等）在 `pytest_sessionfinish` 時停用 guard。
- 新增 `tests/unit/test_shared_path_guard.py`（14 條）：
  - 路徑確實導到 tmp，預設值不變。
  - 6 種寫入動作會被擋，5 種讀取、temp 或 repo 內的寫入放行。
  - **控制組**：在真實 `~/.cache/content-farm/heavy-queue/` 寫檔，guard 會擋下，而且檔案沒有被建立。

**偵測器射程**
- 實際打到過一次：我第一次跑全套時把 `--junitxml` 寫到 `~/.claude/jobs/…/tmp`，被 guard 擋下，訊息原文是 `SharedPathWrite: test wrote to a real shared path (os.mkdir): /Users/lileon/.claude/jobs/0a20aa86/tmp`。之後我把 guard 改成在 sessionfinish 時停用。
- 舊 src 對照：`git archive HEAD`（改動前）解到 `/private/tmp/cf-integrate-oldtree`，只換上新的 conftest 和 guard，跑全套：**1532 passed、0 次寫入真實路徑**。也就是說，舊 conftest 的 `CF_HEAVY_SLOT`／`CF_ADMISSION_UNIT_TEST` 繞道已經讓行程內沒有寫入。這次的改動是把「目前剛好沒寫」變成「寫了就失敗」。
- 真實 heavy-queue 的 `history.jsonl` 裡有 648 筆 `chipcat/run:*`，全部在 2026-10-18 07:40–08:47 UTC。這是測試用的 `tmp_path/"run"` 留下的，時間早於 `CF_ADMISSION_UNIT_TEST` 繞道（review-panels 開發期間）。本任務幾次全套跑完都沒有新增（前後行數見 §5）。這些舊紀錄我沒刪：那是共用檔，而且 `rm` 不在允許範圍。
- 已知盲點：測試啟動的子行程（`subprocess` 跑 scripts/*）在子行程裡寫的東西 guard 看不到。這類子行程會繼承 fixture 設的環境變數，所以預設也會寫到 tmp。另外 guard 會擋參數裡帶受保護路徑的 Popen。

## 4. 評審用量記錄 🟢
- `review/rounds.py` `write_result`：每席（包含仲裁者）都寫 `results/<rid>.json`，內容是 `{…答案, "_usage": {model, effort, models_used, seconds, cost_usd, attempts, tokens{input,output,cache_read,cache_write}}}`。答案無效的席次也寫一份檔（`_failed`、`_errors`），用量不會丟。目前沒有程式讀這些檔案（grep 過）。
- `review/producers.py`：producers.jsonl 原本就有 `CallResult.to_json()`（model、tokens、cost_usd），這次再加上 `at`。
- `review/client.py`：`call_usage()`／`TOKEN_KEYS`。
- `review/usage.py`：彙總 `review/*/round-*/scorecard.json` 的每一席（包含旁輪和 holdout）、producers.jsonl，以及 `production.log.jsonl` 裡帶 `exit_code` 的事件（＝指令步驟，也就是本機車道）。
- `review/scorecard_html.py`：評審表多了 input/output/cache 讀/cache 寫/名目 $ 欄位；每輪顯示「本輪小計」；各階段有「產出 agent」明細；頁首有「用量」表，列出每階段小計和**整支片總計**。
- `scripts/produce.py usage --run-dir … [--json]`：只讀；測試驗證跑完後 run-dir 每個檔案的 mtime 都沒變。
- 測試：`tests/unit/test_review_usage.py`（6 條）。

**範例**（cowos-final，只讀，`PYTHONPATH=<wt>/src .venv/bin/python scripts/produce.py usage --run-dir .claude/worktrees/cf-cowos-facts/output/cowos-final`，2026-10-18 約 16:10 UTC）🟢：
```
雲端車道（claude -p；名目費用，訂閱計費）
  script              25 次  $  9.0434    43.1 分  input=130 output=264,628 cache_read=1,035,974 cache_write=655,804
    round-1          評審  8 席  $  2.9941  …   round-2  8 席 $2.9913   round-3  9 席 $3.0580
  script_structure    29 次  $ 30.3404   116.3 分  input=516 output=694,352 cache_read=26,575,716 cache_write=1,595,471
    round-1 8 席 $3.0848 · round-2 8 席 $2.9520 · round-3 9 席 $3.2628
    producer         產出  4 次  $ 21.0408  input=374 output=429,993 cache_read=25,317,493 cache_write=898,393
  總計                54 次  $ 39.3838   159.4 分  input=646 output=958,980 cache_read=27,611,690 cache_write=2,251,275
  （評審 $18.3430、產出 $21.0408；模型 claude-haiku-5-5, claude-opus-5-5, claude-sonnet-5-5）
本機車道（指令步驟牆鐘）
  voice 29 次 8186.1 s · media 28 次 8895.0 s · mascot 21 次 10457.2 s · assembly 19 次 1807.3 s · mix 16 次 559.0 s …
  總計 30041.2 s（500.7 分）
```
- 解讀注意：
  - 本機車道是 run-dir 整段 log 的累計，包含這個 run-dir 複製前的歷史，所以 29 次 voice 是多次重跑的總和；「最近」欄才是最後一次。
  - `article`／`deck` 出現在本機車道，是因為 agent 步驟的 verify 指令也會記 `exit_code`。
  - cowos-final 沒有 topic 和 article 的評審輪（文章已凍結），所以「從選題到現在」在這支片上是從腳本開始算。
  - yokai-kyubi-v2 目前沒有 `review/`，所以沒拿來示範。
  - 名目費用是 CLI 回報的數字，實際走訂閱。

## 5. heavy hook 規則 🟢
`REPORT-review-panels.md` 的〈PreToolUse hook 規則〉在整合後仍然成立（`lanes/heavy_rules.py` 沒改，`tests/unit/test_lanes_heavy_rules.py` 全過）。補充如下：
- `channels/shared/heavy_work.json` `commands`「heavy repo scripts」新增：
  - `scripts/news.py … render`（hn-daily）
  - `motion_parallax_worker.py`、`host_depth_worker.py`（mlx-video venv 的 torch 模型）
  - `seam_check.py`（ffmpeg 整片解碼）
  - `render_slide_styles.py`、`record_slide_style_motion.py`（同 render_slides）
  - 不擋：`news.py lint/prepare/weekly-check`、`produce.py news …`、`produce.py usage`。
- `steps` 新增 need：`news_render` 6 GB／gpu shared／render 鎖；`news_script`、`news_prepare`、`weekly_check` 是輕量步驟。
- cowos-facts 和 yokai-tempo 在 `scripts/`、`explainer/` 都沒有新增重腳本（`git diff --stat feat/review-panels HEAD -- scripts src/content_farm/explainer` 只出現 hn-daily 的檔案）。
- 測試案例：
  - 擋：原本 12 條，加上 7 條新的——`news.py render --run-dir …`、`news.py --run-dir … render`、`motion_parallax_worker.py`、`host_depth_worker.py`、`seam_check.py`、`render_slide_styles.py`、`record_slide_style_motion.py`。
  - 放行：原本 10 條，加上 5 條——`news.py lint`、`news.py prepare`、`produce.py news daily`、`produce.py usage`、`scripts/heavy -- … news.py render`。
- **最終指令**（hook 裡用；bare python3，只用 stdlib）：
  ```
  python3 /Users/lileon/project/content-farm/scripts/heavy --check "<整條 Bash 指令>"
  # stdout: {"block", "heavy", "matched", "why"}；exit 2 = 擋（把 why 當訊息回給 agent），0 = 放行
  # 範圍判斷（cwd 或指令含 content-farm 才呼叫）在 hook 端做，--check 本身不看 cwd
  ```
- 在本 worktree 用 `/opt/homebrew/bin/python3` 實測：
  - `news.py render …` → exit 2，`{"block": true, "matched": "heavy repo scripts", …}`
  - `scripts/heavy --label hn -- python scripts/news.py render …` → exit 0
  - `ffmpeg -i a.mov b.mp4` → exit 2
  - `produce.py usage …` → exit 0
- ⚠️ **前提**：主 checkout（`/Users/lileon/project/content-farm`）目前**沒有** `scripts/heavy`，也沒有 `src/content_farm/lanes/`（`ls` 原文：`No such file or directory`）。hook 如果照上面的路徑裝，在主 checkout 切到含 feat/integrate 的版本之前，每次都會找不到檔案。orchestrator 要先決定兩件事：主 checkout 要切到哪裡，以及 hook 找不到腳本時要放行還是擋下。我沒動主 checkout。

## 6. 測試結果 🟢
- `PYTHONPATH=<wt>/src .venv/bin/python -m pytest tests -q -p no:cacheprovider --deselect "tests/unit/test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results[asyncio]"` → `1565 passed, 1 skipped, 1 deselected`
- `bash scripts/check.sh` → `ok: review config valid for 4 channels`、`188 passed`；`bash scripts/check.sh --full` → `1565 passed, 1 skipped, 1 deselected`
- 修正：`check.sh --full` 原本的 `--deselect` 沒有寫 `[asyncio]` 後綴，所以根本沒排除到（cf-yokai-tempo 回報過這件事），已經補上。
- 子行程寫入的旁證：真實 `heavy-queue/history.jsonl` 在全套開跑前是 746 行，跑完後 748 行。多出來的 2 筆是 `2026-10-18T15:55:26` 的 `yokai/yokai-kyubi-v2:deck／gate_deck`，屬於 yokai worker 的 production run，不是測試。
- 合併過程中有一次全套出現 8 個失敗：我在跑的途中改了 producers.py，import 進來的是改到一半的檔案。那 3 個檔案單獨重跑是 49 passed，之後的全套是 0 失敗。

## 副作用與清理
- `/private/tmp/cf-integrate-oldtree/`、`/private/tmp/cf-integrate-oldsrc/`：舊 src 對照組用的解壓目錄，`rm` 不在允許範圍，留給 orchestrator 清。
- job tmp 裡的 `oldsrc.tar`、`oldtree.tar` 會隨 job 一起刪除。
- 沒有跑 production run，沒動 cowos-final 和 yokai-kyubi-v2 的 run-dir（只讀過 cowos-final 的 review／log）。沒有 push，沒開瀏覽器，沒上傳，沒用付費服務。
- worktree 裡未追蹤的 `graft/` 是開工前就有的索引，沒有 commit。

## 進度紀錄（append）
- 開分支 → 合 yokai-tempo（只有 CLAIMS 衝突）→ 合 hn-daily（4 處衝突，見 §2）→ commit efbc5b8。
- 測試隔離：paths.py、queue 延遲解析、conftest guard、控制組。
- usage：results `_usage`、scorecard 小計與總計、`produce.py usage`。
- heavy 規則補齊，`check.sh` 修正 deselect 後綴、加入新測試。
