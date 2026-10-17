"""``upload/manual/README.md``: the YouTube Studio upload checklist, in Studio's order."""

from __future__ import annotations

from content_farm.production import voice_source
from content_farm.production.manual_kit import TAGS_MAX_CHARS, TITLE_MAX, Kit, human_duration, human_size
from content_farm.production.publish import DISCLOSURE_MARK

MACHINE_VOICE_BANNER = "> ⚠️ **暫用機器聲（macOS say），待換 Fish Audio 後重出。這一版不要公開。**\n"
PREVIEW_BANNER = ("> ⚠️ **成片閘門尚未核可**：以下是預覽資料。Leon `produce.py approve --gate final` "
                  "並跑完 package 後，重跑 `produce.py manual-kit` 才是正式版。\n")
PRIVACY_NAMES = {"private": "私人", "unlisted": "不公開", "public": "公開"}


def _status_lines(kit: Kit) -> list[str]:
    qc = "未跑" if kit.qc_errors is None else f"{kit.qc_errors} error / {kit.qc_warnings} warn"
    meta_src = ("manual-kit 臨時產生（成片閘門未核可目前成片）" if kit.preview
                else "`upload/youtube_meta.json`（gate_final 已核可目前成片）")
    voice = voice_source.provider_name(kit.voice_provider) + ("（暫用）" if kit.machine_voice else "")
    return [
        f"- 目標頻道：**{kit.channel.name}**（`{kit.channel.code}`，{kit.channel.line}）"
        + ("— Shorts（直式，Studio 會自動判定）" if kit.is_short else ""),
        f"- 影片檔：`{kit.video}`",
        f"- 片長 {human_duration(kit.seconds)}（{kit.seconds:.1f} 秒）・檔案 {human_size(kit.size_bytes)}",
        f"- 配音：{voice}・QC：{qc}",
        f"- metadata 來源：{meta_src}",
        "- 本機預覽：`preview.html`（上傳前先用瀏覽器開一次：字幕、章節、說明欄）",
    ]


def warnings(kit: Kit) -> list[str]:
    meta, notes = kit.meta, []
    tags_len = len(",".join(meta.get("tags") or []))
    if tags_len > TAGS_MAX_CHARS:
        notes.append(f"- 標籤合計 {tags_len} 字元，超過 {TAGS_MAX_CHARS}，要刪幾個。")
    if kit.qc_errors:
        notes.append(f"- QC 有 {kit.qc_errors} 個 error，見 `qc/qc_report.json`。")
    if kit.is_short and kit.seconds > 60:
        notes.append(f"- 直式影片 {kit.seconds:.0f} 秒，超過 60 秒不一定被判成 Shorts。")
    if not kit.subtitles:
        notes.append("- 找不到 `subtitles/subtitles.srt`，字幕這步跳過。")
    return notes


def _visibility(meta: dict) -> str:
    if meta.get("publish_at"):
        return f"「排定時間」：{meta['publish_at']}（先選私人再設排程，到點自動公開）"
    return f"「{PRIVACY_NAMES.get(meta.get('privacy_status'), '私人')}」（Leon 看過成片再改）"


def synthetic_advice(meta: dict) -> str:
    """Studio's 「變造或合成內容」 answer; the description's disclosure line is separate."""
    if meta.get("contains_synthetic_media"):
        return "選 **「是」**（頻道設定 `altered_content_label: true`）。說明欄最後一行另有文字揭露。"
    if DISCLOSURE_MARK in meta.get("description", ""):
        return ("選 **「否」**，不勾（Leon 2026-10-16 決策 916c2864e31f）。合成內容改在說明欄最後一行用文字揭露，"
                "已寫在 `description.txt`。AI 圖依規則只用插畫／水墨，不做擬真畫面。")
    return "選 **「否」**（本片沒有合成語音或 AI 圖，說明欄也沒有揭露句）。"


def _elements(kit: Kit) -> list[str]:
    subs = ("   - 字幕：新增語言 **中文（台灣）**→「上傳檔案」→「含時間碼」→ `subtitles.srt`。"
            "畫面已燒入字幕，CC 預設關閉，觀眾自行開啟才會疊兩層。" if kit.subtitles
            else "   - 字幕：這支片沒有 srt。")
    if kit.is_short:
        spec = kit.short_spec
        related = (f"改在「相關影片」連到「{spec.long_channel}」的《{spec.long_title}》（長片上線後再設）"
                   if spec else "需要的話在「相關影片」連到同頻道的長片")
        return [subs, f"   - Shorts 沒有片尾畫面／資訊卡；{related}"]
    return [subs,
            "   - 片尾畫面：最後 20 秒放「訂閱」＋「最新上傳的影片」",
            "   - 資訊卡：在章節轉折點放同頻道相關影片或播放清單（同頻道還沒有其他影片前先不加）"]


def _test_and_compare(kit: Kit) -> list[str]:
    """Three thumbnails → Studio 「測試與比較」 (Leon 2026-10-17; YouTube Help 13861714)."""
    if not kit.variants or kit.is_short:
        return []
    names = "、".join(f"`{p.name}`" for p in kit.variants)
    return [
        f"   - **縮圖 A/B（{len(kit.variants)} 款都上傳）**：在縮圖區按「測試與比較」（只有電腦版 Studio、且已開啟進階功能才有），"
        f"依序上傳 {names}。",
        "     - 測試期間**不要改標題或縮圖**（改了測試會中止）；YouTube 以「觀看時間占比」選勝出款，最長約兩週。",
        "     - 結果：Winner＝自動全面換成該款；Performed Same／Inconclusive＝保留第一張（A）。結果截圖回報 orchestrator。",
        "     - 預約公開或私人影片要等公開後測試才會開始；Shorts 不能測。",
    ]


def _studio_steps(kit: Kit) -> list[str]:
    meta = kit.meta
    return [
        "## YouTube Studio 步驟",
        "",
        f"1. 右上角切換到頻道 **{kit.channel.name}**（不是其他品牌頻道）。",
        "2. 「建立」→「上傳影片」→ 選上面的影片檔。",
        "3. **詳細資訊**",
        f"   - 標題：貼 `title.txt`（{len(meta['title'])}/{TITLE_MAX} 字）",
        "   - 說明：貼 `description.txt`（章節、參考資料、素材授權、AI 揭露都在裡面）",
        f"   - 縮圖：上傳 `{kit.thumbnail.name if kit.thumbnail else 'thumbnail.png'}`。{kit.thumbnail_note}",
        *_test_and_compare(kit),
        f"   - 播放清單：「{kit.playlist}」（沒有就新建）",
        "   - 觀眾：**「否，這不是為兒童打造的內容」**",
        "   - 展開「顯示更多」：",
        f"     - 變造或合成內容：{synthetic_advice(meta)}",
        "     - 標籤：貼 `tags.txt`",
        "     - 影片語言：**中文（台灣）**；字幕認證：無",
        f"     - 類別：**{kit.category}**",
        "     - 授權：標準 YouTube 授權；允許嵌入",
        "4. **影片元素**",
        *_elements(kit),
        "5. **檢查**：等版權與廣告適合度檢查跑完；有 Content ID 聲明就先停，回報 orchestrator。",
        f"6. **瀏覽權限**：{_visibility(meta)}",
    ]


def build_readme(kit: Kit) -> str:
    chapters = kit.meta.get("chapters") or []
    notes = warnings(kit)
    files = ["title.txt", "description.txt", "tags.txt", kit.thumbnail.name if kit.thumbnail else "thumbnail.png",
             *(p.name for p in kit.variants),
             *(["subtitles.srt", "subtitles.vtt"] if kit.subtitles else []), "preview.html"]
    lines = [
        *([MACHINE_VOICE_BANNER] if kit.machine_voice else []),
        *([PREVIEW_BANNER] if kit.preview else []),
        f"# 手動上傳：{kit.meta['title']}",
        "",
        *_status_lines(kit),
        "",
        *(["## 先處理", *notes, ""] if notes else []),
        *_studio_steps(kit),
        "",
        "## 章節（已在說明欄內）",
        "",
        *([f"- {c['timestamp']} {c['title']}" for c in chapters] or ["- （無）"]),
        "",
        f"AI 揭露：Studio 勾選 `contains_synthetic_media={kit.meta.get('contains_synthetic_media')}`；"
        f"說明欄文字揭露{'有' if DISCLOSURE_MARK in kit.meta.get('description', '') else '無'}。",
        "",
        "## 檔案",
        "",
        f"`{kit.directory}/`：" + "、".join(files),
        "",
    ]
    return "\n".join(lines)
