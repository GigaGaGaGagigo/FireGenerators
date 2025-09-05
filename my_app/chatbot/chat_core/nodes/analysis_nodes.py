"""
WRITER: Kang Joseph
DATE: 2025-08-12
DESCRIPTION: Final response node(s) for summarizing the user's goal from Q&A.
"""

import time

from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Annotated, Literal

from my_app.chatbot.chat_core.model_loader import (
    OPENAI_MODEL_NAME,
    get_llm_models,
)
from my_app.chatbot.chat_core.prompt_loader import load_prompt_from_yaml
from my_app.chatbot.chat_core.state import OverallState


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

    chain = prompt_template | llm  # pyright: ignore[reportPossiblyUnboundVariable]

    result = chain.invoke(
        {"compacted_user_answer": state.user_answers_compacted[current_category]},
    )
    analysis_data = result.content

    message_prompt: str = ANALYSIS_USER_ANSWER_PROMPTS[current_category].format(
        user_name=state.user_meta_data["name"], data=analysis_data
    )

    return {
        "logs": [
            {
                "level": "info",
                "message": f"User answer analyzed for {current_category}",
                "timestamp": time.time(),
            }
        ],
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

    response = chain.invoke({"qa_pairs": qa_pairs, "target_category": current_category})

    return {
        "logs": [
            {
                "level": "info",
                "message": f"User answer compacted for {current_category}",
                "timestamp": time.time(),
            }
        ],
        "user_answers_compacted": {
            current_category: [response.content],
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


def summarize_user_profile(state: OverallState, config: RunnableConfig):
    prompt = """
You are a seasoned 20-year investment strategist. With experience from witnessing countless investor successes and failures, you can cut through the noise to see the underlying psychology and fatal risks hidden in data. 
Your analysis is blunt, direct, and brutally honest, gentle. Use polite language.
Using the provided `{data}`, write a sharp, analytical profile as **a single, continuous paragraph** following these instructions:

**Writing Instructions:**
1.  **Diagnose the Situation:** First, concisely diagnose the investor's current state. Weave together their goals, emotions, and knowledge level, but stick only to the critical facts.
2.  **Pinpoint the Core Problem:** Next, transition with a direct, hard-hitting phrase like **"최종 의견은 다음과 같습니다."** or **"The fatal flaw in this profile is..."** to pinpoint the most dangerous inconsistency or risk you've uncovered. hard-hitting phrase follow the data's language.
3.  **Provide Actionable Advice:** Finally, conclude with clear, actionable insights based on your diagnosis in one sentence. This isn't a theoretical exercise; it's a concrete prescription for what must be done now.
4.  **Final Format:** The output must not contain any headings or bullet points.
"""

    user_resource_data = {
        "investment_goal": state.user_meta_data["investment_goal"],
        "investment_emotions": state.user_meta_data["investment_emotions"],
        "interests_categories": state.user_meta_data["interests_categories"],
        "investment_level": state.user_meta_data["investment_level"],
        "knowledge_level": state.user_meta_data["knowledge_level"],
        "risk_tolerance": state.user_meta_data["risk_tolerance"],
    }

    prompt_template = PromptTemplate(
        template=prompt,
        input_variables=["data"],
    )

    llm = get_llm_models(OPENAI_MODEL_NAME)

    structured_llm = llm

    chain = prompt_template | structured_llm

    result = chain.invoke(
        {
            "data": user_resource_data,
        }
    )

    user_profile_summary: str = result.content

    ai_message = f"{state.user_meta_data['name']}님의 프로필 요약이 저장되었습니다. {state.user_meta_data['name']}님에 대한 간단한 분석 결과는 다음과 같습니다. {user_profile_summary}입니다."

    return {
        "logs": [
            {
                "level": "info",
                "message": "User profile summary generated",
                "timestamp": time.time(),
            }
        ],
        "messages": [AIMessage(content=ai_message)],
        "user_meta_data": {
            **state.user_meta_data,
            "user_profile_summary": user_profile_summary,
        },
    }
