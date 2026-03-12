"""Google Drive uploader — upload pipeline outputs to a shared folder."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _write_token_secure(token_path: Path, content: str) -> None:
    """Write token file with owner-only permissions (0o600)."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_DEFAULT_TOKEN_FILE = "security/drive_token.json"


class DriveUploader:
    """Upload files to Google Drive using OAuth2 user credentials.

    Falls back to service account if OAuth2 token is unavailable.
    Requires: pip install google-api-python-client google-auth google-auth-oauthlib
    """

    def __init__(
        self,
        credentials_path: str,
        folder_id: str,
        project_root: str = ".",
    ) -> None:
        self._credentials_path = credentials_path
        self._folder_id = folder_id
        self._project_root = Path(project_root)
        self._service = None

    @property
    def _token_path(self) -> Path:
        """Resolve token path relative to project root."""
        return self._project_root / _DEFAULT_TOKEN_FILE

    def _get_service(self) -> Any:
        """Lazy-init the Drive API service."""
        if self._service is not None:
            return self._service

        from googleapiclient.discovery import build  # type: ignore[import-untyped]

        creds = self._load_credentials()
        self._service = build("drive", "v3", credentials=creds)
        return self._service

    def _load_credentials(self) -> Any:
        """Load credentials: try OAuth2 token first, fall back to service account."""
        token_path = self._token_path

        # Try OAuth2 user credentials (avoids service account quota issue)
        if token_path.exists():
            from google.oauth2.credentials import Credentials  # type: ignore[import-untyped]

            creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)  # type: ignore[no-untyped-call]
            if creds.valid:
                return creds
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request  # type: ignore[import-untyped]

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
            from google.oauth2 import service_account  # type: ignore[import-untyped]

            return service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
                str(creds_path), scopes=_SCOPES,
            )

        # Assume it's an OAuth2 client secret — run auth flow
        return self._run_oauth_flow(creds_path, token_path)

    def _run_oauth_flow(self, client_secret_path: Path, token_path: Path) -> Any:
        """Run OAuth2 flow for user credentials (one-time browser auth)."""
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

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
        return str(folder_link)

    def _upload_single_file(self, service: Any, file_path: Path, parent_id: str) -> str:
        """Upload a single file to Drive, return file ID."""
        from googleapiclient.http import MediaFileUpload  # type: ignore[import-untyped]

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
        return str(uploaded["id"])

    # ------------------------------------------------------------------
    # Listing / querying
    # ------------------------------------------------------------------

    def list_files(self, folder_id: str) -> list[dict[str, str]]:
        """List files in a Drive folder.

        Returns list of ``{id, name, mimeType}`` dicts.
        """
        service = self._get_service()
        results: list[dict[str, str]] = []
        page_token: str | None = None

        while True:
            resp = service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
                pageSize=100,
            ).execute()
            results.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return results

    def find_subfolder(self, parent_id: str, name: str) -> str | None:
        """Find a subfolder by name within *parent_id*.

        Returns the folder ID if found, ``None`` otherwise.
        """
        service = self._get_service()
        q = (
            f"'{parent_id}' in parents"
            f" and name = '{name}'"
            f" and mimeType = 'application/vnd.google-apps.folder'"
            f" and trashed = false"
        )
        resp = service.files().list(q=q, fields="files(id)").execute()
        files = resp.get("files", [])
        return files[0]["id"] if files else None

    def create_subfolder(self, parent_id: str, name: str) -> str:
        """Create a new subfolder and return its ID."""
        service = self._get_service()
        folder_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = service.files().create(
            body=folder_metadata, fields="id",
        ).execute()
        return str(folder["id"])

    async def upload_files(
        self,
        files: list[Path],
        folder_id: str,
    ) -> list[str]:
        """Upload multiple files to an *existing* Drive folder.

        Returns a list of created file IDs.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._upload_files_sync, files, folder_id,
        )

    def _upload_files_sync(
        self, files: list[Path], folder_id: str,
    ) -> list[str]:
        service = self._get_service()
        ids: list[str] = []
        for fp in files:
            if fp.is_file():
                ids.append(self._upload_single_file(service, fp, folder_id))
        return ids

    # ------------------------------------------------------------------
    # Internal upload helpers
    # ------------------------------------------------------------------

    def _upload_subdir(self, service: Any, dir_path: Path, parent_id: str) -> None:
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
    project_root: str = ".",
) -> DriveUploader | None:
    """Create a DriveUploader if credentials are configured."""
    if not credentials_path or not folder_id:
        logger.info("Google Drive not configured — skipping upload")
        return None
    return DriveUploader(
        credentials_path=credentials_path,
        folder_id=folder_id,
        project_root=project_root,
    )


def extract_folder_id(link: str) -> str | None:
    """Extract folder ID from a Google Drive URL.

    Supports:
    - ``https://drive.google.com/drive/folders/FOLDER_ID``
    - ``https://drive.google.com/drive/folders/FOLDER_ID?...``

    Returns ``None`` if the link is not a recognised Drive folder URL.
    """
    import re

    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", link)
    return m.group(1) if m else None


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
