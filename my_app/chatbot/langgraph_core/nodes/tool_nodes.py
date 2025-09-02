"""
Tool Nodes for Human-in-the-Loop Patterns

이 모듈은 interrupt 방식을 대신하여 tool call을 통해 사용자 입력을 수집하는
더 자연스러운 LangGraph 워크플로우를 구현합니다.

핵심 개념:
1. interrupt_before 대신 tool call을 사용하여 사용자 입력 요청
2. Streamlit UI가 tool call에 응답하여 사용자 선택 전달
3. LangGraph가 tool response를 받아 워크플로우 계속 진행

WRITER: Kang Joseph (with Claude Code assistance)
DATE: 2025-08-23
"""

import time

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from typing_extensions import Annotated, Any, Dict

from my_app.chatbot.langgraph_core.llm_agents import (
    OPENAI_MODEL_NAME,
    get_gpt_agent_with_tool,
)
from my_app.chatbot.langgraph_core.state import OverallState


class RequestHumanInput(BaseModel):
    category: Annotated[str, Field(description="User profile category to set")]
    questions: Annotated[list[str], Field(description="Questions to ask")]
    options: Annotated[list[list[str]], Field(description="Options to choose from")]


def call_llm(state: OverallState):
    llm = get_gpt_agent_with_tool(OPENAI_MODEL_NAME)
    messages = state.messages
    response = llm.invoke(messages)

    return {"messages": [response]}


def process_human_input_tool(state: OverallState) -> Dict[str, Any]:
    """
    사용자에게 질문을 요청하는 노드
    request predefined question set from the user

    이 함수는 interrupt_before 방식을 대체합니다:
        - 기존: interrupt_before로 workflow 중단 후 사용자 입력 대기
    - 새로운 방식: tool call을 생성하여 UI가 자연스럽게 응답하도록 함

    작동 순서:
    1. 현재 진행 중인 카테고리 확인
    2. 해당 카테고리의 질문 데이터 로드
    3. 이미 답변된 질문 수를 계산하여 다음 질문 결정
    4. tool call이 포함된 AIMessage 생성
    5. Streamlit UI가 처리할 추가 데이터 준비
    """

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

    if gathered_answers_length < 5:
        order_message: HumanMessage = HumanMessage(
            content="Create follow-up questions to refine the user's profile. Use GenerateFollowUp Tool"
        )
    else:
        order_message: HumanMessage = HumanMessage(
            content="Your task now is to call the 'AnalyzeProfile' tool to perform the analysis."
        )

    return {"messages": [order_message]}
