import streamlit as st
from pathlib import Path
import datetime
import sys, os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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
        adjust_level_by_emotion,
        load_contents_from_supabase
    )
    from contents.recommendation.explanation_generator import generate_explanation
    from contents.recommendation.user_contents_logger import get_logger
    import google.generativeai as genai
    from supabase import create_client, Client
    import os
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
# Gemini를 활용한 감정 점수 분석
# ==================
@st.cache_data(ttl=300)  # 5분 캐싱
def analyze_emotion_score_with_gemini(emotions_text):
    """Gemini를 사용해서 감정 텍스트를 점수로 변환 (-50 ~ +50)"""
    if not emotions_text or emotions_text in ['[]', '{}', 'null']:
        return 0
    
    try:
        # Gemini API 초기화
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return 0
            
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        다음은 사용자의 투자 관련 감정 상태입니다: {emotions_text}
        
        이 감정들을 분석해서 전체적인 감정 점수를 -50부터 +50 사이의 숫자로 평가해주세요.
        
        평가 기준:
        - 긍정적 감정 (기대감, 설렘, 자신감, 희망 등): +점수
        - 부정적 감정 (불안감, 걱정, 후회, 두려움 등): -점수
        - 중립적 감정 (평범함, 보통 등): 0 근처
        
        결과는 숫자만 답해주세요. 예: 15 또는 -20
        """
        
        response = model.generate_content(prompt)
        score_text = response.text.strip()
        
        # 숫자 추출
        import re
        numbers = re.findall(r'-?\d+', score_text)
        if numbers:
            score = int(numbers[0])
            return max(-50, min(50, score))  # -50~50 범위로 제한
        return 0
        
    except Exception as e:
        st.warning(f"감정 분석 중 오류: {e}")
        return 0

def parse_user_profile_data():
    """Supabase profiles 테이블 데이터를 파싱해서 UI용 데이터로 변환"""
    user_data = st.session_state.get('user_data', {})
    
    # 사용자 이름 추출
    user_name = user_data.get('name', '사용자님')
    
    # knowledge_level 변환
    knowledge_level = user_data.get('knowledge_level', 'Beginner')
    level_mapping = {'Beginner': '입문자', 'Intermediate': '중급자', 'Advanced': '고급자'}
    user_level = level_mapping.get(knowledge_level, '입문자')
    
    # investment_emotions를 Gemini로 분석
    investment_emotions_raw = user_data.get('investment_emotions', '[]')
    emotions_score = analyze_emotion_score_with_gemini(str(investment_emotions_raw))
    
    # interests_categories 파싱
    interests_categories = user_data.get('interests_categories', '[]')
    if isinstance(interests_categories, str):
        try:
            import json
            interests_categories = json.loads(interests_categories)
        except:
            interests_categories = []
    
    # user_summary와 knowledge_summary 추출
    user_summary = user_data.get('user_summary', '').strip()
    knowledge_summary = user_data.get('knowledge_summary', '').strip()
    
    return {
        'user_name': user_name,
        'user_level': user_level,
        'knowledge_level': knowledge_level,
        'emotions': emotions_score,
        'interest_tags': interests_categories,
        'user_summary': user_summary,
        'knowledge_summary': knowledge_summary,
        'risk_tolerance': user_data.get('risk_tolerance', 50),
        'investment_goal': user_data.get('investment_goal', ''),
        'investment_level': user_data.get('investment_level', 'None')
    }

# ==================
# 사용자 뷰
# ==================
def render_user_view():
    
    # 헤더
    st.title("🕹️ 맞춤 금융 지식")
    st.caption("당신의 수준과 관심사에 따라 추천된 맞춤형 금융 정보를 확인해보세요!")

    # Supabase profiles 테이블에서 실제 사용자 데이터 파싱 (읽기 전용)
    profile_data = parse_user_profile_data()
    user_name = profile_data['user_name']
    user_level = profile_data['user_level']
    knowledge_level = profile_data['knowledge_level']
    emotions = profile_data['emotions']
    interest_tags = profile_data['interest_tags']
    user_summary = profile_data['user_summary']
    knowledge_summary = profile_data['knowledge_summary']
    risk_tolerance = profile_data['risk_tolerance']
    
    top_n = st.session_state.get('top_n', 3)

    # 2x2 그리드 레이아웃: 왼쪽(프로필) | 오른쪽(분석 결과들)
    col_left, col_right = st.columns([1, 1])
    
    # 왼쪽: 메인 금융 프로필 카드
    with col_left:
        st.markdown('### 📋 나의 금융 프로필')
        
        # 감정 상태에 따른 이모지
        emotion_emoji = "😊" if emotions > 10 else "😔" if emotions < -10 else "😐"
        
        main_profile_text = f"""
        <p>👋 안녕하세요, <strong>{user_name}</strong>님! 챗봇과 퀴즈로 분석한 당신의 금융 프로필을 알려드릴게요.</p>
        <br>
        <p>🏦 <strong>금융 지식 수준:</strong> {user_level} ({knowledge_level})</p>
        <p>🔥 <strong>현재 감정 점수:</strong> {emotion_emoji} {emotions}점 (-50~+50)</p>
        <p>📊 <strong>위험 허용도:</strong> {risk_tolerance}점</p>
        <p>💡 <strong>관심 분야:</strong> {', '.join(interest_tags) if interest_tags else '아직 설정되지 않음'}</p>
        <br>
        <p>이제 금융 프로필을 바탕으로 <strong>{user_name}</strong>님의 지식 레벨을 높일 시간입니다. 맞춤 추천 받기 버튼을 누르면 당신을 위한 맞춤 정보가 추천됩니다.🙌</p>
        """
        
        st.markdown(f'<div class="profile-card" style="height: 385px;">{main_profile_text}</div>', unsafe_allow_html=True)
    
    # 오른쪽: 분석 결과들 (퀴즈 UI 스타일)
    with col_right:
        # 퀴즈 스타일 CSS 추가
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
        
        # 상단: AI 투자 성향 분석
        if user_summary and user_summary.strip() and user_summary not in ['NULL', 'null', 'None']:
            st.markdown(f"""
            <div class="quiz-header">
                📑 {user_name}님의 투자 성향
            </div>
            <div class="quiz-card">
                <div class="quiz-content">
                    {user_summary}
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="quiz-header">
                📑 {user_name}님의 투자 성향
            </div>
            <div class="quiz-card">
                <div class="quiz-content">
                    💬 {user_name}님, 챗봇과 대화를 나누시면 투자 성향을 분석해드릴게요!
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # 하단: 금융 지식 수준 분석
        if knowledge_summary and knowledge_summary.strip() and knowledge_summary not in ['NULL', 'null', 'None']:
            st.markdown(f"""
            <div class="quiz-header">
                🎓 {user_name}님의 금융 레벨 
            </div>
            <div class="quiz-card">
                <div class="quiz-content">
                    {knowledge_summary}
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="quiz-header">
                🎓 {user_name}님의 금융 레벨 
            </div>
            <div class="quiz-card">
                <div class="quiz-content">
                    📝 {user_name}님, 퀴즈를 완료하시면 금융 지식 수준을 분석해드릴게요!
                </div>
            </div>
            """, unsafe_allow_html=True)

    # 맞춤 콘텐츠 추천 버튼 
    if 'last_recommendation' not in st.session_state:
        if st.button("💫 맞춤 추천 받기", use_container_width=True):
            if not interest_tags:
                st.warning("관심 분야를 최소 1개 선택해주세요!")
                st.stop()
            with st.spinner("🚥 AI가 맞춤 정보를 찾고 있어요..."):
                rec_result = get_hybrid_recommendations({
                    "user_id": f"user_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "level": knowledge_level,
                    "emotions": emotions,
                    "interest_tags": interest_tags,
                    "recent_seen_card_ids": [],
                    "liked_tags": []
                }, top_n=top_n)
            if rec_result["success"]:
                st.session_state['last_recommendation'] = rec_result
                st.rerun()
            else:
                st.error("추천을 가져올 수 없어요. 잠시 후 다시 시도해주세요.")
    else:
        # 추천 완료 안내 메시지
        st.success("✨ 맞춤 정보가 추천되었습니다!")

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
                card_identifier = content.get('card_id', content.get('id', i))
                explanation_key = f"explanation_{card_identifier}"
                log_id_key = f"log_id_{card_identifier}"

                with col_btn:
                    if st.button("💡 AI 맞춤 설명", key=f"user_explain_btn_{card_identifier}"):
                        with st.spinner("당신을 위한 맞춤 설명을 만들고 있어요..."):
                            try:
                                explanation = generate_explanation(
                                    level=knowledge_level,
                                    content_title=content.get('title',''),
                                    content_description=content.get('content','')[:300]
                                )
                                st.session_state[explanation_key] = explanation
                                
                                # 실시간 로그 저장
                                try:
                                    supabase_client = st.session_state.get("supabase")
                                    logger = get_logger(supabase_client)
                                    if logger:
                                        user_data = st.session_state.get('user_data', {})
                                        user_id = user_data.get('id', 'anonymous')
                                        contents_id_for_log = content.get('id')

                                        if contents_id_for_log:
                                            user_context = {
                                                'emotions': emotions,
                                                'interest_tags': interest_tags,
                                                'risk_tolerance': profile_data.get('risk_tolerance', 50),
                                                'investment_goal': profile_data.get('investment_goal', ''),
                                                'user_summary': profile_data.get('user_summary', ''),
                                                'knowledge_summary': profile_data.get('knowledge_summary', '')
                                            }
                                            
                                            log_id = logger.log_content_view(
                                                user_id=str(user_id),
                                                contents_id=contents_id_for_log,
                                                content_title=content.get('title', ''),
                                                original_content=content.get('content', ''),
                                                ai_explanation=explanation,
                                                user_level=knowledge_level,
                                                user_context=user_context,
                                                recommendation_source=content.get('recommendation_source', 'unknown'),
                                                recommendation_rank=content.get('recommendation_rank', i)
                                            )
                                            if log_id:
                                                st.session_state[log_id_key] = log_id
                                        else:
                                            st.warning(f"콘텐츠의 UUID가 없어 로그 저장이 불가능합니다: card_id={content.get('card_id')}")

                                except Exception as log_error:
                                    st.error(f"로그 저장 중 오류 발생: {log_error}")
                                
                                st.success("✅ 설명이 준비됐어요!")
                            except Exception as e:
                                st.error(f"설명을 만들 수 없어요 😅: {e}")
                
                with col_exp:
                    if explanation_key in st.session_state:
                        st.markdown(
                            f'<div class="ai-explanation">{st.session_state[explanation_key]}</div>',
                            unsafe_allow_html=True
                        )
                        
                        # 피드백 버튼
                        feedback_recorded_key = f"feedback_recorded_{card_identifier}"
                        if log_id_key in st.session_state and feedback_recorded_key not in st.session_state:
                            st.write("이 설명이 도움이 되었나요?")
                            fb_cols = st.columns([1, 1, 8])
                            with fb_cols[0]:
                                if st.button("👍", key=f"fb_pos_{card_identifier}"):
                                    supabase_client = st.session_state.get("supabase")
                                    logger = get_logger(supabase_client)
                                    if logger:
                                        logger.log_feedback(st.session_state[log_id_key], 'positive')
                                        st.toast("피드백 감사합니다! 👍")
                                        st.session_state[feedback_recorded_key] = 'positive'
                                        st.rerun()
                            with fb_cols[1]:
                                if st.button("👎", key=f"fb_neg_{card_identifier}"):
                                    supabase_client = st.session_state.get("supabase")
                                    logger = get_logger(supabase_client)
                                    if logger:
                                        logger.log_feedback(st.session_state[log_id_key], 'negative')
                                        st.toast("피드백 감사합니다! 개선에 참고할게요.")
                                        st.session_state[feedback_recorded_key] = 'negative'
                                        st.rerun()
                        elif feedback_recorded_key in st.session_state:
                            if st.session_state[feedback_recorded_key] == 'positive':
                                st.success("👍 피드백이 반영되었습니다.")
                            else:
                                st.warning("👎 아쉬운 점을 알려주셔서 감사합니다.")

                # 태그
                tags = safe_tags(content.get('tags', []))
                if tags:
                    tag_html = ''.join([f'<span class="tag">#{t}</span>' for t in tags[:4]])
                    st.markdown(tag_html, unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)

    # 이전 조회 콘텐츠 히스토리
    st.divider()
    st.markdown('### 📚 나의 학습 히스토리')
    
    try:
        supabase_client = st.session_state.get("supabase")
        logger = get_logger(supabase_client)
        if logger:
            user_data = st.session_state.get('user_data', {})
            user_id = user_data.get('id', 'anonymous')
            
            if user_id != 'anonymous':
                history = logger.get_user_content_history(str(user_id), limit=10)
                
                if history:
                    st.markdown(f"**최근 확인한 콘텐츠 {len(history)}개**")
                    
                    for idx, log_item in enumerate(history[:5], 1):
                        with st.expander(f"{idx}. {log_item['content_title']} ({log_item['user_level']})", expanded=False):
                            col_hist1, col_hist2 = st.columns([3, 1])
                            
                            with col_hist1:
                                # AI 설명 표시
                                if log_item.get('ai_explanation'):
                                    st.markdown("**AI 설명:**")
                                    st.markdown(
                                        f'<div class="ai-explanation">{log_item["ai_explanation"]}</div>',
                                        unsafe_allow_html=True
                                    )
                                
                                # 피드백이 있는 경우 표시
                                if log_item.get('feedback_type'):
                                    feedback_emoji = {"positive": "👍", "neutral": "😐", "negative": "👎"}
                                    feedback_text = {"positive": "도움됨", "neutral": "보통", "negative": "아쉬움"}
                                    st.success(f"{feedback_emoji.get(log_item['feedback_type'], '❓')} {feedback_text.get(log_item['feedback_type'], '알 수 없음')}으로 평가")
                            
                            with col_hist2:
                                st.markdown("**📊 상세 정보**")
                                viewed_at = datetime.datetime.fromisoformat(log_item['viewed_at'].replace('Z', '+00:00'))
                                st.write(f"조회 시간: {viewed_at.strftime('%m/%d %H:%M')}")
                else:
                    st.info("아직 조회한 콘텐츠가 없습니다. 맞춤 추천을 받아보세요!")
            else:
                st.info("로그인 후 학습 히스토리를 확인할 수 있습니다.")
    except Exception as e:
        st.warning("학습 히스토리를 불러올 수 없습니다.")
        print(f"히스토리 로드 실패: {e}")

    # 학습 현황
    if 'last_recommendation' in st.session_state:
        st.divider() 
        st.markdown('### 📊 현재 세션 학습 현황')
        
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
# 콘텐츠 데이터 시각화 함수들
# ==================

@st.cache_data(ttl=600)  # 10분 캐싱
def load_and_analyze_contents():
    """Supabase에서 콘텐츠 데이터를 로드하고 분석"""
    try:
        all_contents = load_contents_from_supabase()
        
        # topic_id를 카테고리명으로 매핑
        topic_mapping = {
            2: "경제",
            4: "과학", 
            5: "금융",
            6: "사회"
        }
        
        # topic_id를 카테고리명으로 변환
        for content in all_contents:
            topic_id = content.get('topic_id')
            if topic_id in topic_mapping:
                content['category_name'] = topic_mapping[topic_id]
            else:
                content['category_name'] = content.get('category', '기타')
        
        # 데이터 분석
        df = pd.DataFrame(all_contents)
        
        analysis = {
            'total_contents': len(all_contents),
            'level_distribution': df['level'].value_counts().to_dict() if 'level' in df.columns else {},
            'category_distribution': df['category_name'].value_counts().to_dict() if 'category_name' in df.columns else {},
            'contents_df': df,
            'raw_contents': all_contents
        }
        
        return analysis
    except Exception as e:
        st.error(f"콘텐츠 데이터 로드 실패: {e}")
        return None

def render_content_overview_charts():
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
    col_left, col_right = st.columns(2)
    
    with col_left:
        # 레벨별 분포 파이 차트
        if analysis['level_distribution']:
            fig_level = px.pie(
                values=list(analysis['level_distribution'].values()),
                names=list(analysis['level_distribution'].keys()),
                title="레벨별 콘텐츠 분포",
                color_discrete_map={
                    'Beginner': '#D0EBD1',  
                    'Intermediate': '#7DC679', 
                    'Advanced': '#249148'  
                }
            )
            fig_level.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_level, use_container_width=True)
    
    with col_right:
        # 카테고리별 + 난이도별 분포 스택 바 차트
        if analysis['category_distribution'] and not analysis['contents_df'].empty:
            # 카테고리별, 레벨별 데이터 준비
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
                    color_discrete_map={
                        'Beginner': "#D0EBD1",    
                        'Intermediate': "#7DC679", 
                        'Advanced': "#249148"      
                    },
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
    
    # 상세 데이터 테이블 (확장 가능)
    with st.expander("📊 콘텐츠 상세 데이터 테이블"):
        if not analysis['contents_df'].empty:
            # 주요 컬럼만 표시 (category_name 사용)
            display_columns = ['title', 'level', 'category_name', 'topic_id']
            if 'tags' in analysis['contents_df'].columns:
                display_columns.append('tags')
            
            # 존재하는 컬럼만 필터링
            available_columns = [col for col in display_columns if col in analysis['contents_df'].columns]
            filtered_df = analysis['contents_df'][available_columns] if available_columns else analysis['contents_df']
            st.dataframe(filtered_df, use_container_width=True)

# ==================
# 관리자 상세 뷰 
# ==================
def render_admin_view():
    """개발자/관리자용 상세 분석 뷰"""
    
    st.title("🔍 하이브리드 추천 시스템 분석 ")
    st.caption("개발자를 위한 분석 페이지 입니다. 룰베이스 + 벡터 서치 기반으로 하이브리드 방식으로 추천되고 있는 상세 결과를 확인하세요.")
    
    # 콘텐츠 데이터 전체 규모 시각화
    render_content_overview_charts()
    
    st.divider()
    
    # 사용자 행동 분석 대시보드
    st.markdown('### 📊 사용자 행동 분석 대시보드')
    
    try:
        supabase_client = st.session_state.get("supabase")
        logger = get_logger(supabase_client)
        if logger:
            # 전체 콘텐츠 분석
            content_analytics = logger.get_content_analytics(days=30)
            
            if content_analytics.get('total_views', 0) > 0:
                # 상단 메트릭
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
                
                # 차트 영역
                col_left, col_right = st.columns(2)
                
                with col_left:
                    # 피드백 분포 차트
                    feedback_dist = content_analytics.get('feedback_distribution', {})
                    if feedback_dist:
                        fig_feedback = px.pie(
                            values=list(feedback_dist.values()),
                            names=list(feedback_dist.keys()),
                            title="사용자 피드백 분포",
                            color_discrete_map={
                                'positive': '#4CAF50',
                                'neutral': '#FF9800', 
                                'negative': '#F44336'
                            }
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
            else:
                st.info("아직 사용자 행동 데이터가 충분하지 않습니다. 더 많은 콘텐츠 조회가 필요합니다.")
        else:
            st.error("로거 초기화에 실패했습니다.")
    except Exception as e:
        st.error(f"사용자 행동 분석을 불러올 수 없습니다: {e}")
    
    st.divider()
    
    # 메인 콘텐츠 영역에 고급 파라미터 설정
    st.markdown('### 🎛️ 하이브리드 추천 가중치 설정')
    
    st.info("""
    하이브리드 추천 시스템은 다음과 같은 가중치를 사용하여 콘텐츠를 추천합니다.
    - **벡터 검색 가중치 (α):** 0.6
    - **레벨 매칭 가중치 (β):** 0.3
    - **태그 매칭 가중치 (γ):** 0.1
    
    검색 파라미터는 다음과 같이 설정되어 있습니다.
    - **벡터 검색 후보 수:** 10
    - **룰 기반 후보 수:** 10
    - **유사도 임계값:** 0.15
    """)

    st.divider()

    # 감정 기반 레벨 조정 분석
    st.markdown('### 🧠 감정 기반 레벨 조정 분석')
    
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
        emotion_status = "😔 부정적" if emotions <= -30 else "😊 긍정적" if emotions >= 30 else "😐 중립적"
        st.metric("감정 상태", emotion_status)
    
    st.info(f"**조정 사유**: {reason}")

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
                    col_left, col_right = st.columns([2, 1])

                    with col_left:
                        # 원본 데이터와 AI 생성 설명
                        st.markdown("##### 📜 추천된 콘텐츠 상세")
                        
                        # 원본 콘텐츠
                        content_text = content.get('content', content.get('description', ''))
                        if content_text:
                            content_text = str(content_text)
                            st.markdown("**📝 원본 콘텐츠 내용**")
                            st.markdown(f'<div style="background: #f9f9f9; padding: 10px; border-radius: 5px; border-left: 3px solid #666; max-height: 200px; overflow-y: auto;">{content_text}</div>', unsafe_allow_html=True)
                        
                        st.markdown("<br>", unsafe_allow_html=True)

                        # AI 생성 설명
                        st.markdown("**🤖 AI 생성 맞춤 설명**")
                        card_identifier = content.get('card_id', content.get('id', i))
                        explanation_key = f"explanation_{card_identifier}"
                        
                        if explanation_key in st.session_state:
                            st.markdown(
                                f'<div style="background: #e8f5e8; padding: 15px; border-radius: 8px; border-left: 4px solid #4CAF50; margin: 10px 0;">'
                                f'{st.session_state[explanation_key]}</div>',
                                unsafe_allow_html=True
                            )
                        else:
                            st.info("💡 사용자가 아직 이 콘텐츠의 AI 설명을 생성하지 않았습니다.")

                    with col_right:
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

                        st.warning(f"**추천 핵심 사유**: {reason}")
                        st.divider()

                        # 기타 기본 정보
                        st.markdown("##### 📋 콘텐츠 기본 정보")
                        st.write(f"- **레벨**: {content.get('level', 'Unknown')}")
                        st.write(f"- **태그**: {', '.join(safe_tags(content.get('tags', [])))}")
                        topic_mapping = {2: "경제", 4: "과학", 5: "금융", 6: "사회"}
                        topic_id = content.get('topic_id')
                        category_name = topic_mapping.get(topic_id, content.get('category', 'Unknown'))
                        st.write(f"- **카테고리**: {category_name}")
            
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

    # 사이드바에서 추천 설정만 관리
    with st.sidebar:
        st.header("⚙️ 추천 설정")
        top_n = st.select_slider("추천 받을 개수", [1,2,3,4,5], 
                                value=st.session_state.get('top_n', 3), 
                                key="top_n_common")
        
        # 세션에 top_n만 저장
        st.session_state['top_n'] = top_n

    tab1, tab2 = st.tabs(["맞춤 금융 지식", "추천 시스템 분석"])

    with tab1:
        render_user_view()

    with tab2:
        render_admin_view()

if __name__ == "__main__":
    render()