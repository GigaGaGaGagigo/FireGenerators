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
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Annotated, Literal

from my_app.chatbot.langgraph_core.llm_agents import (
    GEMINI_MODEL_NAME,
    get_llm_agents,
)
from my_app.chatbot.langgraph_core.state import OutputState, OverallState
from my_app.chatbot.services.profile_service import ProfileService


class AnalyzeProfile(BaseModel):
    pass


class AnalysisData(BaseModel):
    data: list[str] = Field(
        description="""A list of strings containing the analysis result. 
        """
    )


class AnalysisRiskTolerance(BaseModel):
    data: int = Field(
        description="""this MUST be a list with a single string representing an integer score from 0 to 100, for example: ['75'].
        For other categories, this MUST be a list of strings.
        """
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


def analyze_user_answers(state: OverallState) -> dict:
    prompt = ""

    if state.target_profile_category[0] == "investment_goal":
        prompt = """
        You are an expert financial analyst AI. Your task is to analyze a list of question-and-answer pairs and summarize the user's investment goals into a concise, easy-to-understand paragraph.

        **Instructions:**
        1.  **Analyze the Input**: Carefully review the provided question-and-answer data in `{qa_pairs}`.
        2.  **Identify Key Information**: Extract the core information about the user's investment objectives, such as their financial goals (e.g., retirement, home purchase), investment horizon, and general approach to investing.
        3.  **Synthesize a Summary**: Combine the key information into a single, coherent paragraph. This summary should be a descriptive text, not a number or a score.
        4.  **Language**: The final summary must be written in Korean.

        **Example of a good summary:**
        "사용자님은 장기적인 관점에서 안정적인 노후 자금 마련을 최우선 목표로 하고 있으며, 이를 위해 약 10년 이상의 투자 기간을 고려하고 있습니다. 또한, 원금 손실에 대한 우려가 있어 보수적인 투자 방식을 선호하는 것으로 보입니다."

        **Input Data:**
        - `qa_pairs`: {qa_pairs}

        Based on your analysis, generate the summary paragraph.
        """
    elif state.target_profile_category[0] == "investment_emotions":
        prompt = """
        You are an expert emotion analyst specializing in extracting key emotions from a user's answers.
        Your goal is to analyze the provided list of **question-answer sets ({qa_pairs})** and extract core emotional keywords from each answer.

        **Instructions:**
            1.  **Understand the Input Data**: The input {qa_pairs} is a list of independent 'question-answer sets'.
            2.  **Scope of Analysis**: Your analysis should focus on the 'answer' text of each set. Refer to the 'question' to understand the context if the answer is ambiguous.
            3.  **Extract Core Emotions**:
                - From each answer, extract **up to two** core emotions as Korean nouns (e.g., '기대감', '아쉬움').
                - If no clear emotion can be found in an answer, **do not extract any keyword for it and simply skip it.**
            4.  **Output Format**:
                - Your final output must be a bulleted list containing only the keywords from the sets where emotions were found.
                - Items that were skipped should not be included in the final list in any form.

        **Example of Processing (처리 예시):**
        - Input Set 1:
            - 질문: "투자를 시작할 때 어떤 마음이셨나요?"
            - 답변: "수익을 낼 수 있을지 걱정도 되고, 한편으로는 설레기도 했어요."
            - Result: • 걱정, 설렘
        - Input Set 2:
            - 질문: "현재 보유하신 주식은 무엇인가요?"
            - 답변: "삼성전자와 카카오입니다."
            - Result: (No emotion to extract, so it is excluded from the final list)

        Now, begin your analysis of {qa_pairs}.
        Your final output should be a bulleted list consisting only of the extracted emotional keywords.

        input_variables:
            - qa_pairs
        """
    elif state.target_profile_category[0] == "interests_categories":
        prompt = """
        You will be provided with a list of data consisting of question-answer pairs. Your primary goal is to identify and extract core keywords related to investment topics from the answers.
        
        Output Format Constraints (Crucial):
        - The final output must be a simple bulleted list (e.g., * 키워드).
        - Do not write any introductory or concluding sentences, paragraphs, or any narrative text. Your response should contain only the list of keywords.
        - Ensure each keyword is unique and listed only once.
        
        Extraction Rules:
        1. Analyze {qa_pairs} as a list of question-answer pairs, and extract only the 'answer' part of each question-answer pair.
        2. List keywords independently. For example, '전기차 & 자율주행' must be separated into two keywords: '전기차' and '자율주행'.
        3. Filter for keywords that represent recognizable investment sectors, industries, or stock market categories. Exclude abstract concepts or strategies.
        
        Language: The final output must be in Korean.

        input_variables:
            - qa_pairs
        """
    elif state.target_profile_category[0] == "investment_level":
        prompt = """
        You are an expert investment analyst.
        Your primary task is to evaluate a user's investment knowledge, experience, and mindset based on a provided set of questions and their corresponding answers.
        Analyze {qa_pairs}, which is a list of tuples containing questions and the user's answers in Korean, holistically to determine their overall investment level.
        
        Your evaluation criteria are as follows:
            Beginner:
                Shows a primary focus on capital preservation and a strong fear of loss.
                Lacks a clear understanding of fundamental concepts like the risk-return tradeoff and diversification.
                Reacts emotionally to market volatility (e.g., would sell during a downturn).
                Has vague financial goals and little to no practical investment experience.
            Intermediate:
                Understands and can articulate core investment principles such as diversification and long-term investing.
                Has some practical experience (e.g., has started investing in stocks or funds).
                Can tolerate a moderate level of risk to achieve higher returns.
                Demonstrates a rational, long-term perspective during market downturns.
                Has specific, medium-to-long-term financial goals.
            Advanced:
                Demonstrates a deep understanding of investment strategies, portfolio management, and risk metrics.
                Has significant practical experience and a well-defined investment philosophy.
                Understands the impact of macroeconomic factors and investor psychology.
                Makes decisions based on a clear strategy, including proactive risk management like rebalancing or strategic asset allocation.
            
        Input Format:
            You will receive a Python list of tuples. Each tuple contains ('question', 'answer').
            - qa_pairs
        
        Output Format:
            Your response MUST be a single word in lowercase: beginner, intermediate, or advanced. Do not provide any explanations, reasoning, or additional text.
        """
    elif state.target_profile_category[0] == "knowledge_level":
        prompt = """
        You are an expert AI designed to evaluate a user's investment knowledge level based on their answers to a series of questions. 
        Your task is to analyze the provided list of question-and-answer pairs, {qa_pairs}, and classify the user's knowledge into one of three categories: 'beginner', 'intermediate', or 'advanced'.
        Evaluation Criteria:
            Beginner: The user demonstrates a misunderstanding of fundamental and core investment principles such as diversification, risk tolerance, asset allocation, and basic financial terminology. Their answers often reflect common misconceptions or an overly simplistic and high-risk approach to investing.
            Intermediate: The user has a solid grasp of basic investment concepts but may show gaps in knowledge regarding more advanced topics, such as specific risk metrics (e.g., Maximum Drawdown), behavioral finance theories, or nuanced portfolio management strategies. Their answers are generally on the right track but may lack depth or precision.
            Advanced: The user demonstrates a comprehensive and nuanced understanding of a wide range of investment topics, from fundamental principles to advanced theories and practical applications. Their answers are accurate, well-reasoned, and reflect an ability to think critically about complex financial scenarios.
        Instructions:
            Analyze the following input data and return only one of the three labels: 'beginner', 'intermediate', or 'advanced'.
        """
    elif state.target_profile_category[0] == "risk_tolerance":
        prompt = """
        You are an expert AI specializing in evaluating an investor's risk tolerance.
        Your task is to analyze the user's answers and provide a single numerical score representing their risk tolerance.

        - The score must be an integer between 0 and 100.
        - 0: extreme risk aversion (will not accept any possibility of losing principal)
        - 100: extreme risk tolerance (willing to take very high risks for potentially very high returns)

        Analyze the following question-answer pairs comprehensively:
        {qa_pairs}

        Based on your analysis, quantify the user's risk tolerance as a single integer score between 0 and 100.

        Output format instructions:
        - Your output MUST be a list containing a single string, where the string is the integer score.
        - Example: If the calculated score is 73, the output should be ["73"].
        - Do not include any explanations, reasons, or additional text. Just the list with the score string.
        """

    prompt_template = PromptTemplate(template=prompt, input_variables=["qa_pairs"])
    llm = get_llm_agents(GEMINI_MODEL_NAME)

    if state.target_profile_category[0] == "risk_tolerance":
        structured_llm = llm.with_structured_output(AnalysisRiskTolerance)
    else:
        structured_llm = llm.with_structured_output(AnalysisData)

    chain = prompt_template | structured_llm

    qa_pairs: list[tuple[str, str]] = state.user_answers_by_category[
        state.target_profile_category[0]
    ]

    print(qa_pairs)

    try:
        if state.target_profile_category[0] == "risk_tolerance":
            raw_analysis_data: AnalysisRiskTolerance = (
                AnalysisRiskTolerance.model_validate(
                    chain.invoke({"qa_pairs": qa_pairs})
                )
            )
        else:
            raw_analysis_data: AnalysisData = AnalysisData.model_validate(
                chain.invoke({"qa_pairs": qa_pairs})
            )
            if len(raw_analysis_data.data) <= 0:
                raise ValueError("No analyzed data")

    except ValidationError as e:
        raise ValueError(f"Unexpected result type from chain.invoke: {e}")

    analysis_data = raw_analysis_data.data

    current_category = state.target_profile_category[0]

    analysis_data

    return {
        "messages": [AIMessage(content=str(analysis_data))],
        "user_meta_data": {
            **state.user_meta_data,
            current_category: analysis_data,
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

    llm = get_llm_agents(GEMINI_MODEL_NAME)
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

    llm = get_llm_agents(GEMINI_MODEL_NAME)
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
