import base64
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
    from my_app.chatbot.chat_core.graph_builder import GraphBuilder
    from my_app.chatbot.chat_core.state import InputState, OverallState
    from my_app.chatbot.services import ProfileService
    from my_app.chatbot.utils import (
        CATEGORY_KEYS,
        determine_profile_status,
        find_missing_profile_categories,
        get_current_question_info,
        sync_questions,
    )
except Exception as e:
    st.write(f"Error: {e}")
    raise e


IMAGE_PATH: Path = Path(__file__).parents[2] / "assets" / "FIRE_LOGO_large.png"
FINISHED_CHAT_IMAGE_PATH: Path = Path(__file__).parents[2] / "assets" / "2.png"


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


def get_image_base64(image_path: str) -> str:
    """Convert image to base64 string for CSS background."""
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
            return f"data:image/png;base64,{encoded_string}"
    except Exception as e:
        st.error(f"이미지 로드 실패: {e}")
        return ""


def apply_background_image(
    image_name: str = "FIRE_LOGO_large.png", style: str = "cover", opacity: float = 0.85
):
    """Apply background image with different styles."""
    background_image_path = str(Path(__file__).parents[2] / "assets" / image_name)
    background_image_b64 = get_image_base64(background_image_path)

    if not background_image_b64:
        return False

    styles = {
        "cover": """
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        """,
        "repeat": """
        background-size: 30px 30px;
        background-position: 0 0;
        background-repeat: repeat;
        """,
        "center": """
        background-size: auto;
        background-position: center;
        background-repeat: no-repeat;
        """,
        "stretch": """
        background-size: 100% 100%;
        background-position: center;
        background-repeat: no-repeat;
        """,
    }

    css_style = styles.get(style, styles["cover"])

    st.markdown(
        f"""
    <style>
    .stApp {{
        background-image: url('{background_image_b64}');
        background-attachment: fixed;
        {css_style}
        opacity: {opacity};
    }}

    /* 콘텐츠 영역에 반투명한 흰색 배경 추가 */
    .stApp > div {{
        background-color: rgba(255, 255, 255, 0.85) !important;
        border-radius: 10px;
        margin: 10px;
        padding: 10px;
    }}

    /* 사이드바와 메인 영역 구분 */
    .stApp > div[data-testid="stSidebar"] {{
        background-color: rgba(255, 255, 255, 0.95) !important;
    }}
    </style>
    """,
        unsafe_allow_html=True,
    )
    return True


def initialize_chatbot():
    if "graph" not in st.session_state:
        st.session_state.graph = create_chat_graph()
        # st.session_state.graph.display_node_design()
        st.session_state.config = RunnableConfig()
        st.session_state["ai"] = {}
        st.session_state["ai"]["initialized"] = False
        st.session_state["ai"]["messages"] = []
        st.session_state["ai"]["msg_index"] = 0
        st.session_state["state_result"] = {}
        st.session_state["tool"] = {}
        st.session_state["tool"]["tool_call_id"] = None
        st.session_state["tool"]["tool_call_name"] = None
        st.session_state["quiz"] = {}
        st.session_state["user_answers"] = {}
        st.session_state["events"] = []
        st.session_state["interrupts"] = []

        for category in CATEGORY_KEYS:
            st.session_state["quiz"][category] = {"questions": [], "options": []}
            st.session_state["quiz"][category]["synced"] = False
            st.session_state["updated_profile"] = {}
            st.session_state["user_answers"][category] = []
            st.session_state["updated_profile"][category] = []

        st.session_state["chatbot"] = {}
        st.session_state["chatbot"]["logs"] = []
        st.session_state["updates"] = []
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

    # user_answers나 quiz_questions가 None이거나 비어있는 경우 처리
    if not user_answers or not quiz_questions:
        return

    # check if all questions have been answered
    if len(user_answers) >= len(quiz_questions) and len(quiz_questions) > 0:
        try:
            counts = len(quiz_questions)
            st.progress(
                100,
                text=f"[{current_category}] Progress: {counts}/{counts}",
            )

            st.session_state["user_answers"][current_category] = []
            st.session_state["quiz"][current_category]["questions"] = []
            st.session_state["quiz"][current_category]["options"] = []
            st.session_state["quiz"][current_category]["synced"] = False

            run_graph(resume=True, resume_data=user_answers)

            # logging
            session_log = {
                "level": "info",
                "message": "The workflow has been automatically resumed.",
                "timestamp": time.time(),
                "location": "checkAnd_resume_workflow, after invoke",
            }
            st.session_state["chatbot"]["logs"].append(session_log)

            st.rerun()

        except Exception as e:
            # logging
            session_log: dict[str, float | str] = {
                "level": "warning",
                "message": f"failed to resume the workflow: {e}",
                "timestamp": time.time(),
                "location": "checkAnd_resume_workflow, after invoke",
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
                # user_answers가 None이거나 비어있는 경우 안전하게 처리
                user_answers = st.session_state.get("user_answers", {})
                if current_category in user_answers:
                    updated_answers = user_answers[current_category][:]
                    updated_answers.append((question_info["question"], choice))
                    st.session_state["user_answers"][current_category] = updated_answers

                    session_log = {
                        "level": "info",
                        "message": f"The answer has been saved. category: {current_category}, question: {question_info['question']}, choice: {choice}",
                        "timestamp": time.time(),
                        "location": "create_answer_callback, after save_answer",
                    }
                    st.session_state["chatbot"]["logs"].append(session_log)

                else:
                    session_log = {
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
            # events가 None이거나 비어있는 경우 안전하게 처리
            if "events" not in st.session_state:
                st.session_state["events"] = []
            
            st.session_state["events"] += event
            key = list(event.keys())[0]
            update = event[key]

            if key != "__interrupt__":
                if "messages" in update and update["messages"]:
                    for message in update["messages"]:
                        st.session_state["ai"]["messages"].append(
                            message
                        ) if isinstance(
                            message, AIMessage
                        ) and message.content != "" else message

            else:
                if isinstance(update[0], Interrupt):
                    interrupt_obj = update[0]
                    # interrupts가 None이거나 비어있는 경우 안전하게 처리
                    if "interrupts" not in st.session_state:
                        st.session_state["interrupts"] = []
                    st.session_state["interrupts"].append(interrupt_obj)

    else:
        for event in graph.stream(
            state,
            config=config,
            stream_mode="updates",
        ):
            # events가 None이거나 비어있는 경우 안전하게 처리
            if "events" not in st.session_state:
                st.session_state["events"] = []
            
            st.session_state["events"] += event
            key = list(event.keys())[0]
            update = event[key]

            if key != "__interrupt__":
                if "messages" in update and update["messages"]:
                    for message in update["messages"]:
                        st.session_state["ai"]["messages"].append(
                            message
                        ) if isinstance(
                            message, AIMessage
                        ) and message.content != "" else message

            else:
                if isinstance(update[0], Interrupt):
                    interrupt_obj = update[0]
                    # interrupts가 None이거나 비어있는 경우 안전하게 처리
                    if "interrupts" not in st.session_state:
                        st.session_state["interrupts"] = []
                    st.session_state["interrupts"].append(interrupt_obj)


def render_quiz(container):
    with container:
        # debug logs
        with st.expander("Debug Logs"):
            graph_state: OverallState | None = st.session_state.graph.get_state(
                st.session_state.config
            )
            st.write(graph_state)

        # interrupts가 None이거나 비어있는 경우 안전하게 처리
        interrupts = st.session_state.get("interrupts", [])
        if not interrupts:
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


def render_finished_chat(container):
    with container:
        st.image(FINISHED_CHAT_IMAGE_PATH, use_container_width=True)


def reset_data():
    supabase = st.session_state.supabase
    user_id = st.session_state.user.id
    supabase.table("profiles").update(
        {
            "investment_goal": [],
            "investment_emotions": [],
            "interests_categories": [],
            "investment_level": [],
            "knowledge_level": [],
            "risk_tolerance": 0,
        }
    ).eq("id", user_id).execute()


def render_chat(container):
    with container:
        messages = st.session_state.get("ai", {}).get("messages", [])
        idx = st.session_state["ai"]["msg_index"]

        if idx == 0:
            with st.chat_message("ai"):
                for message in messages:
                    st.write_stream(stream_text(message.content))
                idx += len(messages)
                st.session_state["ai"]["msg_index"] = idx
        elif len(messages) > idx:
            for msg_idx in range(idx, len(messages)):
                with st.chat_message("ai"):
                    st.write_stream(stream_text(messages[msg_idx].content))
            idx += len(messages) - idx
            st.session_state["ai"]["msg_index"] = idx
        else:
            for msg_idx in range(idx):
                with st.chat_message("ai"):
                    st.write(messages[msg_idx].content)

        graph_state = st.session_state.graph.get_state(st.session_state.config)

        user_meta_data = getattr(graph_state, "values", {}).get("user_meta_data", {})

        if user_meta_data.get("profile_status", "") == "completed":
            st.session_state["interrupts"] = []
            for category in CATEGORY_KEYS:
                st.session_state["user_answers"][category] = []
                st.session_state["quiz"][category]["questions"] = []
                st.session_state["quiz"][category]["options"] = []
                st.session_state["quiz"][category]["synced"] = False
            render_finished_chat(st.session_state["quiz_placeholder"])
            st.empty()
            st.balloons()
            if st.button("🔁 다시 시작", use_container_width=True):
                reset_data()
                st.rerun()


def render():
    # 배경 이미지 적용 예시들:
    # apply_background_image(style="cover", opacity=0.8)      # 전체 화면 커버
    # apply_background_image(style="repeat", opacity=0.9)     # 반복 패턴
    # apply_background_image(style="center", opacity=0.7)     # 가운데 정렬
    # apply_background_image(style="stretch", opacity=0.8)    # 화면에 맞춰 늘이기
    # apply_background_image("FIRE_LOGO_small.png", "repeat", 0.95)  # 다른 이미지 사용

    if apply_background_image("FIRE_LOGO_small.png", style="repeat", opacity=1):
        st.markdown(
            '<div style="text-align: center; color: red; font-size: 40px; font-weight: bold; font-family: Montserrat; background-color: white; padding: 10px; border-radius: 5px;opacity: 0.7;">Jasan Rescue 🚒</div>',
            unsafe_allow_html=True,
        )

    initialize_chatbot()

    # 커스텀 CSS 적용
    css_path = str(Path(__file__).parents[2] / "assets" / "style.css")
    load_css(css_path)

    _, left_screen, right_screen, _ = st.columns([0.1, 0.4, 0.4, 0.1], border=False)

    with left_screen:
        st.session_state["quiz_placeholder"] = st.container(border=True, height=500)

    with right_screen:
        st.session_state["chat_placeholder"] = st.container(border=True, height=500)

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

        input_state = InputState(
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

        run_graph(input_state, resume=False)

    render_chat(st.session_state["chat_placeholder"])
    render_quiz(st.session_state["quiz_placeholder"])


if __name__ == "__main__":
    render()
