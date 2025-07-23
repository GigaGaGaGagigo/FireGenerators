import streamlit as st
from supabase import create_client, Client


st.markdown(
    """
    <center>
        <h1>💁 회원 가입</h1>
    </center>
    """,
    unsafe_allow_html=True,
)

supabase: Client = st.session_state.supabase

if "regester_data" in st.session_state:
    del st.session_state.register_data

with st.form("register_form"):
    name: str = st.text_input("당신의 나이는 몇 살인가요?")
    reason: str = st.text_input("FIREgenerator를 시작하게 된 계기를 말씀해주세요.")
    goal: str = st.text_input("자산 운용의 목표는 무엇인가요?")
    period: str = st.text_input("자산 운용 기간은 얼마인가요?")
    experience: str = st.selectbox("자산 운용 경험이 있나요?", ["예", "아니오"])
    next_page: bool = st.form_submit_button("다음")

    if next_page:
        register_data: dict[str, str] = {
            "name": name,
            "reason": reason,
            "goal": goal,
            "period": period,
            "experience": experience,
        }

        st.session_state.register_data = register_data

        st.switch_page("register/survey.py")
