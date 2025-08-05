from streamlit_option_menu import option_menu
import streamlit as st

st.set_page_config(page_title="FIREgenerator", layout="wide")

# ----- Top Header Layout -----
st.markdown(
    """
    <style>
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 5px 5px;
            border-bottom: 1px solid #e0e0e0;
        }
        .header-left {
            font-size: 24px;
            font-weight: bold;
            color: #273F4F;
        }
        .header-right {
            display: flex;
            gap: 24px;
            font-size: 14px;
            color: #465461;
            align-items: center;
        }
        .header-right span {
            cursor: pointer;
        }
    </style>

    <div class="header">
        <div class="header-left">
        FIREgenerator
        </div>
        <div class="header-right">
            <span>About us</span>
            <span>Our Team</span>
            <span>👤 로그인됨: <b>green</b></span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

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
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    selected = option_menu(
        menu_title=None,
        options=[
            "Chatbot",
            "오늘의 퀴즈",
            "오늘의 콘텐츠",
            "맞춤형 상품 추천",
            "투자 시뮬레이션",
            "모의 투자 및 분석",
            "Setting",
            "Logout",
        ],
        icons=[
            "chat-dots", "question-circle", "book", "gift",
            "graph-up", "bar-chart-line", "gear", "box-arrow-right"
        ],
        default_index=0,
        styles={
            "container": {"padding": "0", "background-color": "#F2F2F2"},
            "icon": {"color": "#273F4F", "font-size": "18px"},  # 기본 아이콘 색
            "nav-link": {
                "font-size": "16px",
                "text-align": "left",
                "--hover-color": "#FEE5A5",  # hover 배경색
            },
            "nav-link-selected": {
                "background-color": "#FE7743",
                "color": "white",
                "icon" : "white"            
            },
        },
    )
    
# ----- Page Routing -----
# 각 메뉴에 맞는 페이지 불러오기. 실제 파일 경로에 맞게 수정 필요
if selected == "Chatbot": # 현재는 테스트 파일로 라우팅 처리된 상태
    import chatbot_test as page
    page.run()

# elif selected == "오늘의 퀴즈":
#     import pages.quiz as page
#     page.run()

# elif selected == "오늘의 콘텐츠":
#     import pages.content as page
#     page.run()

# elif selected == "맞춤형 상품 추천":
#     import pages.recommendation as page
#     page.run()

# elif selected == "시뮬레이션":
#     import pages.simulation as page
#     page.run()

# elif selected == "모의 투자 및 분석":
#     import pages.analysis as page
#     page.run()

# elif selected == "Setting":
#     import pages.settings as page
#     page.run()

# elif selected == "Logout":
#     import pages.logout as page
#     page.run()