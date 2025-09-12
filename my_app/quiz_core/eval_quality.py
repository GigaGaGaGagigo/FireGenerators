from __future__ import annotations

import os
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

from openai import OpenAI  # sync client


# =========================
#  Pricing & Cost Estimate
# =========================
def default_pricing():
    return {
        "gpt-4.1":     {"input_per_1k": 0.01,   "output_per_1k": 0.03},   # ← 추가
        "gpt-4o-mini": {"input_per_1k": 0.0006, "output_per_1k": 0.002},
        "gpt-5":       {"input_per_1k": 0.03,   "output_per_1k": 0.09},
    }


def estimate_monthly_cost(
    usages: Dict[str, Dict[str, int]],
    *,
    pricing: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    pricing = pricing or default_pricing()
    total = 0.0
    breakdown = {}
    for model, u in usages.items():
        inp = max(0, int(u.get("input_tokens", 0)))
        out = max(0, int(u.get("output_tokens", 0)))
        p = pricing.get(model, {"input_per_1k": 0.0, "output_per_1k": 0.0})
        cost = (inp / 1000.0) * p["input_per_1k"] + (out / 1000.0) * p["output_per_1k"]
        breakdown[model] = round(cost, 4)
        total += cost
    return {"total_usd": round(total, 2), "by_model": breakdown}


# =========================
#  Judge Schema & Parser
# =========================
@dataclass
class JudgeScore:
    clarity: int
    correctness: int
    difficulty_fit: int
    ambiguity: int
    justification: int
    overall: int
    comments: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["overall"] = int(self.overall)
        return d


def _parse_judge_json(text: str) -> JudgeScore:
    s = text.strip()
    if "```" in s:
        for chunk in s.split("```"):
            if "{" in chunk:
                s = chunk
                break
    i = s.find("{")
    if i >= 0:
        s = s[i:]
    try:
        data = json.loads(s)
    except Exception:
        data = {}

    def iz(v):
        try:
            return max(0, min(5, int(v)))
        except Exception:
            return 0

    if not data:
        return JudgeScore(0, 0, 0, 0, 0, 0, "empty_response")

    return JudgeScore(
        clarity=iz(data.get("clarity")),
        correctness=iz(data.get("correctness")),
        difficulty_fit=iz(data.get("difficulty_fit") or data.get("difficulty")),
        ambiguity=iz(data.get("ambiguity")),
        justification=iz(data.get("justification")),
        overall=iz(data.get("overall")),
        comments=str(data.get("comments") or "no_comment")[:300],
    )


# =========================
#  Safe Caller
# =========================
def _chat_create_fast_json(client: OpenAI, *, model: str, messages: List[Dict[str, str]]):
    kwargs = {"model": model, "messages": messages, "response_format": {"type": "json_object"}}
    try:
        return client.chat.completions.create(**kwargs)
    except Exception:
        kwargs.pop("response_format", None)
        return client.chat.completions.create(**kwargs)



def _build_judge_prompt_fast(question: Dict[str, Any]) -> str:
    qtext = str(question.get("question_text", ""))
    opts = question.get("options", [])
    ans = str(question.get("answer", ""))
    qtype = str(question.get("question_type", "mcq"))
    weight = question.get("weight", 1)

    return f"""
너는 금융 문제 품질 판사다. 
반드시 아래 JSON 스키마를 그대로 채워서 출력해야 한다. 
모든 항목은 0~5 정수, comments는 한국어로 간단히 한 줄 이상 설명을 반드시 작성한다. 
추가 텍스트, 설명, 서론 금지. **JSON만 출력**.

문항:
- 유형: {qtype}
- 가중치: {weight}
- 질문: {qtext}
- 보기: {opts}
- 정답: {ans}

평가기준 (0~5 정수):
- clarity, correctness, difficulty_fit, ambiguity, justification, overall

JSON 스키마:
{{
  "clarity": 0,
  "correctness": 0,
  "difficulty_fit": 0,
  "ambiguity": 0,
  "justification": 0,
  "overall": 0,
  "comments": ""
}}
""".strip()

def _judge_one(client: OpenAI, q: Dict[str, Any], *, judge_model: str) -> Dict[str, Any]:
    prompt = _build_judge_prompt_fast(q)
    messages = [
        {"role": "system", "content": "You are a strict grader. JSON only."},
        {"role": "user", "content": prompt},
    ]

    q_out = dict(q)
    try:
        # 토큰 제한 파라미터 없이 호출
        resp = _chat_create_fast_json(client, model=judge_model, messages=messages)
        text = (resp.choices[0].message.content or "").strip()
        js = _parse_judge_json(text)
        q_out["judge"] = js.to_dict()

        usage = getattr(resp, "usage", None)
        if usage:
            q_out["_usage"] = {
                "model": judge_model,
                "input_tokens": usage.prompt_tokens,
                "output_tokens": usage.completion_tokens,
            }
    except Exception as e:
        q_out["judge"] = JudgeScore(0, 0, 0, 0, 0, 0, f"judge_error: {e}").to_dict()
    return q_out

def judge_questions_batch(
    questions: List[Dict[str, Any]],
    *,
    judge_model: str = "gpt-5",
    openai_client: Optional[OpenAI] = None,
) -> List[Dict[str, Any]]:
    client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    out: List[Dict[str, Any]] = []
    for q in questions:
        out.append(_judge_one(client, q, judge_model=judge_model))  # ← max_tokens 제거
    return out


# =========================
#   Session-style Runner
# =========================
class QuizEvalSession:
    def __init__(self, *, judge_model: str = "gpt-5"):
        self.judge_model = judge_model
        self._questions: List[Dict[str, Any]] = []
        self._usage_tokens: Dict[str, Dict[str, int]] = {}

    def add(self, question_payload: Dict[str, Any]) -> None:
        self._questions.append(dict(question_payload))

    def add_usage(self, *, model: str, input_tokens: int, output_tokens: int) -> None:
        u = self._usage_tokens.setdefault(model, {"input_tokens": 0, "output_tokens": 0})
        u["input_tokens"] += max(0, int(input_tokens))
        u["output_tokens"] += max(0, int(output_tokens))

    def finalize(self) -> Dict[str, Any]:
        judged = judge_questions_batch(self._questions, judge_model=self.judge_model)

        # usage 합산
        for q in judged:
            if "_usage" in q:
                u = q["_usage"]
                self.add_usage(model=u["model"], input_tokens=u["input_tokens"], output_tokens=u["output_tokens"])

        cost_est = estimate_monthly_cost(self._usage_tokens) if self._usage_tokens else {"total_usd": 0.0, "by_model": {}}
        return {
            "judged_questions": judged,
            "cost_estimate": cost_est,
            "num_questions": len(self._questions),
        }


# =============== #
#   Local Test    #
# =============== #
if __name__ == "__main__":
    session = QuizEvalSession(judge_model="gpt-5")
    session.add({
        "question_id": "q_001",
        "question_text": "복리는 원금과 이자에 다시 이자가 붙는 것을 말한다. (O/X)",
        "options": [],
        "answer": "O",
        "user_answer": "O",
        "is_correct": 1,
        "question_type": "ox",
        "weight": 1,
        "category": "기초",
        "served_level": "초",
        "user_proficiency_before": 1,
        "response_time_ms": 4300,
        "model_gen_time_ms": 900,
        "explanation_text": "복리는 이자에 이자가 붙는 구조를 의미합니다."
    })

    result = session.finalize()
    print(json.dumps(result, ensure_ascii=False, indent=2))
