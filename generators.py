from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
load_dotenv()


Industry = Literal["general", "medical", "insurance"]
BlogPlatform = Literal["tistory", "naver"]


@dataclass(frozen=True)
class GenerateInput:
    industry: Industry
    topic: str
    keywords: list[str]
    tone: str
    platform: Literal["shorts", "reels", "tiktok"]
    seconds: int = 45
    blog_platform: BlogPlatform = "tistory"


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_filename(s: str) -> str:
    s = "".join(ch for ch in s.strip() if ch.isalnum() or ch in (" ", "-", "_"))
    s = "_".join(s.split())
    return s[:80] or "output"


def _ensure_outputs_dir(base_dir: Path) -> Path:
    out = base_dir / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_output(base_dir: Path, title: str, body: str, kind: str, ext: str = "md") -> Path:
    out_dir = _ensure_outputs_dir(base_dir)
    ext = ext.lstrip(".") or "txt"
    path = out_dir / f"{_now_stamp()}__{_safe_filename(title)}__{kind}.{ext}"
    path.write_text(body, encoding="utf-8")
    return path


def _contains_money_imagery_hint(text: str) -> bool:
    bad = [
        "돈",
        "현금",
        "수익",
        "벌",
        "대박",
        "부자",
        "원금",
        "확정",
        "보장수익",
        "$",
        "₩",
    ]
    t = text.replace(" ", "")
    return any(b in t for b in bad)


def _compliance_preamble(industry: Industry) -> str:
    if industry == "medical":
        return (
            "안내: 본 글은 일반적인 정보 제공 목적이며, 개인 상태에 따라 결과는 달라질 수 있습니다. "
            "정확한 진단과 치료 계획은 의료진 상담을 통해 결정됩니다.\n"
        )
    if industry == "insurance":
        return (
            "안내: 본 글은 일반적인 정보 제공 목적이며, 상품별 조건·보장·면책·보험료 등은 다를 수 있습니다. "
            "가입 전 약관 및 상품설명서를 확인하고, 필요 시 전문가 상담을 권장합니다.\n"
        )
    return ""


def _image_block(idx: int, title: str, guidance: str) -> str:
    # Naver 블로그에서는 실제 이미지 업로드 후, 아래 플레이스홀더를 교체해 사용하면 됩니다.
    return (
        f"\n[사진{idx}] {title}\n"
        f"- 촬영/삽입 가이드: {guidance}\n"
        f"- 캡션 예시: {title}\n"
    )


def _safe_image_guidance(industry: Industry) -> str:
    base = "음식/재료/도구/손동작/과정 위주로 깔끔하게"
    if industry == "insurance":
        return base + " (현금/돈다발/수익·부자 연상 소품은 사용하지 않기)"
    return base


def _maybe_table(main_kw: str) -> str:
    # 너무 과하지 않게, 읽기 좋은 비교표 1개 기본 제공
    return (
        f"\n## 한눈에 보는 {main_kw} 체크표\n"
        f"| 구간 | 흔한 실수 | 해결 포인트 |\n"
        f"|---|---|---|\n"
        f"| 준비 | 목표/조건이 불명확 | 목표 1문장 + 시작 상태(온도·수분·양) 점검 |\n"
        f"| 진행 | 순서/타이밍이 들쭉날쭉 | 순서 고정 후 1가지만 조절 |\n"
        f"| 마무리 | 과처리(너무 오래) | 마지막 1~2분은 짧게, 여열 활용 |\n"
    )


def _tags_line(keywords: list[str]) -> str:
    # 티스토리/유튜브 업로드용으로 바로 복붙 가능한 태그 라인
    kws = [k.strip().replace("#", "") for k in keywords if k.strip()]
    uniq: list[str] = []
    for k in kws:
        if k not in uniq:
            uniq.append(k)
    if not uniq:
        return ""
    return " ".join(f"#{k.replace(' ', '')}" for k in uniq[:12])


def _tistory_block(title: str, body: str, keywords: list[str]) -> str:
    # 티스토리 글에서 바로 쓰기 좋은 구성(목차/태그/내부링크 유도 포함)
    tags = _tags_line(keywords)
    return (
        f"{title}\n\n"
        f"[목차]\n"
        f"1) 핵심 요약\n"
        f"2) 준비/재료\n"
        f"3) 단계별 방법\n"
        f"4) 체크표\n"
        f"5) FAQ\n\n"
        f"{body}\n\n"
        f"## 다음 글 추천(내부링크)\n"
        f"- 관련 주제 1: (작성 후 링크 삽입)\n"
        f"- 관련 주제 2: (작성 후 링크 삽입)\n\n"
        f"{'태그: ' + tags if tags else ''}\n"
    )


def _generate_blog_with_claude(inp: GenerateInput) -> tuple[str, str] | None:
    """Claude API로 블로그 글 생성. API 키 없거나 실패시 None 반환."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "여기에_Claude_API_키_입력":
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        kw = [k.strip() for k in inp.keywords if k.strip()]
        main_kw = kw[0] if kw else inp.topic
        keywords_str = ", ".join(kw)
        platform_name = {"tistory": "티스토리", "naver": "네이버 블로그"}.get(inp.blog_platform, "블로그")

        prompt = f"""당신은 SEO에 최적화된 한국어 블로그 글 전문 작가입니다.

주제: {inp.topic}
핵심 키워드: {keywords_str}
톤/분위기: {inp.tone}
플랫폼: {platform_name}
업종: {inp.industry}

다음 조건으로 블로그 글을 작성하세요:
- 제목은 클릭을 유도하고 SEO에 좋게 (메인 키워드 포함)
- 본문은 1500자 이상
- 소제목(##), 목록, 강조(**) 등 마크다운 활용
- 독자가 실제로 도움받을 수 있는 실용적인 내용
- {'티스토리용: 목차/태그/내부링크 유도 포함' if inp.blog_platform == 'tistory' else '네이버용: 자연스럽고 읽기 좋게'}

응답 형식:
TITLE: (제목)
---
(본문 내용)"""

        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if "TITLE:" in text and "---" in text:
            parts = text.split("---", 1)
            title = parts[0].replace("TITLE:", "").strip()
            body = parts[1].strip()
        else:
            lines = text.split("\n")
            title = lines[0].strip()
            body = "\n".join(lines[1:]).strip()
        return title, body
    except Exception as e:
        print(f"[Claude API 오류] {e}")
        return None


def _generate_blog_with_groq(inp: GenerateInput) -> tuple[str, str] | None:
    """Groq API로 네이버 SEO 최적화 블로그 글 생성."""
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        kw = [k.strip() for k in inp.keywords if k.strip()]
        main_kw = kw[0] if kw else inp.topic
        sub_kws = kw[1:] if len(kw) > 1 else []
        sub_kws_str = ", ".join(sub_kws) if sub_kws else main_kw

        prompt = f"""당신은 네이버 블로그 SEO 전문 작가입니다. 아래 조건으로 블로그 글을 작성하세요.

[주제] {inp.topic}
[메인 키워드] {main_kw}
[서브 키워드] {sub_kws_str}
[톤] {inp.tone}

=== 네이버 상위노출 SEO 규칙 ===
1. 제목: 메인 키워드를 앞에 배치, 25~35자, 숫자/궁금증 포함 (예: "멸치볶음 레시피 5가지 – 초보도 바삭하게 만드는 법")
2. 첫 문단(리드): 메인 키워드 2회 이상 자연스럽게 포함, 3~4문장
3. 소제목(##): 서브 키워드 포함, 6~8개 소제목
4. 본문: 2000자 이상, 메인 키워드 10회 이상, 서브 키워드 각 3회 이상
5. 재료/순서는 표(| 구분)로 정리
6. FAQ 섹션: 실제 네이버 검색 질문 패턴으로 5개
7. 마무리: 메인 키워드 + 핵심 요약 1문단
8. 태그: 메인 키워드 + 서브 키워드 포함 10개

응답 형식 (반드시 준수):
TITLE: (제목)
---
(본문 - 마크다운 형식)"""

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.7,
        )
        text = resp.choices[0].message.content.strip()
        if "TITLE:" in text and "---" in text:
            parts = text.split("---", 1)
            title = parts[0].replace("TITLE:", "").strip()
            body = parts[1].strip()
        else:
            lines = text.split("\n")
            title = lines[0].strip()
            body = "\n".join(lines[1:]).strip()
        return title, body
    except Exception as e:
        print(f"[Groq API 오류] {e}")
        return None


def generate_blog_post(inp: GenerateInput) -> tuple[str, str]:
    """
    Returns (title, body). Groq → Claude → 템플릿 순으로 시도.
    """
    # Groq API 시도 (우선)
    result = _generate_blog_with_groq(inp)
    if result:
        title, body = result
        kw = [k.strip() for k in inp.keywords if k.strip()]
        if inp.blog_platform == "tistory":
            return title, _tistory_block(title=title, body=body, keywords=kw)
        return title, body

    # Claude API 시도
    result = _generate_blog_with_claude(inp)
    if result:
        title, body = result
        if inp.blog_platform == "tistory":
            kw = [k.strip() for k in inp.keywords if k.strip()]
            return title, _tistory_block(title=title, body=body, keywords=kw)
        return title, body
    kw = [k.strip() for k in inp.keywords if k.strip()]
    main_kw = kw[0] if kw else inp.topic.strip()
    sub_kws = ", ".join(kw[1:4]) if len(kw) > 1 else ""

    if inp.industry == "insurance":
        price_phrase = "보험료가 경쟁력 있게 설계될 수 있는 포인트"
    else:
        price_phrase = "비용을 합리적으로 관리하는 팁"

    title = f"{main_kw} 완전정리: 초보도 실패 줄이는 핵심 포인트"

    pre = _compliance_preamble(inp.industry)
    img_guide = _safe_image_guidance(inp.industry)
    body = (
        f"{pre}\n"
        f"## {main_kw}, 왜 검색이 많을까?\n"
        f"{main_kw}는(은) 일상에서 자주 마주치지만, 막상 직접 해보면 작은 차이로 결과가 크게 달라지는 주제입니다. "
        f"오늘 글에서는 {main_kw}를 처음 접하는 분들도 이해하기 쉽도록 핵심 흐름을 정리하고, "
        f"실제로 적용할 수 있는 체크리스트까지 함께 안내합니다.\n\n"
        f"{_image_block(1, f'{main_kw} 완성 사진(클로즈업)', img_guide)}\n"
        f"## 오늘 글에서 얻어갈 것\n"
        f"- 핵심 개념/기본 원리\n"
        f"- 실패를 줄이는 준비 단계\n"
        f"- 단계별 실행 방법\n"
        f"- 자주 묻는 질문(FAQ)\n\n"
        f"## 준비 단계: 이것만 점검해도 결과가 달라집니다\n"
        f"1) 목표를 한 문장으로 정리하기: “{main_kw}를 통해 무엇을 해결하려는지”를 먼저 적어보세요.\n"
        f"2) 조건 확인하기: 상황(환경/재료/기간/예산/제약조건)을 체크하면 시행착오가 줄어듭니다.\n"
        f"3) 기준 만들기: 결과를 판단할 기준(맛/시간/안전/유지관리 등)을 정해두면 선택이 쉬워집니다.\n\n"
        f"{_image_block(2, '재료/도구 준비 컷', img_guide)}\n"
        f"## 단계별 방법(초보용 가이드)\n"
        f"### 1단계: 기본을 단순화하기\n"
        f"처음에는 변수를 줄이는 게 중요합니다. 레시피든 절차든, 가장 기본이 되는 흐름을 먼저 반복해 보세요. "
        f"기본이 안정되면 그 다음에 취향(간, 식감, 구성)을 조절해도 늦지 않습니다.\n\n"
        f"{_image_block(3, '1단계 진행 중(핵심 과정) 컷', img_guide)}\n"
        f"### 2단계: 실패가 자주 나는 지점부터 막기\n"
        f"대부분의 실패는 특정 구간에서 반복됩니다. 예를 들어 불 조절, 타이밍, 순서, 혹은 재료의 상태처럼요. "
        f"이 구간을 ‘느리게’ 진행하거나, 체크리스트로 고정하면 결과가 안정됩니다.\n\n"
        f"{_image_block(4, '2단계(실수 포인트 비교) 컷', img_guide)}\n"
        f"### 3단계: 완성도를 올리는 마무리\n"
        f"마무리는 ‘여열/휴지/정리’처럼 사소해 보이는 과정에서 차이가 납니다. "
        f"마지막 1~2분의 선택이 전체 품질을 좌우하니, 다음 포인트를 기억해 두세요.\n"
        f"- 과하게 오래 처리하지 않기\n"
        f"- 향/식감/균형을 한 번 더 점검하기\n"
        f"- 보관/재사용(다음 활용)을 고려한 마무리\n\n"
        f"{_image_block(5, '마무리(완성 직전/플레이팅) 컷', img_guide)}\n"
        f"{_maybe_table(main_kw)}\n"
        f"## {price_phrase}\n"
        f"불필요한 지출이나 낭비는 대부분 ‘정보 부족’과 ‘준비 부족’에서 생깁니다. "
        f"{main_kw}도 마찬가지로, 기본 재료/도구를 무리하게 늘리기보다 "
        f"자주 쓰는 핵심만 갖추고 반복하는 편이 결과와 효율 모두에 도움이 됩니다.\n\n"
        f"## 자주 묻는 질문(FAQ)\n"
        f"### Q1. {main_kw}를 처음 하는데, 무엇부터 하면 좋을까요?\n"
        f"가장 기본 흐름을 한 번 그대로 따라 하고, 그 다음에 한 가지 요소만 조절해 보세요. "
        f"한 번에 여러 요소를 바꾸면 원인을 찾기 어려워집니다.\n\n"
        f"### Q2. 결과가 들쭉날쭉해요. 왜 그럴까요?\n"
        f"대개는 재료/환경 상태, 시간, 순서에서 차이가 납니다. "
        f"‘똑같이 했는데 다르다’고 느껴질 때는, 시작 상태(온도/수분/용량)를 먼저 맞추는 것이 효과적입니다.\n\n"
        f"### Q3. 한 번에 잘 되게 하는 팁이 있나요?\n"
        f"체크리스트를 만들어 3번만 반복해 보세요. "
        f"대부분의 주제는 3회 반복 후부터 감이 잡히고 품질이 안정됩니다.\n\n"
        f"## 마무리\n"
        f"오늘은 {main_kw}를 기준으로 준비부터 실행, 마무리까지 흐름을 정리했습니다. "
        f"핵심은 ‘변수를 줄여 기본을 안정화’하고, ‘실패가 나는 구간을 체크리스트로 고정’하는 것입니다.\n"
    )

    if sub_kws:
        body += f"\n추가 키워드 참고: {sub_kws}\n"

    # Ensure length (1500+ chars) by padding with a value-add section.
    if len(body) < 1500:
        body += (
            "\n## 체크리스트(저장용)\n"
            "- 목표 1문장 정리\n"
            "- 시작 상태(온도/수분/용량) 맞추기\n"
            "- 순서/타이밍 고정\n"
            "- 과처리(너무 오래) 피하기\n"
            "- 마무리 후 보관/재사용까지 고려\n"
            "\n이 체크리스트만 지켜도 결과가 훨씬 안정됩니다.\n"
        )

    if inp.blog_platform == "tistory":
        return title, _tistory_block(title=title, body=body, keywords=kw or [main_kw])
    return title, body


def _srt_from_cuts(lines: list[tuple[str, str]], ends: list[str]) -> str:
    # Very simple SRT for quick import. Times are approximate.
    # lines: [(start, text), ...] where start is "MM:SS"
    def to_ts(mmss: str) -> str:
        mm, ss = mmss.split(":")
        return f"00:{int(mm):02d}:{int(ss):02d},000"

    out: list[str] = []
    for i, ((start, text), end) in enumerate(zip(lines, ends), start=1):
        out.append(str(i))
        out.append(f"{to_ts(start)} --> {to_ts(end)}")
        out.append(text.strip())
        out.append("")
    return "\n".join(out).strip() + "\n"


def generate_shorts_45s(inp: GenerateInput) -> tuple[str, str]:
    """
    Returns (title, script) for a ~45s short with cuts, narration, and captions.
    Includes safe image guidance: avoids money/profit imagery.
    """
    kw = [k.strip() for k in inp.keywords if k.strip()]
    main_kw = kw[0] if kw else inp.topic.strip()

    sec = 60 if int(inp.seconds) >= 60 else 45
    title = f"{main_kw} {sec}초 요약: 실패 줄이는 순서"

    hashtags = _tags_line(kw or [main_kw])
    script = (
        f"플랫폼: {inp.platform} / 길이: {sec}초\n"
        f"주제: {main_kw}\n\n"
        f"## 쇼츠 구성(총 {sec}초)\n"
        f"### 컷 1 (0–{5 if sec==60 else 3}초) 훅\n"
        f"- 화면: 완성 샷 클로즈업(음식/결과물 위주)\n"
        f"- 자막: \"{main_kw} 실패하는 포인트, 딱 3개\"\n"
        f"- 나레이션: \"{main_kw} 하다가 망하는 지점, 오늘 {sec}초로 정리해요.\"\n\n"
        f"### 컷 2 ({5 if sec==60 else 3}–{15 if sec==60 else 10}초) 포인트 1: 시작 상태 맞추기\n"
        f"- 화면: 재료/도구/환경을 한 화면에 정리\n"
        f"- 자막: \"시작 상태(온도·수분·양) 맞추기\"\n"
        f"- 나레이션: \"먼저 시작 상태를 맞추면 결과가 확 안정돼요. 온도, 수분, 양부터 동일하게.\"\n\n"
        f"### 컷 3 ({15 if sec==60 else 10}–{27 if sec==60 else 20}초) 포인트 2: 순서 고정\n"
        f"- 화면: 단계별로 짧게 스냅(1→2→3)\n"
        f"- 자막: \"순서 바꾸면 맛/결과가 흔들려요\"\n"
        f"- 나레이션: \"한 번에 이것저것 바꾸지 말고, 순서를 고정한 뒤 한 가지만 조절하세요.\"\n\n"
        f"### 컷 4 ({27 if sec==60 else 20}–{42 if sec==60 else 32}초) 포인트 3: 과처리 금지\n"
        f"- 화면: 시간/불/강도 조절(타이머, 약불 표시 등)\n"
        f"- 자막: \"오래 하면 딱딱/질김/과해짐\"\n"
        f"- 나레이션: \"대부분 ‘너무 오래’ 해서 망해요. 마지막 1~2분은 특히 짧게, 과처리만 피하면 돼요.\"\n\n"
        f"### 컷 5 ({42 if sec==60 else 32}–{54 if sec==60 else 41}초) 마무리: 향/균형 체크\n"
        f"- 화면: 마무리 재료(예: 깨/참기름/견과/간 조절)를 넣는 장면\n"
        f"- 자막: \"마무리 한 번 더 체크\"\n"
        f"- 나레이션: \"마무리에서 향이랑 균형만 잡아주면 완성도가 확 올라갑니다.\"\n\n"
        f"### 컷 6 ({54 if sec==60 else 41}–{sec}초) CTA\n"
        f"- 화면: 한 입/플레이팅 + 저장 유도\n"
        f"- 자막: \"저장해두고 그대로 따라하기\"\n"
        f"- 나레이션: \"{main_kw}, 저장해두고 그대로 따라 해보세요.\"\n\n"
        f"## 자막 묶음(짧게)\n"
        f"- 시작 상태 맞추기\n"
        f"- 순서 고정\n"
        f"- 과처리 금지\n"
        f"- 마무리 체크\n\n"
        f"## 이미지/소품 가이드(안전)\n"
        f"- 음식/재료/조리도구/손동작 위주\n"
        f"- 돈/수익/현금/그래프 폭등 등 연상 소품·이미지 사용하지 않기\n"
        f"\n## 업로드용 해시태그(복붙)\n"
        f"{hashtags}\n"
    )

    # Extra guardrail for money/profit hints in user-provided text
    if _contains_money_imagery_hint(inp.topic) or any(_contains_money_imagery_hint(k) for k in kw):
        script += "\n주의: 입력 키워드에 금전/수익 연상이 포함되어 보여서, 화면 구성에서 관련 소품/표현은 제외했습니다.\n"

    if sec == 60:
        starts = ["00:00", "00:05", "00:15", "00:27", "00:42", "00:54"]
        ends = ["00:05", "00:15", "00:27", "00:42", "00:54", "01:00"]
    else:
        starts = ["00:00", "00:04", "00:12", "00:20", "00:33", "00:41"]
        ends = ["00:04", "00:12", "00:20", "00:33", "00:41", "00:45"]

    srt = _srt_from_cuts(
        list(
            zip(
                starts,
                [
                    f"{main_kw} 실패 포인트 3개만 막아요",
                    "1) 시작 상태 맞추기(온도·수분·양)",
                    "2) 순서 고정(한 번에 하나만 조절)",
                    "3) 과처리 금지(마지막 1~2분 짧게)",
                    "마무리 체크(향·균형) + 여열 활용",
                    "저장해두고 그대로 따라하기",
                ],
                strict=False,
            )
        ),
        ends=ends,
    )

    return title, script + "\n\n---\n\n## SRT(자동 자막)\n" + srt

