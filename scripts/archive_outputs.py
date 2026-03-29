"""Batch-archive completed output directories to Google Drive.

Scans output/ for run dirs that contain an upload/ subfolder (meaning
the video is prepared for YouTube). Uploads each to Drive, then deletes
the local copy.

Usage:
    python scripts/archive_outputs.py [--dry-run] [--output-dir output]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from content_farm.config import Settings
from content_farm.pipeline.container import ServiceContainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _dir_size_mb(path: Path) -> float:
    """Calculate directory size in MB."""
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def find_archivable_dirs(output_dir: Path) -> list[Path]:
    """Return run dirs that have an upload/ subfolder, sorted by name."""
    if not output_dir.is_dir():
        return []
    dirs = [
        d for d in sorted(output_dir.iterdir())
        if d.is_dir() and (d / "upload").is_dir()
    ]
    return dirs


async def archive_one(
    run_dir: Path,
    container: ServiceContainer,
) -> str | None:
    """Upload a single run dir to Drive. Returns Drive link or None on failure."""
    from content_farm.drive.uploader import DriveUploader

    uploader = container.create_drive_uploader()
    if uploader is None:
        logger.error("Drive uploader not available — check credentials")
        return None

    try:
        link = await uploader.upload_folder(run_dir, run_dir.name)
    except Exception:
        logger.exception("Failed to upload %s", run_dir.name)
        return None

    if not link or not link.startswith("http"):
        logger.error("Upload returned invalid link for %s: %s", run_dir.name, link)
        return None

    return link


async def main() -> None:
    parser = argparse.ArgumentParser(description="Archive completed outputs to Drive")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List what would be archived without uploading or deleting",
    )
    parser.add_argument(
        "--output-dir", default="output",
        help="Path to the output directory (default: output)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    dirs = find_archivable_dirs(output_dir)

    if not dirs:
        print("No archivable directories found (need output/*/upload/).")
        return

    print(f"Found {len(dirs)} archivable director{'y' if len(dirs) == 1 else 'ies'}:\n")
    total_mb = 0.0
    for d in dirs:
        mb = _dir_size_mb(d)
        total_mb += mb
        print(f"  {d.name}  ({mb:.0f} MB)")
    print(f"\n  Total: {total_mb:.0f} MB\n")

    if args.dry_run:
        print("Dry run — no changes made.")
        return

    settings = Settings()
    container = ServiceContainer(settings)

    if not container.has_drive_credentials():
        print("ERROR: Drive credentials not configured. Set CF_DRIVE_* env vars.")
        sys.exit(1)

    archived = 0
    freed_mb = 0.0

    for d in dirs:
        mb = _dir_size_mb(d)
        print(f"Uploading {d.name} ({mb:.0f} MB) ...", end=" ", flush=True)

        link = await archive_one(d, container)
        if link is None:
            print("FAILED — skipping delete")
            continue

        print(f"OK → {link}")
        shutil.rmtree(d)
        logger.info("Deleted local: %s", d)
        archived += 1
        freed_mb += mb

    print(f"\nDone: {archived}/{len(dirs)} archived, {freed_mb:.0f} MB freed.")


if __name__ == "__main__":
    asyncio.run(main())
