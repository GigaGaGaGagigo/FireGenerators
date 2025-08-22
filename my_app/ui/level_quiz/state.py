import json, re, os, time, uuid
import streamlit as st

from my_app.quiz_core.constants import COMMON_PATH, COMMON_COUNT
from ui.level_quiz.data.user_context import fetch_user_keywords
from my_app.quiz_core.utils import _get_user_id

def init_quiz_state():
    defaults = {
        "quiz_questions": [],
        "quiz_index": 0,
        "quiz_score": 0,
        "total_weight": 0,
        "proficiency": 5,
        "wrong_notes": [],
        "history": [],
        "generated_count": 0,
        "quiz_started": False,
        "quiz_completed": False,
        "user_keywords": [],
        "completion_announced": False,
        "role": "User",
        "messages": [],
        "eval_cache": {},
        "processing": False,
        "generated_saved": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if not isinstance(st.session_state.messages, list):
        st.session_state.messages = []

def ensure_user_keywords():
    if st.session_state.user_keywords:
        return
    user = st.session_state.get("user")
    user_id = _get_user_id(user)
    st.session_state.user_keywords = fetch_user_keywords(user_id) if user_id else []

def load_common_questions():
    if not os.path.exists(COMMON_PATH):
        st.error(f"공통문항 파일을 찾을 수 없습니다: {COMMON_PATH}")
        return []
    import json
    with open(COMMON_PATH, "r", encoding="utf-8") as f:
        qs = json.load(f)
    for q in qs:
        q["options"] = q.get("options", []) or []
        q["weight"] = q.get("weight", 1) or 1
    return qs[:COMMON_COUNT]
