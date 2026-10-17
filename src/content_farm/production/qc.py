"""Automatic quality checks on a finished run (``qc/qc_report.json``).

Each check returns a :class:`Finding` with a level:
``error`` blocks the final approval unless the reviewer overrides it with a
written reason; ``warn`` is shown on the review page; ``ok`` is evidence that
the check ran. A check that could not run reports ``error`` with the reason —
silence is never success.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from content_farm.explainer.deck import Deck, MediaKind, Motion
from content_farm.production.channels import Channel

QC_REPORT = Path("qc") / "qc_report.json"
BLACK_MIN_SECONDS = 0.5
AV_DRIFT_SECONDS = 2.0
ASPECT_SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
_NON_COMMERCIAL = re.compile(r"\bNC\b|non-?commercial", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    check: str
    level: str      # ok | warn | error
    message: str


def final_video(run_dir: Path) -> Path | None:
    """The mascot-composited final if it exists, else the assembly draft."""
    for name in ("final.mp4", "draft.mp4"):
        path = run_dir / "assembly" / name
        if path.is_file():
            return path
    return None


def policy_findings(channel: Channel, deck: Deck) -> list[Finding]:
    """Does the deck ask for media the channel is not allowed to use?"""
    allowed = {MediaKind.SLIDE, MediaKind.ANIMATED, MediaKind.TITLE_CARD}
    if channel.media.stock:
        allowed.add(MediaKind.STOCK)
    if channel.media.ai_image:
        allowed.add(MediaKind.AI_IMAGE)
    if channel.media.artwork:
        allowed.add(MediaKind.ARTWORK)
    bad = [f"{slide.id}:{slide.media_kind.value}" for slide in deck.slides
           if slide.media_kind not in allowed]
    if bad:
        return [Finding("media_policy", "error",
                        f"channel {channel.code} does not allow: {', '.join(bad)}")]
    from content_farm.explainer.illustrate import forbidden_prompt_terms

    styled = [f"{slide.id}:{','.join(terms)}" for slide in deck.slides
              if slide.media_kind == MediaKind.AI_IMAGE and slide.media is not None
              and (terms := forbidden_prompt_terms(f"{slide.media.prompt} {slide.media.motion_prompt}"))]
    if styled:
        return [Finding("ai_style", "error", f"ai_image prompts ask for photo-realism or an artist's "
                                             f"style (rule: 非擬真、不模仿畫家): {'; '.join(styled)}")]
    wan_findings = wan_count_findings(deck)
    if wan_findings:
        return wan_findings
    return [Finding("media_policy", "ok", f"{len(deck.slides)} slides within channel media policy")]


def deck_findings(channel: Channel, deck: Deck) -> list[Finding]:
    """Media policy plus the channel rules (identity, template wording, commentary, mascot)."""
    from content_farm.production.channel_rules import deck_rule_findings
    from content_farm.production.channels import other_identities

    return policy_findings(channel, deck) + deck_rule_findings(channel, deck, other_identities(channel))


def credits_findings(channel: Channel, credits: dict | None) -> list[Finding]:
    if credits is None:
        return [Finding("credits", "error", "credits.json missing (run media first)")]
    findings: list[Finding] = []
    pending = credits.get("pending") or []
    if pending:
        ids = ", ".join(f"{p.get('slide_id')}({p.get('kind')})" for p in pending)
        findings.append(Finding("credits_pending", "error", f"placeholders still in the video: {ids}"))
    incomplete = [e.get("slide_id", "?") for e in credits.get("entries", [])
                  if not e.get("license") or (e.get("kind") == "stock" and not e.get("source_url"))]
    if incomplete:
        findings.append(Finding("credits_fields", "error",
                                f"entries without licence/source: {', '.join(incomplete)}"))
    artwork = [e for e in credits.get("entries", []) if e.get("kind") == "artwork"]
    if channel.media.artwork_license_required:
        for entry in artwork:
            licence = str(entry.get("license", ""))
            if not entry.get("license_url") or _NON_COMMERCIAL.search(licence):
                findings.append(Finding("artwork_license", "error",
                                        f"{entry.get('slide_id')}: licence {licence!r} not usable "
                                        "for a monetised channel (need CC0/PD + licence URL)"))
    findings += ai_image_findings(credits.get("entries", []))
    if not any(f.level == "error" for f in findings):
        findings.append(Finding("credits", "ok",
                                f"{len(credits.get('entries', []))} credited assets, none pending"))
    return findings


AI_PARAMS = ("model", "prompt", "seed")


def wan_count_findings(deck: Deck) -> list[Finding]:
    """Wan key shots cost ~15 min and ~26 GB each: at most two per video (2bacb8a2b8b0)."""
    from content_farm.explainer.wan import MAX_WAN_PER_VIDEO

    wan_slides = [slide.id for slide in deck.slides
                  if slide.media_kind == MediaKind.AI_IMAGE and slide.media is not None
                  and slide.media.motion_kind == Motion.WAN]
    if len(wan_slides) > MAX_WAN_PER_VIDEO:
        return [Finding("ai_motion", "error", f"{len(wan_slides)} slides ask for motion: wan "
                                              f"(max {MAX_WAN_PER_VIDEO}): {', '.join(wan_slides)}")]
    return []


def ai_motion_findings(ai: list[dict]) -> list[Finding]:
    """Every AI frame's motion is recorded: Wan with model/prompt/seed, parallax with its depth
    tool; a fallback (e.g. Wan not baked) is a warning, not an error."""
    from content_farm.explainer.wan import MAX_WAN_PER_VIDEO

    if not any("motion" in e for e in ai):
        return []  # credits written before motion existed (2026-10-16 ai-illustration runs)
    findings: list[Finding] = []
    moves = [(e.get("slide_id", "?"), e.get("motion") or {}) for e in ai]
    wan = [(slide, move) for slide, move in moves if move.get("kind") == Motion.WAN.value]
    if len(wan) > MAX_WAN_PER_VIDEO:
        findings.append(Finding("ai_motion", "error",
                                f"{len(wan)} Wan clips in the video (max {MAX_WAN_PER_VIDEO})"))
    unrecorded = [slide for slide, move in wan if any(move.get(k) in (None, "") for k in AI_PARAMS)]
    unrecorded += [slide for slide, move in moves
                   if move.get("kind") == Motion.PARALLAX.value and not move.get("tool_repo")]
    if unrecorded:
        findings.append(Finding("ai_motion", "error",
                                f"AI motion without its model/parameters: {', '.join(unrecorded)}"))
    fallbacks = [f"{slide}({move['requested']}→{move.get('kind')}: {move.get('fallback_reason')})"
                 for slide, move in moves if move.get("requested")]
    if fallbacks:
        findings.append(Finding("ai_motion", "warn", f"motion fell back: {'; '.join(fallbacks)}"))
    if not findings:
        kinds = sorted({move.get("kind", "none") for _, move in moves})
        findings.append(Finding("ai_motion", "ok",
                                f"motion recorded for {len(ai)} AI image(s): {', '.join(kinds)}"))
    return findings


def ai_image_findings(entries: list[dict]) -> list[Finding]:
    """Leon 2026-10-16 rules: every AI frame carries 「AI 示意圖」; generation parameters are
    recorded; prompts never ask for photo-realism or an artist's style."""
    from content_farm.explainer.illustrate import AI_LABEL, forbidden_prompt_terms

    ai = [e for e in entries if e.get("kind") == "ai_image"]
    if not ai:
        return []
    findings: list[Finding] = []
    unlabelled = [e.get("slide_id", "?") for e in ai if e.get("ai_label") != AI_LABEL]
    if unlabelled:
        findings.append(Finding("ai_label", "error", f"AI image without the 「{AI_LABEL}」 badge: "
                                                     f"{', '.join(unlabelled)}"))
    unrecorded = [f"{e.get('slide_id', '?')}({'/'.join(k for k in AI_PARAMS if e.get(k) in (None, ''))})"
                  for e in ai if any(e.get(k) in (None, "") for k in AI_PARAMS)]
    if unrecorded:
        findings.append(Finding("ai_params", "error",
                                f"AI image without model/prompt/seed in credits: {', '.join(unrecorded)}"))
    styled = [f"{e.get('slide_id', '?')}:{','.join(bad)}" for e in ai
              if (bad := forbidden_prompt_terms(str(e.get("prompt", ""))))]
    if styled:
        findings.append(Finding("ai_style", "error", f"photo-real / artist-style prompt: {'; '.join(styled)}"))
    findings += ai_motion_findings(ai)
    if not any(f.level == "error" for f in findings):
        findings.append(Finding("ai_image", "ok", f"{len(ai)} AI image(s) labelled 「{AI_LABEL}」 "
                                                  "with model/prompt/seed recorded"))
    return findings


def probe_streams(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration",
         "-of", "json", str(video)],
        capture_output=True, text=True, timeout=60, check=True,
    )
    return json.loads(out.stdout)


def format_findings(channel: Channel, streams: dict) -> list[Finding]:
    video = next((s for s in streams.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams.get("streams", []) if s.get("codec_type") == "audio"), None)
    if video is None or audio is None:
        return [Finding("streams", "error", "final video lacks a video or an audio stream")]
    findings: list[Finding] = []
    size = (int(video["width"]), int(video["height"]))
    expected = ASPECT_SIZES[channel.format.aspect]
    findings.append(Finding("resolution", "ok" if size == expected else "error",
                            f"{size[0]}x{size[1]} (expected {expected[0]}x{expected[1]})"))
    seconds = float(video.get("duration", 0))
    low, high = channel.format.target_seconds
    findings.append(Finding("duration", "ok" if low <= seconds <= high else "warn",
                            f"{seconds:.1f}s (channel target {low}-{high}s)"))
    goal = channel.format.goal_seconds
    if goal is not None:
        findings.append(Finding("duration_goal", "ok" if seconds >= goal else "warn",
                                f"{seconds:.1f}s vs goal >= {goal}s (mid-roll needs 8:00)"))
    drift = abs(float(audio.get("duration", 0)) - seconds)
    findings.append(Finding("av_drift", "ok" if drift <= AV_DRIFT_SECONDS else "warn",
                            f"audio/video differ by {drift:.2f}s"))
    return findings


_BLACK = re.compile(r"black_start:([\d.]+)\s+black_end:([\d.]+)")


def black_segments(video: Path, min_seconds: float = BLACK_MIN_SECONDS) -> list[tuple[float, float]]:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vf",
         f"blackdetect=d={min_seconds}:pix_th=0.10", "-an", "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800,
    )
    if out.returncode != 0:
        raise RuntimeError(f"blackdetect failed: {out.stderr[-400:]}")
    return [(float(a), float(b)) for a, b in _BLACK.findall(out.stderr)]


def black_findings(segments: list[tuple[float, float]]) -> list[Finding]:
    if not segments:
        return [Finding("black_frames", "ok", f"no black segment >= {BLACK_MIN_SECONDS}s")]
    spans = ", ".join(f"{a:.1f}-{b:.1f}s" for a, b in segments[:8])
    return [Finding("black_frames", "error", f"{len(segments)} black segment(s): {spans}")]


def subtitle_findings(run_dir: Path, channel: Channel) -> list[Finding]:
    srt = run_dir / "subtitles" / "subtitles.srt"
    if not srt.is_file():
        return [Finding("subtitle_safe_zone", "error", f"{srt.relative_to(run_dir)} missing")]
    if channel.format.aspect == "9:16":
        return portrait_subtitle_findings(srt)
    if channel.format.aspect != "16:9":
        return [Finding("subtitle_safe_zone", "warn", f"no safe-zone measurement for {channel.format.aspect}")]
    from content_farm.assembly.drawtext import find_cjk_font
    from content_farm.explainer.mascot.clearance import wide_lines

    wide = wide_lines(srt, find_cjk_font())
    if wide:
        worst = wide[0]
        return [Finding("subtitle_safe_zone", "error",
                        f"{len(wide)} line(s) reach the mascot column; widest x={worst.right_edge}: "
                        f"{worst.text}")]
    return [Finding("subtitle_safe_zone", "ok", "every subtitle line clears the mascot column")]


def portrait_subtitle_findings(srt: Path, font_path: str | None = None) -> list[Finding]:
    """9:16: every line fits between the side margins and no cue is taller than the subtitle band."""
    from PIL import ImageFont

    from content_farm.assembly.drawtext import find_cjk_font
    from content_farm.production import shorts_cut as cut

    font_path = font_path or find_cjk_font()
    if font_path is None:
        return [Finding("subtitle_safe_zone", "error", "no CJK font found to measure subtitles")]
    font = ImageFont.truetype(font_path, cut.SUB_FONT_SIZE)
    limit = cut.FRAME_W - 2 * cut.SUB_MARGIN_X
    cues = cut.parse_cues(srt.read_text(encoding="utf-8"))
    wide, tall = [], []
    for cue in cues:
        lines = cue.text.split("\n")
        if len(lines) > cut.SUB_MAX_LINES:
            tall.append(cue.text.replace("\n", "／"))
        for line in lines:
            x0, _, x1, _ = font.getbbox(line)
            if (x1 - x0) + 2 * cut.SUB_OUTLINE > limit:
                wide.append(line)
    if wide or tall:
        parts = ([f"{len(wide)} line(s) wider than {limit}px: {wide[0]}"] if wide else []) + \
                ([f"{len(tall)} cue(s) over {cut.SUB_MAX_LINES} lines: {tall[0]}"] if tall else [])
        return [Finding("subtitle_safe_zone", "error", "; ".join(parts))]
    return [Finding("subtitle_safe_zone", "ok", f"{len(cues)} cues fit the 9:16 subtitle band")]


def short_motion_findings(run_dir: Path) -> list[Finding]:
    """Scripted Short: no stage may hold still longer than MAX_STEP_SECONDS (review: 13 s card)."""
    path = run_dir / "short" / "beat_report.json"
    if not path.is_file():
        return []
    report = json.loads(path.read_text(encoding="utf-8"))
    limit = float(report["max_step_seconds"])
    slow = [f"beat {b['beat']} {b['visual']} {b['longest_hold']:.1f}s" for b in report["beats"]
            if b["longest_hold"] > limit]
    if slow:
        return [Finding("short_motion", "error", f"stage holds longer than {limit:.0f}s: {', '.join(slow)}")]
    worst = max(b["longest_hold"] for b in report["beats"])
    return [Finding("short_motion", "ok", f"{len(report['beats'])} beats, longest still stage {worst:.1f}s")]


def qc_channel(run_dir: Path, channel: Channel) -> Channel:
    """A Short cut is checked as a Short (9:16, Shorts length) whatever channel publishes it;
    e.g. the 7,722 Short on the 16:9 chipcat channel."""
    from content_farm.production import shorts_cut

    if not shorts_cut.is_short_cut(run_dir):
        return channel
    short_format = channel.format.model_copy(update={
        "length": "short", "aspect": "9:16", "target_seconds": (1, int(shorts_cut.MAX_SHORT_SECONDS)),
        "goal_seconds": None})
    return channel.model_copy(update={"format": short_format})


def run_qc(run_dir: Path, channel: Channel, deck: Deck | None) -> dict:
    channel = qc_channel(run_dir, channel)
    findings: list[Finding] = []
    if deck is not None:
        findings += deck_findings(channel, deck)
    credits_path = run_dir / "credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.is_file() else None
    if channel.media.stock or channel.media.ai_image or channel.media.artwork:
        findings += credits_findings(channel, credits)
    findings += subtitle_findings(run_dir, channel)
    findings += short_motion_findings(run_dir)
    if deck is not None and channel.format.length == "long":
        from content_farm.production.thumbnail import thumbnail_findings

        findings += thumbnail_findings(run_dir, channel)
    from content_farm.production.thumbnail import variant_findings

    findings += variant_findings(run_dir, channel)   # A/B variants or Shorts covers, when the run has them
    video = final_video(run_dir)
    if video is None:
        findings.append(Finding("final_video", "error", "assembly/final.mp4 and draft.mp4 missing"))
    else:
        findings.append(Finding("final_video", "ok", video.relative_to(run_dir).as_posix()))
        try:
            findings += format_findings(channel, probe_streams(video))
            findings += black_findings(black_segments(video))
        except (subprocess.SubprocessError, RuntimeError, KeyError, ValueError) as exc:
            findings.append(Finding("probe", "error", f"could not inspect {video.name}: {exc}"))
    report = {
        "video": video.relative_to(run_dir).as_posix() if video else None,
        "errors": sum(f.level == "error" for f in findings),
        "warnings": sum(f.level == "warn" for f in findings),
        "findings": [asdict(f) for f in findings],
    }
    path = run_dir / QC_REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
