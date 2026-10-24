# REPORT — 畫面與腳本品質 v5

分支 `worktree-cf-quality-v5`（從 `worktree-cf-revisual` ac0392c 開出，merge `worktree-cf-stock-footage`；衝突只有 `CLAIMS.jsonl`（取聯集）與 `wan.py`（見下））。沒有 push、沒付費服務、沒開瀏覽器、沒跑新影片。

## TL;DR
- 9 項裡 8 項已落地並有測試；第 5 項（CLIP 語意排序）**程式與測試完成，但本機沒有 CLIP 權重也沒有 sentence-transformers，從未用真權重跑過**——預設關閉，設 `CF_CLIP_MODEL_DIR` 才啟用。
- 第 6、8 項查證後**不需改碼**（字幕本來就在所有縮放之後；loudnorm 本來就是兩段式），只加測試／記錄現況。
- pytest：2007 passed、1 skipped；`test_multi_provider` 1 個既有失敗不變。
- 離線數字：深海 stock 片有 2 段 dead zone 共 32 秒；cel v4 沒有 dead zone；slideshow 平均分 deepsea 8.5、cel v4 23.3（v3 為 20.4，v4 反而略高，見下）。
- 所有新檢查都在 `channels/<code>.yaml` 的 `quality:` 區塊有開關（預設全開）。

## 各項改動

| # | 做了什麼 | 在哪 | 步驟 |
|---|---|---|---|
| 1 | 投影片感評分：每頁 0–100 分（重複版型、畫面字過多、單畫面佔太久、純文字頁、prompt 太泛、同樣的平移運鏡）；≥40 分算高風險，超過 25 % 的頁高風險就產生一份要求清單，deck producer 會多收到**一次**（`review/slideshow_risk.json` 記錄；重做失敗或違反頻道規則就還原第一版；不擋 run）。QC 加 warn。 | `explainer/slideshow_risk.py`、`production/slideshow_fix.py`、`panel_flow._run_producer`、`qc.slideshow_findings` | deck |
| 2 | 靜止偵測：成片抽樣 4 fps 的 96×54 灰階，硬切分鏡，每鏡判 static／pan／motion；static 鏡 >10 秒 = dead zone，寫 `qc/static_scan.json`、QC warn、`score_ledger.json` 的 `qc.static_scan`。 | `production/static_scan.py`、`qc.static_scan_findings`、`score_ledger.record_qc` | qc |
| 3 | 鏡頭語言：`Media` 新增 `shot_size`／`camera`／`lighting`；illustrate 的 prompt = 風格 + 景別 + 主體 + 光線；camera 在沒寫 `motion_prompt` 時成為 Wan 運動文字；lint `shot-size-repeat`（相鄰兩張同景別，error）、`shot-size-variety`、`text-hold`（warn）；DIRECTOR.md 的節奏清單改寫進 deck skill 的「Quality v5」一節。 | `explainer/shot_language.py`、`deck.py`、`lint.py`、`illustrate.py`、`.claude/skills/deck/SKILL.md` | deck、illustrate |
| 4 | 頻道風格檔 `channels/styles/<code>.md`（畫風／色彩／構圖／禁用），5 個有 AI 插圖的頻道各一份（內容取自原 style_prefix）；illustrate 讀它組 prefix，slide prompt 要求「禁用」項會被拒；`quality.style_file: false` 退回 yaml 的 style_prefix。 | `explainer/style_file.py`、`illustrate.style_for/settings_for`、`scripts/illustrate.py` | illustrate |
| 5 | 素材語意挑選：關鍵字過篩後，前 6 名依「旁白句 vs 候選描述」的 CLIP 文字相似度重排（領先 <0.02 就維持原序；壞掉就保持原序）；紀錄 model、授權、分數進 credits。 | `explainer/footage/clip_rank.py`、`footage/client.py`、`media.py`、`scripts/media_to_visual.py` | media |
| 6 | 查證：Wan（lanczos）、stock footage（cover-crop）都在 media 步驟縮到 1920×1080；assembly 先 normalize→concat→merge audio 才燒 ASS；mascot 疊加只疊不縮；三個 Shorts 渲染的濾鏡圖都是 `ass=` 最後。**不用修**，加測試鎖住順序。 | `tests/unit/test_subtitle_order.py` | assembly |
| 7 | 伏筆帳本 `hooks_ledger.json`（article 產、deck 填 slide id；結構檢查、未收、先收後埋、不存在的 slide）；章節 `must_keep`／`must_avoid`（`Section` 新欄位，lint error）；連貫性檢查（同上下文＋單位的數量詞不同、「三個方法」後出現第四項）；兩者以 `hooks.txt`／`coherence.txt` 進 script 評審的 pro 素材，QC 也 warn；評審 `observations`（逐字引用＋平實描述，不准好壞與分數）與分數分開存進 score ledger。 | `review/hooks_ledger.py`、`coherence.py`、`script_checks.py`、`materials.py`、`schemas.PRO`、`prompts.py`、`rounds.py`、`score_ledger.py`、article／deck-outline／deck skills | article、deck、qc |
| 8 | 現況（不改）：`audio_mix/mix.py` 已是兩段式 loudnorm（pass 1 量測、pass 2 `linear=true` 套用，TP −1.5）；程式預設 `master_lufs=-14`（YouTube 目標），但 cel／deepsea／technews／yokai 設成 −23.4 以保留人聲（沿用九尾狐決策）。實測兩支離線成片 integrated = −23.4 LUFS、true peak −5.2／−8.8 dBFS。要不要改成 −14 是 Leon 的決策，我沒動。 | — | mix |
| 9 | 全套 pytest 見上；離線驗證見下。 | `scripts/quality_v5_offline.py`、`artifacts/quality-v5/offline.json` | — |

## 追加（orch-personal 2026-10-24：模型比較要同 prompt 給 Leon 看，不直接投入）
- **CLIP 排序現在預設關閉**：`channels/<code>.yaml` 的 `quality.clip_rank` 預設 `false`，`scripts/media_to_visual.py` 要加 `--clip-rank` 且設 `CF_CLIP_MODEL_DIR` 才會用。
- **`artifacts/quality-v5/clip-compare/`**：深海 6 個 stock 段（s06、s11、s13、s16、s21、s25）的「關鍵字挑」前 1 名各剪 5 秒（`sNN-keyword-pick.mp4`，640 寬）＋旁白句＋出處授權，在 `compare.json`。**「CLIP 挑」那一半沒做出來**：本機沒有權重，我想用 pip 把 sentence-transformers 裝到暫存目錄，被 auto mode 擋下，我沒有繞過。`compare.json` 的 `clip_pick` 全是 null。權重與套件到位後跑 `scripts/clip_compare.py --cache <worktree>/.cache/footage --dir artifacts/quality-v5/clip-compare` 就會補上 `sNN-clip-pick.mp4`（腳本已寫、只做語法檢查，**未實跑**）。
- **前後對照**：鏡頭語言／風格檔改變的是 prompt，要看圖得跑本機 mflux（`CF_MFLUX_*` 未設、也不該在這個任務跑模型），所以沒有圖；改附 `artifacts/quality-v5/style-before-after.md`（deepsea s01、s02 同一份 deck 的前後 prompt 全文）。既有 deck 沒指定 `shot_size`，所以鏡頭語言層對舊 deck 沒有改變畫面；風格檔只改了 prefix 的詞序與構圖句。兩者預設開，可關：`quality.shot_language: false`、`quality.style_file: false`（`shot_language` 開關目前只標示、lint 規則仍會跑；要完全關掉 lint 需另改，未做）。

## 授權處理
- **OpenMontage（AGPL）、InkOS（AGPL）**：只讀概念（知識庫筆記與研究摘要），所有程式、欄位名稱、權重與規則自行重寫，沒有貼任何原碼。
- **lemo-opuscar（MIT）、ffmpeg-skill（MIT）**：只改寫概念與節奏清單的意思；DIRECTOR.md 是用 WebFetch 讀了公開檔案，沒有複製段落，沒有引用程式片段，所以沒有需要保留的版權聲明；若日後直接引用要附 MIT 聲明。
- **CLIP 權重**：只接受兩個，記在 `clip_rank.MODEL_LICENSES`——`sentence-transformers/clip-ViT-B-32-multilingual-v1`（Apache-2.0，中文旁白對英文描述需要它）、`openai/clip-vit-base-patch32`（MIT，只有英文）；用到別的模型會直接拒絕。授權是我讀模型卡的印象，**未在本機重新核對模型卡**（🟡）。
- 程式不下載任何東西；權重要人手放到 `CF_CLIP_MODEL_DIR`。

## 離線驗證（只算分，沒重渲染）
來源：`artifacts/quality-v5/offline.json`（`scripts/quality_v5_offline.py`），🟢 可重跑。

| 片 | 檔 | 投影片感平均 | 高風險頁 | 新 lint 規則 |
|---|---|---|---|---|
| deepsea-1-stock | deck.json（26 頁） | 8.5 | 1（s24） | 無 |
| cel-run2-v4 | deck.v3.json（23 頁） | 20.4 | 2 | text-hold ×4 |
| cel-run2-v4 | deck.json（23 頁） | 23.3 | 4（s06、s10、s18、s22） | shot-size-variety、text-hold ×4 |

- cel v3→v4 的分數**沒有變好**（20.4→23.3）：v4 把文字頁換成 AI 圖，但相鄰 parallax 圖沒指定運鏡，吃到 `same_move`；這是新評分抓得到、v4 當時沒有規則管的事。沒有真 producer 可跑，所以「自動修一次」的**前後數字拿不到**，只有單元測試證明流程（問一次、有改善才留、失敗還原、不二次詢問）。
- 靜止偵測（成片 `release.mp4`）：

| 片 | static | motion | pan | static 佔比 | dead zone |
|---|---|---|---|---|---|
| deepsea-1-stock（9:58） | 108.5 s | 455.8 s | 0 | 19 % | 2 段、共 32.2 s（約 0:30–0:46 與 1:07–1:23，count-up 動畫結束後的靜態頁） |
| cel-run2-v4（8:04） | 70.2 s | 394.8 s | 0 | 15 % | 0 |

  調校過程：第一版門檻把深海 55 秒判成 static，原因是兩頁文字頁的切換差異低於切鏡門檻、以及 parallax 在深色圖上每步差異很小；改成「相鄰取樣差 <0.2 的平靜段」加字幕閃動吸收後才合理。抽幀目視確認 0:30、0:38、0:46 是靜止的 big-number 頁。**限制**：pan 判定很保守，兩支實片都是 0；parallax 的深色圖若動得比 0.2 灰階還小會被當成 static；mascot 說話的小幅動畫會被算成 motion，所以有 mascot 的頁面可能漏報。門檻（`CALM_STEP`、`BLIP_*`）都在 `static_scan.py` 頂端。
- 字幕順序、loudnorm：見上表第 6、8 項。

## 沒做／沒驗的
1. **CLIP 排序沒有用真權重跑過**（本機無 CLIP、無 sentence-transformers、HF 快取只有 Wan、depth、whisper、bge-m3、e5）。單元測試用假 embedder；候選描述用文字（供應商沒給縮圖），未來有影格時 `embed_images` 同介面可擴充。🟡
2. **自動修一次的實際效果沒量到**（見上）。
3. `hooks_ledger.json` 目前只有 skill 指示與檢查，**article 的 `check_article.py` 沒加驗證**；沒有帳本的舊 run 不會出任何訊息。
4. observations 只加在 script 階段的 pro 評審；title／final 等沒加；`rounds._merge_facts`／carry 重用的舊座位沒有 observations。
5. 短片（`short_script`、news）沒套用伏筆帳本、鏡頭語言、投影片感（那些是 deck 長片專用）。
6. `shot_size` 以 prompt 字詞推測的部分是英文關鍵字，舊 deck 沒指定時不算重複（避免誤殺）。
7. 沒有動 `channels/ent.yaml`、`offwork.yaml`（無 AI 插圖）。

## wan.py 合併處理
revisual 把 `--negative-prompt` 固定為 `NEGATIVE_PROMPT`，stock-footage 讓 `WanPolicy.negative_prompt` 覆寫預設。合併後：`p.negative_prompt or NEGATIVE_PROMPT`。因此 stock-footage 的測試「無 policy 不帶 --negative-prompt」不再成立，已改成「無 policy 用預設 negative prompt」。

## 清理
沒有留下測試檔或暫存分支；暫存影格與腳本放在 `$CLAUDE_JOB_DIR/tmp`（由系統清理）。主 checkout 未動。知識庫：只改四則參考筆記（OpenMontage、lemo-opuscar、ffmpeg-skill、InkOS）的 tags 與「下一步」；`本機 AI 影片模型比較` 不屬本次，沒動。

## 下一步（給 orchestrator）
- 取得 CLIP 權重放到 `CF_CLIP_MODEL_DIR`（並 `pip install sentence-transformers`）後，跑一次 deepsea 的 media 步驟比對挑片差異。
- 下一支真實 run 觀察：`review/slideshow_risk.json`、`qc/static_scan.json`、score ledger 的 `observations`。
- 決策：賽璐璐／深海／yokai／technews 的 master_lufs 要不要從 −23.4 改成 −14。
