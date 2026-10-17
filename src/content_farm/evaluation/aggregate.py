"""Turn a round's result files into scores: three columns (視覺／聽覺／內容) plus audience and
homepage numbers, each check with a traffic light, and the common fix list.

Holdout viewers are scored separately and never feed the fix list (anti-overfitting).
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path

from content_farm.evaluation.homepage import CONTRAST_MIN, HUE_DISTANCE_MIN, SMALL_GLYPH_MIN, SUBJECT_MIN
from content_farm.evaluation.panel import Thresholds

FIX_WINDOW = 20.0      # s: fixes this close in time, same category, are one issue


@dataclass(frozen=True)
class Check:
    column: str          # visual | audio | content
    name: str
    value: object
    target: str
    ok: bool
    critical: bool = True


def seconds(text: str | None) -> float | None:
    if not text or text in ("null", "None"):
        return None
    match = re.match(r"^\s*(\d+):(\d{1,2})", str(text))
    return int(match.group(1)) * 60 + int(match.group(2)) if match else None


def load_results(round_dir: Path) -> tuple[list[dict], list[dict]]:
    manifest = json.loads((round_dir / "round.json").read_text(encoding="utf-8"))
    viewers, pros = [], []
    for entry in manifest["reviewers"]:
        path = Path(entry["result"])
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_rid"], data["_holdout"] = entry["rid"], entry["holdout"]
        (viewers if entry["kind"] == "viewer" else pros).append(data)
    return viewers, pros


def _click(view: dict, variant: str) -> float | None:
    click = view.get("click") or {}
    if "score" in click:                         # 2026-10-17 trial format: one score
        return float(click["score"])
    value = click.get(variant)
    return float(value) if isinstance(value, (int, float)) else None


def audience(viewers: list[dict], duration: float, variants: list[str]) -> dict:
    if not viewers:
        return {"count": 0}
    leave = []
    for view in viewers:
        left = seconds(view.get("left_at"))
        leave.append(1.0 if left is None else min(left / duration, 1.0))
    clicks = {v: [c for view in viewers if (c := _click(view, v)) is not None] for v in variants or ["A"]}
    click_means = {v: round(statistics.mean(c), 2) for v, c in clicks.items() if c}
    engagement = [s.get("engagement", 0) for view in viewers for s in view.get("segments", [])]
    windows = max((len(view.get("segments", [])) for view in viewers), default=0)
    curve = []
    for k in range(windows):
        t = k * 10
        curve.append(round(sum(1 for view in viewers
                               if (seconds(view.get("left_at")) or 1e9) > t) / len(viewers), 2))
    heat = {view.get("persona", view["_rid"]): [s.get("engagement") for s in view.get("segments", [])]
            for view in viewers}
    best = max(click_means, key=click_means.get) if click_means else None
    return {"count": len(viewers), "leave_pct": [round(x, 2) for x in leave],
            "leave_median_pct": round(statistics.median(leave), 2),
            "left_at": {view.get("persona", view["_rid"]): view.get("left_at") for view in viewers},
            "click_by_variant": click_means, "best_variant": best,
            "click_best": click_means.get(best) if best else None,
            "engagement_mean": round(statistics.mean(engagement), 2) if engagement else None,
            "finish_share": round(sum(bool(v.get("finish")) for v in viewers) / len(viewers), 2),
            "subscribe_share": round(sum(bool(v.get("subscribe")) for v in viewers) / len(viewers), 2),
            "curve": curve, "heat": heat,
            "pronunciation": sorted({w for v in viewers for w in (v.get("pronunciation") or []) if w})}


def homepage_stats(viewers: list[dict], keys: dict) -> dict:
    per_variant: dict[str, dict[str, list]] = {}
    for view in viewers:
        for answer in view.get("homepage") or []:
            feed = Path(str(answer.get("feed", ""))).name
            key = keys.get(feed)
            if key is None:
                continue
            noticed = [int(n) for n in answer.get("noticed") or [] if str(n).isdigit()]
            rank = noticed.index(key["ours_card"]) + 1 if key["ours_card"] in noticed else len(noticed) + 1
            slot = per_variant.setdefault(key["variant"], {"ranks": [], "picked": [], "cards": []})
            slot["ranks"].append(rank)
            slot["picked"].append(int(str(answer.get("picked", -1)).strip() or -1) == key["ours_card"])
            slot["cards"].append(key["cards"])
    out = {}
    for variant, slot in sorted(per_variant.items()):
        n = statistics.mean(slot["cards"])
        out[variant] = {"noticed_median": statistics.median(slot["ranks"]),
                        "pick_rate": round(sum(slot["picked"]) / len(slot["picked"]), 2),
                        "chance": round(1 / n, 3), "answers": len(slot["ranks"])}
    return out


def fix_list(viewers: list[dict], pros: list[dict]) -> list[dict]:
    """Fixes from non-holdout viewers and pros, grouped by category and time."""
    raw = []
    for view in viewers:
        if view["_holdout"]:
            continue
        for fix in view.get("top_fixes") or []:
            raw.append({"t": seconds(fix.get("t")), "category": fix.get("category", "content"),
                        "problem": fix.get("problem", ""), "fix": fix.get("fix", ""), "who": view["_rid"]})
    for pro in pros:
        for issue in pro.get("issues") or []:
            raw.append({"t": seconds(issue.get("t")), "category": issue.get("category", "content"),
                        "problem": issue.get("problem", ""), "fix": issue.get("fix", ""), "who": pro["_rid"],
                        "severity": issue.get("severity", "med")})
    groups: list[dict] = []
    for item in sorted(raw, key=lambda r: (r["category"], r["t"] if r["t"] is not None else -1)):
        home = next((g for g in groups if g["category"] == item["category"] and item["t"] is not None
                     and g["t"] is not None and abs(g["t"] - item["t"]) <= FIX_WINDOW), None)
        if home is None:
            groups.append({**item, "who": [item["who"]], "items": [item]})
        else:
            home["who"].append(item["who"])
            home["items"].append(item)
    groups.sort(key=lambda g: (-len(set(g["who"])), g["t"] if g["t"] is not None else 0))
    return [{"t": g["t"], "category": g["category"], "votes": len(set(g["who"])), "who": sorted(set(g["who"])),
             "problem": g["problem"], "fix": g["fix"], "also": [i["problem"] for i in g["items"][1:4]]}
            for g in groups]


def objective_checks(obj: dict, thumbs: dict | None = None) -> list[Check]:
    c, v, a = obj["content"], obj["visual"], obj["audio"]
    checks = [
        Check("content", "死區（10 秒內無畫面變化、音效、鉤子）", len(obj["dead_zones"]), "0", not obj["dead_zones"]),
        Check("content", "首個鉤子（秒）", c.get("first_hook"), "≤15", c.get("first_hook") is not None and c["first_hook"] <= 15),
        Check("content", "鉤子最大間隔（秒）", c["max_gap"], "≤10", c["max_gap"] <= 10),
        Check("content", "re-hook 缺口（>90 秒無問題／預告）", len(c["rehook_gaps"]), "0", not c["rehook_gaps"], False),
        Check("content", "章節結尾沒預告", len(c["chapter_teases"]), "0", not c["chapter_teases"], False),
        Check("visual", "最長靜止（秒）", v["longest_still"], "≤8", v["longest_still"] <= v["still_max"]),
        Check("visual", "空白畫面段", len(v["blanks"]), "0", not v["blanks"]),
        Check("visual", "轉場殘影段", len(v["held_blends"]), "0", not v["held_blends"]),
        Check("visual", "字幕字高（% 畫面高）", v["subtitle"]["height_pct"], "5–6", 5.0 <= v["subtitle"]["height_pct"] <= 6.0),
        Check("visual", "字幕底條", v["subtitle"]["box"], "有", bool(v["subtitle"]["box"]), False),
        Check("visual", "字幕閃現（<0.4 秒或 >9 字/秒）", len((v.get("subtitle_timing") or {}).get("collapsed", [])), "0",
              not (v.get("subtitle_timing") or {}).get("collapsed")),
        Check("visual", "畫面數字與旁白不同步", len(v["sync"]), "≤3", len(v["sync"]) <= 3, False),
        Check("visual", "文字過密頁（>60 字）", len(v["density"]["dense_pages"]), "≤2", len(v["density"]["dense_pages"]) <= 2, False),
        Check("visual", "每分鐘換場", v["cuts_per_minute"], "≥6", v["cuts_per_minute"] >= 6, False),
    ]
    if a.get("integrated") is not None:
        rates = [w["rate"] for w in a.get("windows", []) if w.get("rate")]
        rate = round(statistics.median(rates), 1) if rates else None
        unders = [w["bgm_under_voice_db"] for w in a["windows"] if w.get("bgm_under_voice_db") is not None]
        under = round(statistics.median(unders), 1) if unders else None
        checks += [
            Check("audio", "整體響度（LUFS）", a["integrated"], "-14 ±1", abs(a["integrated"] + 14) <= 1),
            Check("audio", "真峰值（dBTP）", a["true_peak"], "≤ -1.5（容許 +0.5）", a["true_peak"] <= -1.0),
            Check("audio", "削波取樣數", a["clipped_samples"], "0", a["clipped_samples"] == 0),
            Check("audio", "語速中位（字/秒，說話時）", rate, "3.8–5.8", rate is not None and 3.8 <= rate <= 5.8),
            Check("audio", "音高起伏（半音）", a["pitch_spread_st"], "≥1.6（不單調）", a["pitch_spread_st"] >= 1.6, False),
            Check("audio", "BGM 低於人聲（dB，中位）", under, "12–18", under is not None and 12 <= under <= 18),
            Check("audio", "ducking（dB）", a.get("ducking_db"), "≥3", (a.get("ducking_db") or 0) >= 3, False),
            Check("audio", "死空氣（≥2 秒無聲）", len(a.get("dead_air", [])), "0", not a.get("dead_air")),
            Check("audio", "念錯（CER 平均）", (a.get("speech_check") or {}).get("mean_cer"), "≤0.08",
                  ((a.get("speech_check") or {}).get("mean_cer") or 0) <= 0.08, False),
        ]
    for key, m in (thumbs or {}).items():
        checks += [
            Check("visual", f"縮圖 {key}：168px 主標字高（px）", m["glyph_px_at_168"], f"≥{SMALL_GLYPH_MIN:.0f}",
                  (m["glyph_px_at_168"] or 0) >= SMALL_GLYPH_MIN, False),
            Check("visual", f"縮圖 {key}：文字對比", m["contrast"], f"≥{CONTRAST_MIN}", (m["contrast"] or 0) >= CONTRAST_MIN, False),
            Check("visual", f"縮圖 {key}：主體佔比", m["subject_share"], f"≥{SUBJECT_MIN}", m["subject_share"] >= SUBJECT_MIN, False),
            Check("visual", f"縮圖 {key}：與競品色相差（°）", m["hue_distance"], f"≥{HUE_DISTANCE_MIN:.0f}",
                  (m["hue_distance"] or 0) >= HUE_DISTANCE_MIN, False),
        ]
    return checks


def column_scores(checks: list[Check]) -> dict:
    out = {}
    for column in ("visual", "audio", "content"):
        mine = [c for c in checks if c.column == column]
        if not mine:
            out[column] = {"score": None, "light": "gray"}
            continue
        passed = sum(c.ok for c in mine)
        light = "red" if any(c.critical and not c.ok for c in mine) else "yellow" if passed < len(mine) else "green"
        out[column] = {"score": round(10 * passed / len(mine), 1), "light": light, "passed": passed, "total": len(mine)}
    return out


def verdict(aud: dict, home: dict, columns: dict, thresholds: Thresholds) -> dict:
    reasons = []
    if aud.get("count"):
        if aud["leave_median_pct"] < thresholds.leave_median_pct:
            reasons.append(f"離開中位 {aud['leave_median_pct']:.0%} < {thresholds.leave_median_pct:.0%}")
        if (aud.get("click_best") or 0) < thresholds.click_mean:
            reasons.append(f"點擊意願 {aud.get('click_best')} < {thresholds.click_mean}")
    for column, data in columns.items():
        if thresholds.objective_all_green and data["light"] == "red":
            reasons.append(f"{column} 欄有關鍵指標未過")
    if home:
        best = min(home.values(), key=lambda h: (h["noticed_median"], -h["pick_rate"]))
        if best["noticed_median"] > thresholds.homepage_noticed_median:
            reasons.append(f"首頁被注意名次中位 {best['noticed_median']} > {thresholds.homepage_noticed_median}")
        if best["pick_rate"] < thresholds.homepage_pick_factor * best["chance"]:
            reasons.append(f"首頁被選比例 {best['pick_rate']:.0%} < {thresholds.homepage_pick_factor:.0f}×{best['chance']:.0%}")
    return {"pass": not reasons, "reasons": reasons}
