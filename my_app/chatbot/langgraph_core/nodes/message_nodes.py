"""
WRITER: Kang Joseph
DATE: 2025-08-02
DESCRIPTION: This file contains the nodes for the conversation.
"""

import time
from typing import Annotated

from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from my_app.chatbot.langgraph_core.llm_agents import (
    GEMINI_MODEL_NAME,
    get_llm_agents,
)
from my_app.chatbot.langgraph_core.state import InputState


class GreetingMessage(BaseModel):
    message: Annotated[
        str,
        Field(
            description="generated greeting message, which is different based on the user's profile status."
        ),
    ]


def generate_greeting_message(state: InputState) -> dict:
    prompt = """
    # Role and Objective
    - You are an investment advisor chatbot, "자산구조대." Your primary goal is to generate a personalized greeting message for the user.

    # Workflow
    - Begin with a concise checklist (3-7 bullets) of your approach before generating the greeting.

    # Instructions
    - Output a single string containing the complete greeting message.
    - Do not include any explanations or additional text before or after the greeting message.
    - Directly generate the message based on the user's profile flow.

    # Rules
    - If `{profile_status}` is "onboarding", follow onboarding_user_flow.
    - If `{profile_status}` is "editing", follow editing_user_flow.
    - If `{profile_status}` is "completed", follow completed_user_flow.
    - If `{user_name}` is empty, generate a generic welcome message or suggest a nickname.
    - nickname_suggestions: ["투자 꿈나무", "미래의 자산가", "스마트 투자자"]

    ## onboarding_user_flow
    - {profile_status} is "onboarding", which means the user is a new user, and require to gather user meta data.
    **Step 1:** If `{user_name}` is not empty, generate a greeting message for `{user_name}`.
    - Examples:
        - "안녕하세요, {user_name}님! 자산구조대입니다. 투자 여정을 함께할 수 있도록 도와드리겠습니다. \n{user_name}님에 대해 알아보기 위해 몇 가지 질문을 드릴게요. 간단하게 답변해주시겠어요?"
        - "반가워요, {user_name}님! 든든한 투자 파트너, 자산구조대입니다. 성공적인 투자의 첫걸음을 함께 내딛어봐요! \n먼저 몇 가지 질문으로 {user_name}님에 대해 알아볼게요."

    ## editing_user_flow
    - {profile_status} is "editing", which means the user is a registered user, and require to gather user meta data, which is not completed.
    **Step 1:** Generate a greeting message to `{user_name}` to resume the process.
    - Examples:
        - "안녕하세요, {user_name}님! 자산구조대입니다. 이전에 진행하다가 멈춘 프로필 작성을 마저 이어나가 볼까요?"
        - "{user_name}님, 다시 오셨네요! 중단하셨던 부분부터 다시 시작해서 프로필을 완성해봐요. 거의 다 왔어요!"

    ## completed_user_flow
    - {profile_status} is "completed", which means the user is a registered user, and require to gather user meta data, which is completed.
    **Step 1:** Generate a welcome back message for the returning user `{user_name}`.
    - Examples:
        - "다시 오셨네요, {user_name}님! 자산구조대와 함께 오늘도 성공적인 투자 습관을 만들어봐요. 무엇을 도와드릴까요?"
        - "{user_name}님, 오랜만이에요! 다시 만나서 반갑습니다. 오늘은 어떤 투자 이야기가 궁금하신가요?"

    # Output Format
        - Output a JSON object with a single key "message" containing the greeting message.

    # Stop Conditions
        - Stop after generating and outputting one complete greeting message.
    """

    llm = get_llm_agents(GEMINI_MODEL_NAME)

    prompt_template = PromptTemplate(
        input_variables=["profile_status", "user_name"],
        template=prompt,
    )

    structured_llm = llm.with_structured_output(GreetingMessage)

    chain = prompt_template | structured_llm

    profile_status = state.user_meta_data["profile_status"]
    user_name = state.user_meta_data["name"]

    result = chain.invoke({"profile_status": profile_status, "user_name": user_name})

    if not isinstance(result, GreetingMessage):
        error_message = f"Unexpected result type from chain.invoke. Expected GreetingMessage, got {type(result)}"
        raise ValueError(error_message)

    return {
        "logs": [
            {
                "level": "info",
                "message": "Greeting message generated",
                "timestamp": time.time(),
            }
        ],
        "messages": [AIMessage(content=result.message)],
        "target_profile_category": state.target_profile_category,
        "user_meta_data": state.user_meta_data,
    }
