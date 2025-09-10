import streamlit as st
from pathlib import Path
import datetime
import sys
import os
import re
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
        get_recommendation_summary,
        adjust_level_by_emotion,
        load_contents_from_supabase
    )
    from contents.recommendation.explanation_generator import generate_explanation
    from contents.recommendation.user_contents_logger import get_logger
    try:
        import google.generativeai as genai
    except ImportError:
        genai = None
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

def get_emotion_status(emotion_score):
    """감정 점수를 사용자 친화적인 표현으로 변환"""
    if emotion_score >= 30:
        return {
            "status": "매우 긍정적",
            "emoji": "😊",
            "description": "투자에 대한 기대감이 높은 상태",
            "color": "#28a745",
            "range": "30점 이상"
        }
    elif emotion_score >= 10:
        return {
            "status": "긍정적", 
            "emoji": "🙂",
            "description": "투자에 대해 낙관적인 마음가짐",
            "color": "#20c997",
            "range": "10~29점"
        }
    elif emotion_score >= -10:
        return {
            "status": "중립적",
            "emoji": "😐", 
            "description": "평온하고 균형잡힌 투자 심리",
            "color": "#6c757d",
            "range": "-10~9점"
        }
    elif emotion_score >= -30:
        return {
            "status": "다소 불안",
            "emoji": "😟",
            "description": "투자에 대한 약간의 우려가 있는 상태",
            "color": "#fd7e14",
            "range": "-30~-11점"
        }
    else:
        return {
            "status": "불안감 높음",
            "emoji": "😔",
            "description": "투자에 대한 걱정이 많은 상태",
            "color": "#dc3545",
            "range": "-30점 미만"
        }

def get_risk_tolerance_status(risk_score):
    """위험 허용도를 사용자 친화적인 표현으로 변환"""
    if risk_score >= 80:
        return {
            "status": "적극적 투자 성향",
            "emoji": "🚀",
            "description": "높은 수익을 위해 큰 위험도 감수할 수 있음",
            "color": "#dc3545",
            "range": "80점 이상"
        }
    elif risk_score >= 60:
        return {
            "status": "공격적 투자 성향",
            "emoji": "📈",
            "description": "적당한 위험을 감수하며 수익 추구",
            "color": "#fd7e14",
            "range": "60~79점"
        }
    elif risk_score >= 40:
        return {
            "status": "균형 잡힌 투자 성향",
            "emoji": "⚖️",
            "description": "안정성과 수익성의 적절한 균형 선호",
            "color": "#20c997",
            "range": "40~59점"
        }
    elif risk_score >= 20:
        return {
            "status": "보수적 투자 성향",
            "emoji": "🛡️",
            "description": "안정성을 중시하며 낮은 위험 선호",
            "color": "#6f42c1",
            "range": "20~39점"
        }
    else:
        return {
            "status": "매우 보수적 투자 성향",
            "emoji": "🏦",
            "description": "원금 보장을 최우선으로 하는 안전 투자",
            "color": "#28a745",
            "range": "20점 미만"
        }

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
        if not genai:
            return 0
            
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return 0
            
        try:
            if genai and hasattr(genai, 'configure') and hasattr(genai, 'GenerativeModel'):
                configure_func = getattr(genai, 'configure')
                model_class = getattr(genai, 'GenerativeModel')
                configure_func(api_key=api_key)
                model = model_class('gemini-1.5-flash')
            else:
                return 0
        except (AttributeError, Exception):
            return 0
        
        prompt = f"""
        다음은 사용자의 투자 관련 감정 상태입니다: {emotions_text}
        
        이 감정들을 분석해서 전체적인 감정 점수를 -50부터 +50 사이의 숫자로 평가해주세요.
        
        평가 기준:
        - 긍정적 감정 (기대감, 설렘, 자신감, 희망 등): +점수
        - 부정적 감정 (불안감, 걱정, 두려움 등): -점수
        - 중립적 감정 (평범함, 보통 등): 0 근처
        
        결과는 숫자만 답해주세요. 예: 15 또는 -20
        """
        
        response = model.generate_content(prompt)
        score_text = response.text.strip()
        
        # 숫자 추출
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
# UI 렌더링 헬퍼 함수들
# ================== 
def render_user_profile_card(profile_data):
    """사용자 프로필 카드 렌더링"""
    user_name = profile_data['user_name']
    user_level = profile_data['user_level']
    knowledge_level = profile_data['knowledge_level']
    emotions = profile_data['emotions']
    interest_tags = profile_data['interest_tags']
    risk_tolerance = profile_data['risk_tolerance']
    
    emotion_info = get_emotion_status(emotions)
    risk_info = get_risk_tolerance_status(risk_tolerance)
    
    main_profile_text = f"""
    <p>👋 안녕하세요, <strong>{user_name}</strong>님! 챗봇과 퀴즈로 분석한 당신의 금융 프로필을 알려드릴게요.</p>
    <br>
    <p>🏦 <strong>금융 지식 수준:</strong> {user_level} ({knowledge_level})</p>
    <p>💭 <strong>현재 투자 심리:</strong> {emotion_info['emoji']} {emotion_info['status']}</p>
    <p>📊 <strong>투자 성향:</strong> {risk_info['emoji']} {risk_info['status']}</p>
    <p>💡 <strong>관심 분야:</strong> {', '.join(interest_tags) if interest_tags else '아직 설정되지 않음'}</p>
    <br>
    <p>이제 금융 프로필을 바탕으로 <strong>{user_name}</strong>님의 지식 레벨을 높일 시간입니다. 맞춤 추천 받기 버튼을 누르면 당신을 위한 맞춤 정보가 추천됩니다.🙌</p>
    """
    
    st.markdown(f'<div class="profile-card" style="height: 385px;">{main_profile_text}</div>', unsafe_allow_html=True)

def render_user_analysis_cards(profile_data):
    """사용자 분석 결과 카드들 렌더링"""
    user_name = profile_data['user_name']
    user_summary = profile_data['user_summary']
    knowledge_summary = profile_data['knowledge_summary']
    
    # 퀴즈 스타일 CSS
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
    
    # 투자 성향 분석
    if user_summary and user_summary.strip() and user_summary not in ['NULL', 'null', 'None']:
        content = user_summary
    else:
        content = f"💬 {user_name}님, 챗봇과 대화를 나누시면 투자 성향을 분석해드릴게요!"
    
    st.markdown(f"""
    <div class="quiz-header">📑 {user_name}님의 투자 성향</div>
    <div class="quiz-card"><div class="quiz-content">{content}</div></div>
    """, unsafe_allow_html=True)
    
    # 금융 지식 수준 분석
    if knowledge_summary and knowledge_summary.strip() and knowledge_summary not in ['NULL', 'null', 'None']:
        content = knowledge_summary
    else:
        content = f"📝 {user_name}님, 퀴즈를 완료하시면 금융 지식 수준을 분석해드릴게요!"
    
    st.markdown(f"""
    <div class="quiz-header">🎓 {user_name}님의 금융 레벨</div>
    <div class="quiz-card"><div class="quiz-content">{content}</div></div>
    """, unsafe_allow_html=True)

# ================== 
# 사용자 뷰
# ================== 
def render_user_view():
    """사용자 뷰 메인 렌더링 함수"""
    # 헤더
    st.title("🕹️ 맞춤 금융 지식")
    st.caption("당신의 관심사와 금융 레벨 따라 추천된 맞춤 금융 지식를 확인해보세요!")

    # 사용자 데이터 파싱
    profile_data = parse_user_profile_data()
    knowledge_level = profile_data['knowledge_level']
    emotions = profile_data['emotions']
    interest_tags = profile_data['interest_tags']
    user_summary = profile_data['user_summary']
    knowledge_summary = profile_data['knowledge_summary']
    
    top_n = st.session_state.get('top_n', 3)
    use_llm_rerank = st.session_state.get('use_llm_rerank', True)

    # 2x2 그리드 레이아웃
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.markdown('### 📋 나의 금융 프로필')
        render_user_profile_card(profile_data)
    
    with col_right:
        render_user_analysis_cards(profile_data)

    # 맞춤 콘텐츠 추천 버튼
    if 'recommendation_result' not in st.session_state:
        if st.button("💫 맞춤 추천 받기", use_container_width=True):
            if not interest_tags:
                st.warning("관심 분야를 최소 1개 선택해주세요!")
                st.stop()
            spinner_text = "🐾 AI가 맞춤 정보를 찾고 있어요..." if use_llm_rerank else "🚥 맞춤 정보를 찾고 있어요..."
            with st.spinner(spinner_text):
                rec_result = get_hybrid_recommendations({
                    "user_id": f"user_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "level": knowledge_level,
                    "emotions": emotions,
                    "interest_tags": interest_tags,
                    "recent_seen_card_ids": [],
                    "liked_tags": [],
                    "user_summary": user_summary,
                    "knowledge_summary": knowledge_summary
                }, top_n=top_n, use_llm_rerank=use_llm_rerank)
            if rec_result["success"]:
                st.session_state['recommendation_result'] = rec_result
                st.session_state['shown_recommendations'] = rec_result['results']
                st.rerun()
            else:
                st.error("추천을 가져올 수 없어요. 잠시 후 다시 시도해주세요.")

    st.divider()

    # 추천 콘텐츠 카드 및 재추천 로직
    if 'shown_recommendations' in st.session_state:
        st.success("✨ 맞춤 정보가 추천되었습니다!")
        st.markdown('### 🚀 나만의 맞춤 추천')

        results = st.session_state['shown_recommendations']
        
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
                                content_description=content.get('content','')[:300],
                                contents_id=content.get('id')
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

        # 재추천 버튼
        st.divider()
        rec_result = st.session_state['recommendation_result']
        all_candidates = rec_result['metadata']['all_candidates']
        shown_ids = {c['card_id'] for c in st.session_state['shown_recommendations']}
        more_available = len(all_candidates) > len(shown_ids)

        if more_available:
            if st.button("🔄 새로운 맞춤 정보 더 보기", use_container_width=True):
                with st.spinner("피드백을 반영하여 새로운 정보를 찾고 있어요..."):
                    base_scores = rec_result['metadata']['base_scores']
                    
                    previous_results = st.session_state['shown_recommendations']
                    
                    # Gather feedback
                    feedback = {'liked': [], 'disliked': []}
                    for content in previous_results:
                        card_identifier = content.get('card_id', content.get('id'))
                        feedback_key = f"feedback_recorded_{card_identifier}"
                        if feedback_key in st.session_state:
                            if st.session_state[feedback_key] == 'positive':
                                feedback['liked'].append(content)
                            elif st.session_state[feedback_key] == 'negative':
                                feedback['disliked'].append(content)
                    
                    analysis = load_and_analyze_contents()
                    if not analysis:
                        st.error("콘텐츠 데이터를 불러올 수 없어 재추천할 수 없습니다.")
                        st.stop()
                    
                    all_contents = analysis['raw_contents']
                    card_map = {str(c.get("card_id")): c for c in all_contents}

                    scores_to_sort = base_scores.copy()
                    if feedback['liked'] or feedback['disliked']:
                        boost_tags = set()
                        for item in feedback['liked']:
                            boost_tags.update(safe_tags(item.get('tags', [])))

                        penalize_tags = set()
                        for item in feedback['disliked']:
                            penalize_tags.update(safe_tags(item.get('tags', [])))

                        for cid in all_candidates:
                            if cid not in card_map: continue
                            content_tags = set(safe_tags(card_map[cid].get('tags', [])))
                            
                            if boost_tags.intersection(content_tags):
                                scores_to_sort[cid] = scores_to_sort.get(cid, 0.0) + 0.2
                            if penalize_tags.intersection(content_tags):
                                scores_to_sort[cid] = scores_to_sort.get(cid, 0.0) - 0.3
                    
                    sorted_candidates = sorted(scores_to_sort.keys(), key=lambda cid: scores_to_sort.get(cid, 0.0), reverse=True)

                    top_n = st.session_state.get('top_n', 3)
                    new_rec_ids = []
                    for cid in sorted_candidates:
                        if cid not in shown_ids:
                            new_rec_ids.append(cid)
                        if len(new_rec_ids) >= top_n:
                            break
                    
                    if new_rec_ids:
                        new_results = [card_map[cid] for cid in new_rec_ids if cid in card_map]
                        for i, content in enumerate(new_results):
                            content['recommendation_reason'] = f"새로운 추천: 이전 학습 내용과 피드백을 반영하여 추천되었습니다."
                            content['recommendation_source'] = 'reranked'
                            content['recommendation_rank'] = len(results) + i + 1
                        
                        st.session_state['shown_recommendations'].extend(new_results)
                        st.rerun()
                    else:
                        st.info("더 이상 추천해드릴 새로운 콘텐츠가 없습니다. 😃")
        else:
            st.info("모든 추천 후보를 확인했습니다. 😃")

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
                                # Supabase 날짜 형식 파싱 (microseconds 자리수 문제 해결)
                                try:
                                    viewed_at_str = log_item['viewed_at'].replace('Z', '+00:00')
                                    # microseconds가 5자리인 경우 6자리로 패딩
                                    viewed_at_str = re.sub(r'\.(\d{5})\+', r'.\g<1>0+', viewed_at_str)
                                    viewed_at = datetime.datetime.fromisoformat(viewed_at_str)
                                except ValueError:
                                    # 파싱 실패시 현재 시간 사용
                                    viewed_at = datetime.datetime.now()
                                st.write(f"조회 시간: {viewed_at.strftime('%m/%d %H:%M')}")
                else:
                    st.info("아직 조회한 콘텐츠가 없습니다. 맞춤 추천을 받아보세요!")
            else:
                st.info("로그인 후 학습 히스토리를 확인할 수 있습니다.")
    except Exception as e:
        st.warning("학습 히스토리를 불러올 수 없습니다.")
        print(f"히스토리 로드 실패: {e}")

    # 학습 현황
    if 'recommendation_result' in st.session_state:
        st.divider() 
        st.markdown('### 📊 현재 세션 학습 현황')
        
        rec_result = st.session_state['recommendation_result']
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
    st.caption("개발자를 위한 분석 페이지 입니다. 룰베이스 + 벡터 서치 기반으로 하이브리드 방식으로 리랭킹 되어 추천되고 있는 상세 결과를 확인하세요.")
    
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
    
    # 하이브리드 추천 시스템 아키텍처 설명
    st.markdown('### 🏗️ 하이브리드 추천 시스템 아키텍처')
    
    # 전체 프로세스 플로우 차트 (깔끔한 단색 톤)
    st.markdown("""
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
    """, unsafe_allow_html=True)
    
    # 상세 설명을 탭으로 구성
    tab1, tab2, tab3 = st.tabs(["🎯 1단계: 후보군 수집", "⚖️ 2단계: 수치 리랭킹", "🎖️ 3단계: LLM 컨텍스트 리랭킹"])
    
    with tab1:
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
            """
            )
        
        with col2:
            st.markdown("""
            **🧠 벡터 검색**
            - **다중 모델**: BGE-M3, KO-SRoBERTa
            - **컨텍스트 임베딩**: 사용자 프로필 기반
            - **FAISS 인덱스**: 고속 유사도 검색
            
            **📊 매개변수:**
            - 후보 수: 10개  
            - 유사도 임계값: 0.15
            - 레벨 필터링: 사전 적용
            """
            )
            
        with col3:
            st.markdown("""
            **📋 기본 룰**
            - **레벨 매칭**: 사용자 지식 수준 일치
            - **태그 매칭**: 관심사 기반 필터링
            - **중복 제거**: 기존 조회 콘텐츠 제외
            
            **📊 매개변수:**
            - 후보 수: 10개
            - 레벨 필터링: 엄격 모드
            - 태그 점수 가중치: 40%
            """
            )
    
    with tab2:
        st.markdown("#### 수치 기반 리랭킹 공식")
        
        st.latex(r"""
        Score_{final} = \alpha \times Score_{vector} + \beta \times Score_{level} + \gamma \times Score_{tag}
        """,)
        
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
        """
        )
    
    with tab3:
        st.markdown("#### GPT-4o-mini 컨텍스트 리랭킹")
        
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
            """
            )
        
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
            """
            )
    
    st.divider()
    
    # 현재 설정 요약
    st.markdown('### 📊 현재 시스템 설정 요약')
    
    # 성능 지표를 깔끔한 카드 형태로 표시
    metric_cols = st.columns(4)
    
    with metric_cols[0]:
        st.markdown("""
        <div style="background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid #e9ecef;">
            <h4 style="color: #495057; margin: 0; font-size: 14px; font-weight: 600;">후보군 크기</h4>
            <p style="font-size: 28px; font-weight: 700; margin: 8px 0; color: #212529;">~20개</p>
            <small style="color: #6c757d;">룰베이스 + 벡터서치</small>
        </div>
        """, unsafe_allow_html=True)
    
    with metric_cols[1]:
        st.markdown("""
        <div style="background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid #e9ecef;">
            <h4 style="color: #495057; margin: 0; font-size: 14px; font-weight: 600;">리랭킹 방식</h4>
            <p style="font-size: 28px; font-weight: 700; margin: 8px 0; color: #212529;">2단계</p>
            <small style="color: #6c757d;">수치 → LLM</small>
        </div>
        """, unsafe_allow_html=True)
    
    with metric_cols[2]:
        st.markdown("""
        <div style="background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid #e9ecef;">
            <h4 style="color: #495057; margin: 0; font-size: 14px; font-weight: 600;">개인화 수준</h4>
            <p style="font-size: 28px; font-weight: 700; margin: 8px 0; color: #212529;">HIGH</p>
            <small style="color: #6c757d;">컨텍스트 분석</small>
        </div>
        """, unsafe_allow_html=True)
    
    with metric_cols[3]:
        st.markdown("""
        <div style="background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid #e9ecef;">
            <h4 style="color: #495057; margin: 0; font-size: 14px; font-weight: 600;">처리 속도</h4>
            <p style="font-size: 28px; font-weight: 700; margin: 8px 0; color: #212529;">~3초</p>
            <small style="color: #6c757d;">LLM 포함</small>
        </div>
        """, unsafe_allow_html=True)

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
        emotion_info = get_emotion_status(emotions)
        st.metric("현재 투자 심리", f"{emotion_info['emoji']} {emotion_info['status']}", delta=f"{emotions}점")
    
    st.info(f"**조정 사유**: {reason}")
    
    # 감정 점수 분류 기준 표시 (관리자용)
    with st.expander("📊 감정 점수 분류 기준"):
        st.markdown("""
        | 점수 범위 | 상태 | 설명 | 추천 전략 |
        |-----------|------|------|-----------|
        | 30점 이상 | 😊 매우 긍정적 | 투자에 대한 기대감이 높음 | 도전적인 콘텐츠 추천 |
        | 10~29점 | 🙂 긍정적 | 낙관적인 마음가짐 | 성장 지향 콘텐츠 |
        | -10~9점 | 😐 중립적 | 균형잡힌 투자 심리 | 기본 수준 콘텐츠 |
        | -30~-11점 | 😟 다소 불안 | 약간의 우려 있음 | 안정적인 콘텐츠 우선 |
        | -30점 미만 | 😔 불안감 높음 | 투자 걱정이 많음 | 쉽고 안전한 콘텐츠로 하향 조정 |
        """
        )
        
        profile_data = parse_user_profile_data()
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
        """
        )
    

    st.divider()

    # 추천 결과 상세 분석
    if 'recommendation_result' in st.session_state:
        rec_result = st.session_state['recommendation_result']
        if rec_result.get("success"):
            st.markdown('### 📊 추천 결과 상세 분석')
            
            # 전체 요약
            st.success(get_recommendation_summary(rec_result))
            
            results = rec_result["results"]
            metadata = rec_result["metadata"]
            
            # 성능 지표 (LLM 리랭킹 정보 포함)
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
                    col_left, col_right = st.columns([1, 1])

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
                        st.markdown("**AI 생성 맞춤 설명**")
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
                        topic_mapping = {2: "경제", 4: "과학", 5: "금융", 6: "사회"}
                        topic_id = content.get('topic_id')
                        category_name = topic_mapping.get(topic_id, content.get('category', 'Unknown'))
                        st.write(f"- **카테고리**: {category_name}")
            
            # 메타데이터 상세 분석
            with st.expander("🔧 메타데이터 상세 분석"):
                # LLM 리랭킹 정보 (있는 경우)
                llm_info = metadata.get('llm_rerank_info', {})
                if llm_info.get('llm_used', False):
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
                            # 전체 콘텐츠에서 제목 매핑 (Supabase에서 로드)
                            try:
                                from contents.recommendation.hybrid_recommender_v2 import load_contents_from_supabase
                                all_contents = load_contents_from_supabase()
                                card_titles = {content.get("card_id"): content.get("title", "제목 없음") for content in all_contents}
                            except:
                                # 백업: 결과에서 가져오기
                                results = rec_result.get("results", [])
                                card_titles = {content.get("card_id"): content.get("title", "제목 없음") for content in results}
                            
                            for cid, score in list(context_scores.items())[:3]:  # 상위 3개만 표시
                                title = card_titles.get(cid, "제목 로드 실패")
                                # 제목이 너무 길면 잘라서 표시
                                display_title = title[:25] + "..." if len(title) > 25 else title
                                st.write(f"- **{display_title}**: {score:.3f}")
                                st.caption(f"ID: {cid[:8]}")
                    
                    # LLM 원시 응답 (제목 포함)
                    if llm_info.get('llm_raw_response'):
                        with st.expander("LLM 원시 응답 보기"):
                            raw_response = llm_info['llm_raw_response']
                            
                            # 원시 응답에 제목 정보 추가
                            try:
                                # 전체 콘텐츠에서 제목 매핑
                                try:
                                    from contents.recommendation.hybrid_recommender_v2 import load_contents_from_supabase
                                    all_contents = load_contents_from_supabase()
                                    card_titles = {content.get("card_id"): content.get("title", "제목 없음") for content in all_contents}
                                except:
                                    card_titles = {}
                                
                                # LLM이 평가한 후보들의 card_id 추출
                                context_scores = llm_info.get('context_scores', {})
                                if context_scores and card_titles:
                                    st.markdown("**📋 평가된 콘텐츠 목록:**")
                                    for i, (cid, score) in enumerate(context_scores.items(), 1):
                                        title = card_titles.get(cid, "제목 로드 실패")
                                        st.write(f"**후보 {i}**: {title} (점수: {score:.3f})")
                                    st.divider()
                                
                                st.markdown("**GPT-4o-mini 원시 응답:**")
                                st.code(raw_response, language="text")
                            except Exception as e:
                                st.code(raw_response, language="text")
                    st.divider()
                
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
        
        # LLM 컨텍스트 리랭킹 옵션 추가
        use_llm_rerank = st.checkbox(
            "AI 컨텍스트 리랭킹", 
            value=st.session_state.get('use_llm_rerank', True),
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
