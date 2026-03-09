"""CLI entry point for generating a video script."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from content_farm.config import Settings
from content_farm.llm.cache import FileCache, NullCache
from content_farm.llm.client import LLMClient
from content_farm.script_gen.generator import ScriptGenerator
from content_farm.script_gen.schemas import ScriptRequest
from content_farm.types import Tone, VideoLength


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a YouTube video script")
    parser.add_argument("--topic", required=True, help="Video topic")
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
        "--no-cache", action="store_true", help="Disable response caching"
    )
    parser.add_argument(
        "--output", "-o", help="Output file path (default: stdout)"
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

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

    request = ScriptRequest(
        topic=args.topic,
        keywords=args.keywords,
        video_length=VideoLength(args.length),
        tone=Tone(args.tone),
    )

    logging.getLogger(__name__).info(
        "Generating script: topic=%s, length=%s, tone=%s",
        request.topic,
        request.video_length,
        request.tone,
    )

    try:
        script = await generator.generate(request)
    finally:
        await llm.close()

    output = json.dumps(script.model_dump(), indent=2, default=str)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Script saved to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    asyncio.run(main())
