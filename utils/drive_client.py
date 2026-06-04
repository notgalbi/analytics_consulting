"""
drive_client.py — Google Drive API wrapper using service account auth.

Setup:
  1. Create a Google Cloud project, enable the Drive API.
  2. Create a service account, download the JSON key.
  3. Set GOOGLE_SERVICE_ACCOUNT_JSON env var to the JSON string (not file path).
     On Streamlit Cloud, add it to st.secrets instead.
  4. Clients share their Drive folder with the service account email.

Public API:
    is_configured()                                              → bool
    get_service()                                                → Resource | None
    folder_id_from_url(url)                                      → str | None
    list_files(service, folder_id, mime_filter)                  → list[dict]
    download_bytes(service, file_id)                             → bytes
    upload_bytes(service, folder_id, name, data, mime_type)      → str
    get_or_create_folder(service, parent_id, name)               → str
"""
from __future__ import annotations

import io
import json
import os
import re
from typing import Optional

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_FOLDER_MIME = "application/vnd.google-apps.folder"


def is_configured() -> bool:
    """Return True if service account credentials are available."""
    return _get_sa_json() is not None


def get_service():
    """
    Authenticate with Google Drive via service account.
    Returns a Drive v3 Resource, or raises RuntimeError if auth fails.
    """
    sa_json = _get_sa_json()
    if not sa_json:
        raise RuntimeError(
            "Google Drive is not configured. "
            "Set GOOGLE_SERVICE_ACCOUNT_JSON in your .env or Streamlit secrets."
        )
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_service_account_info(sa_json, scopes=_SCOPES)
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except ImportError:
        raise RuntimeError(
            "Google API packages are not installed. "
            "Run: pip install google-auth google-api-python-client google-auth-httplib2"
        )
    except Exception as e:
        raise RuntimeError(f"Drive authentication failed: {e}") from e


def folder_id_from_url(url: str) -> Optional[str]:
    """
    Extract folder ID from a Google Drive URL.
    Handles /folders/<id>, open?id=<id>, and bare IDs.
    Returns None if no valid ID found.
    """
    if not url:
        return None
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    # Bare ID (33-char alphanumeric)
    stripped = url.strip()
    if re.fullmatch(r"[a-zA-Z0-9_-]{10,}", stripped):
        return stripped
    return None


def list_files(
    service,
    folder_id: str,
    mime_filter: Optional[str] = None,
) -> list[dict]:
    """
    List non-trashed files in a Drive folder, newest first.
    Returns [{id, name, mimeType, modifiedTime, size}].
    """
    q = f"'{folder_id}' in parents and trashed = false"
    if mime_filter:
        q += f" and mimeType = '{mime_filter}'"

    results: list[dict] = []
    page_token = None
    while True:
        resp = (
            service.files()
            .list(
                q=q,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                pageSize=100,
                pageToken=page_token,
            )
            .execute()
        )
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return sorted(results, key=lambda f: f.get("modifiedTime", ""), reverse=True)


def download_bytes(service, file_id: str) -> bytes:
    """Download a Drive file and return raw bytes."""
    from googleapiclient.http import MediaIoBaseDownload

    buf = io.BytesIO()
    request = service.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def upload_bytes(
    service,
    folder_id: str,
    name: str,
    data: bytes,
    mime_type: str = "application/octet-stream",
) -> str:
    """
    Upload bytes to a Drive folder.
    Overwrites any existing file with the same name in the folder.
    Returns the file ID.
    """
    from googleapiclient.http import MediaIoBaseUpload

    existing = list_files(service, folder_id)
    existing_id = next((f["id"] for f in existing if f["name"] == name), None)
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=False)

    if existing_id:
        file = service.files().update(fileId=existing_id, media_body=media).execute()
    else:
        file_meta = {"name": name, "parents": [folder_id]}
        file = service.files().create(body=file_meta, media_body=media, fields="id").execute()

    return file["id"]


def get_or_create_folder(service, parent_id: str, name: str) -> str:
    """Find or create a sub-folder named `name` inside `parent_id`. Returns folder ID."""
    q = (
        f"'{parent_id}' in parents "
        f"and name = '{name}' "
        f"and mimeType = '{_FOLDER_MIME}' "
        f"and trashed = false"
    )
    resp = service.files().list(q=q, fields="files(id)").execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]

    meta = {"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]}
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


# ── Internal ──────────────────────────────────────────────────────────────────

def _get_sa_json() -> Optional[dict]:
    """Load service account credentials from env var or Streamlit secrets."""
    # Env var (local dev) — full JSON string
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    # Streamlit secrets — prefer TOML table [gcp_service_account]
    try:
        import streamlit as st
        sa = st.secrets.get("gcp_service_account")
        if sa:
            return dict(sa)
        # Fall back to JSON string value
        secret = st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if secret:
            if isinstance(secret, str):
                return json.loads(secret)
            if isinstance(secret, dict):
                return dict(secret)
    except Exception:
        pass

    return None
