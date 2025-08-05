"""
WRITER: Kang Joseph
DATE: 2025-08-02
DESCRIPTION:

TODO:

# 대화 처리 + 분석 여부 판단

"""

from typing import Any, Dict

from my_app.ui.chatbot.langgraph_core.chains import (
    onboarding_chain,  # <--- 미리 만들어진 동적 Chain을 import
)
from my_app.ui.chatbot.langgraph_core.llm_agents import (
    GEMINI_MODEL_NAME,
    get_llm_agents,
)
from my_app.ui.chatbot.langgraph_core.state import ChatState


def conversation_node(state: ChatState) -> Dict[str, Any]:
    llm_client = get_llm_agents(GEMINI_MODEL_NAME)

    return {"messages": [llm_client.invoke(state["messages"])]}


# def generate_onboarding_response(state: ChatState) -> dict:
#     """온보딩 대화 응답을 생성합니다."""

#     # state에서 필요한 모든 정보를 꺼냅니다.
#     # load_memory_node에서 가져온 db_profile이 user_data가 됩니다.
#     user_data = state.get("UserState", "user_email")
#     user_message = state["messages"]
#     history = state.get("conversation_history", "")

#     # invoke를 호출할 때, 필요한 모든 데이터를 딕셔너리로 전달합니다.
#     # _render_onboarding_prompt 함수가 이 딕셔너리를 입력받게 됩니다.
#     response = onboarding_chain.invoke(
#         {
#             "user_data": user_data,
#             "user_message": user_message,
#             "conversation_history": history,
#         }
#     )

#     return {"final_response": response.content}


def generate_onboarding_response(state: ChatState) -> dict:
    user_data = state.get("UserState", {})
    user_message = state["messages"]
    history = state.get("conversation_history", "")

    response = onboarding_chain.invoke(
        {
            "user_data": user_data,
            "user_message": user_message,
            "conversation_history": history,
        }
    )

    return {"messages": [response]}
