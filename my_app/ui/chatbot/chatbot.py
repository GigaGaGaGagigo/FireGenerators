import time
from pathlib import Path

import streamlit as st
from typing_extensions import Iterator

from ui.chatbot.langgraph_core.graph_builder import GraphBuilder

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
                if "graph" in st.session_state:
                    state = st.session_state.graph.get_state()
                    if state:
                        st.write("**Graph State:**")
                        st.json(
                            {
                                "target_profile_category": state.target_profile_category,
                                "profile_status": state.profile_status,
                                "workflow_stage": state.workflow_stage,
                                "evaluation_results": state.evaluation_results,
                                "investment_goal": state.investment_goal,
                                "investment_emotions": state.investment_emotions,
                                "interests_categories": state.interests_categories,
                                "investment_level": state.investment_level,
                                "knowledge_level": state.knowledge_level,
                                "evaluation_results_logs": state.evaluation_results_logs,
                            }
                        )

        if st.session_state.get("ai", {}).get("initialized", False):
            state = st.session_state.graph.get_state()

            if state is not None:
                if len(state.target_profile_category) > 0:
                    target_profile_category: str = state.target_profile_category[0]

                    quiz_conetents: dict[str, dict[str, list]] = getattr(
                        state, "quiz_content_by_category", {}
                    )
                    quiz_set: dict[str, list] = quiz_conetents.get(
                        target_profile_category, {}
                    )

                    if quiz_set:
                        st.session_state["quiz"][target_profile_category][
                            "questions"
                        ] = quiz_set.get("questions", [])
                        st.session_state["quiz"][target_profile_category][
                            "options"
                        ] = quiz_set.get("options", [])

                        questions: list[str] = st.session_state["quiz"][
                            target_profile_category
                        ].get("questions", [])
                        options: list[list[str]] = st.session_state["quiz"][
                            target_profile_category
                        ].get("options", [])

                        q_index: int = len(
                            st.session_state["user_answers"][
                                target_profile_category
                            ]
                        )

                        if 0 <= q_index < len(questions):
                            current_question: str = questions[q_index]
                            current_options: list[str] = (
                                options[q_index] if q_index < len(options) else []
                            )

                            st.write_stream(stream_text(current_question))

                            def on_answer_change(
                                idx_key: str,
                                question_text: str,
                                total_questions: int,
                                current_q_index: int,
                                category_key: str,
                            ):
                                choice = st.session_state.get(idx_key)
                                user_answers = st.session_state["user_answers"][
                                    category_key
                                ]
                                if choice:
                                    user_answers.append((question_text, choice))
                                    state = st.session_state.graph.get_state()
                                    if current_q_index + 1 >= total_questions:
                                        state = st.session_state.graph.get_state()

                                        if state.workflow_stage == "generate_qa":
                                            st.session_state.graph.graph.update_state(
                                                st.session_state.graph.config,
                                                {
                                                    "answers_by_category": {
                                                        category_key: user_answers
                                                    }
                                                },
                                            )

                                            st.session_state.graph.invoke(
                                                None,
                                                config=st.session_state.graph.config,
                                            )
                                        elif (
                                            state.workflow_stage == "finished_qa"
                                            and len(user_answers) == total_questions
                                        ):
                                            st.session_state.graph.graph.update_state(
                                                st.session_state.graph.config,
                                                {
                                                    "answers_by_category": {
                                                        category_key: user_answers
                                                    }
                                                },
                                            )
                                            st.session_state["state_result"] = (
                                                st.session_state.graph.invoke(
                                                    None,
                                                    config=st.session_state.graph.config,
                                                )
                                            )

                            idx_key = f"question_radio_{q_index}"
                            st.radio(
                                "옵션을 선택하세요:",
                                options=current_options,
                                key=idx_key,
                                index=None,
                                on_change=on_answer_change,
                                args=(
                                    idx_key,
                                    current_question,
                                    len(questions),
                                    q_index,
                                    target_profile_category,
                                ),
                            )
                else:
                    # 모든 퀴즈가 완료되었을 때 메시지 표시
                    st.success("프로필 생성이 완료되었습니다! ✨")
                    st.info("오른쪽 화면에서 최종 결과를 확인하세요.")
                    st.balloons()


def render():
    if "graph" not in st.session_state:
        st.session_state.graph = create_chat_graph()
        # st.session_state.graph.display_node_design()
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
                            config=None,
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
                state = st.session_state.graph.get_state()

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