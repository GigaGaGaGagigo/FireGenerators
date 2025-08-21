import time
from pathlib import Path

import streamlit as st
from langchain_core.runnables import RunnableConfig
from typing_extensions import Iterator

from ui.chatbot.handlers.answer_handler import create_answer_callback
from ui.chatbot.langgraph_core.graph_builder import GraphBuilder
from ui.chatbot.utils.state_helpers import (
    debug_state_info,
    get_current_question_info,
    get_current_state_safely,
    sync_quiz_data_to_session,
    validate_session_state,
)

IMAGE_PATH: Path = Path(__file__).parents[2] / "assets" / "FIRE_LOGO_large.png"

CATEGORY_KEYS: list[str] = [
    "investment_goal",
    "investment_emotions",
    "interests_categories",
    "investment_level",
    "knowledge_level",
]

USER_DATA_KEY: list[str] = [
    "ai",
    "quiz",
    "user_answers",
    "updated_profile",
    "state_result",
]

STREAM_DELAY_S = 0.01
STREAMLIT_SLEEP_S = 0.5


def load_css(file_path: str) -> None:
    """Injects custom CSS into the Streamlit app."""
    with open(file_path, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def initialize_chatbot():
    if "graph" not in st.session_state:
        st.session_state.graph = create_chat_graph()
        st.session_state.config = RunnableConfig(
            configurable={"thread_id": "1"},
        )
        st.session_state["ai"] = {}
        st.session_state["ai"]["initialized"] = False
        st.session_state["ai"]["messages"] = []
        st.session_state["ai"]["message_trigger"] = False
        st.session_state["ai"]["prev_message"] = None
        st.session_state["ai"]["message_count"] = 0
        st.session_state["quiz"] = {}
        st.session_state["user_answers"] = {}
        st.session_state["updated_profile"] = {}
        st.session_state["state_result"] = {}

        for category in CATEGORY_KEYS:
            st.session_state["quiz"][category] = {"questions": [], "options": []}
            st.session_state["user_answers"][category] = []
            st.session_state["updated_profile"][category] = []


def create_chat_graph() -> GraphBuilder:
    return GraphBuilder(
        interrupt_before=["generate_follow_up_questions", "analyze_user_goal"]
    )


def stream_text(message: str) -> Iterator[str]:
    for char in message:
        yield char
        time.sleep(STREAM_DELAY_S)


def determine_profile_status(user_data: dict) -> str:
    categories_to_check: list[bool] = []

    for key in CATEGORY_KEYS:
        value: list[str] | str | None = user_data.get(key)
        if isinstance(value, list):
            if len(value) == 0:
                categories_to_check.append(True)
            else:
                categories_to_check.append(False)
        elif value is None:
            categories_to_check.append(True)
        else:
            categories_to_check.append(False)

    all_none: bool = all(categories_to_check)
    any_set: bool = any(categories_to_check)

    if all_none:
        return "onboarding"

    if any_set:
        return "editing"

    return "completed"


def find_missing_profile_categories(user_data: dict) -> list[str] | None:
    categories_to_update: list[str] = []

    for key in CATEGORY_KEYS:
        value: list[str] | str | None = user_data.get(key)
        if isinstance(value, list):
            if len(value) == 0:
                categories_to_update.append(key)
        elif value is None:
            categories_to_update.append(key)

    return categories_to_update


def render_quiz(container):
    with container:
        st.write("### 퀴즈")

        # Debug log expander
        with st.expander("디버그 로그"):
            if st.session_state.get("ai", {}).get("initialized", False):
                st.write("**Graph State:**")
                debug_info = debug_state_info()
                st.json(debug_info)

        # 세션 상태 검증
        if not validate_session_state():
            st.error("시스템 초기화가 완료되지 않았습니다. 페이지를 새로고침해주세요.")
            return

        if st.session_state.get("ai", {}).get("initialized", False):
            state = get_current_state_safely()

            if state is None:
                st.error("그래프 상태를 가져올 수 없습니다.")
                return

            # 현재 진행 중인 카테고리 확인
            if (
                hasattr(state, "target_profile_category")
                and len(state.target_profile_category) > 0
            ):
                current_category = state.target_profile_category[0]

                # 퀴즈 데이터 동기화
                if sync_quiz_data_to_session(state, current_category):
                    # 현재 질문 정보 가져오기
                    question_info = get_current_question_info(current_category)

                    if question_info:
                        # 질문 표시
                        st.write_stream(stream_text(question_info["question"]))

                        # 답변 옵션 표시
                        idx_key = f"question_radio_{question_info['index']}"

                        answer_callback = create_answer_callback(
                            question_text=question_info["question"],
                            total_questions=question_info["total"],
                            current_q_index=question_info["index"],
                            category_key=current_category,
                            idx_key=idx_key,
                        )

                        st.radio(
                            "옵션을 선택하세요:",
                            options=question_info["options"],
                            key=idx_key,
                            index=None,
                            on_change=answer_callback,
                        )
                    else:
                        st.info("질문을 불러오는 중입니다...")
                else:
                    st.error("퀴즈 데이터 동기화에 실패했습니다.")
            else:
                # 모든 퀴즈가 완료되었을 때 메시지 표시
                st.success("프로필 생성이 완료되었습니다! ✨")
                st.info("오른쪽 화면에서 최종 결과를 확인하세요.")
                st.balloons()


def render():
    initialize_chatbot()

    # 커스텀 CSS 적용 - 소희님 render 시작 부분에 추가하시면 됩니다.
    css_path = str(Path(__file__).parents[2] / "assets" / "style.css")
    load_css(css_path)

    margin_1, left_screen, right_screen, margin_2 = st.columns(
        [0.1, 0.4, 0.4, 0.1], border=False
    )

    with left_screen:
        quiz_placeholder = st.container(border=True, height=850)

    with right_screen:
        with st.container(border=True, height=850):
            if not st.session_state.get("ai", {}).get("initialized", False):
                with st.status(
                    "AI를 불러오고 있습니다. 잠시만 기다려주세요.", expanded=True
                ) as status:
                    st.write("Loading User Data...")
                    user_data = st.session_state.user_data
                    user_name: str = user_data["name"]

                    profile_status: str = determine_profile_status(user_data)
                    categories_to_update: list[str] | None = (
                        find_missing_profile_categories(user_data)
                    )
                    st.write("Loading User Data... Done")
                    time.sleep(STREAMLIT_SLEEP_S)
                    st.write("Loading AI...")
                    try:
                        st.session_state.graph.invoke(
                            input={
                                "user_name": user_name,
                                "profile_status": profile_status,
                                "target_profile_category": categories_to_update,
                            },
                            config=st.session_state.config,
                        )
                        st.session_state["ai"]["initialized"] = True
                        time.sleep(STREAMLIT_SLEEP_S)
                        st.write("Loading AI... Done")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: Initialize graph failed. {e}")
                        time.sleep(STREAMLIT_SLEEP_S)
                        st.write("Loading AI... Failed")
                    time.sleep(STREAMLIT_SLEEP_S)

                    status.update(
                        label="Download complete!", state="complete", expanded=False
                    )

            if st.session_state.get("ai", {}).get("initialized", False):
                st.write("### 챗봇")
                state = st.session_state.graph.get_state(st.session_state.config)

                if state is not None:
                    ai_messages = list(getattr(state, "ai_messages", []))
                    is_new_message = (
                        len(ai_messages) > st.session_state.ai["message_count"]
                    )

                    for msg in ai_messages[:-1]:
                        with st.chat_message("ai"):
                            st.write(msg.content)

                    quiz_rendered = False
                    if ai_messages:
                        last_msg = ai_messages[-1]
                        if is_new_message:
                            with st.chat_message("ai"):
                                st.write_stream(stream_text(last_msg.content))
                            st.session_state.ai["message_count"] = len(ai_messages)
                            render_quiz(quiz_placeholder)
                            quiz_rendered = True
                            st.rerun()
                        else:
                            with st.chat_message("ai"):
                                st.write(last_msg.content)

                    conclusion = getattr(state, "conclusion", None)
                    if conclusion:
                        with st.chat_message("assistant"):
                            st.write_stream(stream_text(conclusion))

                    if not quiz_rendered:
                        render_quiz(quiz_placeholder)


if __name__ == "__main__":
    render()
