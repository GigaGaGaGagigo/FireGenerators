"""
WRITER: Kang Joseph
DATE: 2025-08-12
DESCRIPTION: Final response node(s) for summarizing the user's goal from Q&A.
"""

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Literal

from ui.chatbot.langgraph_core.llm_agents import (
    GEMINI_MODEL_NAME,
    get_llm_agents,
)
from ui.chatbot.langgraph_core.state import OverallState


class GoalAnalysisResult(BaseModel):
    analyzed_data: list[str] = Field(description="Analyzed data")


def analyze_user_goal(state: OverallState) -> dict:
    prompt = ""

    if state.target_profile_category[0] == "investment_goal":
        prompt = """
        You are an expert financial analyst AI. Your task is to synthesize a user's investment goal into a single, comprehensive paragraph based on a provided list of question-and-answer pairs.
        Instructions:
            1. Analyze {qa_pairs}, which is a list of tuples containing questions and the user's answers in Korean.
            2. Identify the key aspects of the user's investment profile:
                - Investment Experience
                - Primary and Secondary Goals (e.g., stable income, market-level returns)
                - Investment Horizon (short-term and long-term)
                - Risk Tolerance (e.g., maximum acceptable loss)
                - Flexibility and approach to balancing goals.
            3. Combine these identified aspects into a single, coherent paragraph that summarizes the user's overall investment objective.
            4. The final output must always be in Korean.
        
        input_variables:
            - target_profile_category
            - qa_pairs
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

    prompt_template = PromptTemplate(template=prompt, input_variables=["qa_pairs"])
    llm = get_llm_agents(GEMINI_MODEL_NAME)
    structured_llm = llm.with_structured_output(GoalAnalysisResult)
    chain = prompt_template | structured_llm

    target_category: Literal[
        "investment_goal",
        "investment_emotions",
        "interests_categories",
        "investment_level",
        "knowledge_level",
    ] = state.target_profile_category[0]

    qa_pairs: list[tuple[str, str]] = state.answers_by_category[target_category]

    try:
        result: GoalAnalysisResult = GoalAnalysisResult.model_validate(
            chain.invoke({"qa_pairs": qa_pairs})
        )
    except ValidationError as e:
        raise ValueError(f"Unexpected result type from chain.invoke: {e}")

    if len(result.analyzed_data) <= 0:
        raise ValueError("No analyzed data")

    update_dict = {
        "ai_messages": [],
        "workflow_stage": "generated_analyzed_data",
    }

    # target_category에 따라 동적으로 상태 업데이트
    if target_category in ["investment_level", "knowledge_level"]:
        # 이 필드들은 문자열이므로, 분석 결과의 첫 번째 문장을 저장합니다.
        if result.analyzed_data:
            update_dict[target_category] = result.analyzed_data[0]
    else:
        # 이 필드들은 문자열 리스트입니다.
        update_dict[target_category] = list(set(result.analyzed_data))

    return update_dict
