# my_app/quiz_core/offline_eval.py
from __future__ import annotations

import os
import json
import csv
import datetime
from typing import List, Dict, Any, Optional

from my_app.quiz_core.eval_quality import (
    judge_questions_batch,
    estimate_monthly_cost,
    default_pricing,
)


def _now_tag() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def export_recent_questions_judgement(
    questions: List[Dict[str, Any]],
    *,
    outdir: str = "my_app/quiz_core/exports/judge",
    n: int = 10,
    judge_model: str = "gpt-5",
    examples_to_show: int = 0,   # 빠른 평가 목적: 0 권장
    max_per_call: int = 10,
    max_tokens_per_call: int = 180,
) -> Dict[str, str]:
    """
    최근 n개 문항을 LLM-as-a-judge로 평가하고, 화면에 표시하지 않고 파일로 저장.

    결과물 (outdir 아래 생성):
    - judged_<timestamp>.jsonl : 원문항 + judge 점수/코멘트 (라인별 JSON)
    - judged_<timestamp>.csv   : 주요 열만 CSV
    - judged_summary_<timestamp>.json : 평균/개수 등 요약
    """
    outdir = _ensure_dir(outdir)
    ts = _now_tag()

    if not isinstance(questions, list):
        questions = []
    batch = [q for q in questions[-n:] if isinstance(q, dict) and q.get("question_text") and q.get("answer")]

    judged = judge_questions_batch(
        questions=batch,
        judge_model=judge_model,
        examples_to_show=examples_to_show,
        max_per_call=max_per_call,
        max_tokens_per_call=max_tokens_per_call,
    )

    # 파일 경로들
    fp_jsonl = os.path.join(outdir, f"judged_{ts}.jsonl")
    fp_csv   = os.path.join(outdir, f"judged_{ts}.csv")
    fp_sum   = os.path.join(outdir, f"judged_summary_{ts}.json")

    # 1) JSONL 저장
    with open(fp_jsonl, "w", encoding="utf-8") as f:
        for item in judged:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # 2) CSV 저장
    cols = [
        "question_text", "answer",
        "clarity", "correctness", "difficulty_fit",
        "ambiguity", "justification", "overall", "comments"
    ]
    with open(fp_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for q in judged:
            j = q.get("judge") or {}
            writer.writerow([
                (q.get("question_text") or "").replace("\n", " ")[:200],
                q.get("answer") or "",
                j.get("clarity", 0),
                j.get("correctness", 0),
                j.get("difficulty_fit", j.get("difficulty_fit", 0)),
                j.get("ambiguity", 0),
                j.get("justification", 0),
                j.get("overall", 0),
                (j.get("comments") or "").replace("\n", " ")[:300],
            ])

    # 3) 요약 통계 저장
    def _to_num(x, default=0.0):
        try:
            return float(x)
        except Exception:
            return default

    if judged:
        overalls = [_to_num((q.get("judge") or {}).get("overall", 0)) for q in judged]
        ambigu   = [_to_num((q.get("judge") or {}).get("ambiguity", 0)) for q in judged]
        avg_overall = round(sum(overalls) / len(overalls), 3) if overalls else 0.0
        bad_cnt     = sum(1 for o in overalls if o < 3)
        ambi_cnt    = sum(1 for a in ambigu if a >= 3)
    else:
        avg_overall, bad_cnt, ambi_cnt = 0.0, 0, 0

    summary = {
        "timestamp": ts,
        "count": len(judged),
        "avg_overall": avg_overall,
        "need_improve_count": bad_cnt,   # overall < 3
        "ambiguous_count": ambi_cnt,     # ambiguity ≥ 3
        "files": {
            "jsonl": fp_jsonl,
            "csv": fp_csv,
        }
    }
    with open(fp_sum, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return {"jsonl": fp_jsonl, "csv": fp_csv, "summary": fp_sum}


def export_monthly_cost(
    *,
    outdir: str = "my_app/quiz_core/exports/eval",
    usages: Optional[Dict[str, Dict[str, int]]] = None,
    pricing: Optional[Dict[str, Dict[str, float]]] = None,
) -> str:
    """
    월별 API 비용 추산을 파일로 저장.
    - usages: {"model": {"input_tokens": int, "output_tokens": int}, ...}
    - pricing: default_pricing() 기반으로 운영 단가 반영 가능
    결과물:
    - cost_<timestamp>.json
    """
    outdir = _ensure_dir(outdir)
    ts = _now_tag()

    if usages is None:
        usages = {
            "gpt-4":       {"input_tokens": 2_000_000, "output_tokens": 500_000},
            "gpt-4o-mini": {"input_tokens": 1_000_000, "output_tokens": 300_000},
            "gpt-5":       {"input_tokens":   200_000, "output_tokens":  80_000},
        }
    result = estimate_monthly_cost(usages, pricing=(pricing or default_pricing()))

    fp = os.path.join(outdir, f"cost_{ts}.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(
            {"timestamp": ts, "usages": usages, "pricing": (pricing or default_pricing()), "result": result},
            f, ensure_ascii=False, indent=2
        )
    return fp


# =============== #
#   Local Test    #
# =============== #
if __name__ == "__main__":
    # 샘플 저장 경로는 요구한 경로에 맞춤
    dummy_questions = [
        {"question_text": "예금자보호제도는 1인당 1기관 기준으로 1억원까지 보호한다. (O/X)", "answer": "O", "options": [], "question_type": "ox", "weight": 1},
        {"question_text": "복리는 원금과 이자에 다시 이자가 붙는다. (O/X)", "answer": "O", "options": [], "question_type": "ox", "weight": 1},
    ]

    paths = export_recent_questions_judgement(
        questions=dummy_questions,
        outdir="my_app/quiz_core/exports/judge",
        n=2,
        judge_model="gpt-5",
        examples_to_show=0,
    )
    print(paths)

    cost_path = export_monthly_cost(outdir="my_app/quiz_core/exports/eval")
    print(cost_path)
