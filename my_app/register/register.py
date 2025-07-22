import streamlit as st


st.title("Register 1")

with st.form("register_form"):
    name = st.text_input("당신의 나이는 몇 살인가요?")
    reason: st.text_input("FIREgenerator를 시작하게 된 계기를 말씀해주세요.")
    goal: st.text_input("자산 운용의 목표는 무엇인가요?")
    period: st.text_input("자산 운용 기간은 얼마인가요?")
    experience = st.selectbox("자산 운용 경험이 있나요?", ["예", "아니오"])
    submit = st.form_submit_button("Submit")
