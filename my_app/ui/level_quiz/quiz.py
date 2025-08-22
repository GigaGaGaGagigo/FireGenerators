import os
import json
import uuid
import time
import random
import re
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client
from ui.level_quiz.data.user_context import fetch_user_keywords
from ui.chatbot.chatbot_sample import generate_simple_response, stream_data
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, BadRequestError


load_dotenv()

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# OpenAI (키 없으면 즉시 종료: 로컬 폴백 금지)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("OPENAI_API_KEY가 설정되지 않았습니다. .env에 OPENAI_API_KEY를 넣어주세요.")
    raise SystemExit("Missing OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

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

def save_result(score, level, level_summary):
    """
    퀴즈 결과 + LLM 요약(level_summary)을 함께 저장.
    - quiz_results 테이블에 summary_sentences, evidence, next_actions 컬럼이 JSON으로 있어야 합니다.
    """
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
            "user_id": user_id,
            "user_name": user_name,
            "score": score,
            "level": level,
            "summary_sentences": (level_summary or {}).get("summary_sentences"),
            "evidence": (level_summary or {}).get("evidence"),
            "next_actions": (level_summary or {}).get("next_actions"),
        }).execute()
    except Exception as e:
        # 저장 실패해도 앱이 죽지 않도록 조용히 무시(원하면 st.error로 노출)
        # st.error(f"[quiz_results 저장 실패] {e}")
        return None

    return {"user_name": user_name, "score": score, "level": level}
# ── OpenAI 공통 호출 유틸 (Chat Completions) ─────────────────────────────────
def _with_retry(callable_fn, max_tries=4):
    for i in range(max_tries):
        try:
            return callable_fn()
        except RateLimitError:
            if i == max_tries - 1: raise
            time.sleep((2 ** i) + random.random() * 0.5)
        except (APIConnectionError, APIError):
            if i == max_tries - 1: raise
            time.sleep((2 ** i) + random.random() * 0.5)

def _chat_json(system_prompt: str, user_prompt: str, json_schema: dict | None = None):
    """
    Chat Completions로 JSON 결과 받기.
    - 최신 SDK: response_format(json_schema) 사용
    - 구버전 SDK: response_format 미지원이면 자동 재시도(일반 텍스트 → JSON 파싱)
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    def _call_with_schema():
        kwargs = {
            "model": OPENAI_MODEL,
            "messages": messages,
        }
        if json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": json_schema,
                    "strict": True
                }
            }
        return client.chat.completions.create(**kwargs)

    # 1) 스키마 시도
    try:
        resp = _with_retry(_call_with_schema)
        text = (resp.choices[0].message.content or "").strip()
        return _safe_json_loads(_extract_json(text), None)
    except (TypeError, BadRequestError) as e:
        # - 서버가 스키마를 거부(BadRequestError: 400)하면
        #   → 스키마 없이 평문 JSON 강제 프롬프트로 재시도
        pass
    except APIError as e:
        # 일부 환경에선 APIError로 400이 포장될 수 있음
        if "response_format" in str(e) or "Invalid schema for response_format" in str(e):
            pass
        else:
            raise
    # 2) 스키마 없이 강력 지시로 JSON만 요구
    def _call_plain():
        plain_messages = [
            {"role": "system", "content": system_prompt + "\n반드시 JSON만 출력하세요."},
            {"role": "user", "content": user_prompt + "\nJSON 이외의 텍스트/마크다운/설명 금지."},
        ]
        return client.chat.completions.create(model=OPENAI_MODEL, messages=plain_messages)
    resp = _with_retry(_call_plain)
    text = (resp.choices[0].message.content or "").strip()
    return _safe_json_loads(_extract_json(text), None)

# ── 문제 생성/채점/요약 프롬프트 ─────────────────────────────────────────────
SYSTEM_PROMPT_QGEN = (
    "너는 한국어 금융 교육 전문가다. OX 또는 4지선다 문제 중 1문항을 생성한다. "
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
    "규칙: JSON 키: level(초급|중급|상급), summary_sentences(문자열 3개 배열), evidence(선택), next_actions(선택). "
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

# ── JSON Schema (문서화용; 구버전 SDK에서도 동작하게 설계됨) ────────────────
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
        "evidence": {"type": "object"},
        "next_actions": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["level", "summary_sentences"],
    "additionalProperties": False
}


# ── 세션 집계/랭킹/요약 폴백 ──────────────────────────────────────────────────
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
        matched = False
        for topic, pats in TOPIC_KEYWORDS.items():
            if any(re.search(p, qtext, flags=re.I) for p in pats):
                agg["topic_stats"][topic]["total"] += 1
                if is_ok: agg["topic_stats"][topic]["correct"] += 1
                matched = True
        if not matched and user_keywords:
            t = "관심사"
            agg["topic_stats"].setdefault(t, {"total": 0, "correct": 0})
            agg["topic_stats"][t]["total"] += 1
            if is_ok: agg["topic_stats"][t]["correct"] += 1
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
    evidence = {"overall_accuracy": agg["overall_accuracy"], "weighted_score": agg["weighted_score"],
                "avg_time_sec": agg["avg_time_sec"], "hint_rate": agg["hint_rate"],
                "strong_topics": strong_topics, "weak_topics": weak_topics}
    return {"level": level_kor, "summary_sentences": [s1, s2, s3], "evidence": evidence,
            "next_actions": [f"{', '.join(weak_names)} 10문항 보충", "오답노트에 헷갈린 근거 1줄 정리"]}

# ── LLM 요약 생성기 (gpt‑5‑mini) ─────────────────────────────────────────────
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
    data = _chat_json(SYSTEM_PROMPT_SUMMARY, user_prompt, SUMMARY_SCHEMA)
    if not data: return None
    level = str(data.get("level", "")).strip()
    if level not in ("초급", "중급", "상급"):
        level = {"Beginner": "초급", "Intermediate": "중급", "Advanced": "상급"}.get(level, "중급")
    summaries = data.get("summary_sentences", [])
    if not isinstance(summaries, list) or len(summaries) < 3:
        return None
    return {"level": level, "summary_sentences": summaries[:3],
            "evidence": data.get("evidence"), "next_actions": data.get("next_actions")}

# ── LLM 문항 생성 (gpt‑5‑mini) ───────────────────────────────────────────────
def generate_next_question(proficiency: int, score: int, max_score: int, wrong_notes: list, history: list, keywords: list):
    short_hist = [{
        "q": h["question_text"][:40] + ("..." if len(h["question_text"]) > 40 else ""),
        "ans": h["answer"], "ua": h["user_answer"], "ok": h["correct"]
    } for h in history[-5:]]
    history_summary = json.dumps(short_hist, ensure_ascii=False)
    wrong_summary = " / ".join(wrong_notes[-3:]) if wrong_notes else "없음"
    keywords_str = ", ".join(keywords) if keywords else "기초, 저위험, ETF, 예금, 채권"

    user_prompt = USER_PROMPT_QGEN_TMPL.format(
        proficiency=proficiency, score=score, max_score=max_score or 1,
        wrong_summary=wrong_summary, history_summary=history_summary, keywords_str=keywords_str
    )
    data = _chat_json(SYSTEM_PROMPT_QGEN, user_prompt, QGEN_SCHEMA)
    if not data:
        st.error("문항 생성 LLM 호출 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        st.stop()

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
            st.error("생성된 문항 형식이 유효하지 않습니다. 다시 시도해주세요.")
            st.stop()
    else:
        if not q["question_text"] or q["answer"].upper() not in {"O","X"}:
            st.error("생성된 OX 문항 형식이 유효하지 않습니다. 다시 시도해주세요.")
            st.stop()
    return q

# ── 채점 (gpt‑5, 로컬 폴백 제거) ────────────────────────────────────────
def evaluate_answer(question_text: str, options, answer: str, user_answer: str, level:str, proficiency: int):
    cache_key = json.dumps({
        "q": question_text, "opts": options, "a": answer, "ua": user_answer, "p": proficiency, "lvl": level or "easy"
    }, ensure_ascii=False, sort_keys=True)
    cache = st.session_state.get("eval_cache", {})
    if cache_key in cache:
        return cache[cache_key]

    user_prompt = USER_PROMPT_EVAL_TMPL.format(
        question_text=question_text, options=options if options else [], answer=answer,
        user_answer=user_answer, level=(level or "easy"), proficiency=proficiency
    )
    data = None
    try:
        data = _chat_json(SYSTEM_PROMPT_EVAL, user_prompt, EVAL_SCHEMA)
    
    except Exception as e:
        # 호출 자체가 실패한 경우, 정확한 예외/메시지 보여주기
        st.error("채점용 LLM 호출 중 오류가 발생했습니다.")
        with st.sidebar:
            st.divider()
            st.caption("🛠 디버그 (채점 호출 예외)")
            st.code(f"{type(e).__name__}: {e}")
        st.stop()

    if not data:
        st.error("채점용 LLM 호출 중 오류가 발생했습니다. (JSON 파싱 실패)")
        # raw 변수는 이 스코프에 없으므로 사용 금지
        st.stop()

    result = {
        "is_correct": bool(data.get("is_correct")),
        "feedback": str(data.get("feedback", "")).strip(),
        "delta": int(data.get("delta", 0)),
    }
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
        if "llm_error" in st.session_state:
            st.divider()
            st.caption("🛠 디버그")
            st.code(st.session_state["llm_error"])

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
            full_feedback = f"{feedback_text}\n{eval_res['feedback']}" if eval_res.get("feedback") else feedback_text

            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": full_feedback
            })

            st.session_state.processing = False
            st.session_state.quiz_index += 1
            st.rerun()

    else:
        total_weight = st.session_state.total_weight
        score = st.session_state.quiz_score
        level_eng = classify_level(score, total_weight)  # Beginner/Intermediate/Advanced

        level_map = {"Beginner": "초급", "Intermediate": "중급", "Advanced": "상급"}
        level_kor = level_map.get(level_eng, "중급")

        level_summary = generate_level_summary_llm(
            level_eng=level_eng,
            history=st.session_state.history,
            total_weight=total_weight,
            user_keywords=st.session_state.user_keywords
        )

        model_version = "gpt5mini_chatcompletions"
        if not level_summary:
            agg = _aggregate_session(st.session_state.history, total_weight, st.session_state.user_keywords)
            level_summary = _build_summary_from_agg(agg, level_kor, st.session_state.user_keywords)
            model_version = "rule_based_v1"
        else:
            if not level_summary.get("evidence"):
                agg = _aggregate_session(st.session_state.history, total_weight, st.session_state.user_keywords)
                strong, weak = _rank_topics(agg["topic_stats"])
                level_summary["evidence"] = {
                    "overall_accuracy": agg["overall_accuracy"],
                    "weighted_score": agg["weighted_score"],
                    "strong_topics": [{"topic": n, "accuracy": round(c/t,2) if t else 0.0, "n": t} for n,t,c,_ in strong],
                    "weak_topics": [{"topic": n, "accuracy": round(c/t,2) if t else 0.0, "n": t} for n,t,c,_ in weak],
                }

        if not st.session_state.get("completion_announced", False):
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": "퀴즈를 완료하셨군요! 이제 다음 단계를 진행할게요"
            })
            st.session_state.completion_announced = True
            
        result_data = save_result(score, level_eng, level_summary)
        user_name = result_data.get("user_name") if result_data else None

        render_result_card(score, total_weight, level_eng, user_name)

        ev = (level_summary.get("evidence", {}) or {})
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

    if "messages" not in st.session_state or not isinstance(st.session_state.messages, list):
        st.session_state.messages = []

    if "welcome_injected" not in st.session_state:
        st.session_state.welcome_injected = False

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

    st.title("🧠 오늘의 퀴즈")
    st.caption("공통문항 + LLM 맞춤 문항으로 금융 지식을 빠르게 점검합니다.")

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
