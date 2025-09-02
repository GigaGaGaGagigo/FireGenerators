"""
WRITER: Kang Joseph
DATE: 2025-08-12
DESCRIPTION: Final response node(s) for summarizing the user's goal from Q&A.
"""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Annotated, Literal

from my_app.chatbot.chat_core.model_loader import (
    OPENAI_MODEL_NAME,
    get_llm_models,
)
from my_app.chatbot.chat_core.prompt_loader import load_prompt_from_yaml
from my_app.chatbot.chat_core.state import OutputState, OverallState
from my_app.chatbot.services.profile_service import ProfileService


class AnalyzeProfile(BaseModel):
    pass


class AnalysisData(BaseModel):
    data: list[str] = Field(
        description="A list of strings containing the analysis result."
    )


class ValidationAnalysisData(BaseModel):
    is_valid: Literal["valid", "invalid"] = Field(
        description="Whether the user's response is valid for the category."
    )
    explanation: str = Field(description="Explanation for the assessment.")


class UserProfileSummary(BaseModel):
    summary: Annotated[
        str, Field(description="user profile summary from the user's meta data")
    ]


ANALYSIS_USER_ANSWER_PROMPTS = {
    "interests_categories": "{user_name}님의 관심사는 {data} 이네요!",
    "investment_emotions": "{user_name}님의 투자에 대해 느끼는 감정은 {data} 이군요!",
    "investment_goal": "{user_name}님의 투자 목표는 {data} 라고 볼 수 있겠습니다.",
    "investment_level": "{user_name}님의 투자 수준은 {data} 으로 정해졌습니다. 대화를 통해서 변경될 수 있으니, 크게 신경쓰지 마세요.",
    "knowledge_level": "{user_name}님의 금융 지식 수준은 {data} 으로 정해졌습니다. 대화를 통해서 변경될 수 있으니, 크게 신경쓰지 마세요.",
    "risk_tolerance": "{user_name}님의 위험 허용 수준은 {data} 입니다.",
}


def analyze_user_answers(state: OverallState) -> dict:
    current_category = state.target_profile_category[0]

    if current_category == "interests_categories":
        prompt_template = load_prompt_from_yaml("analysis_interests_categories")
    elif current_category == "investment_emotions":
        prompt_template = load_prompt_from_yaml("analysis_investment_emotions")
    elif current_category == "investment_goal":
        prompt_template = load_prompt_from_yaml("analysis_investment_goal")
    elif current_category == "investment_level":
        prompt_template = load_prompt_from_yaml("analysis_investment_level")
    elif current_category == "knowledge_level":
        prompt_template = load_prompt_from_yaml("analysis_knowledge_level")
    elif current_category == "risk_tolerance":
        prompt_template = load_prompt_from_yaml("analysis_risk_tolerance")

    llm = get_llm_models(OPENAI_MODEL_NAME)

    chain = prompt_template | llm.with_structured_output(AnalysisData)

    result = chain.invoke(
        {"compacted_user_answer": state.user_answers_compacted[current_category]}
    )
    analysis_data = result.data

    message_prompt: str = ANALYSIS_USER_ANSWER_PROMPTS[current_category].format(
        user_name=state.user_meta_data["user_name"], data=analysis_data
    )

    return {
        "messages": [AIMessage(content=message_prompt)],
        "user_meta_data": {
            **state.user_meta_data,
            current_category: analysis_data,
        },
    }


def compact_user_answer(state: OverallState):
    current_category = state.target_profile_category[0]
    qa_pairs = state.user_answers_by_category[current_category]
    llm = get_llm_models(OPENAI_MODEL_NAME)

    #     prompt = f"""
    # Compact the {qa_pairs} in one sentence. The provided data is a list of tuples, where each tuple consists of a question and its corresponding answer.
    # Your task is to understand the intent of the question and, based on the user's answer.
    # The summary sentence must include the key words from the input data. Ensure the output is in the user's original language.
    # """

    prompt = """
You are an expert profiler specializing in analyzing investor psychology and tendencies.
Your mission is to synthesize the provided {qa_pairs} into a single, insightful Korean sentence that creates a concise "profile" of the investor for a specific: {target_category}.

Follow this process:
1.  **Identify the Core Theme:** First, analyze the common intent of the questions to understand the central theme of the dataset (e.g., 'emotional response to investment', 'investment goals and time horizon').
2.  **Extract and Connect Meanings:** Extract the core meaning from each of the user's answers. Then, logically connect these meanings into one coherent narrative.
3.  **Generate the Profile Sentence:** The final output must be an insightful summary that holistically represents the investor's characteristics for the given category.

**Output Rules:**
- The final output must be the profile sentence ONLY.
- Do not include any prefixes, titles, or labels.
- The response must begin directly with the generated sentence itself.
- Respond in the user's original language.
"""

    prompt_template = PromptTemplate(
        template=prompt, input_variables=["qa_pairs", "target_category"]
    )

    chain = prompt_template | llm

    compacted_user_answer = chain.invoke(
        {"qa_pairs": qa_pairs, "target_category": current_category}
    )

    return {
        "logs": [
            {
                "level": "info",
                "message": f"User answer compacted for {current_category}",
                "timestamp": time.time(),
            }
        ],
        "user_answers_compacted": {
            **state.user_answers_compacted,
            current_category: compacted_user_answer,
        },
    }


def evaluate_analysis_result(state: OverallState) -> dict:
    """This node should assess whether a user has completed their profile
    setup based on the non-empty fields in the state."""

    prompt = """
    You are a **Profile Data Evaluation Expert**.
        Your mission is to determine if the `analyzed_user_data` accurately and sufficiently reflects the user's profile based on the original **question-answer sets ({qa_pairs})**.

        **Instructions:**
        1.  Review the inputs: {target_profile_category}, {qa_pairs}, {analyzed_user_data}.
        2.  Apply the **Evaluation Guide** below for the given `target_profile_category`.
        3.  Judge based on **Accuracy** (correct) and **Sufficiency** (complete). Both criteria must be met for a `valid` result. Otherwise, it is `invalid`.
        4.  Provide the output in the specified JSON format. The `explanation` field **must be in Korean** and clearly state the reasoning for your judgment.

        ---

        ### **Evaluation Guide by Data Type**

        *   **`investment_goal`** (List[str])
            *   **Valid**: Includes all key goals (e.g., '노후 준비', '주택 마련') mentioned in the **question-answer sets** without omission.
            *   **Invalid**: Fails to include a key goal (lacks Sufficiency) or adds a goal that was not mentioned (lacks Accuracy).

        *   **`investment_emotions`** (List[str])
            *   **Valid**: Accurately reflects the main emotions expressed in the **question-answer sets** (e.g., '불안감', '아쉬움').
            *   **Invalid**: Incorrectly includes investment *tendencies* or *attitudes* (e.g., '보수적', '원금 보장 선호') instead of emotions (lacks Accuracy), or omits clearly stated emotions (lacks Sufficiency).

        *   **`interests_categories`** (List[str])
            *   **Valid**: Includes all mentioned investment topics/assets (e.g., '미국 주식', 'ETF').
            *   **Invalid**: Omits any of the key topics mentioned.

        *   **`investment_level`** & **`knowledge_level`** (str: 'beginner'|'intermediate'|'advanced')
            *   **Valid**: The classification is reasonably justified by the user's experience (e.g., duration, amount) or demonstrated knowledge within the **question-answer sets**.
            *   **Invalid**: The classification clearly misrepresents or distorts the user's experience or knowledge.

        ---

        ### **Output Format (JSON)**

        **[Example for a Valid case (유효한 경우 예시)]**
        ```json
        {{
        "is_valid": true,
        "explanation": "질문-답변 세트에서 언급된 '노후 준비'와 '주택 마련'이라는 두 가지 핵심 목표를 모두 정확하게 포함하고 있으므로 유효함."
        }}
        ```

        **[Example for an Invalid case (무효한 경우 예시)]**
        ```json
        {{
        "is_valid": false,
        "explanation": "판단 근거: 불충분성. 질문-답변 세트에서 '노후 준비' 외에 '주택 마련'이라는 목표도 언급되었으나, 분석된 데이터에서 누락되었으므로 무효함."
        }}
        ```
    """

    prompt_template = PromptTemplate(
        template=prompt,
        input_variables=["analyzed_user_data", "target_profile_category", "qa_pairs"],
    )

    llm: ChatOpenAI = get_llm_models(OPENAI_MODEL_NAME)
    structured_llm = llm.with_structured_output(ValidationAnalysisData)

    chain = prompt_template | structured_llm

    target_category = state.target_profile_category[0]
    analysis_user_answer = state.user_meta_data.get(target_category, [])

    raw_schema = chain.invoke(
        {
            "analyzed_user_data": analysis_user_answer,
            "target_profile_category": target_category,
            "qa_pairs": state.user_answers_by_category.get(target_category, []),
        }
    )

    try:
        raw_data: ValidationAnalysisData = ValidationAnalysisData.model_validate(
            raw_schema
        )
    except ValidationError as e:
        raise ValueError(f"Unexpected result type from chain.invoke: {e}")

    return {
        "messages": [
            {
                "type": "ai",
                "content": raw_data.explanation,
            }
        ],
    }

    # return {

    #     "evaluation_results": {
    #         **state.evaluation_results,
    #         target_profile_category: schema.is_valid,
    #     },
    #     "evaluation_results_logs": {
    #         **state.evaluation_results_logs,
    #         target_profile_category: schema.explanation,
    #     },
    # }


def summarize_user_profile(state: OverallState, config: RunnableConfig) -> OutputState:
    prompt = """You are an expert Korean financial advisor named '자산구조대'. Your task is to create a warm, encouraging, and personalized summary for a user based on their investment profile.

    User Profile Data:
    - Investment Goals: {investment_goals}
    - Investment Emotions: {investment_emotions}
    - Areas of Interest: {interests_categories}
    - Investment Experience: {investment_level}
    - Financial Knowledge: {knowledge_level}
    - Risk Tolerance: {risk_tolerance}

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
            "investment_goal",
            "investment_emotions",
            "interests_categories",
            "investment_level",
            "knowledge_level",
            "risk_tolerance",
        ],
    )

    llm = get_llm_models(OPENAI_MODEL_NAME)
    structured_llm = llm.with_structured_output(UserProfileSummary)

    chain = prompt_template | structured_llm

    raw_schema = chain.invoke(
        {
            "investment_goals": state.user_meta_data["investment_goal"],
            "investment_emotions": state.user_meta_data["investment_emotions"],
            "interests_categories": state.user_meta_data["interests_categories"],
            "investment_level": state.user_meta_data["investment_level"],
            "knowledge_level": state.user_meta_data["knowledge_level"],
            "risk_tolerance": state.user_meta_data["risk_tolerance"],
        }
    )

    try:
        raw_summary: UserProfileSummary = UserProfileSummary.model_validate(raw_schema)
    except ValidationError as e:
        raise ValueError(f"Unexpected result type from chain.invoke: {e}")

    user_profile_summary: str = raw_summary.summary

    # =========== vector 생성 코드  코드 나중에 노드로 분리 필요

    load_dotenv(Path(__file__).parents[4] / ".env")

    client = OpenAI(
        api_key=os.getenv("UPSTATE_API_KEY"),
        base_url=os.getenv("UPSTATE_BASE_URL"),
    )

    embedding_response = client.embeddings.create(
        input=user_profile_summary, model="embedding-query"
    )

    user_profile_vector = embedding_response.data[0].embedding

    # =========================================================

    # =========== Summary 를 DB에 저장하는 코드 나중에 노드로 분리 필요

    profile_service: ProfileService | None = config["configurable"].get(
        "profile_service"
    )

    if profile_service is not None:
        current_category = "user_profile_summary"
        current_data = user_profile_summary

        profile_service.update_category(current_category, current_data)
        profile_service.update_category("user_profile_vector", user_profile_vector)

    # =========================================================

    return OutputState(
        logs=[
            {
                "level": "info",
                "message": "User profile summary generated",
                "timestamp": time.time(),
            }
        ],
        messages=[{"type": "ai", "content": user_profile_summary}],
        user_meta_data={
            **state.user_meta_data,
            "user_profile_summary": user_profile_summary,
            "user_profile_vector": user_profile_vector,
        },
    )
