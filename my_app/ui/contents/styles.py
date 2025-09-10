# ================== 
# UI 스타일 모듈
# ================== 
import streamlit as st


def apply_global_styles():
    """전역 스타일 적용"""
    st.markdown("""
    <style>
    .main .block-container { 
        padding-top: 2rem;
        max-width: 1200px;
    }

    /* 프로필 카드 */
    .profile-card {
        background: #FFFFFF;
        border-radius: 12px;
        padding: 1rem;
        margin: 1rem 0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border-left: 4px solid #999; 
        transition: all 0.2s ease;
    }
    .profile-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 18px rgba(0,0,0,0.12);
    }

    /* 버튼 (주황색 hover, 테두리 제거) */
    .stButton > button {
        background: #f0f0f0 !important;
        color: #333 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.5rem 1.2rem !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }
    .stButton > button:hover {
        background: #ff9800 !important;
        color: #fff !important;
    }

    /* 쉬운 설명 텍스트 */
    .ai-explanation {
        background: #f9f9f9;
        border-left: 4px solid #ff9800;
        border-radius: 6px;
        padding: 1rem;
        margin: 0.5rem 0;
        font-size: 1rem; /* 글씨 크기 키움 */
        line-height: 1.6;
    }

    /* 태그: 옅은 노란색 */
    .tag {
        background: #fff9c4;
        color: #333;
        padding: 0.3rem 0.7rem;
        border-radius: 12px;
        font-size: 0.8rem;
        margin-right: 0.3rem;
        display: inline-block;
    }

    /* 콘텐츠 카드 */
    .content-card {
        background: #fff;
        border-radius: 12px;
        padding: 1rem;
        margin: 1rem 0;
        border: 1px solid #ddd;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }

    /* 관리자 뷰 스타일 */
    .admin-metric {
        background: #fff;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border: 1px solid #eee;
    }

    .admin-metric h4 {
        color: #666;
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }

    .admin-metric p {
        color: #ff9800;
        font-weight: bold;
        font-size: 1.1rem;
        margin: 0;
    }

    /* 차트 컨테이너 */
    .chart-container {
        background: #fff;
        border-radius: 8px;
        padding: 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border: 1px solid #eee;
        margin: 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)


def apply_quiz_styles():
    """퀴즈 관련 스타일 적용"""
    st.markdown("""
    <style>
    .quiz-card {
        border: 1px solid rgba(148,163,184,.28);
        border-radius: 16px;
        padding: 18px;
        margin: 10px 0 14px 0;
        background: rgba(2,6,23,.02);
        height: 150px;
        overflow-y: auto;
    }
    .quiz-header {
        background: linear-gradient(135deg, rgba(99,102,241,.10), rgba(16,185,129,.10));
        border: 1px solid rgba(148,163,184,.22);
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 8px;
        font-weight: 600;
        font-size: 0.95rem;
    }
    .quiz-content {
        line-height: 1.6;
        font-size: 0.9rem;
        color: #374151;
    }
    </style>
    """, unsafe_allow_html=True)


def get_content_card_style(title: str) -> str:
    """콘텐츠 카드 HTML 스타일 반환"""
    return f'<div class="content-card"><h4>{title}</h4></div>'


def get_ai_explanation_style(explanation: str) -> str:
    """AI 설명 스타일 반환"""
    return f'<div class="ai-explanation">{explanation}</div>'


def get_profile_card_style(content: str, height: int = 385) -> str:
    """프로필 카드 스타일 반환"""
    return f'<div class="profile-card" style="height: {height}px;">{content}</div>'


def get_quiz_card_style(header: str, content: str) -> str:
    """퀴즈 카드 스타일 반환"""
    return f"""
    <div class="quiz-header">{header}</div>
    <div class="quiz-card"><div class="quiz-content">{content}</div></div>
    """


def get_tag_style(tags: list, max_tags: int = 4) -> str:
    """태그 스타일 HTML 반환"""
    if not tags:
        return ""
    display_tags = tags[:max_tags]
    tag_html = ''.join([f'<span class="tag">#{t}</span>' for t in display_tags])
    return tag_html


def get_metric_card_style(title: str, value: str, subtitle: str = "") -> str:
    """메트릭 카드 스타일 반환"""
    return f"""
    <div style="background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid #e9ecef;">
        <h4 style="color: #495057; margin: 0; font-size: 14px; font-weight: 600;">{title}</h4>
        <p style="font-size: 28px; font-weight: 700; margin: 8px 0; color: #212529;">{value}</p>
        <small style="color: #6c757d;">{subtitle}</small>
    </div>
    """


def get_process_flow_style() -> str:
    """프로세스 플로우 차트 스타일 반환"""
    return """
    <div style="background: #f8f9fa; padding: 25px; border-radius: 12px; margin: 15px 0; border: 1px solid #e9ecef;">
        <h4 style="text-align: center; color: #495057; margin-bottom: 20px; font-weight: 600;">📊 추천 프로세스 플로우</h4>
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <div style="background: white; padding: 15px; border-radius: 8px; margin: 5px; flex: 1; text-align: center; min-width: 160px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 4px solid #6c757d;">
                <strong style="color: #495057;">1️⃣ 후보군 수집</strong><br>
                <small style="color: #6c757d;">감정룰 + 벡터서치 + 기본룰</small>
            </div>
            <div style="font-size: 20px; color: #6c757d; margin: 0 10px;">→</div>
            <div style="background: white; padding: 15px; border-radius: 8px; margin: 5px; flex: 1; text-align: center; min-width: 160px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 4px solid #6c757d;">
                <strong style="color: #495057;">2️⃣ 수치 리랭킹</strong><br>
                <small style="color: #6c757d;">α, β, γ 가중치 적용</small>
            </div>
            <div style="font-size: 20px; color: #6c757d; margin: 0 10px;">→</div>
            <div style="background: white; padding: 15px; border-radius: 8px; margin: 5px; flex: 1; text-align: center; min-width: 160px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 4px solid #6c757d;">
                <strong style="color: #495057;">3️⃣ LLM 리랭킹</strong><br>
                <small style="color: #6c757d;">GPT-4o-mini 컨텍스트</small>
            </div>
        </div>
    </div>
    """


def get_celebration_style() -> str:
    """학습 완료 축하 메시지 스타일 반환"""
    return """
    <div style='text-align: center; padding: 20px;'>
        <h2 style='color: #ff9800;'>🏆 축하합니다! 🏆</h2>
        <p style='font-size: 18px; color: #333;'>오늘의 학습을 모두 완주하셨네요!</p>
        <p style='font-size: 16px; color: #666;'>내일도 새로운 금융 지식과 함께해요! 💪</p>
    </div>
    """