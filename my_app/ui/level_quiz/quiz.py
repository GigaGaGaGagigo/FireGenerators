import os
import re
import json
import uuid
import streamlit as st
import google.generativeai as genai
from dotenv import load_dotenv
from supabase import create_client
from ui.level_quiz.data.user_context import fetch_user_keywords

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
TOTAL_QUESTIONS = 10
COMMON_COUNT = 3

# ── Style (상단 잘림 방지 & 깔끔 스타일) ──────────────────────────────────────
def inject_styles():
    st.markdown("""
    <style>
      .block-container { padding-top: 1.2rem; }
      .quiz-top-spacer { height: 12px; }
      /* 상단 잘림 방지: 여백 확대 + 스크롤 앵커 보정 */
      .block-container { padding-top: 3.2rem; padding-bottom: 2rem; }
      .main > div:first-child { padding-top: 0.8rem !important; }
      html { scroll-padding-top: 64px; }

      .stMarkdown p { margin-bottom: 0.4rem; }

      /* 헤더 카드 */
      .quiz-header {
        background: linear-gradient(135deg, rgba(99,102,241,.10), rgba(16,185,129,.10));
        border: 1px solid rgba(148,163,184,.22);
        border-radius: 16px; padding: 16px 18px; margin-bottom: 10px;
      }
      .badge {
        display:inline-flex; gap:6px; align-items:center;
        padding: 4px 10px; border-radius: 999px;
        background: rgba(148,163,184,.15);
        border: 1px solid rgba(148,163,184,.35);
        font-size: .85rem;
      }
      .badge.mode { background: rgba(99,102,241,.12); border-color: rgba(99,102,241,.35); }
      .badge.score { background: rgba(16,185,129,.12); border-color: rgba(16,185,129,.35); }

      /* 질문 카드 */
      .question-card {
        border: 1px solid rgba(148,163,184,.28);
        border-radius: 16px; padding: 18px; margin: 10px 0 14px 0;
        background: rgba(2,6,23,.02);
      }
      .question-title { font-weight: 700; font-size: 1.05rem; }

      /* 옵션 카드형 라디오 느낌 */
      div[data-baseweb="radio"] > div { gap: 10px; }
      label[data-baseweb="radio"] {
        width: 100%;
        border: 1px solid rgba(148,163,184,.3);
        border-radius: 12px; padding: 10px 12px; margin: 4px 0;
        transition: all .15s ease;
        background: white;
      }
      label[data-baseweb="radio"]:hover {
        border-color: rgba(99,102,241,.6);
        box-shadow: 0 0 0 3px rgba(99,102,241,.12) inset;
      }

      /* 버튼 */
      .stButton > button {
        border-radius: 12px !important;
        height: 48px; font-size: 18px; font-weight: 700;
      }

      /* 사이드바 태그 */
      .tag {
        display:inline-block; padding:4px 10px; margin: 2px 6px 6px 0;
        border-radius: 999px; font-size:.85rem;
        background: rgba(148,163,184,.14); border: 1px solid rgba(148,163,184,.3);
      }
    </style>
    """, unsafe_allow_html=True)

def render_result_card(score: int, total_weight: int, level: str, user_name: str | None = None):
    st.balloons()
    name = f" <span style='opacity:.7'>( {user_name} )</span>" if user_name else ""
    st.markdown(f"""
    <div style="
      border:1px solid rgba(148,163,184,.28);
      border-radius:16px;padding:18px;margin-top:8px;
      background:linear-gradient(135deg, rgba(99,102,241,.08), rgba(16,185,129,.08));
    ">
      <div style="font-weight:800;font-size:1.1rem;margin-bottom:6px;">🎉 금융 퀴즈 완료{name}</div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin:8px 0 2px 0;">
        <span style="padding:6px 12px;border-radius:999px;border:1px solid rgba(148,163,184,.35);background:white;">🏆 점수 <b>{score}</b> / {total_weight}</span>
        <span style="padding:6px 12px;border-radius:999px;border:1px solid rgba(148,163,184,.35);background:white;">🧠 레벨 <b>{level}</b></span>
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
        "proficiency": 5,       # 0~10
        "wrong_notes": [],
        "history": [],
        "generated_count": 0,
        "quiz_started": False,
        "quiz_completed": False,
        "user_keywords": [],
        "completion_announced": False,

    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

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

def load_common_questions():
    """1~3번: 로컬 공통문제 적재"""
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

def save_result(score, level):
    """Supabase quiz_results 저장(선택). 세션에 user가 없으면 None."""
    user = st.session_state.get("user")
    if not user or not supabase:
        return None
    user_id = user.get("user_id") or user.get("id")
    try:
        res = supabase.table("users").select("user_name, user_role").eq("user_id", user_id).execute()
        if res.data:
            user_data = res.data[0]
            user_name = user_data.get("user_name", "Anonymous")
            st.session_state.role = user_data.get("user_role", "User")
        else:
            user_name = "Anonymous"
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

# ── 2. LLM 프롬프트 설계 ─────────────────────────────────────────────────────
SYSTEM_PROMPT_QGEN = """
너는 한국어 금융 교육 전문가다. 사용자 수준을 더 정밀하게 측정하기 위한 4지선다 문제를 1문항 생성한다.
요구:
- JSON 객체 한 개만 반환.
- 필수 필드: question_text, options(4개 문자열), answer("1"~"4"), explanation(두 문장 이내), level("easy" 또는 "medium"), weight(int: easy=1, medium=2).
- 애매모호하지 않게, 오답도 그럴듯하지만 명확히 틀리게 구성.
- 사용자 약점(틀린 개념)과 현재 수준, 관심사를 반영해 난이도와 내용을 조정.
"""

USER_PROMPT_QGEN_TMPL = """
현재까지 측정된 사용자의 금융역량 점수(0~10): {proficiency}/10
누적 점수(가중치 합 기준): {score}/{max_score}
틀린 문제 요약(최대 3개): {wrong_summary}
이전 문항들(요약): {history_summary}
사용자 관심사 키워드: {keywords_str}

위 정보를 바탕으로 다음 요구를 만족하는 새 4지선다 문제 1개를 생성해줘.
출력은 오직 JSON 객체 한 개만 반환.
"""

SYSTEM_PROMPT_EVAL = """
너는 금융 퀴즈 채점 및 난이도 조절을 돕는 평가자다.
입력된 문항, 정답, 사용자의 답변을 보고,
- is_correct: true/false
- feedback: 한국어 한두 문장 피드백
- delta: 정수 (-2 ~ +2) 범위. 사용자의 역량 점수(proficiency)를 얼마나 조정할지 제안.
JSON 객체로만 출력.
"""

USER_PROMPT_EVAL_TMPL = """
문항: {question_text}
선택지: {options}
정답: {answer}
사용자 답변: {user_answer}
현재 proficiency(0~10): {proficiency}

출력은 오직 JSON 객체 한 개만.
"""

# ── 3. LLM 호출 로직 (Node 두 개) ────────────────────────────────────────────
def generate_next_question(proficiency: int, score: int, max_score: int, wrong_notes: list, history: list, keywords: list):
    # 최근 5문항만 요약
    short_hist = []
    for h in history[-5:]:
        short_hist.append({
            "q": h["question_text"][:40] + ("..." if len(h["question_text"]) > 40 else ""),
            "ans": h["answer"],
            "ua": h["user_answer"],
            "ok": h["correct"]
        })
    history_summary = json.dumps(short_hist, ensure_ascii=False)
    wrong_summary = " / ".join(wrong_notes[-3:]) if wrong_notes else "없음"
    keywords_str = ", ".join(keywords) if keywords else "기초, 저위험, ETF, 예금, 채권"

    if not GOOGLE_API_KEY:
        return {
            "question_text": "채권 금리 상승 시 기존 채권 가격의 일반적 변화는?",
            "options": ["1. 상승", "2. 하락", "3. 불변", "4. 금리와 무관"],
            "answer": "2",
            "explanation": "채권 가격은 금리와 반대로 움직입니다.",
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

    q = {
        "question_text": str(data.get("question_text", "")).strip(),
        "options": _coerce_mc_options(data.get("options", [])),
        "answer": str(data.get("answer", "")).strip(),
        "explanation": str(data.get("explanation", "")).strip(),
        "level": (str(data.get("level", "easy")).lower()),
        "weight": int(data.get("weight", 1))
    }
    if q["level"] not in ("easy", "medium"):
        q["level"] = "easy"
    if q["weight"] not in (1, 2):
        q["weight"] = 1 if q["level"] == "easy" else 2
    if not q["question_text"] or len(q["options"]) != 4 or q["answer"] not in {"1","2","3","4"}:
        q = {
            "question_text": "인덱스 펀드의 특징으로 옳지 않은 것은?",
            "options": ["1. 지수 추종", "2. 낮은 보수", "3. 초과수익 직접 추구", "4. 분산투자"],
            "answer": "3",
            "explanation": "인덱스 펀드는 지수 복제를 목표로 한다.",
            "level": "medium" if proficiency >= 6 else "easy",
            "weight": 2 if proficiency >= 6 else 1
        }
    return q

def evaluate_answer(question_text: str, options, answer: str, user_answer: str, proficiency: int):
    if not GOOGLE_API_KEY:
        correct = user_answer == answer
        return {
            "is_correct": correct,
            "feedback": "좋아요! 개념을 잘 이해하고 있어요." if correct else "괜찮아요. 해설을 읽고 개념을 정리해보세요.",
            "delta": 1 if correct else -1
        }

    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content([
        SYSTEM_PROMPT_EVAL,
        USER_PROMPT_EVAL_TMPL.format(
            question_text=question_text,
            options=options,
            answer=answer,
            user_answer=user_answer,
            proficiency=proficiency
        )
    ])
    content = (resp.text or "").strip()
    data = _safe_json_loads(_extract_json(content), {})
    return {
        "is_correct": bool(data.get("is_correct", user_answer == answer)),
        "feedback": str(data.get("feedback", "")).strip() or ("정답입니다!" if user_answer == answer else "오답입니다."),
        "delta": int(data.get("delta", 1 if user_answer == answer else -1))
    }

# ── Sidebar status ────────────────────────────────────────────────────────────
def render_sidebar_status():
    with st.sidebar:
        st.markdown("### 📊 진행 요약")
        prog = (st.session_state.quiz_index) / TOTAL_QUESTIONS if TOTAL_QUESTIONS else 0
        st.progress(prog)
        st.metric("진행", f"{st.session_state.quiz_index}/{TOTAL_QUESTIONS}")
        st.metric("획득 점수", f"{st.session_state.quiz_score}/{st.session_state.total_weight or 1}")
        st.metric("프로피션시(0~10)", st.session_state.proficiency)
        if st.session_state.user_keywords:
            st.caption("관심사")
            st.markdown("".join([f"<span class='tag'>{t}</span>" for t in st.session_state.user_keywords]), unsafe_allow_html=True)

# ── 4. 반복 구조 + UI 엔진 ───────────────────────────────────────────────────
def render_quiz_section():
    inject_styles()
    init_quiz_state()
    render_sidebar_status()

    if not st.session_state.get("quiz_started", False):
        return

    # 최초 진입: 공통문항 적재 + 사용자 관심사 로딩
    if not st.session_state.quiz_questions:
        st.session_state.quiz_questions = load_common_questions()
        st.session_state.quiz_index = 0
        st.session_state.quiz_score = 0
        st.session_state.total_weight = sum(q.get("weight",1) for q in st.session_state.quiz_questions)
        st.session_state.proficiency = 5
        st.session_state.wrong_notes = []
        st.session_state.history = []
        st.session_state.generated_count = 0

        # 🔹 사용자 관심사 로딩
        user = st.session_state.get("user")
        user_id = user.get("user_id") or user.get("id") if user else None
        st.session_state.user_keywords = fetch_user_keywords(user_id) if user_id else []

    # Header
    st.markdown('<div class="quiz-top-spacer"></div>', unsafe_allow_html=True)  # 🔧 상단 여백
    mode = "공통문제" if st.session_state.quiz_index < 3 else "LLM 생성"
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
    st.progress((st.session_state.quiz_index + 0) / TOTAL_QUESTIONS)

    # 4~10번: 필요 시 LLM 생성
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
        answer_type = "mc" if options else "ox"
        key_ans = f"selected_answer_{st.session_state.quiz_index}"

        if key_ans not in st.session_state:
            st.session_state[key_ans] = None

        if answer_type == "ox":
            col = st.columns(2)
            if col[0].button("⭕ O", key=f"btn_o_{st.session_state.quiz_index}", use_container_width=True):
                st.session_state[key_ans] = "o"; st.rerun()
            if col[1].button("❌ X", key=f"btn_x_{st.session_state.quiz_index}", use_container_width=True):
                st.session_state[key_ans] = "x"; st.rerun()
        else:
            st.write("선택지 중 하나를 고르세요:")
            st.session_state[key_ans] = st.radio(
                label=f"Q{st.session_state.quiz_index + 1} 선택지",   # 접근성 확보
                options=options,
                index=None,
                key=f"radio_q{st.session_state.quiz_index}",
                label_visibility="collapsed"                           # 화면에서는 숨김
            )

        selected_answer = st.session_state[key_ans]

        # Next 버튼
        next_disabled = selected_answer is None
        if st.button("다음 ▶", type="primary", disabled=next_disabled, use_container_width=True, key=f"next_{st.session_state.quiz_index}"):
            user_answer = (selected_answer or "").strip().lower()
            correct = quiz["answer"].strip().lower()
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
                answer=quiz["answer"],
                user_answer=user_answer.upper() if answer_type == "mc" else user_answer.upper(),
                proficiency=st.session_state.proficiency
            )
            st.session_state.proficiency = max(0, min(10, st.session_state.proficiency + int(eval_res.get("delta", 0))))

            # 점수/오답 반영 (UI 출력은 하지 않음)
            is_correct = (user_answer == correct)
            if is_correct:
                st.session_state.quiz_score += weight
            else:
                st.session_state.wrong_notes.append(quiz["question_text"])

            # 히스토리 저장
            st.session_state.history.append({
                "question_text": quiz["question_text"],
                "options": options,
                "answer": quiz["answer"],
                "user_answer": user_answer.upper(),
                "correct": is_correct,
                "weight": weight,
                "proficiency_after": st.session_state.proficiency
            })

            # ✅ 피드백/해설/LLM평가는 챗봇 메시지로만 전송
            feedback_text = "정답입니다! ✅" if is_correct else f"오답입니다 ❌ . 정답은 {correct}입니다."
            full_feedback = f"{feedback_text}\n해설: {explanation or '해설이 제공되지 않았어요.'}"
            if eval_res.get("feedback"):
                full_feedback += f"\nLLM 평가: {eval_res['feedback']}"
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": full_feedback
            })

            # 다음 문항으로
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

        # 왼쪽 퀴즈 패널 결과 카드
        render_result_card(score, total_weight, level, user_name)

        # 다시 시작/종료 선택 버튼
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔁 다시 시작", use_container_width=True):
                # 상태 리셋 후 공통문제부터 재시작
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
                # 결과 화면만 남기고 종료
                st.session_state.quiz_started = False
                st.session_state.quiz_completed = True
                st.session_state.quiz_index = 0
                st.session_state.quiz_score = 0
                st.rerun()

def render():
    """오늘의 퀴즈 페이지 엔트리 포인트."""
    inject_styles()
    init_quiz_state()

    # 채팅 패널 전달용 메시지 버퍼 보장 (위에서 사용 중)
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 헤더
    st.title("🧠 오늘의 퀴즈")
    st.caption("공통문항 + LLM 맞춤 문항으로 금융 지식을 빠르게 점검합니다.")

    # 상태/컨트롤 영역
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
            else:
                if st.button("⏸ 중단", use_container_width=True):
                    # 진행 중단(결과 저장은 하지 않음)
                    st.session_state.quiz_started = False
                    st.session_state.quiz_index = 0
                    st.session_state.quiz_score = 0
                    st.session_state.total_weight = 0
                    st.rerun()
        with c2:
            if st.button("🔄 초기화", use_container_width=True):
                # 모든 상태 리셋
                for key in [
                    "quiz_questions","quiz_index","quiz_score","total_weight",
                    "proficiency","wrong_notes","history","generated_count",
                    "quiz_started","quiz_completed","completion_announced",
                    "user_keywords"
                ]:
                    st.session_state.pop(key, None)
                st.rerun()

    # 안내 카드 (시작 전만 표시)
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
        return

    # 실제 퀴즈 섹션 렌더링
    render_quiz_section()
