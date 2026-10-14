#!/usr/bin/env python3
"""CLI: generate Nano Banana images via Playwright browser automation.

Reads a storyboard_prompts.md file from a run directory, lets you pick
which variant to process, then drives Gemini web chat to generate each
image shot. Downloads go into the run's ``visual/`` folder with
timeline filenames (``MM:SS~MM:SS.png``).

Usage:
    python scripts/generate_visuals.py --run-dir output/<run>/
    python scripts/generate_visuals.py --run-dir output/<run>/ --variant 0  # pick Variant A

Explainer ai_image slides (prompts written by media_to_visual.py):
    python scripts/generate_visuals.py --run-dir output/<run>/ --variant 0 \
        --storyboard ai_image_prompts.md --out-dir assets/ai_images
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from content_farm.config import Settings
from content_farm.visual_gen.gemini_browser import (
    GeminiBrowser,
    GeminiBrowserConfig,
)
from content_farm.visual_gen.storyboard_parser import Variant, parse_storyboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("generate_visuals")


def _choose_variant(variants: list[Variant], preset: int | None) -> Variant:
    if preset is not None:
        if preset < 0 or preset >= len(variants):
            print(f"❌ --variant {preset} out of range (0..{len(variants) - 1})")
            sys.exit(1)
        return variants[preset]

    print("\nAvailable variants:")
    for idx, v in enumerate(variants):
        imgs = len(v.image_shots)
        vids = len(v.video_shots)
        print(f"  [{idx}] Variant {v.name} — {imgs} images, {vids} videos")

    while True:
        choice = input("\nPick a variant number (or Q to quit): ").strip()
        if choice.lower() in {"q", "quit"}:
            sys.exit(0)
        try:
            idx = int(choice)
            if 0 <= idx < len(variants):
                return variants[idx]
        except ValueError:
            pass
        print("Invalid choice, try again.")


async def _main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True, help="Path to output/<run>/")
    ap.add_argument(
        "--variant", type=int, default=None,
        help="Variant index (0-based). If omitted, will prompt interactively.",
    )
    ap.add_argument(
        "--headless", action="store_true",
        help="Run browser headless (no UI). Default: headed.",
    )
    ap.add_argument(
        "--system-chrome", action="store_true",
        help="Use your installed Google Chrome (channel='chrome') instead "
             "of Playwright's Chromium. Combine with --chrome-profile to "
             "reuse your existing Chrome profile (already-logged-in).",
    )
    ap.add_argument(
        "--chrome-profile", default=None,
        help="Override user_data_dir (e.g. ~/Library/Application Support/Google/Chrome). "
             "WARNING: close Chrome first — it can't be running with this profile.",
    )
    ap.add_argument(
        "--cdp-port", type=int, default=None,
        help="Attach to an already-running Chrome via CDP (e.g. 9222). "
             "Launch Chrome first with scripts/launch_chrome_debug.sh. "
             "Avoids Google's automation detection because Chrome is a real "
             "user session.",
    )
    ap.add_argument(
        "--storyboard", default="storyboard_prompts.md",
        help="Prompt file, relative to --run-dir (explainer: ai_image_prompts.md).",
    )
    ap.add_argument(
        "--out-dir", default="visual",
        help="Download directory, relative to --run-dir (explainer: assets/ai_images).",
    )
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    storyboard = run_dir / args.storyboard
    if not storyboard.is_file():
        print(f"❌ Not found: {storyboard}")
        print("   Generate a storyboard first with `/project:storyboard <run-dir>`")
        sys.exit(1)

    variants = parse_storyboard(storyboard)
    if not variants:
        print(f"❌ No variants parsed from {storyboard}")
        sys.exit(1)

    variant = _choose_variant(variants, args.variant)
    print(f"\n✅ Selected: Variant {variant.name}")
    print(f"   {len(variant.image_shots)} image shots, "
          f"{len(variant.video_shots)} video shots (videos will be skipped)\n")

    settings = Settings()  # type: ignore[call-arg]
    user_data_dir = Path(
        args.chrome_profile or settings.gemini_browser_user_data_dir
    ).expanduser().resolve()
    download_dir = run_dir / args.out_dir

    use_system_chrome = args.system_chrome or settings.gemini_browser_use_system_chrome

    if use_system_chrome and args.chrome_profile is None:
        print("⚠️  Using system Chrome without --chrome-profile — will still")
        print("   create a fresh profile at the default user_data_dir.")

    config = GeminiBrowserConfig(
        user_data_dir=user_data_dir,
        download_dir=download_dir,
        delay_between_prompts_s=settings.gemini_browser_delay_s,
        generation_timeout_s=settings.gemini_browser_generation_timeout_s,
        headless=args.headless or settings.gemini_browser_headless,
        use_system_chrome=use_system_chrome,
        cdp_port=args.cdp_port,
    )

    browser = GeminiBrowser(config)
    results = await browser.run(list(variant.shots))

    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    success_count = sum(1 for r in results if r.success)
    print(f"  ✅ Success: {success_count}/{len(results)}")
    print(f"  ❌ Failed:  {len(results) - success_count}/{len(results)}")

    failed = [r for r in results if not r.success]
    if failed:
        print("\nFailed shots:")
        for r in failed:
            print(f"  - {r.shot.filename}: {r.error}")
        print("\nRe-run and pick the same variant to retry the failed ones.")

    print(f"\nImages saved to: {download_dir}")
    print("\nNext step: assemble the video with")
    print(f"  python scripts/run_stage.py --stage assembly_timeline "
          f"--run-dir {run_dir.relative_to(Path.cwd()) if run_dir.is_relative_to(Path.cwd()) else run_dir}")


if __name__ == "__main__":
    asyncio.run(_main())
