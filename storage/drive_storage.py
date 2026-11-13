"""Optional Google Drive archive for uploaded source documents and project evidence."""
from __future__ import annotations
import io
from typing import Any


def upload_file_to_drive(service_account_info: dict[str, Any], folder_id: str, filename: str, mime_type: str, content: bytes) -> dict[str, str]:
    if not folder_id:
        raise ValueError("DRIVE_FOLDER_ID belum diatur.")
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    scopes = ["https://www.googleapis.com/auth/drive.file"]
    info = dict(service_account_info)
    if isinstance(info.get("private_key"), str): info["private_key"] = info["private_key"].replace("\\n", "\n")
    credentials = Credentials.from_service_account_info(info, scopes=scopes)
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type or "application/octet-stream", resumable=True)
    created = service.files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=media,
        fields="id,name,webViewLink,mimeType",
        supportsAllDrives=True,
    ).execute()
    return {"file_id": created.get("id", ""), "name": created.get("name", filename), "web_view_link": created.get("webViewLink", ""), "mime_type": created.get("mimeType", mime_type)}
