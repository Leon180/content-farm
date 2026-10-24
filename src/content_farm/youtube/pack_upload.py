"""Plan and execute uploads of an upload pack (always private, quota-checked)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_farm.youtube.channel_tokens import resolve_refresh_token, resolve_token_source
from content_farm.youtube.pack import PackItem
from content_farm.youtube.quota import (
    CHANNELS_LIST_COST,
    FAILED_CALL_COST,
    THUMBNAILS_SET_COST,
    VIDEOS_INSERT_COST,
    QuotaLedger,
    pacific_day,
    upload_cost,
)

RESULT_FILENAME = "upload_result.json"

ProviderFactory = Callable[[str, str], Any]  # (channel, refresh_token) -> provider


def studio_url(video_id: str) -> str:
    return f"https://studio.youtube.com/video/{video_id}/edit"


def describe_item(item: PackItem, environ: Mapping[str, str]) -> str:
    """Multi-line dry-run description of exactly what would be sent."""
    source = resolve_token_source(item.channel, environ)
    synthetic = {True: "true", False: "false", None: "UNSET"}[item.contains_synthetic_media]
    lines = [
        f"[{item.folder.name}]  {'Short' if item.is_short else '長片'}"
        f"{'' if item.listed_in_index else '  (未列入 INDEX)'}",
        f"  channel    : {item.channel}  (token: {source or 'MISSING'})",
        f"  title      : {item.title}",
        f"  description: {len(item.description)} chars / {item.description_bytes} bytes",
        f"  tags       : {', '.join(item.tags)}",
        f"  category   : {item.category_id}",
        f"  thumbnail  : {item.thumbnail_path.name if item.thumbnail_path else '(none)'}",
        f"  containsSyntheticMedia: {synthetic}",
        "  privacyStatus: private",
        f"  quota      : {upload_cost(has_thumbnail=item.thumbnail_path is not None)} units",
    ]
    if item.pinned_comment_path:
        lines.append(f"  reminder   : 公開後手動貼置頂留言 ← {item.pinned_comment_path.name}")
    tail = [ln for ln in item.description.splitlines() if ln.strip()][-2:]
    lines.extend(f"  desc tail  : {ln[:80]}" for ln in tail)
    lines.extend(f"  SANITIZED  : {n}" for n in item.notes)
    lines.extend(f"  PROBLEM    : {p}" for p in item.problems())
    return "\n".join(lines)


def summarize_quota(items: list[PackItem], ledger: QuotaLedger, day: str) -> str:
    total = sum(upload_cost(has_thumbnail=i.thumbnail_path is not None) for i in items)
    return (
        f"quota day {day} (Pacific): used {ledger.used(day)} / {ledger.limit}, "
        f"remaining {ledger.remaining(day)}; this run needs {total} "
        f"({VIDEOS_INSERT_COST}/video + {THUMBNAILS_SET_COST}/thumbnail + "
        f"{CHANNELS_LIST_COST}/channel check) -> "
        f"{'fits' if total <= ledger.remaining(day) else 'will stop partway'}"
    )


@dataclass(frozen=True)
class UploadOutcome:
    folder: str
    status: str  # "uploaded" | "skipped-existing" | "skipped-problems" | "stopped-quota" | "failed"
    detail: str = ""


async def upload_one(
    item: PackItem,
    provider: Any,
    *,
    channel_info: dict[str, str],
    now: datetime,
) -> dict[str, Any]:
    """Insert the video (private) and set the thumbnail. Returns the result record."""
    video_id = await provider.upload_video(
        video_path=item.video_path,
        title=item.title,
        description=item.description,
        tags=item.tags,
        settings=item.settings(),
    )
    record: dict[str, Any] = {
        "videoId": video_id,
        "studioUrl": studio_url(video_id),
        "channel": item.channel,
        "channelTitle": channel_info["title"],
        "channelId": channel_info["id"],
        "title": item.title,
        "privacyStatus": "private",
        "containsSyntheticMedia": item.contains_synthetic_media,
        "uploadedAt": now.isoformat(),
        "thumbnailSet": False,
        "pinnedCommentFile": str(item.pinned_comment_path) if item.pinned_comment_path else None,
    }
    if item.thumbnail_path:
        try:
            await provider.set_thumbnail(video_id=video_id, thumbnail_path=item.thumbnail_path)
            record["thumbnailSet"] = True
        except Exception as err:  # video is already up; keep its id, report the thumbnail failure
            record["thumbnailError"] = f"{type(err).__name__}: {err}"
    return record


async def run_upload(
    items: list[PackItem],
    *,
    environ: Mapping[str, str],
    ledger: QuotaLedger,
    provider_factory: ProviderFactory,
    log: Callable[[str], None] = print,
    force: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> list[UploadOutcome]:
    """Upload items in order; stop at the first one the remaining quota can't cover."""
    outcomes: list[UploadOutcome] = []
    providers: dict[str, Any] = {}
    day = pacific_day()

    for index, item in enumerate(items):
        result_path = item.folder / RESULT_FILENAME
        if result_path.is_file() and not force:
            outcomes.append(UploadOutcome(item.folder.name, "skipped-existing"))
            log(f"skip {item.folder.name}: {RESULT_FILENAME} exists (use --force to re-upload)")
            continue
        problems = item.problems()
        if problems:
            outcomes.append(UploadOutcome(item.folder.name, "skipped-problems", "; ".join(problems)))
            log(f"skip {item.folder.name}: {'; '.join(problems)}")
            continue
        cost = upload_cost(has_thumbnail=item.thumbnail_path is not None)
        if not ledger.can_afford(day, cost):
            log(
                f"STOP: {item.folder.name} needs {cost} units, only {ledger.remaining(day)} left "
                f"today ({day} Pacific)."
            )
            outcomes.extend(
                UploadOutcome(rest.folder.name, "stopped-quota") for rest in items[index:]
            )
            break
        try:
            if item.channel not in providers:
                token = resolve_refresh_token(item.channel, environ)
                providers[item.channel] = provider_factory(item.channel, token)
            provider = providers[item.channel]
            info = provider.get_authorized_channel()
            ledger = ledger.spend(day, CHANNELS_LIST_COST)
            log(f"{item.folder.name}: uploading as channel '{info['title']}' ...")
            try:
                record = await upload_one(item, provider, channel_info=info, now=clock())
            except Exception:
                # Count only what actually succeeded; a rejected call is booked as 1 unit.
                ledger = ledger.spend(day, FAILED_CALL_COST)
                raise
            ledger = ledger.spend(day, cost - CHANNELS_LIST_COST)
            result_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except Exception as err:
            outcomes.append(UploadOutcome(item.folder.name, "failed", f"{type(err).__name__}: {err}"))
            log(f"FAILED {item.folder.name}: {type(err).__name__}: {err}")
            continue
        outcomes.append(UploadOutcome(item.folder.name, "uploaded", record["studioUrl"]))
        log(f"done {item.folder.name}: {record['studioUrl']}")
        if item.pinned_comment_path:
            log(f"  reminder: 公開後手動貼置頂留言 ← {item.pinned_comment_path}")
    return outcomes
