"""
WRITER: Kang Joseph
DATE: 2025-08-12
DESCRIPTION: Finalization node to convert accumulated OverallState into OutputState
for UI consumption (e.g., summary sentence for user's goal).
"""

from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field, ValidationError

from my_app.ui.chatbot.langgraph_core.llm_agents import (
    GEMINI_MODEL_NAME,
    get_llm_agents,
)
from my_app.ui.chatbot.langgraph_core.state import OutputState, OverallState


class ResponseGenResult(BaseModel):
    conclusion: str = Field(description="Conclusion")


def build_output_state_from_analysis(state: OverallState) -> OutputState:
    # Format user profile data for better readability
    investment_goals = ", ".join(state.investment_goal) or "Not specified"
    investment_emotions = ", ".join(state.investment_emotions) or "Not specified"
    interests = ", ".join(state.interests_categories) or "Not specified"
    experience = state.investment_level or "Not specified"
    knowledge = state.knowledge_level or "Not specified"

    prompt = f"""You are an expert Korean financial advisor named '자산구조대'. Your task is to create a warm, encouraging, and personalized summary for a user based on their investment profile.

    User Profile Data:
    - Investment Goals: {investment_goals}
    - Investment Emotions: {investment_emotions}
    - Areas of Interest: {interests}
    - Investment Experience: {experience}
    - Financial Knowledge: {knowledge}

    Instructions:
        1. Write in Korean only
        2. Create a comprehensive synthesis that shows deep understanding of the user's situation
        3. Connect their goals with their current experience level and risk tolerance
        4. Provide specific, actionable next steps that feel natural and encouraging
        5. Use a warm, professional tone while avoiding complex financial jargon
        6. Keep it concise: 2-3 sentences maximum
        7. Make the user feel understood and confident about their investment journey

    Example style (adapt to the actual user data):
        "장기적인 자산 증식을 목표로 하시면서도 안정성을 중시하는 신중한 접근이 인상적입니다! 부동산과 주식에 대한 관심을 바탕으로, 초보자 수준에 맞는 분산 투자 전략을 단계적으로 구축해나가시면 좋겠습니다. 우선 안정적인 인덱스 펀드부터 시작해서 경험을 쌓아가시는 것을 추천드립니다."

    Now generate a personalized summary based on the provided user profile. Output only the summary in Korean, no additional text or prefixes.
    """

    prompt_template = PromptTemplate(
        template=prompt,
        input_variables=[
            state.investment_goal,
            state.investment_emotions,
            state.interests_categories,
            state.investment_level,
            state.knowledge_level,
        ],
    )

    llm = get_llm_agents(GEMINI_MODEL_NAME)
    structured_llm = llm.with_structured_output(ResponseGenResult)

    chain = prompt_template | structured_llm

    raw_schema = chain.invoke(
        {
            "investment_goals": investment_goals,
            "investment_emotions": investment_emotions,
            "interests": interests,
            "experience": experience,
            "knowledge": knowledge,
        }
    )

    try:
        schema: ResponseGenResult = ResponseGenResult.model_validate(raw_schema)
    except ValidationError as e:
        raise ValueError(f"Unexpected result type from chain.invoke: {e}")

    conclusion = schema.conclusion

    return OutputState(
        conclusion=conclusion,
        ai_messages=[AIMessage(content=conclusion)],
        investment_goal=list(state.investment_goal),
        investment_emotions=list(state.investment_emotions),
        interests_categories=list(state.interests_categories),
        investment_level=str(state.investment_level),
        knowledge_level=str(state.knowledge_level),
    )
