"""
LangGraph 상태 관리를 위한 헬퍼 함수들
타입 안전성과 에러 처리를 개선합니다.
"""

import time

import streamlit as st
from typing_extensions import Any, Dict

from my_app.chatbot.langgraph_core.state import OverallState

CATEGORY_KEYS: list[str] = [
    "interests_categories",
    "investment_emotions",
    "investment_goal",
    "investment_level",
    "knowledge_level",
    "risk_tolerance",
]


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
        elif key == "risk_tolerance" and value == 0:
            categories_to_check.append(True)

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
        elif key == "risk_tolerance" and value == 0:
            categories_to_update.append(key)

    return categories_to_update


def sync_questions() -> str | None:
    interrupt_obj = st.session_state["interrupts"][-1]

    category = interrupt_obj.value["category"]
    questions = interrupt_obj.value["questions"]
    options = interrupt_obj.value["options"]

    if st.session_state["quiz"].get(category, {}).get("synced", False):
        return category

    # already updated
    if st.session_state["quiz"].get(category, {}).get("questions", []) == questions:
        return category

    st.session_state["quiz"][category] = {
        "questions": questions,
        "options": options,
    }

    st.session_state["quiz"][category]["synced"] = True

    # logging
    st.session_state["chatbot"]["logs"].append(
        {
            "level": "info",
            "message": f"Interrupt handled for category '{category}'. Quiz data synced.",
            "timestamp": time.time(),
        }
    )

    return category


def get_current_question_info(category: str) -> dict[str, Any] | None:
    try:
        if category not in st.session_state["quiz"]:
            return None

        questions: list[str] = st.session_state["quiz"][category].get("questions", [])
        options: list[str] = st.session_state["quiz"][category].get("options", [])

        if not questions:
            return None

        # calculate the current question index
        answered_count: int = len(st.session_state["user_answers"].get(category, []))

        if answered_count >= len(questions):
            return None  # all questions are completed

        current_question: str = questions[answered_count]
        current_options: list[str] | str = (
            options[answered_count] if answered_count < len(options) else []
        )

        return {
            "question": current_question,
            "options": current_options,
            "index": answered_count,
            "total": len(questions),
        }

    except Exception as e:
        # logging
        session_log: dict[str, float | str] = {
            "level": "error",
            "message": f"failed to get the current question information: {e}",
            "timestamp": time.time(),
            "location": "get_current_question_info, after invoke",
        }
        st.session_state["chatbot"]["logs"].append(session_log)
        return None


def debug_state_info() -> Dict[str, Any]:
    try:
        state: OverallState | None = st.session_state.graph.get_state(
            st.session_state.config
        )
        if not state:
            return {"error": "failed to get the current state"}

        user_meta_data = getattr(state, "user_meta_data", {})

        return {
            "db_data": getattr(st.session_state, "user_data", {}),
            "user_meta_data": user_meta_data,
            "target_profile_category": getattr(state, "target_profile_category", []),
            "quiz_in_streamlit": st.session_state["quiz"],
        }

    except Exception as e:
        return {"error": f"failed to collect debug information: {e}"}
