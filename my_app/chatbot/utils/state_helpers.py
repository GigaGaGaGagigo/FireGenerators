import time
from typing import Any

import streamlit as st

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
        elif value is None or value == "":
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
        elif value is None or value == "":
            categories_to_update.append(key)
        elif key == "risk_tolerance" and value == 0:
            categories_to_update.append(key)

    return categories_to_update


def sync_questions() -> str | None:
    # interrupts가 None이거나 비어있는 경우 안전하게 처리
    interrupts = st.session_state.get("interrupts", [])
    if not interrupts:
        return None

    interrupt_obj = interrupts[-1]

    # interrupt_obj가 None이거나 value가 없는 경우 처리
    if (
        not interrupt_obj
        or not hasattr(interrupt_obj, "value")
        or not interrupt_obj.value
    ):
        return None

    category = interrupt_obj.value.get("category")
    questions = interrupt_obj.value.get("questions")
    options = interrupt_obj.value.get("options")

    # 필수 데이터가 없는 경우 처리
    if not category or not questions or not options:
        return None

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
