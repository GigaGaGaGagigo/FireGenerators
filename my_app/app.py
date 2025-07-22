import streamlit as st
import requests

st.title("금융용어 챗봇")
query = st.text_input("궁금한 금융 용어를 입력하세요")
if st.button("질문하기"):
    res = requests.get("http://localhost:8000/ask", params={"query": query})
    st.markdown(f"### 💡 답변: {res.json()['answer']}")
    try:
        if res.status_code == 200:
            json_data = res.json()
            st.markdown(f"### 💡 답변: {json_data.get('answer', '답변 없음')}")
        else:
            st.error(f"❌ 서버 오류: {res.status_code}\n\n{res.text}")
    except requests.exceptions.JSONDecodeError:
        st.error(f"❌ 응답이 JSON 형식이 아닙니다:\n\n{res.text}")
