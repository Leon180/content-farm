"""Check and re-fetch missing artifacts for a pipeline run.

Checks Google Drive first (if configured), falls back to local directory scan.
Reports what's missing, then re-runs only the missing stages after
user confirmation and uploads results to Google Drive.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from content_farm.config import Settings
from content_farm.drive.uploader import extract_folder_id
from content_farm.pipeline.container import ServiceContainer
from content_farm.pipeline.context import PipelineContext
from content_farm.pipeline.state import PipelineStateDB
from content_farm.script_gen.schemas import Script
from content_farm.telegram.approval import ApprovalGate

logger = logging.getLogger(__name__)

# Expected folder → file patterns for each stage
_STAGE_FOLDERS: dict[str, tuple[str, list[str]]] = {
    "voice": ("audio", ["*.mp3"]),
    "visual": ("visual", ["scene_*.mp4"]),
    "subtitle": ("subtitles", ["*.srt", "*.ass"]),
    "thumbnail": ("thumbnails", ["*.jpg", "*.png"]),
}

# Stages where file count should match scene count
_PER_SCENE_STAGES = frozenset({"voice", "visual"})


class FetchResult(BaseModel):
    """Immutable result of a fetch operation."""

    model_config = {"frozen": True}

    run_id: str
    refetched_stages: tuple[str, ...]
    total_stages_checked: int
    drive_link: str = ""


@dataclass
class _MissingReport:
    """Internal: what's missing and why."""

    missing_stages: list[str] = field(default_factory=list)
    stage_details: dict[str, str] = field(default_factory=dict)
    # Stages where cloud is missing but local has files (upload-only)
    local_only_stages: list[str] = field(default_factory=list)

    @property
    def has_missing(self) -> bool:
        return bool(self.missing_stages)


# ------------------------------------------------------------------
# Detection: Drive-based (primary) and local (fallback)
# ------------------------------------------------------------------


def _detect_missing_drive(
    uploader,
    drive_folder_id: str,
    run_dir: Path,
    script: Script,
) -> _MissingReport:
    """Check Drive subfolders for missing artifacts.

    For each stage: check cloud count, compare with local if cloud is short.
    """
    report = _MissingReport()
    n_scenes = len(script.scenes)

    for stage, (folder_name, patterns) in _STAGE_FOLDERS.items():
        expected = n_scenes if stage in _PER_SCENE_STAGES else 1
        cloud_count = _count_drive_files(uploader, drive_folder_id, folder_name)

        if cloud_count >= expected:
            continue

        local_count = _count_local_files(run_dir / folder_name, patterns)

        if local_count >= expected:
            report.missing_stages.append(stage)
            report.local_only_stages.append(stage)
            report.stage_details[stage] = (
                f"雲端缺少，本地有 {local_count} 個檔案，需要上傳"
            )
        elif cloud_count == 0 and local_count == 0:
            report.missing_stages.append(stage)
            report.stage_details[stage] = "雲端和本地都沒有檔案"
        else:
            report.missing_stages.append(stage)
            report.stage_details[stage] = (
                f"雲端 {cloud_count}/{expected}, 本地 {local_count}/{expected}"
            )

    return report


def _detect_missing_local(run_dir: Path, script: Script) -> _MissingReport:
    """Scan local run directory for missing artifacts (fallback)."""
    report = _MissingReport()
    n_scenes = len(script.scenes)

    for stage, (folder_name, patterns) in _STAGE_FOLDERS.items():
        folder = run_dir / folder_name

        if not folder.is_dir():
            report.missing_stages.append(stage)
            report.stage_details[stage] = "資料夾不存在"
            continue

        count = _count_local_files(folder, patterns)
        expected = n_scenes if stage in _PER_SCENE_STAGES else 1

        if count == 0:
            report.missing_stages.append(stage)
            report.stage_details[stage] = "資料夾是空的"
        elif count < expected:
            report.missing_stages.append(stage)
            report.stage_details[stage] = (
                f"只有 {count}/{expected} 個場景的檔案"
            )

    return report


def _count_drive_files(uploader, parent_id: str, subfolder_name: str) -> int:
    """Count files in a Drive subfolder. Returns 0 if subfolder doesn't exist."""
    try:
        subfolder_id = uploader.find_subfolder(parent_id, subfolder_name)
        if not subfolder_id:
            return 0
        return len(uploader.list_files(subfolder_id))
    except Exception:
        logger.warning("Drive query failed for %s", subfolder_name, exc_info=True)
        return 0


def _count_local_files(folder: Path, patterns: list[str]) -> int:
    """Count matching files in a local folder."""
    if not folder.is_dir():
        return 0
    files: list[Path] = []
    for pat in patterns:
        files.extend(folder.glob(pat))
    return len(files)


def _build_missing_report(
    container: ServiceContainer,
    db: PipelineStateDB,
    run_id: str,
    run_dir: Path,
    script: Script,
) -> _MissingReport:
    """Build missing report: Drive-first, local fallback."""
    if not container.has_drive_credentials():
        return _detect_missing_local(run_dir, script)

    drive_link = db.get_checkpoint(run_id, "drive")
    if not drive_link:
        return _detect_missing_local(run_dir, script)

    folder_id = extract_folder_id(drive_link)
    if not folder_id:
        return _detect_missing_local(run_dir, script)

    uploader = container.create_drive_uploader()
    if uploader is None:
        return _detect_missing_local(run_dir, script)

    try:
        return _detect_missing_drive(uploader, folder_id, run_dir, script)
    except Exception:
        logger.warning("Drive check failed, falling back to local", exc_info=True)
        return _detect_missing_local(run_dir, script)


# ------------------------------------------------------------------
# Report formatting
# ------------------------------------------------------------------


def _format_report(
    report: _MissingReport,
    script: Script,
    run_id: str,
) -> str:
    """Format a user-friendly report of missing artifacts."""
    lines = [f"Run: {run_id} | {script.video_title}"]
    lines.append("缺少以下素材：")

    local_only = set(report.local_only_stages)

    for stage in report.missing_stages:
        folder_name = _STAGE_FOLDERS[stage][0]
        detail = report.stage_details.get(stage, "")
        tag = " [只需上傳]" if stage in local_only else ""

        if stage == "visual":
            kw_parts = []
            for scene in script.scenes:
                if scene.visual_hint.keywords:
                    kw = ", ".join(scene.visual_hint.keywords)
                    kw_parts.append(f"場景 {scene.scene_number}: {kw}")
            if kw_parts:
                lines.append(f"  - {folder_name}/ ({detail}){tag}")
                for part in kw_parts:
                    lines.append(f"      {part}")
            else:
                lines.append(f"  - {folder_name}/ ({detail}){tag}")
        else:
            lines.append(f"  - {folder_name}/ ({detail}){tag}")

    lines.append("")
    lines.append("確認要重新生成並上傳嗎？")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


async def fetch_missing_artifacts(
    run_id: str,
    settings: Settings,
    container: ServiceContainer,
    gate: ApprovalGate,
    db: PipelineStateDB,
) -> FetchResult:
    """Detect missing artifacts (Drive-first), confirm, re-run, upload.

    Steps:
    1. Load run from state DB
    2. Check Drive for missing (fallback to local)
    3. Report to user and wait for confirmation
    4. Re-generate truly-missing stages; upload local-only stages
    5. Upload all new files to Drive
    """
    run_info = db.get_run(run_id)
    if run_info is None:
        raise ValueError(f"Run not found: {run_id}")

    run_dir = Path(run_info.output_dir)

    script = _load_script(run_id, db)
    if script is None:
        await gate.notify_progress(1, 1, f"Run {run_id} 沒有儲存 script，無法檢查。")
        return FetchResult(
            run_id=run_id,
            refetched_stages=(),
            total_stages_checked=0,
        )

    report = _build_missing_report(container, db, run_id, run_dir, script)

    if not report.has_missing:
        await gate.notify_progress(1, 1, "所有素材都已完備，無需重新抓取。")
        return FetchResult(
            run_id=run_id,
            refetched_stages=(),
            total_stages_checked=len(_STAGE_FOLDERS),
        )

    message = _format_report(report, script, run_id)
    confirmed = await gate.confirm_action(message)

    if not confirmed:
        await gate.notify_progress(1, 1, "已取消。")
        return FetchResult(
            run_id=run_id,
            refetched_stages=(),
            total_stages_checked=len(_STAGE_FOLDERS),
        )

    ctx = _build_context(run_id, run_dir, settings, gate, db, script)

    # Separate upload-only vs needs-refetch
    upload_only = set(report.local_only_stages)
    needs_refetch = [s for s in report.missing_stages if s not in upload_only]

    refetched: list[str] = []
    total = len(needs_refetch) + 1  # +1 for upload step
    step = 0

    stage_runners = {
        "voice": ("正在生成語音...", _run_voice),
        "visual": ("正在搜尋影片素材...", _run_visual),
        "subtitle": ("正在生成字幕...", _run_subtitle),
        "thumbnail": ("正在生成縮圖...", _run_thumbnail),
    }

    for stage in needs_refetch:
        if stage not in stage_runners:
            continue
        msg, runner_fn = stage_runners[stage]
        step += 1
        await gate.notify_progress(step, total, msg)
        await runner_fn(ctx, container)
        refetched.append(stage)

    # Upload everything (refetched + local-only) to Drive
    step += 1
    await gate.notify_progress(step, total, "正在上傳至 Google Drive...")
    drive_link = await _upload_new_files(ctx, container, db)

    all_handled = refetched + list(upload_only)
    await gate.notify_progress(
        step, total,
        f"完成！已補齊 {len(all_handled)} 個 pipeline steps",
    )

    return FetchResult(
        run_id=run_id,
        refetched_stages=tuple(all_handled),
        total_stages_checked=len(_STAGE_FOLDERS),
        drive_link=drive_link,
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _load_script(run_id: str, db: PipelineStateDB) -> Script | None:
    """Load script from DB."""
    script_json = db.get_script_json(run_id)
    if script_json:
        return Script.model_validate_json(script_json)
    return None


def _build_context(
    run_id: str,
    run_dir: Path,
    settings: Settings,
    gate: ApprovalGate,
    db: PipelineStateDB,
    script: Script,
) -> PipelineContext:
    """Build a PipelineContext with artifacts restored from checkpoints."""
    run_info = db.get_run(run_id)
    completed = set(run_info.completed_stages) if run_info else set()

    ctx = PipelineContext(
        settings=settings,
        run_id=run_id,
        run_dir=run_dir,
        gate=gate,
        completed_stages=completed,
        script=script,
    )

    if "voice" in completed:
        from content_farm.voice.schemas import VoiceArtifact

        data = db.get_checkpoint(run_id, "voice")
        if data:
            ctx.voice = VoiceArtifact.model_validate(data)

    if "visual" in completed:
        from content_farm.visual.schemas import VisualArtifact

        data = db.get_checkpoint(run_id, "visual")
        if data:
            ctx.visual = VisualArtifact.model_validate(data)

    return ctx


async def _run_voice(ctx: PipelineContext, container: ServiceContainer) -> None:
    from content_farm.pipeline.stages import run_voice_stage

    await run_voice_stage(ctx, container)


async def _run_visual(ctx: PipelineContext, container: ServiceContainer) -> None:
    from content_farm.pipeline.stages import run_visual_stage

    await run_visual_stage(ctx, container)


async def _run_subtitle(ctx: PipelineContext, container: ServiceContainer) -> None:
    from content_farm.pipeline.stages import run_subtitle_stage

    await run_subtitle_stage(ctx, container)


async def _run_thumbnail(ctx: PipelineContext, container: ServiceContainer) -> None:
    from content_farm.pipeline.stages import run_thumbnail_stage

    await run_thumbnail_stage(ctx, container)


async def _upload_new_files(
    ctx: PipelineContext,
    container: ServiceContainer,
    db: PipelineStateDB,
) -> str:
    """Upload newly generated files to the existing Drive folder."""
    drive_link = db.get_checkpoint(ctx.run_id, "drive") or ""

    if not drive_link or not container.has_drive_credentials():
        return f"file://{ctx.run_dir}"

    folder_id = extract_folder_id(drive_link)
    if not folder_id:
        logger.warning("Could not parse folder ID from drive link: %s", drive_link)
        return drive_link

    uploader = container.create_drive_uploader()
    if uploader is None:
        return drive_link

    total_uploaded = 0
    for _stage, (folder_name, patterns) in _STAGE_FOLDERS.items():
        local_dir = ctx.run_dir / folder_name
        if not local_dir.is_dir():
            continue

        files: list[Path] = []
        for pat in patterns:
            files.extend(sorted(local_dir.glob(pat)))

        if not files:
            continue

        remote_folder_id = uploader.find_subfolder(folder_id, folder_name)
        if remote_folder_id:
            await uploader.upload_files(files, remote_folder_id)
            total_uploaded += len(files)

    logger.info("Uploaded %d files to Drive", total_uploaded)
    return drive_link
