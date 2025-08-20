"""
WRITER: Kang Joseph
DATE: 2025-08-12
DESCRIPTION: This file contains the nodes for the questions.
"""

from operator import add

from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field, ValidationError, field_validator
from typing_extensions import Literal

from ui.chatbot.langgraph_core.llm_agents import (
    GEMINI_MODEL_NAME,
    get_llm_agents,
)
from ui.chatbot.langgraph_core.state import OverallState


class FollowUpQuestionsSchema(BaseModel):
    questions: list[str] = Field(
        description="Exactly 2 follow-up questions in Korean.",
        min_length=2,
        max_length=2,
    )
    options: list[list[str]] = Field(
        description="Per-question choices. Must be 2 lists, each containing exactly 4 options (Korean).",
        min_length=2,
        max_length=2,
    )

    @field_validator("questions")
    @classmethod
    def validate_questions_len(cls, value: list[str]) -> list[str]:
        if len(value) != 2:
            raise ValueError("questions must contain exactly 2 items")
        if any(not isinstance(q, str) or not q.strip() for q in value):
            raise ValueError("each question must be a non-empty string")
        return value

    @field_validator("options")
    @classmethod
    def validate_options_shape(cls, value: list[list[str]]) -> list[list[str]]:
        if len(value) != 2:
            raise ValueError("options must contain exactly 2 lists (one per question)")
        for idx, opt in enumerate(value):
            if not isinstance(opt, list) or len(opt) != 4:
                raise ValueError(f"options[{idx}] must contain exactly 4 string items")
            if any(not isinstance(o, str) or not o.strip() for o in opt):
                raise ValueError("all options must be non-empty strings")
        return value


def prepare_fixed_question_set(state: OverallState) -> dict:
    qa_sets: dict[str, list[list[str]] | list[str]] = {}

    if state.target_profile_category[0] == "investment_goal":
        ai_message: str = f"""
        고객님의 소중한 자산을 위한 첫걸음, 바로 나에게 맞는 투자 목표를 아는 것에서부터 시작해요. {state.user_name}님의 투자 목표를 같이 알아 보겠습니다.
        """

        qa_sets: dict[str, list[list[str]] | list[str]] = {
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
                    "(자산 증식) 5년 이상의 장기적인 관점에서 시장 평균 수준의 수익률을 목표로 자산을 꾸준히 증식시키고 싶습니다.",
                    "(고수익 추구) 단기적인 손실을 감수하더라도 10년 이상의 장기 투자를 통해 시장 평균을 초과하는 높은 수익을 추구합니다.",
                ],
                [
                    "원금 손실은 절대 용납할 수 없습니다. 수익이 거의 없더라도 원금이 보장되는 것이 가장 중요합니다.",
                    "약간의 원금 손실 위험은 감수할 수 있지만, 그 대가로 예금 금리 이상의 수익을 기대합니다.",
                    "투자 원금의 최대 20%까지 손실을 감수할 수 있으며, 이를 통해 장기적으로 주식 시장 평균 수준의 수익을 얻고 싶습니다.",
                    "단기적으로 20% 이상의 손실도 감수할 수 있습니다. 높은 위험을 감수하고 높은 수익을 목표로 합니다.",
                ],
            ],
        }

    elif state.target_profile_category[0] == "investment_emotions":
        ai_message: str = f"""
        투자에 대해서 어떻게 생각하는지 알아볼까요? {state.user_name}님의 투자 성향을 같이 알아 보겠습니다.
        """

        qa_sets: dict[str, list[list[str]] | list[str]] = {
            "questions": [
                "투자에 대한 핵심 감정 - '투자'와 관련하여 다음 중 현재 자신의 마음 상태를 가장 잘 설명하는 것은 무엇인가요?",
                "위험 상황에서의 감정적 반응 - 내가 보유한 투자 상품의 가치가 일주일 만에 15% 하락했다는 알림을 받았습니다. 이때 가장 먼저 드는 감정은 무엇인가요?",
                "투자 정보 탐색의 동기 - 투자에 대한 정보를 찾아보거나 관련 뉴스를 접할 때, 주로 어떤 생각이나 동기로 움직이나요?",
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
        }
    elif state.target_profile_category[0] == "interests_categories":
        ai_message: str = f"""
        관심이 있는 투자 분야는 무엇인지 알아볼까요? {state.user_name}님의 관심 분야를 같이 알아 보겠습니다.
        """

        qa_sets: dict[str, list[list[str]] | list[str]] = {
            "questions": [
                "미래 성장을 주도할 기술 분야 중 가장 관심 있는 분야는 무엇입니까?",
                "어떠한 산업의 사회적, 경제적 변화에 가장 큰 기회가 있다고 생각하십니까?",
                "실생활과 밀접하게 관련된 다음 분야 중, 투자 매력도가 가장 높다고 생각하는 분야는 어디입니까?",
            ],
            "options": [
                [
                    "인공지능(AI) & 반도체: 4차 산업혁명의 핵심으로, 모든 산업에 적용될 수 있는 잠재력을 가진 기술 분야",
                    "전기차 & 자율주행: 친환경 정책과 기술 발전에 따라 빠르게 성장하고 있는 차세대 모빌리티 분야",
                    "친환경 에너지 & 탄소중립: 기후 변화 대응을 위한 전 세계적인 노력으로 중요성이 커지고 있는 분야",
                    "우주항공 & 방위산업: 새로운 탐사 영역 개척과 지정학적 중요성 증대로 주목받는 분야",
                ],
                [
                    "바이오 & 헬스케어: 고령화 사회 진입과 신약 개발 기술의 발전으로 지속적인 성장이 기대되는 분야",
                    "금융 & 핀테크: 기술 발전에 따른 금융 서비스의 혁신과 변화를 주도하는 분야",
                    "콘텐츠 & 엔터테인먼트: 한류 열풍과 같이 글로벌 시장으로 확장하며 높은 부가가치를 창출하는 분야",
                    "사이버보안 & 데이터: 디지털 전환이 가속화되면서 모든 산업에서 필수적인 요소로 자리 잡은 분야",
                ],
                [
                    "차세대 운송수단: 전기차, 배터리 기술 등 우리의 이동 방식을 근본적으로 바꿀 분야",
                    "인공지능 기반 서비스: 빅데이터를 활용하여 개인화된 서비스를 제공하고 산업 효율성을 높이는 분야",
                    "K-컬처 및 미디어: 전 세계적으로 영향력을 확대하고 있는 한국의 문화 콘텐츠 관련 분야",
                    "첨단 의료 기술: 혁신적인 신약이나 의료기기를 통해 인류의 수명 연장과 삶의 질 개선에 기여하는 분야",
                ],
            ],
        }

    elif state.target_profile_category[0] == "investment_level":
        ai_message: str = f"""
        투자 수준을 알아볼까요? {state.user_name}님의 투자 수준을 같이 알아 보겠습니다.
        """

        qa_sets: dict[str, list[list[str]] | list[str]] = {
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
        }

    elif state.target_profile_category[0] == "knowledge_level":
        ai_message: str = f"""
        투자 지식 수준을 알아볼까요? {state.user_name}님의 투자 지식 수준을 같이 알아 보겠습니다.
        """

        qa_sets: dict[str, list[list[str]] | list[str]] = {
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
        }

    raw_questions: list[list[str]] | list[str] = qa_sets.get("questions", [])
    raw_options: list[list[str]] | list[str] = qa_sets.get("options", [])

    questions: list[str] = (
        [str(q) for q in raw_questions] if isinstance(raw_questions, list) else []
    )

    options: list[list[str]] = []
    if isinstance(raw_options, list):
        for opt in raw_options:
            if isinstance(opt, list):
                options.append([str(o) for o in opt])
            else:
                options.append([str(opt)])

    target_profile_category: Literal[
        "investment_goal",
        "investment_emotions",
        "interests_categories",
        "investment_level",
        "knowledge_level",
    ] = state.target_profile_category[0]

    return {
        "workflow_stage": "generate_qa",
        "ai_messages": [AIMessage(content=ai_message)],
        "quiz_content_by_category": {
            target_profile_category: {
                "questions": questions,
                "options": options,
            }
        },
    }


def generate_follow_up_questions(state: OverallState) -> dict:
    qa_pairs = state.answers_by_category.get(state.target_profile_category[0], [])

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

    llm = get_llm_agents(GEMINI_MODEL_NAME)
    structured_llm = llm.with_structured_output(FollowUpQuestionsSchema)

    chain = prompt_template | structured_llm

    raw_result = chain.invoke(
        {
            "target_profile_category": state.target_profile_category[0],
            "qa_pairs": qa_pairs,
        }
    )

    try:
        Schema: FollowUpQuestionsSchema = FollowUpQuestionsSchema.model_validate(
            raw_result
        )
    except ValidationError as e:
        raise ValueError(f"Unexpected result type from chain.invoke: {e}")

    ProfileCategory = Literal[
        "investment_goal",
        "investment_emotions",
        "interests_categories",
        "investment_level",
        "knowledge_level",
    ]

    target_profile_category: ProfileCategory = state.target_profile_category[0]

    current_quiz_content = state.quiz_content_by_category.get(
        target_profile_category, {}
    )
    current_questions = current_quiz_content.get("questions", [])
    current_options = current_quiz_content.get("options", [])

    return {
        "ai_messages": [],
        "workflow_stage": "finished_qa",
        "quiz_content_by_category": {
            **state.quiz_content_by_category,
            target_profile_category: {
                "questions": add(
                    current_questions,
                    Schema.questions,
                ),
                "options": add(
                    current_options,
                    Schema.options,
                ),
            },
        },
    }
