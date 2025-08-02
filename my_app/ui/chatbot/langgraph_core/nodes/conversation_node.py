"""
WRITER: Kang Joseph
DATE: 2025-08-02
DESCRIPTION:

TODO:
"""

from typing import Any, Dict

from my_app.ui.chatbot.langgraph_core.llm_clients import (
    GEMINI_MODEL_NAME,
    get_llm_client,
)
from my_app.ui.chatbot.langgraph_core.state.chat_state import ChatState


def conversation_node(state: ChatState) -> Dict[str, Any]:
    llm_client = get_llm_client(GEMINI_MODEL_NAME)

    return {"messages": [llm_client.invoke(state["messages"])]}
