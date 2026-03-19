from __future__ import annotations

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Streamlit Cloud secrets → os.environ 동기화
import os
for _k in ["GEMINI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY", "PIXABAY_API_KEY", "ELEVENLABS_API_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"]:
    try:
        if _k in st.secrets:
            os.environ[_k] = st.secrets[_k]
    except Exception:
        pass

from generators import GenerateInput, generate_blog_post, generate_shorts_45s, save_output
from youtube_uploader import (
    UploadRequest,
    list_my_channels,
    parse_hashtags_to_tags,
    save_client_secret,
    token_path,
    upload_video,
)
from news_fetcher import fetch_news
from video_maker import make_news_short, make_bible_short
from bible_verses import get_daily_verse


BASE_DIR = Path(__file__).resolve().parent


def _extract_file_text(uploaded_file) -> str:
    """업로드된 파일에서 텍스트 추출 (PDF/TXT)."""
    try:
        if uploaded_file.name.endswith(".txt"):
            return uploaded_file.read().decode("utf-8", errors="ignore")
        elif uploaded_file.name.endswith(".pdf"):
            try:
                import pdfplumber
                with pdfplumber.open(uploaded_file) as pdf:
                    return "\n".join(p.extract_text() or "" for p in pdf.pages)[:6000]
            except ImportError:
                import PyPDF2
                reader = PyPDF2.PdfReader(uploaded_file)
                return "\n".join(p.extract_text() or "" for p in reader.pages)[:6000]
    except Exception as e:
        st.error(f"파일 읽기 실패: {e}")
    return ""
YOUTUBE_DIR = BASE_DIR / ".local_youtube"


st.set_page_config(page_title="블로그/쇼츠 자동 생성", layout="wide")
st.title("블로그 글 작성 / 쇼츠 만들기")
st.caption("입력 → 버튼 클릭으로 블로그 글(1500자+)과 쇼츠(45/60초) 대본을 자동 생성합니다.")

main_tab, news_tab, bible_tab, blogger_tab = st.tabs(["✍️ 블로그/쇼츠 작성", "📺 뉴스 쇼츠 자동 생성", "✝️ 성경 쇼츠", "📝 블로거 포스팅"])

# ───────────────────────────────────────────────────────────────
# 탭 1: 기존 블로그/쇼츠 작성
# ───────────────────────────────────────────────────────────────
with main_tab:
    with st.expander("업종별 준수사항", expanded=False):
        st.markdown(
            "- **의료**: 과장/단정 표현을 피하고, 정보 제공 목적 및 개인차 안내를 포함합니다.\n"
            "- **보험/금융**: 확정 수익·원금 보장 등 오해 소지 표현을 피하고, 약관/설명서 확인 안내를 포함합니다.\n"
            "- **이미지**: 돈/수익을 연상시키는 소품·이미지를 지양합니다.\n"
        )

    st.sidebar.header("설정")

    industry = st.sidebar.selectbox(
        "업종",
        options=[
            ("general", "일반(요리/생활/리뷰 등)"),
            ("medical", "병원/의료"),
            ("insurance", "보험/금융"),
        ],
        format_func=lambda x: x[1],
    )[0]

    blog_platform = st.sidebar.selectbox(
        "블로그 플랫폼",
        options=[
            ("tistory", "티스토리"),
            ("naver", "네이버 블로그"),
        ],
        format_func=lambda x: x[1],
    )[0]

    platform = st.sidebar.selectbox(
        "쇼츠 플랫폼",
        options=[
            ("shorts", "유튜브 쇼츠"),
            ("reels", "인스타 릴스"),
            ("tiktok", "틱톡"),
        ],
        format_func=lambda x: x[1],
    )[0]

    seconds = st.sidebar.selectbox(
        "쇼츠 길이",
        options=[60, 45],
        index=0,
    )

    st.sidebar.divider()
    st.sidebar.caption(
        f"현재 설정: 업종={industry}, 블로그={blog_platform}, 쇼츠={platform}, 길이={seconds}초"
    )

    st.sidebar.divider()
    st.sidebar.subheader("유튜브 업로드(자동)")
    yt_enabled = st.sidebar.checkbox("유튜브 API 업로드 사용", value=False)

    YOUTUBE_DIR.mkdir(parents=True, exist_ok=True)
    profiles_file = YOUTUBE_DIR / "profiles.txt"
    if profiles_file.exists():
        raw_profiles = [l.strip() for l in profiles_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        raw_profiles = ["main"]

    yt_profile = st.sidebar.selectbox("채널 프로필 선택", options=raw_profiles, index=0)
    new_profile = st.sidebar.text_input("새 프로필 추가 (예: cook, life)", value="")
    if new_profile.strip():
        if new_profile not in raw_profiles:
            raw_profiles.append(new_profile.strip())
            profiles_file.write_text("\n".join(raw_profiles), encoding="utf-8")
            st.sidebar.success(f"프로필 '{new_profile}' 추가됨. 드롭다운에서 선택해 주세요.")

    left, right = st.columns([1, 1])

    with left:
        topic = st.text_input("주제", value="")
        keywords_raw = st.text_input("핵심 키워드(쉼표로 구분)", value="")
        tone = st.text_input("톤/분위기", value="친근하고 따라 하기 쉽게")

    with right:
        st.markdown("### 빠른 안내")
        st.markdown(
            "- **네이버**: 생성된 TXT를 메모장(TextEdit)에서 열어 복사→붙여넣기 권장\n"
            "- **티스토리**: 목차/태그/내부링크 섹션이 자동 포함됩니다\n"
        )

    # 보험 업종일 때 설계안 파일 업로드
    extra_context = ""
    if industry == "insurance":
        st.markdown("#### 📄 설계안 파일 업로드 (선택)")
        doc_file = st.file_uploader("설계안 PDF 또는 TXT 업로드", type=["pdf", "txt"], key="main_doc")
        if doc_file:
            extra_context = _extract_file_text(doc_file)
            if extra_context:
                st.success(f"✅ 파일 읽기 완료 ({len(extra_context)}자)")

    inp = GenerateInput(
        industry=industry,
        blog_platform=blog_platform,
        topic=topic.strip(),
        keywords=[k.strip() for k in keywords_raw.split(",") if k.strip()],
        tone=tone.strip(),
        platform=platform,
        seconds=seconds,
        extra_context=extra_context,
    )

    st.divider()

    blog_clicked = st.button("블로그 글 작성", type="primary", use_container_width=True)
    shorts_clicked = st.button(f"쇼츠 만들기({seconds}초)", use_container_width=True)

    if blog_clicked:
        title, body = generate_blog_post(inp)
        txt_payload = f"{title}\n\n{body}\n"
        saved_txt = save_output(BASE_DIR, title=title, body=txt_payload, kind="blog", ext="txt")

        st.subheader("생성된 블로그 글")
        st.markdown(f"**제목:** {title}")
        st.text_area("본문", value=body, height=420)
        st.download_button(
            label="메모장용 TXT 다운로드",
            data=txt_payload.encode("utf-8"),
            file_name=saved_txt.name,
            mime="text/plain",
            use_container_width=True,
        )
        st.caption(f"저장 위치(TXT): `{saved_txt}`")

    if shorts_clicked:
        try:
            title, script = generate_shorts_45s(inp)
            txt_payload = f"{title}\n\n{script}\n"
            saved_txt = save_output(BASE_DIR, title=title, body=txt_payload, kind="shorts", ext="txt")

            st.subheader(f"생성된 {seconds}초 쇼츠 대본")
            st.markdown(f"**제목:** {title}")
            st.text_area("대본", value=script, height=300)
            st.download_button(
                label="TXT 다운로드",
                data=txt_payload.encode("utf-8"),
                file_name=saved_txt.name,
                mime="text/plain",
                use_container_width=True,
            )

            st.divider()
            if st.button("🎬 영상으로 만들기", type="primary", use_container_width=True):
                with st.spinner("영상 생성 중... (30~60초 소요)"):
                    try:
                        video_path = make_news_short(
                            title=title,
                            summary=script,
                            category="general",
                            out_dir=BASE_DIR / "outputs",
                        )
                        st.success("완료!")
                        st.video(str(video_path))
                        with open(video_path, "rb") as f:
                            st.download_button(
                                label="📥 영상 다운로드",
                                data=f.read(),
                                file_name=video_path.name,
                                mime="video/mp4",
                                use_container_width=True,
                            )
                    except Exception as e:
                        st.error(f"영상 생성 실패: {e}")
        except Exception as e:
            st.error(f"쇼츠 생성 오류: {e}")

    st.divider()
    st.subheader("유튜브 쇼츠 업로드(선택)")
    st.caption("영상(mp4)은 편집 앱에서 만든 파일을 선택해서 업로드합니다. 첫 1회는 구글 로그인/권한 허용이 필요해요.")

    if not yt_enabled:
        st.info("사이드바에서 **유튜브 API 업로드 사용**을 켜면 업로드가 활성화됩니다.")
    else:
        colA, colB = st.columns([1, 1])

        with colA:
            client_secret_file = st.file_uploader(
                "OAuth 클라이언트 JSON 업로드(client_secret.json)",
                type=["json"],
                help="Google Cloud Console에서 만든 OAuth Client(Desktop app) JSON 파일",
            )
            video_file = st.file_uploader("업로드할 영상(mp4)", type=["mp4", "mov", "m4v"])

        with colB:
            yt_title = st.text_input("유튜브 제목", value=f"{topic} 1분 요약")
            yt_desc = st.text_area(
                "유튜브 설명(복붙)",
                value=f"{topic}\n\n#shorts\n",
                height=180,
            )
            yt_hashtags = st.text_input("해시태그(예: #멸치볶음 #레시피)", value="")
            privacy = st.selectbox("공개 설정", options=["unlisted", "private", "public"], index=0)

        auth_col1, auth_col2 = st.columns([1, 1])

        profile_secret_path = YOUTUBE_DIR / f"client_secret__{yt_profile}.json"
        profile_token_path = token_path(YOUTUBE_DIR, yt_profile)

        if client_secret_file is not None:
            saved_secret = save_client_secret(YOUTUBE_DIR, yt_profile, client_secret_file.getvalue())
            st.success(f"OAuth JSON 저장됨: `{saved_secret}`")

        if auth_col1.button("내 채널 확인(로그인)", use_container_width=True):
            if not profile_secret_path.exists():
                st.error("먼저 OAuth 클라이언트 JSON을 업로드해 주세요.")
            else:
                try:
                    channels = list_my_channels(profile_secret_path, profile_token_path)
                    if not channels:
                        st.warning("로그인은 됐지만 채널 정보를 못 가져왔어요. 계정/권한을 확인해 주세요.")
                    else:
                        st.write("연결된 채널:")
                        for ch in channels:
                            snippet = ch.get("snippet", {})
                            st.write(f"- {snippet.get('title', '(no title)')}")
                except Exception as e:
                    st.error(str(e))

        if auth_col2.button("영상 업로드", type="primary", use_container_width=True):
            if not profile_secret_path.exists():
                st.error("먼저 OAuth 클라이언트 JSON을 업로드해 주세요.")
            elif video_file is None:
                st.error("업로드할 영상(mp4)을 선택해 주세요.")
            else:
                out_dir = BASE_DIR / "outputs"
                out_dir.mkdir(parents=True, exist_ok=True)
                video_path = out_dir / f"upload__{yt_profile}__{video_file.name}"
                video_path.write_bytes(video_file.getvalue())

                tags = parse_hashtags_to_tags(yt_hashtags)
                req = UploadRequest(
                    video_path=video_path,
                    title=yt_title,
                    description=yt_desc,
                    tags=tags,
                    privacy_status=privacy,  # type: ignore[arg-type]
                )
                try:
                    resp = upload_video(profile_secret_path, profile_token_path, req)
                    vid = resp.get("id")
                    st.success(f"업로드 완료. Video ID: `{vid}`")
                except Exception as e:
                    st.error(str(e))


# ───────────────────────────────────────────────────────────────
# 탭 2: 뉴스 쇼츠 자동 생성
# ───────────────────────────────────────────────────────────────
with news_tab:
    st.subheader("📺 뉴스 쇼츠 자동 생성")
    st.caption("뉴스를 자동으로 가져와 Gemini + Imagen으로 영상을 만듭니다.")

    import os
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    _news_ready = bool(gemini_key and gemini_key != "여기에_Gemini_API_키_입력")
    if not _news_ready:
        st.warning("⚠️ `.env` 파일에 `GEMINI_API_KEY`를 입력해야 합니다.")
        st.code("GEMINI_API_KEY=your_key_here", language="bash")

    if _news_ready:
        n_col1, n_col2 = st.columns([1, 2])

        with n_col1:
            news_category = st.radio(
                "뉴스 카테고리",
                options=[("economy", "📈 경제"), ("sports", "⚽ 스포츠"), ("politics", "🏛️ 정치")],
                format_func=lambda x: x[1],
            )[0]

            politics_filter = False
            if news_category == "politics":
                politics_filter = st.checkbox("민주당 우호 기사 필터링", value=True, help="차별금지법, 민주당 지지 프레임 기사 자동 제외")

            fetch_btn = st.button("🔄 뉴스 가져오기", use_container_width=True)

        if "news_articles" not in st.session_state:
            st.session_state.news_articles = []
        if "selected_article_idx" not in st.session_state:
            st.session_state.selected_article_idx = 0

        if fetch_btn:
            with st.spinner("뉴스 수집 중..."):
                articles = fetch_news(
                    news_category,
                    max_items=8,
                    apply_politics_filter=politics_filter,
                )
                st.session_state.news_articles = articles
                st.session_state.selected_article_idx = 0

        articles = st.session_state.news_articles

        if not articles:
            st.info("위에서 카테고리 선택 후 **뉴스 가져오기**를 눌러주세요.")
        else:
            with n_col2:
                article_titles = [f"{i+1}. {a.title[:40]}..." if len(a.title) > 40 else f"{i+1}. {a.title}" for i, a in enumerate(articles)]
                sel_idx = st.selectbox("기사 선택", options=list(range(len(articles))), format_func=lambda i: article_titles[i])
                st.session_state.selected_article_idx = sel_idx

            selected = articles[sel_idx]

            st.divider()
            st.markdown(f"**제목:** {selected.title}")
            if selected.summary:
                st.markdown(f"**요약:** {selected.summary[:200]}...")
            if selected.link:
                st.markdown(f"[기사 원문 보기]({selected.link})")

            st.divider()

            make_btn = st.button("🎬 쇼츠 영상 만들기", type="primary", use_container_width=True)

            if make_btn:
                out_dir = BASE_DIR / "outputs"
                progress = st.progress(0, text="대본 생성 중...")
                try:
                    progress.progress(20, text="대본 생성 중...")
                    video_path = make_news_short(
                        title=selected.title,
                        summary=selected.summary,
                        category=news_category,
                        out_dir=out_dir,
                        article_image_url=selected.image_url,
                    )
                    progress.progress(100, text="완료!")
                    st.success("영상 생성 완료!")
                    st.caption(f"저장 위치: `{video_path}`")

                    with open(video_path, "rb") as f:
                        st.video(f.read())

                    with open(video_path, "rb") as f:
                        st.download_button(
                            label="📥 영상 다운로드",
                            data=f.read(),
                            file_name=video_path.name,
                            mime="video/mp4",
                            use_container_width=True,
                        )
                except Exception as e:
                    st.error(f"영상 생성 실패: {e}")

# ───────────────────────────────────────────────────────────────
# 탭 3: 성경 쇼츠
# ───────────────────────────────────────────────────────────────
with bible_tab:
    import random as _random
    from bible_verses import VERSES

    st.subheader("✝️ 오늘의 말씀 쇼츠")
    st.caption("우리말성경 기반 - 랜덤 구절 또는 직접 선택")

    # 세션 초기화
    if "bible_idx" not in st.session_state:
        st.session_state.bible_idx = _random.randint(0, len(VERSES) - 1)

    col_rand, col_pick = st.columns([1, 2])
    with col_rand:
        if st.button("🎲 랜덤 구절", use_container_width=True):
            st.session_state.bible_idx = _random.randint(0, len(VERSES) - 1)
    with col_pick:
        ref_list = [v["ref"] for v in VERSES]
        picked = st.selectbox("구절 직접 선택", options=ref_list,
                              index=st.session_state.bible_idx, label_visibility="collapsed")
        st.session_state.bible_idx = ref_list.index(picked)

    verse = VERSES[st.session_state.bible_idx]
    st.markdown(f"### 📖 {verse['ref']}")
    st.markdown(f"> {verse['text']}")

    if st.button("🎬 성경 쇼츠 영상 만들기", type="primary", use_container_width=True):
        with st.spinner("영상 생성 중... (30~60초 소요)"):
            try:
                video_path = make_bible_short(verse, BASE_DIR / "outputs")
                st.success("완료!")
                with open(video_path, "rb") as f:
                    st.download_button(
                        label="📥 영상 다운로드",
                        data=f.read(),
                        file_name=video_path.name,
                        mime="video/mp4",
                        use_container_width=True,
                    )
                st.video(str(video_path))
            except Exception as e:
                st.error(f"영상 생성 실패: {e}")

# ───────────────────────────────────────────────────────────────
# 탭 4: 블로거 포스팅
# ───────────────────────────────────────────────────────────────
with blogger_tab:
    st.subheader("📝 Google Blogger 자동 포스팅")
    st.caption("블로그 글 자동 생성 후 Blogger에 바로 발행합니다.")

    BLOGGER_ID = "7254148981721208318"

    def _auto_fill_keywords(topic: str) -> dict:
        """Groq으로 주제에 맞는 키워드/톤/라벨 자동 생성."""
        import os
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            try:
                api_key = st.secrets.get("GROQ_API_KEY", "")
            except Exception:
                pass
        if not api_key:
            return {"error": "GROQ_API_KEY 없음"}
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": f"""블로그 주제: "{topic}"
아래 항목을 JSON으로만 응답하세요 (다른 텍스트 없이):
{{
  "main_keyword": "메인 키워드 1개",
  "sub_keywords": "서브키워드1, 서브키워드2, 서브키워드3, 서브키워드4",
  "tone": "톤/분위기 한 문장",
  "labels": "라벨1,라벨2,라벨3"
}}"""}],
                max_tokens=200,
                temperature=0.3,
            )
            import json, re
            text = resp.choices[0].message.content.strip()
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as _e:
            return {"error": str(_e)}
        return {}

    if "b_keywords" not in st.session_state:
        st.session_state.b_keywords = ""
    if "b_tone" not in st.session_state:
        st.session_state.b_tone = "친근하고 따라하기 쉽게"
    if "b_labels" not in st.session_state:
        st.session_state.b_labels = ""

    with st.form(key="topic_form", clear_on_submit=False):
        b_topic = st.text_input("주제 입력 (엔터 또는 버튼으로 자동완성)", value="", key="b_topic")
        auto_submit = st.form_submit_button("✨ 키워드 자동 완성", use_container_width=True)

    if auto_submit and b_topic.strip():
        with st.spinner("키워드 생성 중..."):
            auto = _auto_fill_keywords(b_topic.strip())
            if "error" in auto:
                st.error(f"오류: {auto['error']}")
            elif auto:
                st.session_state.b_keywords = f"{auto.get('main_keyword','')}, {auto.get('sub_keywords','')}"
                st.session_state.b_tone = auto.get("tone", "친근하고 따라하기 쉽게")
                st.session_state.b_labels = auto.get("labels", "")
            else:
                st.error("GROQ_API_KEY가 없거나 응답 실패")

    b_col1, b_col2 = st.columns([1, 1])
    with b_col1:
        b_keywords = st.text_input("키워드(메인, 서브)", key="b_keywords")
        b_tone = st.text_input("톤", key="b_tone")
    with b_col2:
        b_labels = st.text_input("라벨/태그(쉼표 구분)", key="b_labels")
        b_industry = st.selectbox("업종", options=[("general","일반"),("medical","의료"),("insurance","보험/금융")], format_func=lambda x: x[1], key="b_industry")[0]

    # 보험 업종일 때 설계안 업로드
    b_extra_context = ""
    if b_industry == "insurance":
        st.markdown("#### 📄 설계안 파일 업로드 (선택)")
        b_doc_file = st.file_uploader("설계안 PDF 또는 TXT 업로드", type=["pdf", "txt"], key="b_doc")
        if b_doc_file:
            b_extra_context = _extract_file_text(b_doc_file)
            if b_extra_context:
                st.success(f"✅ 파일 읽기 완료 ({len(b_extra_context)}자)")

    if "blogger_title" not in st.session_state:
        st.session_state.blogger_title = ""
        st.session_state.blogger_body = ""

    gen_post_btn = st.button("🚀 글 생성 + Blogger 발행", use_container_width=True, type="primary")
    if gen_post_btn:
        with st.spinner("글 생성 중..."):
            try:
                b_inp = GenerateInput(
                    industry=b_industry,
                    blog_platform="naver",
                    topic=b_topic.strip(),
                    keywords=[k.strip() for k in b_keywords.split(",") if k.strip()],
                    tone=b_tone.strip(),
                    platform="shorts",
                    seconds=60,
                    extra_context=b_extra_context,
                )
                title, body = generate_blog_post(b_inp)
            except Exception as e:
                st.error(f"글 생성 실패: {e}")
                title, body = None, None

        if title:
            with st.spinner("이미지 검색 및 발행 중... (30~60초 소요)"):
                try:
                    from blogger_poster import post_to_blogger, _fetch_ai_images, _translate_keyword
                    labels = [l.strip() for l in b_labels.split(",") if l.strip()]

                    # 이미지 미리 fetch해서 상태 표시
                    import re as _re
                    kw = _re.sub(r'(레시피|만드는\s*법|만들기|요리법|요리).*', '', b_topic.strip()).strip()
                    if not kw:
                        kw = b_topic.strip()
                    px_key = os.getenv("PIXABAY_API_KEY", "")
                    if not px_key:
                        st.warning("⚠️ PIXABAY_API_KEY가 없어서 이미지 없이 발행됩니다. Streamlit Secrets에 추가해주세요.")
                    else:
                        en_kw = _translate_keyword(kw)
                        st.info(f"🔍 이미지 검색 키워드: **{en_kw}** (원본: {kw})")
                        image_urls = _fetch_ai_images(kw, count=5)
                        if image_urls:
                            st.success(f"✅ 이미지 {len(image_urls)}장 준비됨")
                        else:
                            st.warning("⚠️ Pixabay 이미지를 찾지 못했습니다. 이미지 없이 발행됩니다.")

                    result = post_to_blogger(BLOGGER_ID, title, body, labels, image_keyword=kw if kw else b_topic.strip())
                    post_url = result.get("url", "")
                    st.success(f"발행 완료!")
                    st.markdown(f"[{title}]({post_url})")
                    st.session_state.edit_b_title = title
                    st.session_state.edit_b_body = body
                except Exception as e:
                    st.error(f"발행 실패: {e}")

    if st.session_state.get("edit_b_title"):
        st.divider()
        st.text_input("마지막 발행 제목", key="edit_b_title", disabled=True)
