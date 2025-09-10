import time
from typing import Annotated, Any, Dict

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from my_app.chatbot.chat_core.model_loader import (
    OPENAI_MODEL_NAME,
    get_llm_models,
)
from my_app.chatbot.chat_core.state import OverallState


class RequestHumanInput(BaseModel):
    category: Annotated[str, Field(description="User profile category to set")]
    questions: Annotated[list[str], Field(description="Questions to ask")]
    options: Annotated[list[list[str]], Field(description="Options to choose from")]


def call_llm(state: OverallState):
    llm = get_llm_models(OPENAI_MODEL_NAME, tool=True, new_user=True)
    messages = state.messages
    response = llm.invoke(messages)

    return {"messages": [response]}


def process_human_input_tool(state: OverallState) -> Dict[str, Any]:
    try:
        last_message = state.messages[-1]
        tool_call = getattr(last_message, "tool_calls", [])[0]
        tool_call_id: str = tool_call["id"]
        parsed_args = RequestHumanInput.model_validate(tool_call["args"])

        questions_to_ask: dict[str, list[list[str]] | list[str] | str] = {
            "category": parsed_args.category,
            "questions": parsed_args.questions,
            "options": parsed_args.options,
        }

    except (IndexError, KeyError, AttributeError, Exception) as e:
        return {
            "logs": [
                {
                    "level": "error",
                    "message": f"failed to extract tool_call: {e}",
                    "timestamp": time.time(),
                }
            ]
        }

    user_answers: list[tuple[str, str]] = interrupt(questions_to_ask)

    if not user_answers:
        return {
            "logs": [
                {
                    "level": "warning",
                    "message": "failed to extract user_answers",
                    "timestamp": time.time(),
                }
            ],
            "messages": [
                {"tool_call_id": tool_call_id, "type": "tool", "content": "[]"}
            ],
        }

    tool_message: ToolMessage = ToolMessage(
        content=str(user_answers),
        tool_call_id=tool_call_id,
    )

    current_category = getattr(state, "target_profile_category", [])[0]
    existing_answers_by_category = getattr(state, "user_answers_by_category", {})
    current_category_answers = existing_answers_by_category.get(current_category, [])

    return {
        "messages": [tool_message],
        "logs": [
            {
                "level": "info",
                "message": "user_answers collected",
                "timestamp": time.time(),
            }
        ],
        "user_answers_by_category": {
            **existing_answers_by_category,
            current_category: current_category_answers + user_answers,
        },
    }


def determine_next_node(state: OverallState):
    current_category = getattr(state, "target_profile_category", [])[0]
    existing_answers_by_category = getattr(state, "user_answers_by_category", {})

    gathered_answers_length = len(
        existing_answers_by_category.get(current_category, [])
    )

    order_message: HumanMessage

    if gathered_answers_length < 5:
        # pyrefly: ignore  # annotation-mismatch
        order_message = HumanMessage(
            content="Create follow-up questions to refine the user's profile. Use GenerateFollowUp Tool"
        )
    else:
        # pyrefly: ignore  # annotation-mismatch
        order_message = HumanMessage(
            content="Your task now is to call the 'AnalyzeProfile' tool to perform the analysis."
        )

    return {"messages": [order_message]}
