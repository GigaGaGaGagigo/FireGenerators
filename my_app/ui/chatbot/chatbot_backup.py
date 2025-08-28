import time
from pathlib import Path

import streamlit as st
from langchain_core.runnables import RunnableConfig
from typing_extensions import Any, Iterator

# answer_handler.py 제거됨 - 인라인 구현으로 대체
from my_app.chatbot.langgraph_core.graph_builder import GraphBuilder
from my_app.chatbot.langgraph_core.state import OverallState
from my_app.chatbot.utils.state_helpers import (
    check_and_resume_workflow,
    debug_state_info,
    get_current_question_info,
    get_current_state,
    sync_quiz_data_to_session,
)

IMAGE_PATH: Path = Path(__file__).parents[2] / "assets" / "FIRE_LOGO_large.png"

CATEGORY_KEYS: list[str] = [
    "investment_emotions",
    "investment_goal",
    "investment_level",
    "interests_categories",
    "knowledge_level",
    "risk_tolerance",
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
        # st.session_state.graph.display_node_design()
        st.session_state.config = RunnableConfig(
            recursion_limit=50,
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

        st.session_state["chatbot"] = {}
        st.session_state["chatbot"]["logs"] = []


def create_chat_graph():
    return GraphBuilder().build_workflow()


def stream_text(message: str) -> Iterator[str]:
    for char in message:
        yield char
        time.sleep(STREAM_DELAY_S)


def create_answer_callback(question_info: dict, current_category: str):
    """
    Factory function to create an answer callback function.

    Args:
        question_info: current question information
        current_category: current category

    Returns:
        callable: answer callback function
    """

    def answer_callback():
        try:
            idx_key = f"question_radio_{question_info['index']}"
            choice = st.session_state.get(idx_key)

            if choice:
                if current_category in st.session_state.get("user_answers", {}):
                    st.session_state["user_answers"][current_category].append(
                        (question_info["question"], choice)
                    )
                    session_log: dict[str, float | str] = {
                        "level": "info",
                        "message": f"The answer has been saved. category: {current_category}, question: {question_info['question']}, choice: {choice}",
                        "timestamp": time.time(),
                        "location": "create_answer_callback, after save_answer",
                    }
                    st.session_state["chatbot"]["logs"].append(session_log)

                    if question_info["index"] + 1 >= question_info["total"]:
                        session_log: dict[str, float | str] = {
                            "level": "info",
                            "message": f"The workflow has been done. category: {current_category}",
                            "timestamp": time.time(),
                            "location": "create_answer_callback, after check_and_resume_workflow",
                        }
                        st.session_state["chatbot"]["logs"].append(session_log)
                        check_and_resume_workflow()
                    else:
                        session_log: dict[str, float | str] = {
                            "level": "info",
                            "message": f"The workflow has been resumed. category: {current_category}",
                            "timestamp": time.time(),
                            "location": "create_answer_callback, after check_and_resume_workflow",
                        }
                        st.session_state["chatbot"]["logs"].append(session_log)
                    st.rerun()
                else:
                    session_log: dict[str, float | str] = {
                        "level": "error",
                        "message": f"The answer is not saved. category: {current_category}",
                        "timestamp": time.time(),
                        "location": "create_answer_callback, after save_answer",
                    }
                    st.session_state["chatbot"]["logs"].append(session_log)
                    st.stop()
        except Exception as e:
            session_log: dict[str, float | str] = {
                "level": "error",
                "message": f"Error: {e}",
                "timestamp": time.time(),
                "location": "create_answer_callback, after exception",
            }
            st.session_state["chatbot"]["logs"].append(session_log)
            st.stop()

    return answer_callback


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
        # debug logs TODO: Delete this code part after making logging system, 2025-08-23
        with st.expander("Debug Logs"):
            if st.session_state.get("ai", {}).get("initialized", False):
                st.write("**Graph State:**")
                debug_info: dict[str, Any] = debug_state_info()
                st.json(debug_info)

        if st.session_state.get("ai", {}).get("initialized", False):
            try:
                # handler for checking if the LangGraph workflow has been resumed
                if check_and_resume_workflow():
                    # if the workflow has been resumed, wait for a moment and re-render

                    # logging when the workflow has been resumed
                    session_log: dict[str, float | str] = {
                        "level": "info",
                        "message": "The workflow has been resumed.",
                        "timestamp": time.time(),
                        "location": "render_quiz, after check_and_resume_workflow",
                    }
                    st.session_state["chatbot"]["logs"].append(session_log)
                    st.rerun()

                state: OverallState | None = get_current_state()

                if state is None:
                    # loggging when the graph state is not found
                    session_log: dict[str, float | str] = {
                        "level": "warning",
                        "message": "The graph state is not found.",
                        "timestamp": time.time(),
                        "location": "render_quiz, after get_current_state",
                    }
                    st.session_state["chatbot"]["logs"].append(session_log)

                    # re-render the page for emergency
                    if st.button("rerun"):
                        st.rerun()

                # check if the current category is set
                if (
                    state is not None
                    and hasattr(state, "target_profile_category")
                    and state.target_profile_category is not None
                    and len(state.target_profile_category) > 0
                ):
                    current_category: str = state.target_profile_category[0]

                    # sync quiz data to session
                    if sync_quiz_data_to_session(state, current_category):
                        # get current question information
                        question_info = get_current_question_info(current_category)

                        # TODO:  showing progress bar is necessary?
                        if question_info:
                            progress: float = (
                                question_info["index"] / question_info["total"]
                            )
                            st.progress(
                                progress,
                                text=f"[{current_category}] Progress: {question_info['index']}/{question_info['total']}",
                            )

                            # display question
                            st.write_stream(stream_text(question_info["question"]))

                            # factory pattern for answer callback - st.radio can't get additional arguments
                            idx_key = f"question_radio_{question_info['index']}"
                            answer_callback = create_answer_callback(
                                question_info, current_category
                            )

                            st.radio(
                                "옵션을 선택하세요:",
                                options=question_info["options"],
                                key=idx_key,
                                index=None,
                                on_change=answer_callback,
                            )
                        else:
                            session_log: dict[str, float | str] = {
                                "sender": "streamlit",
                                "level": "warning",
                                "message": "The question information is not found.",
                                "timestamp": time.time(),
                                "location": "render_quiz, after get_current_question_info",
                            }
                            st.session_state["chatbot"]["logs"].append(session_log)
                            st.stop()
                    else:
                        session_log: dict[str, float | str] = {
                            "level": "error",
                            "message": "Failed to sync quiz data.",
                            "timestamp": time.time(),
                            "location": "render_quiz, after sync_quiz_data_to_session",
                        }
                        st.session_state["chatbot"]["logs"].append(session_log)
                        st.stop()
                else:
                    session_log: dict[str, float | str] = {
                        "level": "info",
                        "message": "The workflow has been resumed.",
                        "timestamp": time.time(),
                        "location": "render_quiz, after check_and_resume_workflow",
                    }
                    st.session_state["chatbot"]["logs"].append(session_log)
                    st.balloons()

            except Exception as e:
                session_log: dict[str, float | str] = {
                    "level": "error",
                    "message": f"Error: {e}",
                    "timestamp": time.time(),
                    "location": "render_quiz, after exception",
                }
                st.session_state["chatbot"]["logs"].append(session_log)
                st.stop()
        else:
            session_log: dict[str, float | str] = {
                "level": "info",
                "message": "The workflow is not initialized.",
                "timestamp": time.time(),
                "location": "render_quiz, after exception",
            }
            st.session_state["chatbot"]["logs"].append(session_log)


def render():
    initialize_chatbot()

    # 커스텀 CSS 적용
    css_path = str(Path(__file__).parents[2] / "assets" / "style.css")
    load_css(css_path)

    _, left_screen, right_screen, _ = st.columns([0.1, 0.4, 0.4, 0.1], border=False)

    with left_screen:
        quiz_placeholder = st.container(border=True, height=850)

    with right_screen:
        with st.container(border=True, height=850):
            if not st.session_state.get("ai", {}).get("initialized", False):
                with st.status(
                    "AI를 불러오고 있습니다. 잠시만 기다려주세요.", expanded=True
                ) as status:
                    st.write("Loading User Data...")
                    user_data: dict = st.session_state.user_data
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
                        label="Initialization complete!",
                        state="complete",
                        expanded=False,
                    )

            if st.session_state.get("ai", {}).get("initialized", False):
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
                            quiz_rendered = (
                                True  # 왜 ? message가 추가 되어야지만 퀴즈를 출력 ??
                            )
                            st.rerun()
                        else:
                            with st.chat_message("ai"):
                                st.write(last_msg.content)

                    conclusion = getattr(state, "conclusion", None)

                    if conclusion:
                        with st.chat_message("ai"):
                            st.write_stream(stream_text(conclusion))

                    if not quiz_rendered:
                        render_quiz(quiz_placeholder)


if __name__ == "__main__":
    render()
