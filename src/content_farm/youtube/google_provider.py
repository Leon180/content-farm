"""Google YouTube Data API v3 provider — OAuth2, resumable upload."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from content_farm.youtube.schemas import UploadSettings

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleProvider:
    """YouTube uploader using Google Data API v3 with OAuth2."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._service: object | None = None

    def _build_credentials(self) -> Credentials:
        """Reconstruct OAuth2 credentials from stored components."""
        creds = Credentials(
            token=None,
            refresh_token=self._refresh_token,
            token_uri=_TOKEN_URI,
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        creds.refresh(Request())
        return creds

    def _ensure_service(self) -> object:
        """Lazily build the YouTube API service."""
        if self._service is None:
            creds = self._build_credentials()
            self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def get_authorized_channel(self) -> dict[str, str]:
        """Return ``{"id", "title"}`` of the channel this token acts for (channels.list mine)."""
        service = self._ensure_service()
        response = service.channels().list(part="snippet", mine=True).execute()  # type: ignore[union-attr]
        items = response.get("items", [])
        if not items:
            raise RuntimeError("Token is authorized but owns no YouTube channel")
        return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}

    def get_videos(self, video_ids: list[str]) -> dict[str, dict]:
        """Read back snippet+status for up to 50 videos (videos.list, 1 quota unit)."""
        service = self._ensure_service()
        response = service.videos().list(  # type: ignore[union-attr]
            part="snippet,status", id=",".join(video_ids), maxResults=50,
        ).execute()
        return {item["id"]: item for item in response.get("items", [])}

    def update_snippet(self, video_id: str, changes: dict) -> dict:
        """videos.update (50 units): overlay ``changes`` on the live snippet, keep all other fields.

        videos.update replaces the whole snippet, so the current one is read first.
        Returns the snippet that was written.
        """
        current = self.get_videos([video_id]).get(video_id)
        if current is None:
            raise RuntimeError(f"Video {video_id} not found")
        merged = {**current["snippet"], **changes}
        service = self._ensure_service()
        service.videos().update(  # type: ignore[union-attr]
            part="snippet", body={"id": video_id, "snippet": merged},
        ).execute()
        return merged

    async def upload_video(
        self,
        *,
        video_path: Path,
        title: str,
        description: str,
        tags: tuple[str, ...] = (),
        settings: UploadSettings | None = None,
    ) -> str:
        """Upload video via resumable upload. Returns video ID."""
        s = settings or UploadSettings()
        return await asyncio.to_thread(
            self._upload_video_sync, video_path, title, description, tags, s,
        )

    def _upload_video_sync(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: tuple[str, ...],
        settings: UploadSettings,
    ) -> str:
        """Synchronous resumable upload with progress logging."""
        service = self._ensure_service()

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": list(tags),
                "categoryId": settings.category_id,
                "defaultLanguage": settings.default_language,
                "defaultAudioLanguage": settings.default_language,
            },
            "status": {
                # publishAt requires a private video; it flips to public at that time.
                "privacyStatus": "private" if settings.publish_at else settings.privacy_status,
                # status.madeForKids is read-only; selfDeclaredMadeForKids is the writable field.
                "selfDeclaredMadeForKids": settings.made_for_kids,
            },
        }
        if settings.publish_at:
            body["status"]["publishAt"] = settings.publish_at
        if settings.contains_synthetic_media is not None:
            body["status"]["containsSyntheticMedia"] = settings.contains_synthetic_media

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=settings.chunk_size_bytes,
        )

        request = service.videos().insert(  # type: ignore[union-attr]
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info("Upload progress: %d%%", pct)

        video_id: str = response["id"]
        logger.info(
            "Video uploaded: id=%s title=%r privacy=%s",
            video_id, title, settings.privacy_status,
        )
        return video_id

    async def set_thumbnail(
        self,
        *,
        video_id: str,
        thumbnail_path: Path,
    ) -> None:
        """Set custom thumbnail for an uploaded video."""
        await asyncio.to_thread(self._set_thumbnail_sync, video_id, thumbnail_path)

    def _set_thumbnail_sync(self, video_id: str, thumbnail_path: Path) -> None:
        service = self._ensure_service()
        media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
        service.thumbnails().set(  # type: ignore[union-attr]
            videoId=video_id,
            media_body=media,
        ).execute()
        logger.info("Thumbnail set for video %s", video_id)

    async def set_captions(
        self,
        *,
        video_id: str,
        caption_path: Path,
        language: str = "zh-TW",
    ) -> None:
        """Upload SRT captions for an uploaded video."""
        await asyncio.to_thread(
            self._set_captions_sync, video_id, caption_path, language,
        )

    def _set_captions_sync(
        self, video_id: str, caption_path: Path, language: str,
    ) -> None:
        service = self._ensure_service()
        body = {
            "snippet": {
                "videoId": video_id,
                "language": language,
                "name": f"{language} captions",
                "isDraft": False,
            },
        }
        media = MediaFileUpload(str(caption_path), mimetype="application/octet-stream")
        service.captions().insert(  # type: ignore[union-attr]
            part="snippet",
            body=body,
            media_body=media,
        ).execute()
        logger.info("Captions uploaded for video %s (lang=%s)", video_id, language)
