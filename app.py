from __future__ import annotations

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

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
YOUTUBE_DIR = BASE_DIR / ".local_youtube"


st.set_page_config(page_title="블로그/쇼츠 자동 생성", layout="wide")
st.title("블로그 글 작성 / 쇼츠 만들기")
st.caption("입력 → 버튼 클릭으로 블로그 글(1500자+)과 쇼츠(45/60초) 대본을 자동 생성합니다.")

main_tab, news_tab, bible_tab = st.tabs(["✍️ 블로그/쇼츠 작성", "📺 뉴스 쇼츠 자동 생성", "✝️ 성경 쇼츠"])

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
        topic = st.text_input("주제", value="멸치볶음 레시피")
        keywords_raw = st.text_input("핵심 키워드(쉼표로 구분)", value="멸치볶음, 멸치볶음 레시피, 밑반찬")
        tone = st.text_input("톤/분위기", value="친근하고 따라 하기 쉽게")

    with right:
        st.markdown("### 빠른 안내")
        st.markdown(
            "- **네이버**: 생성된 TXT를 메모장(TextEdit)에서 열어 복사→붙여넣기 권장\n"
            "- **티스토리**: 목차/태그/내부링크 섹션이 자동 포함됩니다\n"
            "- **사진**: 본문에 `[사진1]~[사진5]` 슬롯이 자동 들어갑니다\n"
        )

    inp = GenerateInput(
        industry=industry,
        blog_platform=blog_platform,
        topic=topic.strip(),
        keywords=[k.strip() for k in keywords_raw.split(",") if k.strip()],
        tone=tone.strip(),
        platform=platform,
        seconds=seconds,
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
