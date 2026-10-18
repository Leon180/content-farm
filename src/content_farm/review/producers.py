"""Producer agents (topic, article, deck, titles & thumbnails) as ``claude -p`` subprocesses that
write their files into the run-dir. model / effort come from the stage's ``producer`` tier in
review_panels.yaml. A rework call gets the routed fix list (``review/<gate>.fixes.json``) and
must touch only what the fixes and their linked scope name.

Each call returns a tiny JSON receipt (``RECEIPT``) so the result is schema-checked like a review.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from content_farm.review.client import Call, CallResult, run_call
from content_farm.review.config import ReviewConfig, Tier

REPO = Path(__file__).resolve().parents[3]
RECEIPT = {"type": "object", "additionalProperties": False, "required": ["files", "summary"],
           "properties": {"files": {"type": "array", "items": {"type": "string"}}, "summary": {"type": "string"},
                          "fixed": {"type": "array", "items": {"type": "string"}}}}
TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch")   # + Bash scoped to the repo python

SCRIPTS = ("check_article.py", "deck_to_script.py", "make_thumbnail.py", "render_slides.py")
TIMEOUT_S = {"topic": 1500, "article": 2700, "deck": 3600, "thumbnail_spec": 1800}

# step → (stage whose producer tier applies, gate whose fixes apply)
STEP_STAGE = {"topic": ("topic", "topic"), "article": ("article", "article"), "deck": ("script", "deck"),
              "thumbnail_spec": ("title_thumb", "title")}

COMMON = """你是 content-farm（繁中 YouTube 內容工廠）的製作 agent，工作目錄就是這支片的 run-dir：{run_dir}
頻道設定：{repo}/channels/{channel}.yaml（讀它：品牌、角色、片長、規則）。既定規則：艱深名詞先用國高中程度比喻再給定義；
八卦和冷笑話穿插、八卦必須有來源；不給投資建議；不用別人影片的原片；不誇大標題縮圖。
只在 run-dir 內寫檔。不要 git commit、不要上傳任何東西、不要呼叫付費 API。"""

TASKS = {
    "topic": """任務：選題候選。從趨勢、Hacker News、新聞、頻道待辦清單（{repo}/channels/backlog/{channel}.yaml）整理 8–12 個候選，
排除 topics/channel_history.txt 裡已做過的題目。寫 topics/candidates.json：
{{"candidates":[{{"id":"t01","title":"標題草案","hook":"一句鉤子","minutes":8,"sources":["可查的來源網址"],"note":"為何適合這頻道"}}]}}
每題至少 2 個可公開查證的來源網址（用 WebSearch／WebFetch 確認存在）。""",
    "article": """任務：研究與文章。題目在 topic.json 的 chosen[0]。照 {repo}/.claude/skills/article/SKILL.md 的做法（不要停下來等人審），
寫 article.md 與 sources.json。每個數字和八卦都附來源 id，來源要是你實際打開過的網址。
交出前逐條自我查核（兩位事實查核員會各自回頭查每個來源，任何一條錯誤或無來源就整篇退回）：
- 每個 [src:] 標記後面的那句話，來源原文要真的這樣說；你的推論、比喻、換算不要掛來源，寫成「換算起來」「也就是說」；
- 保留來源的限定詞：「據報導」「預定」「據稱」「估計」「規劃」「最先端用」等不能拿掉，範圍（台灣唯一≠全球唯一）不能放大；
- 報導刊登日≠事件發生日；說話的人要寫對（不同時期的社長是不同人），轉述媒體要寫轉述自誰（例如「日經報導、9to5Mac 轉述」）；
- 打不開或抽不出文字的來源（PDF、付費牆）不要當唯一依據；查不到就刪掉那句。
- 論點核心的因果（「因為 A 所以 B」）若來源沒有直接說，就寫成頻道自己的判斷（「我們的判斷是」「看起來」），不要寫成事實；
  引述要歸屬給來源裡真的說話的人（報導本身的敘述不是「業界主管說」）。
- 寫完跑 `{python} {repo}/scripts/check_article.py --run-dir {run_dir}`，有問題改到 0 problem(s)。""",
    "deck": """任務：腳本。依 article.md，照 {repo}/.claude/skills/deck-outline/SKILL.md 與 {repo}/.claude/skills/deck/SKILL.md 的規則
（不要停下來等人審），直接寫 deck.json（可先寫 deck_outline.json），並寫 promise.txt：一句「這支片答應觀眾什麼」。
若有 review/article.story_notes.json（編劇對文章故事線的建議），在講稿裡處理，但不能新增文章沒有的事實。
寫完跑 `{python} {repo}/scripts/deck_to_script.py --run-dir {run_dir} --strict`，有錯就改到通過。
開場 15 秒內要有鉤子；每 5–10 秒要有留人的點；內容要撐得起片長，不要灌水。""",
    "thumbnail_spec": """任務：標題與縮圖。依 deck.json 與 promise.txt：
1. 寫 titles.json：{{"titles":[{{"id":"T1","text":"…"}}, …]}}，5–6 個標題（中文開頭、不誇大、承諾在講稿裡有兌現）。
2. 寫 thumbnail.json（主縮圖）與 thumbnail_variants.json（3 款：A 角色大表情、B 主視覺問句、C 數字對比），格式見
   {repo}/src/content_farm/production/thumbnail.py（ThumbnailSpec／ThumbnailVariants）；promise 必須是講稿前 60 秒內的原句。
3. 跑 `{python} {repo}/scripts/make_thumbnail.py --run-dir {run_dir} --channel {channel} --variants` 確認能渲染。""",
}


def _fixes_text(run_dir: Path, gate: str) -> str:
    path = run_dir / "review" / f"{gate}.fixes.json"
    if not path.is_file():
        return ""
    plan = json.loads(path.read_text(encoding="utf-8"))
    lines, deferred = [], []
    for step, slot in plan.get("steps", {}).items():
        for fix in slot["fixes"]:
            if gate == "article" and not _is_fact(fix):
                deferred.append(fix)      # story notes: the script stage tells the story, the article stays facts
                continue
            scope = fix["scope"]
            lines.append(f"- [{step}] {fix.get('problem')} → {fix.get('fix')}（指認：{json.dumps(fix.get('ref'), ensure_ascii=False)}；"
                         f"連動要一起改：句子 {', '.join(scope['sentence_ids']) or '—'}；標題 {', '.join(scope['titles']) or '—'}；"
                         f"縮圖 {'是' if scope['thumbnail'] else '否'}；說明欄 {'是' if scope['description'] else '否'}）")
    reasons = "；".join(plan.get("reasons", []))
    if deferred:
        (run_dir / "review" / "article.story_notes.json").write_text(
            json.dumps(deferred, ensure_ascii=False, indent=1), encoding="utf-8")
    return (f"\n這是退回重做（第 {plan.get('round')} 輪評審未過：{reasons}）。修改清單（{path}）：\n" + "\n".join(lines)
            + "\n只改清單與連動範圍列出的地方，其他句子一字不動（沒改到的句子 id 要保持不變）；"
              "改寫時不要新增沒查證過的說法——新寫的每一句一樣會被查核；"
              "不准為了分數灌水或誇大。fixed 欄位列出你處理了哪些。")


def _is_fact(fix: dict) -> bool:
    """Article reworks carry only fact items (2026-10-18: in attempts 2 and 3 the rewrite for the
    story editor's notes added the new unsourced claims that failed the last round)."""
    return fix.get("category") == "fact" or str(fix.get("who", "")).startswith("fact_checker")


def producer_tier(config: ReviewConfig, step: str) -> Tier:
    stage, _ = STEP_STAGE[step]
    tier = config.stages[stage].producer
    return tier or Tier(model="sonnet", effort="medium")


def produce(step: str, run_dir: Path, *, channel: str, config: ReviewConfig, python: str,
            client: Callable[[Call], CallResult] | None = None) -> CallResult:
    if step not in TASKS:
        raise ValueError(f"no producer agent for step {step!r}")
    _, gate = STEP_STAGE[step]
    fmt = {"run_dir": run_dir, "repo": REPO, "channel": channel, "python": python}
    prompt = "\n\n".join((COMMON.format(**fmt), TASKS[step].format(**fmt), _fixes_text(run_dir, gate),
                          "完成後用結構化輸出回報寫了哪些檔。"))
    tier = producer_tier(config, step)
    log_dir = run_dir / "review" / "producers"
    log_dir.mkdir(parents=True, exist_ok=True)
    rid = f"{step}-{len(list(log_dir.glob(f'{step}-*.prompt.md'))) + 1}"
    (log_dir / f"{rid}.prompt.md").write_text(prompt, encoding="utf-8")
    # Claude Code matches Bash prefixes word by word, so each allowed script is named (a "scripts/" prefix never matched).
    tools = (*TOOLS, *(f"Bash({python} {REPO}/scripts/{name}:*)" for name in SCRIPTS))
    # Read access: the repo's rules and code, never output/ (2026-10-18: an attempt-2 agent read attempt 1's
    # reviewer results through a repo-wide --add-dir).
    dirs = tuple(REPO / d for d in (".claude/skills", "channels", "src", "scripts", "assets"))
    call = Call(rid, prompt, RECEIPT, tier.model, tier.effort, tools=tools, cwd=run_dir, add_dirs=dirs,
                env=(("PYTHONPATH", str(REPO / "src")),),
                timeout_s=TIMEOUT_S[step], retries=1, write_tools=True)   # one retry: network drops (2026-10-18)
    result = (client or (lambda c: run_call(c, log_dir=log_dir)))(call)
    with (log_dir / "producers.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"step": step, **result.to_json(), "receipt": result.output}, ensure_ascii=False) + "\n")
    return result
