"""CLI entry point for the full content pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from pathlib import Path

from content_farm.config import Settings
from content_farm.pipeline.orchestrator import ContentPipeline, MaterialsResult, PipelineResult
from content_farm.script_gen.schemas import Script, ScriptRequest
from content_farm.types import Tone, VideoLength


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full content pipeline")
    parser.add_argument("--topic", help="Video topic (required unless --script or --resume is used)")
    parser.add_argument("--script", help="Path to pre-approved script JSON (skips generation + approval)")
    parser.add_argument("--resume", help="Resume a failed run by run_id")
    parser.add_argument("--list-runs", action="store_true", help="List recent pipeline runs")
    parser.add_argument(
        "--keywords", nargs="*", default=[], help="Keywords to incorporate",
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
        "--mode",
        choices=["materials", "full"],
        default="materials",
        help="Pipeline mode: materials (template video + Drive) or full (end-to-end)",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable LLM cache")
    parser.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--output-dir", default=None, help="Output directory")
    args = parser.parse_args()
    if not args.script and not args.topic and not args.resume and not args.list_runs:
        parser.error("One of --topic, --script, --resume, or --list-runs is required")
    return args


async def main() -> None:
    args = parse_args()

    settings = Settings()  # type: ignore[call-arg]

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    output_dir = Path(args.output_dir) if args.output_dir else Path("output")

    pipeline = ContentPipeline(
        settings=settings,
        output_dir=output_dir,
        use_cache=not args.no_cache,
        skip_upload=args.skip_upload,
    )

    # --- List runs ---
    if args.list_runs:
        from content_farm.pipeline.state import PipelineStateDB
        db = PipelineStateDB(output_dir / "pipeline_state.db")
        runs = db.list_runs()
        if not runs:
            print("No pipeline runs found.")
        else:
            print(f"{'RUN ID':<14} {'STATUS':<13} {'STAGES':<40} {'TOPIC'}")
            print("-" * 90)
            for r in runs:
                stages = ", ".join(r.completed_stages) or "(none)"
                print(f"{r.run_id:<14} {r.status:<13} {stages:<40} {r.topic[:30]}")
        db.close()
        return

    # --- Resume ---
    if args.resume:
        print(f"Resuming run: {args.resume}")
        result = await pipeline.resume(args.resume)
        _print_full_result(result)
        return

    if args.script:
        script_data = json.loads(Path(args.script).read_text(encoding="utf-8"))
        script = Script.model_validate(script_data)
        print(f"Loaded script: {script.video_title} ({len(script.scenes)} scenes)")
        result = await pipeline.run_from_script(script)
        _print_full_result(result)
        return

    request = ScriptRequest(
        topic=args.topic,
        keywords=tuple(args.keywords),
        video_length=VideoLength(args.length),
        tone=Tone(args.tone),
        language=settings.default_language,
    )

    if args.mode == "materials":
        mat_result = await pipeline.run_materials(request)
        _print_materials_result(mat_result)
    else:
        result = await pipeline.run(request)
        _print_full_result(result)


def _print_full_result(result: PipelineResult) -> None:
    print("\nPipeline complete!")
    print(f"  Output: {result.output_dir}")
    print(f"  Video:  {result.assembly.file_path}")
    if result.upload:
        print(f"  YouTube: {result.upload.url}")


def _print_materials_result(result: MaterialsResult) -> None:
    print("\nMaterials pipeline complete!")
    print(f"  Output:   {result.output_dir}")
    print(f"  Template: {result.template_video_path}")
    if result.drive_link:
        print(f"  Drive:    {result.drive_link}")


if __name__ == "__main__":
    asyncio.run(main())
