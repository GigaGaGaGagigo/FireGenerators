# ---- 프롬프트 ----
SYSTEM_PROMPT_QGEN = (
    "너는 한국어 금융 교육 전문가다. OX 또는 4지선다 문제 중 1문항을 생성한다. "
    "4지선다는 반드시 정답이 1개만 있어야 함"
    "JSON만 출력. 필요한 필드: "
    "question_type('ox'|'mcq'), question_text(str), options(4개 배열; mcq일 때만), "
    "answer(mcq '1'~'4' | ox 'O'|'X'), explanation(두 문장 이내), level('easy'|'medium'), "
    "weight(easy=1, medium=2)"
)
USER_PROMPT_QGEN_TMPL = (
    "사용자 역량(0~10): {proficiency}/10\n"
    "누적 점수: {score}/{max_score}\n"
    "틀렸던 문제(최대 3개): {wrong_summary}\n"
    "이전 문항(요약): {history_summary}\n"
    "관심사 키워드: {keywords_str}\n\n"
    "위 정보를 반영해 1문항만 생성. JSON만."
)

SYSTEM_PROMPT_EVAL = (
    "너는 한국어 금융 퀴즈 채점 전문가다. 반드시 JSON만 출력한다.\n"
    "정답입니다.오답입니다 이런거 하지마"
    "- is_correct(bool): 정오 판정\n"
    "- feedback(str): 2~3문장. 왜 맞았/틀렸는지 핵심 개념을 구체적으로 설명하고,\n"
    "  틀렸다면 정답 도출 팁 1가지를 제시한다.\n"
    "- delta(int -2~+2): 숙련도 변화량(정답=+1~+2, 오답=-1~-2)"
)
USER_PROMPT_EVAL_TMPL = (
    "문항: {question_text}\n"
    "선택지: {options}\n"
    "정답: {answer}\n"
    "사용자 답변: {user_answer}\n"
    "난이도: {level}\n"
    "proficiency: {proficiency}\n"
    "JSON만."
)

SYSTEM_PROMPT_SUMMARY = (
    "너는 한국어 금융 교육 코치다. 퀴즈 세션 기록을 분석해 "
    "1) 최종 숙련 레벨 라벨(초급/중급/상급)과 "
    "2) 금융지식 수준을 설명하는 3문장 요약 "
    "을 JSON으로만 출력한다. "
    "규칙: JSON 키: level(초급|중급|상급), summary_sentences(문자열 3개 배열), evidence. "
    "summary_sentences: 각 1문장, 총 3문장. '정답/오답' 문구 금지. 구체적 개념/주제 언급."
)
USER_PROMPT_SUMMARY_TMPL = (
    "최종 레벨(영문): {level_eng}\n총 가중치: {total_weight}\n사용자 관심사: {keywords}\n\n"
    "문항 기록(최대 {max_items}개):\n{history_json}\n\n"
    "토픽 키워드:\n{topic_json}\n\n"
    "요구:\n- 위 기록을 바탕으로 강점/약점을 주제 단어로 구체화.\n"
    "- '초급/중급/상급' 중 하나로 level을 한국어로 표기.\n"
    "- summary_sentences는 정확히 3문장.\n- JSON만 출력."
)

# ---- JSON Schema (response_format용) ----
QGEN_SCHEMA = {
    "type": "object",
    "properties": {
        "question_type": {"type": "string", "enum": ["ox", "mcq"]},
        "question_text": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "answer": {"type": "string"},
        "explanation": {"type": "string"},
        "level": {"type": "string", "enum": ["easy", "medium"]},
        "weight": {"type": "integer", "enum": [1, 2]}
    },
    "required": ["question_type", "question_text", "answer", "level", "weight"],
    "additionalProperties": False
}
EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "is_correct": {"type": "boolean"},
        "feedback": {"type": "string", "minLength": 10},
        "delta": {"type": "integer", "minimum": -2, "maximum": 2}
    },
    "required": ["is_correct", "feedback", "delta"],
    "additionalProperties": False
}
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "level": {"type": "string", "enum": ["초급", "중급", "상급"]},
        "summary_sentences": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
        "evidence": {"type": "object"}
    },
    "required": ["level", "summary_sentences"],
    "additionalProperties": False
}
