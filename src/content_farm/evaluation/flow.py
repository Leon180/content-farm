"""eval-loop state machine shared by ``scripts/eval_prelaunch.py`` and ``produce.py eval-loop``.

One call advances the loop by one step and says what has to happen next:
- no round yet, or the last round failed *and the video changed since* → prepare the next round;
- a round is waiting for reviewer results → WAIT (the session dispatches the briefs as sub-agents);
- a round has all results → score it, log it, redraw the scorecard; PASS / STOP (max rounds) /
  FIX (apply the common fix list, re-render, call again);
- a round passed before the holdout viewer saw it → prepare a holdout-only addendum (reported,
  never fed into fixes).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from content_farm.evaluation import loop
from content_farm.evaluation.homepage import load_competitors, mean_hue, measure_page, thumb_metrics
from content_farm.evaluation.panel import Panels, load_panels
from content_farm.evaluation.prepare import EVAL_DIR, prepare_round
from content_farm.production.channels import Channel
from content_farm.retention.report import upload_video

DEFAULT_COMPETITORS = Path("output") / "eval-competitors"


@dataclass(frozen=True)
class Step:
    status: str          # waiting | fix | pass | stop | prepared
    message: str
    round: int | None = None

    @property
    def exit_code(self) -> int:
        return {"pass": 0, "stop": 4}.get(self.status, 3)


def video_fingerprint(run_dir: Path) -> str:
    video = upload_video(run_dir)
    if video is None:
        return ""
    stat = video.stat()
    return hashlib.sha256(f"{video.name}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()[:16]


def stage_for(channel: Channel, round_no: int, max_rounds: int) -> str:
    if channel.format.length == "short":
        return "shorts"
    return "final" if round_no >= max_rounds else "rough_cut"


def _rounds(run_dir: Path) -> list[Path]:
    found = [p for p in (run_dir / EVAL_DIR).glob("round-*") if (p / "round.json").is_file()]
    return sorted(found, key=lambda p: (int(p.name.split("-")[1]), p.name))


def thumbs_for(run_dir: Path, competitors_dir: Path | None) -> dict:
    hues = []
    if competitors_dir and (competitors_dir / "competitors.json").is_file():
        from PIL import Image

        for card in load_competitors(competitors_dir):
            with Image.open(card.image) as img:
                hues.append(mean_hue(img)[0])
    out = {}
    work = run_dir / "thumbnails" / ".work"
    for image in sorted((run_dir / "thumbnails").glob("variant_*.jpg")):
        key = image.stem.split("_")[-1].upper()
        # render_variants writes variant_<key as in the spec>.html (usually upper case); a case-sensitive
        # filesystem would miss it under the lower-case name and score subject share 0
        html = next((p for p in (work / f"variant_{key}.html", work / f"variant_{key.lower()}.html") if p.is_file()),
                    None)
        page = measure_page(html) if html else {}
        out[key] = thumb_metrics(image, page, hues)
    return out


def advance(run_dir: Path, channel: Channel, *, max_rounds: int | None = None, panels: Panels | None = None,
            competitors_dir: Path | None = None, changes: list[str] | None = None,
            minutes: float | None = None) -> Step:
    panels = panels or load_panels()
    max_rounds = max_rounds or panels.thresholds.max_rounds
    competitors = competitors_dir or (run_dir.parent / "eval-competitors" / run_dir.name.split("-")[0])
    competitors = competitors if (competitors / "competitors.json").is_file() else None
    rounds = _rounds(run_dir)
    if rounds:
        last = rounds[-1]
        manifest = json.loads((last / "round.json").read_text(encoding="utf-8"))
        missing = [e for e in manifest["reviewers"] if not Path(e["result"]).is_file()]
        if missing:
            briefs = "\n".join(f"  {e['rid']}: {e['brief']}" for e in missing)
            return Step("waiting", f"{last.name}: {len(missing)} reviewer(s) pending — dispatch each brief as a "
                                   f"sub-agent (Agent tool), in parallel:\n{briefs}", manifest["round"])
        if not (last / "score.json").is_file():
            score = loop.score_round(run_dir, last.name if "holdout" in last.name else manifest["round"],
                                     panels.thresholds, label=last.name, thumbs=thumbs_for(run_dir, competitors))
            loop.append_log(run_dir, loop.log_entry(score, minutes=minutes, changes=changes or []))
            loop.redraw(run_dir, channel.name, ["baseline", *[p.name for p in rounds]])
            if "holdout" in last.name:
                return Step("pass", f"holdout addendum scored: leave median "
                                    f"{(score.get('holdout') or {}).get('leave_median_pct')}", manifest["round"])
        score = json.loads((last / "score.json").read_text(encoding="utf-8"))
        number = manifest["round"]
        if score["verdict"]["pass"] or "holdout" in last.name:
            if not manifest.get("final_round") and not any("holdout" in p.name for p in rounds):
                prepare_round(run_dir, round_no=number, panels=panels, stage=stage_for(channel, number, max_rounds),
                              channel_code=channel.code, channel_name=channel.name, final_round=True,
                              competitors_dir=None, holdout_only=True, dir_name=f"round-{number}-holdout")
                return Step("waiting", f"round {number} passed; holdout addendum prepared: "
                                       f"{run_dir / EVAL_DIR / f'round-{number}-holdout' / 'briefs'}", number)
            return Step("pass", f"round {number} passes every threshold", number)
        if number >= max_rounds:
            return Step("stop", f"round {number} = max rounds and still short: {'；'.join(score['verdict']['reasons'])}",
                        number)
        if manifest.get("video_fingerprint") == video_fingerprint(run_dir):
            return Step("fix", f"round {number} failed ({'；'.join(score['verdict']['reasons'])}). Apply the fix "
                               f"list in {last / 'score.json'} (verifiable items only), re-render, then run again.",
                        number)
    number = loop.next_round(run_dir) if rounds else 1
    manifest = prepare_round(run_dir, round_no=number, panels=panels, stage=stage_for(channel, number, max_rounds),
                             channel_code=channel.code, channel_name=channel.name,
                             final_round=number >= max_rounds, competitors_dir=competitors)
    manifest["video_fingerprint"] = video_fingerprint(run_dir)
    (run_dir / EVAL_DIR / f"round-{number}" / "round.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return Step("prepared", f"round {number} prepared ({len(manifest['reviewers'])} reviewers); dispatch briefs in "
                            f"{run_dir / EVAL_DIR / f'round-{number}' / 'briefs'}", number)
