import sys
import time
from pathlib import Path

import streamlit as st
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, Interrupt
from typing_extensions import Iterator

sys.path.append(str(Path(__file__).parents[3]))

try:
    from my_app.chatbot.langgraph_core.graph_builder import GraphBuilder
    from my_app.chatbot.langgraph_core.state import InputState
    from my_app.chatbot.langgraph_core.state.state import OverallState
    from my_app.chatbot.services import ProfileService
    from my_app.chatbot.utils import (
        CATEGORY_KEYS,
        # debug_state_info,
        determine_profile_status,
        find_missing_profile_categories,
        get_current_question_info,
        sync_questions,
    )
except ImportError as e:
    st.write(f"Error: {e}")
    raise e


IMAGE_PATH: Path = Path(__file__).parents[2] / "assets" / "FIRE_LOGO_large.png"


USER_DATA_KEY: list[str] = [
    "ai",
    "quiz",
    "user_answers",
    "toolupdated_profile",
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
        st.session_state.config = RunnableConfig()
        st.session_state["ai"] = {}
        st.session_state["ai"]["initialized"] = False
        st.session_state["ai"]["messages"] = []
        st.session_state["ai"]["last_message"] = None
        st.session_state["ai"]["message_count"] = 0
        st.session_state["state_result"] = {}
        st.session_state["tool"] = {}
        st.session_state["tool"]["tool_call_id"] = None
        st.session_state["tool"]["tool_call_name"] = None
        st.session_state["quiz"] = {}
        st.session_state["user_answers"] = {}

        for category in CATEGORY_KEYS:
            st.session_state["quiz"][category] = {"questions": [], "options": []}
            st.session_state["quiz"][category]["synced"] = False
            st.session_state["updated_profile"] = {}
            st.session_state["user_answers"][category] = []
            st.session_state["updated_profile"][category] = []

        st.session_state["chatbot"] = {}
        st.session_state["chatbot"]["logs"] = []
        st.session_state["events"] = []
        st.session_state["updates"] = []
        st.session_state["interrupts"] = []
        st.session_state["quiz_rendered_at_options"] = False


def create_chat_graph():
    return GraphBuilder().build_workflow()


def stream_text(message: str) -> Iterator[str]:
    for char in message:
        yield char
        time.sleep(STREAM_DELAY_S)


def check_and_submit_tool_response(current_category: str):
    user_answers: list[tuple[str, str]] = st.session_state.get("user_answers", {}).get(
        current_category, []
    )

    quiz_questions: list[str] = (
        st.session_state.get("quiz", {}).get(current_category, {}).get("questions", [])
    )

    # check if all questions have been answered
    if len(user_answers) >= len(quiz_questions) and len(quiz_questions) > 0:
        try:
            st.session_state["user_answers"][current_category] = []
            st.session_state["quiz"][current_category]["questions"] = []
            st.session_state["quiz"][current_category]["options"] = []
            st.session_state["quiz"][current_category]["synced"] = False

            run_graph(resume=True, resume_data=user_answers)

            # logging
            session_log: dict[str, float | str] = {
                "level": "info",
                "message": "The workflow has been automatically resumed.",
                "timestamp": time.time(),
                "location": "check_and_resume_workflow, after invoke",
            }
            st.session_state["chatbot"]["logs"].append(session_log)

            st.rerun()

        except Exception as e:
            # logging
            session_log: dict[str, float | str] = {
                "level": "warning",
                "message": f"failed to resume the workflow: {e}",
                "timestamp": time.time(),
                "location": "check_and_resume_workflow, after invoke",
            }
            st.session_state["chatbot"]["logs"].append(session_log)


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
                    updated_answers = st.session_state["user_answers"][
                        current_category
                    ][:]
                    updated_answers.append((question_info["question"], choice))
                    st.session_state["user_answers"][current_category] = updated_answers

                    session_log: dict[str, float | str] = {
                        "level": "info",
                        "message": f"The answer has been saved. category: {current_category}, question: {question_info['question']}, choice: {choice}",
                        "timestamp": time.time(),
                        "location": "create_answer_callback, after save_answer",
                    }
                    st.session_state["chatbot"]["logs"].append(session_log)

                else:
                    session_log: dict[str, float | str] = {
                        "level": "error",
                        "message": f"The answer is not saved. category: {current_category}",
                        "timestamp": time.time(),
                        "location": "create_answer_callback, after save_answer",
                    }
                    st.session_state["chatbot"]["logs"].append(session_log)

        except Exception as e:
            session_log: dict[str, float | str] = {
                "level": "error",
                "message": f"Error: {e}",
                "timestamp": time.time(),
                "location": "create_answer_callback, after exception",
            }
            st.session_state["chatbot"]["logs"].append(session_log)

    return answer_callback


def run_graph(
    state: InputState | OverallState | None = None,
    resume: bool = False,
    resume_data: list[tuple[str, str]] = [],
):
    graph = st.session_state.graph
    config = st.session_state.config

    if resume:
        for event in graph.stream(
            Command(resume=resume_data), config=config, stream_mode="updates"
        ):
            st.session_state["events"] += event
            key = list(event.keys())[0]
            update = event[key]

            if key != "__interrupt__":
                if "messages" in update and update["messages"]:
                    if (
                        isinstance(update["messages"][-1], AIMessage)
                        and update["messages"][-1].content != ""
                    ):
                        st.session_state["ai"]["last_message"] = update["messages"][
                            -1
                        ].content

            else:
                if isinstance(update[0], Interrupt):
                    interrupt_obj = update[0]
                    st.session_state["interrupts"].append(interrupt_obj)

            #  render_quiz(st.session_state["quiz_placeholder"])
    else:
        for event in graph.stream(
            state,
            config=config,
            stream_mode="updates",
        ):
            st.session_state["events"] += event
            key = list(event.keys())[0]
            update = event[key]

            if key != "__interrupt__":
                if "messages" in update and update["messages"]:
                    if (
                        isinstance(update["messages"][-1], AIMessage)
                        and update["messages"][-1].content != ""
                    ):
                        st.session_state["ai"]["last_message"] = update["messages"][
                            -1
                        ].content

            else:
                if isinstance(update[0], Interrupt):
                    interrupt_obj = update[0]
                    st.session_state["interrupts"].append(interrupt_obj)

            #   render_quiz(st.session_state["quiz_placeholder"])


def render_quiz(container):
    with container:
        # debug logs
        with st.expander("Debug Logs"):
            graph_state: OverallState | None = st.session_state.graph.get_state(
                st.session_state.config
            )
            st.write(graph_state)

        if not st.session_state.get("interrupts"):
            return

        graph_state: OverallState | None = st.session_state.graph.get_state(
            st.session_state.config
        )

        user_meta_data = getattr(graph_state, "user_meta_data", {})

        if user_meta_data.get("profile_status", "") == "completed":
            st.empty()
            st.balloons()
            return

        current_category = sync_questions()

        if not current_category:
            return

        check_and_submit_tool_response(current_category)

        if st.session_state["quiz"][current_category].get("synced", False):
            question_info = get_current_question_info(current_category)

            if question_info:
                progress = question_info["index"] / question_info["total"]
                st.progress(
                    progress,
                    text=f"[{current_category}] Progress: {question_info['index']}/{question_info['total']}",
                )
                st.write_stream(stream_text(question_info["question"]))

                idx_key = f"question_radio_{question_info['index']}"

                # 콜백 함수 생성
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


def render_chat(container):
    with container:
        messages = st.session_state.get("ai", {}).get("messages", [])
        last_message = st.session_state.get("ai", {}).get("last_message", None)

        if len(messages) == 0 or last_message != messages[-1]:
            if messages:
                with st.chat_message("ai"):
                    st.write(messages)

            with st.chat_message("ai"):
                st.write_stream(stream_text(last_message))

            st.session_state.get("ai", {}).get("messages").append(last_message)
        else:
            for message in messages:
                with st.chat_message("ai"):
                    st.write(message)

        # st.write(st.session_state["events"])


def render():
    initialize_chatbot()

    # 커스텀 CSS 적용
    css_path = str(Path(__file__).parents[2] / "assets" / "style.css")
    load_css(css_path)

    _, left_screen, right_screen, _ = st.columns([0.1, 0.4, 0.4, 0.1], border=False)

    with left_screen:
        st.session_state["quiz_placeholder"] = st.container(border=True, height=850)

    with right_screen:
        st.session_state["chat_placeholder"] = st.container(border=True, height=850)

    if not st.session_state.get("ai", {}).get("initialized", False):
        user_data: dict = st.session_state.user_data
        user_name: str = user_data["name"]
        profile_status: str = determine_profile_status(user_data)
        categories_to_update: list[str] | None = find_missing_profile_categories(
            user_data
        )

        config = RunnableConfig(
            recursion_limit=50,
            configurable={
                "thread_id": "1",
                "profile_service": ProfileService(
                    st.session_state.supabase, st.session_state.user.id
                ),
            },
        )
        st.session_state.config = config
        st.session_state["ai"]["initialized"] = True

        user_data = InputState(
            target_profile_category=categories_to_update,
            user_meta_data={
                "name": user_name,
                "profile_status": profile_status,
                "investment_goal": user_data["investment_goal"],
                "investment_emotions": user_data["investment_emotions"],
                "interests_categories": user_data["interests_categories"],
                "investment_level": user_data["investment_level"],
                "knowledge_level": user_data["knowledge_level"],
                "risk_tolerance": user_data["risk_tolerance"],
            },
        )

        # user_data = InputState(
        #     target_profile_category=[
        #         "investment_goal",
        #         "investment_emotions",
        #         "interests_categories",
        #         "investment_level",
        #         "knowledge_level",
        #         "risk_tolerance",
        #     ],
        #     user_meta_data={
        #         "name": "강요셉",
        #         "profile_status": "onboarding",
        #         "investment_goal": [],
        #         "investment_emotions": [],
        #         "interests_categories": [],
        #         "investment_level": [],
        #         "knowledge_level": [],
        #         "risk_tolerance": 0,
        #     },
        # )

        run_graph(user_data, resume=False)

        st.write(st.session_state["chatbot"]["logs"])

    render_chat(st.session_state["chat_placeholder"])
    render_quiz(st.session_state["quiz_placeholder"])

    # st.write(st.session_state["interrupts"])


if __name__ == "__main__":
    render()
