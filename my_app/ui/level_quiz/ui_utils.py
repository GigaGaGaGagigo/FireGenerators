import streamlit as st
from typing import Optional

# Style 
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

def render_sidebar_status(TOTAL_QUESTIONS: Optional[int] = None):
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