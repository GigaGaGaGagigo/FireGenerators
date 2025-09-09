# ================== 
# 사용자 맞춤 추천 시스템 - 리팩토링된 메인 파일
# ================== 
import streamlit as st
from pathlib import Path
import sys
import os

# ============== 
# 환경 세팅
# ============== 
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
sys.path.insert(0, str(project_root))

contents_rec_path = os.path.join(str(project_root), "contents", "recommendation")
if contents_rec_path not in sys.path:
    sys.path.insert(0, contents_rec_path)

# 리팩토링된 모듈들 import - app.py에서 실행되므로 절대 import만 사용
try:
    from ui.contents.constants import DEFAULT_CONFIG
    from ui.contents.styles import apply_global_styles
    from ui.contents.data_utils import parse_user_profile_data
    from ui.contents.user_components import (
        render_user_profile_card, render_user_analysis_cards,
        render_recommendation_button, render_recommendation_contents,
        render_more_recommendations_button, render_learning_history,
        render_learning_progress
    )
    from ui.contents.admin_components import (
        render_content_overview_charts, render_user_behavior_analytics,
        render_hybrid_system_architecture, render_system_configuration,
        render_emotion_based_analysis, render_recommendation_analysis
    )
except ImportError as e:
    st.error(f"모듈을 불러올 수 없습니다: {e}")
    st.info("리팩토링된 모듈들을 찾을 수 없습니다. 백업 파일로 되돌리고 있습니다...")
    st.stop()


def render_user_view():
    """사용자 뷰 메인 렌더링 함수 - 리팩토링됨"""
    # 헤더
    st.title("🕹️ 맞춤 금융 지식")
    st.caption("당신의 관심사와 금융 레벨 따라 추천된 맞춤 금융 지식를 확인해보세요!")

    # 사용자 데이터 파싱
    profile_data = parse_user_profile_data()
    interest_tags = profile_data['interest_tags']
    
    top_n = st.session_state.get('top_n', DEFAULT_CONFIG["top_n"])
    use_llm_rerank = st.session_state.get('use_llm_rerank', DEFAULT_CONFIG["use_llm_rerank"])

    # 2x2 그리드 레이아웃
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.markdown('### 📋 나의 금융 프로필')
        render_user_profile_card(profile_data)
    
    with col_right:
        render_user_analysis_cards(profile_data)

    # 맞춤 콘텐츠 추천 버튼
    render_recommendation_button(interest_tags, profile_data, top_n, use_llm_rerank)

    st.divider()

    # 추천 콘텐츠 카드 및 재추천 로직
    if 'shown_recommendations' in st.session_state:
        results = st.session_state['shown_recommendations']
        
        # 추천 콘텐츠 렌더링
        render_recommendation_contents(results, profile_data)

        # 재추천 버튼
        st.divider()
        rec_result = st.session_state['recommendation_result']
        render_more_recommendations_button(rec_result, results)

    # 이전 조회 콘텐츠 히스토리
    st.divider()
    render_learning_history()

    # 학습 현황
    render_learning_progress()


def render_admin_view():
    """개발자/관리자용 상세 분석 뷰 - 리팩토링됨"""
    
    st.title("🔍 하이브리드 추천 시스템 분석 ")
    st.caption("개발자를 위한 분석 페이지 입니다. 룰베이스 + 벡터 서치 기반으로 하이브리드 방식으로 리랭킹 되어 추천되고 있는 상세 결과를 확인하세요.")
    
    # 콘텐츠 데이터 전체 규모 시각화
    render_content_overview_charts()
    
    st.divider()
    
    # 사용자 행동 분석 대시보드
    render_user_behavior_analytics()
    
    st.divider()
    
    # 하이브리드 추천 시스템 아키텍처 설명
    render_hybrid_system_architecture()
    
    st.divider()

    # 현재 설정 요약
    render_system_configuration()

    st.divider()

    # 감정 기반 레벨 조정 분석
    render_emotion_based_analysis()
    
    st.divider()

    # 추천 결과 상세 분석
    render_recommendation_analysis()


def render():
    """메인 렌더링 함수 - 리팩토링됨"""
    apply_global_styles()

    # 사이드바에서 추천 설정만 관리
    with st.sidebar:
        st.header("⚙️ 추천 설정")
        top_n = st.select_slider("추천 받을 개수", [1,2,3,4,5], 
                                value=st.session_state.get('top_n', DEFAULT_CONFIG["top_n"]), 
                                key="top_n_common")
        
        # LLM 컨텍스트 리랭킹 옵션 추가
        use_llm_rerank = st.checkbox(
            "AI 컨텍스트 리랭킹", 
            value=st.session_state.get('use_llm_rerank', DEFAULT_CONFIG["use_llm_rerank"]),
            help="GPT-4o-mini가 사용자 맥락을 고려해 추천 순위를 재조정합니다. 더 정확하지만 처리 시간이 약간 늘어날 수 있습니다.",
            key="use_llm_rerank_common"
        )
        
        # 세션에 설정 저장
        st.session_state['top_n'] = top_n
        st.session_state['use_llm_rerank'] = use_llm_rerank

    tab1, tab2 = st.tabs(["맞춤 금융 지식", "추천 시스템 분석"])

    with tab1:
        render_user_view()

    with tab2:
        render_admin_view()


if __name__ == "__main__":
    render()