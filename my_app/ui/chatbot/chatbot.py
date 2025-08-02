import time
import uuid
from pathlib import Path

import streamlit as st

IMAGE_PATH = Path(__file__).parent.parent.parent / "assets" / "FIRE_LOGO_large.png"


def stream_data(message: str):
    for word in message:
        yield word
        time.sleep(0.01)


# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
    # 초기 봇 메시지 추가
    st.session_state.messages.append(
        {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": "Hello, I'm the FIREgenerator chatbot. How can I help you today?",
        }
    )

st.set_page_config(layout="wide")
margin_1, left_screen, right_screen, margin_2 = st.columns(
    [0.1, 0.4, 0.4, 0.1], border=True
)

with left_screen:
    with st.container(border=True):
        st.write("con1")
        st.image(IMAGE_PATH, width=200)

with right_screen:
    chat_message_area, chat_input_area = (
        right_screen.columns([1])[0].container(),
        right_screen.columns([1])[0].container(),
    )

    chat_message_area = right_screen.container(
        border=True, height=int(600 * 0.9)
    )  # 80% of 600px

    chat_input_area = right_screen.container(
        border=False, height=int(600 * 0.1)
    )  # 20% of 600px

    with chat_message_area:
        # 기존 메시지들 표시
        for i, message in enumerate(st.session_state.messages):
            with st.chat_message(message["role"]):
                # 가장 마지막 메시지이고 AI 메시지인 경우에만 stream 사용
                if (
                    i == len(st.session_state.messages) - 1
                    and message["role"] == "assistant"
                ):
                    st.write_stream(stream_data(message["content"]))
                else:
                    st.write(message["content"])

    with chat_input_area:
        # 채팅 입력 처리
        if prompt := st.chat_input("Type your message here"):
            # 사용자 메시지를 세션 상태에 추가
            st.session_state.messages.append(
                {"id": str(uuid.uuid4()), "role": "user", "content": prompt}
            )

            # 새로운 메시지가 추가되었으므로 페이지 새로고침
            st.rerun()
