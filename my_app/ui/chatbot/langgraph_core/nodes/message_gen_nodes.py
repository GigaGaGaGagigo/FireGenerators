"""
WRITER: Kang Joseph
DATE: 2025-08-02
DESCRIPTION: This file contains the nodes for the conversation.
"""

from typing import Annotated, Literal

from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field, ValidationError

from my_app.ui.chatbot.langgraph_core.llm_agents import (
    GEMINI_MODEL_NAME,
    get_llm_agents,
)
from my_app.ui.chatbot.langgraph_core.prompt_loader import read_yaml_prompt
from my_app.ui.chatbot.langgraph_core.state.state import InputState


class GreetingGenerationResult(BaseModel):
    profile_status: Annotated[
        Literal["onboarding", "editing", "completed"],
        Field(
            description="user profile status (onboarding = new user, editting = existing user, not completed, completed = completed)"
        ),
    ]
    ai_message: Annotated[str, Field(description="generated greeting message")]


def initialize_conversation(state: InputState) -> dict:
    prompt = """
    You are an investment advisor chatbot, \"자산구조대\".
    Your primary goal is to generate a tailored greeting message to the user.

    Output instructions:
    - The output must be a single string containing the complete greeting message.
    - Do not add any extra explanations or text before or after the greeting message.
    - Directly generate the message based on the relevant flow.

    Rules:
    - If {profile_status} is \"onboarding\", follow onboarding_user_flow.
    - If {profile_status} is \"editing\", follow editing_user_flow.
    - If {profile_status} is \"completed\", follow completed_user_flow.

    onboarding_user_flow:
        Step 1: Generate a greeting message for {user_name}.
            - examples:
                - \"안녕하세요, {user_name}님! 자산구조대입니다. 투자 여정을 함께할 수 있도록 도와드리겠습니다. \n{user_name}님에 대해 알아보기 위해 몇 가지 질문을 드릴게요. 간단하게 답변해주시겠어요?\"
                - \"반가워요, {user_name}님! 당신의 든든한 투자 파트너, 자산구조대입니다. 성공적인 투자의 첫걸음을 함께 내디뎌봐요! \n먼저 몇 가지 질문으로 {user_name}님에 대해 알아볼게요.\"

        Step 2: If {user_name} is empty, generate a generic welcome message or suggest a nickname.
            - nickname_suggestions: [\"투자 꿈나무\", \"미래의 자산가\", \"스마트 투자자\"]
            - examples:
                - \"안녕하세요! 자산구조대에 오신 것을 환영합니다. 당신의 투자 여정을 함께할 수 있도록 도와드리겠습니다. \n먼저 당신에 대해 알아보기 위해 몇 가지 질문을 드릴게요. 간단하게 답변해주시겠어요?\"
                - \"반갑습니다! 저는 당신의 투자 길잡이, 자산구조대입니다. 당신을 '투자 꿈나무'라고 불러드릴까요? \n이제 당신에 대해 알아보기 위한 몇 가지 질문에 답변해주세요.\"

    editing_user_flow:
        Step 1: Generate a greeting message to {user_name} to resume the process.
            - examples:
                - \"안녕하세요, {user_name}님! 자산구조대입니다. 이전에 진행하다가 멈춘 프로필 작성을 마저 이어나가 볼까요?\"
                - {user_name}님, 다시 오셨네요! 중단하셨던 부분부터 다시 시작해서 프로필을 완성해봐요. 거의 다 왔어요!\"

    completed_user_flow:
        Step 1: Generate a welcome back message for the returning user {user_name}.
        - examples:
            - \"다시 오셨네요, {user_name}님! 자산구조대와 함께 오늘도 성공적인 투자 습관을 만들어봐요. 무엇을 도와드릴까요?\"
            - {user_name}님, 오랜만이에요! 다시 만나서 반갑습니다. 오늘은 어떤 투자 이야기가 궁금하신가요?\"
    """

    llm = get_llm_agents(GEMINI_MODEL_NAME)

    # 프롬프트를 PromptTemplate으로 래핑
    prompt_template = PromptTemplate(
        input_variables=["profile_status", "user_name"],
        template=prompt,
    )

    structured_llm = llm.with_structured_output(GreetingGenerationResult)

    chain = prompt_template | structured_llm

    raw_result = chain.invoke(
        {"profile_status": state.profile_status, "user_name": state.user_name}
    )

    try:
        result: GreetingGenerationResult = GreetingGenerationResult.model_validate(
            raw_result
        )
    except ValidationError as e:
        raise ValueError(f"Unexpected result type from chain.invoke: {e}")

    # index 0 category is current category
    initial_answers_by_category = (
        {state.target_profile_category[0]: []} if state.target_profile_category else {}
    )

    return {
        "user_name": state.user_name,
        "ai_messages": [AIMessage(content=result.ai_message)],
        "answers_by_category": initial_answers_by_category,
        "profile_status": result.profile_status,
        "target_profile_category": state.target_profile_category,
        "workflow_stage": "serve_fixed_qa",
    }


if __name__ == "__main__":
    prompt = read_yaml_prompt("greeting")
    print(prompt)
