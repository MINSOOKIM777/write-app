from __future__ import annotations

import os
import re
import io
import subprocess
import textwrap
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
ELEVENLABS_VOICE_MINSOO = "dJF4sfoeozl3QvAp0ct6"
ELEVENLABS_VOICE_AYLA   = "vNkdizTnVyIVt41zBCjK"


def _edge_tts(text: str, out_path: Path, voice: str = "ko-KR-HyunsuMultilingualNeural",
              rate: str = "+0%", pitch: str = "-3Hz") -> Path:
    """Microsoft Edge 신경망 TTS (무료, 자연스러운 한국어)."""
    import asyncio, edge_tts

    async def _run():
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(str(out_path))

    asyncio.run(_run())
    return out_path
from PIL import Image, ImageDraw, ImageFont
import requests

load_dotenv()

VIDEO_W, VIDEO_H = 1080, 1920  # 세로형 쇼츠

CATEGORY_COLORS = {
    "economy": {"bg": (10, 18, 40), "accent": (0, 190, 255), "text": (255, 255, 255), "sub": (160, 200, 255)},
    "sports":  {"bg": (18, 8, 8),   "accent": (255, 50, 50),  "text": (255, 255, 255), "sub": (255, 180, 180)},
    "politics":{"bg": (15, 25, 15), "accent": (50, 200, 100), "text": (255, 255, 255), "sub": (180, 240, 200)},
    "general": {"bg": (20, 20, 20), "accent": (220, 180, 80), "text": (255, 255, 255), "sub": (220, 200, 160)},
}

# 카테고리별 Pexels 검색 키워드 (배경 이미지용)
CATEGORY_IMAGE_KEYWORDS = {
    "economy": ["stock market chart", "financial district", "economy money", "trading floor", "bank building"],
    "sports":  ["sports stadium", "soccer field", "baseball game", "athletic competition", "sport crowd"],
    "politics":["government building", "parliament", "political meeting", "korea flag", "diplomacy"],
}


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def generate_shorts_script(title: str, summary: str, category: str) -> dict:
    """Groq API로 60초 뉴스 쇼츠 대본 생성."""
    import json
    from groq import Groq

    cat_kr = {"economy": "경제", "sports": "스포츠", "politics": "정치"}.get(category, category)
    groq = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

    prompt = f"""당신은 뉴스 앵커입니다.
아래 {cat_kr} 뉴스를 60초 분량으로 또렷하게 읽어주세요.
질문하지 말고, 과장하지 말고, 뉴스 내용만 자연스럽게 전달하세요.
나레이션은 60초 분량이 되도록 충분히 작성하세요 (각 슬라이드 2~3문장).

뉴스 제목: {title}
뉴스 요약: {summary}

image_keyword 작성 규칙 (매우 중요):
- Pixabay 검색에 쓸 영어 키워드로 뉴스 내용과 직접 관련된 실물/장소/사물만
- 예시:
  * 서울 아파트 → "Seoul apartment buildings"
  * 휘발유 가격 → "gas station fuel price"
  * 주가 하락 → "stock market graph decline"
  * 환율 상승 → "dollar exchange rate"
  * 부동산 → "Korea apartment real estate"
  * 야구 → "baseball game korea"
  * 축구 → "soccer football match"
  * 금리 → "bank interest rate"
- "bear", "bull" 같은 비유 절대 금지
- 슬라이드마다 서로 다른 키워드
- 반드시 영어 2~4단어

다음 JSON 형식으로만 답하세요 (다른 설명 없이):
{{
  "video_title": "유튜브 제목 (35자 이내, 뉴스 제목 그대로)",
  "hook": "첫 자막 (20자 이내, 핵심 내용 요약)",
  "slides": [
    {{
      "caption": "자막 (20자 이내)",
      "narration": "나레이션 2~3문장. 빠르고 명확하게. 핵심 정보 전달.",
      "image_keyword": "뉴스 내용 관련 구체적 영어 키워드"
    }},
    {{
      "caption": "자막",
      "narration": "나레이션 2~3문장.",
      "image_keyword": "슬라이드1과 다른 구체적 영어 키워드"
    }},
    {{
      "caption": "자막",
      "narration": "나레이션 2~3문장.",
      "image_keyword": "슬라이드2와 다른 구체적 영어 키워드"
    }},
    {{
      "caption": "자막",
      "narration": "나레이션 2~3문장.",
      "image_keyword": "슬라이드3과 다른 구체적 영어 키워드"
    }},
    {{
      "caption": "자막",
      "narration": "나레이션 2~3문장.",
      "image_keyword": "슬라이드4와 다른 구체적 영어 키워드"
    }}
  ],
  "cta": "마지막 자막 (구독/알림 유도, 20자 이내)",
  "hashtags": "관련 해시태그 5개"
}}"""

    r = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
    )
    text = r.choices[0].message.content.strip()
    m = re.search(r"\{[\s\S]+\}", text)
    if not m:
        raise ValueError(f"Groq JSON 없음:\n{text}")
    raw = m.group()
    # 제어문자 제거 후 파싱
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 문자열 값 내 줄바꿈을 공백으로 치환 후 재시도
        raw = re.sub(r'(?<=: ")(.*?)(?=")', lambda m: m.group().replace('\n', ' '), raw, flags=re.DOTALL)
        return json.loads(raw)


def fetch_image_bytes(keyword: str, category: str, article_image_url: str = "") -> bytes | None:
    """키워드로 주제에 맞는 이미지 가져오기."""

    # 1. 뉴스 기사 원본 이미지 (가장 정확)
    if article_image_url:
        try:
            r = requests.get(article_image_url, timeout=8,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and len(r.content) > 5000:
                return r.content
        except Exception:
            pass

    # 2. Pixabay API
    pixabay_key = os.getenv("PIXABAY_API_KEY", "")
    if pixabay_key:
        try:
            import random as _rand
            eng_words = re.findall(r'[a-zA-Z]+', keyword)
            q = " ".join(eng_words[:4]) if eng_words else keyword
            page = _rand.randint(1, 3)
            r = requests.get(
                "https://pixabay.com/api/",
                params={"key": pixabay_key, "q": q, "image_type": "photo",
                        "per_page": 10, "page": page, "safesearch": "true"},
                timeout=8,
            )
            if r.status_code == 200:
                hits = r.json().get("hits", [])
                if hits:
                    pick = _rand.choice(hits)
                    ir = requests.get(pick["webformatURL"], timeout=10)
                    if ir.status_code == 200 and len(ir.content) > 5000:
                        return ir.content
        except Exception:
            pass

    # 3. loremflickr 폴백
    try:
        # 영어 키워드만 추출
        eng_words = re.findall(r'[a-zA-Z]+', keyword)
        if not eng_words:
            # 카테고리 기본 키워드
            defaults = {
                "economy": ["stock", "market", "finance"],
                "sports": ["baseball", "soccer", "sport"],
                "politics": ["government", "politics", "parliament"],
                "bible": ["sunrise", "peaceful", "nature"],
            }
            eng_words = defaults.get(category, ["news"])
        import random as _rand
        kw_str = ",".join(eng_words[:3])
        seed = _rand.randint(1, 9999)
        r = requests.get(
            f"https://loremflickr.com/1080/1920/{kw_str}?random={seed}",
            timeout=10, allow_redirects=True
        )
        if r.status_code == 200 and len(r.content) > 5000:
            return r.content
    except Exception:
        pass

    return None


def _get_font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                # AppleSDGothicNeo.ttc: index 3=Bold, 0=Regular
                idx = 3 if bold and path.endswith(".ttc") else 0
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                continue
    return ImageFont.load_default()


def _load_bg(bg_bytes: bytes | None, colors: dict) -> Image.Image:
    if bg_bytes:
        try:
            bg = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
            # 크롭하여 9:16 비율 맞추기
            bw, bh = bg.size
            target_ratio = VIDEO_W / VIDEO_H
            current_ratio = bw / bh
            if current_ratio > target_ratio:
                new_w = int(bh * target_ratio)
                left = (bw - new_w) // 2
                bg = bg.crop((left, 0, left + new_w, bh))
            else:
                new_h = int(bw / target_ratio)
                top = (bh - new_h) // 2
                bg = bg.crop((0, top, bw, top + new_h))
            return bg.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
        except Exception:
            pass
    return Image.new("RGBA", (VIDEO_W, VIDEO_H), colors["bg"] + (255,))


def _make_first_frame(
    title: str,
    category: str,
    bg_bytes: bytes | None,
    channel_name: str = "뉴스 쇼츠",
) -> Image.Image:
    """JTBC 스타일 세로형 첫 프레임 (1080x1920)."""
    colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS["economy"])
    cat_labels = {"economy": "⚡ 경제 속보", "sports": "🏆 스포츠", "politics": "🔴 정치 뉴스"}
    cat_label = cat_labels.get(category, "📢 뉴스")

    bg = _load_bg(bg_bytes, colors)

    # 강한 하단 그라디언트
    overlay = Image.new("RGBA", (VIDEO_W, VIDEO_H), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    for y in range(VIDEO_H // 3, VIDEO_H):
        alpha = int(230 * ((y - VIDEO_H // 3) / (VIDEO_H * 2 / 3)))
        draw_ov.line([(0, y), (VIDEO_W, y)], fill=(0, 0, 0, min(alpha, 230)))
    frame = Image.alpha_composite(bg, overlay).convert("RGB")
    draw = ImageDraw.Draw(frame)

    font_badge = _get_font(40, bold=True)
    font_ch    = _get_font(42, bold=True)
    font_title = _get_font(96, bold=True)
    font_sub   = _get_font(80, bold=True)

    # 상단 좌: 카테고리 뱃지
    bx, by = 36, 40
    badge_text = f"  {cat_label}  "
    bbox = draw.textbbox((bx, by), badge_text, font=font_badge)
    draw.rectangle([bbox[0]-2, bbox[1]-4, bbox[2]+2, bbox[3]+8], fill=colors["accent"])
    draw.text((bx, by), badge_text, font=font_badge, fill=(0, 0, 0))

    # 상단 우: 채널명
    draw.text((VIDEO_W - 36, 44), channel_name, font=font_ch, fill=(255, 255, 255),
              anchor="ra", stroke_width=2, stroke_fill=(0, 0, 0))

    # 하단: 제목 (최대 3줄, 첫줄 흰색 나머지 강조색)
    lines = textwrap.wrap(title, width=11)[:3]
    total_h = len(lines) * 110
    y_start = VIDEO_H - total_h - 80
    for i, line in enumerate(lines):
        color = (255, 255, 255) if i == 0 else colors["accent"]
        font  = font_title if i == 0 else font_sub
        draw.text((VIDEO_W // 2, y_start + i * 110), line, font=font, fill=color,
                  anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))

    return frame


def make_thumbnail(
    title: str,
    category: str,
    bg_bytes: bytes | None,
    out_path: Path,
    channel_name: str = "뉴스 쇼츠",
) -> Path:
    """JTBC 스타일 썸네일 생성 (1280x720 유튜브 썸네일)."""
    TW, TH = 1280, 720
    colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS["economy"])
    cat_labels = {"economy": "경제 속보", "sports": "스포츠", "politics": "정치 뉴스"}
    cat_label = cat_labels.get(category, "뉴스")

    # 배경 (가로형)
    if bg_bytes:
        try:
            bg = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
            bw, bh = bg.size
            target_ratio = TW / TH
            current_ratio = bw / bh
            if current_ratio > target_ratio:
                new_h = bh
                new_w = int(bh * target_ratio)
                left = (bw - new_w) // 2
                bg = bg.crop((left, 0, left + new_w, new_h))
            else:
                new_w = bw
                new_h = int(bw / target_ratio)
                top = (bh - new_h) // 2
                bg = bg.crop((0, top, new_w, top + new_h))
            bg = bg.resize((TW, TH), Image.LANCZOS)
        except Exception:
            bg = Image.new("RGBA", (TW, TH), colors["bg"] + (255,))
    else:
        bg = Image.new("RGBA", (TW, TH), colors["bg"] + (255,))

    # 어두운 하단 그라디언트
    overlay = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    for y in range(TH // 2, TH):
        alpha = int(200 * ((y - TH // 2) / (TH // 2)))
        draw_ov.line([(0, y), (TW, y)], fill=(0, 0, 0, alpha))
    frame = Image.alpha_composite(bg, overlay).convert("RGB")
    draw = ImageDraw.Draw(frame)

    font_badge  = _get_font(32, bold=True)
    font_ch     = _get_font(36, bold=True)
    font_title  = _get_font(82, bold=True)
    font_title2 = _get_font(74, bold=True)

    # 상단 좌: 카테고리 뱃지
    badge_x, badge_y = 30, 24
    badge_text = f"  {cat_label}  "
    bbox = draw.textbbox((badge_x, badge_y), badge_text, font=font_badge)
    draw.rectangle([bbox[0]-4, bbox[1]-4, bbox[2]+4, bbox[3]+8], fill=colors["accent"])
    draw.text((badge_x, badge_y), badge_text, font=font_badge, fill=(0, 0, 0))

    # 상단 우: 채널명
    draw.text((TW - 20, 24), channel_name, font=font_ch, fill=(255, 255, 255), anchor="ra",
              stroke_width=2, stroke_fill=(0, 0, 0))

    # 제목 줄바꿈 (최대 14자/줄)
    lines = textwrap.wrap(title, width=14)[:3]

    # 첫 줄: 흰색, 나머지: 강조색
    total_h = len(lines) * 95
    y_start = TH - total_h - 40
    for i, line in enumerate(lines):
        color = (255, 255, 255) if i == 0 else colors["accent"]
        font = font_title if i == 0 else font_title2
        draw.text((TW // 2, y_start + i * 95), line, font=font, fill=color, anchor="mm",
                  stroke_width=4, stroke_fill=(0, 0, 0))

    frame.save(str(out_path), "JPEG", quality=95)
    return out_path


def _make_slide_image(
    caption: str,
    bg_bytes: bytes | None,
    category: str,
    slide_index: int,
    total_slides: int,
    hook: str = "",
    cta: str = "",
    title: str = "",
    channel_name: str = "뉴스 쇼츠",
) -> Image.Image:
    colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS["economy"])
    cat_labels = {"economy": "경제 속보", "sports": "스포츠", "politics": "정치 뉴스"}
    cat_label = cat_labels.get(category, "뉴스")

    # 첫 슬라이드는 JTBC 스타일 (세로형)
    if slide_index == 0:
        return _make_first_frame(title or hook, category, bg_bytes, channel_name)

    # 이후 슬라이드: 배경
    bg = _load_bg(bg_bytes, colors)

    # 어두운 오버레이
    overlay = Image.new("RGBA", (VIDEO_W, VIDEO_H), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    for y in range(500):
        alpha = int(160 * (1 - y / 500))
        draw_ov.line([(0, y), (VIDEO_W, y)], fill=(0, 0, 0, alpha))
    for y in range(VIDEO_H - 700, VIDEO_H):
        alpha = int(210 * ((y - (VIDEO_H - 700)) / 700))
        draw_ov.line([(0, y), (VIDEO_W, y)], fill=(0, 0, 0, alpha))

    frame = Image.alpha_composite(bg, overlay).convert("RGB")
    draw = ImageDraw.Draw(frame)

    def get_font(size: int):
        candidates = [
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        ]
        for path in candidates:
            if Path(path).exists():
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    font_cap = get_font(62)

    # 자막만 하단에 표시
    if caption:
        wrapped = textwrap.wrap(caption, width=14)
        cap_y = VIDEO_H - 260
        for line in wrapped[:3]:
            draw.text((VIDEO_W // 2, cap_y), line, font=font_cap, fill=(255, 255, 255), anchor="mm",
                      stroke_width=3, stroke_fill=(0, 0, 0))
            cap_y += 80

    return frame


def _speed_up_audio(input_path: Path, output_path: Path, speed: float = 3.0) -> Path:
    """ffmpeg으로 오디오 재생 속도 올리기. atempo 최대 2.0이라 체인으로 3배 처리."""
    try:
        # atempo는 0.5~2.0 범위만 지원 → 3배는 2.0,1.5로 체인
        if speed <= 2.0:
            af = f"atempo={speed}"
        else:
            # 예: 3.0 = 2.0 * 1.5
            af = f"atempo=2.0,atempo={speed/2.0:.2f}"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(input_path),
            "-filter:a", af,
            str(output_path)
        ], capture_output=True, check=True)
        return output_path
    except Exception:
        return input_path


def make_bible_short(verse: dict, out_dir: Path) -> Path:
    """성경 구절 쇼츠 영상 생성. verse = {"ref": "요한복음 3:16", "text": "..."}"""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    tmp_dir = out_dir / f"_tmp_bible_{stamp}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    ref  = verse["ref"]
    text = verse["text"]

    # "4:8" → "4장 8절", "3:5-6" → "3장 5절에서 6절" 변환 (TTS 읽기용)
    SINO = {"1":"일","2":"이","3":"삼","4":"사","5":"오","6":"육","7":"칠","8":"팔","9":"구","10":"십",
            "11":"십일","12":"십이","13":"십삼","14":"십사","15":"십오","16":"십육","17":"십칠","18":"십팔","19":"십구","20":"이십",
            "21":"이십일","22":"이십이","23":"이십삼","24":"이십사","25":"이십오","26":"이십육","27":"이십칠","28":"이십팔","29":"이십구","30":"삼십",
            "31":"삼십일","40":"사십","50":"오십","100":"백","119":"백십구","139":"백삼십구","145":"백사십오","150":"백오십"}

    def num_to_sino(n: str) -> str:
        n = n.strip()
        if n in SINO:
            return SINO[n]
        try:
            v = int(n)
            if v <= 30:
                return SINO.get(n, n)
            tens = v // 10
            ones = v % 10
            result = SINO.get(str(tens * 10), "") + (SINO.get(str(ones), "") if ones else "")
            return result or n
        except Exception:
            return n

    def ref_to_speech(r: str) -> str:
        book, *rest = r.rsplit(" ", 1) if " " in r else (r, [])
        chapter_verse = rest[0] if rest else ""
        if not chapter_verse:
            return r
        if "-" in chapter_verse and ":" in chapter_verse:
            ch, vv_part = chapter_verse.split(":", 1)
            v_start, v_end = vv_part.split("-", 1)
            return f"{book} {num_to_sino(ch)}장 {num_to_sino(v_start)}절에서 {num_to_sino(v_end)}절"
        elif ":" in chapter_verse:
            ch, v = chapter_verse.split(":", 1)
            return f"{book} {num_to_sino(ch)}장 {num_to_sino(v)}절"
        return r

    ref_spoken = ref_to_speech(ref)

    # 1. Groq으로 1분 묵상 나레이션 생성
    from groq import Groq
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
    prompt = f"""당신은 1516교회 이상준 목사님 스타일로 설교하는 묵상 진행자입니다.

이상준 목사님 스타일 특징:
- 차분하고 진지하지만 따뜻한 어조
- 회중의 아픔과 일상에서 먼저 공감한 뒤 말씀으로 연결
- 본인의 솔직한 경험을 자연스럽게 녹여냄 ("저도 그런 적이 있었어요")
- 단호하고 명확한 메시지 ("하나님은 우리를 포기하지 않으십니다")
- 예수 그리스도 중심으로 귀결
- 현대적 비유 사용 (일상, 직장, 관계 등)
- 마무리는 짧고 힘있는 선포

아래 성경 구절로 유튜브 쇼츠 1분 분량의 나레이션을 작성하세요.
구절 참조는 반드시 "{ref_spoken}" 으로 읽어야 합니다.

구절: {ref_spoken}
본문: {text}

구조:
1. 일상적 공감 도입 (10초)
2. "{ref_spoken}" 자연스럽게 언급 후 본문 낭독 (10초)
3. 삶에 적용되는 따뜻하고 명확한 묵상 메시지 (30초)
4. 힘있는 마무리 선포 (10초)

주의:
- 구어체로만 작성
- "예수 이름으로", "할렐루야", "아멘" 등 종교적 추임새 절대 금지
- 성경 본문 내용과 직접 연결된 말만 사용
- 나레이션 텍스트만 출력"""

    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.7,
    )
    narration = resp.choices[0].message.content.strip()

    # 2. TTS - 성경은 느리고 낮게
    raw_audio = tmp_dir / "bible_raw.mp3"
    _edge_tts(narration, raw_audio, rate="+5%", pitch="-3Hz")

    # 2. 배경 이미지 (성경/신앙 어울리는 배경)
    BIBLE_KEYWORDS = ["cross sunset sky", "church light rays", "heaven clouds golden",
                      "bible sunrise mountain", "holy light forest", "golden light cross",
                      "peaceful chapel sunrise", "prayer hands light"]
    import random
    kw = random.choice(BIBLE_KEYWORDS)
    img_bytes = fetch_image_bytes(kw, "bible")

    # 3. 슬라이드 이미지 (성경 전용 디자인)
    W, H = VIDEO_W, VIDEO_H
    img = Image.new("RGB", (W, H), (20, 10, 40))

    if img_bytes:
        try:
            bg = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((W, H))
            dark = Image.new("RGB", (W, H), (0, 0, 0))
            img = Image.blend(bg, dark, alpha=0.55)
        except Exception:
            pass

    draw = ImageDraw.Draw(img)

    def get_font(size: int):
        for path in [
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/Library/Fonts/NanumGothic.ttf",
        ]:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    # 구절 본문 줄 나눔 후 전체 높이 계산해서 세로 가운데 배치
    wrapped = textwrap.wrap(text, width=14)
    line_h = 82
    ref_h = 70
    gap = 30
    total_h = ref_h + gap + len(wrapped[:8]) * line_h
    start_y = (H - total_h) // 2

    # 구절 참조
    draw.text((W // 2, start_y + ref_h // 2), ref, font=get_font(58), fill=(255, 215, 100), anchor="mm",
              stroke_width=2, stroke_fill=(0, 0, 0))

    # 구절 본문
    y = start_y + ref_h + gap
    for line in wrapped[:8]:
        draw.text((W // 2, y), line, font=get_font(52), fill=(255, 255, 255), anchor="mm",
                  stroke_width=2, stroke_fill=(0, 0, 0))
        y += line_h

    # 하단 브랜딩
    draw.text((W // 2, H - 100), "오늘의 말씀", font=get_font(44), fill=(200, 180, 120), anchor="mm")

    frame_path = tmp_dir / "bible_frame.jpg"
    img.save(str(frame_path), "JPEG", quality=92)

    # 4. 영상 조립
    from moviepy import ImageClip, AudioFileClip
    audio_clip = AudioFileClip(str(raw_audio))
    video = ImageClip(str(frame_path)).with_duration(audio_clip.duration).with_audio(audio_clip)

    safe_ref = "".join(c for c in ref if c.isalnum() or c in " -_:").strip()[:30]
    out_path = out_dir / f"{stamp}__{safe_ref}__bible_short.mp4"
    video.write_videofile(str(out_path), fps=24, codec="libx264", audio_codec="aac", logger=None)

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return out_path


def make_news_short(title: str, summary: str, category: str, out_dir: Path, article_image_url: str = "") -> Path:
    """뉴스 쇼츠 영상 생성 파이프라인."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    tmp_dir = out_dir / f"_tmp_{stamp}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 1. 대본 생성
    script = generate_shorts_script(title, summary, category)
    video_title = script.get("video_title", title)
    hook        = script.get("hook", "")
    cta         = script.get("cta", "구독하고 알림 켜세요!")
    slides_data = script.get("slides", [])

    # 2. 나레이션 전체 합치기
    narration_parts = [hook + "."] if hook else []
    for s in slides_data:
        narration_parts.append(s.get("narration", ""))
    narration_parts.append(cta)
    narration_full = " ".join(narration_parts)

    # 3. TTS - 뉴스는 빠르고 또렷하게
    raw_audio = tmp_dir / "narration_raw.mp3"
    _edge_tts(narration_full, raw_audio, rate="+30%", pitch="+0Hz")
    audio_path = raw_audio

    # 4. 슬라이드 이미지 생성
    total = len(slides_data)
    frame_paths: list[Path] = []
    first_img_bytes = None
    for i, slide in enumerate(slides_data):
        kw = slide.get("image_keyword", "news")
        # 첫 슬라이드엔 기사 원본 이미지 우선 사용
        art_img = article_image_url if i == 0 else ""
        img_bytes = fetch_image_bytes(kw, category, art_img)
        if i == 0:
            first_img_bytes = img_bytes
        frame = _make_slide_image(
            caption=slide.get("caption", ""),
            bg_bytes=img_bytes,
            category=category,
            slide_index=i,
            total_slides=total,
            hook=hook if i == 0 else "",
            cta=cta if i == total - 1 else "",
            title=video_title,
        )
        fp = tmp_dir / f"slide_{i:02d}.jpg"
        frame.save(str(fp), "JPEG", quality=92)
        frame_paths.append(fp)

    # 5. 영상 조립
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

    audio_clip = AudioFileClip(str(audio_path))
    total_dur  = audio_clip.duration
    slide_dur  = total_dur / total

    clips = [ImageClip(str(fp)).with_duration(slide_dur) for fp in frame_paths]
    video = concatenate_videoclips(clips, method="compose").with_audio(audio_clip)

    safe_title = "".join(c for c in video_title if c.isalnum() or c in " -_")[:40].strip()
    out_path = out_dir / f"{stamp}__{safe_title}__news_short.mp4"

    video.write_videofile(str(out_path), fps=24, codec="libx264", audio_codec="aac", logger=None)

    # 썸네일 생성 (유튜브용 1280x720)
    thumb_path = out_dir / f"{stamp}__{safe_title}__thumbnail.jpg"
    make_thumbnail(video_title, category, first_img_bytes, thumb_path)

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return out_path
