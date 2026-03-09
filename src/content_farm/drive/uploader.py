"""Google Drive uploader — upload pipeline outputs to a shared folder."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _write_token_secure(token_path: Path, content: str) -> None:
    """Write token file with owner-only permissions (0o600)."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_FILE = "security/drive_token.json"


class DriveUploader:
    """Upload files to Google Drive using OAuth2 user credentials.

    Falls back to service account if OAuth2 token is unavailable.
    Requires: pip install google-api-python-client google-auth google-auth-oauthlib
    """

    def __init__(self, credentials_path: str, folder_id: str) -> None:
        self._credentials_path = credentials_path
        self._folder_id = folder_id
        self._service = None

    def _get_service(self):
        """Lazy-init the Drive API service."""
        if self._service is not None:
            return self._service

        from googleapiclient.discovery import build

        creds = self._load_credentials()
        self._service = build("drive", "v3", credentials=creds)
        return self._service

    def _load_credentials(self):
        """Load credentials: try OAuth2 token first, fall back to service account."""
        token_path = Path(_TOKEN_FILE)

        # Try OAuth2 user credentials (avoids service account quota issue)
        if token_path.exists():
            from google.oauth2.credentials import Credentials

            creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
            if creds.valid:
                return creds
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request

                creds.refresh(Request())
                _write_token_secure(token_path, creds.to_json())
                return creds

        # Fall back to service account
        creds_path = Path(self._credentials_path)
        if not creds_path.exists():
            raise FileNotFoundError(
                f"No credentials found: {creds_path.name}"
            )

        creds_data = json.loads(creds_path.read_text(encoding="utf-8"))

        if creds_data.get("type") == "service_account":
            from google.oauth2 import service_account

            return service_account.Credentials.from_service_account_file(
                str(creds_path), scopes=_SCOPES,
            )

        # Assume it's an OAuth2 client secret — run auth flow
        return self._run_oauth_flow(creds_path, token_path)

    def _run_oauth_flow(self, client_secret_path: Path, token_path: Path):
        """Run OAuth2 flow for user credentials (one-time browser auth)."""
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path), _SCOPES,
        )
        creds = flow.run_local_server(port=0)
        _write_token_secure(token_path, creds.to_json())
        logger.info("OAuth2 token saved to %s", token_path)
        return creds

    async def upload_folder(
        self,
        local_dir: Path,
        folder_name: str,
    ) -> str:
        """Upload all files in local_dir to a new subfolder in Drive.

        Returns the shareable link to the created subfolder.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._upload_folder_sync, local_dir, folder_name,
        )

    def _upload_folder_sync(self, local_dir: Path, folder_name: str) -> str:
        """Synchronous folder upload."""
        service = self._get_service()

        # Create subfolder
        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [self._folder_id],
        }
        folder = service.files().create(
            body=folder_metadata, fields="id, webViewLink",
        ).execute()
        subfolder_id = folder["id"]
        folder_link = folder.get("webViewLink", "")

        logger.info("Created Drive folder: %s (%s)", folder_name, subfolder_id)

        # Upload all files in local_dir
        for file_path in sorted(local_dir.iterdir()):
            if file_path.is_file():
                self._upload_single_file(service, file_path, subfolder_id)
            elif file_path.is_dir():
                self._upload_subdir(service, file_path, subfolder_id)

        # Make folder accessible via link
        service.permissions().create(
            fileId=subfolder_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        logger.info("Drive upload complete: %s", folder_link)
        return folder_link

    def _upload_single_file(self, service, file_path: Path, parent_id: str) -> str:
        """Upload a single file to Drive, return file ID."""
        from googleapiclient.http import MediaFileUpload

        mime_type = _guess_mime_type(file_path)
        media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)

        file_metadata = {
            "name": file_path.name,
            "parents": [parent_id],
        }
        uploaded = service.files().create(
            body=file_metadata, media_body=media, fields="id",
        ).execute()

        logger.info("Uploaded: %s (%s)", file_path.name, uploaded["id"])
        return uploaded["id"]

    def _upload_subdir(self, service, dir_path: Path, parent_id: str) -> None:
        """Upload a subdirectory and its files."""
        folder_metadata = {
            "name": dir_path.name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = service.files().create(
            body=folder_metadata, fields="id",
        ).execute()
        sub_id = folder["id"]

        for file_path in sorted(dir_path.iterdir()):
            if file_path.is_file():
                self._upload_single_file(service, file_path, sub_id)


def create_drive_uploader(
    credentials_path: str,
    folder_id: str,
) -> DriveUploader | None:
    """Create a DriveUploader if credentials are configured."""
    if not credentials_path or not folder_id:
        logger.info("Google Drive not configured — skipping upload")
        return None
    return DriveUploader(credentials_path=credentials_path, folder_id=folder_id)


def _guess_mime_type(path: Path) -> str:
    """Guess MIME type from file extension."""
    mime_map = {
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".srt": "text/plain",
        ".ass": "text/plain",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    return mime_map.get(path.suffix.lower(), "application/octet-stream")
