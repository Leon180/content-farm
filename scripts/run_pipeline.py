"""CLI entry point for the full content pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from content_farm.config import Settings
from content_farm.pipeline.orchestrator import ContentPipeline
from content_farm.script_gen.schemas import ScriptRequest
from content_farm.types import Tone, VideoLength


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full content pipeline")
    parser.add_argument("--topic", required=True, help="Video topic")
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
    parser.add_argument("--no-cache", action="store_true", help="Disable LLM cache")
    parser.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--output-dir", default=None, help="Output directory")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    settings = Settings()  # type: ignore[call-arg]

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    pipeline = ContentPipeline(
        settings=settings,
        output_dir=args.output_dir,
        use_cache=not args.no_cache,
        skip_upload=args.skip_upload,
    )

    request = ScriptRequest(
        topic=args.topic,
        keywords=tuple(args.keywords),
        video_length=VideoLength(args.length),
        tone=Tone(args.tone),
        language=settings.default_language,
    )

    result = await pipeline.run(request)

    print(f"\nPipeline complete!")
    print(f"  Output: {result.output_dir}")
    print(f"  Video:  {result.assembly.file_path}")
    if result.upload:
        print(f"  YouTube: {result.upload.url}")


if __name__ == "__main__":
    asyncio.run(main())
