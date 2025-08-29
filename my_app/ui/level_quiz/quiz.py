import os, json, uuid, time, streamlit as st
from my_app.quiz_core.constants import TOTAL_QUESTIONS, COMMON_COUNT,MAX_CONTEXT_TURNS,ROLLING_SUMMARY_MAX_CHARS 
from my_app.quiz_core.logic import (
    classify_level, _aggregate_session, _rank_topics, _build_summary_from_agg,
    generate_next_question, evaluate_answer, generate_level_summary_llm,
    save_generated_question, save_result
)
from ui.level_quiz.state import init_quiz_state, ensure_user_keywords, load_common_questions
from ui.level_quiz.ui_utils import inject_styles, render_result_card, render_sidebar_status
from my_app.quiz_core.services import update_rolling_summary
from concurrent.futures import ThreadPoolExecutor, as_completed

# (있으면) 우측 챗봇 샘플
try:
    from ui.chatbot.chatbot_sample import generate_simple_response, stream_data
except Exception:
    def generate_simple_response(x): return "도움이 필요하신 내용을 말씀해 주세요!"
    def stream_data(x): yield x

def parallel_eval_and_qgen(
    quiz: dict,
    *,
    options: list[str],
    user_answer_text: str,
    answer_type: str,
    proficiency: int,
    score: int,
    total_weight: int,
    wrong_notes: list,
    history: list,
    keywords: list,
    do_qgen: bool = True,
):
    """
    반환 형식 고정:
    (eval_res: dict, next_question: dict|None, user_answer: str, correct: str, weight: int, eval_dt: float, qgen_dt: float)
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # --- 입력 정규화 ---
    options_list = options if isinstance(options, list) else []
    question_text = str(quiz.get("question_text", "") or "")
    correct = str((quiz.get("answer") or "")).strip()
    level = quiz.get("level", "easy")
    weight = int(quiz.get("weight", 1))

    # user_answer: mcq면 "1"~"4", ox면 "O"/"X"
    if answer_type == "mc":
        try:
            idx = options_list.index(user_answer_text)
            user_answer = str(idx + 1)
        except Exception:
            user_answer = "0"
    else:
        user_answer = (user_answer_text or "").strip()

    def _safe_eval():
        t0 = time.perf_counter()
        try:
            res = evaluate_answer(
                question_text=question_text,
                options=options_list,
                answer=correct,
                user_answer=user_answer,
                level=level,
                proficiency=proficiency
            )
            if not isinstance(res, dict):
                res = {"delta": 0, "feedback": "", "note": "non-dict eval result"}
            return res, time.perf_counter() - t0
        except Exception as e:
            return {"delta": 0, "feedback": "", "error": f"eval_error: {type(e).__name__}: {e}"}, time.perf_counter() - t0

    def _safe_qgen(cur_prof: int, cur_score: int, cur_total_weight: int):
        t0 = time.perf_counter()
        try:
            nq = generate_next_question(
                proficiency=cur_prof,
                score=cur_score,
                max_score=cur_total_weight or 1,
                wrong_notes=wrong_notes if isinstance(wrong_notes, list) else [],
                history=history if isinstance(history, list) else [],
                keywords=keywords if isinstance(keywords, list) else []
            )
            if isinstance(nq, dict):
                nq.setdefault("question_text", "")
                nq.setdefault("answer", "")
                nq.setdefault("options", [])
                nq.setdefault("question_type", "mcq" if nq.get("options") else "ox")
                nq.setdefault("weight", 1)
            else:
                nq = None
            return nq, time.perf_counter() - t0
        except Exception:
            return None, time.perf_counter() - t0

    # --- do_qgen=False: 채점만 동기 실행 ---
    if not do_qgen:
        eval_res, eval_dt = _safe_eval()
        return eval_res, None, user_answer, correct, weight, eval_dt, 0.0

    # --- do_qgen=True: 채점 + 생성 병렬 ---
    eval_res, eval_dt = None, 0.0
    first_q, qgen_dt = None, 0.0
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_eval = ex.submit(_safe_eval)
        fut_qgen = ex.submit(_safe_qgen, proficiency, score, total_weight)
        for fut in as_completed([fut_eval, fut_qgen]):
            if fut is fut_eval:
                try:
                    eval_res, eval_dt = fut.result()
                except Exception:
                    eval_res, eval_dt = {"delta": 0, "feedback": "", "error": "eval_future_error"}, 0.0
            else:
                try:
                    first_q, qgen_dt = fut.result()
                except Exception:
                    first_q, qgen_dt = None, 0.0

    if not isinstance(eval_res, dict):
        eval_res = {"delta": 0, "feedback": "", "error": "eval_none"}

    # 델타 기반 리롤
    try:
        delta = int(eval_res.get("delta", 0))
    except Exception:
        delta = 0
    new_prof = max(0, min(10, proficiency + delta))
    need_reroll = abs(delta) >= 2 or first_q is None

    if need_reroll:
        bumped = score + (weight if (user_answer.lower() == correct.lower()) else 0)
        second_q, qgen_dt2 = _safe_qgen(new_prof, bumped, total_weight)
        if second_q is not None:
            return eval_res, second_q, user_answer, correct, weight, eval_dt, qgen_dt2
        # 리롤 실패 시 first_q라도 반환
        return eval_res, first_q, user_answer, correct, weight, eval_dt, qgen_dt

    return eval_res, first_q, user_answer, correct, weight, eval_dt, qgen_dt


def _ensure_list_session_key(key: str):
    if key not in st.session_state or not isinstance(st.session_state[key], list):
        st.session_state[key] = []

def _ensure_number_session_key(key: str, default: int | float = 0):
    if key not in st.session_state or not isinstance(st.session_state[key], (int, float)):
        st.session_state[key] = default

def render_quiz_section():
    inject_styles()
    init_quiz_state()
    ensure_user_keywords()

    if not st.session_state.get("quiz_started", False):
        return

    # ── 세션키 타입 가드 ──────────────────────────────────────────────
    _ensure_list_session_key("quiz_questions")
    _ensure_number_session_key("quiz_index", 0)
    _ensure_number_session_key("quiz_score", 0)
    _ensure_number_session_key("proficiency", 5)
    _ensure_list_session_key("wrong_notes")
    _ensure_list_session_key("history")
    _ensure_number_session_key("generated_count", 0)
    _ensure_number_session_key("total_weight", 0)

    # 최초 진입 시(빈 상태) 공통문항 적재
    if len(st.session_state.quiz_questions) == 0 and st.session_state.quiz_index == 0:
        # 공통문항 append
        for q in load_common_questions():
            st.session_state.quiz_questions.append(q)

    # total_weight 동기화 (세션/로컬)
    total_weight = sum(q.get("weight", 1) for q in st.session_state.quiz_questions)
    st.session_state.total_weight = total_weight

    # 사이드바 상태
    render_sidebar_status(
        total_questions=TOTAL_QUESTIONS,
        score=st.session_state.quiz_score,
        total_weight=total_weight,
        proficiency=st.session_state.proficiency,
        user_keywords=st.session_state.user_keywords,
    )

    st.markdown('<div class="quiz-top-spacer"></div>', unsafe_allow_html=True)
    mode = "공통문제" if st.session_state.quiz_index < COMMON_COUNT else "LLM 생성"
    st.markdown(f"""
    <div class="quiz-header">
    <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
        <div><strong>💡 금융 퀴즈</strong></div>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
        <span class="badge mode">🧭 {mode}</span>
        <span class="badge score">🏆 점수 {st.session_state.quiz_score}/{total_weight or 1}</span>
        <span class="badge">🧠 Proficiency {st.session_state.proficiency}/10</span>
        </div>
    </div>
    </div>
    """, unsafe_allow_html=True)
    st.progress((st.session_state.quiz_index) / (TOTAL_QUESTIONS or 1))

    # LLM 생성부: 현재 인덱스가 꼬리를 물면 새 문항 생성
    while (
        st.session_state.quiz_index >= COMMON_COUNT
        and len(st.session_state.quiz_questions) < TOTAL_QUESTIONS
        and st.session_state.quiz_index >= len(st.session_state.quiz_questions)
    ):
        _t0 = time.perf_counter()
        _next_q_no = len(st.session_state.quiz_questions) + 1

        q = generate_next_question(
            proficiency=st.session_state.proficiency,
            score=st.session_state.quiz_score,
            max_score=total_weight or 1,
            wrong_notes=st.session_state.wrong_notes,
            history=st.session_state.history,
            keywords=st.session_state.user_keywords
        )

        dt = time.perf_counter() - _t0
        _ensure_number_session_key("timing_qgen_total", 0.0)
        _ensure_number_session_key("timing_qgen_n", 0)
        st.session_state.timing_qgen_total += dt
        st.session_state.timing_qgen_n += 1
        print(f"[QGEN] Q{_next_q_no}: {dt:.2f}s")

        # ── append는 단 한 번만 ──
        if isinstance(q, dict) and q.get("question_text") and q.get("answer"):
            _ensure_list_session_key("quiz_questions")
            st.session_state.quiz_questions.append(q)
            st.session_state.generated_count += 1
        else:
            print("[WARN] invalid qgen result; skip")
            break

        # 총 가중치 갱신
        total_weight = sum(q_.get("weight", 1) for q_ in st.session_state.quiz_questions)
        st.session_state.total_weight = total_weight


    # 생성셋 저장(1회)
    if (
        len(st.session_state.quiz_questions) == TOTAL_QUESTIONS 
        and not st.session_state.get("generated_saved", False)
    ):
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
            if st.session_state.get("processing"): 
                st.stop()
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
            # 현재 문항 인덱스(0-based)
            cur_idx = st.session_state.quiz_index
            
            # 다음 문항 생성이 필요한가?
            need_next_q = (cur_idx >= COMMON_COUNT) and (cur_idx < TOTAL_QUESTIONS - 1)

            # --- 병렬: 채점 + 다음문제 생성 ---
            t0_total = time.perf_counter()
            try:
                eval_res, next_q, user_answer, correct, weight, eval_dt, qgen_dt = parallel_eval_and_qgen(
                    quiz=quiz,
                    options=options,
                    user_answer_text=(selected_answer or "").strip(),
                    answer_type=answer_type,
                    proficiency=st.session_state.proficiency,
                    score=st.session_state.quiz_score,
                    total_weight=total_weight,
                    wrong_notes=st.session_state.wrong_notes,
                    history=st.session_state.history,
                    keywords=st.session_state.user_keywords,
                    do_qgen=need_next_q,   # ← 마지막 문제에서는 False
                )
            except Exception as e:
                st.session_state.processing = False
                raise RuntimeError(f"채점 LLM 호출 실패: {type(e).__name__}: {e}")
            
            total_dt = time.perf_counter() - t0_total  # ← 한 문제당 전체 소요 시간
            print(f"[PER-QUESTION TOTAL] {total_dt:.2f}s (eval {eval_dt:.2f}s + qgen {qgen_dt:.2f}s)")

            # 타이밍 누적
            _ensure_number_session_key("timing_eval_total", 0.0)
            _ensure_number_session_key("timing_eval_n", 0)
            _ensure_number_session_key("timing_qgen_total", 0.0)
            _ensure_number_session_key("timing_qgen_n", 0)
            if eval_dt and eval_dt > 0:
                st.session_state.timing_eval_total += eval_dt
                st.session_state.timing_eval_n += 1
            if qgen_dt and qgen_dt > 0:
                st.session_state.timing_qgen_total += qgen_dt
                st.session_state.timing_qgen_n += 1

            avg_eval = (st.session_state.timing_eval_total / st.session_state.timing_eval_n) if st.session_state.timing_eval_n else 0.0
            avg_qgen = (st.session_state.timing_qgen_total / st.session_state.timing_qgen_n) if st.session_state.timing_qgen_n else 0.0

            _ensure_number_session_key("timing_summary", 0.0)
            print(
                f"[TIMING SUMMARY] QGEN total {st.session_state.timing_qgen_total:.2f}s, "
                f"avg {avg_qgen:.2f}s | EVAL total {st.session_state.timing_eval_total:.2f}s, "
                f"avg {avg_eval:.2f}s | SUMMARY {st.session_state.timing_summary:.2f}s"
            )

            # --- 평가 결과 반영/피드백/히스토리 ---
            is_correct = (user_answer.strip().lower() == correct.strip().lower())
            delta = int(eval_res.get("delta", 0)) if isinstance(eval_res, dict) else (1 if is_correct else -1)
            feedback_text_model = (eval_res.get("feedback") if isinstance(eval_res, dict) else "") or ""
            st.session_state.proficiency = max(0, min(10, st.session_state.proficiency + delta))
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
            full_feedback = f"{feedback_text}\n{feedback_text_model}".strip()
            _ensure_list_session_key("messages")
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": full_feedback
            })

            #  마지막 문제 전(0~8)이고, 공통 이후부터만 next_q 넣기
            if need_next_q and next_q and isinstance(next_q, dict) and len(st.session_state.quiz_questions) < TOTAL_QUESTIONS:
                st.session_state.quiz_questions.append(next_q)
                # total_weight 갱신
                total_weight = sum(q_.get("weight", 1) for q_ in st.session_state.quiz_questions)
                st.session_state.total_weight = total_weight

            st.session_state.processing = False
            st.session_state.quiz_index += 1
            st.rerun()

    else:
        # 완료
        total_weight = sum(q.get("weight", 1) for q in st.session_state.quiz_questions)
        st.session_state.total_weight = total_weight
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

        # 타입 정규화
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

        # 재보정 안전막 (형태 보장)
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
            _ensure_list_session_key("messages")
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": "퀴즈를 완료하셨군요! 이제 다음 단계를 진행할게요"
            })
            st.session_state.completion_announced = True

        result_data = save_result(score, level_eng, level_summary)
        user_name = (result_data or {}).get("user_name")

        render_result_card(score, total_weight, level_eng, user_name)
        agg = _aggregate_session(
            st.session_state.history,
            total_weight,
            st.session_state.user_keywords
        )

        overall_pct = int(agg["overall_accuracy"] * 100)
        weighted = agg["weighted_score"]

        # evidence 일관성 확보
        if isinstance(level_summary, dict):
            level_summary["evidence"] = {
                "overall_accuracy": agg["overall_accuracy"],
                "weighted_score": agg["weighted_score"],
                "strong_topics": [
                    {"topic": n, "accuracy": round(c/t, 2) if t else 0.0, "n": t}
                    for n, t, c, _ in _rank_topics(agg["topic_stats"])[0]
                ],
                "weak_topics": [
                    {"topic": n, "accuracy": round(c/t, 2) if t else 0.0, "n": t}
                    for n, t, c, _ in _rank_topics(agg["topic_stats"])[1]
                ],
            }

        # 요약 문장 안전 추출
        if isinstance(level_summary, dict):
            sents = list(level_summary.get("summary_sentences", []))
        elif isinstance(level_summary, list):
            sents = [str(x) for x in level_summary]
        else:
            sents = []

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
                # 안전 초기화
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
