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

from content_farm.explainer.deck import Deck, MediaKind
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
    bad = [f"{slide.id}:{slide.media_kind.value}" for slide in deck.slides
           if slide.media_kind not in allowed]
    if bad:
        return [Finding("media_policy", "error",
                        f"channel {channel.code} does not allow: {', '.join(bad)}")]
    return [Finding("media_policy", "ok", f"{len(deck.slides)} slides within channel media policy")]


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
    if not findings:
        findings.append(Finding("credits", "ok",
                                f"{len(credits.get('entries', []))} credited assets, none pending"))
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
    if channel.format.aspect != "16:9":
        return [Finding("subtitle_safe_zone", "warn", "safe-zone measurement only covers 16:9")]
    from content_farm.assembly.drawtext import find_cjk_font
    from content_farm.explainer.mascot.clearance import wide_lines

    wide = wide_lines(srt, find_cjk_font())
    if wide:
        worst = wide[0]
        return [Finding("subtitle_safe_zone", "error",
                        f"{len(wide)} line(s) reach the mascot column; widest x={worst.right_edge}: "
                        f"{worst.text}")]
    return [Finding("subtitle_safe_zone", "ok", "every subtitle line clears the mascot column")]


def run_qc(run_dir: Path, channel: Channel, deck: Deck | None) -> dict:
    findings: list[Finding] = []
    if deck is not None:
        findings += policy_findings(channel, deck)
    credits_path = run_dir / "credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.is_file() else None
    if channel.media.stock or channel.media.ai_image or channel.media.artwork:
        findings += credits_findings(channel, credits)
    findings += subtitle_findings(run_dir, channel)
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
