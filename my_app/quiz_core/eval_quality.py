# my_app/quiz_core/eval_quality.py
from __future__ import annotations

import os
import json
import random
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

from openai import OpenAI  # sync client


# =========================
#  Pricing & Cost Estimate
# =========================
def default_pricing() -> Dict[str, Dict[str, float]]:
    """
    1K 토큰당 가격(USD). 실제 운영 시 최신 가격으로 갱신하세요.
    """
    return {
        "gpt-4":       {"input_per_1k": 0.01,  "output_per_1k": 0.03},
        "gpt-4o-mini": {"input_per_1k": 0.0006, "output_per_1k": 0.002},
        "gpt-5":       {"input_per_1k": 0.03,  "output_per_1k": 0.09},  # 판사 전용
    }


def estimate_monthly_cost(
    usages: Dict[str, Dict[str, int]],
    *,
    pricing: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """
    usages 예:
    {
      "gpt-4":       {"input_tokens": 2_000_000, "output_tokens": 500_000},
      "gpt-4o-mini": {"input_tokens": 1_000_000, "output_tokens": 300_000},
      "gpt-5":       {"input_tokens": 200_000,   "output_tokens": 80_000}
    }
    """
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
    # 0~5 점수
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

    return JudgeScore(
        clarity=iz(data.get("clarity")),
        correctness=iz(data.get("correctness")),
        difficulty_fit=iz(data.get("difficulty_fit") or data.get("difficulty")),
        ambiguity=iz(data.get("ambiguity")),
        justification=iz(data.get("justification")),
        overall=iz(data.get("overall")),
        comments=str(data.get("comments") or "")[:300],
    )


# =========================
#  Fast GPT-5 Judge Caller
# =========================
def _chat_create_fast_json(client: OpenAI, *, model: str, messages: List[Dict[str, str]], max_tokens: int = 200):
    """
    gpt-5 판사용 빠른 호출:
    - temperature/penalties 미전달 (모델 디폴트 사용)
    - response_format=json_object (가능한 경우) -> 파싱 비용↓
    - 안되면 response_format 제거하여 1회 폴백
    """
    try:
        return client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},  # JSON-only
            max_tokens=max_tokens,
        )
    except Exception:
        # 일부 모델/환경에서 response_format 미지원일 수 있음 → 폴백
        return client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )


def _build_judge_prompt_fast(question: Dict[str, Any]) -> str:
    """
    리즈닝 금지/간단 스키마 전용, 초경량 판사 프롬프트.
    """
    qtext = question.get("question_text", "")
    opts = question.get("options", [])
    ans = question.get("answer", "")
    qtype = question.get("question_type", "mcq")
    weight = question.get("weight", 1)

    return f"""
너는 금융 문제 품질 판사다. 설명/사고과정/사설 금지. **JSON만** 출력해.
문항:
- 유형: {qtype}
- 가중치: {weight}
- 질문: {qtext}
- 보기: {opts}
- 정답: {ans}

평가기준(0~5 정수):
- clarity, correctness, difficulty_fit, ambiguity, justification, overall

JSON 스키마(그대로):
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


def judge_questions_batch(
    questions: List[Dict[str, Any]],
    *,
    judge_model: str = "gpt-5",           # 기본 gpt-5
    examples_to_show: int = 0,            # 빠른 평가 목적: 0 (인자만 유지)
    openai_client: Optional[OpenAI] = None,
    temperature: Optional[float] = None,  # 사용하지 않음(호환용)
    max_per_call: int = 10,
    max_tokens_per_call: int = 180,
) -> List[Dict[str, Any]]:
    """
    gpt-5 빠른 판사: 한 문제씩 짧게 채점(동기).
    - JSON-only, no temperature, no reasoning
    """
    client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not isinstance(questions, list) or not questions:
        return []

    out: List[Dict[str, Any]] = []
    batch: List[Dict[str, Any]] = []

    def _flush_batch(batch_items: List[Dict[str, Any]]):
        for q in batch_items:
            prompt = _build_judge_prompt_fast(q)
            try:
                resp = _chat_create_fast_json(
                    client,
                    model=judge_model,
                    messages=[
                        {"role": "system", "content": "You are a strict grader. Do not explain. Output JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens_per_call,
                )
                text = (resp.choices[0].message.content or "").strip()
                js = _parse_judge_json(text)
            except Exception as e:
                js = JudgeScore(0, 0, 0, 0, 0, 0, f"judge_error: {type(e).__name__}: {e}")

            q_with_score = dict(q)
            q_with_score["judge"] = js.to_dict()
            out.append(q_with_score)

    for q in questions:
        batch.append(q)
        if len(batch) >= max_per_call:
            _flush_batch(batch)
            batch = []
    if batch:
        _flush_batch(batch)

    return out


# =============== #
#   Local Test    #
# =============== #
if __name__ == "__main__":
    # 간단 자체 테스트 (환경변수 OPENAI_API_KEY 필요)
    sample_questions = [{
        "question_text": "복리는 원금과 이자에 다시 이자가 붙는 것을 말한다. (O/X)",
        "options": [],
        "answer": "O",
        "question_type": "ox",
        "weight": 1
    }]
    scored = judge_questions_batch(sample_questions, judge_model="gpt-5", max_tokens_per_call=150)
    print(json.dumps(scored, ensure_ascii=False, indent=2))
