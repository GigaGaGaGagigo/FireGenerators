import json
import time

from langchain.prompts import PromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from my_app.chatbot.chat_core.model_loader import OPENAI_MODEL_NAME, get_llm_models
from my_app.chatbot.chat_core.prompt_loader import load_prompt_from_yaml
from my_app.chatbot.chat_core.state import OverallState


class GenerateQuestions(BaseModel):
    pass


class RequestUserInput(BaseModel):
    pass


class CombineUserMetaData(BaseModel):
    pass


class PresentQuestions(BaseModel):
    pass


class UpdateProfileList(BaseModel):
    content: list[str] = Field(
        description="A list of strings containing the analysis result."
    )


def ask_to_start_conversation(state: OverallState):
    ai_message = AIMessage(
        content=f"{state.user_meta_data['name']}님, 오늘의 정보와 관련된 대화를 진행해보고 싶으신가요?"
    )

    prompt_content = """
Ask user to start conversation.
Use the 'RequestUserInput' tool to ask user to start conversation.
"""
    human_message = HumanMessage(content=prompt_content)

    return {
        "logs": [
            {
                "level": "info",
                "message": "Ask user to start conversation",
                "timestamp": time.time(),
            }
        ],
        "messages": [ai_message, human_message],
        "user_meta_data": {
            **state.user_meta_data,
            "edit_mode": "ASKING",
        },
    }


def process_to_start_conversation(state: OverallState):
    try:
        last_message = state.messages[-1]
        tool_call = getattr(last_message, "tool_calls", [])[0]
        tool_call_id: str = tool_call["id"]

        questions_to_ask: dict[str, list[list[str]] | list[str] | str] = {
            "category": "continue_conversation",
            "questions": ["대화를 진행하시겠습니까?"],
            "options": [["yes", "no"]],
        }

    except (IndexError, KeyError, AttributeError, Exception) as e:
        return {
            "logs": [
                {
                    "level": "error",
                    "message": f"failed to extract tool_call: {e}",
                    "timestamp": time.time(),
                }
            ]
        }

    user_answers: list[tuple[str, str]] = interrupt(questions_to_ask)

    user_answer = user_answers[0][1]

    edit_mode = "CONTINUE" if user_answer == "yes" else "FINISHED"

    tool_message: ToolMessage = ToolMessage(
        content=str(user_answers),
        tool_call_id=tool_call_id,
    )

    return {
        "messages": [tool_message],
        "logs": [
            {
                "level": "info",
                "message": "user_answers collected for start conversation",
                "timestamp": time.time(),
            }
        ],
        "user_meta_data": {
            **state.user_meta_data,
            "edit_mode": edit_mode,
        },
    }


def decide_to_continue_conversation(state: OverallState):
    edit_mode = state.user_meta_data["edit_mode"]

    human_message = (
        "Continue the conversation. Call 'GenerateQuestions' tool."
        if edit_mode == "CONTINUE"
        else "Finish the conversation."
    )

    return {
        "messages": [HumanMessage(content=human_message)],
        "logs": [
            {
                "level": "info",
                "message": "Decide to continue conversation",
                "timestamp": time.time(),
            }
        ],
        "user_meta_data": {
            **state.user_meta_data,
            "edit_mode": edit_mode,
        },
    }


def talk_llm(state: OverallState):
    llm = get_llm_models(OPENAI_MODEL_NAME, tool=True, new_user=False)
    messages = state.messages
    response = llm.invoke(messages)
    return {"messages": [response]}


def generate_questions_based_on_report(state: OverallState):
    target_profile_category = [
        "interests_categories",
        "investment_emotions",
        "investment_goal",
        "risk_tolerance",
    ]
    report = state.search_dataset["report"]

    prompt_content = """
You are a 'Prompt Engineer' who analyzes a user's investment tendencies to create a personalized profile. 
Your mission is to analyze the provided {report} data in JSON format and generate a set of questions to understand the user's disposition for each item specified in {target_profile_category}.

1.  **Analyze Input Data**: Analyze the "summary", "key_opportunities", "potential_risks", and "analyst_take" sections of the given {report} to comprehensively understand the profile of a potential investor (interests, emotions, goals, risk tolerance).
2.  **Generate Questions and Options**:
    *   For each item specified in {target_profile_category}, create **3 questions** designed to verify and elaborate on the inferred investment profile.
    *   Each question must be accompanied by **4 options** for the user to choose from.
3.  **Prevent Bias**: To avoid leading the user, minimize the direct use of specific keywords from the {report} (e.g., 'AI', 'semiconductor') in the questions. Instead, use more abstract and neutral language.
4.  **Output Format**: The final output must strictly adhere to the JSON structure provided in the example below. Do not add numbers or letters to the questions or options.

Output only the JSON object as plain text, without any markdown, code block, or extra formatting.
{{
    "interests_categories": {{
        "questions": ["새로운 투자 기회를 탐색할 때 어떤 유형의 정보에 가장 먼저 주목하시나요?", "...", "..."],
        "options": [[
        "안정적인 현금 흐름을 가진 전통 산업 관련 뉴스",
        "기술 혁신으로 미래 시장을 주도할 신흥 기술 동향",
        "정부 정책 변화나 규제 완화에 따른 수혜 분야 분석",
        "시장 변동성이 낮고 예측 가능한 분야의 보고서"
        ],["..."],["..."]]
    }},
    "investment_emotions": {{
        "questions": ["유망한 투자처를 발견했지만, 동시에 잠재적 위험에 대한 경고를 접했을 때 어떤 감정이 드시나요?", "...", "..."],
        "options": [[
        "위험을 감수하더라도 기회를 잡아야 한다는 강한 기대감",
        "기회와 위험을 신중하게 분석하며 관망하려는 침착함",
        "손실 가능성에 대한 우려로 투자를 주저하게 되는 불안감",
        "이미 알려진 위험이라면 문제가 없다고 생각하는 낙관론"
        ],["..."], ["..."]]
    }},
    // ... (이하 생략) ...
}}
"""

    prompt = PromptTemplate.from_template(template=prompt_content)
    llm = get_llm_models(OPENAI_MODEL_NAME)
    chain = prompt | llm

    result = chain.invoke(
        {"report": report, "target_profile_category": target_profile_category}
    )

    result_json = json.loads(result.content)

    last_message = state.messages[-1]
    tool_call = getattr(last_message, "tool_calls", [])[0]
    tool_call_id: str = tool_call["id"]

    tool_message: ToolMessage = ToolMessage(
        content=str(result_json),
        tool_call_id=tool_call_id,
    )

    return {
        "messages": [tool_message],
        "logs": [
            {
                "level": "info",
                "message": "questions generated based on report",
                "timestamp": time.time(),
            }
        ],
        "questions_by_category": result_json,
        "target_profile_category": target_profile_category,
    }


def decide_to_present_questions(state: OverallState):
    return {
        "messages": [
            HumanMessage(
                content="Ask user to answer the questions. Call 'PresentQuestion' tool."
            )
        ],
        "logs": [
            {
                "level": "info",
                "message": "Decide to present questions",
                "timestamp": time.time(),
            }
        ],
    }


def present_questions_based_on_report(state: OverallState):
    last_message = state.messages[-1]
    tool_call = getattr(last_message, "tool_calls", [])[0]
    tool_call_id: str = tool_call["id"]

    current_category = state.target_profile_category[0]
    questions = state.questions_by_category[current_category]["questions"]
    options = state.questions_by_category[current_category]["options"]

    questions_to_ask: dict[str, list[list[str]] | list[str] | str] = {
        "category": current_category,
        "questions": questions,
        "options": options,
    }
    user_answers: list[tuple[str, str]] = interrupt(questions_to_ask)

    if not user_answers:
        return {
            "logs": [
                {
                    "level": "warning",
                    "message": "failed to extract user_answers",
                    "timestamp": time.time(),
                }
            ],
            "messages": [
                {"tool_call_id": tool_call_id, "type": "tool", "content": "[]"}
            ],
        }

    tool_message: ToolMessage = ToolMessage(
        content=str(user_answers),
        tool_call_id=tool_call_id,
    )

    return {
        "messages": [tool_message],
        "logs": [
            {
                "level": "info",
                "message": "user_input collected",
                "timestamp": time.time(),
            }
        ],
        "user_answers_by_category": {
            **state.user_answers_by_category,
            current_category: user_answers,
        },
    }


def compact_user_answer_based_on_report(state: OverallState):
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
        "messages": [],
        "logs": [
            {
                "level": "info",
                "message": f"User answer compacted based on report for {current_category}",
                "timestamp": time.time(),
            }
        ],
        "user_answers_compacted": {
            current_category: [response.content],
        },
    }


def analyze_user_answers_based_on_report(state: OverallState) -> dict:
    # 기존 메타 데이터를 저장할 곳이 필요함
    current_category = state.target_profile_category[0]

    prompt_list = {
        "interests_categories": load_prompt_from_yaml("analysis_interests_categories"),
        "investment_emotions": load_prompt_from_yaml("analysis_investment_emotions"),
        "investment_goal": load_prompt_from_yaml("analysis_investment_goal"),
        "risk_tolerance": load_prompt_from_yaml("analysis_risk_tolerance"),
    }

    prompt_template = prompt_list[current_category]

    llm = get_llm_models(OPENAI_MODEL_NAME)

    chain_list = {
        "interests_categories": prompt_template
        | llm.with_structured_output(UpdateProfileList),
        "investment_emotions": prompt_template
        | llm.with_structured_output(UpdateProfileList),
        "investment_goal": prompt_template
        | llm.with_structured_output(UpdateProfileList),
        "investment_level": prompt_template | llm,
        "knowledge_level": prompt_template | llm,
        "risk_tolerance": prompt_template | llm,
    }

    chain = chain_list[current_category]

    result = chain.invoke(  # type: ignore
        {"compacted_user_answer": state.user_answers_compacted[current_category]},
    )

    analysis_data = result.content

    message_prompt = f"{state.user_meta_data['name']}님과의 대화를 통해 새로  알아낸 내용은 다음과 같습니다:{analysis_data}"

    return {
        "logs": [
            {
                "level": "info",
                "message": f"User answer analyzed for {current_category}",
                "timestamp": time.time(),
            }
        ],
        "messages": [AIMessage(content=message_prompt)],
        "user_meta_data_updated": {
            **state.user_meta_data_updated,
            current_category: analysis_data,
        },
    }


def determine_next_user_node(state: OverallState):
    state.target_profile_category.pop(0)

    order_message = (
        HumanMessage(content="Call 'CombineUserMetaData' tool.")
        if len(state.target_profile_category) == 0
        else HumanMessage(content=" Call 'PresentQuestions' tool.")
    )

    return {
        "logs": [
            {
                "level": "info",
                "message": "Determine next user node",
                "timestamp": time.time(),
            }
        ],
        "messages": [order_message],
        "target_profile_category": state.target_profile_category,
    }


def combine_user_meta_data(state: OverallState):
    combine_categories = [
        "interests_categories",
        "investment_emotions",
        "investment_goal",
    ]

    prompt_list = {
        "interests_categories": """
# Persona
You are an expert data analyst specializing in updating and managing user metadata. Your primary function is to accurately interpret shifts in user preferences and merge data lists logically.

# Primary Task
You will receive two lists of investment interests: {old_data} and {new_data}. Your task is to merge these lists into a single, updated list of interests.

# Processing Rules
1.  **Uniqueness:** The final list must contain only unique items. Duplicates must be removed.
2.  **Prioritize New Data (Weighting):** The {new_data} list represents the user's most current interests. All unique items from {new_data} MUST be included in the final list.
3.  **Conflict Resolution and Merging:**
    *   Analyze the themes of both lists. The provided {old_data} focuses purely on growth/tech ("AI", "Future Growth Tech"). The {new_data} expands significantly into safe assets ("Government Bonds," "Short-term Bonds," "Cash Equivalents") and specific investment methods ("Individual Stocks," "Micro-investing"), while retaining one growth theme.
    *   This indicates a shift or expansion in strategy, not a complete replacement.
    *   Therefore, retain items from {old_data} ONLY IF they are not conceptually redundant or directly contradicted by the new, broader focus. (In this context, "AI" is a specific example of "Future Growth Tech," which was retained, so "AI" should also be retained as a related interest).
4.  **Order:** The specific order of the final list is less important than the inclusion of all relevant items, but new items should be treated as the primary interest set.
5.  **Output:** You must output ONLY the final, merged Python list (array) of strings. Do not add any explanatory text, reasoning.

# Output Format
You must output ONLY the final, merged Python list (array) of strings. Do not add any explanatory text, reasoning, or formatting.
        """,
        "investment_emotions": """
You are a "User Metadata Management Specialist" who meticulously analyzes and manages user data. Your mission is to merge existing data {old_data} with new data {new_data} to create a single, unified list (`updated_data`) that accurately reflects the user's latest state.

### CRITICAL INSTRUCTION
Your primary task is to **MERGE**, not simply replace. The final `updated_data` list must be a superset of {new_data} and all compatible elements from {old_data}. Do not discard {old_data} entirely unless all its elements conflict with {new_data}.

### Step-by-Step Process
You must follow this process exactly:
1.  **Initialize:** Start the `updated_data` list by adding all elements from {new_data}. This list represents the user's most current state.
2.  **Evaluate:** Iterate through each element of the {old_data} list one by one.
3.  **Decision:** For each element from {old_data}, determine if it semantically or emotionally conflicts with the overall context established by {new_data}.
4.  **Append:** If the element from {old_data} does **not** conflict, append it to the `updated_data` list. If it conflicts, discard it.

### Output Format
Your final output must be **only** the `updated_data` list, formatted as a Python list of strings. Do not include any other text, explanations, or formatting.

### Example
Learn how to apply the process by studying this example:
        """,
        "investment_goal": """
You are an expert User Profile Analyst AI. Your primary skill is to synthesize user data into a single, highly coherent summary sentence that captures their most current intentions.

# Objective
Analyze the user's {old_data} and {new_data} for the given {category}. Your goal is to produce a single, consolidated summary sentence that accurately reflects the user's updated profile, giving strict priority to {new_data} in case of any conflicts.

# Instructions
1.  **Analyze**: Examine the statements in both {old_data} and {new_data}.
2.  **CRITICAL RULE**: The output MUST be a single, complete, and natural-sounding sentence. Do not use multiple sentences or bullet points.
        """,
    }

    for category in combine_categories:
        prompt_string = prompt_list[category]
        prompt_template = PromptTemplate.from_template(template=prompt_string)
        llm = get_llm_models(OPENAI_MODEL_NAME)
        chain = prompt_template | llm
        result = chain.invoke(
            {
                "old_data": state.user_meta_data[category],
                "new_data": state.user_meta_data_updated[category],
                "category": category,
            }
        )
        state.user_meta_data[category] = result.content

    old_data = int(state.user_meta_data["risk_tolerance"])
    new_data = int(state.user_meta_data_updated["risk_tolerance"])
    updated_data = int((old_data + new_data) / 2)
    state.user_meta_data["risk_tolerance"] = updated_data

    return {
        "user_meta_data": {
            **state.user_meta_data,
            **state.user_meta_data_updated,
        },
    }
