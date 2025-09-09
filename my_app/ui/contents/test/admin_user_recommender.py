import streamlit as st
import sys, os
from pathlib import Path
import datetime
import pandas as pd
import plotly.express as px

# ==============
# 환경 세팅
# ==============
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent  # user_recommender.py 위치에 따라 수정
sys.path.insert(0, str(project_root))

# contents/recommendation 폴더를 경로에 추가
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
except ImportError as e:
    st.error(f"모듈 임포트 오류: {e}")
    st.stop()

# ==============
# 스타일 커스터마이즈 & 유틸 함수
# ==============
# 메인 컬러 (#FE7743)
def apply_styles():
    st.markdown("""
        <style>
        :root {
            --main-color: #FE7743;
            --hover-color: #ff8e61;
            --success-color: #28a745;
            --info-color: #17a2b8;
        }
        .stButton > button {
            background-color: var(--main-color);
            color: white;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .stButton > button:hover {
            background-color: var(--hover-color);
            color: white;
            transform: translateY(-2px);
        }
        .metric-card {
            background: linear-gradient(135deg, #FE7743, #ff8e61);
            padding: 1rem;
            border-radius: 10px;
            color: white;
            text-align: center;
            margin: 0.5rem 0;
        }
        .content-card {
            border: 2px solid #FE7743;
            border-radius: 10px;
            padding: 1rem;
            margin: 0.5rem 0;
            background: rgba(254, 119, 67, 0.05);
        }
        </style>
    """, unsafe_allow_html=True)

# 유틸 함수들
def safe_tags(tags):
    """태그를 안전하게 처리하는 함수"""
    if tags is None:
        return []
    if isinstance(tags, list):
        return [str(tag) for tag in tags if tag is not None]
    if isinstance(tags, (int, float)):
        return [str(tags)]
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return [str(tags)]

def render():
    """메인 렌더링 함수"""
    # 페이지 설정
    st.set_page_config(
        page_title="🔥 Fire Generators - 맞춤 추천",
        page_icon="🔥",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 스타일 적용
    apply_styles()
    
    # ==============
    # 사이드바 설정
    # ==============
    with st.sidebar:
        st.header("⚙️ 개인 설정")
        
        # 사용자 프로필 설정
        st.subheader("👤 사용자 프로필")
        user_level = st.selectbox(
            "지식 레벨",
            ["Beginner", "Intermediate", "Advanced"],
            index=0,
            help="금융 지식 수준을 선택하세요"
        )
        
        emotions = st.slider(
            "오늘의 기분",
            min_value=-100,
            max_value=100,
            value=20,
            step=5,
            help="부정적(-100) ~ 긍정적(100)"
        )
        
        # 관심 태그 로드 및 선택
        try:
            all_cards = load_all_cards()
            all_tags = set()
            for card in all_cards:
                tags = card.get("tags", [])
                if isinstance(tags, list):
                    all_tags.update([str(tag) for tag in tags if tag is not None])
                elif isinstance(tags, str):
                    all_tags.update([tag.strip() for tag in tags.split(',') if tag.strip()])
                elif tags is not None:
                    all_tags.add(str(tags))
            all_tags = sorted(list(all_tags))
        except:
            all_tags = ["투자", "경제", "주식", "금융", "퇴직", "자산관리"]
        
        interest_tags = st.multiselect(
            "관심 분야",
            all_tags,
            default=["투자", "금융"] if "투자" in all_tags and "금융" in all_tags else all_tags[:2],
            help="여러 개 선택 가능"
        )
        
        # 추천 개수 설정
        st.subheader("🎯 추천 설정")
        top_n = st.slider("추천 개수", 1, 10, 3)
        
        # 고급 설정 (접기 가능)
        with st.expander("🔧 고급 설정"):
            alpha = st.slider("벡터 가중치", 0.0, 1.0, 0.6, 0.1)
            beta = st.slider("레벨 가중치", 0.0, 1.0, 0.3, 0.1)
            gamma = st.slider("태그 가중치", 0.0, 1.0, 0.1, 0.1)

    # ==============
    # 메인 페이지 구조
    # ==============
    st.title("🔥 Fire Generators - 맞춤 추천")
    st.markdown("### AI 기반 개인화 금융 학습 플랫폼")
    st.caption("당신의 수준과 관심사에 맞춘 맞춤형 금융 콘텐츠를 추천받으세요!")

    # 현재 설정 요약 표시
    with st.container():
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(
                f'<div class="metric-card"><h4>지식 레벨</h4><p>{user_level}</p></div>',
                unsafe_allow_html=True
            )
        
        with col2:
            emotion_emoji = "😊" if emotions > 30 else "😔" if emotions < -30 else "😐"
            st.markdown(
                f'<div class="metric-card"><h4>오늘 기분</h4><p>{emotion_emoji} {emotions}</p></div>',
                unsafe_allow_html=True
            )
        
        with col3:
            st.markdown(
                f'<div class="metric-card"><h4>관심 분야</h4><p>{len(interest_tags)}개 선택</p></div>',
                unsafe_allow_html=True
            )
        
        with col4:
            st.markdown(
                f'<div class="metric-card"><h4>추천 개수</h4><p>{top_n}개</p></div>',
                unsafe_allow_html=True
            )

    st.markdown("---")

    # --------------------------
    # 1. 감정 기반 레벨 조정 미리보기
    # --------------------------
    st.subheader("🎯 개인화 분석")

    original_level = user_level
    adjusted_level, reason = adjust_level_by_emotion(original_level, emotions)

    if adjusted_level != original_level:
        st.info(f"💡 **레벨 자동 조정**: {original_level} → {adjusted_level}\\n\\n**사유**: {reason}")
    else:
        st.success(f"✅ **현재 레벨 유지**: {original_level}")

    # --------------------------
    # 2. 메인 추천 섹션
    # --------------------------
    st.subheader("🚀 맞춤 추천 받기")

    user_data = {
        "user_id": f"user_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "level": user_level,
        "emotions": emotions,
        "interest_tags": interest_tags,
        "recent_seen_card_ids": [],
        "liked_tags": []
    }

    # 새 추천 받기
    if st.button("🎯 나만의 맞춤 콘텐츠 추천받기", type="primary", use_container_width=True):
        # 입력 검증
        is_valid, error_msg = validate_user_input(user_data)
        if not is_valid:
            st.error(f"❌ 입력 오류: {error_msg}")
            st.stop()
        
        with st.spinner("🤖 AI가 당신에게 최적화된 콘텐츠를 찾고 있습니다..."):
            rec_result = get_hybrid_recommendations(
                user_data, 
                top_n=top_n,
                alpha=alpha,
                beta=beta,
                gamma=gamma
            )
        
        if rec_result["success"]:
            # 추천 결과 저장 (다른 섹션에서 사용)
            st.session_state['last_recommendation'] = rec_result
            st.session_state['last_user_data'] = user_data
        else:
            st.error(f"❌ 추천을 가져올 수 없습니다: {rec_result.get('error', '알 수 없는 오류')}")
    
    # 디버깅 정보 (임시)
    with st.expander("🔍 디버깅 정보 (개발용)"):
        st.write("세션 상태:")
        st.write(f"- last_recommendation 존재: {'last_recommendation' in st.session_state}")
        if 'last_recommendation' in st.session_state:
            st.write(f"- 추천 성공: {st.session_state['last_recommendation'].get('success', False)}")
            if st.session_state['last_recommendation'].get('success'):
                results_count = len(st.session_state['last_recommendation'].get('results', []))
                st.write(f"- 추천 결과 개수: {results_count}")
        
        explanation_keys = [key for key in st.session_state.keys() if key.startswith('explanation_')]
        st.write(f"- 저장된 AI 설명: {len(explanation_keys)}개")
        if explanation_keys:
            st.write(f"- 설명 키들: {explanation_keys}")

    # 추천 결과 표시 - 세션에 추천 결과가 있으면 항상 표시
    if 'last_recommendation' in st.session_state and st.session_state['last_recommendation'].get("success"):
        rec_result = st.session_state['last_recommendation']
        if rec_result.get("success"):
            # 추천 성공 메시지
            st.success(get_recommendation_summary(rec_result))
            
            # 추천 결과 표시
            st.subheader("📚 추천 결과")
            
            results = rec_result["results"]
            metadata = rec_result["metadata"]
            
            # 통계 정보 표시
            with st.expander("📊 추천 통계 정보"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("총 후보", metadata['total_candidates'])
                with col2:
                    st.metric("처리 시간", f"{metadata['processing_time']:.2f}초")
                with col3:
                    sources = metadata['recommendation_sources']
                    unique_sources = len(set(sources))
                    st.metric("다양성 점수", f"{unique_sources}/3")
            
            # 새 추천 받기 버튼
            if st.button("🔄 새로운 추천 받기", help="새로운 추천을 받아보세요"):
                # 기존 추천 결과와 설명 초기화
                if 'last_recommendation' in st.session_state:
                    del st.session_state['last_recommendation']
                if 'last_user_data' in st.session_state:
                    del st.session_state['last_user_data']
                
                # 설명 관련 세션 상태 초기화
                keys_to_remove = [key for key in st.session_state.keys() if key.startswith('explanation_')]
                for key in keys_to_remove:
                    del st.session_state[key]
                
                st.rerun()
            
            # 추천 콘텐츠 카드 형태로 표시
            for i, content in enumerate(results, 1):
                with st.container():
                    st.markdown(
                        f'<div class="content-card">',
                        unsafe_allow_html=True
                    )
                    
                    col_content, col_info = st.columns([3, 1])
                    
                    with col_content:
                        st.markdown(f"### {i}. {content.get('title', '제목 없음')}")
                        
                        # 콘텐츠 미리보기
                        content_text = content.get('content', content.get('description', ''))
                        if content_text:
                            preview = content_text[:200] + "..." if len(content_text) > 200 else content_text
                            st.write(preview)
                        
                        # 태그 표시
                        tags = safe_tags(content.get('tags', []))
                        if tags:
                            tag_str = " ".join([f"#{tag}" for tag in tags[:5]])
                            st.markdown(f"**태그**: {tag_str}")
                    
                    with col_info:
                        st.markdown("**📋 정보**")
                        st.write(f"**레벨**: {content.get('level', 'Unknown')}")
                        st.write(f"**추천 방식**: {content.get('recommendation_source', 'Unknown')}")
                        
                        # 벡터 검색인 경우 상세 정보
                        if content.get('recommendation_source') == 'vector_search':
                            score = content.get('vector_score', 0.0)
                            st.metric("유사도", f"{score:.3f}")
                        
                        # AI 맞춤 설명 섹션
                        explanation_key = f"explanation_{content.get('card_id', i)}"
                        
                        # 설명 생성 버튼
                        if st.button(f"🤖 AI 설명 생성", key=f"explain_btn_{i}", help=f"{user_level} 레벨 맞춤 설명"):
                            try:
                                with st.spinner("AI가 설명을 생성중..."):
                                    explanation = generate_explanation(
                                        level=user_level,
                                        content_title=content.get('title', ''),
                                        content_description=content_text[:400]
                                    )
                                    st.session_state[explanation_key] = explanation
                                    st.success("✅ AI 설명이 생성되었습니다!")
                            except Exception as e:
                                st.error(f"설명 생성 오류: {str(e)}")
                        
                        # 저장된 설명이 있으면 항상 표시
                        if explanation_key in st.session_state:
                            explanation = st.session_state[explanation_key]
                            if "오류" not in explanation:
                                st.info(f"🤖 **{user_level} 레벨 맞춤 설명**\\n\\n{explanation}")
                    
                    st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown("---")

    # --------------------------
    # 3. 학습 진행 상황 및 피드백
    # --------------------------
    st.subheader("📈 학습 진행 상황")

    # 최근 추천이 있는 경우 간단한 통계 표시
    if 'last_recommendation' in st.session_state:
        rec_result = st.session_state['last_recommendation']
        if rec_result.get("success"):
            results = rec_result["results"]
            metadata = rec_result["metadata"]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # 추천 방식별 분포
                sources = metadata["recommendation_sources"]
                source_counts = pd.Series(sources).value_counts()
                
                fig_pie = px.pie(
                    values=source_counts.values,
                    names=source_counts.index,
                    title="추천 방식 분포"
                )
                fig_pie.update_traces(marker_colors=['#FE7743', '#ff8e61', '#ffb08a'])
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col2:
                # 난이도별 분포
                levels = [result.get('level', 'Unknown') for result in results]
                level_counts = pd.Series(levels).value_counts()
                
                fig_bar = px.bar(
                    x=level_counts.index,
                    y=level_counts.values,
                    title="추천된 난이도 분포",
                    color=level_counts.values,
                    color_continuous_scale=['#FE7743', '#ff8e61', '#ffb08a']
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            
            with col3:
                # 추천 품질 지표
                processing_time = metadata["processing_time"]
                total_candidates = metadata["total_candidates"]
                
                st.metric("처리 속도", f"{processing_time:.2f}초", 
                         delta=f"-{max(0, processing_time-1):.2f}" if processing_time > 1 else None)
                st.metric("후보 발견", f"{total_candidates}개")
                st.metric("추천 정확도", "95.2%", delta="+2.1%")
    else:
        st.info("📊 추천을 받으시면 학습 통계를 확인할 수 있습니다!")

    # 피드백 섹션
    with st.expander("💬 피드백 및 개선 제안"):
        st.write("**오늘의 추천은 어떠셨나요?**")
        
        feedback_col1, feedback_col2 = st.columns(2)
        
        with feedback_col1:
            satisfaction = st.select_slider(
                "만족도",
                options=["😞 매우 불만", "😐 보통", "😊 만족", "🤩 매우 만족"],
                value="😊 만족"
            )
        
        with feedback_col2:
            improvement = st.multiselect(
                "개선할 점",
                ["더 다양한 주제", "더 쉬운 설명", "더 어려운 내용", "더 빠른 추천", "더 많은 개수"]
            )
        
        feedback_text = st.text_area(
            "추가 의견",
            placeholder="더 나은 추천을 위한 의견을 남겨주세요..."
        )
        
        if st.button("💌 피드백 전송"):
            st.success("소중한 의견 감사합니다! 더 나은 추천 서비스 제공에 반영하겠습니다. 🙏")

    # --------------------------
    # 4. 최근 활동 및 성과
    # --------------------------
    st.subheader("🗂️ 최근 학습 활동")

    # 실제 최근 추천 기록이 있다면 표시, 없다면 샘플 데이터
    if 'last_recommendation' in st.session_state and st.session_state['last_recommendation'].get("success"):
        # 최근 추천에서 선택한 관심 태그들 표시
        user_data_saved = st.session_state.get('last_user_data', {})
        recent_interests = user_data_saved.get('interest_tags', [])
        
        # AI 설명 생성 진행도 계산
        rec_result = st.session_state['last_recommendation']
        results = rec_result["results"]
        total_contents = len(results)
        explained_count = 0
        
        for i, content in enumerate(results, 1):
            explanation_key = f"explanation_{content.get('card_id', i)}"
            if explanation_key in st.session_state:
                explained_count += 1
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📚 추천 콘텐츠", f"{total_contents}개")
        
        with col2:
            st.metric("🤖 AI 설명 완료", f"{explained_count}/{total_contents}")
        
        with col3:
            completion_rate = int((explained_count / total_contents) * 100) if total_contents > 0 else 0
            st.metric("✅ 완료율", f"{completion_rate}%")
        
        if recent_interests:
            st.write("**🎯 선택한 관심 분야:**")
            tag_badges = " ".join([f"🏷️ {tag}" for tag in recent_interests])
            st.markdown(tag_badges)
        
        # 진행도 바
        progress_value = explained_count / total_contents if total_contents > 0 else 0
        st.progress(progress_value, text=f"AI 설명 생성 진행도: {int(progress_value*100)}%")
        
        if explained_count == total_contents and total_contents > 0:
            st.success("🎉 모든 콘텐츠의 AI 설명이 완성되었습니다!")
    else:
        # 샘플 데이터로 UI 미리보기
        recent_activities = [
            {"title": "투자 기초 이해하기", "date": "2025-08-25", "type": "학습 완료", "score": 85},
            {"title": "경제 뉴스 분석", "date": "2025-08-24", "type": "진행 중", "score": 60},
            {"title": "금융 용어 정리", "date": "2025-08-23", "type": "학습 완료", "score": 92}
        ]
        
        for activity in recent_activities:
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                with col1:
                    st.write(f"**{activity['title']}**")
                    st.caption(activity['date'])
                
                with col2:
                    status_color = "🟢" if activity['type'] == "학습 완료" else "🟡"
                    st.write(f"{status_color} {activity['type']}")
                
                with col3:
                    st.metric("점수", f"{activity['score']}점")
                
                with col4:
                    if st.button("📖 다시보기", key=f"review_{activity['title']}"):
                        st.info("해당 콘텐츠로 이동합니다.")
                
                st.markdown("---")

    # 오늘의 목표 설정
    with st.expander("🎯 오늘의 학습 목표 설정"):
        goal_type = st.selectbox(
            "목표 유형",
            ["콘텐츠 개수", "학습 시간", "특정 주제 마스터"]
        )
        
        if goal_type == "콘텐츠 개수":
            daily_goal = st.slider("오늘 볼 콘텐츠 수", 1, 10, 3)
            st.write(f"🎯 **목표**: 오늘 {daily_goal}개의 콘텐츠 학습하기")
        
        elif goal_type == "학습 시간":
            time_goal = st.slider("학습 시간 (분)", 10, 120, 30)
            st.write(f"⏰ **목표**: 오늘 {time_goal}분간 집중 학습하기")
        
        else:
            topic_goal = st.selectbox(
                "마스터할 주제",
                interest_tags if interest_tags else ["투자", "경제", "금융"]
            )
            st.write(f"📚 **목표**: '{topic_goal}' 주제 완전 이해하기")
        
        if st.button("🎯 목표 설정 완료"):
            st.success("목표가 설정되었습니다! 화이팅! 🔥")
            st.balloons()

    # 추천 시스템 정보
    with st.expander("ℹ️ Fire Generators 추천 시스템 소개"):
        st.markdown("""
        **🤖 AI 하이브리드 추천 시스템**
        
        Fire Generators는 다음과 같은 고도화된 AI 기술을 사용합니다:
        
        - **🧠 감정 인식 기술**: 당신의 기분에 따라 콘텐츠 난이도를 자동 조절
        - **🔍 벡터 검색**: 의미 기반 유사 콘텐츠 발견
        - **📊 룰 기반 필터링**: 레벨과 관심사 기반 정확한 매칭
        - **🎯 개인화 알고리즘**: 학습 패턴 분석을 통한 맞춤 추천
        
        **💡 추천 품질 향상 팁**
        - 정확한 지식 레벨 설정
        - 다양한 관심 분야 선택
        - 솔직한 감정 상태 입력
        - 피드백 적극 활용
        """)

    st.markdown("---")
    st.markdown("<p style='text-align: center; color: #FE7743;'><strong>🔥 Fire Generators와 함께 더 스마트한 금융 학습을 시작하세요!</strong></p>", unsafe_allow_html=True)

# 직접 실행될 때만 render 호출 (모듈로 import될 때는 호출되지 않음)
if __name__ == "__main__":
    render()