"""
WRITER: Kang Joseph
DATE: 2025-08-12
DESCRIPTION: This file contains the nodes for the questions.
"""

import time
from operator import add

from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Annotated, Any

from my_app.chatbot.langgraph_core.llm_agents import (
    GEMINI_MODEL_NAME,
    get_llm_agents,
)
from my_app.chatbot.langgraph_core.state import OverallState


class FollowUpQA(BaseModel):
    category: Annotated[str, Field(description="User profile category to set")]
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
            description="Per-question choices. Must be 2 lists, each containing options.",
        ),
    ]

    # Pydantic field validators are not working as expected.
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


PREDEFINED_QA: dict[str, dict[str, list[Any]]] = {
    "investment_goal": {
        "questions": [
            "투자 경험 - 귀하의 투자 경험에 대해 가장 잘 설명하는 것은 무엇인가요?",
            "투자 목표와 기간 - 투자를 통해 가장 중요하게 생각하는 목표는 무엇이며, 이를 위해 얼마나 오래 투자할 수 있나요?",
            "위험과 기대수익의 관계 - 다음 중 귀하의 투자 성향에 가장 가까운 설명은 무엇인가요?",
        ],
        "options": [
            [
                "투자 경험이 전혀 없습니다.",
                "주식, 채권 또는 뮤추얼 펀드에 대해 약간의 지식과 경험이 있습니다.",
                "다양한 유형의 투자에 대해 잘 알고 있으며 상당한 경험이 있습니다.",
                "저는 전문 투자자입니다.",
            ],
            [
                "(안정적 원금 유지) 3년 이내의 단기간 동안 원금을 안전하게 보존하는 것이 최우선입니다.",
                "(안정적 이자 수익) 3년에서 5년 정도의 기간 동안 예금보다 약간 높은 수준의 안정적인 이자 수익을 원합니다.",
                "(자산 증식) 5년 이상의 장기적인 관점에서 시장 평균 수준전 수익률을 목표로 자산을 꾸준히 증식시키고 싶습니다.",
                "(고수익 추구) 단기적인 손실을 감수하더라도 10년 이상의 장기 투자를 통해 시장 평균을 초과하는 높은 수익을 추구합니다.",
            ],
            [
                "원금 손실은 절대 용납할 수 없습니다. 수익이 거의 없더라도 원금이 보장되는 것이 가장 중요합니다.",
                "약간의 원금 손실 위험은 감수할 수 있지만, 그 대가로 예금 금리 이상의 수익을 기대합니다.",
                "투자 원금의 최대 20%까지 손실을 감수할 수 있으며, 이를 통해 장기적으로 주식 시장 평균 수준의 수익을 얻고 싶습니다.",
                "단기적으로 20% 이상의 손실도 감수할 수 있으며, 높은 위험을 감수하고 높은 수익을 목표로 합니다.",
            ],
        ],
    },
    "investment_emotions": {
        "questions": [
            "투자에 대해서 어떻게 생각하는지 알아볼까요?",
            "위험 상황에서의 감정적 반응 - 내가 보유한 투자 상품의 가치가 일주일 만에 15% 하락했다는 알림을 받았습니다. 이때 가장 먼저 드는 감정은 무엇인가요?",
            "투자 정보 탐색의 동기 - 투자에 대한 정보를 찾아보거나 관련 뉴스를 접할 때, 주로 어떤 생각이나 동기로 움직이나요?",
        ],
        "options": [
            [
                "내 자산을 성장시킹나 유망한 투자처를 남들보다 먼저 발견하고 싶다.",
                "내 자산을 인플레이션이나 예상치 못한 위험으부터 안전하게 지킬 방법을 찾고 싶다.",
                "시장 붕괴나 금리 인상 같은 악재를 미리 파악해서 손실을 피하는 것이 최우선이다.",
                "투자를 하려면 최소한 이 정도는 알아야 한다는 생각에 의무적으로 찾아본다.",
            ],
            [
                "장기적으로 보면 일시적인 변동일 뿐, 크게 신경 쓰지 않는다.",
                "'더 저렴할 때 살걸' 혹은 '고점에 팔걸' 하는 아쉬움이 남는다.",
                "손실이 더 커질까 봐 불안하고, 계속해서 계좌를 확인하게 된다.",
                "'역시 투자는 위험해', '투자를 시작하지 말았어야 했나' 하는 후회가 밀려온다.",
            ],
            [
                "새로운 성장 동력이나 유망한 투자처를 남들보다 먼저 발견하고 싶다.",
                "내 자산을 인플레이션이나 예상치 못한 위험으부터 안전하게 지킬 방법을 찾고 싶다.",
                "시장 붕괴나 금리 인상 같은 악재를 미리 파악해서 손실을 피하는 것이 최우선이다.",
                "투자를 하려면 최소한 이 정도는 알아야 한다는 생각에 의무적으로 찾아본다.",
            ],
        ],
    },
    "interests_categories": {
        "questions": [
            "미래 성장을 주도할 기술 분야 중 가장 관심 있는 분야는 무엇입니까?",
            "어떠한 산업의 사회적, 경제적 변화에 가장 큰 기회가 있다고 생각하십니까?",
            "실생활과 밀접하게 관련된 다음 분야 중, 투자 매력도가 가장 높다고 생각하는 분야는 어디입니까?",
        ],
        "options": [
            [
                "내 자산을 성장시킬 수 있는 가장 효과적인 방법이라는 긍정적인 믿음이 있다.",
                "미래를 위해 반드시 해야 하는 일이지만, 과정이 즐겁기보다는 의무감에 가깝다.",
                "잠재적 수익 가능성도 알지만, 언제든 손실을 볼 수 있다는 생각에 늘 조심스럽다.",
                "아직은 나와는 먼 이야기처럼 느껴지며, 무엇부터 알아봐야 할지 막막하다.",
            ],
            [
                "장기적으로 보면 일시적인 변동일 뿐, 크게 신경 쓰지 않는다.",
                "'더 저렴할 때 살걸' 혹은 '고점에 팔걸' 하는 아쉬움이 남는다.",
                "손실이 더 커질까 봐 불안하고, 계속해서 계좌를 확인하게 된다.",
                "'역시 투자는 위험해', '투자를 시작하지 말았어야 했나' 하는 후회가 밀려온다.",
            ],
            [
                "새로운 성장 동력이나 유망한 투자처를 남들보다 먼저 발견하고 싶다.",
                "내 자산을 인플레이션이나 예상치 못한 위험으로부터 안전하게 지킬 방법을 찾고 싶다.",
                "시장 붕괴나 금리 인상 같은 악재를 미리 파악해서 손실을 피하는 것이 최우선이다.",
                "투자를 하려면 최소한 이 정도는 알아야 한다는 생각에 의무적으로 찾아본다.",
            ],
        ],
    },
    "investment_level": {
        "questions": [
            "본인의 투자 경험을 가장 잘 설명하는 것은 무엇인가요?",
            "주식 시장이 단기적으로 20% 하락하는 상황을 가정할 때, 본인의 생각과 가장 가까운 것은 무엇인가요?",
            "성공적인 투자를 위한 포트폴리오(자산 구성) 운영에 대해 어떻게 생각하시나요?",
        ],
        "options": [
            [
                "주로 원금 손실 위험이 없는 예·적금을 이용하며, 투자는 아직 시작하지 않았습니다.",
                "투자 원금의 손실 가능성을 인지하고 있으며, 펀드나 주식에 소액으로 투자를 시작한 단계입니다.",
                "2년 이상 꾸준히 주식, 펀드 등에 투자하고 있으며, 스스로 종목이나 상품을 분석하고 선택합니다.",
                "주식, 채권 외에 해외주식, 파생상품, 대체투자(부동산, 원자재 등)를 포함한 자산 배분 전략을 직접 실행하고 있습니다.",
            ],
            [
                "원금 손실에 대한 두려움이 커서 보유 자산을 모두 팔고 시장을 떠날 것 같습니다.",
                "불안하지만, 장기적으로는 시장이 회복될 것이라 믿고 그대로 보유할 것입니다.",
                "시장 상황을 분석하며, 유망하다고 생각했던 주식을 추가로 매수할 기회로 삼을 수 있습니다.",
                "보유 자산의 위험도를 재평가하고, 포트폴리오 리밸런싱(자산 비중 재조정)을 적극적으로 실행할 것입니다.",
            ],
            [
                "어떤 종목이나 자산이 유망한지 잘 몰라 투자를 시작하기 어렵습니다.",
                "전문가나 지인이 추천하는 유망 종목 몇 개에 집중적으로 투자하는 것이 좋다고 생각합니다.",
                "주식과 채권, 또는 국내와 해외 자산처럼 서로 다른 성격의 자산에 나누어 투자하는 것이 중요하다고 생각합니다.",
                "시장 상황과 본인의 목표에 맞춰 정기적으로 자산 비중을 점검하고, 필요시 비중을 조절하는 과정이 필수적이라고 생각합니다.",
            ],
        ],
    },
    "knowledge_level": {
        "questions": [
            "30대 초반의 사회초년생이 장기적인 관점에서 은퇴 자금 마련을 위해 포트폴리오를 구성하려 합니다. 이 투자자의 상황에 가장 적합한 자산 배분 전략은 무엇일까요?",
            "주가가 계속 하락하는 주식을 보유한 투자자가 '언젠가는 오를 거야'라고 생각하며 손실을 확정하지 않고 계속 보유하는 행동을 가장 잘 설명하는 투자 심리 용어는 무엇인가요?",
            "포트폴리오의 '최대 낙폭(Maximum Drawdown, MDD)'이 크다는 것은 무엇을 의미하며, 이를 관리하기 위한 방법으로 적절하지 않은 것은 무엇인가요?",
        ],
        "options": [
            [
                "원금 보장을 위해 90%를 예금 및 국채에, 10%를 주식에 투자한다.",
                "높은 변동성을 감수하고 빠른 성장을 위해 100%를 유망한 기술주에 투자한다.",
                "장기적인 성장을 추구하며 위험을 분산하기 위해 70%를 글로벌 주식 펀드에, 30%를 채권 펀드에 투자한다.",
                "시장 예측이 불가능하므로 자산의 50%는 현금으로 보유하고 50%는 금(Gold)에 투자한다.",
            ],
            [
                "확증 편향 (Confirmation Bias)",
                "손실 회피 편향 (Loss Aversion)",
                "밴드왜건 효과 (Bandwagon Effect)",
                "지식의 환상 (Illusion of Knowledge)",
            ],
            [
                "의미: 전고점 대비 가장 크게 하락한 비율이 크다는 것 / 관리 방안: 자산 배분 리밸런싱 주기적으로 실행",
                "의미: 단기간에 가장 높은 수익을 낼 수 있는 잠재력이 크다는 것 / 관리 방안: 레버리지(대출)를 적극적으로 활용",
                "의미: 자산 가치가 고점 대비 큰 폭으로 하락할 수 있는 위험이 크다는 것 / 관리 방안: 포트폴리오에 금, 달러 등 안전자산을 편입",
                "의미: 변동성이 큰 시기에 큰 손실을 볼 수 있다는 것 / 관리 방안: 손절매(Stop-loss) 원칙을 설정하고 지킴",
            ],
        ],
    },
    "risk_tolerance": {
        "questions": [
            "당신의 투자 목표에 가장 부합하는 투자 방식은 무엇입니까?",
            "만약 당신의 투자 포트폴리오 가치가 단기간에 20% 하락했다면 어떻게 대응하시겠습니까?",
            "다음 중 당신의 투자 성향을 가장 잘 설명하는 것은 무엇입니까?",
        ],
        "options": [
            [
                "원금 손실의 위험을 최소화하고 안정적인 이자 수익을 추구합니다.",
                "약간의 위험을 감수하더라도 예금 금리 이상의 수익을 기대합니다.",
                "투자 원금의 단기적인 손실을 감수하더라도 장기적으로 높은 자본 수익을 추구합니다.",
                "높은 위험을 감수하더라도 시장 평균 수익률을 훨씬 뛰어넘는 초과 수익을 추구합니다.",
            ],
            [
                "추가적인 손실이 두려워 보유 자산의 대부분을 즉시 매도하겠습니다.",
                "손실이 지속될까 불안하여 포트폴리오의 일부를 매도하여 위험을 줄이겠습니다.",
                "불안감을 느끼지만, 장기적인 계획을 믿고 기존 포트폴리오를 유지하겠습니다.",
                "저가 매수의 기회라고 판단하고, 추가 자금을 투입하는 것을 적극적으로 고려하겠습니다.",
            ],
            [
                "투자 원금에서 5% 이상의 손실이 발생하면 일상생활에 신경이 쓰일 정도로 불편합니다.",
                "투자 원금이 10% 이상 손실 나면 불안하지만, 장기적으로는 회복될 것이라 생각합니다.",
                "투자 원금이 20% 이상 손실 나더라도, 장기적 목표를 위해 감내할 수 있습니다.",
                "30% 이상의 큰 손실이 발생해도 장기적인 관점에서 크게 동요하지 않습니다.",
            ],
        ],
    },
}


def present_predefined_questions(state: OverallState) -> dict:
    current_profile_category: str = state.target_profile_category[0]

    qa_sets = PREDEFINED_QA[current_profile_category]
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

    # 안내 메시지(사용자에게 질문에 답변해달라고 요청)
    instruction_message: HumanMessage = HumanMessage(content=prompt_content)

    return {
        "messages": [instruction_message],
        "questions_by_category": {
            current_profile_category: {
                "questions": questions,
                "options": options,
            }
        },
    }


def create_followup_qa(state: OverallState):
    current_category: str = getattr(state, "target_profile_category", [])[0]
    qa_pairs: list[tuple[str, str]] = state.user_answers_by_category.get(
        current_category, []
    )

    prompt = """
    You are generating follow-up multiple-choice questions to refine a user's {target_profile_category} profile.

    Input:
    - target_profile_category: the category of the profile that the user is being evaluated for.
    - qa_pairs: a list of [question, answer] pairs in chronological order. The last pair is the most recent interaction. Example: [["질문 A","답변 a"], ["질문 B","답변 b"]]

    Requirements:
    1) Produce exactly 2 follow-up questions, and they must be written in Korean.
    2) For each question, produce exactly 4 answer options, all written in Korean. Never produce 3 or 5 options.
    3) Avoid duplicate or near-duplicate options. Do not repeat topics or wording already covered in the prior questions within qa_pairs; ask from a new, deeper angle.
    4) Tone: friendly and concise.
    5) Output must be a single JSON object only, with the schema: {{"questions":[str, str], "options":[[str, str, str, str],[str, str, str, str]]}}.

    Input: {target_profile_category}, {qa_pairs}
    """

    prompt_template = PromptTemplate(
        input_variables=["target_profile_category", "qa_pairs"],
        template=prompt,
    )

    # 여기는 또 도구랑 결합 안한 애로 데려와야 output을 받을 수 있네 하하
    llm = get_llm_agents(GEMINI_MODEL_NAME)
    structured_llm = llm.with_structured_output(FollowUpQA)

    chain = prompt_template | structured_llm

    raw_result = chain.invoke(
        {
            "target_profile_category": current_category,
            "qa_pairs": qa_pairs,
        }
    )

    try:
        follow_up_qa: FollowUpQA = FollowUpQA.model_validate(raw_result)
    except ValidationError as e:
        raise ValueError(f"Unexpected result type from chain.invoke: {e}")

    # 안내 메시지(사용자에게 질문에 답변해달라고 요청)
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

    existing_questions_by_category = getattr(state, "user_answers_by_category", {})
