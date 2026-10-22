"""Blocks the deck producer's brief carries from the first call (cf-pipeline-speed, item 1).

Before: the rubric the panel scores by, the channel's hard rules and the one thing Bash may do were absent, so a
draft was refused only after it was written (九尾狐 deck-12: a 73-char take against the 80-char rule threw away
673 s / 75.9k tokens) and 87 Bash calls were denied. Now each is a short fixed block.
"""

from __future__ import annotations

from content_farm.review.config import ReviewConfig

DECK_STAGE = "script_structure"


def rubric_text(config: ReviewConfig, stage: str = DECK_STAGE) -> str:
    """What the panel that will judge this deck scores, and the bars it must clear."""
    spec = config.stages.get(stage)
    if spec is None:
        return ""
    lines, seen = [], set()
    for seat in spec.seats:
        role = config.roles.get(seat.role)
        if role is None or role.kind != "pro" or seat.role in seen:
            continue
        seen.add(seat.role)
        lines.append(f"- {role.title}：{'、'.join(role.rubric)}（{role.brief.strip()[:60]}…）" if role.brief
                     else f"- {role.title}：{'、'.join(role.rubric)}")
    bars = []
    if spec.threshold.writer_min is not None:
        bars.append(f"每位編劇 ≥ {spec.threshold.writer_min}/10")
    if spec.threshold.leave_median_pct is not None:
        bars.append(f"合成觀眾離開時間中位數 ≥ 片長 {spec.threshold.leave_median_pct:.0%}")
    if not lines and not bars:
        return ""
    return ("評審會用這份 rubric 打分（寫的時候就照它寫，不要等被退回）：\n" + "\n".join(lines)
            + (f"\n過關門檻：{'；'.join(bars)}。" if bars else ""))


def channel_rules_text(channel_code: str) -> str:
    """The checks the policy step runs on deck.json, stated before writing (``production.channel_rules``)."""
    from content_farm.production import channel_rules as rules
    from content_farm.production.channels import load_channel, other_identities

    try:
        channel = load_channel(channel_code)
    except (OSError, ValueError, KeyError):
        return ""
    lines = []
    identity = channel.identity
    if identity is not None:
        lines.append(f"- 開場：前 {rules.OPENING_SLIDES} 張投影片的旁白要說出「{identity.opening.signature}」"
                     f"（開場格式：{identity.opening.format}）。")
        lines.append(f"- 結尾：最後一張投影片的旁白要說出「{identity.outro.signature}」。")
        foreign = [sig for other in other_identities(channel)
                   for sig in (other.opening.signature, other.outro.signature)]
        if foreign:
            lines.append(f"- 不能出現別的頻道的口頭禪：{'、'.join(f'「{s}」' for s in dict.fromkeys(foreign))}；"
                         "也不要用「用二十四張圖」這類片廠範本句。")
    lines.append(f"- 至少 1 張投影片標 `take: true`，旁白加起來要 ≥ {rules.MIN_TAKE_CHARS} 字（是論證的一段，不是口號；"
                 f"差 1 字也會整份被拒收）。")
    mascot = getattr(channel, "mascot", None)
    if mascot is not None and getattr(mascot, "rig_ready", False):
        lines.append(f"- 角色「{mascot.name}」要出現在 ≥ {rules.MIN_MASCOT_SHARE:.0%} 的投影片（每張的 mascot 欄位）。")
    return "頻道規則（違反任何一條，整份產出會被拒收、還原、重做）：\n" + "\n".join(lines)


def bash_text(python: str, repo: str) -> str:
    """The only shell commands the agent may run, spelled exactly (Claude Code matches the prefix word by word)."""
    return (
        "可用的 Bash 指令只有下面這幾支，要完全照這個寫法（絕對路徑，前面不能加 cd、env -C、-I，後面不能用 && ; | 串接，"
        "也不能 python -c、heredoc 或自己寫的腳本）：\n"
        f"- `{python} {repo}/scripts/deck_to_script.py --run-dir <run-dir> --strict`：驗證並產生 script.json。\n"
        f"- `{python} {repo}/scripts/apply_deck_patch.py --run-dir <run-dir> --patch <patch.json>`：改很多句時，先用 Write 寫一個 "
        "patch.json（`{\"句子id\": \"新文字\", \"deletes\": [\"要刪的句子id\"]}`），由這支程式套用到 deck.json 並自動跑上一支驗證。\n"
        "讀檔用 Read／Grep／Glob，改檔用 Edit（單句）或 apply_deck_patch（多句），不要用 shell 讀寫。")


def deck_brief(config: ReviewConfig, channel_code: str, python: str, repo: str) -> str:
    return "\n\n".join(p for p in (rubric_text(config), channel_rules_text(channel_code), bash_text(python, repo)) if p)
