from __future__ import annotations

import os
import json
import requests
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/blogger"]
TOKEN_PATH = Path(__file__).resolve().parent / "token_blogger.json"
SECRET_PATH = Path(__file__).resolve().parent / "client_secret.json"


def _get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(SECRET_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _markdown_table_to_html(text: str) -> str:
    """마크다운 표를 HTML 표로 변환."""
    lines = text.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "|" in line and i + 1 < len(lines) and re.match(r"^\|[-| :]+\|", lines[i + 1].strip()):
            # 표 시작
            html = '<table style="width:100%;border-collapse:collapse;margin:16px 0;">'
            # 헤더
            headers = [h.strip() for h in line.strip().strip("|").split("|")]
            html += "<thead><tr>"
            for h in headers:
                html += f'<th style="border:1px solid #ddd;padding:8px;background:#f5f5f5;">{h}</th>'
            html += "</tr></thead><tbody>"
            i += 2  # 헤더 + 구분선 넘기기
            while i < len(lines) and "|" in lines[i]:
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                html += "<tr>"
                for c in cells:
                    html += f'<td style="border:1px solid #ddd;padding:8px;">{c}</td>'
                html += "</tr>"
                i += 1
            html += "</tbody></table>"
            result.append(html)
        else:
            result.append(line)
            i += 1
    return "\n".join(result)


import re


def _markdown_to_html(text: str) -> str:
    """기본 마크다운 → HTML 변환."""
    lines = text.split("\n")
    result = []
    for line in lines:
        # 제목
        if line.startswith("### "):
            line = f"<h3>{line[4:]}</h3>"
        elif line.startswith("## "):
            line = f"<h2>{line[3:]}</h2>"
        elif line.startswith("# "):
            line = f"<h1>{line[2:]}</h1>"
        # 리스트
        elif line.startswith("- ") or line.startswith("* "):
            line = f"<li>{line[2:]}</li>"
        elif re.match(r"^\d+\) ", line):
            line = f"<li>{line[line.index(')')+2:]}</li>"
        # 굵게
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        # 빈줄 → <br>
        if line.strip() == "":
            line = "<br>"
        result.append(line)
    return "\n".join(result)


def _fetch_pixabay_images(keyword: str, count: int = 5) -> list[str]:
    """Pixabay에서 키워드 관련 이미지 URL 반환."""
    api_key = os.getenv("PIXABAY_API_KEY", "")
    if not api_key:
        return []
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params={"key": api_key, "q": keyword, "image_type": "photo", "per_page": count, "lang": "ko"},
            timeout=8,
        )
        hits = r.json().get("hits", [])
        return [h["webformatURL"] for h in hits[:count]]
    except Exception:
        return []


def _insert_images_into_html(body: str, image_urls: list[str]) -> str:
    """본문을 3등분해서 이미지 삽입."""
    if not image_urls:
        return body
    lines = body.split("<br>")
    chunk = max(1, len(lines) // (len(image_urls) + 1))
    result = []
    img_idx = 0
    for i, line in enumerate(lines):
        result.append(line)
        if img_idx < len(image_urls) and (i + 1) % chunk == 0:
            img_tag = f'<br><img src="{image_urls[img_idx]}" style="width:100%;max-width:600px;margin:16px 0;border-radius:8px;" /><br>'
            result.append(img_tag)
            img_idx += 1
    return "<br>".join(result)


def post_to_blogger(blog_id: str, title: str, content: str, labels: list[str] | None = None, image_keyword: str = "") -> dict:
    """Blogger에 글 발행. 성공 시 응답 dict 반환."""
    creds = _get_credentials()
    service = build("blogger", "v3", credentials=creds)

    # 마크다운 → HTML 변환
    content = _markdown_to_html(content)
    content = _markdown_table_to_html(content)

    # 이미지 삽입
    if image_keyword:
        image_urls = _fetch_pixabay_images(image_keyword, count=5)
        content = _insert_images_into_html(content, image_urls)

    body_data: dict = {
        "title": title,
        "content": content,
    }
    if labels:
        body_data["labels"] = labels

    result = service.posts().insert(blogId=blog_id, body=body_data, isDraft=False).execute()
    return result
