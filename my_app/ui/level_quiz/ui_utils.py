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
    import streamlit as st

    lvl_key = (level or "").strip().lower()
    pct = round((score / (total_weight or 1)) * 100)

    # ----- 단계별 스타일 / 메시지 -----
    lvl_map = {
        "beginner": {
            "label": "Beginner",
            "title": "1단계",
            "color": "#EF4444",
            "bg": "linear-gradient(135deg, rgba(239,68,68,.9), rgba(239,68,68,.7))",
            "guide": "기초 금융 지식이 더 필요합니다. 기본 개념부터 차근차근 학습해보세요."
        },
        "intermediate": {
            "label": "Intermediate",
            "title": "2단계",
            "color": "#F59E0B",
            "bg": "linear-gradient(135deg, rgba(245,158,11,.9), rgba(245,158,11,.7))",
            "guide": "중급 수준의 금융 지식을 보유하고 있습니다. 분산 투자, 리스크 관리 개념을 강화해보세요."
        },
        "advanced": {
            "label": "Advanced",
            "title": "3단계",
            "color": "#10B981",
            "bg": "linear-gradient(135deg, rgba(16,185,129,.9), rgba(16,185,129,.7))",
            "guide": "높은 수준의 금융 지식을 보유하고 있습니다. 심화된 자산배분 전략과 FIRE 개념을 실천해보세요."
        }
    }
    theme = lvl_map.get(lvl_key, lvl_map["intermediate"])
    name_html = f"<span style='opacity:.7'>({user_name})</span>" if user_name else ""

    st.balloons()
    st.markdown(f"""
    <div style="border-radius:18px;overflow:hidden;
                box-shadow:0 4px 14px rgba(0,0,0,.15);margin:16px 0;">
      <!-- 상단 큰 단계 표시 -->
      <div style="background:{theme['bg']};padding:28px;text-align:center;color:white;">
        <div style="font-size:2.2rem;font-weight:900;">{theme['title']}</div>
        <div style="font-size:1.3rem;margin-top:4px;">{theme['label']} 단계</div>
        <div style="margin-top:8px;opacity:.9;">🎉 금융 퀴즈 완료 {name_html}</div>
      </div>

      <!-- 진행 현황 -->
      <div style="padding:20px;background:#f9fafb;">
        <div style="font-weight:700;margin-bottom:10px;">단계별 진행 현황</div>
        <div style="display:flex;justify-content:space-between;gap:8px;margin:10px 0;">
          <div style="flex:1;text-align:center;">
            <div style="font-size:1.5rem;">1️⃣</div>
            <div style="font-size:.9rem;">Beginner</div>
          </div>
          <div style="flex:1;text-align:center;">
            <div style="font-size:1.5rem;">2️⃣</div>
            <div style="font-size:.9rem;">Intermediate</div>
          </div>
          <div style="flex:1;text-align:center;">
            <div style="font-size:1.5rem;">3️⃣</div>
            <div style="font-size:.9rem;">Advanced</div>
          </div>
        </div>
        <div style="margin-top:6px;background:rgba(148,163,184,.3);height:10px;border-radius:999px;overflow:hidden;">
          <div style="width:{pct}%;height:100%;background:{theme['color']};"></div>
        </div>
        <div style="margin-top:6px;opacity:.85;">점수 {score}/{total_weight} · 정답률 {pct}%</div>
      </div>

      <!-- 상세 가이드 -->
      <div style="padding:20px;background:white;">
        <div style="font-weight:700;margin-bottom:8px;">📖 현재 단계 상세 가이드</div>
        <div style="line-height:1.55;opacity:.9;">{theme['guide']}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)



def render_sidebar_status(total_questions: int, score: int, total_weight: int, proficiency: int, user_keywords: list[str]):
    with st.sidebar:
        st.markdown("### 📊 진행 요약")
        prog = (st.session_state.quiz_index) / (total_questions or 1)
        st.progress(min(1.0, prog))
        st.metric("진행", f"{st.session_state.quiz_index}/{total_questions}")
        st.metric("획득 점수", f"{score}/{total_weight or 1}")
        st.metric("숙련도(0~10)", proficiency)
        if user_keywords:
            st.caption("관심사")
            st.markdown("".join([f"<span class='tag'>{t}</span>" for t in user_keywords]), unsafe_allow_html=True)
        if "llm_error" in st.session_state:
            st.divider()
            st.caption("🛠 디버그")
            st.code(st.session_state["llm_error"])
