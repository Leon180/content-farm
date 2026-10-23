# REPORT — 分支整合＋故事張力卡關（2026-10-23）

分支 `worktree-cf-story-calibrate`（從 `worktree-cf-chipcat-run2` 開）。全套 pytest：**1787 passed、1 failed（`test_multi_provider`，事前就存在）**。未 push、未開瀏覽器、未上傳。

## TL;DR
- 三個分支已依序併入（cel-run1 fast-forward；frog-motion、offwork-skit-build 各一個 CLAIMS.jsonl 衝突，取聯集）。offwork-skit-render 未併。
- 觀眾門檻：6 份稿、同 persona 同順序，opus 離開比 sonnet 晚 **0.22**（座位層 0.23，90% CI 0.15–0.32）→ opus 0.50 換成 sonnet 尺度 ≈ 0.27–0.28，落到下限，**採 0.35**（原 0.40）。編劇：opus 高 **0.59**（n=12，CI 0.36–0.82，系統性）→ 6.5 換算 5.9，**採 6.0**。花費名目 **$10.10**（< $15）。
- **關鍵發現**：換算後的門檻沒有「救」到任何一份稿：cel run1 兩輪（19.5%／25.6%）、chipcat run2 R1（27.5%）仍遠低於 0.35，卡關是**真的故事問題**，不是門檻太嚴。唯一差別：chipcat run2 R3（36%／6.5／6.0）在新門檻下會過。
- 新增：文章階段的「敘事骨架」（story_spine.json＋rubric 提前＋數量詞規則）；結構改寫後 article 輪數重算；yokai 拿掉青蛙書記；評審拿掉聲音；每關最多 3 輪、第 3 輪沒過放行。各附測試。

## 0. 整合
| 順序 | 分支 | 結果 |
|---|---|---|
| 1 | worktree-cf-cel-run1 | fast-forward（仲裁 key、引用切句修正） |
| 2 | worktree-cf-frog-motion | CLAIMS.jsonl 衝突 → 兩邊聯集 |
| 3 | worktree-cf-offwork-skit-build | CLAIMS.jsonl 衝突 → 兩邊聯集；其餘自動合併 |

merge 後全套 pytest：1765 passed、1 skipped、1 failed（`test_multi_provider` 既有失敗）。

## 1. 觀眾／編劇門檻校正（🟢 本機實測，數據在 `docs/story-calibrate/data/`，已強制加入 git）
方法：取各稿 script_structure 回合裡已存的 viewer／writer 提示（同 persona、同順序、同資料夾素材），各用 **sonnet·low 與 opus·low** 重評一次（`scripts/calibrate_audience.py run`，算術在 `review/calibrate.py`）。

| 稿 | 座位 | sonnet 離開中位 | opus 離開中位 | 差 |
|---|---|---|---|---|
| yokai-kyubi-v2 R1 | 4 | 0.689 | 0.722 | +0.033 |
| cel run1 R1 | 4 | 0.171 | 0.219 | +0.048 |
| cel run1 R2 | 4 | 0.227 | 0.480 | +0.253 |
| chipcat run1 R1 | 4 | 0.190 | 0.362 | +0.172 |
| chipcat run2 R1 | 4 | 0.290 | 0.398 | +0.108 |
| chipcat run2 R3 | 5 | 0.292 | 1.000 | +0.708 |

- 稿層差：平均 0.22，90% bootstrap CI 0.087–0.391（n=6，很寬）；中位 0.14。座位層（24 對）平均差 CI 0.153–0.315。
- 換算：0.50 − 0.22 = **0.28**（CI 0.11–0.41）；中位法 0.36。取「下限 0.35」。**0.40→0.35**，寫在 `review_panels.yaml`（4 個階段）與 `config.py` 的 `LEAVE_MEDIAN_FLOOR`。
- 編劇：12 對分數（6 稿×2 位），opus 平均高 0.59（CI 0.358–0.817，排除 0 → 系統性）；sonnet 對失敗稿幾乎都打 6.0。6.5−0.59 = 5.91 → **script_structure writer_min 6.0**（`WRITER_MIN_FLOOR`）。shorts_script 的 writer_min 沒量過，維持 6.5。
- 限制（🟡）：n=6 稿、每稿 4–5 席；chipcat run2 R3 的 opus 全員看完（1.0）是離群值，拉高平均；sonnet 與 opus 在「R3 的故事是否修好」上意見相反。`lifted`（全 opus）比較模式仍用同一份 yaml 門檻（比 opus 尺度鬆），只用於比較，沒另外分檔。
- 離線重算（`calibrate_audience.py replay`，`replay.json`）：

| 回合 | 離開中位 | 編劇 | 舊門檻(0.40/6.5) | 新門檻(0.35/6.0) |
|---|---|---|---|---|
| cel run1 R1 | 19.5% | 6.5／5.5 | 不過 | 不過 |
| cel run1 R2 | 25.6% | 6.0／6.0 | 不過 | 不過 |
| chipcat run2 R1 | 27.5% | 5.5／6.3 | 不過 | 不過 |
| chipcat run2 R2 | 35.8% | 5.5／6.8 | 不過 | 不過（story 5.5） |
| chipcat run2 R3 | 36.0% | 6.0／6.5 | 不過 | **過** |
| yokai R1 | 72.2% | 6.5／6.5 | 過 | 過 |

## 2. 大綱／文章階段先設計留人點
- `review/story_spine.py`：`SPINE_BRIEF`（開場鉤子＋一條貫穿的人物或衝突＋每 60–90 秒〔≈450 字〕一個轉折／懸念＋收尾回扣＋「不編造情節、不改事實規則」）；`check_spine()` 檢查 `story_spine.json`（hook／through_line／payoff、beats ≥ 文章字數÷450〔最少 3〕、beat 的章節錨點存在、>700 字的章節至少一個 beat）。
- `review/brief.py: article_brief()`＝骨架＋**script_structure 的 rubric 與門檻**（照 pipeline-speed 待辦 1 的做法）＋數量詞規則；`producers.py` 對**初稿**與**結構改寫**附上，事實修補的 rework 不附。初稿與結構改寫都要求跑 `check_article.py --require-spine`。
- `scripts/check_article.py`：`--require-spine`；`story_spine.json` 存在就一定檢查；數量詞檢查（見 4）。`.claude/skills/article/SKILL.md` 加 Step 3b。事實規則（文章 3 輪、0 錯）沒動。
- 🟡 **未驗證效果**：骨架要求是否真的提高離開中位，需要一次新片實跑；離線只能驗到「要求有送出去、檢查會擋」。文章模板的固定錨點（a-timeline／a-numbers…）仍在，是名詞表／時間軸堆疊的來源之一，沒動。
- 離線檢視現有文章（`check_spine` 的字數規則）：用 `_sections()` 量：cel run1 正文 2,578 字、7 個錨點 → 需要 ≥5 個 beat，且 a-chain（921 字）必須有 beat；chipcat run2 正文 2,372 字、9 個錨點 → ≥5 個 beat，沒有章節超過 700 字。規則門檻不高，現有文章的章節結構大致過得去；重點在 beat 要真的是轉折，這點只能靠評審。

## 3. orchestrator 追加項
1. **結構改寫後 article 輪數重算**：`_StructuralArticle.accept()` 接受改寫後呼叫 `new_stage_cycle(("article",), reason=結構改寫…)`，舊輪次移到 `cycle-N/`、下一輪是 round-1，並寫進 `review/new_cycle.jsonl`；`article.locked.md` 仍在 → 沒變的已查核句不重查，只查新句。測試：`test_an_accepted_structure_rewrite_moves_the_spent_article_rounds_aside`、`..._is_round_one`。
2. **數量詞前後一致**：寫進 `QUANTITY_BRIEF`（初稿與結構改寫 brief）；`check_quantifiers()` 只抓「N 類／種／項／點：a、b、c」同一句內條目數對不上。🟡 **抓不到 cel 那次的形狀**（文章說「七類」、另一節有 8–10 個小標）——我對 cel 的三版文章跑過，0 命中；那類跨章節的數量對照仍只靠 brief 與事實查核。
3. **yokai 拿掉青蛙書記**：`channels/yokai.yaml` `mascot.rig_ready: false`（`pngtuber/frog-scribe` 與 frog motion profile 都保留；改回 true 即恢復）。既有機制就會：mascot 步驟 `applies=rig_ready` 跳過、`mascot_findings` 與縮圖「角色必須在縮圖上」不適用、deck 的 channel_rules brief 不再要求吉祥物占比。測試：`test_yokai_without_a_mascot_*`、`test_yokai_thumbnail_*`、`test_production_channels` 更新。
4. **評審拿掉聲音**：刪 `editor_audio` 角色與 final 席次（`REQUIRED_ROLES` 同步）；persona 裡的語速／聲音特質、editor_visual 的 BGM／音效與「聲音設計」rubric 移除；final 觀眾提示不再給 `audio.txt`（不產生）、`objective.json` 去掉 `audio`；`pronunciation` 不再必填；`verdicts.final()` 丟掉 audio 欄（不再擋 `objective_all_green`）、丟掉 category audio／pronunciation、caused_by voice／mix、target audio 的問題。🟡 舊的 `evaluation/`（留存分析）子系統沒動，不是評審團。
5. **每關最多 3 輪、第 3 輪沒過放行**：`Stage.waive_on_last_round`（預設 true，yaml 可逐階段關掉）；`gate.panel_gate`／`delta.delta_gate` 在最後一輪未過（或內容在輪數用完後又變動、差異查核用完）時，改寫 `review/<gate>.decision.json`（`approved`＋`waived:{why,reasons,round}`）並回 `pass`，訊息含「放行」與未過項目；**席次失效／模型不符／缺席仍然擋下（blocked）**；topic 全被否決時不放行。所有階段 `max_rounds ≤ 3`（原本就是，另有測試鎖住）。測試：`test_a_failed_last_round_is_waved_through_and_recorded`、`..._never_hides_a_reviewer_that_failed`、`..._when_waiving_is_off`、article／delta 的對應測試。
   - ⚠️ 風險請 Leon／orchestrator 知悉：**這也放行了 article（事實 0 錯）與 script_facts／media（合規）**，等於第 3 輪仍有事實錯誤或授權問題時會往下走，只靠 gate_final 人工把關。我照指示做了「每關」；若要保留事實／合規關的硬停，把 `article`、`script_facts`、`media` 的 `waive_on_last_round: false` 寫進 `review_panels.yaml` 即可（程式與測試已支援）。

## 4. 結論與建議
- 門檻已校正，但三部片的離開中位多半仍 <0.35：先看新骨架有沒有改善，再談門檻。chipcat run2 的 R3 在新門檻下會過；cel 的法規題材仍需要人物／事件主線（骨架第 2 點）。
- 下一輪實跑時看：`story_spine.json` 有沒有被產出、script_structure R1 離開中位、article 在結構改寫後是不是從 round-1 開始。

## 進度紀錄
- 2026-10-23：整合、校正、骨架、四項追加完成並 commit；對話遠低於 30 萬 token。

## 副作用與清理
- 評審花費（名目）$10.10，來源 `docs/story-calibrate/data/*/{sonnet,opus}/*.json`；未使用付費 API key。
- worktree 內 `graft/` 為索引資料夾（未加入 git）。未動 `output/`、其他 worktree 的檔案、`.env`。
- 背景程序皆已結束；沒有暫存檔留在 repo。
