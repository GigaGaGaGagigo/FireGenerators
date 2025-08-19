import sys
import time
from pathlib import Path

import streamlit as st
from typing_extensions import Iterator

project_root: Path = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

try:
    from my_app.ui.chatbot.langgraph_core.graph_builder import GraphBuilder
except ImportError:
    print("import failed.")


IMAGE_PATH: Path = Path(__file__).parents[2] / "assets" / "FIRE_LOGO_large.png"

CATEGORY_KEYS: list[str] = [
    "investment_goal",
    "investment_emotions",
    "interests_categories",
    "investment_level",
    "knowledge_level",
]

st.set_page_config(layout="wide")

STREAM_DELAY_S = 0.01


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


if "graph" not in st.session_state:
    st.session_state.graph = create_chat_graph()
    st.session_state["ai"] = {}
    st.session_state["ai"]["initialized"] = False
    st.session_state["ai"]["messages"] = []
    st.session_state["ai"]["message_trigger"] = False
    st.session_state["ai"]["prev_message"] = None
    st.session_state["quiz"] = {}
    st.session_state["user_answers"] = {}
    st.session_state["updated_profile"] = {}
    st.session_state["state_result"] = {}

    for category in CATEGORY_KEYS:
        st.session_state["quiz"][category] = {"questions": [], "options": []}
        st.session_state["user_answers"][category] = []
        st.session_state["updated_profile"][category] = []


# Layout columns
margin_1, left_screen, right_screen, margin_2 = st.columns(
    [0.1, 0.4, 0.4, 0.1], border=False
)

with left_screen:
    with st.container(border=True, height=int(850)):
        user_data = st.session_state.user_data
        user_name: str = user_data["name"]
        st.write(user_name)

        categories_to_update: list[str] | None = find_missing_profile_categories(
            user_data
        )
        if st.session_state.get("ai", {}).get("initialized", False):
            if "graph" in st.session_state:
                state = st.session_state.graph.get_state()
                if state:
                    if len(state.target_profile_category) > 0:
                        st.write(
                            f"target_profile_category: {state.target_profile_category[0]}"
                        )
                    else:
                        st.write("target_profile_category: empty")
                    st.write(f"profile_status: {state.profile_status}")
                    st.write(f"workflow_stage: {state.workflow_stage}")
                    st.write(f"evaluation_results: {state.evaluation_results}")
                    st.write(f"investment_goal: {state.investment_goal}")
                    st.write(f"investment_emotions: {state.investment_emotions}")
                    st.write(f"interests_categories: {state.interests_categories}")
                    st.write(f"investment_level: {state.investment_level}")
                    st.write(f"knowledge_level: {state.knowledge_level}")
                    st.write(state.evaluation_results_logs)

                # if "user_answers" in st.session_state:
                #     st.write(f"user_answers: {st.session_state['user_answers']}")

        if st.session_state.get("ai", {}).get("initialized", False):
            state = st.session_state.graph.get_state()

            if state is not None:
                if len(state.target_profile_category) > 0:
                    target_profile_category: str = state.target_profile_category[0]
                else:
                    st.write("target_profile_category: empty")
                    st.stop()

                quiz_conetents: dict[str, dict[str, list]] = getattr(
                    state, "quiz_content_by_category", {}
                )

                quiz_set: dict[str, list] = quiz_conetents.get(
                    target_profile_category, {}
                )

                if quiz_set:
                    st.session_state["quiz"][target_profile_category]["questions"] = (
                        quiz_set.get("questions", [])
                    )
                    st.session_state["quiz"][target_profile_category]["options"] = (
                        quiz_set.get("options", [])
                    )

                    questions: list[str] = st.session_state["quiz"][
                        target_profile_category
                    ].get("questions", [])
                    options: list[list[str]] = st.session_state["quiz"][
                        target_profile_category
                    ].get("options", [])

                    q_index: int = len(
                        st.session_state["user_answers"][target_profile_category]
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

                                if st.session_state["ai"]["prev_message"] is not None:
                                    message = state.ai_messages[-1].content
                                    if (
                                        message
                                        != st.session_state["ai"]["prev_message"]
                                    ):
                                        st.session_state["ai"]["messages"].append(
                                            state.ai_messages[-1]
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


with right_screen:
    with st.container(border=True, height=int(850)):
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
                time.sleep(1)
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
                    time.sleep(1)
                    st.write("Loading AI... Done")
                except Exception as e:
                    st.error(f"Error: Initialize graph failed. {e}")
                    time.sleep(1)
                    st.write("Loading AI... Failed")
                time.sleep(1)

                status.update(
                    label="Download complete!", state="complete", expanded=False
                )

        if st.session_state.get("ai", {}).get("initialized", False):
            state = st.session_state.graph.get_state()

            if state is not None:
                ai_messages = list(getattr(state, "ai_messages", []))
                for msg in ai_messages:
                    st.write(msg.content)

                if ai_messages[-1].content != st.session_state["ai"]["prev_message"]:
                    st.session_state["ai"]["message_trigger"] = True
                else:
                    st.session_state["ai"]["message_trigger"] = False

                # if st.session_state["ai"]["message_trigger"]:
                #     st.write(ai_messages[-1].content)
                #     # st.rerun()

                # conclusion = getattr(state, "conclusion", None)
                # if conclusion:
                #     st.write(conclusion)
                #     st.rerun()
