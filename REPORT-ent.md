# REPORT — 娛樂新聞頻道 `ent`（2026-10-23）

分支 `worktree-cf-ent`（fb74850 = speed3 ← merge `worktree-cf-technews` ← merge `worktree-cf-lanes-deadlock`）。未 push、未開瀏覽器、未上傳、無付費服務（配音為本機 VoxCPM2）。
證據：🟢 本機實測／🟡 只驗到存在或估算。

## TL;DR
- 🟢 **成片 1 支**：`artifacts/ent/ent-2026-10-23-golden-bell-delay.mp4`（Shorts，38.9 秒，3.4 MB，9:16），停在 `gate_final` 之前（評審團通過、QC 0 error）。題目：金鐘獎因颱風延期（自由時報）。
- 🟢 護欄全是程式：來源白名單、禁碰題材過濾、逐句出處查核（無出處＝錯誤→自動修一次）、畫面只准文字卡（QC 擋）。新增 32+ 項測試，全套 pytest **1870 passed**（`test_multi_provider` 既有失敗已 deselect）。
- 頻道名稱候選：**娛樂快報**（暫用）／星聞速報／演藝圈有據。
- 費用（名目，訂閱額度，上限估計）：約 US$4.3（選題 0.80＋成片 run 約 3.1＋另兩支只寫到稿約 0.4），預算 20。
- 需知：(1) 評審團選的 3 則全是同一事件（金鐘獎延期）——沒有跨事件去重；(2) 劇本編劇給 3/10（只記分數不擋）；(3) 沒做長片（見 §3）；(4) 聲音由 VoiceDesign 設計，F0 偏高（297 Hz），聽感未人工確認。

## 1. 頻道設定
`channels/ent.yaml`（brand `ent`＝新增品牌：洋紅色票、麥克風剪影、`docs/examples/brands/ent.json`）；無角色（`rig_ready: false`）；`take_label: 快報點評`（「編輯觀點」與 technews 撞 identity 測試）；第四段改為「各方說法」（`analogy_required: false`，不需國高中比喻）；評審團 persona 5＋holdout（追星上班族、一般觀眾、新聞系行銷、家長、退休公務員；影評 holdout）；`channels.ent` 覆寫同 technews（Short 稿退回 `news_script`）。
格式判定沿用 technews 的 `news/select.py`（評審席投票＋原文字數 ≥5000 才准長片＋每日長片上限 1）。

## 2. 來源白名單（`series.news.feeds`，公開 RSS，每站每次 1 個請求，`PoliteHttp` 間隔＋30 分鐘快取）
| id | 媒體 | 今日實測 |
|---|---|---|
| cna | 中央社（文化） | 20 |
| ltn | 自由時報娛樂 | 40 |
| udn | 聯合報 | **0**：RSS 回 20 筆空白佔位（無標題／連結、pubDate 1970）；解析全丟，等對方修好自動恢復 |
| ettoday | ETtoday 星光雲 | 50 |
| yahoo | Yahoo奇摩娛樂 | 30 |
| nhk | NHK（cat3 科学・文化） | 12 |
| soompi | Soompi | 60 |
| variety / deadline | Variety / Deadline | 10 / 12 |
- Oricon：RSS 回 410，未納入（🟢 實測）。
- 抓取當下 26 則被護欄剔除（`output/ent-2026-10-23/excluded.json`）；179 則去重後在 36 小時內；讀原文 20 則全部可讀。

## 3. 護欄實作（程式位置與測試 `tests/unit/test_news_ent.py`）
1. **只採白名單媒體、每句標出處**：`feeds.parse_feed` 連結不在該 feed 的 `domains` 就丟（計入 off_list）；`daily.admit` 再擋一次；`script.lint` 擋 sources 不在白名單；`claims.audit` 要求每句事實的 claim 引用「實際讀過的那一頁」且 `evidence` 必須逐字出現在原文快取。host 比對用 host 後綴，非子字串（`ltn.com.tw.evil.example` 不過）。
2. **傳聞不當事實講**：每句事實（hook／what／why／各方說法）需有 claim（`reported`／`confirmed`）。`reported` 句必須含「據」＋媒體名＋報導用詞；`confirmed` 需原文佐證有當事人／經紀公司／官方自己說的字樣且句中點名是誰。違反＝`NO_CLAIM／BAD_SOURCE／NO_EVIDENCE／UNATTRIBUTED／NOT_CONFIRMED` 錯誤。**走 auto_fix**：`fact_audit` 步驟（`audit_step.py`）查一次→刪無法出處的句、把有出處但說法不當的改寫成「據X報導，…」→不重查往下走；記錄在 `review/fact_audit.json`（含 before/after sha）與 `review/auto_fix.jsonl`（`fix_issued`／`passed_without_recheck`）；`fact_on_fail: stop` 時同樣的錯誤停下且不改檔。空段落以標題句保底。測試涵蓋每個錯誤碼、改寫冪等、不改輸入、policy stop。今日成片腳本：2 項錯誤（主管機關發言被保守降為「據報導」）自動改寫後通過。
3. **禁碰題材**（未成年人、性醜聞細節、病情死因、私人住址／家人，中英日關鍵字，`guard.py`）：標題＋摘要在排名**前**剔除；選題評審席有 `sensitive` 旗標，任一席標記即排除；完稿 `lint` 再擋（整支重選題）。刻意寬鬆（會多殺，例如含「孩子」的劇名）。測試含三語例句與正常標題不誤殺。
4. **畫面**：Shorts 只用自製文字／來源卡（無 `<img>`）；`qc.visual_policy_findings` 對「無 stock／AI 圖／美術／原片且無角色」的頻道，若頁面含 img/video/url() 或 credits 有 Wikimedia CC（含作者與授權）以外的第三方素材即 error。本次 QC：「7 pages, text cards only; no third-party media」🟢。本次未使用 Wikimedia 照片。
- 其他頻道不受影響（測試鎖住：tech 選題 prompt 不變、`admit` 對 technews 為 no-op、chipcat／technews 不套視覺規則）。

## 4. 聲音
Qwen3-TTS VoiceDesign（指令：三十歲左右男性、輕快俏皮的電台娛樂節目主持）6 個 seed（4100–4105）。**注意：6 個 take 的 F0 皆 221–297 Hz，偏女聲／中性，指令的「男性」沒被完全遵守**🟡（未人工聆聽）。選 take4104（對 chipcat 最低）→ `~/.local/share/content-farm-voices/ent-ref.wav`＋`.txt`，由 VoxCPM2 複製。
ECAPA 相似度（同人約 0.8+；chipcat/cel 彼此 0.44，chipcat/offwork 0.37）：
| take | chipcat | cel | offwork（停用頻道） |
|---|---|---|---|
| 4104（採用） | 0.316 | 0.287 | 0.648 |
| 4101 | 0.364 | 0.256 | 0.737 |
| 其餘 | 0.35–0.39 | 0.25–0.33 | 0.65–0.76 |
對 chipcat／cel 低於既有頻道間距；對 offwork 偏高（0.65，offwork 已停用）。**科技新知的 ref 在我跑時尚未產生，無法比對 🔴**。建議 Leon 聽 `ent-ref.wav` 與成片後決定是否重設計（改指令強調低沉男聲、再跑 6 seed）。實測語速未回填（`chars_per_second` 仍為暫估 4.6）。

## 5. 分數紀錄（`review/score_ledger.json`，只記不擋）
- 腳本評審：離開中位 0.482、編劇 **3/10**（未達 6.5，記錄後放行）。
- 成片評審：離開中位 0.387（過 0.35）；視覺欄 7.8、內容欄 6.0（red 燈，不擋）；縮圖一致 3/3；剪輯 4.5。
- 選題：20 則讀完，平均分最高 8.25、其餘 7 以下；詳 `output/ent-2026-10-23/selection.json`。
- 事實：`fact_audit` 2 項錯誤自動修（上述）。

## 6. 費用與牆鐘
- 名目費用見 TL;DR（以 cost_usd 加總，可能略高估）；未用付費 API key（`CF_ANTHROPIC_API_KEY` 設為佔位值只為通過 Settings 驗證，TTS 為本機）。
- 成片 run 牆鐘 9714 s（首事件 13:11→15:53 UTC）：**排隊 2566 s**（含 swap≥90% 與 GPU 互斥）、機器實做 248 s（voice 87.8、news_render 56.7、script agent 52.3、成片評審 30.3）、決策／未歸類等待 6231 s＋668 s（主要是等聲音設計的本機佇列：VoiceDesign 排了約 1.5 小時，被 technews-run1 預約與記憶體 <24 GB 擋住；後來 merge `worktree-cf-lanes-deadlock` 重啟）。
- 選題＋3 支稿約 10 分鐘；網路抓取＋讀 20 篇約 25 秒。

## 7. 成片
`artifacts/ent/ent-2026-10-23-golden-bell-delay.mp4`（Shorts 直接放；`output/ent-2026-10-23-ltn-921ae71267/`）。另兩支（`…ltn-3c3f38f935`、`…yahoo-4af302233d`）只寫到 `news_prepare`（稿＋audit），同一事件，未配音渲染。**長片 0 支**：今日 20 則原文最長的中文稿約 2.5–4.6k 字 <5000 門檻（只有 Deadline 8.2k，但評審 5.75 分低於 6）。

## 8. 風險／待辦
- 🟡 腳本偏單調（同一句型「據自由時報報導」重複 4 次，這是保守改寫的代價）；編劇 3 分。
- 🟡 選題無跨來源「同事件」去重（今日 3 則同題）；建議下一步在 `rank.dedupe` 加事件級聚類或在 `select` 加「同題只留一則」。
- 🔴 `confirmed` 判定依賴關鍵字（證實／表示／宣布…），主管機關或發言人的陳述會被保守降成 reported。
- 🔴 禁碰題材關鍵字是寬鬆正則，非語意判斷；評審席 `sensitive` 是第二道。
- 🔴 `gate_final` 未核可（依派工停在其前）；未上傳。
- 副作用：`output/ent-*`（gitignored）；聲音暫存在 `~/.claude/jobs/1fb7fba3/tmp/`；`~/.local/share/content-farm-voices/ent-ref.{wav,txt}` 為本任務新增。

## 進度紀錄
- 2026-10-23：全部完成並 commit；pytest 1870 passed。
