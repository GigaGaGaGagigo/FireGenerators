from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Literal

from ui.chatbot.langgraph_core.llm_agents import (
    GEMINI_MODEL_NAME,
    get_llm_agents,
)
from ui.chatbot.langgraph_core.state import OverallState


class EvaluationAnalysisResponseSchema(BaseModel):
    is_valid: Literal["valid", "invalid"] = Field(
        description="Whether the user's response is valid for the category"
    )
    explanation: str = Field(description="Explanation for the assessment")


def evaluation_analysis(state: OverallState) -> dict:
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

    llm = get_llm_agents(GEMINI_MODEL_NAME)
    structured_llm = llm.with_structured_output(EvaluationAnalysisResponseSchema)

    chain = prompt_template | structured_llm

    target_category = state.target_profile_category[0]
    analyzed_user_data = None

    if target_category == "investment_goal":
        analyzed_user_data = state.investment_goal
    elif target_category == "investment_emotions":
        analyzed_user_data = state.investment_emotions
    elif target_category == "interests_categories":
        analyzed_user_data = state.interests_categories
    elif target_category == "investment_level":
        analyzed_user_data = state.investment_level
    elif target_category == "knowledge_level":
        analyzed_user_data = state.knowledge_level
    else:
        raise ValueError(f"Invalid target_profile_category: {target_category}")

    raw_schema = chain.invoke(
        {
            "analyzed_user_data": analyzed_user_data,
            "target_profile_category": target_category,
            "qa_pairs": state.answers_by_category.get(target_category, []),
        }
    )

    try:
        schema: EvaluationAnalysisResponseSchema = (
            EvaluationAnalysisResponseSchema.model_validate(raw_schema)
        )
    except ValidationError as e:
        raise ValueError(f"Unexpected result type from chain.invoke: {e}")

    target_profile_category: Literal[
        "investment_goal",
        "investment_emotions",
        "interests_categories",
        "investment_level",
        "knowledge_level",
    ] = state.target_profile_category[0]

    return {
        "evaluation_results": {
            **state.evaluation_results,
            target_profile_category: schema.is_valid,
        },
        "evaluation_results_logs": {
            **state.evaluation_results_logs,
            target_profile_category: schema.explanation,
        },
    }
