import streamlit as st
import sys
import os
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List

# 프로젝트 루트 경로 추가
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent  # my_app/ui/contents/ -> my_app/
sys.path.insert(0, str(project_root))

try:
    # 하이브리드 추천 시스템 임포트 - contents/recommendation 폴더를 경로에 추가
    contents_rec_path = os.path.join(str(project_root), "contents", "recommendation")
    if contents_rec_path not in sys.path:
        sys.path.insert(0, contents_rec_path)
    
    from contents.recommendation.hybrid_recommender_v2 import (
        get_hybrid_recommendations, 
        validate_user_input,
        get_recommendation_summary,
        adjust_level_by_emotion
    )
    from contents.recommendation.data_access import load_all_cards
    from contents.recommendation.explanation_generator import generate_explanation
except ImportError as e:
    st.error(f"모듈 임포트 오류: {e}")
    st.stop()

# ========================================
# 설정 및 상수
# ========================================

SAMPLE_USERS = {
    "긍정적 초보자": {
        "user_id": "positive_beginner",
        "level": "Beginner",
        "emotions": 50,
        "interest_tags": ["투자", "경제", "금융"],
        "recent_seen_card_ids": [],
        "liked_tags": []
    },
    "부정적 중급자": {
        "user_id": "negative_intermediate", 
        "level": "Intermediate",
        "emotions": -40,
        "interest_tags": ["주식", "투자", "금융"],
        "recent_seen_card_ids": [],
        "liked_tags": []
    },
    "중립 고급자": {
        "user_id": "neutral_advanced",
        "level": "Advanced",
        "emotions": 0,
        "interest_tags": ["투자", "퇴직", "자산관리"],
        "recent_seen_card_ids": [],
        "liked_tags": []
    }
}

# ========================================
# 유틸 함수
# ========================================

def safe_tags(tags):
    if tags is None:
        return []
    if isinstance(tags, list):
        return [str(tag) for tag in tags if tag is not None]
    if isinstance(tags, (int, float)):
        return [str(tags)]
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return [str(tags)]


# ========================================
# UI 구성 함수들
# ========================================

def render_user_input_section():
    """사용자 입력 섹션"""
    st.subheader("🎯 사용자 설정")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**기본 정보**")
        
        # 샘플 사용자 선택
        sample_user_key = st.selectbox(
            "샘플 사용자",
            list(SAMPLE_USERS.keys()),
            help="미리 정의된 테스트 사용자"
        )
        
        sample_user = SAMPLE_USERS[sample_user_key].copy()
        
        # 기본값 설정
        user_level = st.selectbox(
            "지식 레벨",
            ["Beginner", "Intermediate", "Advanced"],
            index=["Beginner", "Intermediate", "Advanced"].index(sample_user["level"])
        )
        
        emotions = st.slider(
            "감정 점수",
            min_value=-100,
            max_value=100,
            value=sample_user["emotions"],
            step=5,
            help="부정적(-100) ~ 긍정적(100)"
        )
    
    with col2:
        st.write("**관심 분야**")
        
        # 모든 태그 로드
        try:
            all_cards = load_all_cards()
            all_tags = set()
            for card in all_cards:
                tags = card.get("tags", [])
                if isinstance(tags, list):
                    # 태그가 숫자일 경우를 대비해 문자열로 변환
                    all_tags.update([str(tag) for tag in tags if tag is not None])
                elif isinstance(tags, str):
                    all_tags.update([tag.strip() for tag in tags.split(',') if tag.strip()])
                elif tags is not None:
                    all_tags.add(str(tags))
            all_tags = sorted(list(all_tags))
        except:
            all_tags = ["투자", "경제", "주식", "금융", "퇴직", "자산관리"]
        
        # 기본값을 안전하게 처리 (존재하는 태그만 선택)
        safe_defaults = [tag for tag in sample_user["interest_tags"] if tag in all_tags]
        
        interest_tags = st.multiselect(
            "관심 태그",
            all_tags,
            default=safe_defaults,
            help="여러 개 선택 가능"
        )
    
    # 사용자 데이터 구성
    user_data = {
        "user_id": f"debug_user_{sample_user_key}",
        "level": user_level,
        "emotions": emotions,
        "interest_tags": interest_tags,
        "recent_seen_card_ids": [],
        "liked_tags": []
    }
    
    return user_data

def render_level_adjustment_analysis(user_data: Dict):
    """감정 기반 레벨 조정 분석"""
    st.subheader(" 🕹️ 감정 기반 레벨 조정 분석")
    
    original_level = user_data["level"]
    emotions = user_data["emotions"]
    
    # 레벨 조정 결과
    adjusted_level, reason = adjust_level_by_emotion(original_level, emotions)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("원래 레벨", original_level)
    
    with col2:
        st.metric("조정된 레벨", adjusted_level)
    
    with col3:
        # 감정 상태 표시
        if emotions <= -30:
            emotion_status = "😔 부정적"
            emotion_color = "red"
        elif emotions >= 30:
            emotion_status = "😊 긍정적"
            emotion_color = "green"
        else:
            emotion_status = "😐 중립적"
            emotion_color = "gray"
        
        st.markdown(f"**감정 상태**: <span style='color: {emotion_color}'>{emotion_status}</span>", 
                   unsafe_allow_html=True)
    
    st.info(f"**조정 사유**: {reason}")
    
    # 감정 점수별 레벨 변화 시뮬레이션
    with st.expander("📊 감정 점수별 레벨 변화 시뮬레이션"):
        # 레벨을 숫자로 매핑
        level_mapping = {"Beginner": 1, "Intermediate": 2, "Advanced": 3}
        reverse_mapping = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}
        
        emotion_range = range(-100, 101, 10)
        level_changes = []
        
        for emo in emotion_range:
            adj_level, _ = adjust_level_by_emotion(original_level, emo)
            level_changes.append({
                "감정점수": emo,
                "조정레벨_숫자": level_mapping.get(adj_level, 1),
                "조정레벨": adj_level,
                "원래레벨": original_level
            })
        
        df = pd.DataFrame(level_changes)
        
        # 숫자 값으로 차트 생성
        fig = px.line(df, x="감정점수", y="조정레벨_숫자", 
                     title=f"{original_level}에서 시작하는 감정별 레벨 변화",
                     markers=True)
        
        # y축을 문자열 레벨로 표시
        fig.update_yaxes(
            tickmode='array',
            tickvals=[1, 2, 3],
            ticktext=["Beginner", "Intermediate", "Advanced"],
            title="레벨"
        )
        
        # 원래 레벨 라인 (숫자로)
        original_level_num = level_mapping.get(original_level, 1)
        fig.add_hline(y=original_level_num, line_dash="dash", 
                     annotation_text=f"원래 레벨 ({original_level})")
        
        # 현재 감정 라인
        fig.add_vline(x=emotions, line_dash="dot", 
                     annotation_text=f"현재 감정({emotions})")
        
        st.plotly_chart(fig, use_container_width=True)

def render_recommendation_results(recommendation_result: Dict):
    """추천 결과 상세 분석"""
    if not recommendation_result["success"]:
        st.error(f"추천 실패: {recommendation_result.get('error', '알 수 없는 오류')}")
        return
    
    metadata = recommendation_result["metadata"]
    results = recommendation_result["results"]
    
    st.subheader("🎯 추천 결과 분석")
    
    # 전체 요약
    st.success(get_recommendation_summary(recommendation_result))
    
    # 후보 분포 차트
    col1, col2 = st.columns(2)
    
    with col1:
        # 후보 출처별 분포
        sources_dist = metadata["candidate_sources_distribution"]
        
        fig_pie = px.pie(
            values=list(sources_dist.values()),
            names=list(sources_dist.keys()),
            title="후보 출처별 분포"
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        # 최종 추천 출처 분포
        final_sources = metadata["recommendation_sources"]
        final_dist = pd.Series(final_sources).value_counts()
        
        fig_bar = px.bar(
            x=final_dist.index,
            y=final_dist.values,
            title="최종 추천 출처별 분포"
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    
    # 추천 콘텐츠 상세 정보
    st.subheader("📚 추천 콘텐츠 상세")

    for i, content in enumerate(results, 1):
        with st.expander(f"{i}. {content.get('title', 'Unknown')} - {content.get('recommendation_source', 'unknown')}"):
            col_content, col_reason = st.columns([2, 1])
            
            with col_content:
                st.write("**기본 정보**")
                st.write(f"- **레벨**: {content.get('level', 'Unknown')}")
                st.write(f"- **태그**: {', '.join(safe_tags(content.get('tags', [])))}")
                st.write(f"- **카테고리**: {content.get('category', 'Unknown')}")
                
                # 콘텐츠 미리보기 (안전 변환)
                content_text = content.get('content', content.get('description', ''))
                if content_text:
                    content_text = str(content_text)  # 안전 처리
                    st.write("**내용 미리보기**")
                    st.write(content_text[:200] + "..." if len(content_text) > 200 else content_text)
                
            with col_reason:
                st.write("**추천 상세 정보**")
                st.success(f"**추천 순위**: {content.get('recommendation_rank', 'Unknown')}")
                st.info(f"**출처**: {content.get('recommendation_source', 'Unknown')}")
                
                # 벡터 검색인 경우 사용된 임베딩 모델 표시
                if content.get('recommendation_source') == 'vector_search':
                    vector_model = content.get('vector_model', 'Unknown')
                    vector_score = content.get('vector_score', 0.0)
                    st.success(f"**임베딩 모델**: {vector_model}")
                    st.metric("유사도 점수", f"{vector_score:.3f}")
                
                st.warning(f"**사유**: {content.get('recommendation_reason', 'Unknown')}")

def render_metadata_analysis(metadata: Dict):
    """메타데이터 상세 분석"""
    st.subheader("🔍 추천 과정 상세 분석")
    
    with st.expander("📊 성능 및 통계 정보"):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("처리 시간", f"{metadata['processing_time']:.3f}초")
        
        with col2:
            st.metric("총 후보", metadata['total_candidates'])
        
        with col3:
            st.metric("최종 추천", metadata['final_recommendations'])
        
        with col4:
            # 리스트의 모든 요소를 str으로 변환하여 join
            models_used = metadata.get('models_used', [])
            if models_used:
                models_text = ", ".join([str(model) for model in models_used if model is not None])
                st.metric("사용 모델", f"{len(models_used)}개")
                st.caption(f"모델: {models_text}")
            else:
                st.metric("사용 모델", "0개")
                st.caption("모델: 없음")
    
    with st.expander("💡 감정 기반 룰 추천 상세"):
        emotion_details = metadata['emotion_rule_details']
        
        st.json(emotion_details)
    
    with st.expander("🔧 시스템 파라미터"):
        params = metadata['parameters']
        
        param_df = pd.DataFrame([
            {"파라미터": str(key), "값": str(value)} 
            for key, value in params.items()
            if key is not None and value is not None
        ])
        st.dataframe(param_df, use_container_width=True)
    
    with st.expander("💬 생성된 컨텍스트 텍스트"):
        st.code(metadata['context_text'], language="text")

# ========================================
# 메인 렌더링 함수
# ========================================

def render_hybrid_analysis_tab():
    """하이브리드 추천 분석 탭 내용"""
    # 사이드바 설정
    with st.sidebar:
        st.header("⚙️ 설정")
        
        # 분석 모드 옵션
        debug_level = st.selectbox(
            "분석 모드",
            ["기본", "상세", "전체"],
            index=1
        )
        
        # 추천 파라미터 조정
        st.subheader("🎛️ 추천 파라미터")
        top_n = st.slider("최종 추천 개수", 1, 10, 3)
        k_vec = st.slider("벡터 검색 개수", 5, 20, 10)
        k_rule = st.slider("룰 기반 후보 개수", 5, 20, 10)
        
        alpha = st.slider("벡터 가중치", 0.0, 1.0, 0.6, 0.1)
        beta = st.slider("레벨 가중치", 0.0, 1.0, 0.3, 0.1)
        gamma = st.slider("태그 가중치", 0.0, 1.0, 0.1, 0.1)
        
        sim_threshold = st.slider("유사도 임계값", 0.0, 0.5, 0.15, 0.05)
    
    # 메인 콘텐츠
    # 1. 사용자 입력
    user_data = render_user_input_section()
    
    # 2. 감정 기반 레벨 조정 분석
    render_level_adjustment_analysis(user_data)
    
    # 3. 추천 실행 버튼
    if st.button("🚀 맞춤형 금융 정보 추천받기", type="primary"):
        # 입력 검증
        is_valid, error_msg = validate_user_input(user_data)
        if not is_valid:
            st.error(f"입력 오류: {error_msg}")
            st.stop()
        
        # 추천 실행
        with st.spinner("추천 시스템 실행 중..."):
            recommendation_result = get_hybrid_recommendations(
                user_data,
                top_n=top_n,
                k_vec=k_vec,
                k_rule=k_rule,
                alpha=alpha,
                beta=beta,
                gamma=gamma,
                sim_threshold=sim_threshold
            )
        
        # 추천 결과를 세션 상태에 저장 (다른 탭에서 사용하기 위해)
        st.session_state['last_recommendation_result'] = recommendation_result
        st.session_state['last_user_data'] = user_data
        
        # 4. 결과 분석
        render_recommendation_results(recommendation_result)
        
        # 5. 메타데이터 상세 분석
        if debug_level in ["상세", "전체"]:
            render_metadata_analysis(recommendation_result["metadata"])
        
        # 6. 추가 분석 (전체 모드)
        if debug_level == "전체":
            st.subheader("🔬 추가 분석")
            
            with st.expander("📈 추천 품질 지표"):
                metadata = recommendation_result["metadata"]
                results = recommendation_result["results"]
                
                # 커버리지 분석
                total_content_count = len(load_all_cards())
                coverage = (metadata["total_candidates"] / total_content_count) * 100
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("후보 커버리지", f"{coverage:.2f}%")
                with col2:
                    st.metric("추천 다양성", len(set(metadata["recommendation_sources"])))
                with col3:
                    vector_count = len([r for r in results if r.get("recommendation_source") == "vector_search"])
                    st.metric("벡터 검색 비율", f"{vector_count}/{len(results)}")
                
                # 임베딩 모델별 선택 통계
                st.write("**임베딩 모델별 최종 선택 통계**")
                model_stats = {}
                for result in results:
                    if result.get("recommendation_source") == "vector_search":
                        model = result.get("vector_model", "Unknown")
                        model_stats[model] = model_stats.get(model, 0) + 1
                
                if model_stats:
                    model_df = pd.DataFrame([
                        {"모델": model, "선택 횟수": count, "비율": f"{count/sum(model_stats.values())*100:.1f}%"} 
                        for model, count in model_stats.items()
                    ])
                    st.dataframe(model_df, use_container_width=True)
                else:
                    st.info("벡터 검색으로 선택된 콘텐츠가 없습니다.")
            
            with st.expander("💾 결과 데이터 다운로드"):
                # JSON 다운로드
                import json
                result_json = json.dumps(recommendation_result, ensure_ascii=False, indent=2)
                st.download_button(
                    "JSON 다운로드",
                    result_json,
                    file_name="recommendation_result.json",
                    mime="application/json"
                )

def render_llm_explanation_tab():
    """LLM 맞춤 설명 탭 내용"""
    st.markdown("### 🎙️ AI 맞춤 설명 생성")
    st.markdown("하이브리드 추천으로 선택된 금융 정보를 사용자 레벨에 맞춰 AI가 쉽게 설명해드립니다.")
    
    # 이전 추천 결과가 있는지 확인
    if 'last_recommendation_result' not in st.session_state:
        st.warning("⚠️ 먼저 **하이브리드 분석** 탭에서 금융 정보 추천을 받아주세요!")
        st.info("👈 왼쪽 탭으로 이동해서 추천을 실행하면 여기서 AI 맞춤 설명을 받을 수 있습니다.")
        return
    
    recommendation_result = st.session_state['last_recommendation_result']
    user_data = st.session_state['last_user_data']
    
    if not recommendation_result.get("success", False):
        st.error("추천 결과에 오류가 있습니다. 다시 추천을 받아주세요.")
        return
        
    results = recommendation_result["results"]
    user_level = user_data["level"]
    
    st.success(f"✅ {len(results)}개의 추천 콘텐츠에 대한 **{user_level} 레벨** 맞춤 설명을 생성할 수 있습니다.")
    
    # 콘텐츠별 설명 생성
    for i, content in enumerate(results, 1):
        st.markdown("---")
        st.subheader(f"📚 {i}. {content.get('title', 'Unknown Title')}")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # 원본 콘텐츠 미리보기
            st.write("**📝 원본 내용:**")
            original_content = content.get('content', content.get('description', ''))
            preview_content = original_content[:200] + "..." if len(original_content) > 200 else original_content
            st.markdown(f"*{preview_content}*")
        
        with col2:
            # 콘텐츠 메타 정보
            st.write("**📊 콘텐츠 정보**")
            st.write(f"- **레벨**: {content.get('level', 'Unknown')}")
            st.write(f"- **출처**: {content.get('recommendation_source', 'Unknown')}")
            if content.get('recommendation_source') == 'vector_search':
                st.write(f"- **임베딩 모델**: {content.get('vector_model', 'Unknown')}")
                st.write(f"- **유사도**: {content.get('vector_score', 0):.3f}")
        
        # AI 설명 생성 섹션
        content_key = f"llm_explanation_{content.get('card_id', i)}_{user_level}"
        
        if content_key in st.session_state:
            # 이미 생성된 설명 표시
            st.write(f"**🤖 {user_level} 레벨 맞춤 설명:**")
            explanation = st.session_state[content_key]
            if "오류" in explanation:
                st.error(explanation)
            else:
                st.info(explanation)
        else:
            # 설명 생성 버튼
            if st.button(f"✨ {user_level} 레벨 맞춤 설명 생성", key=f"generate_btn_{i}"):
                try:
                    with st.spinner(f"AI가 {user_level} 레벨에 맞는 설명을 생성하고 있습니다... 🤖"):
                        explanation = generate_explanation(
                            level=user_level,
                            content_title=content.get('title', ''),
                            content_description=original_content[:400]  # 400자 제한
                        )
                        st.session_state[content_key] = explanation
                        st.success("✅ AI 설명이 생성되었습니다!")
                        st.rerun()
                        
                except Exception as e:
                    error_msg = f"설명 생성 오류: {str(e)}"
                    st.session_state[content_key] = error_msg
                    st.error(error_msg)
    
    # 모든 설명 초기화 버튼
    st.markdown("---")
    if st.button("🔄 모든 AI 설명 초기화", help="생성된 모든 AI 설명을 삭제합니다"):
        # LLM 설명 관련 세션 상태 초기화
        keys_to_remove = [key for key in st.session_state.keys() if key.startswith('llm_explanation_')]
        for key in keys_to_remove:
            del st.session_state[key]
        st.success("모든 AI 설명이 초기화되었습니다!")
        st.rerun()

def render():
    """메인 페이지 렌더링 - 탭 구조"""
    st.title("🚀 하이브리드 추천 시스템")
    st.markdown("AI 기반 맞춤형 금융 지식 추천을 통해 개인화된 금융 학습 경험을 제공합니다.")
    
    # 탭 생성
    tab1, tab2 = st.tabs(["📊 하이브리드 분석", "💬 AI 맞춤 설명"])
    
    with tab1:
        render_hybrid_analysis_tab()
    
    with tab2:
        render_llm_explanation_tab()

if __name__ == "__main__":
    # Streamlit 페이지 설정
    st.set_page_config(
        page_title="하이브리드 추천 디버그",
        page_icon="🛠️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    render()