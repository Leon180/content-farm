"""CLI entry point for generating a video script.

Two modes:
- Topic mode: ``--topic "..."`` generates from scratch (short OR long form)
- Prescript mode: ``--from-prescript <run_dir>`` consumes an approved
  chapter-level ``prescript.json`` and runs only the expansion phase.
  Long-form only — short-form prescript is still handled by the Claude skill.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from content_farm.config import Settings
from content_farm.llm.cache import FileCache, NullCache
from content_farm.llm.client import LLMClient
from content_farm.script_gen.generator import ScriptGenerator
from content_farm.script_gen.schemas import (
    ChapterOutline,
    ChapterOutlineList,
    ScriptRequest,
)
from content_farm.types import GenreTemplate, Orientation, Tone, VideoLength


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a YouTube video script")
    parser.add_argument(
        "--topic",
        required=False,
        default=None,
        help="Video topic (required unless --from-prescript is used)",
    )
    parser.add_argument(
        "--keywords", nargs="*", default=[], help="Keywords to incorporate"
    )
    parser.add_argument(
        "--tone",
        choices=[t.value for t in Tone],
        default="educational",
        help="Script tone",
    )
    parser.add_argument(
        "--length",
        choices=[v.value for v in VideoLength],
        default="medium",
        help="Video length",
    )
    parser.add_argument(
        "--orientation",
        choices=[o.value for o in Orientation],
        default="portrait",
        help="Video orientation (portrait for shorts, landscape for long-form)",
    )
    parser.add_argument(
        "--genre",
        choices=[g.value for g in GenreTemplate],
        default=None,
        help="Long-form genre template (ignored for short videos)",
    )
    parser.add_argument(
        "--from-prescript",
        dest="from_prescript",
        default=None,
        help="Path to a run directory containing a chapter-level prescript.json "
             "(long-form only). Skips chapter outline generation and expands "
             "approved chapters directly.",
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Disable response caching"
    )
    parser.add_argument(
        "--output", "-o", help="Output file path (default: stdout)"
    )
    return parser.parse_args()


def _parse_chapter_prescript(path: Path) -> tuple[str, ChapterOutlineList]:
    """Read a chapter-level prescript.json and return (topic, ChapterOutlineList).

    Raises ``ValueError`` if the file is a short-form prescript (has ``scenes[]``
    but no ``chapters[]``) — those stay in the skill-level flow.
    """
    if not path.is_file():
        msg = f"prescript.json not found at {path}"
        raise FileNotFoundError(msg)

    data = json.loads(path.read_text(encoding="utf-8"))

    if "chapters" not in data or not data["chapters"]:
        msg = (
            f"prescript.json at {path} has no 'chapters' array — this looks "
            f"like a short-form prescript. --from-prescript only supports "
            f"long-form chapter outlines."
        )
        raise ValueError(msg)

    topic = data.get("topic") or data.get("video_title", "")
    if not topic:
        msg = f"prescript.json at {path} missing 'topic' and 'video_title'"
        raise ValueError(msg)

    chapters_data = data["chapters"]
    chapters = tuple(
        ChapterOutline(
            chapter_number=ch["chapter_number"],
            title=ch["title"],
            summary=ch["summary"],
            duration_seconds=float(ch["duration_seconds"]),
            key_points=tuple(ch.get("key_points", ())),
            hook=ch.get("hook", ""),
            payoff=ch.get("payoff", ""),
            start_timestamp=float(ch.get("start_timestamp", 0.0)),
        )
        for ch in chapters_data
    )

    outline = ChapterOutlineList(
        video_title=data.get("video_title", topic),
        description=data.get("description", ""),
        chapters=chapters,
        tags=tuple(data.get("tags", ())),
        sources=tuple(data.get("sources", ())),
    )
    return topic, outline


async def main() -> None:
    args = parse_args()

    if args.from_prescript is None and not args.topic:
        print(
            "Error: either --topic or --from-prescript must be provided.",
            file=sys.stderr,
        )
        sys.exit(2)

    settings = Settings()  # type: ignore[call-arg]

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    llm = LLMClient(api_key=settings.anthropic_api_key.get_secret_value())

    if args.no_cache:
        cache = NullCache()
    else:
        cache = FileCache(settings.cache_dir)

    generator = ScriptGenerator(llm=llm, cache=cache, settings=settings)

    if args.from_prescript is not None:
        run_dir = Path(args.from_prescript)
        prescript_path = run_dir / "prescript.json"
        topic, outline = _parse_chapter_prescript(prescript_path)

        # Long-form prescript mode: video_length default bumps to LONG if caller
        # left the default, since chapter-level prescripts are inherently long.
        length_value = args.length if args.length != "medium" else "long"

        request = ScriptRequest(
            topic=topic,
            keywords=args.keywords,
            video_length=VideoLength(length_value),
            tone=Tone(args.tone),
            orientation=Orientation(args.orientation),
            genre=GenreTemplate(args.genre) if args.genre else None,
        )
        logging.getLogger(__name__).info(
            "Expanding approved prescript: topic=%s, chapters=%d, length=%s, "
            "orientation=%s, genre=%s",
            request.topic,
            len(outline.chapters),
            request.video_length,
            request.orientation,
            request.genre,
        )
        try:
            script = await generator.generate_from_approved_chapters(request, outline)
        finally:
            await llm.close()

        # Default output: write script.json inside the run_dir unless overridden
        output_path = Path(args.output) if args.output else (run_dir / "script.json")
    else:
        request = ScriptRequest(
            topic=args.topic,
            keywords=args.keywords,
            video_length=VideoLength(args.length),
            tone=Tone(args.tone),
            orientation=Orientation(args.orientation),
            genre=GenreTemplate(args.genre) if args.genre else None,
        )
        logging.getLogger(__name__).info(
            "Generating script: topic=%s, length=%s, tone=%s, orientation=%s, genre=%s",
            request.topic,
            request.video_length,
            request.tone,
            request.orientation,
            request.genre,
        )
        try:
            script = await generator.generate(request)
        finally:
            await llm.close()

        output_path = Path(args.output) if args.output else None

    output = json.dumps(script.model_dump(), indent=2, default=str, ensure_ascii=False)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        print(f"Script saved to {output_path}")

        # Long-form scripts also get a human-friendly summary for the review gate
        if script.chapters and args.from_prescript is not None:
            summary_path = output_path.parent / "script_summary.md"
            summary_path.write_text(
                _build_script_summary(script), encoding="utf-8"
            )
            print(f"Review summary saved to {summary_path}")
            _print_review_gate_notice(output_path.parent, script)
    else:
        print(output)


def _build_script_summary(script) -> str:  # noqa: ANN001
    """Render a human-scannable markdown summary of a long-form script."""
    lines: list[str] = []
    lines.append(f"# Script Review — {script.video_title}")
    lines.append("")
    total_min = (script.total_duration_seconds or 0) / 60
    lines.append(
        f"**Total:** {len(script.scenes)} scenes across {len(script.chapters)} "
        f"chapters — ~{total_min:.1f} min estimated"
    )
    lines.append(f"**Orientation:** {script.orientation.value}")
    lines.append(
        f"**Genre:** {script.genre.value if script.genre else '—'}"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    scenes_by_chapter: dict[int, list] = {}
    for scene in script.scenes:
        scenes_by_chapter.setdefault(scene.chapter_number or 0, []).append(scene)

    for ch in script.chapters:
        lines.append(f"## Chapter {ch.chapter_number} — {ch.title}")
        lines.append(
            f"*{ch.duration_seconds:.0f}s estimated · starts at "
            f"{int(ch.start_timestamp // 60):02d}:{int(ch.start_timestamp % 60):02d}*"
        )
        lines.append("")
        lines.append(f"> **Hook:** {ch.hook}")
        lines.append(f"> **Payoff:** {ch.payoff}")
        lines.append("")
        for scene in scenes_by_chapter.get(ch.chapter_number, ()):
            lines.append(
                f"### Scene {scene.scene_number} · {scene.duration_seconds:.0f}s · "
                f"{scene.title}"
            )
            lines.append("")
            lines.append(scene.narration)
            lines.append("")
            keywords = ", ".join(scene.b_roll_keywords) or "—"
            lines.append(f"*B-roll:* `{keywords}`")
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Review Checklist")
    lines.append("")
    lines.append("- [ ] Every chapter hook actually hooks; every payoff actually pays off")
    lines.append("- [ ] No factual claims you cannot defend (check research.md)")
    lines.append("- [ ] Tone matches target genre; no trendy slang (狂 / 絕了), moderate 欸")
    lines.append("- [ ] Total duration sits in the 5-15 min sweet spot")
    lines.append("- [ ] No chapter is boring enough to skip past")
    lines.append("")
    lines.append("**Edit `script.json` directly** for any changes; subsequent")
    lines.append("stages (voice, storyboard, assembly) read that file, not this summary.")
    return "\n".join(lines)


def _print_review_gate_notice(run_dir: Path, script) -> None:  # noqa: ANN001
    """Print a loud terminal prompt so the user knows to stop and review."""
    total_min = (script.total_duration_seconds or 0) / 60
    print()
    print("=" * 70)
    print(" SCRIPT REVIEW GATE — stop here before running voice stage")
    print("=" * 70)
    print(
        f"  • {len(script.scenes)} scenes · {len(script.chapters)} chapters · "
        f"~{total_min:.1f} min"
    )
    print(f"  • Skim:   {run_dir / 'script_summary.md'}")
    print(f"  • Edit:   {run_dir / 'script.json'}  (this is the source of truth)")
    print()
    print("  When satisfied:")
    print(f"    python scripts/run_stage.py --stage voice --run-dir {run_dir}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
