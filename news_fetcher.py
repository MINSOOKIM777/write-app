from __future__ import annotations

import re
import feedparser
import requests
from dataclasses import dataclass
from datetime import datetime

# 정치 뉴스에서 제외할 키워드
POLITICS_FILTER_KEYWORDS: list[str] = [
    # 차별금지/평등 법안
    "차별금지법", "평등법",
    # 민주당 우호 프레임
    "민주당 주도", "민주당이 촉구", "민주당 환영", "민주당 강행", "민주당이 추진",
    "민주당이 제안", "민주당 압승",
    # 이재명 관련
    "이재명", "이 대통령", "李대통령", "李 대통령",
    # 과장된 지지율 (비현실적 수치 필터)
    "지지율 80", "지지율 85", "지지율 90", "지지율 91", "지지율 92",
    "지지율 93", "지지율 94", "지지율 95", "지지율 96", "지지율 97",
    "지지율 98", "지지율 99",
    "긍정 80", "긍정 85", "긍정 90", "긍정 91", "긍정 92",
    "긍정 93", "긍정 94", "긍정 95", "긍정 96", "긍정 97", "긍정 98",
    "국정수행 긍정 8", "국정수행 긍정 9",
    # 검찰개혁
    "검찰개혁", "검수완박",
    # 성소수자
    "성소수자", "퀴어", "트랜스젠더 권리",
    # 편향 여론조사 매체
    "MBC여론조사", "민주당 여론조사", "리얼미터 민주",
]

# 카테고리별 트렌딩 키워드 (구글 뉴스 검색용)
TRENDING_KEYWORDS: dict[str, list[str]] = {
    "economy": [
        "환율 원달러",
        "기름값 휘발유 유가",
        "코스피 코스닥 주가",
        "한국은행 기준금리 금리",
        "아파트 집값 부동산",
        "소비자물가 물가 장바구니",
        "무역수지 수출 수입",
        "취업 실업률 고용",
        "최저임금 임금",
        "관세 미국관세 무역",
    ],
    "sports": [
        "KBO 프로야구",
        "K리그 프로축구",
        "한국 국가대표 축구",
        "NBA 농구",
        "EPL 프리미어리그",
        "KBL 프로농구",
        "골프 LPGA PGA",
        "배구 V리그",
    ],
    "politics": [
        "국민의힘 야당",
        "국회 법안 표결",
        "외교 한미 한중",
        "북한 도발 안보",
        "지방선거 여론",
        "국방부 군사",
    ],
}

# 구글 뉴스 한국 경제/스포츠/정치 검색 (Top Stories 제외 - 글로벌 뉴스 많음)
CATEGORY_FEEDS: dict[str, str] = {
    "economy": "",   # 키워드 검색만 사용
    "sports":  "",
    "politics": "",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
}


@dataclass
class NewsArticle:
    title: str
    summary: str
    link: str
    category: str
    image_url: str = ""
    comment_count: int = 0


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_filtered(title: str, summary: str, filter_keywords: list[str]) -> bool:
    text = (title + " " + summary).replace(" ", "")
    return any(kw.replace(" ", "") in text for kw in filter_keywords)


def _scrape_og_image(url: str) -> str:
    """기사 URL에서 og:image 추출. 구글뉴스 리다이렉트 처리."""
    try:
        # 구글뉴스 링크면 실제 기사 URL 추출
        if "news.google.com" in url:
            r = requests.get(url, headers=HEADERS, timeout=6, allow_redirects=True)
            url = r.url  # 최종 리다이렉트 URL
            if "news.google.com" in url:
                return ""  # 리다이렉트 실패

        r = requests.get(url, headers=HEADERS, timeout=6, allow_redirects=True)
        if r.status_code != 200:
            return ""
        html = r.text
        for pattern in [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        ]:
            m = re.search(pattern, html)
            if m:
                img = m.group(1)
                if img.startswith("http") and "google" not in img:
                    return img
        return ""
    except Exception:
        return ""


def _parse_feed(url: str) -> list[dict]:
    """구글 뉴스 RSS 파싱."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        feed = feedparser.parse(r.text)
        return feed.entries
    except Exception:
        return []


def fetch_news(
    category: str,
    max_items: int = 10,
    apply_politics_filter: bool = False,
) -> list[NewsArticle]:
    """
    구글 뉴스 Top Stories + 트렌딩 키워드 검색을 조합해
    현재 이슈가 많은 뉴스를 가져옵니다. 매번 다른 순서로 섞어서 반환.
    """
    import random
    seen: set[str] = set()
    raw_entries: list = []

    # 1. 카테고리 Top Stories
    top_url = CATEGORY_FEEDS.get(category)
    if top_url:
        entries = _parse_feed(top_url)
        raw_entries.extend(entries)

    # 2. 트렌딩 키워드 - 매번 랜덤 순서로 섞기
    keywords = TRENDING_KEYWORDS.get(category, []).copy()
    random.shuffle(keywords)
    for kw in keywords:
        encoded = requests.utils.quote(kw)
        # 캐시 방지용 타임스탬프 추가
        ts = int(datetime.now().timestamp())
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko&ts={ts}"
        entries = _parse_feed(url)
        raw_entries.extend(entries)

    # 3. Top Stories 이후 항목들을 섞어서 다양성 확보
    top_count = len(_parse_feed(top_url)) if top_url else 0
    top_entries = raw_entries[:top_count]
    rest_entries = raw_entries[top_count:]
    random.shuffle(rest_entries)
    raw_entries = top_entries + rest_entries

    # 4. 중복 제거 + 필터 + 변환
    articles: list[NewsArticle] = []
    for entry in raw_entries:
        title = _clean_html(getattr(entry, "title", "")).strip()
        if not title or title in seen:
            continue

        summary_raw = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        summary = _clean_html(summary_raw)[:300]

        if apply_politics_filter and _is_filtered(title, summary, POLITICS_FILTER_KEYWORDS):
            continue

        # 뉴스 출처 제거 (구글 뉴스는 "제목 - 언론사" 형태)
        title = re.sub(r"\s*-\s*[^-]+$", "", title).strip()

        seen.add(title)
        link = getattr(entry, "link", "")

        # RSS 미디어 이미지 추출
        image_url = ""
        media = getattr(entry, "media_content", [])
        if media and isinstance(media, list):
            image_url = media[0].get("url", "")
        if not image_url:
            for enc in getattr(entry, "enclosures", []):
                if "image" in enc.get("type", ""):
                    image_url = enc.get("href", "")
                    break

        # RSS 이미지 없으면 기사 페이지 og:image 스크래핑
        if not image_url and link:
            image_url = _scrape_og_image(link)

        articles.append(NewsArticle(
            title=title,
            summary=summary,
            link=link,
            category=category,
            image_url=image_url,
        ))

        if len(articles) >= max_items:
            break

    return articles
