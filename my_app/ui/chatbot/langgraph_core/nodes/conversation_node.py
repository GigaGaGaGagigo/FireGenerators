"""
WRITER: Kang Joseph
DATE: 2025-08-02
DESCRIPTION:

TODO:

# 대화 처리 + 분석 여부 판단

"""

from typing import Literal

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from my_app.ui.chatbot.langgraph_core.llm_agents import (
    GEMINI_MODEL_NAME,
    get_llm_agents,
)
from my_app.ui.chatbot.langgraph_core.prompt_loader import load_prompt
from my_app.ui.chatbot.langgraph_core.state import ChatState


class AnalysisResultStructured(BaseModel):
    user_message: str = Field(description="Original user message")
    is_analysis_required: Literal["Skip_Analysis", "Run_Analysis"] = Field(
        description="Either 'Skip_Analysis' or 'Run_Analysis'"
    )
    reason: str = Field(description="Brief explanation for the decision")


def check_analysis_requirements(state: ChatState):
    # if user_messages is empty or llm decideds to analyze
    if len(state["user_messages"]) == 0:
        return {"is_analysis_required": "Skip_Analysis"}

    prompt = load_prompt("system_prompts", "analysis_required")
    prompt_template = PromptTemplate.from_template(prompt)

    llm = get_llm_agents(GEMINI_MODEL_NAME)
    structured_llm = llm.with_structured_output(AnalysisResultStructured)

    latest_message = state["user_messages"][-1]

    chain = prompt_template | structured_llm

    analysis_result = chain.invoke({"user_message": latest_message})

    analysis_result_dict = analysis_result.model_dump()  # type: ignore

    print(f"➡️ user_message: {analysis_result_dict['user_message']}")
    print(f"➡️ is_analysis_required: {analysis_result_dict['is_analysis_required']}")
    print(f"➡️ reason: {analysis_result_dict['reason']}")

    return {"is_analysis_required": analysis_result_dict["is_analysis_required"]}
