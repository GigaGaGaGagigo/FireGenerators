import streamlit as st

st.title("Chatbot")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# 메시지 전체 삭제 버튼
if st.button("메시지 전체 삭제"):
    st.session_state.chat_history = []
    st.rerun()

# 메시지 리스트 + 개별 삭제 버튼 (한 번만!)
for i, message in enumerate(st.session_state.chat_history):
    col1, col2 = st.columns([10, 1])
    with col1:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    with col2:
        if st.button("❌", key=f"delete_{i}"):
            st.session_state.chat_history.pop(i)
            st.rerun()
            break

user_input = st.chat_input("답변을 입력해주세요.")

if user_input:
    with st.chat_message("user"):
        st.write(user_input)
    st.session_state.chat_history.append({"role": "user", "content": user_input})

    assistant_response = f"assistant response: {user_input}"
    with st.chat_message("자산구조대 🧯"):
        st.write(assistant_response)
    st.session_state.chat_history.append(
        {"role": "자산구조대 🧯", "content": assistant_response}
    )


st.write(st.session_state.asset_data)
