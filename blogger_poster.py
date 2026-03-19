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
    import streamlit as st

    # Streamlit Cloud: Secrets에서 읽기
    try:
        token_str = st.secrets.get("BLOGGER_TOKEN", "")
        secret_str = st.secrets.get("BLOGGER_CLIENT_SECRET", "")
    except Exception:
        token_str = ""
        secret_str = ""

    # 로컬: 파일에서 읽기
    if not token_str and TOKEN_PATH.exists():
        token_str = TOKEN_PATH.read_text(encoding="utf-8")
    if not secret_str and SECRET_PATH.exists():
        secret_str = SECRET_PATH.read_text(encoding="utf-8")

    creds = None
    if token_str:
        creds = Credentials.from_authorized_user_info(json.loads(token_str), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        else:
            if not secret_str:
                raise RuntimeError("client_secret.json 또는 BLOGGER_CLIENT_SECRET Secrets가 필요합니다.")
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(secret_str)
                tmp_path = f.name
            flow = InstalledAppFlow.from_client_secrets_file(tmp_path, SCOPES)
            creds = flow.run_local_server(port=0)
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _is_table_separator(line: str) -> bool:
    s = line.strip()
    return bool(s) and all(c in "|-: " for c in s) and "-" in s and "|" in s


def _markdown_table_to_html(text: str) -> str:
    """마크다운 표를 HTML 표로 변환. 구분선 없는 표도 처리."""
    lines = text.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # 표 시작 감지: 줄이 |로 시작
        if line.strip().startswith("|"):
            # 연속된 | 줄 수집
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1

            # 구분선 제거
            rows = [l for l in table_lines if not _is_table_separator(l)]
            if not rows:
                result.extend(table_lines)
                continue

            html = '<table style="width:100%;border-collapse:collapse;margin:16px 0;">'
            # 첫 줄 = 헤더
            headers = [h.strip() for h in rows[0].strip().strip("|").split("|") if h.strip()]
            html += "<thead><tr>"
            for h in headers:
                html += f'<th style="border:1px solid #ddd;padding:8px;background:#f5f5f5;text-align:left;">{h}</th>'
            html += "</tr></thead><tbody>"
            for row in rows[1:]:
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                html += "<tr>"
                for c in cells:
                    html += f'<td style="border:1px solid #ddd;padding:8px;">{c}</td>'
                html += "</tr>"
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
    in_ol = False
    in_ul = False
    ol_counter = 0

    for line in lines:
        # 번호 리스트 (1. 또는 1))
        if re.match(r"^\d+[\.\)] ", line):
            if not in_ol:
                result.append('<ol style="line-height:2;padding-left:20px;">')
                in_ol = True
                ol_counter = 0
            ol_counter += 1
            content = re.sub(r"^\d+[\.\)] ", "", line)
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
            result.append(f'<li value="{ol_counter}">{content}</li>')
            continue
        # 💡 팁 줄은 ol 안에서 들여쓰기로 표시 (ol 닫지 않음)
        elif in_ol and (line.startswith("💡") or line.startswith("- ")):
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            result.append(f'<li style="list-style:none;color:#666;font-size:0.9em;margin-left:-10px;">{content}</li>')
            continue
        else:
            if in_ol and line.strip() != "":
                result.append("</ol>")
                in_ol = False
                ol_counter = 0

        # 불릿 리스트
        if line.startswith("- ") or line.startswith("* "):
            if not in_ul:
                result.append('<ul style="line-height:2;padding-left:20px;">')
                in_ul = True
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line[2:])
            result.append(f"<li>{content}</li>")
            continue
        else:
            if in_ul:
                result.append("</ul>")
                in_ul = False

        # 제목
        if line.startswith("### "):
            line = f'<h3 style="margin-top:24px;">{line[4:]}</h3>'
        elif line.startswith("## "):
            line = f'<h2 style="margin-top:32px;border-bottom:2px solid #eee;padding-bottom:8px;">{line[3:]}</h2>'
        elif line.startswith("# "):
            line = f"<h1>{line[2:]}</h1>"
        # 굵게
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        # 빈줄 → 문단 간격
        if line.strip() == "":
            line = '<p style="margin:12px 0;"></p>'
        elif line.strip().startswith("|"):
            pass  # 표는 건드리지 않음
        elif not line.startswith("<"):
            line = f'<p style="line-height:1.9;margin:8px 0;">{line}</p>'
        result.append(line)

    if in_ol:
        result.append("</ol>")
    if in_ul:
        result.append("</ul>")

    return "\n".join(result)


def _get_secret(key: str) -> str:
    val = os.getenv(key, "")
    if not val:
        try:
            import streamlit as st
            val = st.secrets.get(key, "")
        except Exception:
            pass
    return val


def _translate_keyword(keyword: str) -> str:
    """한국어 키워드 → 영어 번역."""
    try:
        from groq import Groq as _Groq
        _key = _get_secret("GROQ_API_KEY")
        if _key:
            c = _Groq(api_key=_key)
            r = c.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": f"Translate this Korean food/dish to English for Pixabay image search. Give the most searchable English term (2-4 words). Examples: 김치찌개→kimchi stew, 불고기→Korean bulgogi beef, 장조림→braised soy beef, 멸치볶음→stir fried anchovies. Now translate: {keyword}"}],
                max_tokens=15,
            )
            return r.choices[0].message.content.strip().strip('"').split("\n")[0]
    except Exception:
        pass
    return keyword


def _fetch_ai_images(keyword: str, count: int = 5) -> list[str]:
    """Pixabay에서 음식 이미지 검색."""
    px_key = _get_secret("PIXABAY_API_KEY")
    if not px_key:
        return []
    en_kw = _translate_keyword(keyword)
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params={"key": px_key, "q": f"{en_kw} food dish", "image_type": "photo", "per_page": count, "category": "food", "safesearch": "true"},
            timeout=8,
        )
        hits = r.json().get("hits", [])
        return [h["webformatURL"] for h in hits[:count]]
    except Exception:
        return []


def _insert_images_into_html(body: str, image_urls: list[str]) -> str:
    """h2 소제목 뒤에 이미지 삽입. h2 부족하면 p 태그 뒤에도 삽입."""
    if not image_urls:
        return body
    img_tag = lambda url: f'<img src="{url}" style="width:100%;max-width:640px;margin:16px 0;border-radius:10px;display:block;" />'
    parts = re.split(r'(<h2[^>]*>.*?</h2>|<p[^>]*>.*?</p>)', body, flags=re.DOTALL)
    result = []
    img_idx = 0
    h2_positions = [i for i, p in enumerate(parts) if p.startswith('<h2')]
    # h2 뒤에 먼저 배치
    insert_at = set(h2_positions[:len(image_urls)])
    # h2가 부족하면 p 태그 위치에 균등 배분
    if len(insert_at) < len(image_urls):
        p_positions = [i for i, p in enumerate(parts) if p.startswith('<p')]
        step = max(1, len(p_positions) // (len(image_urls) - len(insert_at) + 1))
        for j in range(0, len(p_positions), step):
            if len(insert_at) >= len(image_urls):
                break
            insert_at.add(p_positions[j])
    for i, part in enumerate(parts):
        result.append(part)
        if i in insert_at and img_idx < len(image_urls):
            result.append(img_tag(image_urls[img_idx]))
            img_idx += 1
    return "".join(result)


def post_to_blogger(blog_id: str, title: str, content: str, labels: list[str] | None = None, image_keyword: str = "") -> dict:
    """Blogger에 글 발행. 성공 시 응답 dict 반환."""
    creds = _get_credentials()
    service = build("blogger", "v3", credentials=creds)

    # 표 먼저 변환 → 나머지 마크다운 변환
    content = _markdown_table_to_html(content)
    content = _markdown_to_html(content)

    # 이미지 삽입
    if image_keyword:
        image_urls = _fetch_ai_images(image_keyword, count=5)

        content = _insert_images_into_html(content, image_urls)

    body_data: dict = {
        "title": title,
        "content": content,
    }
    if labels:
        body_data["labels"] = labels

    result = service.posts().insert(blogId=blog_id, body=body_data, isDraft=False).execute()
    return result
