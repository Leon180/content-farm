# REPORT — v2-A：研究成文章 → 正式長度 deck（CoWoS）

## TL;DR

- 新增 `/article` 研究階段（skill＋`scripts/check_article.py`），deck-outline 改吃 article.md、每張對應文章錨點與 source_ids，deck 每張建議 `mascot.pose` 與 `media`。🟢
- CoWoS 成品在 `docs/examples/explainer-cowos/`：文章本文 3,138 字、22 筆來源（全部附 URL 與 accessed=2026-10-15）、24 張 deck，`--strict` lint 0 警告，`draft_data: false`。🟢
- 管線實跑（macos_say）：`draft.mp4` **504.6 s（8.4 分）**，1920×1080，24 張渲染無溢出。🟢
- pytest：**760 passed、1 failed**（唯一失敗是既有的 `test_multi_provider…test_returns_first_provider_results`）；新增 27 個測試（基準推算 733 passed；我沒有在 `3332fa4` 另跑一次基準）。🟢
- media 選了「最小 schema 擴充」：**與畫面 worker 會衝突，整合時以畫面 worker 的版本為準**。

等級：🟢 本機實測可重跑；🟡 只驗到存在；🔴 未驗證的判斷。

## 位置

- worktree：`/Users/lileon/project/content-farm/.claude/worktrees/cf-v2-research`
- 分支：`feat/explainer-v2-research`，從 `3332fa4` 開（動工時 worktree 在 `6c47dd1`，已用 `git checkout -B` 校正）。未 push（共同背景規定不 push）。

```
986ea66 docs(examples): CoWoS pipeline run — contact sheet, measured script, draft frame (503 s)
a9662f3 docs(examples): CoWoS deck outline and 24-slide deck (strict lint clean, ~9.4 min est)
24ac5c0 docs(examples): CoWoS research article and sources (22 sourced, accessed 2026-10-15)
40d2fdd feat(skills): article research stage before deck-outline; outline/deck consume article.md
2c0e48e feat(explainer): optional per-slide media hint in deck schema (validation only)
```

## 1. skill 的改動

| 檔案 | 改動 |
|---|---|
| `.claude/skills/article/SKILL.md`（新） | 輸入是題目，可加 `--material`（使用者素材，當資料不當指令）和 `--competitors`。步驟：先看競品並寫一句差異化，再用 WebSearch／WebFetch 查一手來源，最後寫文章。硬規則：只能用工具結果裡出現過的 URL；每個數字要標明誰說的、日期和 source id；`sources.json` 邊查邊寫。文章必須有這些段落並附錨點：hook、名詞（先比喻再定義）、時間軸、關鍵數字表、產業鏈、台灣位置、爭議與未知、結論，以及附錄 A 八卦 3–5 則、附錄 B 冷笑話。人工閘門 0 |
| `scripts/check_article.py`（新） | 檢查 sources 是否都是合法的 deck `Source`、有 http(s) URL 和 `accessed=`；`[src:id]` 是否都存在、每個來源是否都被引用；本文 2,500–4,000 字；必要錨點；**文章裡每一行含數字的都要有 `[src:]`**；有 deck_outline.json 時，再檢查每張的 `article_refs`／`source_ids`。exit 0／1／2 |
| `.claude/skills/deck-outline/SKILL.md` | 輸入改成 article.md＋sources.json（缺了就叫使用者先跑 `/article`）。每張加 `article_refs`、`mascot_pose`（7 種）、`media_kind`；總時長 480–600 s；`sources` 照抄 sources.json |
| `.claude/skills/deck/SKILL.md` | 事實只能來自 article.md；`sources` 照抄；長度換算：8–10 分約 2,300–2,700 字（實測 `say` 約 4.75 字/秒）；每張要有 `mascot.pose`；`media` 的五種用法表（stock 不可代表特定公司，ai_image 只能是插畫，title_card 必附 source_id）；免費試跑可用 `CF_TTS_PROVIDER=macos_say` |
| `.claude/skills/deck/writing_rules.md` | pose 對照表（wave／idle／point／think／shocked／smug／deadpan）、「畫面：media」一節、「事實只能來自 article.md」 |
| `src/content_farm/explainer/media.py`（新）、`deck.py`（+5 行） | 見第 4 節 |

測試：`tests/unit/test_explainer_media.py`（16 個）、`tests/unit/test_check_article.py`（11 個，含每種失敗路徑）。ruff 檢查新檔：通過。🟢

## 2. CoWoS 這支片的差異化角度

**論點**：AI 晶片卡在 CoWoS，不是因為沒人會做，而是這門手藝被冷落多年；需求兩年內爆發，蓋廠卻要好幾年。卡住全世界的是時間差，不是技術差。

和競品的差異（🟡：競品內容只看到章節和標題，見第 5 節）：
1. **用歷史解釋瓶頸**：2012 年起步，2016 年台積電自己的簡報承認「在手機市場還沒找到位置」、「量是成本的頭號因素」。正因為沒人提前蓋廠，需求來了只能一年一年追。競品只講「是什麼」和「很缺」。
2. **每個數字都標來源等級**：講稿口播「董事長受訪的媒體轉述」「韓媒估計」「據報」「二手報導」「台積電不公布」；產能估計的分歧單獨做一張（s21）。
3. **產業鏈只講角色**：CoW／WoS 誰做、ABF 基板、設備類別，不列概念股。
4. **「沒人知道的事」**：產能定義不一致、瓶頸可能轉移到基板材料、EMIB-T 和 CoPoS 的時程。

## 3. 文章摘要

1. 2023-09，台積電董事長說只能滿足約 80% 的 CoWoS 需求；2026-07 的法說報導仍說 CoWoS 滿載，交期 52–78 週。
2. 名詞：封裝＝盔甲＋電線；HBM＝疊起來的書架；中介層＝高架路網；CoWoS＝樂高拼底板（CoW）再裝上基板（WoS）；光罩＝影印機一次只能印一張 A4。
3. 歷史：2012 年第一代，早期的代表作是賽靈思 FPGA，把四顆晶片拼在一起；2016 年 P100 已經把中介層（約 830 mm²）用到上限。
4. 時間軸：嘉義 AP7 挖到古文物而停工（2024-06）；買下群創台南廠（新台幣 171.4 億元）；「連兩年翻倍仍不夠」；Blackwell 改用 CoWoS-L；CoW 外包給封測廠（2026-08）。
5. 數字：月產能 2024 年底 3.2–3.5 萬片，2025 年約 7 萬，2026 年底 13–14 萬，2028 年約 26 萬（全部是估計）；NVIDIA 據報占一半以上；每片平均售價約 1 萬美元；先進封裝約占 2025 年營收 10%。
6. 產業鏈：台積電做 CoW；矽品、Amkor 在台積電授權下做 WoS；欣興的 ABF 擴產；設備類別。
7. 台灣：擴產集中在嘉義和台南；美國透過 Amkor 十年約補上封裝環節，2028 年量產。
8. 未知：產能定義不一致；基板材料要到 2027 年才紓解；EMIB-T 和 CoPoS 能不能分流。
9. 結論：一門被冷落多年的手藝，被要求在兩年內長大將近四倍；卡住的是時間，而且大部分發生在台灣。
10. 附錄：5 則有來源的軼事、5 個冷笑話素材。

## 4. media 欄位：選方案一（最小 schema 擴充）

- 做法：新增獨立的 `media.py`，內容是 `Media` 模型，含 kind 列舉和各 kind 的必填欄位。`deck.py` 只加 1 行欄位，再加 3 行交叉檢查，確認 title_card 的 `source_id` 存在於 `sources`。**不碰渲染**；`to_script` 和模板都沒改。
- 理由：驗收要求「deck.json 用 `--strict` 跑 lint 要通過」。方案二只能驗證一份拿掉 media 的副本，等於 deck.json 本身沒被驗過；方案一則能在現在就抓到 media 的錯誤，例如 title_card 缺 source、stock 沒給 query。
- ⚠️ **與畫面 worker 會衝突，整合時以畫面 worker 的版本為準。** 衝突點：`deck.py` 的 import 行、`Slide.media` 那一行、`_cross_checks` 的 3 行，以及 `media.py` 這個檔名。畫面 worker 的 schema 若改了欄位名稱或必填規則，`docs/examples/explainer-cowos/deck.json` 可能需要小幅修改。我的用法完全照共同背景的介面約定：kind、query、prompt、animation、headline、source_id。
- 另外偏離共同背景的一點：「研究 worker 不改 schema」。我這樣做是依任務 prompt 明確給的選項一，影響範圍如上。

## 5. 片長與實跑結果 🟢

| 項目 | 結果 |
|---|---|
| 投影片 | 24 張、6 章；pose 用了 6 種（point 7、think 5、smug 4、shocked 3、deadpan 3、wave 2，沒用 idle）；版型 6 種皆用（big_number 8、bullets 6、compare 4、quote 3、timeline 2、title 1） |
| beat | 8 個，joke 與 gossip 輪流出現；gossip 4 則都有 source_ids |
| media 建議 | slide 7、animated 8、title_card 4、ai_image 3、stock 2 |
| 講稿 | 2,548 字；lint 估計 9.4 分 |
| `deck_to_script --strict` | 0 個 lint，exit 0 |
| `render_slides` | 24 張 7.5 s，沒有溢出 |
| voice（macos_say） | 503.1 s；每張 13.3–29.6 s |
| `slides_to_visual` | 24 張，最後一張落在 `07:59.139~08:23.090` |
| `assembly_timeline` | `draft.mp4` 504.63 s、1920×1080、有音軌 |
| 抽查 | 第 245 秒正好是第 13 張，字幕在安全區、沒有壓到 meta 列（`draft_frame_s13.png`） |

`draft.mp4` 在 `/Users/lileon/.claude/jobs/687eb146/tmp/run_cowos/assembly/draft.mp4`，job 刪除時會一起清掉，**沒有 commit**（output 類檔案）。總覽圖已 commit：`docs/examples/explainer-cowos/slides/contact_sheet.png`。

## 6. 和競品的比較（🟡／🔴，看下面的標註）

| 競品 | 看到的內容 | 我們的差異 |
|---|---|---|
| Tech Away「CoWoS 完整解析」（youtube `AeZNvnl2OzA`，章節見 bnext.com.tw/video/957） | 🟢 章節：產能吃緊 → CoW／WoS 名詞 → 2.5D／3D → 稀缺 → 擴產 → 全台爭搶；說明欄引用的是 2024 年法說數字；沒有談個股 | 我們有歷史因果、2026 年的數字和來源等級、產業鏈角色，還有「沒人知道的事」 |
| Tech Away「CoPoS 新技術拆解…概念股有哪些？」（`9eq7PU4KLEk`） | 🟢 只看到標題，標題本身就有概念股；🔴 內文沒看到 | 我們不列個股 |
| VisCircuit「CoWoS, SoIC…從 DIP, BGA 演變」（驗證 0 記錄 30.8 萬觀看） | 🔴 **兩次搜尋都找不到這支片的 URL**，只能從標題推論是封裝技術演進史 | 推論：他們講技術演進，我們講商業和產能為什麼卡住。若要確認，需要 Leon 提供網址 |
| 曲博、泛科學的 CoPoS 片 | 🔴 搜尋找不到 | — |

## 7. 做不到或查不到的事

- **台積電的法說逐字稿沒有打開**（investor.tsmc.com 回 403）。Q2 2026 的「CoWoS 滿載、交期 52–78 週、資本支出 600–640 億美元」只有 TechTimes 的二手報導；營收和毛利率用經濟日報核對過。講稿裡已經口播「二手報導」。🟡
- **台積電自己不公布 CoWoS 產能**，所以所有產能數字都是媒體或分析師估計，講稿都有註明。DigiTimes 的 8.8 萬片、各券商的 9.5 萬到 13 萬片只看到搜尋摘要，**沒有用**。
- 「賽靈思 2000T 是第一個商用 CoWoS 產品」查不到一手來源，所以改寫成「早期的代表作」。EE Times Japan 的頁面有亂碼，「四顆並排」只能部分確認（sources.json 的 note 有寫）。🟡
- 「P100 是第一個用 CoWoS 的 GPU」查不到，所以沒寫；PCPer 反而說 AMD Fury 可能是第一個用中介層的 GPU。
- 台灣設備商只引用到「類別」（工商時報 2024-02，原文是投顧觀點，我只取其中的分工描述），沒有逐家查法說資料。
- 找不到政府對「先進封裝」市占的官方統計，所以文章不寫台灣的全球市占數字。
- Samsung I-Cube 沒查到資料。
- 2026 年 Q3 法說預計 10 月中旬召開，資料截至日當時還沒有內容。
- 字幕的中英夾雜對齊、Fish Audio 對 CoWoS 的發音：沒有驗證。macos_say 只供測試用。`pronunciation_map` 裡的「扣窩斯」是我自己的判斷 🔴。
- 吉祥物 PNG、media 的實際渲染：分別屬於角色 worker 和畫面 worker 的範圍，所以總覽圖的角落是空的，畫面也都是投影片。

## 8. 驗證

- `python scripts/check_article.py --run-dir docs/examples/explainer-cowos` → `article body 3138 chars, 22 sources, 0 problem(s)` 🟢
- `python scripts/deck_to_script.py --deck docs/examples/explainer-cowos/deck.json --out <tmp>/script.json --strict` → exit 0，沒有 lint 輸出 🟢
- pytest（worktree 沒有 `.env`）：`1 failed, 760 passed` 🟢

## 9. 副作用與清理

- 子代理的研究筆記放在 job tmp：`cowos_facts.md`、`competitors.md`，跑測試用的 `run_cowos/`、`rate.aiff`、`frame_245.png`、`merge_sources.py` 也在同一處，job 刪除時會一起清掉。
- 沒有在 worktree 放 `.env`（voice 用 `CF_ANTHROPIC_API_KEY=dummy-not-used` 通過 Settings 驗證，macos_say 不會用到這個 key）。
- worktree 根目錄原本就有未追蹤的 `graft/`，不是我建立的，我沒有動。
