import streamlit as st
from pathlib import Path
import datetime
import sys, os
import pandas as pd
import plotly.express as px

# ==============
# 환경 세팅
# ==============
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
sys.path.insert(0, str(project_root))

contents_rec_path = os.path.join(str(project_root), "contents", "recommendation")
if contents_rec_path not in sys.path:
    sys.path.insert(0, contents_rec_path)

try:
    from contents.recommendation.hybrid_recommender_v2 import (
        get_hybrid_recommendations,
        validate_user_input,
        get_recommendation_summary,
        adjust_level_by_emotion
    )
    from contents.recommendation.data_access import load_all_cards
    from contents.recommendation.explanation_generator import generate_explanation
except ImportError:
    st.error("시스템 오류가 발생했습니다.")
    st.stop()

# ==============
# 스타일
# ==============
def apply_styles():
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

# ==================
# 태그 안전 처리
# ==================
def safe_tags(tags):
    if tags is None: return []
    if isinstance(tags, list): return [str(t) for t in tags if t]
    if isinstance(tags, str): return [t.strip() for t in tags.split(",") if t.strip()]
    return [str(tags)]

# ==================
# 사용자 뷰
# ==================
def render_user_view():
    
    # 헤더
    st.title("🕹️ 맞춤 금융 지식")
    st.caption("당신의 수준과 관심사에 따라 추천된 맞춤형 금융 정보를 확인해보세요!")


    # 세션 상태에서 사용자 설정 가져오기 (향후 디비에서 바로 받아오기)
    user_level = st.session_state.get('user_level', '입문자')
    english_level = st.session_state.get('english_level', 'Beginner')
    emotions = st.session_state.get('emotions', 10)
    interest_tags = st.session_state.get('interest_tags', all_tags[:2] if 'all_tags' in locals() else [])
    top_n = st.session_state.get('top_n', 3)

    # 챗봇형 학습 프로필
    st.markdown('### 📋 나의 금융 프로필')
    profile_text = f"""
    <p>👋 안녕하세요! 챗봇과 퀴즈로 분석한 당신의 금융 프로필을 알려드릴게요.</p>
    <p>🏦 당신의 금융 수준은 <strong>{english_level}</strong> 입니다.</p>
    <p>🔥 오늘의 학습 의욕: <strong>{emotions}</strong> 점</p>
    <p>💡 관심 분야: {', '.join(interest_tags) if interest_tags else '없음'}</p>
    """
    st.markdown(f'<div class="profile-card">{profile_text}</div>', unsafe_allow_html=True)

    # 맞춤 콘텐츠 추천 버튼 (프로필 바로 아래)
    col1, col2, col3 = st.columns([1,2,1])
    with col3:
        if st.button("💫 맞춤 추천 받기"):
            if not interest_tags:
                st.warning("관심 분야를 최소 1개 선택해주세요!")
                st.stop()
            with st.spinner("🤖 AI가 맞춤 정보를 찾고 있어요..."):
                rec_result = get_hybrid_recommendations({
                    "user_id": f"user_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "level": english_level,
                    "emotions": emotions,
                    "interest_tags": interest_tags,
                    "recent_seen_card_ids": [],
                    "liked_tags": []
                }, top_n=top_n)
            if rec_result["success"]:
                st.session_state['last_recommendation'] = rec_result
                st.success(f"✨ {len(rec_result['results'])}개의 맞춤 콘텐츠를 찾았어요!")
            else:
                st.error("추천을 가져올 수 없어요. 잠시 후 다시 시도해주세요.")

    st.divider()
    
    # 추천 콘텐츠 카드
    if 'last_recommendation' in st.session_state:
        rec_result = st.session_state['last_recommendation']
        if rec_result.get("success"):
            results = rec_result["results"]
            st.markdown('### 🚀 나만의 맞춤 추천')
            
            for i, content in enumerate(results, 1):
                st.markdown(
                    f'<div class="content-card"><h4>{i}. {content.get("title","제목 없음")}</h4></div>',
                    unsafe_allow_html=True
                )

                # 1:2 비율로 버튼 + 설명
                col_btn, col_exp = st.columns([1, 2])
                explanation_key = f"explanation_{content.get('card_id', i)}"
                
                with col_btn:
                    if st.button("💡 AI 맞춤 설명", key=f"user_explain_btn_{i}"):
                        with st.spinner("당신을 위한 맞춤 설명을 만들고 있어요..."):
                            try:
                                # 원래 설명(content) 전달만 하고 화면엔 출력 하지 않음
                                explanation = generate_explanation(
                                    level=english_level,
                                    content_title=content.get('title',''),
                                    content_description=content.get('content','')[:300]  # 화면엔 안 보임
                                )
                                st.session_state[explanation_key] = explanation
                                st.success("✅ 설명이 준비됐어요!")
                            except:
                                st.error("설명을 만들 수 없어요 😅")
                
                with col_exp:
                    # 버튼 누른 후에만 설명 표시
                    if explanation_key in st.session_state:
                        st.markdown(
                            f'<div class="ai-explanation">{st.session_state[explanation_key]}</div>',
                            unsafe_allow_html=True
                        )

                # 태그
                tags = safe_tags(content.get('tags', []))
                if tags:
                    tag_html = ''.join([f'<span class="tag">#{t}</span>' for t in tags[:4]])
                    st.markdown(tag_html, unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)

    # 학습 현황
    if 'last_recommendation' in st.session_state:
        st.divider() 
        st.markdown('### 📊 나의 학습 현황')
        
        rec_result = st.session_state['last_recommendation']
        if rec_result.get("success"):
            results = rec_result["results"]
            total_contents = len(results)
            explained_count = 0
            
            # 설명 완료 개수 계산
            for i, content in enumerate(results, 1):
                explanation_key = f"explanation_{content.get('card_id', i)}"
                if explanation_key in st.session_state:
                    explained_count += 1
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("📚 추천받은 정보", f"{total_contents}개")
            with col2:
                st.metric("💡 내용을 확인한 정보", f"{explained_count}개")
            with col3:
                completion_rate = int((explained_count / total_contents) * 100) if total_contents > 0 else 0
                st.metric("✅ 학습 진행률", f"{completion_rate}%")
            
            # 진행도 바
            if total_contents > 0:
                progress = explained_count / total_contents
                st.progress(progress, text=f"오늘의 학습 진행: {int(progress*100)}%")
                
                if explained_count == total_contents:
                    st.success("🎉 오늘 추천받은 모든 정보의 설명을 확인했어요!")
                    # st.balloons()  # 풍선 효과
                    st.toast("학습 완료!", icon="🎉")  # 토스트 알림
                    # 또는 커스텀 축하 메시지
                    st.markdown("""
                    <div style='text-align: center; padding: 20px;'>
                        <h2 style='color: #ff9800;'>🏆 축하합니다! 🏆</h2>
                        <p style='font-size: 18px; color: #333;'>오늘의 학습을 모두 완주하셨네요!</p>
                        <p style='font-size: 16px; color: #666;'>내일도 새로운 금융 지식과 함께해요! 💪</p>
                    </div>
                    """, unsafe_allow_html=True)

# ==================
# 관리자 상세 뷰 
# ==================
def render_admin_view():
    """개발자/관리자용 상세 분석 뷰"""
    
    st.title("🔍 하이브리드 정보 추천 시스템 분석 ")
    st.caption("개발자를 위한 분석 페이지 입니다. 룰베이스 + 벡터 서치 기반으로 하이브리드 방식으로 추천되고 있는 상세 결과를 확인하세요.")
    
    # 세션에서 사용자 설정 가져오기
    user_level = st.session_state.get('user_level', '입문자')
    english_level = st.session_state.get('english_level', 'Beginner')
    emotions = st.session_state.get('emotions', 10)
    interest_tags = st.session_state.get('interest_tags', [])
    top_n = st.session_state.get('top_n', 3)


    # 메인 콘텐츠 영역에 고급 파라미터 설정
    st.markdown('### 🎛️ 고급 파라미터 설정')
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("하이브리드 가중치")
        alpha = st.slider("벡터 검색 가중치 (α)", 0.0, 1.0, 0.6, 0.1, key="alpha_admin")
        beta = st.slider("레벨 매칭 가중치 (β)", 0.0, 1.0, 0.3, 0.1, key="beta_admin") 
        gamma = st.slider("태그 매칭 가중치 (γ)", 0.0, 1.0, 0.1, 0.1, key="gamma_admin")
    
    with col2:
        st.subheader("검색 파라미터")
        k_vec = st.slider("벡터 검색 후보 수", 5, 20, 10, key="k_vec_admin")
        k_rule = st.slider("룰 기반 후보 수", 5, 20, 10, key="k_rule_admin")
        sim_threshold = st.slider("유사도 임계값", 0.0, 0.5, 0.15, 0.05, key="sim_threshold_admin")

    st.divider()

    # 현재 사용자 데이터 표시
    st.markdown('### 👤 현재 사용자 프로필')
    
    user_data = {
        "user_id": f"admin_user_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "level": english_level,
        "emotions": emotions,
        "interest_tags": interest_tags,
        "recent_seen_card_ids": [],
        "liked_tags": []
    }
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f'''
            <div class="admin-metric">
                <h4>지식 레벨</h4>
                <p style="color: var(--primary-orange); font-weight: bold;">{user_level}</p>
            </div>
        ''', unsafe_allow_html=True)
    
    with col2:
        mood_emoji = "😊" if emotions > 20 else "😔" if emotions < -20 else "😐"
        st.markdown(f'''
            <div class="admin-metric">
                <h4>감정 점수</h4>
                <p style="color: var(--primary-orange); font-weight: bold;">{mood_emoji} {emotions}</p>
            </div>
        ''', unsafe_allow_html=True)
    
    with col3:
        st.markdown(f'''
            <div class="admin-metric">
                <h4>관심 분야</h4>
                <p style="color: var(--primary-orange); font-weight: bold;">{len(interest_tags)}개 선택</p>
            </div>
        ''', unsafe_allow_html=True)
    
    with col4:
        st.markdown(f'''
            <div class="admin-metric">
                <h4>추천 파라미터</h4>
                <p style="color: var(--primary-orange); font-weight: bold;">α{alpha} β{beta} γ{gamma}</p>
            </div>
        ''', unsafe_allow_html=True)

    st.divider()

    # 감정 기반 레벨 조정 분석
    st.markdown('### 🧠 감정 기반 레벨 조정 분석')
    
    original_level = english_level
    adjusted_level, reason = adjust_level_by_emotion(original_level, emotions)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("원래 레벨", original_level)
    with col2:
        st.metric("조정된 레벨", adjusted_level)
    with col3:
        emotion_status = "😔 부정적" if emotions <= -30 else "😊 긍정적" if emotions >= 30 else "😐 중립적"
        st.metric("감정 상태", emotion_status)
    
    st.info(f"**조정 사유**: {reason}")

    # 고급 추천 실행
    if st.button("🚀 고급 파라미터로 추천 실행", type="primary"):
        if not interest_tags:
            st.warning("관심 분야를 최소 1개 선택해주세요!")
            st.stop()
            
        is_valid, error_msg = validate_user_input(user_data)
        if not is_valid:
            st.error(f"입력 오류: {error_msg}")
            st.stop()
        
        with st.spinner("고급 하이브리드 추천 시스템 실행 중..."):
            rec_result = get_hybrid_recommendations(
                user_data,
                top_n=top_n,
                k_vec=k_vec,
                k_rule=k_rule,
                alpha=alpha,
                beta=beta,
                gamma=gamma,
                sim_threshold=sim_threshold
            )
        
        if rec_result["success"]:
            st.session_state['last_recommendation'] = rec_result
            st.session_state['last_admin_params'] = {
                'alpha': alpha, 'beta': beta, 'gamma': gamma,
                'k_vec': k_vec, 'k_rule': k_rule, 'sim_threshold': sim_threshold
            }
        else:
            st.error(f"추천 실행 실패: {rec_result.get('error', '알 수 없는 오류')}")

    st.divider()

    # 추천 결과 상세 분석
    if 'last_recommendation' in st.session_state:
        rec_result = st.session_state['last_recommendation']
        if rec_result.get("success"):
            st.markdown('### 📊 추천 결과 상세 분석')
            
            # 전체 요약
            st.success(get_recommendation_summary(rec_result))
            
            results = rec_result["results"]
            metadata = rec_result["metadata"]
            
            # 성능 지표
            col1, col2, col3, col4 = st.columns(4)
            
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

            # 후보 분포 차트
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

            # 추천 콘텐츠 상세 정보
            st.markdown('#### 📚 추천 콘텐츠 상세 분석')
            
            for i, content in enumerate(results, 1):
                with st.expander(f"{i}. {content.get('title', 'Unknown')} - {content.get('recommendation_source', 'unknown')}"):
                    col_content, col_reason = st.columns([2, 1])
                    
                    with col_content:
                        st.write("**기본 정보**")
                        st.write(f"- **레벨**: {content.get('level', 'Unknown')}")
                        st.write(f"- **태그**: {', '.join(safe_tags(content.get('tags', [])))}")
                        st.write(f"- **카테고리**: {content.get('category', 'Unknown')}")
                        
                        # 콘텐츠 미리보기
                        content_text = content.get('content', content.get('description', ''))
                        if content_text:
                            content_text = str(content_text)
                            st.write("**내용 미리보기**")
                            st.write(content_text[:200] + "..." if len(content_text) > 200 else content_text)
                    
                    with col_reason:
                        st.write("**추천 상세 정보**")
                        st.success(f"**추천 순위**: {content.get('recommendation_rank', 'Unknown')}")
                        st.info(f"**출처**: {content.get('recommendation_source', 'Unknown')}")
                        
                        # 벡터 검색인 경우 상세 정보
                        if content.get('recommendation_source') == 'vector_search':
                            vector_model = content.get('vector_model', 'Unknown')
                            vector_score = content.get('vector_score', 0.0)
                            st.success(f"**임베딩 모델**: {vector_model}")
                            st.metric("유사도 점수", f"{vector_score:.3f}")
                        
                        st.warning(f"**사유**: {content.get('recommendation_reason', 'Unknown')}")
            
            # 메타데이터 상세 분석
            with st.expander("🔧 메타데이터 상세 분석"):
                st.subheader("감정 기반 룰 추천 상세")
                emotion_details = metadata['emotion_rule_details']
                st.json(emotion_details)
                
                st.subheader("시스템 파라미터")
                params = metadata['parameters']
                param_df = pd.DataFrame([
                    {"파라미터": str(key), "값": str(value)} 
                    for key, value in params.items()
                    if key is not None and value is not None
                ])
                st.dataframe(param_df, use_container_width=True)
                
                st.subheader("생성된 컨텍스트 텍스트")
                st.code(metadata['context_text'], language="text")


# ==================
# 메인 렌더링
# ==================
def render():
    apply_styles()

    # 공통 사이드바에서 사용자 설정 관리
    with st.sidebar:
        st.header("🎯 나의 설정")
        user_level = st.selectbox("내 금융 지식 수준", ["입문자","중급자","고급자"], 
                                 index=["입문자","중급자","고급자"].index(st.session_state.get('user_level', '입문자')), 
                                 key="user_level_common")
        level_mapping = {"입문자": "Beginner", "중급자": "Intermediate", "고급자": "Advanced"}
        english_level = level_mapping[user_level]
        
        emotions = st.slider("오늘의 학습 의욕", -50, 50, st.session_state.get('emotions', 10), 
                            key="emotions_common")
        
        try:
            all_cards = load_all_cards()
            all_tags = set()
            for card in all_cards:
                tags = card.get("tags", [])
                if isinstance(tags, list):
                    all_tags.update([str(tag) for tag in tags if tag])
                elif isinstance(tags, str):
                    all_tags.update([t.strip() for t in tags.split(",") if t.strip()])
            all_tags = sorted(list(all_tags))
        except:
            all_tags = ["투자","경제","주식","금융","부동산","자산관리"]
            
        interest_tags = st.multiselect("관심 분야", all_tags, 
                                     default=st.session_state.get('interest_tags', all_tags[:2]), 
                                     key="interest_tags_common")
        
        top_n = st.select_slider("추천 받을 개수", [1,2,3,4,5], 
                                value=st.session_state.get('top_n', 3), 
                                key="top_n_common")
        
        # 세션에 업데이트된 설정 저장
        st.session_state.update({
            'user_level': user_level,
            'english_level': english_level,
            'emotions': emotions,
            'interest_tags': interest_tags,
            'top_n': top_n
        })

    tab1, tab2 = st.tabs(["맞춤 금융 지식", "추천 시스템 분석"])

    with tab1:
        render_user_view()

    with tab2:
        render_admin_view()

if __name__ == "__main__":
    render()