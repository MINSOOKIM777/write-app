from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


PrivacyStatus = Literal["private", "unlisted", "public"]


@dataclass(frozen=True)
class UploadRequest:
    video_path: Path
    title: str
    description: str
    tags: list[str]
    privacy_status: PrivacyStatus = "unlisted"
    category_id: str = "22"  # People & Blogs (safe default for general shorts)
    made_for_kids: bool = False


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_client_secret(base_dir: Path, profile: str, client_secret_json_bytes: bytes) -> Path:
    ensure_dir(base_dir)
    dst = base_dir / f"client_secret__{profile}.json"
    dst.write_bytes(client_secret_json_bytes)
    return dst


def token_path(base_dir: Path, profile: str) -> Path:
    ensure_dir(base_dir)
    return base_dir / f"token__{profile}.json"


def _load_credentials(client_secret_path: Path, token_file: Path) -> Credentials:
    creds: Credentials | None = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if creds and creds.valid:
        return creds

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_youtube_service(client_secret_path: Path, token_file: Path):
    creds = _load_credentials(client_secret_path=client_secret_path, token_file=token_file)
    return build("youtube", "v3", credentials=creds)


def list_my_channels(client_secret_path: Path, token_file: Path) -> list[dict]:
    yt = get_youtube_service(client_secret_path, token_file)
    resp = yt.channels().list(part="snippet", mine=True).execute()
    return resp.get("items", [])


def upload_video(
    client_secret_path: Path,
    token_file: Path,
    req: UploadRequest,
) -> dict:
    yt = get_youtube_service(client_secret_path, token_file)

    body = {
        "snippet": {
            "title": req.title[:100],
            "description": req.description,
            "tags": [t for t in req.tags if t][:500],
            "categoryId": req.category_id,
        },
        "status": {
            "privacyStatus": req.privacy_status,
            "selfDeclaredMadeForKids": bool(req.made_for_kids),
        },
    }

    media = MediaFileUpload(str(req.video_path), chunksize=-1, resumable=True)

    try:
        insert = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            _status, response = insert.next_chunk()
        return response
    except HttpError as e:
        raise RuntimeError(f"YouTube upload failed: {e}") from e


def parse_hashtags_to_tags(hashtags_line: str) -> list[str]:
    # "#a #b #c" -> ["a", "b", "c"]
    raw = hashtags_line.replace("\n", " ").split()
    tags: list[str] = []
    for w in raw:
        w = w.strip()
        if not w:
            continue
        if w.startswith("#"):
            w = w[1:]
        w = w.strip()
        if not w:
            continue
        if w not in tags:
            tags.append(w)
    return tags[:40]  # YouTube tags practical limit

