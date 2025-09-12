# ================== 
# 관리자 뷰 UI 컴포넌트들
# ================== 
import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Dict, List

from ui.contents.data_utils import (
    load_and_analyze_contents, parse_user_profile_data,
    get_emotion_status, get_risk_tolerance_status, safe_tags
)
from ui.contents.styles import (
    get_metric_card_style, get_process_flow_style, get_ai_explanation_style
)
from ui.contents.constants import CHART_COLORS, TOPIC_MAPPING

def get_admin_recommendation_modules():
    """관리자용 추천 시스템 모듈들을 동적으로 import"""
    contents_rec_path = None
    try:
        # 경로 설정
        import os
        from pathlib import Path
        import importlib.util
        
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        contents_rec_path = os.path.join(str(project_root), "contents", "recommendation")
        
        # 직접 파일을 import하는 방식
        hybrid_spec = importlib.util.spec_from_file_location(
            "hybrid_recommender_v2", 
            os.path.join(contents_rec_path, "hybrid_recommender_v2.py")
        )
        if hybrid_spec is None or hybrid_spec.loader is None:
            raise ImportError("hybrid_recommender_v2 모듈을 찾을 수 없습니다")
        
        hybrid_module = importlib.util.module_from_spec(hybrid_spec)
        hybrid_spec.loader.exec_module(hybrid_module)
        
        logger_spec = importlib.util.spec_from_file_location(
            "user_contents_logger",
            os.path.join(contents_rec_path, "user_contents_logger.py")
        )
        if logger_spec is None or logger_spec.loader is None:
            raise ImportError("user_contents_logger 모듈을 찾을 수 없습니다")
        
        logger_module = importlib.util.module_from_spec(logger_spec)
        logger_spec.loader.exec_module(logger_module)
        
        return (
            hybrid_module.get_recommendation_summary, 
            hybrid_module.adjust_level_by_emotion, 
            hybrid_module.load_contents_from_supabase, 
            logger_module.get_logger
        )
    except Exception as e:
        st.error(f"추천 시스템 모듈을 불러올 수 없습니다: {e}")
        st.info(f"경로 확인: {contents_rec_path if contents_rec_path else '경로 설정 실패'}")
        return None, None, None, None


def render_content_overview_charts() -> None:
    """콘텐츠 전체 규모 시각화"""
    st.markdown('#### 📈 콘텐츠 데이터 전체 규모')
    
    analysis = load_and_analyze_contents()
    if not analysis:
        st.error("콘텐츠 데이터를 불러올 수 없습니다.")
        return
    
    # 상단 메트릭 표시
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("총 콘텐츠 수", analysis['total_contents'])
    
    with col2:
        beginner_count = analysis['level_distribution'].get('Beginner', 0)
        st.metric("입문 레벨", beginner_count)
    
    with col3:
        intermediate_count = analysis['level_distribution'].get('Intermediate', 0)
        st.metric("중급 레벨", intermediate_count)
    
    with col4:
        advanced_count = analysis['level_distribution'].get('Advanced', 0)
        st.metric("고급 레벨", advanced_count)
    
    # 차트 영역
    render_content_distribution_charts(analysis)
    
    # 상세 데이터 테이블
    render_content_detail_table(analysis)


def render_content_distribution_charts(analysis: Dict) -> None:
    """콘텐츠 분포 차트 렌더링"""
    col_left, col_right = st.columns(2)
    
    with col_left:
        # 레벨별 분포 파이 차트
        if analysis['level_distribution']:
            fig_level = px.pie(
                values=list(analysis['level_distribution'].values()),
                names=list(analysis['level_distribution'].keys()),
                title="레벨별 콘텐츠 분포",
                color_discrete_map=CHART_COLORS["level_colors"]
            )
            fig_level.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_level, use_container_width=True)
    
    with col_right:
        # 카테고리별 + 난이도별 분포 스택 바 차트
        if analysis['category_distribution'] and not analysis['contents_df'].empty:
            df_viz = analysis['contents_df']
            if 'category_name' in df_viz.columns and 'level' in df_viz.columns:
                # 카테고리와 레벨별 그룹화
                category_level_counts = df_viz.groupby(['category_name', 'level']).size().reset_index(name='count')
                
                fig_category = px.bar(
                    category_level_counts,
                    x='category_name',
                    y='count',
                    color='level',
                    title="카테고리별 콘텐츠 분포",
                    color_discrete_map=CHART_COLORS["level_colors"],
                    labels={
                        'category_name': '카테고리',
                        'count': '콘텐츠 수',
                        'level': '난이도'
                    }
                )
                fig_category.update_layout(
                    xaxis_title="카테고리",
                    yaxis_title="콘텐츠 수",
                    xaxis_tickangle=-45,
                    legend_title="난이도",
                    legend=dict(
                        orientation="v",
                        yanchor="top",
                        y=1,
                        xanchor="left",
                        x=1.02
                    )
                )
                st.plotly_chart(fig_category, use_container_width=True)
            else:
                st.warning("카테고리별 난이도 분포를 표시할 수 없습니다.")


def render_content_detail_table(analysis: Dict) -> None:
    """콘텐츠 상세 데이터 테이블 렌더링"""
    with st.expander("📊 콘텐츠 상세 데이터 테이블"):
        if not analysis['contents_df'].empty:
            # 주요 컬럼만 표시
            display_columns = ['title', 'level', 'category_name', 'topic_id']
            if 'tags' in analysis['contents_df'].columns:
                display_columns.append('tags')
            
            # 존재하는 컬럼만 필터링
            available_columns = [col for col in display_columns if col in analysis['contents_df'].columns]
            filtered_df = analysis['contents_df'][available_columns] if available_columns else analysis['contents_df']
            st.dataframe(filtered_df, use_container_width=True)


def render_user_behavior_analytics() -> None:
    """사용자 행동 분석 대시보드 렌더링"""
    st.markdown('### 📊 사용자 행동 분석 대시보드')
    
    try:
        _, _, _, get_logger = get_admin_recommendation_modules()
        if not get_logger:
            st.warning("로거 모듈을 불러올 수 없습니다.")
            return
            
        supabase_client = st.session_state.get("supabase")
        logger = get_logger(supabase_client)
        
        if logger:
            content_analytics = logger.get_content_analytics(days=30)
            
            if content_analytics.get('total_views', 0) > 0:
                render_analytics_metrics(content_analytics)
                render_analytics_charts(content_analytics)
            else:
                st.info("아직 사용자 행동 데이터가 충분하지 않습니다. 더 많은 콘텐츠 조회가 필요합니다.")
        else:
            st.error("로거 초기화에 실패했습니다.")
    except Exception as e:
        st.error(f"사용자 행동 분석을 불러올 수 없습니다: {e}")


def render_analytics_metrics(content_analytics: Dict) -> None:
    """분석 메트릭 렌더링"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("총 조회수", content_analytics['total_views'])
    with col2:
        st.metric("순 사용자", content_analytics['unique_users'])
    with col3:
        avg_length = content_analytics.get('avg_explanation_length', 0)
        st.metric("평균 설명 길이", f"{avg_length}자")
    with col4:
        feedback_total = sum(content_analytics.get('feedback_distribution', {}).values())
        feedback_rate = round(feedback_total / content_analytics['total_views'] * 100, 1) if content_analytics['total_views'] > 0 else 0
        st.metric("피드백 비율", f"{feedback_rate}%")


def render_analytics_charts(content_analytics: Dict) -> None:
    """분석 차트 렌더링"""
    col_left, col_right = st.columns(2)
    
    with col_left:
        # 피드백 분포 차트
        feedback_dist = content_analytics.get('feedback_distribution', {})
        if feedback_dist:
            fig_feedback = px.pie(
                values=list(feedback_dist.values()),
                names=list(feedback_dist.keys()),
                title="사용자 피드백 분포",
                color_discrete_map=CHART_COLORS["feedback_colors"]
            )
            st.plotly_chart(fig_feedback, use_container_width=True)
    
    with col_right:
        # 추천 소스별 효과 분석
        source_dist = content_analytics.get('recommendation_source_distribution', {})
        if source_dist:
            fig_source = px.bar(
                x=list(source_dist.keys()),
                y=list(source_dist.values()),
                title="추천 소스별 조회 분포",
                color=list(source_dist.values()),
                color_continuous_scale='Blues'
            )
            fig_source.update_layout(
                xaxis_title="추천 소스",
                yaxis_title="조회 수",
                showlegend=False
            )
            st.plotly_chart(fig_source, use_container_width=True)


def render_hybrid_system_architecture() -> None:
    """하이브리드 추천 시스템 아키텍처 설명 렌더링"""
    st.markdown('### 🏗️ 하이브리드 추천 시스템 아키텍처')
    
    # 전체 프로세스 플로우 차트
    st.markdown(get_process_flow_style(), unsafe_allow_html=True)
    
    # 상세 설명을 탭으로 구성
    render_architecture_tabs()


def render_architecture_tabs() -> None:
    """아키텍처 설명 탭들 렌더링"""
    tab1, tab2, tab3 = st.tabs(["🎯 1단계: 후보군 수집", "⚖️ 2단계: 수치 리랭킹", "🎖️ 3단계: LLM 컨텍스트 리랭킹"])
    
    with tab1:
        render_candidate_collection_tab()
    
    with tab2:
        render_numerical_reranking_tab()
    
    with tab3:
        render_llm_reranking_tab()


def render_candidate_collection_tab() -> None:
    """후보군 수집 전략 탭 렌더링"""
    st.markdown("#### 후보군 수집 전략 (3가지 방식)")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        **😊 감정 기반 룰**
        - **감정 분석**: 사용자 투자 심리 반영
        - **레벨 조정**: 감정에 따른 난이도 변경
        - **Supabase 쿼리**: 실시간 DB 검색
        
        **📊 매개변수:**
        - 후보 수: 10개
        - 감정 점수: -50 ~ +50
        - 레벨 자동 조정
        """)
    
    with col2:
        st.markdown("""
        **🧠 벡터 검색**
        - **다중 모델**: BGE-M3, KO-SRoBERTa
        - **컨텍스트 임베딩**: 사용자 프로필 기반
        - **FAISS 인덱스**: 고속 유사도 검색
        
        **📊 매개변수:**
        - 후보 수: 10개  
        - 유사도 임계값: 0.15
        - 레벨 필터링: 완화 적용 (level_strict=False)
        """)
        
    with col3:
        st.markdown("""
        **📋 기본 룰**
        - **레벨 매칭**: 사용자 지식 수준 일치
        - **태그 매칭**: 관심사 기반 필터링
        - **중복 제거**: 기존 조회 콘텐츠 제외
        
        **📊 매개변수:**
        - 후보 수: 10개
        - 레벨 필터링: 완화 모드 (level_strict=False)
        - 태그 점수 가중치: 40%
        """)


def render_numerical_reranking_tab() -> None:
    """수치 기반 리랭킹 탭 렌더링"""
    st.markdown("#### 수치 기반 리랭킹 공식")
    
    st.latex(r"""
    Score_{final} = \alpha \times Score_{vector} + \beta \times Score_{level} + \gamma \times Score_{tag}
    """)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("벡터 가중치 (α)", "0.6", help="벡터 검색 유사도 점수의 중요도")
    with col2:
        st.metric("레벨 가중치 (β)", "0.3", help="사용자 지식 수준 일치도의 중요도")
    with col3:
        st.metric("태그 가중치 (γ)", "0.1", help="관심사 태그 매칭 점수의 중요도")
    
    st.markdown("""
    **🔧 추가 조정 요소:**
    - **이전 조회 패널티**: -0.2 (중복 방지)
    - **선호 태그 보너스**: +0.1 (개인화 강화)
    - **레벨 차이 패널티**: 1.0 - 0.3 × |차이| (적절한 난이도)
    - **레벨 필터링**: 완화 적용 (Ablation Study 결과 반영)
    """)


def render_llm_reranking_tab() -> None:
    """LLM 리랭킹 탭 렌더링"""
    st.markdown("#### LLM 컨텍스트 리랭킹")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        **🎯 LLM 분석 요소:**
        1. **사용자 프로필**: 지식 수준, 감정 상태, 학습 성향
        2. **콘텐츠 컨텍스트**: 제목, 레벨, 태그, 내용 미리보기
        3. **개인화 매칭**: 투자 성향과 지식 특성 종합 분석
        4. **학습 효과성**: 사용자에게 최적화된 학습 경로 고려
        
        **📊 최종 점수 조합:**
        ```
        최종점수 = 0.7 × LLM컨텍스트점수 + 0.3 × 수치점수
        ```
        
        **💡 핵심 포인트:**
        - **LLM 평가 대상**: 상위 7개만 (효율성)
        - **가중치 비율**: LLM 70% > 수치 30% (컨텍스트 중시)  
        - **폴백 처리**: LLM 실패시 기존 수치점수로 폴백
        """)
    
    with col2:
        st.markdown("""
        **⚙️ LLM 설정:**
        - **모델**: GPT-4o-mini
        - **Temperature**: 0.3
        - **Max Tokens**: 300
        - **Top-p**: 0.9
        - **평가 후보**: 상위 7개
        
        **🎯 출력 형식:**
        ```
        후보 1: context_score=0.85
        후보 2: context_score=0.72
        후보 3: context_score=0.68
        ```
        """)


def render_system_configuration() -> None:
    """현재 시스템 설정 요약 렌더링"""
    st.markdown('### 📊 현재 시스템 설정 요약')
    
    # 성능 지표를 카드 형태로 표시
    metric_cols = st.columns(4)
    
    metrics_data = [
        ("후보군 크기", "~20개", "룰베이스 + 벡터서치"),
        ("리랭킹 방식", "2단계", "수치 → LLM"),
        ("레벨 필터링", "완화 적용", "Ablation Study 반영"),
        ("처리 속도", "~3초", "LLM 포함")
    ]
    
    for i, (title, value, subtitle) in enumerate(metrics_data):
        with metric_cols[i]:
            st.markdown(
                get_metric_card_style(title, value, subtitle),
                unsafe_allow_html=True
            )


def render_emotion_based_analysis() -> None:
    """감정 기반 레벨 조정 분석 렌더링"""
    st.markdown('### 🧠 감정 기반 레벨 조정 분석')
    
    _, adjust_level_by_emotion, _, _ = get_admin_recommendation_modules()
    if not adjust_level_by_emotion:
        st.warning("레벨 조정 모듈을 불러올 수 없습니다.")
        return
    
    profile_data = parse_user_profile_data()
    knowledge_level = profile_data['knowledge_level']
    emotions = profile_data['emotions']
    
    original_level = knowledge_level
    adjusted_level, reason = adjust_level_by_emotion(original_level, emotions)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("원래 레벨", original_level)
    with col2:
        st.metric("조정된 레벨", adjusted_level)
    with col3:
        emotion_info = get_emotion_status(emotions)
        st.metric("현재 투자 심리", f"{emotion_info['emoji']} {emotion_info['status']}", delta=f"{emotions}점")
    
    st.info(f"**조정 사유**: {reason}")
    
    # 감정 점수 분류 기준 표시
    render_emotion_classification_table(profile_data)


def render_emotion_classification_table(profile_data: Dict) -> None:
    """감정 점수 분류 기준 테이블 렌더링"""
    with st.expander("📊 감정 점수 분류 기준"):
        st.markdown("""
        | 점수 범위 | 상태 | 설명 | 추천 전략 |
        |-----------|------|------|-----------|
        | 30점 이상 | 😊 매우 긍정적 | 투자에 대한 기대감이 높음 | 도전적인 콘텐츠 추천 |
        | 10~29점 | 🙂 긍정적 | 낙관적인 마음가짐 | 성장 지향 콘텐츠 |
        | -10~9점 | 😐 중립적 | 균형잡힌 투자 심리 | 기본 수준 콘텐츠 |
        | -30~-11점 | 😟 다소 불안 | 약간의 우려 있음 | 안정적인 콘텐츠 우선 |
        | -30점 미만 | 😔 불안감 높음 | 투자 걱정이 많음 | 쉽고 안전한 콘텐츠로 하향 조정 |
        """)
        
        risk_tolerance = profile_data.get('risk_tolerance', 50)
        risk_info = get_risk_tolerance_status(risk_tolerance)
        
        st.markdown("### 📊 위험 허용도 분류 기준")
        st.markdown(f"**현재 사용자**: {risk_info['emoji']} {risk_info['status']} ({risk_tolerance}점)")
        
        st.markdown("""
        | 점수 범위 | 투자 성향 | 특성 |
        |-----------|-----------|------|
        | 80점 이상 | 🚀 적극적 | 높은 수익을 위해 큰 위험 감수 |
        | 60~79점 | 📈 공격적 | 적당한 위험을 감수하며 수익 추구 |
        | 40~59점 | ⚖️ 균형형 | 안정성과 수익성의 적절한 균형 |
        | 20~39점 | 🛡️ 보수적 | 안정성 중시, 낮은 위험 선호 |
        | 20점 미만 | 🏦 매우 보수적 | 원금 보장 최우선 |
        """)


def render_recommendation_analysis() -> None:
    """추천 결과 상세 분석 렌더링"""
    if 'recommendation_result' in st.session_state:
        rec_result = st.session_state['recommendation_result']
        if rec_result.get("success"):
            st.markdown('### 📊 추천 결과 상세 분석')
            
            # 전체 요약
            get_recommendation_summary, _, _, _ = get_admin_recommendation_modules()
            if get_recommendation_summary:
                st.success(get_recommendation_summary(rec_result))
            else:
                st.warning("추천 요약 모듈을 불러올 수 없습니다.")
            
            results = rec_result["results"]
            metadata = rec_result["metadata"]
            
            # 성능 지표 렌더링
            render_performance_metrics(metadata)
            
            # 분포 분석 차트
            render_recommendation_distribution_charts(metadata)
            
            # 추천 콘텐츠 상세 정보
            render_recommendation_content_details(results, metadata)
            
            # 메타데이터 상세 분석
            render_metadata_analysis(metadata, rec_result)


def render_performance_metrics(metadata: Dict) -> None:
    """성능 지표 렌더링"""
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("처리 시간", f"{metadata['processing_time']:.3f}초")
    with col2:
        st.metric("총 후보", metadata['total_candidates'])
    with col3:
        st.metric("최종 추천", metadata['final_recommendations'])
    with col4:
        sources = metadata['recommendation_sources']
        unique_sources = len(set(sources))
        st.metric("다양성 점수", f"{unique_sources}/3")
    with col5:
        llm_info = metadata.get('llm_rerank_info', {})
        llm_used = "✅" if llm_info.get('llm_used', False) else "❌"
        st.metric("AI 리랭킹", llm_used)


def render_recommendation_distribution_charts(metadata: Dict) -> None:
    """추천 분포 분석 차트 렌더링"""
    st.markdown('#### 📈 추천 분포 분석')
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 후보 출처별 분포
        sources_dist = metadata["candidate_sources_distribution"]
        fig_pie = px.pie(
            values=list(sources_dist.values()),
            names=list(sources_dist.keys()),
            title="후보 출처별 분포"
        )
        fig_pie.update_traces(marker_colors=['#FE7743', '#4A90E2', '#A3D9A5'])
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        # 최종 추천 출처 분포
        final_sources = metadata["recommendation_sources"]
        final_dist = pd.Series(final_sources).value_counts()
        fig_bar = px.bar(
            x=final_dist.index,
            y=final_dist.values,
            title="최종 추천 출처별 분포",
            color=final_dist.values,
            color_continuous_scale=['#FE7743', '#4A90E2', '#A3D9A5']
        )
        st.plotly_chart(fig_bar, use_container_width=True)


def render_recommendation_content_details(results: List[Dict], metadata: Dict) -> None:
    """추천 콘텐츠 상세 정보 렌더링"""
    st.markdown('#### 📚 추천 콘텐츠 상세 분석')
    
    for i, content in enumerate(results, 1):
        with st.expander(f"{i}. {content.get('title', 'Unknown')} - {content.get('recommendation_source', 'unknown')}"):
            col_left, col_right = st.columns([1, 1])

            with col_left:
                render_content_detail_left(content, i)

            with col_right:
                render_content_detail_right(content, metadata)


def render_content_detail_left(content: Dict, i: int) -> None:
    """콘텐츠 상세 정보 왼쪽 컬럼 렌더링"""
    st.markdown("##### 📜 추천된 콘텐츠 상세")
    
    # 원본 콘텐츠
    content_text = content.get('content', content.get('description', ''))
    if content_text:
        content_text = str(content_text)
        st.markdown("**📝 원본 콘텐츠 내용**")
        st.markdown(f'<div style="background: #f9f9f9; padding: 10px; border-radius: 5px; border-left: 3px solid #666; max-height: 200px; overflow-y: auto;">{content_text}</div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    # AI 생성 설명
    st.markdown("**AI 생성 맞춤 설명**")
    card_identifier = content.get('card_id', content.get('id', i))
    explanation_key = f"explanation_{card_identifier}"
    
    if explanation_key in st.session_state:
        st.markdown(
            get_ai_explanation_style(st.session_state[explanation_key]),
            unsafe_allow_html=True
        )
    else:
        st.info("💡 사용자가 아직 이 콘텐츠의 AI 설명을 생성하지 않았습니다.")


def render_content_detail_right(content: Dict, metadata: Dict) -> None:
    """콘텐츠 상세 정보 오른쪽 컬럼 렌더링"""
    # 추천 방식 및 사유
    st.markdown("##### 🎯 어떻게 추천되었나요?")
    source = content.get('recommendation_source', 'Unknown')
    rank = content.get('recommendation_rank', 'N/A')
    reason = content.get('recommendation_reason', '사유 없음')

    st.info(f"**추천 방식**: {source} (순위: {rank})")
    
    if source == 'vector_search':
        score = content.get('vector_score', 0.0)
        model = content.get('vector_model', 'Unknown')
        st.metric("유사도 점수", f"{score:.3f}")
        st.caption(f"사용한 모델: {model}")
    
    # LLM 리랭킹 정보 표시
    if content.get('llm_reranked', False):
        st.success("AI 컨텍스트 리랭킹 적용됨")
        llm_context_score = content.get('llm_context_score')
        llm_final_score = content.get('llm_final_score')
        if llm_context_score is not None:
            st.metric("AI 컨텍스트 점수", f"{llm_context_score:.3f}")
        if llm_final_score is not None:
            st.caption(f"최종 점수: {llm_final_score:.3f}")
    else:
        if metadata.get('llm_rerank_info', {}).get('llm_used', False):
            st.info("ℹ️ 수치 기반 리랭킹 사용")
        else:
            st.caption("리랭킹: 수치 기반")

    st.warning(f"**추천 핵심 사유**: {reason}")
    st.divider()

    # 기타 기본 정보
    st.markdown("##### 📋 콘텐츠 기본 정보")
    st.write(f"- **레벨**: {content.get('level', 'Unknown')}")
    st.write(f"- **태그**: {', '.join(safe_tags(content.get('tags', [])))}")
    topic_id = content.get('topic_id')
    if topic_id is not None:
        category_name = TOPIC_MAPPING.get(topic_id, content.get('category', 'Unknown'))
    else:
        category_name = content.get('category', 'Unknown')
    st.write(f"- **카테고리**: {category_name}")


def render_metadata_analysis(metadata: Dict, rec_result: Dict) -> None:
    """메타데이터 상세 분석 렌더링"""
    with st.expander("🔧 메타데이터 상세 분석"):
        # LLM 리랭킹 정보
        llm_info = metadata.get('llm_rerank_info', {})
        if llm_info.get('llm_used', False):
            render_llm_rerank_details(llm_info, rec_result)
        
        # 감정 기반 룰 추천 상세
        st.subheader("감정 기반 룰 추천 상세")
        emotion_details = metadata['emotion_rule_details']
        st.json(emotion_details)
        
        # 시스템 파라미터
        st.subheader("시스템 파라미터")
        params = metadata['parameters']
        param_df = pd.DataFrame([
            {"파라미터": str(key), "값": str(value)} 
            for key, value in params.items()
            if key is not None and value is not None
        ])
        st.dataframe(param_df, use_container_width=True)
        
        # 생성된 컨텍스트 텍스트
        st.subheader("생성된 컨텍스트 텍스트")
        st.code(metadata['context_text'], language="text")


def render_llm_rerank_details(llm_info: Dict, rec_result: Dict) -> None:
    """LLM 리랭킹 상세 정보 렌더링"""
    st.subheader("LLM 컨텍스트 리랭킹 상세")
    col1, col2 = st.columns(2)
    
    with col1:
        st.write(f"- **모델**: {llm_info.get('llm_model', 'Unknown')}")
        st.write(f"- **평가 후보 수**: {llm_info.get('llm_evaluated_candidates', 0)}")
        st.write(f"- **점수 조합**: {llm_info.get('score_combination', 'Unknown')}")
    
    with col2:
        st.write("**LLM 컨텍스트 점수**")
        context_scores = llm_info.get('context_scores', {})
        if context_scores:
            # 제목 매핑
            try:
                _, _, load_contents_from_supabase, _ = get_admin_recommendation_modules()
                if load_contents_from_supabase:
                    all_contents = load_contents_from_supabase()
                    card_titles = {content.get("card_id"): content.get("title", "제목 없음") for content in all_contents}
                else:
                    card_titles = {}
            except:
                results = rec_result.get("results", [])
                card_titles = {content.get("card_id"): content.get("title", "제목 없음") for content in results}
            
            for cid, score in list(context_scores.items())[:3]:
                title = card_titles.get(cid, "제목 로드 실패")
                display_title = title[:25] + "..." if len(title) > 25 else title
                st.write(f"- **{display_title}**: {score:.3f}")
                st.caption(f"ID: {cid[:8]}")
    
    # LLM 원시 응답
    if llm_info.get('llm_raw_response'):
        render_llm_raw_response(llm_info, rec_result)


def render_llm_raw_response(llm_info: Dict, rec_result: Dict) -> None:
    """LLM 원시 응답 렌더링"""
    with st.expander("LLM 원시 응답 보기"):
        raw_response = llm_info['llm_raw_response']
        
        try:
            # 제목 매핑
            try:
                _, _, load_contents_from_supabase, _ = get_admin_recommendation_modules()
                if load_contents_from_supabase:
                    all_contents = load_contents_from_supabase()
                    card_titles = {content.get("card_id"): content.get("title", "제목 없음") for content in all_contents}
                else:
                    card_titles = {}
            except:
                card_titles = {}
            
            # 평가된 콘텐츠 목록
            context_scores = llm_info.get('context_scores', {})
            if context_scores and card_titles:
                st.markdown("**📋 평가된 콘텐츠 목록:**")
                for i, (cid, score) in enumerate(context_scores.items(), 1):
                    title = card_titles.get(cid, "제목 로드 실패")
                    st.write(f"**후보 {i}**: {title} (점수: {score:.3f})")
                st.divider()
            
            st.markdown("**GPT-4o-mini 원시 응답:**")
            st.code(raw_response, language="text")
        except Exception:
            st.code(raw_response, language="text")