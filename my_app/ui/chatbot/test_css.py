import streamlit as st
from pathlib import Path

def load_css(file_path: str) -> None:
    """Injects custom CSS into the Streamlit app."""
    with open(file_path, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

def render_test():
    """Renders a test page to check CSS application."""
    st.set_page_config(layout="wide")
    
    # Path to the existing CSS file
    css_path = str(Path(__file__).parents[2] / "assets" / "style.css")
    
    try:
        load_css(css_path)
        st.success("Successfully loaded style.css")
    except FileNotFoundError:
        st.error(f"Error: style.css not found at {css_path}")
        return

    st.title("CSS Test Page")
    st.info("This page tests if the custom CSS from style.css is being applied correctly.")

    margin_1, left_screen, right_screen, margin_2 = st.columns(
        [0.1, 0.4, 0.4, 0.1], border=False
    )

    with left_screen:
        with st.container(border=True, height=850):
            st.write("### 퀴즈 영역")
            st.write("이 컨테이너는 흰색 배경과 그림자 효과가 있어야 합니다.")

    with right_screen:
        with st.container(border=True, height=850):
            st.write("### 챗봇 영역")
            st.info("이 컨테이너의 배경색은 옅은 회색(#f8f9fa)이어야 합니다.")

            with st.chat_message("ai"):
                st.write("이것은 AI 채팅 메시지입니다. 옅은 회색 배경을 가져야 합니다.")

if __name__ == "__main__":
    render_test()
