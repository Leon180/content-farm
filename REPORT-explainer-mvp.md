# REPORT — content-farm 簡報式知識影片 MVP（不含付費端到端試跑）

## TL;DR

- 範圍 1–7 全部完成，分支 `feat/explainer-mvp`（基準 `c84d2e0`）共 8 個 commit，**未 push**。🟢
- `pytest`：**712 passed、1 failed**；唯一的失敗是基準就有的 `test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results`。基準是 633 passed，新增 79 個測試，0 skipped（瀏覽器測試有實際跑）。🟢
- 範例總覽圖：`docs/examples/explainer-tsmc/slides/contact_sheet.png`，6 張都沒有溢出（溢出檢查會直接讓渲染失敗）。🟢
- 共用程式只動了第 6 點（字幕每行字數依 orientation 決定）；`run_stage.py` 和 `Script` schema 沒動。Shorts 仍然是 13 字，有測試證明。🟢
- ⚠️ 派工的 worktree 開錯 repo（開在 cts-member-server），所以我在 content-farm 另開了 worktree，見〈前提偏差〉。

等級：🟢 本機實測可重跑；🟡 只驗到存在或讀碼推論；🔴 未驗證的判斷。

## 前提偏差（請先看）

- 這個 session 的 cwd 是 `/Users/lileon/commeet/cts-member-server/.claude/worktrees/cf-explainer-mvp`，那裡的 `git log --oneline -1` 是 `1f0046902a feat(bpm)…`，`git cat-file -t c84d2e0` 回 `fatal: Not a valid object name c84d2e0`。所以任務給的修正指令（`git checkout -B feat/explainer-mvp c84d2e0`）在那裡跑不了。🟢
- `c84d2e0` 在 `/Users/lileon/project/content-farm`（`docs(skills): update pipeline skills and README for current workflow`，分支 `chore/wip-baseline-2026-10`）。🟢
- 我的處理：`git -C /Users/lileon/project/content-farm worktree add .claude/worktrees/cf-explainer-mvp -b feat/explainer-mvp c84d2e0`。這是新增一個 worktree，不動主 checkout，也不動 `chore/wip-baseline-2026-10`。`EnterWorktree` 拒絕切過去（`is not under /Users/lileon/commeet/cts-member-server/.claude/worktrees`），所以全程用絕對路徑操作。🟢
- cts-member-server 那個 worktree 我沒有改任何東西，只在根目錄放了 `CLAIMS.jsonl`，讓 `dispatch.sh --verify` 找得到。

## 位置

- worktree：`/Users/lileon/project/content-farm/.claude/worktrees/cf-explainer-mvp`
- 分支：`feat/explainer-mvp`（本機，未 push）

```
7944bb6 feat(skills): deck-outline and deck skills for the explainer line
128bf56 docs(examples): sample TSMC explainer deck rendered to slides and contact sheet
7a0ac13 fix(explainer): centre list, compare and timeline bodies under the heading
1dfa068 feat(explainer): render_slides with shared browser, overflow gate and contact sheet
3a90d5f feat(explainer): slide templates for six layouts, three themes and mascot slot
d988780 feat(explainer): name slides onto the assembly timeline from measured durations
708c65d feat(explainer): deck.json schema, lint rules and deck_to_script converter
ab19ecb feat(subtitle): pick per-line width by script orientation
```

## 做了什麼（對應任務範圍 1–7）

| # | 內容 | 檔案 |
|---|---|---|
| 1 | `deck.json` 的 pydantic schema：6 種版型，body 依 `layout` 驗證，`extra="forbid"`。硬規則寫成 validator：ai/tech 必填 `as_of`（YYYY-MM）、`source_ids` 必須存在於 `sources`、gossip 必須有來源、narration 30–220 字、heading ≤ 24 字、至少 3 個 section、slide/source id 不重複。量產規則放在 lint：15–30 張、5–10 分鐘、連續 3 張以上沒有 beat、beat 連續同類、版型種類少於 3、bullets 超過一半、有數字沒來源、投資建議用語、`draft_data`。lint 預設只警告，`--strict` 才失敗。轉換器：一張投影片對應一個橫式 `Scene`，一個 section 對應一個 `ChapterOutline`，`genre=knowledge`，`length=medium` | `src/content_farm/explainer/{deck,lint,to_script}.py`、`scripts/deck_to_script.py`、`tests/unit/test_explainer_deck.py`（34 個測試） |
| 2 | 6 個 Jinja2 版型。外框固定：頂欄 0–96 px、內容區 112–820、meta 列 832–872（來源／資料截至／非投資建議）、**字幕安全區 880–1080**（200 px）。吉祥物插槽在右下角（x ≥ 1592、y ≥ 826），和置中、寬約 1250 px 的字幕不會重疊。`mascot.pose` 對應 `<run_dir>/assets/mascot/<pose>.png`，檔案不存在就留空、只記 info log。`draft_data` 為 true 時每張蓋「示意數字・待查證」章。3 套主題：tech（預設，深灰＋橘）、ai（深藍＋青）、knowledge（米白＋襯線） | `src/content_farm/explainer/templates/`（`slide.html.j2`、`layouts/*.html.j2`、`base.css`、`themes/{tech,ai,knowledge}.css`）、`src/content_farm/explainer/pages.py` |
| 3 | 渲染器：整份 deck 共用一個 headless Chromium；每張截圖前跑一次 DOM 檢查，內容區被裁切、進入字幕安全區、或超出畫面左右邊界就算失敗。失敗時列出每一張的 `slide NN (id, layout): 問題`，exit 1；PNG 照樣寫出方便檢查，但不產總覽圖。成功時產出 `slides/contact_sheet.png`。另有 `--show-safe-zone` 除錯用的斜紋疊層 | `src/content_farm/explainer/render.py`、`scripts/render_slides.py`、`tests/unit/test_explainer_render.py`（13 個，含「故意塞爆第 3 張 → 報錯指名 `slide 03 (crowded, bullets)`」的失敗路徑） |
| 4 | slides 到 `visual/` 的命名器：每個邊界從**累計時長**四捨五入一次，所以第 N 張的結束時間和第 N+1 張的開始時間是同一個字串，不會產生縫隙。時長來源依序是 `ffprobe audio/scene_NNN.mp3`（精確），然後 `voice_artifact.json`（四捨五入到 10 ms）；`script.json` 的估算值只有明確指定 `--source script` 時才用，而且會警告。`visual/` 裡已有 timeline 檔時拒絕執行，除非加 `--replace`（只刪 timeline 檔名的檔案） | `src/content_farm/explainer/timeline.py`、`scripts/slides_to_visual.py`、`tests/unit/test_explainer_timeline.py`（21 個；含用 `assembly.timeline_assembly.scan_timeline_clips` 讀回檔名的往返測試，以及「逐張四捨五入會漂移、累計不會」的對照測試） |
| 5 | 兩個 skill。`deck-outline`：素材可以來自 `/research` 的 `research.md`、`--notes` 傳入的使用者文章或筆記，或兩者都用；產出 `deck_outline.json`，含 thesis 和結構，是人工閘門 1。`deck`：寫 `deck.json`、跑 `deck_to_script`（人工閘門 2）、跑 `render_slides` 並顯示總覽圖（人工閘門 3），最後列出付費步驟並註明要使用者明確同意才能跑。四條寫稿硬規則、三種類別的差異、晶片貓的人設，集中寫在共用的 `writing_rules.md` | `.claude/skills/deck-outline/SKILL.md`、`.claude/skills/deck/SKILL.md`、`.claude/skills/deck/writing_rules.md` |
| 6 | 新增設定 `CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE`（預設 24）。`create_subtitle_provider(settings, orientation=None)` 只有在 orientation 是 LANDSCAPE 時才用這個值；`None` 和 PORTRAIT 都維持 13。`VoiceGenerator` 和獨立的 subtitle stage 會把 `script.orientation` 傳進去 | `config.py`（+2 行）、`subtitle/factory.py`、`voice/generator.py`、`pipeline/{container,stages}.py`；`tests/unit/test_subtitle_orientation_wrap.py`（11 個） |
| 7 | 範例 deck「台積電到底賺什麼錢」：6 張，6 種版型各一張，3 個章節，含 1 段 gossip、1 段 joke、4 張帶吉祥物 pose。`draft_data: true`，來源全部標「示意・待查證」，URL 留空不捏造。跑了 deck → script.json → render_slides → 總覽圖，**沒有跑 voice** | `docs/examples/explainer-tsmc/`（`docs/` 在 gitignore 裡，用 `git add -f` 加入） |

### 第 6 點：Shorts 行為不變的證據 🟢

- `create_subtitle_provider(settings)`（舊的呼叫方式，不帶 orientation）→ wrap 13。
- `orientation=None`、`PORTRAIT` → 13；只有 `LANDSCAPE` → 24。
- 行為層面：portrait 的換行輸出和 `wrap_text(..., 13)` 逐字相同；landscape 的行數較少。
- `VoiceGenerator._generate_subtitles` 用三種 script 參數化測試：沒有 orientation、portrait、landscape，分別得到 13、13、24。
- 既有測試全部照過（633 → 712，失敗數維持 1）。

共用程式對基準的 diff（`git diff --stat c84d2e0..HEAD`，只列共用路徑）：

```
 src/content_farm/config.py             |  2 ++
 src/content_farm/pipeline/container.py |  7 +++++--
 src/content_farm/pipeline/stages.py    |  4 +++-
 src/content_farm/subtitle/factory.py   | 20 ++++++++++++++++++--
 src/content_farm/voice/generator.py    |  4 +++-
```

`scripts/run_stage.py`、`src/content_farm/script_gen/` 都沒有出現在 diff 裡。

## 測試結果 🟢

worktree 沒有自己的 venv（`uv sync --offline` 失敗，因為快取裡沒有 playwright），所以借用主 checkout 的 `.venv`，並用 `PYTHONPATH` 指到 worktree 的 `src`。我有先確認 `content_farm.__file__` 指向 worktree，才開始跑測試。

```
PYTHONPATH=<wt>/src /Users/lileon/project/content-farm/.venv/bin/python -m pytest \
  --rootdir <wt> -c <wt>/pyproject.toml <wt>/tests -q -p no:cacheprovider -rs
```

| 時點 | 結果 |
|---|---|
| 基準 `c84d2e0`（動工前） | `1 failed, 633 passed` |
| 完成後 `7944bb6` | `1 failed, 712 passed`，0 skipped |

唯一的失敗在前後兩次都是 `tests/unit/test_multi_provider.py::TestMultiSearch::test_returns_first_provider_results[asyncio]`，訊息是 `assert 2 == 1`，屬於預先存在的失敗。

`ruff check`（新增和修改的檔案）：`All checks passed!`

## 總覽圖

- `docs/examples/explainer-tsmc/slides/contact_sheet.png`：給你看版面用的主圖。
- `docs/examples/explainer-tsmc/contact_sheet_safe_zone.png`：同一份 deck 加上字幕安全區的斜紋。
- 單張全尺寸圖在 `docs/examples/explainer-tsmc/slides/slide_00{1..6}.png`；可手改的 HTML 在同一個目錄。
- 渲染耗時：6 張 2.0 s（含啟動瀏覽器），沒有溢出。🟢

## 刻意沒做的事

- 端到端試跑（voice、assembly、上傳、Drive）：任務本來就排除，而且會花錢。
- 沒有呼叫 Fish Audio、Claude API 或任何付費 API；沒有 push、沒有動 main 或 `chore/wip-baseline-2026-10`、沒有 commit `data/curriculum_map/`、沒有清理根目錄的空目錄殘骸。
- 提案裡的 `code`、`image`、`custom_html` 版型不在 MVP 範圍，schema 會直接拒絕。
- 沒有把 explainer 接進 `run_stage.py` 或 `pipeline` skill；改用獨立的 scripts，再由 `/deck` skill 串接。
- 投影片沒有逐條出現的動畫，也沒有 Ken Burns 推近效果（提案列為 v2）。
- 縮圖沒有改成 HTML 模板（v2）。
- 沒有把 `scripts/validate_script_facts.py` 接到 deck 上（提案 §5.3，約 0.5 人日 🔴）。
- 吉祥物素材：只做了插槽，等你提供 PNG。
- 字幕字型（提案 §7 風險 3）沒有處理：libass 可能退回替代字型，要等端到端試跑時肉眼確認。

## 需要你核可的下一步：端到端試跑

前置條件：先把範例 deck 補成正式稿。要換成真實數字和來源、補到 15–30 張，然後 `draft_data: false`、跑 `--strict` 通過。或者也可以接受直接用 6 張的 draft 版跑一次，只驗證管線通不通。

```bash
# 在 content-farm worktree 根目錄
python scripts/deck_to_script.py --run-dir output/<run> --strict
python scripts/render_slides.py  --run-dir output/<run>           # 閘門 3
python scripts/run_stage.py --stage voice --run-dir output/<run>    # ← 付費（Fish Audio）
python scripts/slides_to_visual.py --run-dir output/<run>
python scripts/run_stage.py --stage assembly_timeline --run-dir output/<run>
# 不跑 upload / drive，先人工看 assembly/draft.mp4
```

試跑時要用眼睛確認的事：
1. 每行 24 字的橫式字幕看起來是否合適；
2. 字幕有沒有壓到 meta 列或吉祥物；
3. Fish Audio 怎麼唸 CoWoS、HBM、TSMC，再決定要不要補 pronunciation_map；
4. whisper `base` 對中英夾雜詞的對齊品質；
5. 投影片切換點和講稿是否對齊（要確認累計時長的命名沒有黑幀）。

預估費用（🔴，沒有查價，不能當報價用）：
- **Fish Audio**：8 分鐘講稿約 2,200 中文字，大約 6.5 KB UTF-8。如果單價還是我記得的「每百萬 UTF-8 bytes 約 US$15」，一次約 US$0.1，重配 3 次也不到 US$1。跑之前要先到 Fish Audio 官網確認現價和計費單位。
- **Claude**：如果 deck-outline 和 deck 在 Claude Code 對話裡寫（現在 skill 的設計就是這樣），不會另外產生 API 帳單。如果改成用 API 跑，以長片腳本的量級估計是幾美元以內（🔴）。
- **whisper 對齊、ffmpeg、Playwright**：都在本機跑，US$0。

## 清理與副作用

- 新增的 git worktree `/Users/lileon/project/content-farm/.claude/worktrees/cf-explainer-mvp` 和本機分支 `feat/explainer-mvp`：保留，這就是交付物。
- worktree 裡有一個空殼 `.venv/`，是 `uv sync --offline` 失敗時留下的。它在 gitignore 裡，不影響 git 狀態，可以刪；我沒有刪，因為合約不允許 `rm`。
- `/Users/lileon/.claude/jobs/40e1e125/tmp/{smoke,safezone}`：冒煙測試的輸出，放在 job tmp，job 刪除時會一起清掉。
- cts-member-server 的派工 worktree：只新增了一個 `CLAIMS.jsonl`，沒有其他改動。
