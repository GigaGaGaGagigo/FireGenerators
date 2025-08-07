import streamlit as st
from streamlit_option_menu import option_menu
from supabase import create_client, Client
from pathlib import Path

# 페이지 임포트
from ui import login
from ui.chatbot import chatbot_sample
from ui.dashboard import dashboard_sample
from ui.settings import settings_sample
from ui.admin import admin_sample

ROLES: list[str | None] = [None, "User", "Admin"]

@st.cache_resource
def init_supabase():
    try:
        supabase: Client = create_client(
            st.secrets["supabase"]["url"], st.secrets["supabase"]["key"]
        )
        return supabase
    except Exception as e:
        st.error(f"Error initializing Supabase: {e}")
        st.stop()

def check_auth_params():
    query_params = st.query_params

    if "code" in query_params:
        code = query_params["code"]
        supabase = init_supabase()
        st.session_state.supabase = supabase

        try:
            response = supabase.auth.exchange_code_for_session({"auth_code": code})

            if response.session:
                st.session_state.session = response.session
                st.session_state.user = response.user

                response_user_data = (
                    supabase.table("users")
                    .select("*")
                    .eq("user_email", st.session_state.user.email)
                    .execute()
                )

                if response_user_data.data:
                    st.session_state.role = response_user_data.data[0]["role"]
                else:
                    st.session_state.role = "User"

                st.query_params.clear()
                st.rerun()

        except Exception as e:
            st.error(f"Authentication failed: {e}")
            st.query_params.clear()

def logout():
    if "session" in st.session_state and st.session_state.session:
        supabase = init_supabase()
        try:
            supabase.auth.sign_out()
        except:
            pass

    for key in ["session", "user", "role", "current_page"]:
        if key in st.session_state:
            del st.session_state[key]

    st.rerun()

def render_sidebar():
    """커스텀 사이드바 렌더링"""
    with st.sidebar:
        try:
            logo_path = Path(__file__).parent / "assets" / "FIREgen_horizontal_logo.png"
            if logo_path.exists():
                st.image(logo_path, width=200)
        except:
            st.markdown("## FIREgenerator")
        
        user_email = st.session_state.user.email if "user" in st.session_state else "Unknown"
        st.success(f"로그인됨: {user_email}")
        
        # 역할에 따른 메뉴 구성
        if st.session_state.role == "Admin":
            menu_options = [
                "Chatbot", "Dashboard", "Admin 1", "Admin 2", 
                "Settings", "Logout"
            ]
            menu_icons = [
                "chat-dots", "bar-chart-line", "person-add", "security",
                "gear", "box-arrow-right"
            ]
            page_mapping = {
                "Chatbot": "chatbot",
                "Dashboard": "dashboard", 
                "Admin 1": "admin1",
                "Admin 2": "admin2",
                "Settings": "settings",
                "Logout": "logout"
            }
        else:
            menu_options = [
                "Chatbot", "오늘의 퀴즈", "오늘의 콘텐츠", "맞춤형 상품 추천",
                "투자 시뮬레이션", "모의 투자 및 분석", "Settings", "Logout"
            ]
            menu_icons = [
                "chat-dots", "question-circle", "book", "gift",
                "graph-up", "bar-chart-line", "gear", "box-arrow-right"
            ]
            page_mapping = {
                "Chatbot": "chatbot",
                "오늘의 퀴즈": "quiz",
                "오늘의 콘텐츠": "content", 
                "맞춤형 상품 추천": "recommendation",
                "투자 시뮬레이션": "simulation",
                "모의 투자 및 분석": "analysis",
                "Settings": "settings",
                "Logout": "logout"
            }
        
        # 현재 선택된 메뉴 찾기
        current_page = st.session_state.get("current_page", "chatbot")
        current_index = 0
        for i, (label, page_key) in enumerate(page_mapping.items()):
            if page_key == current_page:
                current_index = i
                break
        
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
        
        # 선택된 메뉴에 따라 페이지 변경
        new_page = page_mapping[selected]
        if new_page == "logout":
            logout()
        elif new_page != current_page:
            st.session_state.current_page = new_page
            st.rerun()

def render_header():
    """상단 헤더 렌더링"""
    user_email = st.session_state.user.email if "user" in st.session_state else "Unknown"
    user_name = user_email.split("@")[0] if "@" in user_email else "User"
    
    st.markdown(
        f"""
        <style>
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 5px 5px;
                border-bottom: 1px solid #e0e0e0;
                margin-bottom: 20px;
            }}
            .header-left {{
                font-size: 24px;
                font-weight: bold;
                color: #273F4F;
            }}
            .header-right {{
                display: flex;
                gap: 24px;
                font-size: 14px;
                color: #465461;
                align-items: center;
            }}
        </style>

        <div class="header">
            <div class="header-left">FIREgenerator</div>
            <div class="header-right">
                <span>About us</span>
                <span>Our Team</span>
                <span>👤 로그인됨: <b>{user_name}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

def apply_global_styles():
    """전체 애플리케이션 스타일 적용"""
    st.markdown(
        """
        <style>
            .css-1aumxhk { background-color: #F2F2F2; }
            .card {
                background-color: white;
                border-radius: 16px;
                padding: 24px;
                box-shadow: 0px 4px 16px rgba(0,0,0,0.05);
                height: 150px;
            }
            .card h3 {
                color: #FE7743;
                margin-bottom: 8px;
            }
            
            /* 채팅 입력창 스타일 개선 */
            .stChatInput {
                position: fixed !important;
                bottom: 20px !important;
                right: 20px !important;
                width: 48% !important;
                z-index: 999 !important;
                background-color: white !important;
                border-radius: 10px !important;
                box-shadow: 0px 4px 16px rgba(0,0,0,0.1) !important;
                padding: 10px !important;
            }
            
            .stChatInput > div {
                margin-bottom: 0 !important;
            }
            
            .stChatInput input {
                width: 100% !important;
                border-radius: 25px !important;
                border: 2px solid #FE7743 !important;
                padding: 12px 20px !important;
                font-size: 16px !important;
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
            
            /* 오른쪽 컬럼의 채팅 영역 높이 조정 */
            [data-testid="column"]:nth-child(2) {
                height: calc(100vh - 200px) !important;
                overflow-y: auto !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

def route_to_page():
    """페이지 라우팅"""
    current_page = st.session_state.get("current_page", "chatbot")
    
    # 각 페이지별 라우팅
    if current_page == "chatbot":
        chatbot_sample.render()
    elif current_page in ["dashboard", "analysis"]:
        dashboard_sample.render()
    elif current_page == "settings":
        settings_sample.render()
    elif current_page in ["admin1", "admin2"]:
        admin_sample.render(current_page)
    else:
        # 기본 페이지
        chatbot_sample.render()

def main_app():
    """메인 애플리케이션"""
    st.set_page_config(page_title="FIREgenerator", layout="wide")
    
    apply_global_styles()
    render_header()
    render_sidebar()
    
    # 페이지 라우팅
    route_to_page()

def main():
    if "role" not in st.session_state:
        st.session_state.role = None

    check_auth_params()

    if (
        "role" in st.session_state
        and st.session_state.role in ["User", "Admin"]
        and "user" in st.session_state
    ):
        main_app()
    else:
        login.render(init_supabase)

if __name__ == "__main__":
    main()