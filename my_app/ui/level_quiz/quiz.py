import os
import json
import uuid
import time
import random
import re
import streamlit as st
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, TooManyRequests
from dotenv import load_dotenv
from supabase import create_client
from ui.level_quiz.data.user_context import fetch_user_keywords
from ui.chatbot.chatbot_sample import generate_simple_response, stream_data

# ── ENV / Clients ─────────────────────────────────────────────────────────────
load_dotenv()

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.0-flash")

COMMON_PATH = "my_app/ui/level_quiz/data/common_questions.json"
GENERATED_DIR = "my_app/ui/level_quiz/data/generated"
os.makedirs(GENERATED_DIR, exist_ok=True)

TOTAL_QUESTIONS = 10
COMMON_COUNT = 3

# ── Topic 키워드(간단 매칭) ───────────────────────────────────────────────────
TOPIC_KEYWORDS = {
    "예금/금리": [r"예금", r"금리", r"복리", r"단리"],
    "채권": [r"채권", r"듀레이션", r"표면이자", r"만기수익률", r"세후.?수익률"],
    "ETF/인덱스": [r"ETF", r"인덱스", r"지수", r"추적오차"],
    "세금": [r"세금", r"과세", r"배당소득", r"양도소득"],
    "신용/부채": [r"신용", r"신용점수", r"대출", r"DSR", r"원리금"],
    "FIRE/자산배분": [r"FIRE", r"자산배분", r"리밸런싱", r"비상금"],
}

# ── Style ────────────────────────────────────────────────────────────────────
def inject_styles():
    st.markdown("""
    <style>
      .block-container { padding-top: 3.2rem; padding-bottom: 2rem; }
      .quiz-top-spacer { height: 12px; }
      .stMarkdown p { margin-bottom: 0.4rem; }
      .quiz-header {
        background: linear-gradient(135deg, rgba(99,102,241,.10), rgba(16,185,129,.10));
        border: 1px solid rgba(148,163,184,.22);
        border-radius: 16px; padding: 16px 18px; margin-bottom: 10px;
      }
      .badge { display:inline-flex; gap:6px; align-items:center; padding:4px 10px; border-radius:999px;
        background: rgba(148,163,184,.15); border:1px solid rgba(148,163,184,.35); font-size:.85rem; }
      .badge.mode { background: rgba(99,102,241,.12); border-color: rgba(99,102,241,.35); }
      .badge.score { background: rgba(16,185,129,.12); border-color: rgba(16,185,129,.35); }
      .question-card { border:1px solid rgba(148,163,184,.28); border-radius:16px; padding:18px; margin:10px 0 14px 0;
        background: rgba(2,6,23,.02); }
      .question-title { font-weight: 700; font-size: 1.05rem; }
      div[data-baseweb="radio"] > div { gap: 10px; }
      label[data-baseweb="radio"] {
        width: 100%; border:1px solid rgba(148,163,184,.3); border-radius:12px; padding:10px 12px; margin:4px 0;
        transition: all .15s ease; background: white;
      }
      label[data-baseweb="radio"]:hover { border-color: rgba(99,102,241,.6); box-shadow: 0 0 0 3px rgba(99,102,241,.12) inset; }
      .stButton > button { border-radius:12px !important; height:48px; font-size:18px; font-weight:700; }
      .tag { display:inline-block; padding:4px 10px; margin:2px 6px 6px 0; border-radius:999px; font-size:.85rem;
        background: rgba(148,163,184,.14); border:1px solid rgba(148,163,184,.3); }
    </style>
    """, unsafe_allow_html=True)

def render_result_card(score: int, total_weight: int, level: str, user_name: str | None = None):
    st.balloons()
    name = f" <span style='opacity:.7'>( {user_name} )</span>" if user_name else ""
    st.markdown(f"""
    <div style="border:1px solid rgba(148,163,184,.28); border-radius:16px; padding:18px; margin-top:8px;
                background:linear-gradient(135deg, rgba(99,102,241,.08), rgba(16,185,129,.08));">
      <div style="font-weight:800;font-size:1.1rem;margin-bottom:6px;">🎉 금융 퀴즈 완료{name}</div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin:8px 0 2px 0;">
        <span style="padding:6px 12px;border-radius:999px;border:1px solid rgba(148,163,184,.35);background:white;">
          🏆 점수 <b>{score}</b> / {total_weight}</span>
        <span style="padding:6px 12px;border-radius:999px;border:1px solid rgba(148,163,184,.35);background:white;">
          🧠 레벨 <b>{level}</b></span>
      </div>
      <div style="margin-top:12px;opacity:.85">이제 대시보드에서 다음 단계를 진행해보세요.</div>
    </div>
    """, unsafe_allow_html=True)

# ── State init ────────────────────────────────────────────────────────────────
def init_quiz_state():
    defaults = {
        "quiz_questions": [],
        "quiz_index": 0,
        "quiz_score": 0,
        "total_weight": 0,
        "proficiency": 5,
        "wrong_notes": [],
        "history": [],
        "generated_count": 0,
        "quiz_started": False,
        "quiz_completed": False,
        "user_keywords": [],
        "completion_announced": False,
        "role": "User",
        "messages": [],
        "eval_cache": {},
        "processing": False,
        "generated_saved": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if not isinstance(st.session_state.messages, list):
        st.session_state.messages = []

# ── Utils ─────────────────────────────────────────────────────────────────────
def _local_eval(question_text, options, answer, user_answer, proficiency):
    correct = user_answer.strip().lower() == answer.strip().lower()
    return {
        "is_correct": correct,
        "feedback": "핵심 개념을 잘 이해했어요." if correct else "괜찮아요. 해설을 보고 핵심 개념을 정리해보세요.",
        "delta": 1 if correct else -1
    }

def _extract_json(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```json\s*|\s*```$", "", t, flags=re.IGNORECASE)
    m = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", t)
    return m.group(0) if m else t

def _safe_json_loads(s: str, fallback=None):
    try:
        return json.loads(s)
    except Exception:
        return fallback

def _coerce_mc_options(options):
    if not isinstance(options, list): return []
    opts = [str(o).strip() for o in options][:4]
    return opts if len(opts) == 4 else []

def _get_user_id(user):
    if not user: return None
    if isinstance(user, dict): return user.get("user_id") or user.get("id")
    return getattr(user, "user_id", None) or getattr(user, "id", None)

def _get_user_field(user, key, default=None):
    if not user: return default
    if isinstance(user, dict): return user.get(key, default)
    return getattr(user, key, default)

def ensure_user_keywords():
    if st.session_state.user_keywords:
        return
    user = st.session_state.get("user")
    user_id = _get_user_id(user)
    st.session_state.user_keywords = fetch_user_keywords(user_id) if user_id else []

def load_common_questions():
    if not os.path.exists(COMMON_PATH):
        st.error(f"공통문항 파일을 찾을 수 없습니다: {COMMON_PATH}")
        return []
    with open(COMMON_PATH, "r", encoding="utf-8") as f:
        qs = json.load(f)
    for q in qs:
        q["options"] = q.get("options", []) or []
        q["weight"] = q.get("weight", 1) or 1
    return qs[:COMMON_COUNT]

def classify_level(score, max_score):
    rate = 0 if max_score == 0 else score / max_score
    if rate <= 0.2: return "Beginner"
    if rate <= 0.6: return "Intermediate"
    return "Advanced"

def save_generated_question(q: list[dict], meta: dict):
    ts = time.strftime("%Y%m%d-%H%M%S")
    fname = os.path.join(GENERATED_DIR, f"quiz_{ts}.json")
    payload = {"meta": meta, "questions": q}
    try:
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 저장 실패: {e}")

def save_result(score, level):
    user = st.session_state.get("user")
    if not user or not supabase:
        return None
    user_id = _get_user_id(user)
    try:
        res = supabase.table("users").select("user_name, user_role").eq("user_id", user_id).execute()
        if res.data:
            user_data = res.data[0]
            user_name = user_data["user_name"] if isinstance(user_data, dict) else getattr(user_data, "user_name", "Anonymous")
            st.session_state.role = user_data.get("user_role", "User") if isinstance(user_data, dict) else getattr(user_data, "user_role", "User")
        else:
            user_name = "Anonymous"
            if not isinstance(st.session_state.role, str):
                st.session_state.role = _get_user_field(user, "user_role", "User")
    except Exception:
        user_name = "Anonymous"
    try:
        supabase.table("quiz_results").insert({
            "user_id": user_id, "user_name": user_name, "score": score, "level": level
        }).execute()
    except Exception:
        return None
    return {"user_name": user_name, "score": score, "level": level}

# ── 문제 생성/채점 LLM 프롬프트 ───────────────────────────────────────────────
SYSTEM_PROMPT_QGEN = """
너는 한국어 금융 교육 전문가다. OX 또는 4지선다 문제 중 1문항을 생성한다.
JSON만 출력. 필요한 필드:
- question_type: "ox" | "mcq"
- question_text: string
- options: (mcq일 때만) 4개 배열
- answer: mcq "1"~"4", ox "O"/"X"
- explanation: 두 문장 이내
- level: "easy" | "medium"
- weight: easy=1, medium=2
"""

USER_PROMPT_QGEN_TMPL = """
사용자 역량(0~10): {proficiency}/10
누적 점수: {score}/{max_score}
틀렸던 문제(최대 3개): {wrong_summary}
이전 문항(요약): {history_summary}
관심사 키워드: {keywords_str}

위 정보를 반영해 1문항만 생성. JSON만.
"""

SYSTEM_PROMPT_EVAL = """
너는 금융 퀴즈 채점 평가자다. JSON만.
출력 키: is_correct(bool), feedback(str), delta(int -2~+2)
"""

USER_PROMPT_EVAL_TMPL = """
문항: {question_text}
선택지: {options}
정답: {answer}
사용자 답변: {user_answer}
난이도: {level}
proficiency: {proficiency}
JSON만.
"""

# ── LLM 요약 프롬프트(3문장) ────────────────────────────────────────────────
SYSTEM_PROMPT_SUMMARY = """
너는 한국어 금융 교육 코치다. 퀴즈 세션의 전체 기록을 분석해
1) 최종 숙련 레벨 라벨(초급/중급/상급)과
2) 금융지식 수준을 설명하는 3문장 요약
을 JSON으로만 출력한다.

규칙:
- JSON 키: level (초급|중급|상급), summary_sentences (문자열 3개 배열), evidence (선택), next_actions (선택)
- summary_sentences: 각 1문장, 총 3문장. '정답입니다/오답입니다' 같은 채점 문구 금지. 구체적 개념/주제 언급.
- evidence: {overall_accuracy: 0~1, weighted_score: 0~1, strong_topics: [{topic, accuracy, n}], weak_topics: [{topic, accuracy, n}]}
- next_actions: 2~3개의 간단한 다음 학습 액션.
- 텍스트 이외 설명, 마크다운, 코드블록 금지. JSON만.
"""

USER_PROMPT_SUMMARY_TMPL = """
최종 레벨(영문): {level_eng}
총 가중치: {total_weight}
사용자 관심사: {keywords}

문항 기록(최대 {max_items}개):
{history_json}

토픽 키워드:
{topic_json}

요구:
- 위 기록을 바탕으로 강점/약점을 주제 단어로 구체화.
- '초급/중급/상급' 중 하나로 level을 한국어로 표기.
- summary_sentences는 정확히 3문장.
- JSON만 출력.
"""

# ── 세션 집계(LLM 증거값 계산용/폴백용) ───────────────────────────────────────
def _aggregate_session(history: list[dict], total_weight: int, user_keywords: list[str]):
    agg = {
        "total": len(history),
        "correct_cnt": 0,
        "weighted_score": 0.0,
        "overall_accuracy": 0.0,
        "topic_stats": {},
        "hint_rate": 0.0,
        "avg_time_sec": None
    }
    if not history:
        return agg

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
        "next_actions": [f"{', '.join(weak_names)} 10문항 보충", "오답노트에 헷갈린 근거 1줄 정리"]
    }

# ── LLM 요약 생성기 ──────────────────────────────────────────────────────────
def generate_level_summary_llm(level_eng: str, history: list[dict], total_weight: int, user_keywords: list[str]):
    """
    LLM으로 3문장 요약 생성. 실패/무API면 None 반환(규칙기반 폴백 사용).
    """
    if not GOOGLE_API_KEY:
        return None

    # 토큰 고려해서 compact 역사 생성 (최대 40개)
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
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        resp = model.generate_content([
            SYSTEM_PROMPT_SUMMARY,
            USER_PROMPT_SUMMARY_TMPL.format(
                level_eng=level_eng,
                total_weight=total_weight,
                keywords=", ".join(user_keywords) if user_keywords else "없음",
                max_items=MAX_ITEMS,
                history_json=json.dumps(compact, ensure_ascii=False),
                topic_json=json.dumps(topic_json, ensure_ascii=False)
            )
        ])
        content = (resp.text or "").strip()
        data = _safe_json_loads(_extract_json(content), None)
        if not data:
            return None

        # 필수 필드 정리/보정
        level = str(data.get("level", "")).strip()
        if level not in ("초급", "중급", "상급"):
            # 영문이 들어왔을 때 보정
            level_map = {"Beginner": "초급", "Intermediate": "중급", "Advanced": "상급"}
            level = level_map.get(level, "중급")

        summaries = data.get("summary_sentences", [])
        if not isinstance(summaries, list) or len(summaries) < 3:
            return None

        out = {
            "level": level,
            "summary_sentences": summaries[:3],
            "evidence": data.get("evidence", None),
            "next_actions": data.get("next_actions", None),
        }
        return out
    except Exception as e:
        print("[LLM summary] failed:", e)
        return None

# ── LLM 문항 생성/채점 ────────────────────────────────────────────────────────
def generate_next_question(proficiency: int, score: int, max_score: int, wrong_notes: list, history: list, keywords: list):
    short_hist = [{
        "q": h["question_text"][:40] + ("..." if len(h["question_text"]) > 40 else ""),
        "ans": h["answer"], "ua": h["user_answer"], "ok": h["correct"]
    } for h in history[-5:]]
    history_summary = json.dumps(short_hist, ensure_ascii=False)
    wrong_summary = " / ".join(wrong_notes[-3:]) if wrong_notes else "없음"
    keywords_str = ", ".join(keywords) if keywords else "기초, 저위험, ETF, 예금, 채권"

    if not GOOGLE_API_KEY:
        if random.random() < 0.35:
            return {
                "question_type": "ox",
                "question_text": "국채 금리가 오르면 기존 채권 가격은 하락한다. (O/X)",
                "options": [], "answer": "O",
                "explanation": "채권 가격은 금리와 역의 관계입니다.",
                "level": "easy" if proficiency < 6 else "medium",
                "weight": 1 if proficiency < 6 else 2
            }
        else:
            return {
                "question_type": "mcq",
                "question_text": f"관심사({keywords_str.split(',')[0]})와 가장 관련 깊은 저비용 분산투자 수단은?",
                "options": ["1. 종목 몰빵", "2. 레버리지 단타", "3. 인덱스 ETF", "4. 코인 선물"],
                "answer": "3",
                "explanation": "인덱스 ETF는 낮은 보수로 광범위한 분산투자가 가능합니다.",
                "level": "easy" if proficiency < 6 else "medium",
                "weight": 1 if proficiency < 6 else 2
            }

    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content([
        SYSTEM_PROMPT_QGEN,
        USER_PROMPT_QGEN_TMPL.format(
            proficiency=proficiency, score=score, max_score=max_score or 1,
            wrong_summary=wrong_summary, history_summary=history_summary, keywords_str=keywords_str
        )
    ])
    content = (resp.text or "").strip()
    data = _safe_json_loads(_extract_json(content), {}) or {}
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
            q = {
                "question_type": "mcq",
                "question_text": "인덱스 펀드의 특징으로 옳지 않은 것은?",
                "options": ["1. 지수 추종", "2. 낮은 보수", "3. 초과수익 직접 추구", "4. 분산투자"],
                "answer": "3",
                "explanation": "인덱스 펀드는 지수 복제를 목표로 합니다.",
                "level": "medium" if proficiency >= 6 else "easy",
                "weight": 2 if proficiency >= 6 else 1
            }
    else:
        if not q["question_text"] or q["answer"].upper() not in {"O","X"}:
            q = {
                "question_type": "ox",
                "question_text": "채권 금리가 오르면 기존 채권 가격은 하락한다. (O/X)",
                "options": [], "answer": "O",
                "explanation": "가격과 금리는 역관계입니다.",
                "level": "easy" if proficiency < 6 else "medium",
                "weight": 1 if proficiency < 6 else 2
            }
    return q

def evaluate_answer(question_text: str, options, answer: str, user_answer: str, level:str, proficiency: int):
    cache_key = json.dumps({
        "q": question_text, "opts": options, "a": answer, "ua": user_answer, "p": proficiency, "lvl": level or "easy"
    }, ensure_ascii=False, sort_keys=True)
    cache = st.session_state.get("eval_cache", {})
    if cache_key in cache:
        return cache[cache_key]

    if not GOOGLE_API_KEY:
        result = _local_eval(question_text, options, answer, user_answer, proficiency)
        cache[cache_key] = result
        st.session_state.eval_cache = cache
        return result

    model = genai.GenerativeModel(GEMINI_MODEL)
    prompts = [
        SYSTEM_PROMPT_EVAL,
        USER_PROMPT_EVAL_TMPL.format(
            question_text=question_text, options=options, answer=answer,
            user_answer=user_answer, level=(level or "easy"), proficiency=proficiency
        )
    ]
    for attempt, sleep_sec in enumerate([0, 1.0, 2.0, 4.0]):
        try:
            if sleep_sec: time.sleep(sleep_sec)
            resp = model.generate_content(prompts)
            content = (resp.text or "").strip()
            data = _safe_json_loads(_extract_json(content), {}) or {}
            result = {
                "is_correct": bool(data.get("is_correct", user_answer.strip().lower() == answer.strip().lower())),
                "feedback": str(data.get("feedback", "")).strip() or (
                    "정답입니다." if user_answer.strip().lower() == answer.strip().lower() else "오답입니다."
                ),
                "delta": int(data.get("delta", 1 if user_answer.strip().lower() == answer.strip().lower() else -1))
            }
            cache[cache_key] = result
            st.session_state.eval_cache = cache
            return result
        except (ResourceExhausted, TooManyRequests):
            if attempt == 3:
                result = _local_eval(question_text, options, answer, user_answer, proficiency)
                cache[cache_key] = result
                st.session_state.eval_cache = cache
                return result
            continue
        except Exception:
            result = _local_eval(question_text, options, answer, user_answer, proficiency)
            cache[cache_key] = result
            st.session_state.eval_cache = cache
            return result

# ── Sidebar ──────────────────────────────────────────────────────────────────
def render_sidebar_status():
    with st.sidebar:
        st.markdown("### 📊 진행 요약")
        prog = (st.session_state.quiz_index) / (TOTAL_QUESTIONS or 1)
        st.progress(min(1.0, prog))
        st.metric("진행", f"{st.session_state.quiz_index}/{TOTAL_QUESTIONS}")
        st.metric("획득 점수", f"{st.session_state.quiz_score}/{st.session_state.total_weight or 1}")
        st.metric("숙련도(0~10)", st.session_state.proficiency)
        if st.session_state.user_keywords:
            st.caption("관심사")
            st.markdown("".join([f"<span class='tag'>{t}</span>" for t in st.session_state.user_keywords]),
                        unsafe_allow_html=True)

# ── Quiz UI ───────────────────────────────────────────────────────────────────
def render_quiz_section():
    inject_styles()
    init_quiz_state()
    ensure_user_keywords()
    render_sidebar_status()
    if not st.session_state.get("quiz_started", False):
        return

    if not st.session_state.quiz_questions:
        st.session_state.quiz_questions = load_common_questions()
        st.session_state.quiz_index = 0
        st.session_state.quiz_score = 0
        st.session_state.total_weight = sum(q.get("weight",1) for q in st.session_state.quiz_questions)
        st.session_state.proficiency = 5
        st.session_state.wrong_notes = []
        st.session_state.history = []
        st.session_state.generated_count = 0

    st.markdown('<div class="quiz-top-spacer"></div>', unsafe_allow_html=True)
    mode = "공통문제" if st.session_state.quiz_index < COMMON_COUNT else "LLM 생성"
    st.markdown(f"""
    <div class="quiz-header">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
        <div><strong>💡 금융 퀴즈</strong></div>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <span class="badge mode">🧭 {mode}</span>
          <span class="badge score">🏆 점수 {st.session_state.quiz_score}/{st.session_state.total_weight or 1}</span>
          <span class="badge">🧠 Proficiency {st.session_state.proficiency}/10</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.progress((st.session_state.quiz_index) / (TOTAL_QUESTIONS or 1))

    # LLM 생성부(필요 시)
    while len(st.session_state.quiz_questions) < TOTAL_QUESTIONS and st.session_state.quiz_index >= len(st.session_state.quiz_questions):
        q = generate_next_question(
            proficiency=st.session_state.proficiency,
            score=st.session_state.quiz_score,
            max_score=st.session_state.total_weight or 1,
            wrong_notes=st.session_state.wrong_notes,
            history=st.session_state.history,
            keywords=st.session_state.user_keywords
        )
        st.session_state.quiz_questions.append(q)
        st.session_state.total_weight += q.get("weight", 1)
        st.session_state.generated_count += 1

    # 생성셋 저장(1회)
    if (len(st.session_state.quiz_questions) == TOTAL_QUESTIONS and not st.session_state.get("generated_saved", False)):
        save_generated_question(
            st.session_state.quiz_questions,
            meta={
                "count": len(st.session_state.quiz_questions),
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "start_proficiency": 5,
                "current_proficiency": st.session_state.proficiency,
                "score_so_far": st.session_state.quiz_score,
                "total_weight": st.session_state.total_weight,
                "keywords": st.session_state.user_keywords,
            }
        )
        st.session_state.generated_saved = True

    total = len(st.session_state.quiz_questions)
    if st.session_state.quiz_index < total:
        quiz = st.session_state.quiz_questions[st.session_state.quiz_index]
        st.markdown(f"""
        <div class="question-card">
          <div class="question-title">Q{st.session_state.quiz_index + 1}. {quiz['question_text']}</div>
        </div>
        """, unsafe_allow_html=True)

        options = quiz.get("options", [])
        qtype = quiz.get("question_type", "mcq")
        answer_type = "mc" if (qtype == "mcq" and options) else "ox"
        key_ans = f"selected_answer_{st.session_state.quiz_index}"
        if key_ans not in st.session_state:
            st.session_state[key_ans] = None

        if answer_type == "ox":
            col = st.columns(2)
            if col[0].button("⭕", key=f"btn_o_{st.session_state.quiz_index}", use_container_width=True):
                st.session_state[key_ans] = "O"; st.rerun()
            if col[1].button("❌", key=f"btn_x_{st.session_state.quiz_index}", use_container_width=True):
                st.session_state[key_ans] = "X"; st.rerun()
        else:
            st.write("선택지 중 하나를 고르세요:")
            try:
                st.session_state[key_ans] = st.radio(
                    label=f"Q{st.session_state.quiz_index + 1} 선택지",
                    options=options, index=None,
                    key=f"radio_q{st.session_state.quiz_index}", label_visibility="collapsed"
                )
            except TypeError:
                st.session_state[key_ans] = st.radio(
                    label=f"Q{st.session_state.quiz_index + 1} 선택지",
                    options=options,
                    key=f"radio_q{st.session_state.quiz_index}", label_visibility="collapsed"
                )
        selected_answer = st.session_state[key_ans]

        next_disabled = selected_answer is None
        if st.button("다음 ▶", type="primary", disabled=next_disabled, use_container_width=True, key=f"next_{st.session_state.quiz_index}"):
            if st.session_state.get("processing"): st.stop()
            st.session_state.processing = True
            user_answer = (selected_answer or "").strip()
            correct = (quiz["answer"] or "").strip()
            weight = quiz.get("weight", 1)

            if answer_type == "mc":
                try:
                    idx = options.index(selected_answer)
                    user_answer = str(idx + 1)
                except ValueError:
                    user_answer = "0"

            eval_res = evaluate_answer(
                question_text=quiz["question_text"],
                options=options if options else [],
                answer=correct,
                user_answer=user_answer,
                level=quiz.get("level", "easy"),
                proficiency=st.session_state.proficiency
            )
            st.session_state.proficiency = max(0, min(10, st.session_state.proficiency + int(eval_res.get("delta", 0))))

            is_correct = (user_answer.strip().lower() == correct.strip().lower())
            if is_correct:
                st.session_state.quiz_score += weight
            else:
                st.session_state.wrong_notes.append(quiz["question_text"])

            st.session_state.history.append({
                "question_text": quiz["question_text"],
                "options": options,
                "answer": correct,
                "user_answer": user_answer,
                "correct": is_correct,
                "weight": weight,
                "proficiency_after": st.session_state.proficiency
            })

            feedback_text = "정답입니다! ✅" if is_correct else f"오답입니다 ❌ . 정답은 {correct}입니다."
            if eval_res.get("feedback"):
                full_feedback = f"{feedback_text}\n{eval_res['feedback']}"
            else:
                full_feedback = feedback_text

            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": full_feedback
            })

            st.session_state.processing = False
            st.session_state.quiz_index += 1
            st.rerun()

    else:
        # ── 완료 시: 레벨 산정 → LLM 요약(폴백 포함) → 저장/표시 ─────────────
        total_weight = st.session_state.total_weight
        score = st.session_state.quiz_score
        level_eng = classify_level(score, total_weight)  # Beginner/Intermediate/Advanced
        result_data = save_result(score, level_eng)
        user_name = result_data.get("user_name") if result_data else None

        level_map = {"Beginner": "초급", "Intermediate": "중급", "Advanced": "상급"}
        level_kor = level_map.get(level_eng, "중급")

        # 1) LLM 요약 시도
        level_summary = generate_level_summary_llm(
            level_eng=level_eng,
            history=st.session_state.history,
            total_weight=total_weight,
            user_keywords=st.session_state.user_keywords
        )

        model_version = "llm_v1"
        # 2) 실패/무API면 규칙 기반 폴백
        if not level_summary:
            agg = _aggregate_session(st.session_state.history, total_weight, st.session_state.user_keywords)
            level_summary = _build_summary_from_agg(agg, level_kor, st.session_state.user_keywords)
            model_version = "rule_based_v1"
        else:
            # evidence가 비어있으면 최소 증거값 채워주기(표시용 안전망)
            if not level_summary.get("evidence"):
                agg = _aggregate_session(st.session_state.history, total_weight, st.session_state.user_keywords)
                strong, weak = _rank_topics(agg["topic_stats"])
                level_summary["evidence"] = {
                    "overall_accuracy": agg["overall_accuracy"],
                    "weighted_score": agg["weighted_score"],
                    "strong_topics": [{"topic": n, "accuracy": round(c/t,2) if t else 0.0, "n": t} for n,t,c,_ in strong],
                    "weak_topics": [{"topic": n, "accuracy": round(c/t,2) if t else 0.0, "n": t} for n,t,c,_ in weak],
                }

        # 저장
        try:
            if supabase:
                supabase.table("user_level_snapshots").insert({
                    "user_id": _get_user_id(st.session_state.get("user")),
                    "session_id": str(uuid.uuid4()),
                    "level": level_summary["level"],
                    "summary_sentences": level_summary["summary_sentences"],
                    "evidence": level_summary.get("evidence"),
                    "next_actions": level_summary.get("next_actions"),
                    "model_version": model_version
                }).execute()
        except Exception as e:
            print("[snapshots] save failed:", e)

        if not st.session_state.get("completion_announced", False):
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": "퀴즈를 완료하셨군요! 이제 다음 단계를 진행할게요"
            })
            st.session_state.completion_announced = True

        # 카드 렌더
        render_result_card(score, total_weight, level_eng, user_name)

        # 요약 카드
        ev = level_summary.get("evidence", {}) or {}
        overall_pct = int((ev.get("overall_accuracy") or 0) * 100)
        weighted = ev.get("weighted_score", 0)

        st.markdown(f"""
        <div style="border:1px solid rgba(148,163,184,.28);border-radius:16px;padding:16px;margin-top:10px;background:#fff;">
          <div style="font-weight:800;margin-bottom:6px;">🌟 금융 지식 요약 ({level_summary['level']})</div>
          <ul style="margin:0 0 8px 18px;line-height:1.55;">
            <li>{level_summary['summary_sentences'][0]}</li>
            <li>{level_summary['summary_sentences'][1]}</li>
            <li>{level_summary['summary_sentences'][2]}</li>
          </ul>
          <div style="opacity:.8;font-size:.9rem;">
            정답률 {overall_pct}% · 가중점수 {weighted}
          </div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔁 다시 시작", use_container_width=True):
                st.session_state.quiz_questions = []
                st.session_state.quiz_index = 0
                st.session_state.quiz_score = 0
                st.session_state.total_weight = 0
                st.session_state.proficiency = 5
                st.session_state.wrong_notes = []
                st.session_state.history = []
                st.session_state.generated_count = 0
                st.session_state.quiz_started = True
                st.session_state.quiz_completed = False
                st.session_state.completion_announced = False
                st.rerun()
        with c2:
            if st.button("✅ 완료", use_container_width=True):
                st.session_state.quiz_started = False
                st.session_state.quiz_completed = True
                st.session_state.quiz_index = 0
                st.session_state.quiz_score = 0
                st.rerun()

# ── Main Render (Chat + CTA-in-chat) ─────────────────────────────────────────
def render():
    inject_styles()
    init_quiz_state()
    ensure_user_keywords()

    # 상태 보정
    if "messages" not in st.session_state or not isinstance(st.session_state.messages, list):
        st.session_state.messages = []

    if "welcome_injected" not in st.session_state:
        st.session_state.welcome_injected = False

    # 첫 진입 환영 + CTA
    if not st.session_state.welcome_injected and len(st.session_state.messages) == 0:
        st.session_state.messages.append({
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": "안녕하세요! 금융 지식 퀴즈를 시작해보세요. 아래 버튼으로 시작할 수 있어요.",
            "cta": "start_quiz"
        })
        st.session_state.welcome_injected = True

    for m in st.session_state.messages:
        if isinstance(m, dict) and "role" in m and isinstance(m["role"], str):
            r = m["role"].strip().lower()
            m["role"] = r if r in ("assistant", "user") else "assistant"

    # 헤더
    st.title("🧠 오늘의 퀴즈")
    st.caption("공통문항 + LLM 맞춤 문항으로 금융 지식을 빠르게 점검합니다.")

    # 레이아웃
    left_screen, right_screen = st.columns([0.55, 0.45], border=True)

    with left_screen:
        if not st.session_state.get("quiz_started", False):
            st.markdown("""
            <div class="question-card">
              <div class="question-title">진행 방식</div>
              <ul style="margin:6px 0 0 18px; line-height:1.6;">
                <li>총 문항: 10문항 (공통 3 + 맞춤 7)</li>
                <li>문항 유형: OX 또는 4지선다</li>
                <li>난이도에 따라 가중치가 다릅니다 (easy=1, medium=2)</li>
                <li>제출 후 피드백은 챗봇 메시지로 제공됩니다</li>
              </ul>
            </div>
            """, unsafe_allow_html=True)
        else:
            render_quiz_section()

    with right_screen:
        st.title("🚒 금융 구조대")

        chat_container = st.container(border=True, height=500)
        with chat_container:
            has_cta = False
            for i, message in enumerate(st.session_state.messages):
                with st.chat_message(message["role"]):
                    if (
                        i == len(st.session_state.messages) - 1
                        and message["role"] == "assistant"
                        and "streaming" in st.session_state
                        and st.session_state.streaming
                    ):
                        st.write_stream(stream_data(message["content"]))
                        if "streaming" in st.session_state:
                            del st.session_state.streaming
                    else:
                        st.write(message["content"])

                    if (
                        message.get("cta") == "start_quiz"
                        and not st.session_state.get("quiz_started", False)
                        and not st.session_state.get("quiz_completed", False)
                    ):
                        has_cta = True
                        st.divider()
                        if st.button("▶ 시작하기", key="start_quiz_inside", use_container_width=True):
                            st.session_state.quiz_questions = []
                            st.session_state.quiz_index = 0
                            st.session_state.quiz_score = 0
                            st.session_state.total_weight = 0
                            st.session_state.proficiency = 5
                            st.session_state.wrong_notes = []
                            st.session_state.history = []
                            st.session_state.generated_count = 0
                            st.session_state.quiz_completed = False
                            st.session_state.completion_announced = False
                            st.session_state.quiz_started = True
                            st.rerun()

            # 폴백 CTA
            if (
                not has_cta
                and not st.session_state.get("quiz_started", False)
                and not st.session_state.get("quiz_completed", False)
            ):
                if st.button("▶ 시작하기", key="start_quiz_fallback"):
                    st.session_state.quiz_questions = []
                    st.session_state.quiz_index = 0
                    st.session_state.quiz_score = 0
                    st.session_state.total_weight = 0
                    st.session_state.proficiency = 5
                    st.session_state.wrong_notes = []
                    st.session_state.history = []
                    st.session_state.generated_count = 0
                    st.session_state.quiz_completed = False
                    st.session_state.completion_announced = False
                    st.session_state.quiz_started = True
                    st.rerun()

        # 입력창
        if prompt := st.chat_input("투자나 FIRE에 대해 질문해보세요...", key="fire_chatbot"):
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": prompt
            })
            response = generate_simple_response(prompt)
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": response
            })
            st.session_state.streaming = True
            st.rerun()
