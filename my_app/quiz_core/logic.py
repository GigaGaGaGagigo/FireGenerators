import os, json, re, time, uuid
import streamlit as st

from my_app.quiz_core.services import chat_json, supabase, MODEL_QGEN,MODEL_EVAL,MODEL_SUMMARY
from my_app.quiz_core.constants import TOPIC_KEYWORDS, GENERATED_DIR
from my_app.quiz_core.constants import TOTAL_QUESTIONS, COMMON_COUNT,MAX_CONTEXT_TURNS,ROLLING_SUMMARY_MAX_CHARS 
from my_app.quiz_core.utils import _coerce_mc_options, _get_user_id, _get_user_field, json_cache_key
from my_app.quiz_core.prompts import (
    SYSTEM_PROMPT_QGEN, USER_PROMPT_QGEN_TMPL, QGEN_SCHEMA,
    SYSTEM_PROMPT_EVAL, USER_PROMPT_EVAL_TMPL, EVAL_SCHEMA,
    SYSTEM_PROMPT_SUMMARY, USER_PROMPT_SUMMARY_TMPL, SUMMARY_SCHEMA
)

# ---- 스코어링/집계 ----
def classify_level(score, max_score):
    rate = 0 if max_score == 0 else score / max_score
    if rate <= 0.2: return "Beginner"
    if rate <= 0.6: return "Intermediate"
    return "Advanced"

def _aggregate_session(history: list[dict], total_weight: int, user_keywords: list[str]):
    agg = {"total": len(history), "correct_cnt": 0, "weighted_score": 0.0,
           "overall_accuracy": 0.0, "topic_stats": {}, "hint_rate": 0.0, "avg_time_sec": None}
    if not history: return agg
    for t in TOPIC_KEYWORDS.keys():
        agg["topic_stats"][t] = {"total": 0, "correct": 0}
    w_correct = 0
    for h in history:
        is_ok = bool(h.get("correct"))
        w = int(h.get("weight", 1))
        qtext = str(h.get("question_text", ""))

        if is_ok:
            agg["correct_cnt"] += 1
            w_correct += w

        matched_once = False
        for topic, pats in TOPIC_KEYWORDS.items():
            if any(re.search(p, qtext, flags=re.I) for p in pats):
                agg["topic_stats"][topic]["total"] += 1
                if is_ok:
                    agg["topic_stats"][topic]["correct"] += 1
                matched_once = True
        if not matched_once and user_keywords:
            t = "관심사"
            agg["topic_stats"].setdefault(t, {"total": 0, "correct": 0})
            agg["topic_stats"][t]["total"] += 1
            if is_ok:
                agg["topic_stats"][t]["correct"] += 1

    agg["overall_accuracy"] = round(agg["correct_cnt"] / max(1, agg["total"]), 4)
    agg["weighted_score"] = round(w_correct / max(1, total_weight), 4)
    return agg

def _rank_topics(topic_stats: dict):
    rows = []
    for t, s in topic_stats.items():
        tot, cor = s["total"], s["correct"]
        acc = (cor / tot) if tot else 0.0
        rows.append((t, tot, cor, acc))
    strong = sorted([r for r in rows if r[1] >= 1], key=lambda x: (x[3], x[1]), reverse=True)
    weak   = sorted([r for r in rows if r[1] >= 1], key=lambda x: (x[3], -x[1]))
    return strong[:3], weak[:3]

def _build_summary_from_agg(agg: dict, level_kor: str, user_keywords: list[str]):
    strong, weak = _rank_topics(agg["topic_stats"])
    strong_names = [s[0] for s in strong][:2] or ["기초개념"]
    weak_names   = [w[0] for w in weak][:2]   or ["연결개념"]
    s1 = f"{'·'.join(strong_names)} 영역에서 안정적이며 전체 정답률 {int(agg['overall_accuracy']*100)}%를 기록했습니다."
    s2 = f"{'·'.join(weak_names)}에서 오답이 상대적으로 많아 개념 연결/적용 보완이 필요합니다."
    kw = (user_keywords or ["관심 분야"])[0]
    s3 = f"다음 세션은 {', '.join(weak_names)} 중심으로 {kw} 관련 중난도 문제 10문항을 풀고 핵심 개념을 정리해 보세요."
    strong_topics = [{"topic": n, "accuracy": round(c/t,2) if t else 0.0, "n": t} for n,t,c,_ in strong]
    weak_topics   = [{"topic": n, "accuracy": round(c/t,2) if t else 0.0, "n": t} for n,t,c,_ in weak]
    evidence = {
        "overall_accuracy": agg["overall_accuracy"],
        "weighted_score": agg["weighted_score"],
        "avg_time_sec": agg["avg_time_sec"],
        "hint_rate": agg["hint_rate"],
        "strong_topics": strong_topics,
        "weak_topics": weak_topics
    }
    return {
        "level": level_kor,
        "summary_sentences": [s1, s2, s3],
        "evidence": evidence,
    }

# ---- 파일 저장 ----
def save_generated_question(q: list[dict], meta: dict):
    ts = time.strftime("%Y%m%d-%H%M%S")
    fname = os.path.join(GENERATED_DIR, f"quiz_{ts}.json")
    payload = {"meta": meta, "questions": q}
    try:
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 저장 실패: {e}")

# ---- LLM 로직 (교체본) ----
def generate_next_question(proficiency: int, score: int, max_score: int, wrong_notes: list, history: list, keywords: list):
    # 1) 최근 N문항만 간략화해서 포함 (슬라이딩 윈도우)
    tail = history[-MAX_CONTEXT_TURNS:]
    short_hist = [{
        "q": h.get("question_text", "")[:120] + ("..." if len(h.get("question_text","")) > 120 else ""),
        "ua": h.get("user_answer", ""),
        "ans": h.get("answer", ""),
        "ok": bool(h.get("correct")),
        "w": int(h.get("weight", 1)),
    } for h in tail]
    history_summary = json.dumps(short_hist, ensure_ascii=False)

    # 2) 롤링 요약(≤300자)을 세션에서 가져와 함께 넘김
    rolling = (st.session_state.get("rolling_summary") or "").strip()
    if len(rolling) > ROLLING_SUMMARY_MAX_CHARS:
        rolling = rolling[:ROLLING_SUMMARY_MAX_CHARS]

    # 3) 기타 보조 컨텍스트
    wrong_summary = " / ".join(wrong_notes[-3:]) if wrong_notes else "없음"
    keywords_str = ", ".join(keywords) if keywords else "기초, 저위험, ETF, 예금, 채권"

    # 4) 프롬프트 구성: “최근 N개 + 롤링요약”만 넘김 (풀 히스토리 금지)
    user_prompt = USER_PROMPT_QGEN_TMPL.format(
        proficiency=proficiency, score=score, max_score=max_score or 1,
        wrong_summary=wrong_summary, history_summary=history_summary, keywords_str=keywords_str
    )

    data = chat_json(SYSTEM_PROMPT_QGEN, user_prompt, QGEN_SCHEMA, model=MODEL_QGEN)

    if not data:
        raise RuntimeError("문항 생성 실패: LLM 응답 없음")

    q_type = (data.get("question_type") or "mcq").lower()
    q = {
        "question_type": q_type,
        "question_text": str(data.get("question_text", "")).strip(),
        "options": _coerce_mc_options(data.get("options", [])) if q_type == "mcq" else [],
        "answer": str(data.get("answer", "")).strip(),
        "explanation": str(data.get("explanation", "")).strip(),
        "level": (str(data.get("level", "easy")).lower()),
        "weight": int(data.get("weight", 1))
    }
    if q["level"] not in ("easy", "medium"):
        q["level"] = "easy"
    if q["weight"] not in (1, 2):
        q["weight"] = 1 if q["level"] == "easy" else 2

    if q_type == "mcq":
        if not q["question_text"] or len(q["options"]) != 4 or q["answer"] not in {"1","2","3","4"}:
            raise ValueError("생성된 문항 형식이 유효하지 않음 (mcq)")
    else:
        if not q["question_text"] or q["answer"].upper() not in {"O","X"}:
            raise ValueError("생성된 문항 형식이 유효하지 않음 (ox)")
    return q

def evaluate_answer(question_text: str, options, answer: str, user_answer: str, level:str, proficiency: int):
    user_prompt = USER_PROMPT_EVAL_TMPL.format(
        question_text=question_text, options=options if options else [], answer=answer,
        user_answer=user_answer, level=(level or "easy"), proficiency=proficiency
    )
    data = chat_json(SYSTEM_PROMPT_EVAL, user_prompt, EVAL_SCHEMA, model=MODEL_EVAL)
    if not data:
        raise ValueError("채점 LLM 결과 JSON 파싱 실패")

    return {
        "is_correct": bool(data.get("is_correct")),
        "feedback": str(data.get("feedback", "")).strip(),
        "delta": int(data.get("delta", 0)),
    }

def generate_level_summary_llm(level_eng: str, history: list[dict], total_weight: int, user_keywords: list[str]):
    MAX_ITEMS = min(len(history), 40)
    compact = []
    for h in history[-MAX_ITEMS:]:
        compact.append({
            "q": str(h.get("question_text", ""))[:140],
            "ok": bool(h.get("correct")),
            "w": int(h.get("weight", 1)),
            "ua": str(h.get("user_answer", "")),
            "ans": str(h.get("answer", "")),
        })
    topic_json = {k: v for k, v in TOPIC_KEYWORDS.items()}

    user_prompt = USER_PROMPT_SUMMARY_TMPL.format(
        level_eng=level_eng,
        total_weight=total_weight,
        keywords=", ".join(user_keywords) if user_keywords else "없음",
        max_items=MAX_ITEMS,
        history_json=json.dumps(compact, ensure_ascii=False),
        topic_json=json.dumps(topic_json, ensure_ascii=False)
    )
    data = chat_json(SYSTEM_PROMPT_SUMMARY, user_prompt, SUMMARY_SCHEMA, model=MODEL_SUMMARY)
    if not data:
        return None
    level = str(data.get("level", "")).strip()
    if level not in ("초급", "중급", "상급"):
        level = {"Beginner": "초급", "Intermediate": "중급", "Advanced": "상급"}.get(level, "중급")
    summaries = data.get("summary_sentences", [])
    if not isinstance(summaries, list) or len(summaries) < 3:
        return None
    return {"level": level, "summary_sentences": summaries[:3],
            "evidence": data.get("evidence")}

# ---- 결과 저장 ----
def save_result(score, level, level_summary):
    """
    퀴즈 결과 + LLM 요약(level_summary)을 저장.
    - quiz_results: 상세 로그 보관 (summary_sentences, evidence → jsonb 컬럼)
    - profiles: knowledge_level, knowledge_summary 최신화 (knowledge_summary는 text 컬럼)
    """
    user = st.session_state.get("user")
    if not user or not supabase:
        return None

    # (1) 사용자 정보
    user_id = _get_user_id(user)
    try:
        res = supabase.table("profiles").select("name, role").eq("id", user_id).execute()
        if res.data:
            user_data = res.data[0]
            user_name = user_data.get("name") or "Anonymous"
            st.session_state.role = user_data.get("role", "User")
        else:
            user_name = "Anonymous"
            if not isinstance(st.session_state.role, str):
                st.session_state.role = _get_user_field(user, "role", "User")
    except Exception:
        user_name = "Anonymous"

    # (2) 요약 정리
    summary_sentences = (level_summary or {}).get("summary_sentences")
    evidence = (level_summary or {}).get("evidence")

    # text 컬럼에 맞게 변환
    def _summary_for_profiles(val):
        if val is None:
            return None
        if isinstance(val, list):
            return "\n".join(val)  # text 컬럼이므로 문자열로 변환
        return str(val)

    # (3) quiz_results 로그 적재 (jsonb 컬럼)
    try:
        supabase.table("quiz_results").insert({
            "user_id": user_id,
            "user_name": user_name,
            "score": score,
            "level": level,  # 그대로 저장 (beginner/intermediate/advanced)
            "summary_sentences": summary_sentences,
            "evidence": evidence
        }).execute()
    except Exception:
        pass

    # (4) profiles 업데이트 (없으면 upsert)
    update_payload = {
        "knowledge_level": level,
        "knowledge_summary": _summary_for_profiles(summary_sentences),
    }

    try:
        upd = supabase.table("profiles").update(update_payload).eq("id", user_id).execute()
        if not upd.data:  # 업데이트된 행이 없으면 upsert
            supabase.table("profiles").upsert({
                "id": user_id,
                **update_payload
            }).execute()
    except Exception:
        return {"user_name": user_name, "score": score, "level": level, "updated": False}

    return {"user_name": user_name, "score": score, "level": level, "updated": True}
