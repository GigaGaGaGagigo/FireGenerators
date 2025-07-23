import streamlit as st


st.markdown(
    """
    <center>
        <h1>💁 투자 유형 설문</h1>
    </center>
    """,
    unsafe_allow_html=True,
)

if "current_question" in st.session_state:
    st.write(st.session_state.current_question)
    if st.session_state.current_question > 16:
        st.session_state.current_question = 0

if __file__.rfind("survey.py") != -1:
    if "current_question" not in st.session_state:
        st.session_state.current_question = 0
    if "answers" not in st.session_state:
        st.session_state.answers = []

# TODO: Load q&a from DB
questions: list[str] = [f"{i+1}. 질문" for i in range(16)]
choices: list[str] = ["①번 답변", "②번 답변", "③번 답변", "④번 답변"]

current = st.session_state.current_question

if current < len(questions):
    st.write(questions[current])

    cols = st.columns(len(choices))
    for button_num, col in enumerate(cols, start=1):
        if col.button(f"{button_num} 답변", key=f"answer_{current}_{button_num}"):
            st.session_state.answers.append(button_num)
            st.session_state.current_question += 1
            st.rerun()
else:
    st.success("설문이 완료되었습니다!")
    st.write("답변:", st.session_state.answers)
    if st.button("다음"):
        del st.session_state.answers
        st.session_state.current_question = 0
        st.switch_page("register/asset.py")
