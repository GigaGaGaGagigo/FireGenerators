import os, json, uuid, time, streamlit as st
from my_app.quiz_core.constants import TOTAL_QUESTIONS, COMMON_COUNT
from my_app.quiz_core.logic import (
    classify_level, _aggregate_session, _rank_topics, _build_summary_from_agg,
    generate_next_question, evaluate_answer, generate_level_summary_llm,
    save_generated_question, save_result
)
from ui.level_quiz.state import init_quiz_state, ensure_user_keywords, load_common_questions
from ui.level_quiz.ui_utils import inject_styles, render_result_card, render_sidebar_status

# (있으면) 우측 챗봇 샘플
try:
    from ui.chatbot.chatbot_sample import generate_simple_response, stream_data
except Exception:
    def generate_simple_response(x): return "도움이 필요하신 내용을 말씀해 주세요!"
    def stream_data(x): yield x

def render_quiz_section():
    inject_styles()
    init_quiz_state()
    ensure_user_keywords()
    render_sidebar_status(TOTAL_QUESTIONS)

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
        _t0 = time.perf_counter()
        _next_q_no = len(st.session_state.quiz_questions) + 1

        q = generate_next_question(
            proficiency=st.session_state.proficiency,
            score=st.session_state.quiz_score,
            max_score=st.session_state.total_weight or 1,
            wrong_notes=st.session_state.wrong_notes,
            history=st.session_state.history,
            keywords=st.session_state.user_keywords
        )

        dt = time.perf_counter() - _t0
        st.session_state.timing_qgen_total += dt
        st.session_state.timing_qgen_n += 1
        print(f"[QGEN] Q{_next_q_no}: {dt:.2f}s")

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

            _t0 = time.perf_counter()
            eval_res = evaluate_answer(
                question_text=quiz["question_text"],
                options=options if options else [],
                answer=correct,
                user_answer=user_answer,
                level=quiz.get("level", "easy"),
                proficiency=st.session_state.proficiency
            )
            dt = time.perf_counter() - _t0
            st.session_state.timing_eval_total += dt
            st.session_state.timing_eval_n += 1
            print(f"[EVAL] Q{st.session_state.quiz_index + 1}: {dt:.2f}s")
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
            full_feedback = f"{feedback_text}\n{eval_res.get('feedback','')}".strip()

            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": full_feedback
            })

            st.session_state.processing = False
            st.session_state.quiz_index += 1
            st.rerun()

    else:
        # 완료
        total_weight = st.session_state.total_weight
        score = st.session_state.quiz_score
        level_eng = classify_level(score, total_weight)  # Beginner/Intermediate/Advanced
        level_map = {"Beginner": "초급", "Intermediate": "중급", "Advanced": "상급"}
        level_kor = level_map.get(level_eng, "중급")

        _t0 = time.perf_counter()
        level_summary = generate_level_summary_llm(
            level_eng=level_eng,
            history=st.session_state.history,
            total_weight=total_weight,
            user_keywords=st.session_state.user_keywords
        )
        st.session_state.timing_summary = time.perf_counter() - _t0
        print(f"[SUMMARY] built in {st.session_state.timing_summary:.2f}s")
        if isinstance(level_summary, list):
            level_summary = {
                "level": level_kor,
                "summary_sentences": [str(x) for x in level_summary][:3] or ["요약 준비 중", "요약 준비 중", "요약 준비 중"],
                "evidence": None,
                "next_actions": None,
            }
        elif not isinstance(level_summary, dict):
            level_summary = {
                "level": level_kor,
                "summary_sentences": ["요약 준비 중", "요약 준비 중", "요약 준비 중"],
                "evidence": None,
                "next_actions": None,
            }


        model_version = "gpt5_chatcompletions"
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

        # 타입 정규화 (혹시 리스트로 오더라도 방어)
        if isinstance(level_summary, list):
            level_summary = {
                "level": level_kor,
                "summary_sentences": [str(x) for x in level_summary][:3] or ["요약 준비 중","요약 준비 중","요약 준비 중"],
                "evidence": None, "next_actions": None
            }
        elif not isinstance(level_summary, dict):
            level_summary = {
                "level": level_kor,
                "summary_sentences": ["요약 준비 중","요약 준비 중","요약 준비 중"],
                "evidence": None, "next_actions": None
            }

        if not st.session_state.get("completion_announced", False):
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": "퀴즈를 완료하셨군요! 이제 다음 단계를 진행할게요"
            })
            st.session_state.completion_announced = True

        result_data = save_result(score, level_eng, level_summary)
        user_name = (result_data or {}).get("user_name")

        render_result_card(score, total_weight, level_eng, user_name)

        ev = (level_summary.get("evidence", {}) if isinstance(level_summary, dict) else {}) or {}
        overall_pct = int((ev.get("overall_accuracy") or 0) * 100)
        weighted = ev.get("weighted_score", 0)
        sents = (level_summary.get('summary_sentences', []) if isinstance(level_summary, dict) else [])
        s1, s2, s3 = (sents + ["", "", ""])[:3]

        st.markdown(f"""
        <div style="border:1px solid rgba(148,163,184,.28);border-radius:16px;padding:16px;margin-top:10px;background:#fff;">
          <div style="font-weight:800;margin-bottom:6px;">🌟 금융 지식 요약 ({level_summary.get('level','')})</div>
          <ul style="margin:0 0 8px 18px;line-height:1.55;">
            <li>{s1}</li>
            <li>{s2}</li>
            <li>{s3}</li>
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
                st.session_state.timing_qgen_total = 0.0
                st.session_state.timing_qgen_n = 0
                st.session_state.timing_eval_total = 0.0
                st.session_state.timing_eval_n = 0
                st.session_state.timing_summary = 0.0
                st.rerun()
        with c2:
            if st.button("✅ 완료", use_container_width=True):
                st.session_state.quiz_started = False
                st.session_state.quiz_completed = True
                st.session_state.quiz_index = 0
                st.session_state.quiz_score = 0
                st.rerun()


def render():
    for k, v in {
        "timing_qgen_total": 0.0,
        "timing_qgen_n": 0,
        "timing_eval_total": 0.0,
        "timing_eval_n": 0,
        "timing_summary": 0.0,
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v
    inject_styles()
    init_quiz_state()
    ensure_user_keywords()

    # 메시지 보정
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

    st.title("🧠 오늘의 퀴즈")
    st.caption("공통문항 + LLM 맞춤 문항으로 금융 지식을 빠르게 점검합니다.")

    left_screen, right_screen = st.columns([0.55, 0.45], border=True)
    # 총합/평균 계산
    qgen_n = st.session_state.timing_qgen_n or 1
    eval_n = st.session_state.timing_eval_n or 1
    qgen_total = st.session_state.timing_qgen_total
    eval_total = st.session_state.timing_eval_total
    summary_sec = st.session_state.timing_summary

    print(
        "[TIMING SUMMARY] "
        f"QGEN total {qgen_total:.2f}s, avg {qgen_total/qgen_n:.2f}s "
        f"| EVAL total {eval_total:.2f}s, avg {eval_total/eval_n:.2f}s "
        f"| SUMMARY {summary_sec:.2f}s"
    )
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

        # 챗 입력
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

# Streamlit 엔트리
if __name__ == "__main__":
    render()
