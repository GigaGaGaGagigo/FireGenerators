"""
WRITER: Kang Joseph
DATE: 2025-08-02
DESCRIPTION: This file contains the nodes for the conversation.
"""

import time

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableAssign, RunnablePassthrough

from my_app.chatbot.chat_core.model_loader import (
    GEMINI_MODEL_NAME,
    get_llm_models,
)
from my_app.chatbot.chat_core.prompt_loader import (
    load_prompt_from_yaml,
)
from my_app.chatbot.chat_core.state import InputState


def generate_greeting_message(state: InputState) -> dict:
    persona_prompt = load_prompt_from_yaml("persona")
    greeting_prompt = load_prompt_from_yaml("greeting")

    prompt_template: RunnableAssign = (
        RunnablePassthrough.assign(chat_history=persona_prompt) | greeting_prompt  # type: ignore
    )

    llm = get_llm_models(GEMINI_MODEL_NAME)

    chain = prompt_template | llm

    profile_status = state.user_meta_data["profile_status"]
    user_name = state.user_meta_data["name"]

    result = chain.invoke({"profile_status": profile_status, "user_name": user_name})

    return {
        "logs": [
            {
                "level": "info",
                "message": "Greeting message generated",
                "timestamp": time.time(),
            }
        ],
        "messages": [AIMessage(content=result.content)],
        "target_profile_category": state.target_profile_category,
        "user_meta_data": state.user_meta_data,
    }
