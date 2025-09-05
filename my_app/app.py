import sys
import uuid
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st  # noqa: E402
from streamlit.navigation.page import Page as Page  # noqa: E402
from streamlit_option_menu import option_menu  # noqa: E402
from supabase import Client, create_client  # noqa: E402
from supabase._sync.client import SyncClient  # noqa: E402

# ========================================
# 🚀 팀원을 위한 개발 가이드
# ========================================

# 1. 새로운 페이지 추가하기:
#    - ui/ 폴더에 새 페이지 파일 생성
#    - USER_MENUS 딕셔너리에 메뉴 항목 추가
#    - PAGE_ICONS 딕셔너리에 아이콘 추가
#    - get_page_config() 함수에 페이지 정의 추가

# 2. 스타일 수정하기:
#    - apply_global_styles() 함수에서 CSS 수정
#    - 브랜드 컬러: #FE7743 (주황), #273F4F (남색)

# 3. 메뉴 구조 변경:
#    - USER_MENUS에서 사용자별 메뉴 수정
#    - 순서, 이름, 라우팅 키 변경 가능

# 4. 인증 관련:
#    - check_auth_params(): OAuth 처리
#    - logout(): 로그아웃 처리
#    - 새로운 역할 추가시 ROLES 배열 수정

# 5. 디버깅:
#    - st.session_state를 출력해서 상태 확인
#    - st.write(st.session_state)로 전체 상태 확인

# 6. 주의사항:
#    - 세션 상태 변경 후 st.rerun() 필수
#    - 파일 경로는 Path 객체 사용 권장
#    - 에러 처리는 try-except로 감싸기


# ========================================
# CONFIGURATION & CONSTANTS
# ========================================

# 시스템에서 사용가능한 사용자 역할 정의
ROLES: list[str | None] = [None, "User", "Admin"]

# 페이지별 아이콘 매핑 - 팀원이 쉽게 수정 가능
PAGE_ICONS = {
    "chatbot": "chat-dots",
    "dashboard": "bar-chart-line",
    "quiz": "question-circle",
    "content": "book",
    "recommendation": "gift",
    "rag_recommendation": "robot",
    "simulation": "graph-up",
    "analysis": "bar-chart-line",
    "admin1": "person-add",
    "admin2": "security",
    "settings": "gear",
    "logout": "box-arrow-right",
}

# 사용자 역할별 메뉴 구성 - 새로운 메뉴 추가시 여기서 수정
USER_MENUS = {
    "User": [
        ("사용자 메타 분석", "chatbot"),
        ("오늘의 퀴즈", "quiz"),
        ("맞춤형 금융 지식", "content"),
        ("맞춤형 상품 추천", "rag_recommendation"),
        ("현재 보유주식 AI코칭", "simulation"),
        ("종목 피드백", "analysis"),
        ("Settings", "settings"),
        ("Logout", "logout"),
    ],
    "Admin": [
        ("Chatbot", "chatbot"),
        ("Dashboard", "dashboard"),
        ("맞춤형 금융 지식", "content"),
        ("Admin 1", "admin1"),
        ("Admin 2", "admin2"),
        ("Settings", "settings"),
        ("Logout", "logout"),
    ],
}

# ========================================
# CORE FUNCTIONS - 핵심 기능
# ========================================


@st.cache_resource
def init_supabase() -> SyncClient:
    """
    Supabase 클라이언트 초기화 및 캐싱

    Returns:
        Client: 데이터베이스 작업을 위한 Supabase 클라이언트 인스턴스

    Raises:
        Exception: Supabase 초기화 실패시 예외 발생

    Note:
        @st.cache_resource 데코레이터로 인해 한 번만 실행되고 캐시됨
    """
    try:
        supabase: Client = create_client(
            st.secrets["supabase"]["url"], st.secrets["supabase"]["key"]
        )
        return supabase
    except Exception as e:
        st.error(f"Supabase 초기화 오류: {e}")
        st.stop()


def check_auth_params() -> None:
    """
    OAuth 콜백 처리 - Google 로그인 후 리다이렉트 처리

    Purpose:
        - Google 로그인 완료 후 앱으로 돌아올 때 실행
        - URL에 포함된 'authorization code'를 세션으로 교환
        - 사용자 정보를 세션 스테이트에 저장

    Process:
        1. URL 파라미터에서 'code' 확인
        2. code가 있으면 Supabase와 세션 교환
        3. 성공시 사용자 정보 저장 및 로그인 완료
        4. 실패시 에러 메시지 표시
    """
    query_params = st.query_params

    if "code" in query_params:
        code = query_params["code"]
        supabase: SyncClient | None = init_supabase()

        if supabase is None:
            raise ValueError("Supabase client is not initialized")

        st.session_state.supabase = supabase

        try:
            supabase_session = supabase.auth.exchange_code_for_session(
                {"auth_code": code}  # type: ignore
            )

            if supabase_session.session:
                st.session_state.session = supabase_session.session
                st.session_state.user = supabase_session.user

                # 사용자 기본 데이터 로드
                response_user_data = (
                    supabase.table("profiles")
                    .select("*")
                    .eq("id", st.session_state.user.id)  # pyright: ignore[reportOptionalMemberAccess]
                    .execute()
                )
                if "user_data" not in st.session_state:
                    user_data: dict = {
                        "user_email": response_user_data.data[0]["email"],
                        "name": response_user_data.data[0]["name"],
                        "age": response_user_data.data[0]["age"],
                        "gender": response_user_data.data[0]["gender"],
                        "investment_goal": response_user_data.data[0][
                            "investment_goal"
                        ],
                        "investment_emotions": response_user_data.data[0][
                            "investment_emotions"
                        ],
                        "interests_categories": response_user_data.data[0][
                            "interests_categories"
                        ],
                        "investment_level": response_user_data.data[0][
                            "investment_level"
                        ],
                        "knowledge_level": response_user_data.data[0][
                            "knowledge_level"
                        ],
                        "risk_tolerance": response_user_data.data[0]["risk_tolerance"],
                    }
                    st.session_state.user_data = user_data

                if response_user_data.data and response_user_data.data[0]["role"] in [
                    "User",
                    "Admin",
                ]:
                    st.session_state.role = response_user_data.data[0]["role"]
                else:
                    raise Exception("User role is not valid")

                # ── profiles 기준으로 역할/프로필 동기화 ──
                uid = st.session_state.user.id  # pyright: ignore[reportOptionalMemberAccess]
                email = st.session_state.user.email  # pyright: ignore[reportOptionalMemberAccess]
                meta = getattr(st.session_state.user, "user_metadata", {}) or {}
                name = meta.get("full_name") or meta.get("name") or email

                sel = supabase.table("profiles").select("*").eq("id", uid).execute()
                rows = sel.data if hasattr(sel, "data") else sel

                if not rows:
                    ins = (
                        supabase.table("profiles")
                        .insert(
                            {
                                "id": uid,
                                "email": email,
                                "name": name,
                                "role": "User",
                            }
                        )
                        .execute()
                    )
                    profile = (
                        (ins.data or [])[0]
                        if hasattr(ins, "data")
                        else {"id": uid, "email": email, "name": name, "role": "User"}
                    )
                else:
                    profile = rows[0]
                    if not profile.get("role"):
                        upd = (
                            supabase.table("profiles")
                            .update({"role": "User"})
                            .eq("id", uid)
                            .execute()
                        )
                        profile = (
                            (upd.data or [])[0]
                            if hasattr(upd, "data")
                            else {**profile, "role": "User"}
                        )

                st.session_state.profile = profile
                st.session_state.role = profile.get("role", "User")

                # URL 정리 및 페이지 새로고침
                st.query_params.clear()
                st.rerun()

        except Exception as e:
            st.error(f"인증 실패: {e}")
            st.query_params.clear()


def login() -> None:
    """
    Google OAuth를 통한 사용자 로그인 처리

    Features:
        - 중앙 정렬된 로그인 버튼
        - 동적 리다이렉트 URL 생성
        - 에러 처리 포함
    """
    st.markdown(
        """
        <center>
            <h1>FIREgenerator</h1>
        </center>
    """,
        unsafe_allow_html=True,
    )

    # 3열 레이아웃으로 버튼 중앙 배치
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # 로고 이미지 표시 (크기 조절 + 중앙 정렬)
        image_path = Path(__file__).parent / "assets" / "FIRE_LOGO_large.png"
        if image_path.exists():
            # 중앙 정렬을 위한 컨테이너 생성
            _, img_col, _ = st.columns([0.5, 1, 0.5])
            with img_col:
                st.image(image_path)

        # 버튼 크기 조절을 위한 추가 컬럼 생성
        _, btn_col, _ = st.columns([1, 2, 1])
        with btn_col:
            if st.button("Sign in with Google", use_container_width=True):
                try:
                    supabase = init_supabase()

                    # 동적으로 현재 앱 URL 생성
                    current_url = st.get_option("browser.serverAddress") or "localhost"
                    port = st.get_option("browser.serverPort")
                    redirect_url = f"http://{current_url}:{port}/"

                    # Google OAuth 로그인 프로세스 시작
                    response = supabase.auth.sign_in_with_oauth(
                        {
                            "provider": "google",
                            "options": {
                                "redirect_to": redirect_url,
                                "scopes": "email profile",
                            },
                        }
                    )

                    if response and response.url:
                        # Google 로그인 페이지로 자동 리다이렉트
                        st.markdown(
                            f'<meta http-equiv="refresh" content="0;url={response.url}">',
                            unsafe_allow_html=True,
                        )
                        st.info("Google 로그인 중입니다...")

                except Exception as e:
                    st.error(f"로그인 실패: {e}")


def logout() -> None:
    """
    사용자 로그아웃 처리

    Process:
        1. Supabase 서버에서 로그아웃
        2. 세션 스테이트에서 인증 관련 정보 삭제
        3. 페이지 새로고침으로 로그인 페이지로 이동

    Note:
        안전한 접근을 위해 선택적으로 세션 정보 삭제
    """
    from ui.chatbot import USER_DATA_KEY

    if "session" in st.session_state and st.session_state.session:
        supabase: SyncClient | None = init_supabase()

        if supabase is None:
            raise ValueError("Supabase client is not initialized")

        try:
            supabase.auth.sign_out()
        except Exception:
            pass  # 서버 로그아웃 실패해도 로컬 로그아웃은 진행

    # 인증 관련 세션 정보만 선택적으로 삭제
    AUTH_KEYS: list[str] = ["session", "user", "role", "current_page"]

    RESSETABLE_KEYS: list[str] = USER_DATA_KEY + AUTH_KEYS

    for key in RESSETABLE_KEYS:
        if key in st.session_state:
            del st.session_state[key]

    st.cache_data.clear()
    st.cache_resource.clear()

    st.rerun()


# ========================================
# UI COMPONENTS - 사용자 인터페이스 구성요소
# ========================================


def apply_global_styles():
    """
    전체 애플리케이션에 적용될 CSS 스타일 정의

    Features:
        - 배경색 및 카드 스타일
        - 반응형 디자인
        - 브랜드 컬러 적용 (#FE7743, #273F4F)
    """
    st.markdown(
        """
        <style>
            /* 전체 배경 스타일 */
            .css-1aumxhk { 
                background-color: #F2F2F2; 
            }

            /* 카드 컴포넌트 스타일 */
            .card {
                background-color: white;
                border-radius: 16px;
                padding: 12px;
                box-shadow: 0px 4px 16px rgba(0,0,0,0.05);
                height: 150px;
            }
            .card h3 {
                color: #FE7743;
                margin-bottom: 8px;
            }

            /* 채팅 입력 필드 스타일 */
            .stChatInput input {
                width: 100% !important;
                border-radius: 25px !important;
                border: 2px solid #FE7743 !important;
                padding: 12px 20px !important;
                font-size: 16px !important;
                background-color: #ffffff !important;
            }

            .stChatInput input:focus {
                border-color: #FE7743 !important;
                box-shadow: 0 0 0 2px rgba(254, 119, 67, 0.2) !important;
            }

            /* 채팅 메시지 스타일 */
            .stChatMessage {
                margin-bottom: 1rem !important;
                max-width: 100% !important;
            }

            /* 메인 콘텐츠 영역 패딩 조정 */
            .main .block-container {
                padding-bottom: 120px !important;
            }

        </style>
    """,
        unsafe_allow_html=True,
    )


def render_sidebar():
    """
    사이드바 메뉴 렌더링

    Features:
        - 사용자 역할에 따른 동적 메뉴 구성
        - 현재 페이지 상태 유지
        - 아이콘과 함께 직관적인 메뉴
        - 브랜드 컬러 적용
    """
    with st.sidebar:
        # 로고 표시
        try:
            logo_path = (
                Path(__file__).parent / "assets" / "FIREgen_horizontal_logo_edit.png"
            )
            if logo_path.exists():
                st.image(logo_path, width=200)
        except Exception:
            st.markdown("## FIREgenerator")

        # 사용자 역할에 따른 메뉴 구성
        role = st.session_state.get("role", "User")
        if not isinstance(role, str):
            role = "User"  # 문자열이 아닐 경우 기본값
        menu_config = USER_MENUS.get(role, USER_MENUS["User"])

        menu_options = [label for label, _ in menu_config]
        menu_icons = [PAGE_ICONS.get(page_key, "circle") for _, page_key in menu_config]
        page_mapping = {label: page_key for label, page_key in menu_config}

        # 현재 선택된 메뉴 인덱스 찾기
        current_page = st.session_state.get("current_page", "chatbot")
        current_index = 0
        for i, (_, page_key) in enumerate(menu_config):
            if page_key == current_page:
                current_index = i
                break

        # 메뉴 렌더링
        selected = option_menu(
            menu_title=None,
            options=menu_options,
            icons=menu_icons,
            default_index=current_index,
            styles={
                "container": {"padding": "0", "background-color": "#F2F2F2"},
                "icon": {"color": "#273F4F", "font-size": "18px"},
                "nav-link": {
                    "font-size": "16px",
                    "text-align": "left",
                    "--hover-color": "#FEE5A5",
                },
                "nav-link-selected": {
                    "background-color": "#FE7743",
                    "color": "white",
                },
            },
        )

        # 사용자 정보 표시
        user_email = st.session_state.get("profile", {}).get("email", "Unknown")
        st.success(f"로그인됨: {user_email}")

        # 메뉴 선택 처리
        new_page = page_mapping[selected]
        if new_page == "logout":
            logout()
        elif new_page != current_page:
            st.session_state.current_page = new_page
            st.rerun()


# ========================================
# PAGE ROUTING - 페이지 라우팅 시스템
# ========================================


def route_to_page():
    """
    현재 선택된 페이지에 따라 적절한 콘텐츠를 렌더링

    Note:
        각 페이지의 실제 구현은 ui/ 폴더의 해당 파일에서 import하여 사용
    """
    current_page = st.session_state.get("current_page", "chatbot")

    try:
        if current_page == "chatbot":
            try:
                from ui.chatbot.chatbot import render

                render()

            except Exception as e:
                st.error(f"페이지 로딩 중 오류가 발생했습니다: {e}")

        elif current_page == "quiz":
            try:
                from ui.level_quiz.quiz import render

                # 환영 메시지 설정
                if "messages" not in st.session_state or not isinstance(
                    st.session_state.messages, list
                ):
                    st.session_state.messages = []

                if not st.session_state.get("quiz_welcome_pushed", False):
                    st.session_state.messages.append(
                        {
                            "id": str(uuid.uuid4()),
                            "role": "assistant",
                            "content": "안녕하세요! 금융 지식 퀴즈를 시작해보세요. 아래 버튼으로 시작할 수 있어요.",
                        }
                    )
                    st.session_state.quiz_welcome_pushed = True
                    st.session_state.streaming = True
                    st.rerun()

                render()
            except Exception as e:
                st.title("🧠 오늘의 퀴즈")
                st.error("퀴즈 모듈 임포트 중 오류가 발생했습니다.")
                st.exception(e)
                st.stop()

        elif current_page == "content":
            try:
                from ui.contents.user_recommender import render

                render()
            except ImportError as e:
                st.title("🔥 맞춤형 금융 지식")
                st.error(f"페이지를 불러올 수 없습니다: {e}")
                st.info("ui/contents/user_recommender.py 파일을 확인해주세요.")

        elif current_page == "rag_recommendation":
            try:
                from ui.recommendation.rag_recommendation import render

                render()
            except ImportError:
                st.title("🤖 RAG 맞춤 추천")
                st.info("ui/recommendation/rag_recommendation.py 파일을 생성해주세요.")

        elif current_page == "simulation":
            try:
                from ui.trading.trading_ui import render

                render()
            except Exception as e:
                st.error(f"{e} 모듈 임포트 중 오류가 발생했습니다.")
                st.exception
            # except ImportError:
            #     st.title("📈 현재 보유주식 AI코칭")
            #     st.info("ui/trading/trading_ui.py 파일을 생성해주세요.")
        elif current_page == "analysis":
            try:
                from ui.analysis.streamlit_app import render  # type: ignore

                render()
            except Exception as e:
                st.error(f"{e} 모듈 임포트 중 오류가 발생했습니다.")
                st.exception
            # except ImportError:
            #     st.title("📊 종목 피드백")
            #     st.info("ui/analysis/analysis.py 파일을 생성해주세요.")

        elif current_page == "settings":
            try:
                from ui.settings.settings_sample import render

                render()
            except ImportError:
                st.title("⚙️ Settings")
                st.info("ui/settings/settings.py 파일을 생성해주세요.")

        # else:
        #     st.title("🏠 홈")
        #     st.write("환영합니다! 사이드바에서 원하는 메뉴를 선택해주세요.")

    except Exception as e:
        st.error(f"페이지 로딩 중 오류가 발생했습니다: {e}")
        st.write("파일 구조와 import 경로를 확인해주세요.")


def main_app():
    """
    메인 애플리케이션 실행

    Flow:
        1. 스타일 적용
        2. 헤더 렌더링
        3. 사이드바 렌더링 (커스텀 메뉴)
        4. 현재 페이지에 따른 콘텐츠 표시
    """
    apply_global_styles()
    render_sidebar()

    # 현재 선택된 페이지에 따른 콘텐츠 렌더링
    route_to_page()


# ========================================
# MAIN EXECUTION - 메인 실행부
# ========================================


def main():
    """
    애플리케이션 엔트리 포인트

    Flow:
        1. 페이지 설정
        2. 세션 상태 초기화
        3. OAuth 콜백 처리
        4. 인증 상태에 따른 페이지 라우팅
    """
    # 페이지 설정을 가장 먼저 해야 함
    st.set_page_config(
        page_title="FIREgenerator", layout="wide", initial_sidebar_state="expanded"
    )

    # 세션 상태 초기화
    if "role" not in st.session_state:
        st.session_state.role = None

    if "current_page" not in st.session_state:
        st.session_state.current_page = "chatbot"

    # OAuth 콜백 처리 (페이지 로드시마다 확인)
    check_auth_params()

    # 인증 상태 확인 및 페이지 라우팅
    if (
        "role" in st.session_state
        and st.session_state.role in ["User", "Admin"]
        and "user" in st.session_state
    ):
        # 로그인된 사용자: 메인 앱 실행
        main_app()
    else:
        # 미로그인 사용자: 로그인 페이지 표시
        pg = st.navigation([st.Page(login)])  # type: ignore
        pg.run()


# 애플리케이션 실행
if __name__ == "__main__":
    main()
