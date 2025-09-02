"""
WRITER: Kang Joseph
DATE: 2025-08-12
DESCRIPTION: This file contains the nodes for the questions.
"""

import time
from operator import add

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableAssign, RunnablePassthrough
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Annotated

from my_app.chatbot.chat_core.model_loader import (
    GEMINI_MODEL_NAME,
    OPENAI_MODEL_NAME,
    get_llm_models,
)
from my_app.chatbot.chat_core.prompt_loader import (
    load_prompt_from_yaml,
)
from my_app.chatbot.chat_core.state import OverallState


class FollowUpQA(BaseModel):
    questions: Annotated[
        list[str],
        add,
        Field(
            description="Follow-up questions.",
        ),
    ]
    options: Annotated[
        list[list[str]],
        add,
        Field(
            description="Per-question choices.",
        ),
    ]

    # # Pydantic field validators are not working as expected.
    # @field_validator("questions")
    # @classmethod
    # def validate_questions_len(cls, value: list[str]) -> list[str]:
    #     if len(value) != 2:
    #         raise ValueError("questions must contain exactly 2 items")
    #     if any(not isinstance(q, str) or not q.strip() for q in value):
    #         raise ValueError("each question must be a non-empty string")
    #     return value

    # @field_validator("options")
    # @classmethod
    # def validate_options_shape(cls, value: list[list[str]]) -> list[list[str]]:
    #     if len(value) != 2:
    #         raise ValueError("options must contain exactly 2 lists (one per question)")
    #     for idx, opt in enumerate(value):
    #         if not isinstance(opt, list) or len(opt) != 4:
    #             raise ValueError(f"options[{idx}] must contain exactly 4 string items")
    #         if any(not isinstance(o, str) or not o.strip() for o in opt):
    #             raise ValueError("all options must be non-empty strings")
    #     return value


class GenerateFollowUp(BaseModel):
    pass


def present_predefined_questions(state: OverallState) -> dict:
    current_profile_category: str = state.target_profile_category[0]

    persona_prompt = load_prompt_from_yaml("persona")
    introduce_qa = load_prompt_from_yaml("introduce_qa")

    prompt_template: RunnableAssign = (
        RunnablePassthrough.assign(chat_history=persona_prompt) | introduce_qa  # type: ignore
    )

    llm = get_llm_models(GEMINI_MODEL_NAME)
    chain = prompt_template | llm

    result = chain.invoke(
        {
            "target_profile_category": current_profile_category,
            "user_name": state.user_meta_data["name"],
        }
    )

    ai_message_to_user = AIMessage(content=result.content)

    predefined_qa = load_prompt_from_yaml("predefined_qa")

    qa_sets = predefined_qa[current_profile_category]
    questions = qa_sets["questions"]
    options = qa_sets["options"]

    prompt_content = f"""
Ask the user predefined quiz sets.
Use the 'RequestHumanInput' tool to ask the user with predefined quiz sets.

Predefined quiz sets:
- Category: {current_profile_category}
- Questions: {questions}
- Options: {options}
"""
    instruction_message: HumanMessage = HumanMessage(content=prompt_content)

    return {
        "messages": [ai_message_to_user, instruction_message],
        "questions_by_category": {
            current_profile_category: {
                "questions": questions,
                "options": options,
            }
        },
    }


def create_followup_qa(state: OverallState):
    current_category: str = getattr(state, "target_profile_category", [])[0]
    user_answer_compacted: list[str] = state.user_answers_compacted.get(
        current_category, []
    )

    prompt = """
Analyze the following user's investment profile to identify the primary contradiction.
User Profile: "{compacted_user_answer}"
Based on this contradiction, generate two multiple-choice questions designed to clarify the user's true {target_category}.
Each question must have four distinct options that help the user prioritize their conflicting preferences.
**Specific instructions for the '{target_category}' category:**
{category_instruction}.
"""

    instruction: dict[str, str] = {
        "interests_categories": "The questions should connect the user's conflicting preferences to specific investment products. Ask the user to choose which asset class they would feel more comfortable investing in, presenting options that reflect different levels of risk and return (e.g., individual tech stocks vs. government bonds)",
        "investment_emotions": "One of the questions must present a hypothetical market scenario (e.g., 'Your portfolio has dropped 20% in one month'). The options should focus on the user's likely emotional reaction (e.g., 'Anxious and wanting to sell immediately,' 'Concerned but holding,' 'Seeing it as a buying opportunity')",
        "investment_goal": "The questions should force the user to prioritize their ultimate investment objective. Frame the options in terms of life goals or financial outcomes, forcing a choice between a 'high-growth, potentially high-loss' path and a 'slow-growth, high-safety' path (e.g., 'Aiming for early retirement even with risks' vs. 'Ensuring wealth preservation for the future')",
        "investment_level": "The questions should gauge the user's practical experience and confidence. Ask about their past actions or their comfort level with specific investment tasks (e.g., 'How do you typically react to market news?' or 'Which of these actions have you personally taken in the last year?'). The options should range from passive (e.g., 'Set it and forget it') to active (e.g., 'Actively researching and rebalancing my portfolio')",
        "knowledge_level": "One question should be designed to test the user's understanding of a fundamental investment concept directly related to the contradiction, such as the relationship between risk and return. For example, ask 'Which statement about investing is most true?' with options that reveal their understanding (or misunderstanding) of why higher returns typically require taking on more risk",
        "risk_tolerance": "The questions must quantify risk and return to force a concrete choice. Present hypothetical investment scenarios with specific potential gains and losses over a set period (e.g., 'Which of the following one-year outcomes for a $10,000 investment would you be most comfortable with?'). The options should clearly lay out the best-case and worst-case scenarios (e.g., 'A chance to gain $3,000, with a risk of losing $2,000').",
    }

    prompt_template = PromptTemplate(
        template=prompt,
        input_variables=[
            "compacted_user_answer",
            "target_category",
            "category_instruction",
        ],
    )

    # 여기는 또 도구랑 결합 안한 애로 데려와야 output을 받을 수 있네 하하
    llm = get_llm_models(OPENAI_MODEL_NAME)

    chain = prompt_template | llm.with_structured_output(FollowUpQA)

    raw_result = chain.invoke(
        {
            "compacted_user_answer": user_answer_compacted,
            "target_category": current_category,
            "category_instruction": instruction[current_category],
        }
    )

    try:
        follow_up_qa: FollowUpQA = FollowUpQA.model_validate(raw_result)
    except ValidationError as e:
        raise ValueError(f"Unexpected result type from chain.invoke: {e}")

    instruction_message: HumanMessage = HumanMessage(
        content=f"""
Ask user follow-up quiz sets. Use the 'RequestHumanInput' Tool.
Follow-up quiz sets will be passed to the tool.
Generate message to introduce the Data's purpose to user.

Follow-up quiz sets:
- Category: {current_category}
- Questions: {follow_up_qa.questions}
- Options: {follow_up_qa.options}
"""
    )

    existing_questions_by_category = getattr(state, "questions_by_category", {})
    current_quiz_content = existing_questions_by_category.get(current_category, {})
    current_questions = current_quiz_content.get("questions", [])
    current_options = current_quiz_content.get("options", [])

    return {
        "messages": [instruction_message],
        "logs": [
            {
                "level": "info",
                "message": "follow-up questions collected",
                "timestamp": time.time(),
            }
        ],
        "questions_by_category": {
            **existing_questions_by_category,
            current_category: {
                "questions": current_questions + follow_up_qa.questions,
                "options": current_options + follow_up_qa.options,
            },
        },
    }
