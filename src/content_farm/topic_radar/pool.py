"""Cross-channel topic pool: every channel's candidates plus fresh Chinese-web signals, each tagged with the
channel (or possible new channel direction) it suits. Written next to the per-channel files as POOL.json / POOL.md."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from content_farm.topic_radar import build, store
from content_farm.topic_radar.config import RadarConfig
from content_farm.topic_radar.fit import FitRule, PoolConfig, assign_fits
from content_farm.topic_radar.http import RadarHttp
from content_farm.topic_radar.models import Candidate, ChannelRadar, Fit, Pool, PoolEntry, SourceStatus
from content_farm.topic_radar.summary import CHANNEL_NAMES, FORMAT_NAMES

POOL_CONFIG = RadarConfig(channel="pool", topics=())     # the pool has no seed topics; Shorts allowed, no bonus


def _key(candidate: Candidate) -> tuple[str, str]:
    """Same story from two channels' watch lists = one pool entry (trending: same URL; evergreen: same subject)."""
    if candidate.kind == "trending" and candidate.evidence:
        return "url", candidate.evidence[0].url
    return "subject", candidate.subject


def _entry(candidate: Candidate, origin: str, rules: tuple[FitRule, ...]) -> PoolEntry:
    text = f"{candidate.subject} {candidate.title_draft} {candidate.excerpt}"
    return PoolEntry(id="", origin=origin, kind=candidate.kind, subject=candidate.subject,
                     title_draft=candidate.title_draft, format=candidate.format, score=candidate.score,
                     fits=assign_fits(text, rules, origin), evidence=candidate.evidence, excerpt=candidate.excerpt,
                     warnings=candidate.warnings)


def _merge_fits(entries: list[PoolEntry]) -> tuple[Fit, ...]:
    merged: dict[str, Fit] = {}
    for entry in entries:
        for fit in entry.fits:
            merged.setdefault(fit.target, fit)
    return tuple(sorted(merged.values(), key=lambda fit: fit.kind == "new"))


def _dedupe(entries: list[tuple[tuple[str, str], PoolEntry]]) -> list[PoolEntry]:
    groups: dict[tuple[str, str], list[PoolEntry]] = {}
    for key, entry in entries:
        groups.setdefault(key, []).append(entry)
    return [max(group, key=lambda item: item.score).model_copy(update={"fits": _merge_fits(group)})
            for group in groups.values()]


def build_pool(radars: list[ChannelRadar], cn_candidates: list[Candidate], config: PoolConfig, now: datetime,
               sources: tuple[SourceStatus, ...]) -> Pool:
    rows = [(_key(c), _entry(c, radar.channel, config.rules)) for radar in radars for c in radar.candidates]
    rows += [(_key(c), _entry(c, "cn-signal", config.rules)) for c in cn_candidates]
    ranked = sorted(_dedupe(rows), key=lambda item: -item.score)
    day = now.date()
    numbered = tuple(item.model_copy(update={"id": f"pool-{day:%Y%m%d}-{n:02d}"}) for n, item in enumerate(ranked, 1))
    return Pool(date=day.isoformat(), generated_at=now.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
                entries=numbered, sources=sources)


def collect(radars: list[ChannelRadar], http: RadarHttp, config: PoolConfig, now: datetime) -> Pool:
    """Fetch the pool's own Chinese-web signals once, then assemble the pool. A dead source only shows up in ``sources``."""
    notes = build.Notes()
    before = {"net": dict(http.network), "hit": dict(http.cached)}
    signals = build.fetch_trending_signals(config.watch, http, notes, now)
    cn = build.signal_candidates(POOL_CONFIG, signals, now, config.pool_size)
    return build_pool(radars, cn, config, now, build.status_rows(http, before, notes))


# ── output ──────────────────────────────────────────────────────────────────────

def write_pool(root: Path, pool: Pool, markdown: str) -> tuple[Path, Path]:
    folder = store.day_dir(root, pool.date)
    folder.mkdir(parents=True, exist_ok=True)
    json_path, md_path = folder / "POOL.json", folder / "POOL.md"
    json_path.write_text(json.dumps(pool.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def _group_title(rule: FitRule) -> str:
    return rule.label if rule.kind == "new" else f"{CHANNEL_NAMES.get(rule.target, rule.target)}｜{rule.label}"


def _entry_block(rank: int, entry: PoolEntry, fit: Fit) -> list[str]:
    hits = f"，命中 {fit.hits} 個關鍵字" if fit.hits else ""
    lines = [f"**{rank}. {entry.title_draft}**　{FORMAT_NAMES[entry.format]}　提示分 {entry.score}　來源頻道：{entry.origin}",
             f"- 為何適合：{fit.reason}{hits}"]
    for ev in entry.evidence[:2]:
        when = f"；抓取 {ev.fetched_at}" if ev.fetched_at else ""
        note = f"（{ev.note}{when}）" if ev.note or when else ""
        lines.append(f"- {ev.metric}：**{ev.value:,.0f}**{note} — [來源]({ev.url})")
    if entry.excerpt:
        lines.append(f"- 摘要：{entry.excerpt}")
    lines.extend(f"- 注意：{warning}" for warning in entry.warnings)
    return lines


def render_pool(pool: Pool, config: PoolConfig) -> str:
    lines = [f"# 跨頻道選題池　{pool.date}", "",
             "每則候選標出適合的頻道與新頻道方向（規則在 `channels/radar/pool.yaml`，只是提示）。"
             "中文網路（V2EX、B 站）熱度只當信號，不是題目；來源連結與抓取時間可回看。"
             "分數不同來源之間只能粗略比較。", ""]
    seen: set[str] = set()
    for rule in config.rules:
        if rule.target in seen:
            continue
        seen.add(rule.target)
        lines += [f"## {_group_title(rule)}", ""]
        rows = [(entry, fit) for entry in pool.entries for fit in entry.fits if fit.target == rule.target]
        if not rows:
            lines += ["今天沒有候選。", ""]
        for rank, (entry, fit) in enumerate(rows[: config.per_target], 1):
            lines += [*_entry_block(rank, entry, fit), ""]
    bad = [s for s in pool.sources if not s.ok]
    lines += ["## 來源狀態", ""]
    lines += [f"- {s.source}：{'正常' if s.ok else '異常'}（請求 {s.requests}、快取 {s.cache_hits}）{s.note[:140]}" for s in pool.sources
              if s.requests or s.cache_hits or not s.ok]
    if not bad:
        lines += ["- 全部正常。"]
    return "\n".join(lines).rstrip() + "\n"
