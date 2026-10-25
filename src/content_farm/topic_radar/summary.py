"""One-page Markdown digest: each channel's top candidates with their evidence."""

from __future__ import annotations

from content_farm.topic_radar.models import Candidate, ChannelRadar

CHANNEL_NAMES = {"chipcat": "晶片貓", "cel": "賽璐璐研究室", "yokai": "妖怪溯源所", "technews": "科技新知",
                 "deepsea": "深潛日誌", "fable": "寓言學堂"}
FORMAT_NAMES = {"shorts": "Shorts", "long": "長片"}


def _number(value: float) -> str:
    return f"{value:,.0f}" if value >= 100 else f"{value:g}"


def _candidate_block(rank: int, item: Candidate) -> list[str]:
    lines = [f"**{rank}. {item.title_draft}**　建議：{FORMAT_NAMES[item.format]}　提示分 {item.score}",
             f"- 為何這個格式：{item.format_reason}"]
    for ev in item.evidence[:4]:
        note = f"（{ev.note}）" if ev.note else ""
        lines.append(f"- {ev.metric}：**{_number(ev.value)}**{note} — [來源]({ev.url})")
    if item.competitors:
        top = item.competitors[0]
        views = "、".join(f"{c.views:,}" for c in item.competitors)
        lines.append(f"- 競爭影片前 {len(item.competitors)} 名觀看數：{views}；最高 [{top.title}]({top.url})（{top.channel}，{top.published}）")
    for question in item.viewer_questions[:2]:
        lines.append(f"- 觀眾在問（{question.likes} 讚）：「{question.text}」 — [留言所在影片]({question.url})")
    lines.extend(f"- 注意：{warning}" for warning in item.warnings)
    return lines


def render_summary(radars: list[ChannelRadar], date: str, youtube_note: str, top: int = 3) -> str:
    lines = [f"# 選題雷達　{date}", "",
             f"YouTube 認證：{youtube_note}。分數是排序提示，不是門檻；數字與來源都可點開核對。"
             f"YouTube 衍生資料保留至 {radars[0].youtube_data_expires[:10] if radars else '—'}（API 條款 30 天）。", ""]
    for radar in radars:
        lines += [f"## {CHANNEL_NAMES.get(radar.channel, radar.channel)}（{radar.channel}）", ""]
        if not radar.candidates:
            lines += ["今天沒有取得候選（見來源狀態）。", ""]
        for rank, item in enumerate(radar.candidates[:top], 1):
            lines += [*_candidate_block(rank, item), ""]
        bad = [s for s in radar.sources if not s.ok]
        if bad:
            lines += ["來源異常：" + "；".join(f"{s.source}（{s.note[:90]}）" for s in bad), ""]
    return "\n".join(lines).rstrip() + "\n"
