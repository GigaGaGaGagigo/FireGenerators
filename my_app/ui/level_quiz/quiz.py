import os
import re
import json
import uuid
import time
import random
import time
import streamlit as st
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, TooManyRequests
from dotenv import load_dotenv
from supabase import create_client
from ui.level_quiz.data.user_context import fetch_user_keywords
from ui.chatbot.chatbot_sample import generate_simple_response, stream_data

# ── ENV / Clients ─────────────────────────────────────────────────────────────
load_dotenv()

# Supabase (결과 저장용)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.0-flash")

COMMON_PATH = "my_app/ui/level_quiz/data/common_questions.json"
GENERATED_DIR = "my_app/ui/level_quiz/data/generated"  # ★ 변경: 생성문항 저장 디렉토리
os.makedirs(GENERATED_DIR, exist_ok=True)              # ★ 변경: 폴더 자동 생성

TOTAL_QUESTIONS = 10
COMMON_COUNT = 3

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
        "messages": [],  # ★ 변경: 타입 보장
        "eval_cache": {},
        "processing": False,
        "generated_saved": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if not isinstance(st.session_state.messages, list):  # ★ 변경
        st.session_state.messages = []

# ── Utils ─────────────────────────────────────────────────────────────────────

# 로컬 채점 폴백 로직(단순/결정적)
def _local_eval(question_text, options, answer, user_answer, proficiency):
    correct = user_answer.strip().lower() == answer.strip().lower()
    return {
        "is_correct": correct,
        "feedback": "좋아요! 개념을 잘 이해하고 있어요." if correct else "괜찮아요. 해설을 읽고 개념을 정리해보세요.",
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

# ★ 변경: dict/객체 호환 헬퍼 (User.get 에러 방지)
def _get_user_id(user):
    if not user:
        return None
    if isinstance(user, dict):
        return user.get("user_id") or user.get("id")
    return getattr(user, "user_id", None) or getattr(user, "id", None)

def _get_user_field(user, key, default=None):
    if not user: return default
    if isinstance(user, dict): return user.get(key, default)
    return getattr(user, key, default)

# ★ 변경: 언제든 관심사 확보
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

# ★ 변경: 생성 문항 로컬 저장
def save_generated_question(q: list[dict], meta: dict):
    ts = time.strftime("%Y%m%d-%H%M%S")
    fname = os.path.join(GENERATED_DIR, f"quiz_{ts}.json")
    payload = {
        "meta": meta,
        "questions": q
    }
    try:
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 저장 실패: {e}")

def save_result(score, level):
    user = st.session_state.get("user")
    if not user or not supabase:
        return None
    user_id = _get_user_id(user)  # ★ 변경
    try:
        res = supabase.table("users").select("user_name, user_role").eq("user_id", user_id).execute()
        if res.data:
            user_data = res.data[0]
            user_name = user_data["user_name"] if isinstance(user_data, dict) else getattr(user_data, "user_name", "Anonymous")
            st.session_state.role = (
                user_data.get("user_role", "User") if isinstance(user_data, dict)
                else getattr(user_data, "user_role", "User")
            )
        else:
            user_name = "Anonymous"
            # user 객체에 role 정보가 있으면 반영
            if not isinstance(st.session_state.role, str):
                st.session_state.role = _get_user_field(user, "user_role", "User")
    except Exception:
        user_name = "Anonymous"
    try:
        supabase.table("quiz_results").insert({
            "user_id": user_id,
            "user_name": user_name,
            "score": score,
            "level": level
        }).execute()
    except Exception:
        return None
    return {"user_name": user_name, "score": score, "level": level}

# ── 2. LLM 프롬프트 ──────────────────────────────────────────────────────────
# ★ 변경: OX/4지선다 모두 허용 + 관심사 강제 반영
SYSTEM_PROMPT_QGEN = """
너는 한국어 금융 교육 전문가다. 사용자 수준을 정밀하게 측정하기 위해 OX 또는 4지선다 문제 중 1문항을 생성한다.
요구:
- JSON 객체 한 개만 반환.
- 필수 필드:
  - question_type: "ox" 또는 "mcq"
  - question_text: 문자열
  - options: question_type=="mcq"일 때만 4개 문자열 배열, "1~4" 선택지 의미
  - answer: mcq일 땐 "1"~"4", ox일 땐 "O" 또는 "X"
  - explanation: 두 문장 이내
  - level: "easy" 또는 "medium"
  - weight: 정수 (easy=1, medium=2)
- 오답은 그럴듯하되 명확히 틀리게 구성.
- 사용자 약점, 현재 수준(proficiency), **관심사 키워드**를 가능한 한 본문 주제에 반영.
- JSON만 출력하고 다른 텍스트는 출력하지 마라.
"""

USER_PROMPT_QGEN_TMPL = """
사용자 역량 점수(0~10): {proficiency}/10
누적 점수(가중치 합 기준): {score}/{max_score}
틀린 문제 요약(최대 3개): {wrong_summary}
이전 문항들(요약): {history_summary}
사용자 관심사 키워드: {keywords_str}

위 정보를 바탕으로 OX 또는 4지선다 중 적절한 형태로 1문항을 생성해줘.
JSON 객체만 출력.
"""

SYSTEM_PROMPT_EVAL = """
너는 금융 퀴즈 채점 및 난이도 조절 평가자다.
아래 정보를 바탕으로 채점 결과를 JSON으로만 출력하라.

요구사항:
- 출력 키: is_correct (true/false), feedback (문자열), delta (정수: -2~+2)
- feedback은 "정답입니다", "오답입니다", "맞습니다", "틀렸습니다" 등 정오 판단 문구나 이모지(✅❌ 등), 감탄사 없이 작성.
- 피드백 스타일:
  - 친절하고 간결하게, 실제 학습에 도움이 되는 설명만.
  - 정답일 때: 한 문장으로 핵심 개념을 요약.
  - 오답일 때:
    - proficiency ≤ 4 또는 level == "easy": 2~3문장. 쉬운 표현, 왜 틀렸는지 → 핵심 개념 → 바로 적용할 팁(한 문장) 순서.
    - 5 ≤ proficiency ≤ 7 또는 level == "medium": 2문장. 핵심 개념 + 왜/언제 그런지.
    - proficiency ≥ 8: 1~2문장. 개념 정의/예외, 간결한 근거.
- delta 가이드(단, -2~+2 범위 유지):
  - 정답: easy +1, medium +2 (고숙련일수록 +값을 줄여도 됨)
  - 오답: easy -1, medium -2 (저숙련일수록 -값을 줄이거나 0~-1 권장)

출력은 JSON 객체 한 개만. 다른 텍스트는 금지.
"""


USER_PROMPT_EVAL_TMPL = """
문항: {question_text}
선택지: {options}
정답: {answer}
사용자 답변: {user_answer}
난이도(level): {level}
현재 proficiency(0~10): {proficiency}
JSON만.
"""

# ── 3. LLM 호출 로직 ─────────────────────────────────────────────────────────
def generate_next_question(proficiency: int, score: int, max_score: int, wrong_notes: list, history: list, keywords: list):
    # 최근 5문항 요약
    short_hist = [{
        "q": h["question_text"][:40] + ("..." if len(h["question_text"]) > 40 else ""),
        "ans": h["answer"], "ua": h["user_answer"], "ok": h["correct"]
    } for h in history[-5:]]
    history_summary = json.dumps(short_hist, ensure_ascii=False)
    wrong_summary = " / ".join(wrong_notes[-3:]) if wrong_notes else "없음"
    keywords_str = ", ".join(keywords) if keywords else "기초, 저위험, ETF, 예금, 채권"

    # API 미사용시 로컬 fallback (mcq/ox 섞기) ★ 변경
    if not GOOGLE_API_KEY:
        if random.random() < 0.35:
            # OX
            return {
                "question_type": "ox",
                "question_text": "국채 금리가 오르면 일반적으로 채권 가격은 하락한다. (O/X)",
                "options": [],
                "answer": "O",
                "explanation": "채권 가격은 금리와 역의 관계입니다.",
                "level": "easy" if proficiency < 6 else "medium",
                "weight": 1 if proficiency < 6 else 2
            }
        else:
            # MCQ
            return {
                "question_type": "mcq",
                "question_text": "관심사({})과 가장 관련 깊은 저비용 분산투자 수단은?".format(keywords_str.split(",")[0] if keywords_str else "ETF"),
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
            proficiency=proficiency,
            score=score,
            max_score=max_score or 1,
            wrong_summary=wrong_summary,
            history_summary=history_summary,
            keywords_str=keywords_str
        )
    ])
    content = (resp.text or "").strip()
    data = _safe_json_loads(_extract_json(content), {})

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

    # 유효성 보정 ★ 변경
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
    else:  # OX
        if not q["question_text"] or q["answer"].upper() not in {"O","X"}:
            q = {
                "question_type": "ox",
                "question_text": "채권 금리가 오르면 기존 채권 가격은 하락한다. (O/X)",
                "options": [],
                "answer": "O",
                "explanation": "가격과 금리는 역관계입니다.",
                "level": "easy" if proficiency < 6 else "medium",
                "weight": 1 if proficiency < 6 else 2
            }

    return q

# 교체: evaluate_answer (재시도+폴백+캐시)
def evaluate_answer(question_text: str, options, answer: str, user_answer: str, level:str, proficiency: int):
    # 1) 캐시 키 구성 (같은 문항/같은 답변이면 API 재호출 방지)
    cache_key = json.dumps({
        "q": question_text, "opts": options, "a": answer, "ua": user_answer, "p": proficiency, "lvl": level or "easy"
    }, ensure_ascii=False, sort_keys=True)
    cache = st.session_state.get("eval_cache", {})
    if cache_key in cache:
        return cache[cache_key]

    # 2) API 키 없으면 즉시 로컬 채점
    if not GOOGLE_API_KEY:
        result = _local_eval(question_text, options, answer, user_answer,level, proficiency,level)
        cache[cache_key] = result
        st.session_state.eval_cache = cache
        return result

    # 3) Gemini 호출 시 재시도 + 429 폴백
    model = genai.GenerativeModel(GEMINI_MODEL)
    prompts = [
        SYSTEM_PROMPT_EVAL,
        USER_PROMPT_EVAL_TMPL.format(
            question_text=question_text,
            options=options,
            answer=answer,
            user_answer=user_answer,
            level=(level or "easy"),
            proficiency=proficiency
        )
    ]

    # 짧은 백오프 (RPM 초과 방지)
    for attempt, sleep_sec in enumerate([0, 1.0, 2.0, 4.0]):  # 최대 3회 재시도
        try:
            if sleep_sec:
                time.sleep(sleep_sec)
            resp = model.generate_content(prompts)
            content = (resp.text or "").strip()
            data = _safe_json_loads(_extract_json(content), {})
            result = {
                "is_correct": bool(data.get("is_correct", user_answer.strip().lower() == answer.strip().lower())),
                "feedback": str(data.get("feedback", "")).strip() or (
                    "정답입니다!" if user_answer.strip().lower() == answer.strip().lower() else "오답입니다."
                ),
                "delta": int(data.get("delta", 1 if user_answer.strip().lower() == answer.strip().lower() else -1))
            }
            cache[cache_key] = result
            st.session_state.eval_cache = cache
            return result

        except (ResourceExhausted, TooManyRequests) as e:
            # 마지막 시도에서 또 터지면 로컬 폴백
            if attempt == 3:
                result = _local_eval(question_text, options, answer, user_answer, proficiency,level)
                cache[cache_key] = result
                st.session_state.eval_cache = cache
                return result
            # 아니면 다음 루프로 백오프 후 재시도
            continue
        except Exception:
            # 기타 오류도 안전하게 로컬 폴백
            result = _local_eval(question_text, options, answer, user_answer, proficiency,level)
            cache[cache_key] = result
            st.session_state.eval_cache = cache
            return result

# ── Sidebar status ────────────────────────────────────────────────────────────
def render_sidebar_status():
    with st.sidebar:
        st.markdown("### 📊 진행 요약")
        prog = (st.session_state.quiz_index) / (TOTAL_QUESTIONS or 1)
        st.progress(min(1.0, prog))
        st.metric("진행", f"{st.session_state.quiz_index}/{TOTAL_QUESTIONS}")
        st.metric("획득 점수", f"{st.session_state.quiz_score}/{st.session_state.total_weight or 1}")
        st.metric("프로피션시(0~10)", st.session_state.proficiency)
        if st.session_state.user_keywords:
            st.caption("관심사")
            st.markdown("".join([f"<span class='tag'>{t}</span>" for t in st.session_state.user_keywords]),
                        unsafe_allow_html=True)

# ── 4. 반복 구조 + UI 엔진 ───────────────────────────────────────────────────
def render_quiz_section():
    inject_styles()
    init_quiz_state()
    ensure_user_keywords()     # ★ 변경: 먼저 관심사 확보
    render_sidebar_status()    # ★ 변경: 확보 후 사이드바 렌더

    if not st.session_state.get("quiz_started", False):
        return

    # 최초 진입: 공통문항 적재
    if not st.session_state.quiz_questions:
        st.session_state.quiz_questions = load_common_questions()
        st.session_state.quiz_index = 0
        st.session_state.quiz_score = 0
        st.session_state.total_weight = sum(q.get("weight",1) for q in st.session_state.quiz_questions)
        st.session_state.proficiency = 5
        st.session_state.wrong_notes = []
        st.session_state.history = []
        st.session_state.generated_count = 0

    # Header
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

    # 4~10번: 필요 시 LLM 생성 + 로컬 저장 ★ 변경
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

    # ★ 루프가 끝난 뒤: 전체 세트 한 번만 저장
    if (len(st.session_state.quiz_questions) == TOTAL_QUESTIONS
        and not st.session_state.get("generated_saved", False)):
        save_generated_question(
            st.session_state.quiz_questions,
            meta={
                "count": len(st.session_state.quiz_questions),
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "start_proficiency": 5,  # 시작값 사용 중이면 그대로
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

        # 질문 카드
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
            if col[0].button("⭕ O", key=f"btn_o_{st.session_state.quiz_index}", use_container_width=True):
                st.session_state[key_ans] = "O"; st.rerun()
            if col[1].button("❌ X", key=f"btn_x_{st.session_state.quiz_index}", use_container_width=True):
                st.session_state[key_ans] = "X"; st.rerun()
        else:
            st.write("선택지 중 하나를 고르세요:")
            try:
                st.session_state[key_ans] = st.radio(
                    label=f"Q{st.session_state.quiz_index + 1} 선택지",
                    options=options,
                    index=None,
                    key=f"radio_q{st.session_state.quiz_index}",
                    label_visibility="collapsed"
                )
            except TypeError:
                st.session_state[key_ans] = st.radio(
                    label=f"Q{st.session_state.quiz_index + 1} 선택지",
                    options=options,
                    key=f"radio_q{st.session_state.quiz_index}",
                    label_visibility="collapsed"
                )

        selected_answer = st.session_state[key_ans]

        # Next 버튼
        next_disabled = selected_answer is None
        if st.button("다음 ▶", type="primary", disabled=next_disabled, use_container_width=True, key=f"next_{st.session_state.quiz_index}"):
            if st.session_state.get("processing"):
                st.stop()
            st.session_state.processing = True
            user_answer = (selected_answer or "").strip()
            correct = (quiz["answer"] or "").strip()
            explanation = quiz.get("explanation", "")
            weight = quiz.get("weight", 1)

            # 객관식이면 "1~4" 인덱스로 변환
            if answer_type == "mc":
                try:
                    idx = options.index(selected_answer)
                    user_answer = str(idx + 1)
                except ValueError:
                    user_answer = "0"

            # 평가 LLM 호출
            eval_res = evaluate_answer(
                question_text=quiz["question_text"],
                options=options if options else [],
                answer=correct,
                user_answer=user_answer,
                level=quiz.get("level", "easy"),
                proficiency=st.session_state.proficiency
            )
            st.session_state.proficiency = max(0, min(10, st.session_state.proficiency + int(eval_res.get("delta", 0))))

            # 점수/오답
            is_correct = (user_answer.strip().lower() == correct.strip().lower())
            if is_correct:
                st.session_state.quiz_score += weight
            else:
                st.session_state.wrong_notes.append(quiz["question_text"])

            # 히스토리
            st.session_state.history.append({
                "question_text": quiz["question_text"],
                "options": options,
                "answer": correct,
                "user_answer": user_answer,
                "correct": is_correct,
                "weight": weight,
                "proficiency_after": st.session_state.proficiency
            })

            # 챗봇 피드백

            feedback_text = "정답입니다! ✅" if is_correct else f"오답입니다 ❌ . 정답은 {correct}입니다."

            # LLM 피드백 (해설 대체)
            if eval_res.get("feedback"):
                full_feedback = f"{feedback_text}\n{eval_res['feedback']}"
            else:
                full_feedback = feedback_text  # LLM 피드백 없으면 정답/오답만 표시

            # 채팅 메시지 추가
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": full_feedback
            })

            # 다음 문항
            st.session_state.processing = False
            st.session_state.quiz_index += 1
            st.rerun()

    else:
        total_weight = st.session_state.total_weight
        score = st.session_state.quiz_score
        level = classify_level(score, total_weight)
        result_data = save_result(score, level)
        user_name = result_data.get("user_name") if result_data else None

        if not st.session_state.get("completion_announced", False):
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": "퀴즈를 완료하셨군요! 이제 다음 단계를 진행할게요"
            })
            st.session_state.completion_announced = True

        render_result_card(score, total_weight, level, user_name)

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

# ── 메인 Render ──────────────────────────────────────────────────────────────
def render():
    inject_styles()
    init_quiz_state()
    ensure_user_keywords()  # ★ 변경: 시작 전에도 관심사 확보 -> 사이드바에 바로 표시됨

    # 1) 상태 보정
    if "messages" not in st.session_state or not isinstance(st.session_state.messages, list):
        st.session_state.messages = []

    # 2) 환영 메시지 1회 주입 플래그
    if "welcome_injected" not in st.session_state:
        st.session_state.welcome_injected = False

    # 3) 최초 1회: messages가 비어 있으면 환영 메시지 추가
    if not st.session_state.welcome_injected and len(st.session_state.messages) == 0:
        st.session_state.messages.append({
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": "안녕하세요! 금융 지식 퀴즈를 시작해보세요. 아래 버튼으로 시작할 수 있어요."
        })
        st.session_state.welcome_injected = True  # 다시 안 넣도록

    # (선택) role 정규화 - 혹시 모를 공백/대소문자 틀어짐 방지
    for m in st.session_state.messages:
        if isinstance(m, dict) and "role" in m and isinstance(m["role"], str):
            r = m["role"].strip().lower()
            if r not in ("assistant", "user"):
                r = "assistant"
            m["role"] = r

    # 헤더
    st.title("🧠 오늘의 퀴즈")
    st.caption("공통문항 + LLM 맞춤 문항으로 금융 지식을 빠르게 점검합니다.")

    # 상단 컨트롤
    with st.container():
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if not st.session_state.get("quiz_started", False):
                if st.button("▶ 시작하기", type="primary", use_container_width=True):
                    # 상태 초기화 후 시작
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
    # 본 레이아웃
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

    # 오른쪽 채팅 영역
    with right_screen:
        st.title("🚒 금융 구조대")

        # 채팅 메시지 영역 (높이 고정)
        chat_container = st.container(border=True, height=500)
        with chat_container:
            # 기존 메시지들 표시
            for i, message in enumerate(st.session_state.messages):
                with st.chat_message(message["role"]):
                    # 가장 마지막 메시지이고 AI 메시지인 경우에만 stream 사용
                    if (
                        i == len(st.session_state.messages) - 1
                        and message["role"] == "assistant"
                        and "streaming" in st.session_state
                        and st.session_state.streaming
                    ):
                        st.write_stream(stream_data(message["content"]))
                        # 스트리밍 완료 후 플래그 제거
                        if "streaming" in st.session_state:
                            del st.session_state.streaming
                    else:
                        st.write(message["content"])
        # ★ 변경: 오른쪽에서도 시작 가능 + 안전 초기화
        if not st.session_state.quiz_started and not st.session_state.quiz_completed:
            if st.button("시작하기", key="start_quiz_right"):
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

        
        # 채팅 입력 영역
        if prompt := st.chat_input("투자나 FIRE에 대해 질문해보세요...", key="fire_chatbot"):
            # 사용자 메시지 추가
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": prompt
            })

            # AI 응답 생성
            response = generate_simple_response(prompt)
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": response
            })

            # 스트리밍 플래그 설정
            st.session_state.streaming = True

            # 페이지 새로고침
            st.rerun()

