import streamlit as st
import sys
import os
import random
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# ===========================
# 초기 설정 및 환경변수 로드
# ===========================

# 환경 변수 로드 (.env 파일에서 SUPABASE_URL, SUPABASE_KEY 읽어옴)
load_dotenv()

# 프로젝트 루트 디렉토리를 sys.path에 추가 (상대 경로 import를 위해)
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent  # my_app/ui/contents/ -> my_app/
sys.path.insert(0, str(project_root))

try:
    # AI 설명 생성 모듈 및 Supabase 클라이언트 임포트
    from contents.recomendation.explanation_generator import generate_explanation
    from supabase import create_client, Client
except ImportError as e:
    st.error(f"모듈 임포트 오류: {e}")
    st.error("필요한 모듈들을 설치하고 파일을 확인해주세요.")
    st.stop()

# ===========================
# 상수 및 샘플 데이터 정의
# ===========================

# 테스트용 샘플 사용자 데이터
SAMPLE_USERS = {
    "user1": {
        "name": "김초보",
        "knowledge_level": "Beginner",
        "emotion": "긍정",
        "emotions": 50,  # 감정 점수 (-100 ~ 100)
        "interests_categories": ["투자", "ETF", "경제"],
        "tags": ["투자", "ETF", "경제"]
    },
    "user2": {
        "name": "이절약", 
        "knowledge_level": "Intermediate",
        "emotion": "중립",
        "emotions": 0,
        "interests_categories": ["저축", "절약", "사회"],
        "tags": ["저축", "절약", "사회"]
    },
    "user3": {
        "name": "박주식",
        "knowledge_level": "Advanced", 
        "emotion": "부정",
        "emotions": -40,
        "interests_categories": ["주식", "파이어", "산업"],
        "tags": ["주식", "파이어", "산업"]
    }
}

# ===========================
# Supabase 데이터베이스 연결 클래스
# ===========================

class SupabaseConnector:
    """Supabase 데이터베이스 연결 및 데이터 조회를 담당하는 클래스"""
    
    def __init__(self):
        """Supabase 클라이언트 초기화 및 환경변수 검증"""
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        
        # 환경변수가 설정되지 않은 경우 오류 발생
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY를 .env 파일에 설정해주세요")
        
        # Supabase 클라이언트 생성
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
    
    @st.cache_data
    def load_contents(_self):
        """
        Supabase contents 테이블에서 모든 콘텐츠 데이터를 불러오는 메서드
        @st.cache_data: 데이터 캐싱으로 반복 로딩 방지
        """
        try:
            # contents 테이블의 모든 데이터 조회
            response = _self.supabase.table("contents").select("*").execute()
            
            if response.data:
                contents = []
                # 데이터베이스 결과를 표준화된 형태로 변환
                for item in response.data:
                    content = {
                        "id": item.get("id"),
                        "card_id": item.get("card_id"),
                        "title": item.get("title"),
                        "content": item.get("content"),
                        "description": item.get("content"),  # content와 description을 동일하게 처리
                        "level": item.get("level").title() if item.get("level") else "Beginner",  # 첫 글자만 대문자로
                        "style": item.get("style"),
                        "media_type": item.get("media_type"),
                        "topic_id": item.get("topic_id"),
                        "tags": item.get("tags", []),  # 태그가 없으면 빈 리스트
                        "category": item.get("category", "기타"),  # 카테고리가 없으면 '기타'
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at")
                    }
                    contents.append(content)
                return contents
            else:
                st.error("데이터베이스에서 콘텐츠를 찾을 수 없습니다.")
                return []
                
        except Exception as e:
            st.error(f"데이터베이스 연결 오류: {e}")
            return []
    
    @st.cache_data
    def load_topics(_self):
        """
        Supabase topics 테이블에서 토픽 데이터를 불러와 딕셔너리로 반환
        반환 형태: {topic_id: topic_name}
        """
        try:
            response = _self.supabase.table("topics").select("*").execute()
            return {topic["id"]: topic["name"] for topic in response.data} if response.data else {}
        except Exception as e:
            st.error(f"토픽 데이터 로드 오류: {e}")
            return {}
    
    def get_contents_by_level(self, level: str):
        """특정 지식 레벨의 콘텐츠만 조회"""
        try:
            response = self.supabase.table("contents").select("*").eq("level", level.lower()).execute()
            return response.data if response.data else []
        except Exception as e:
            st.error(f"레벨별 콘텐츠 조회 오류: {e}")
            return []
    
    def get_contents_by_topic(self, topic_id: int):
        """특정 토픽의 콘텐츠만 조회"""
        try:
            response = self.supabase.table("contents").select("*").eq("topic_id", topic_id).execute()
            return response.data if response.data else []
        except Exception as e:
            st.error(f"토픽별 콘텐츠 조회 오류: {e}")
            return []

# ===========================
# 콘텐츠 추천 시스템 클래스
# ===========================

class Recommender:
    """사용자 프로필 기반 콘텐츠 추천 시스템"""
    
    def __init__(self, contents):
        """추천 시스템 초기화"""
        self.contents = contents
        self.level_order = ["Beginner", "Intermediate", "Advanced"]  # 레벨 순서 정의

    def adjust_level_by_emotion(self, knowledge_level, emotions):
        """
        사용자의 감정 점수에 따라 학습 레벨을 동적으로 조정
        - 부정적 감정(-30 이하): 더 쉬운 레벨로 하향 조정
        - 긍정적 감정(30 이상): 더 어려운 레벨로 상향 조정
        - 중립적 감정(-29 ~ 29): 레벨 유지
        """
        try:
            idx = self.level_order.index(knowledge_level)
        except ValueError:
            # 잘못된 레벨인 경우 Beginner로 기본 설정
            idx = 0
        
        # 감정 점수에 따른 레벨 조정
        if emotions <= -30:  # 부정적 감정: 더 쉬운 레벨로
            idx = max(0, idx - 1)
        elif emotions >= 30:  # 긍정적 감정: 더 어려운 레벨로
            idx = min(len(self.level_order) - 1, idx + 1)
            
        return self.level_order[idx]

    def recommend(self, knowledge_level, interests_categories, emotions, top_k=3):
        """
        사용자 정보를 바탕으로 맞춤형 콘텐츠 추천
        
        Args:
            knowledge_level: 사용자의 지식 레벨
            interests_categories: 사용자의 관심 분야 리스트
            emotions: 사용자의 감정 점수
            top_k: 추천할 콘텐츠 개수
        
        Returns:
            추천된 콘텐츠 리스트
        """
        # 1. 감정 점수를 고려하여 적절한 레벨로 조정
        adjusted_level = self.adjust_level_by_emotion(knowledge_level, emotions)

        # 2. 조정된 레벨에 맞는 콘텐츠 후보군 필터링
        candidates = [
            c for c in self.contents
            if c.get("level") == adjusted_level
        ]

        def calculate_tag_score(content):
            """
            콘텐츠와 사용자 관심사의 일치도를 계산하는 내부 함수
            콘텐츠 태그와 사용자 관심 카테고리의 겹치는 개수를 점수로 사용
            """
            content_tags = content.get("tags", [])
            # 문자열 형태의 태그를 리스트로 변환 (쉼표로 구분된 경우)
            if isinstance(content_tags, str):
                content_tags = [tag.strip() for tag in content_tags.split(',')]
            
            # 사용자 관심사와 콘텐츠 태그의 교집합 개수 반환
            return sum(tag in interests_categories for tag in content_tags)

        # 3. 각 후보 콘텐츠에 대해 관심도 점수 계산
        scored = [(c, calculate_tag_score(c)) for c in candidates]
        
        if not scored:
            return []

        # 4. 최고 점수를 가진 콘텐츠들을 우선 선별
        max_score = max(score for _, score in scored)
        best = [c for c, score in scored if score == max_score]

        # 5. 추천 결과 선정 및 반환
        if len(best) >= top_k:
            # 최고 점수 콘텐츠가 충분하면 랜덤 샘플링
            return random.sample(best, top_k)
        else:
            # 점수 순으로 정렬하여 상위 k개 선택
            scored.sort(key=lambda x: x[1], reverse=True)
            return [c for c, _ in scored][:top_k]

# ===========================
# 유틸리티 함수들
# ===========================

def get_emotion_status(emotions):
    """감정 점수를 기반으로 감정 상태 텍스트와 색상을 반환"""
    if emotions <= -60:
        return "😭 매우 부정적", "red"
    elif emotions <= -30:
        return "😔 부정적", "orange"
    elif emotions <= -10:
        return "😐 약간 부정적", "yellow"
    elif emotions <= 29:
        return "😐 중립적", "gray"
    elif emotions <= 49:
        return "🙂 약간 긍정적", "lightgreen"
    elif emotions <= 79:
        return "😊 긍정적", "green"
    else:
        return "🤩 매우 긍정적", "darkgreen"

def collect_all_tags(contents):
    """모든 콘텐츠에서 사용된 태그들을 수집하여 정렬된 리스트로 반환"""
    all_tags = set()
    for content in contents:
        tags = content.get('tags', [])
        if isinstance(tags, list):
            all_tags.update(tags)
        elif isinstance(tags, str):
            # 쉼표로 구분된 문자열인 경우 분리
            all_tags.update([tag.strip() for tag in tags.split(',')])
    return sorted(list(all_tags))

def initialize_session_state():
    """Streamlit 세션 상태 초기화 - 페이지 리로드 시에도 상태 유지"""
    defaults = {
        "selected_user_key": "user1",  # 기본 선택된 사용자
        "selected_card": None,  # 현재 선택된 카드
        "recent_cards": [],  # 최근 본 카드 리스트
        "llm_explanations": {},  # AI 생성 설명 캐시
        "expanded_content_id": None,  # 확장된 콘텐츠 ID
        "show_recommendations": False,  # 추천 결과 표시 여부
        "current_user": None,  # 현재 사용자 정보
        "feedback_data": [],  # 사용자 피드백 데이터
        "debug_mode": False,  # 디버그 모드 활성화 여부
        "recommendation_results": [],  # 추천 결과 저장 (새로 추가)
        "recommendation_cache_key": None  # 추천 캐시 키 (새로 추가)
    }
    
    # 세션 상태에 없는 키들을 기본값으로 초기화
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# ===========================
# 피드백 시스템 함수들
# ===========================

def save_feedback(card_id, title, user_name, feedback_type):
    """사용자의 콘텐츠 피드백을 세션에 저장"""
    if 'feedback_data' not in st.session_state:
        st.session_state.feedback_data = []
    
    # 카드 ID가 없으면 제목 해시를 사용하여 생성
    if not card_id:
        card_id = f"content_{hash(title) % 10000}"
    
    # 피드백 엔트리 생성
    feedback_entry = {
        'card_id': card_id,
        'content_title': title,
        'user_name': user_name,
        'feedback_type': feedback_type,  # positive, neutral, negative
        'timestamp': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    st.session_state.feedback_data.append(feedback_entry)

def display_feedback_buttons(content, user_name, content_identifier):
    """콘텐츠에 대한 사용자 피드백 버튼들을 표시"""
    card_id = content.get('id', content.get('card_id', ''))
    title = content.get('title', 'Unknown Title')
    
    st.write("**💬 이 콘텐츠가 도움이 되셨나요?**")
    
    # 각 버튼에 고유한 키 생성 (중복 방지)
    user_hash = hash(user_name) % 10000
    content_hash = hash(str(content_identifier)) % 10000
    feedback_key = f"feedback_{user_hash}_{content_hash}"
    
    # 이미 피드백을 남긴 콘텐츠인지 확인
    existing_feedback = None
    if 'feedback_data' in st.session_state:
        for feedback in st.session_state.feedback_data:
            if (feedback['user_name'] == user_name and 
                feedback['content_title'] == title):
                existing_feedback = feedback['feedback_type']
                break
    
    # 이미 피드백을 받은 경우 결과만 표시
    if existing_feedback:
        emoji_map = {"positive": "👍", "neutral": "😐", "negative": "👎"}
        status_map = {
            "positive": "도움됨으로 평가하셨습니다",
            "neutral": "보통으로 평가하셨습니다", 
            "negative": "아쉬움으로 평가하셨습니다"
        }
        st.success(f"{emoji_map[existing_feedback]} {status_map[existing_feedback]}")
        return
    
    # 피드백 버튼들 표시
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("👍 도움됨", key=f"positive_{feedback_key}", 
                    help="콘텐츠가 유용하고 만족스러워요"):
            save_feedback(card_id, title, user_name, "positive")
            st.success("피드백이 저장되었습니다! 👍")
            # st.rerun() 제거 - 피드백 후 자동 새로고침 방지
    
    with col2:
        if st.button("😐 보통", key=f"neutral_{feedback_key}", 
                    help="나쁘지 않지만 특별하지 않아요"):
            save_feedback(card_id, title, user_name, "neutral")
            st.info("피드백이 저장되었습니다! 😐")
            # st.rerun() 제거
    
    with col3:
        if st.button("👎 아쉬움", key=f"negative_{feedback_key}", 
                    help="내용이 기대에 못 미치거나 개선이 필요해요"):
            save_feedback(card_id, title, user_name, "negative")
            st.warning("피드백이 저장되었습니다! 개선하겠습니다 👎")
            # st.rerun() 제거

# ===========================
# UI 렌더링 함수들
# ===========================

def render_data_loading():
    """Supabase 데이터베이스에서 콘텐츠 데이터 로드"""
    try:
        with st.spinner("Supabase 데이터베이스에서 콘텐츠를 불러오는 중..."):
            # Supabase 연결 및 데이터 로드
            db = SupabaseConnector()
            all_contents = db.load_contents()
            topics_dict = db.load_topics()
            
            if not all_contents:
                st.error("데이터베이스에서 콘텐츠를 찾을 수 없습니다.")
                st.info("환경 변수와 데이터베이스 설정을 확인해주세요.")
                st.stop()
            
            st.success(f"✅ Supabase DB에서 총 {len(all_contents)}개의 콘텐츠를 불러왔습니다!")
            return all_contents, topics_dict
            
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.error("Supabase 연결 정보를 확인하고 다시 시도해주세요.")
        st.stop()

def render_sample_user_selection():
    """샘플 사용자 선택 인터페이스"""
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # 사용자 선택 드롭다운
        user_key = st.selectbox(
            "사용자 선택",
            list(SAMPLE_USERS.keys()),
            format_func=lambda x: SAMPLE_USERS[x]["name"],  # 사용자명으로 표시
            index=list(SAMPLE_USERS.keys()).index(st.session_state.selected_user_key)
        )
        st.session_state.selected_user_key = user_key
    
    user_info = SAMPLE_USERS[user_key]
    
    with col2:
        # 선택된 사용자 정보 표시
        st.markdown(f"""
        **📋 선택된 사용자 정보**  
        - **이름:** {user_info['name']}  
        - **금융 레벨:** {user_info['knowledge_level']}  
        - **감정 상태:** {user_info['emotion']} (점수: {user_info['emotions']})  
        - **관심 분야:** {", ".join(user_info['interests_categories'])}  
        """)
    
    return user_info

def render_custom_user_input(all_contents):
    """사용자 정의 입력 인터페이스"""
    col1, col2 = st.columns(2)
    
    with col1:
        # 기본 사용자 정보 입력
        user_name = st.text_input(
            "사용자 이름 *",
            value="사용자1",
            help="피드백 저장을 위한 사용자 이름을 입력해주세요"
        )
        
        knowledge_level = st.selectbox(
            "지식 레벨 *",
            options=["Beginner", "Intermediate", "Advanced"],
            index=0,
            help="현재 금융 지식 수준을 선택해주세요"
        )
        
        emotions = st.slider(
            "감정 점수 (-100 ~ 100)",
            min_value=-100,
            max_value=100,
            value=0,
            step=10,
            help="현재 감정 상태를 점수로 표현해주세요"
        )
    
    with col2:
        # 관심 분야 선택
        st.write("관심 카테고리 *")
        
        all_tags = collect_all_tags(all_contents)
        default_interests = all_tags[:3] if len(all_tags) >= 3 else all_tags
        
        interests_categories = st.multiselect(
            "관심 있는 카테고리를 선택하세요",
            options=all_tags,
            default=default_interests,
            help="여러 개 선택 가능합니다"
        )
        
        if not interests_categories:
            st.warning("⚠️ 최소 하나 이상의 관심 카테고리를 선택해주세요")
    
    # 감정 상태 시각적 표시
    emotion_status, emotion_color = get_emotion_status(emotions)
    st.markdown(f"**현재 감정 상태:** <span style='color: {emotion_color}'>{emotion_status}</span>", 
                unsafe_allow_html=True)

    # 입력 유효성 검사
    if not user_name.strip() or not interests_categories:
        return None
    
    # 사용자 정보 객체 반환
    return {
        "name": user_name,
        "knowledge_level": knowledge_level,
        "interests_categories": interests_categories,
        "emotions": emotions,
        "emotion": emotion_status.split()[1] if len(emotion_status.split()) > 1 else "중립"
    }

def render_recommendations(user_info, all_contents):
    """추천 시스템 실행 및 결과 표시"""
    st.subheader("🚀 콘텐츠 추천")
    
    # 추천 실행 버튼
    if st.button("💡 맞춤 콘텐츠 추천받기", type="primary"):
        st.session_state.show_recommendations = True
        st.session_state.current_user = user_info.copy()
        
        # 추천 결과 새로 생성하여 세션에 저장
        try:
            rec = Recommender(all_contents)
            results = rec.recommend(
                user_info["knowledge_level"],
                user_info["interests_categories"], 
                user_info["emotions"],
                top_k=3
            )
            
            # 추천 결과를 세션 상태에 저장
            st.session_state.recommendation_results = results
            # 사용자 정보로 캐시 키 생성 (같은 조건에서는 같은 결과 유지)
            cache_key = f"{user_info['knowledge_level']}_{user_info['emotions']}_{','.join(sorted(user_info['interests_categories']))}"
            st.session_state.recommendation_cache_key = cache_key
            
        except Exception as e:
            st.error(f"추천 시스템 오류: {e}")
            return
    
    # 추천 결과 표시 (세션에 저장된 결과 사용)
    if st.session_state.get('show_recommendations', False):
        current_user = st.session_state.get('current_user', user_info)
        saved_results = st.session_state.get('recommendation_results', [])
        
        if saved_results:
            st.success(f"📌 {current_user['name']}님을 위한 추천 결과")
            render_recommendation_cards(saved_results, current_user)
        else:
            st.warning("현재 조건에 맞는 추천 콘텐츠가 없습니다.")

def render_recommendation_cards(results, current_user):
    """추천된 콘텐츠들을 카드 형태로 표시"""
    st.subheader("📚 오늘의 추천 콘텐츠")
    cols = st.columns(3)
    
    # 각 추천 콘텐츠를 카드로 표시
    for i, content in enumerate(results):
        with cols[i]:
            st.markdown(f"### 📖 {content['title']}")
            st.write(f"**레벨:** {content.get('level', 'Unknown')}")
            
            # 콘텐츠 미리보기 (100자 제한)
            short_desc = content.get('content', content.get('description', ''))[:100] + "..."
            st.write(short_desc)
            
            # 상세 보기 버튼
            if st.button(f"🔍 자세히 보기", key=f"flip_{i}"):
                st.session_state.selected_card = content
                st.session_state.expanded_content_id = content.get('id')
                
                # 최근 본 카드 리스트에 추가 (최대 5개)
                if content not in st.session_state.recent_cards:
                    st.session_state.recent_cards.insert(0, content)
                    if len(st.session_state.recent_cards) > 5:
                        st.session_state.recent_cards.pop()
                # st.rerun() 제거 - 페이지 새로고침 방지
    
    # 선택된 카드의 상세 정보 표시
    if st.session_state.selected_card:
        render_selected_card_details(st.session_state.selected_card, current_user)

def render_selected_card_details(selected, current_user):
    """선택된 카드의 상세 정보를 표시"""
    st.markdown("---")
    st.subheader(f"🔎 {selected['title']} - 상세 설명")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 원본 콘텐츠 표시 (400자 제한)
        st.write("**📝 원래 설명:**")
        original_content = selected.get('content', selected.get('description', ''))
        display_content = original_content[:400] + "..." if len(original_content) > 400 else original_content
        st.markdown(display_content)
    
    with col2:
        # 콘텐츠 메타 정보
        st.write("**📊 콘텐츠 정보**")
        st.write(f"- **레벨:** {selected.get('level')}")
        
        tags = selected.get('tags', [])
        if isinstance(tags, list):
            st.write(f"- **태그:** {', '.join(tags)}")
        else:
            st.write(f"- **태그:** {tags}")
    
    # AI 맞춤 설명 섹션
    render_ai_explanation(selected, current_user, original_content)
    
    # 피드백 버튼
    st.markdown("---")
    content_id = selected.get('id', selected.get('card_id'))
    display_feedback_buttons(selected, current_user["name"], content_id)

def render_ai_explanation(selected, current_user, original_content):
    """AI 생성 맞춤 설명 섹션"""
    st.markdown("---")
    st.write("**🤖 AI 맞춤 설명**")
    
    content_id = selected.get('id', selected.get('card_id'))
    user_level = current_user["knowledge_level"]
    content_key = f"{content_id}___{user_level}"  # 캐시 키 생성
    generating_key = f"generating_{content_key}"  # 생성 중 상태 키
    
    # 이미 생성된 설명이 캐시에 있으면 표시
    if content_key in st.session_state.llm_explanations:
        cached_explanation = st.session_state.llm_explanations[content_key]
        if "오류" in cached_explanation:
            st.warning(cached_explanation)
        else:
            st.info(cached_explanation)
    
    # 현재 AI 설명을 생성 중인 상태
    elif st.session_state.get(generating_key, False):
        try:
            with st.spinner("AI가 맞춤 설명을 생성하고 있습니다... ⏳"):
                # AI 설명 생성 API 호출
                custom_expl = generate_explanation(
                    level=user_level,
                    content_title=selected['title'],
                    content_description=original_content[:400]  # 400자로 제한
                )
                # 생성된 설명을 캐시에 저장
                st.session_state.llm_explanations[content_key] = custom_expl
                st.session_state[generating_key] = False
                st.rerun()
                
        except Exception as e:
            # 오류 발생 시 캐시에 오류 메시지 저장
            error_msg = f"설명 생성 오류: {e}"
            st.session_state.llm_explanations[content_key] = error_msg
            st.session_state[generating_key] = False
            st.rerun()
    
    # 아직 생성하지 않은 경우 생성 버튼 표시
    else:
        if st.button("➡️ AI 맞춤 설명 생성", key=f"generate_{content_id}"):
            st.session_state[generating_key] = True
            st.rerun()

def render_statistics(all_contents, topics_dict):
    """데이터베이스 통계 정보 표시"""
    st.markdown("---")
    st.subheader("📊 데이터베이스 통계")
    
    # 기본 통계 메트릭 표시
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("총 콘텐츠", len(all_contents), help="전체 콘텐츠 수")
    
    with col2:
        beginner_count = len([c for c in all_contents if c.get('level') == 'Beginner'])
        st.metric("초급 콘텐츠", beginner_count, help="Beginner 레벨 콘텐츠 수")
    
    with col3:
        intermediate_count = len([c for c in all_contents if c.get('level') == 'Intermediate'])
        st.metric("중급 콘텐츠", intermediate_count, help="Intermediate 레벨 콘텐츠 수")
    
    with col4:
        advanced_count = len([c for c in all_contents if c.get('level') == 'Advanced'])
        st.metric("고급 콘텐츠", advanced_count, help="Advanced 레벨 콘텐츠 수")
    
    # 토픽별 분포 차트 (선택적)
    if st.checkbox("📈 토픽별 분포 차트 보기"):
        try:
            import plotly.express as px
            
            # 차트용 데이터 준비
            topic_data = []
            for content in all_contents:
                topic_id = content.get('topic_id')
                topic_name = topics_dict.get(topic_id, f"Unknown({topic_id})")
                topic_data.append({"토픽": topic_name, "레벨": content.get('level')})
            
            if topic_data:
                topic_df = pd.DataFrame(topic_data)
                # 토픽별, 레벨별 히스토그램 생성
                fig = px.histogram(
                    topic_df, 
                    x="토픽", 
                    color="레벨",
                    title="토픽별 콘텐츠 분포",
                    labels={"count": "콘텐츠 수"}
                )
                st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.warning("Plotly가 설치되지 않아 차트를 표시할 수 없습니다.")

def render_recent_and_feedback():
    """최근 본 카드 목록과 피드백 통계 표시"""
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        # 최근 본 카드 리스트
        st.subheader("📜 최근 본 카드")
        if st.session_state.recent_cards:
            for i, card in enumerate(st.session_state.recent_cards, 1):
                st.write(f"{i}. {card['title']} ({card.get('level', 'Unknown')})")
        else:
            st.info("아직 본 카드가 없습니다.")
    
    with col2:
        # 피드백 통계 요약
        st.subheader("📝 피드백 통계")
        if 'feedback_data' in st.session_state and st.session_state.feedback_data:
            feedback_df = pd.DataFrame(st.session_state.feedback_data)
            st.write(f"**총 피드백 수:** {len(feedback_df)}개")
            
            # 피드백 타입별 개수 표시
            feedback_counts = feedback_df['feedback_type'].value_counts()
            for feedback_type, count in feedback_counts.items():
                emoji = {"positive": "👍", "neutral": "😐", "negative": "👎"}
                st.write(f"{emoji.get(feedback_type, '❓')} {feedback_type}: {count}개")
        else:
            st.info("아직 피드백이 없습니다.")
    
    # 피드백 상세 데이터 테이블 (확장 가능)
    if 'feedback_data' in st.session_state and st.session_state.feedback_data:
        with st.expander("📋 피드백 상세 내역"):
            feedback_df = pd.DataFrame(st.session_state.feedback_data)
            # 주요 컬럼만 표시
            st.dataframe(
                feedback_df[['content_title', 'user_name', 'feedback_type', 'timestamp']], 
                use_container_width=True
            )

def render_sidebar(all_contents, user_info):
    """사이드바에 시스템 정보와 추가 기능 표시"""
    with st.sidebar:
        # 추천 로직 정보 표시 (추천이 실행된 경우)
        if user_info and st.session_state.get('show_recommendations', False):
            current_user = st.session_state.get('current_user', user_info)
            
            rec = Recommender(all_contents)
            adjusted_level = rec.adjust_level_by_emotion(
                current_user["knowledge_level"], 
                current_user["emotions"]
            )
            
            st.markdown("---")
            st.write("**추천 로직 정보:**")
            st.write(f"- 원래 레벨: {current_user['knowledge_level']}")
            st.write(f"- 감정 점수: {current_user['emotions']}")
            st.write(f"- 조정된 레벨: {adjusted_level}")
            
            # 감정 상태에 따른 레벨 변경 사유 설명
            if current_user["emotions"] <= -30:
                st.write("- 변경 사유: 부정적 감정 😔")
                st.write("- 조정: 더 쉬운 레벨로")
            elif current_user["emotions"] >= 30:
                st.write("- 변경 사유: 긍정적 감정 😊")
                st.write("- 조정: 더 어려운 레벨로")
            else:
                st.write("- 변경 사유: 중립적 감정 😐")
                st.write("- 조정: 레벨 유지")
        
        # 피드백 데이터 관리
        st.markdown("---")
        st.subheader("📝 피드백 관리")
        
        if 'feedback_data' in st.session_state and st.session_state.feedback_data:
            if st.button("🗑️ 피드백 데이터 초기화"):
                # 모든 피드백 관련 데이터 초기화
                st.session_state.feedback_data = []
                st.session_state.llm_explanations = {}
                st.session_state.recommendation_results = []  # 추천 결과도 초기화
                st.session_state.show_recommendations = False  # 추천 상태 초기화
                st.session_state.selected_card = None  # 선택된 카드 초기화
                
                # 생성 중 상태 키들도 초기화
                keys_to_remove = [key for key in st.session_state.keys() if key.startswith('generating_')]
                for key in keys_to_remove:
                    del st.session_state[key]
                
                st.success("피드백 데이터가 초기화되었습니다!")
                st.rerun()
        
        # 감정 점수 기준 설명서
        st.markdown("---")
        with st.expander("💡 감정 기준 설명"):
            st.write("""
            **감정 점수 기준:**
            - 매우 부정적: -60 이하
            - 부정적: -30 ~ -59
            - 약간 부정적: -10 ~ -29
            - 중립적: -9 ~ 29
            - 약간 긍정적: 30 ~ 49
            - 긍정적: 50 ~ 79
            - 매우 긍정적: 80 이상
            
            **레벨 조정 로직:**
            - 부정적 감정(-30 이하): 쉬운 레벨
            - 긍정적 감정(30 이상): 어려운 레벨
            - 중립(-29 ~ 29): 레벨 유지
            """)

def render_keyword_management(user_info, all_contents, user_input_mode):
    """관심 키워드 동적 관리 섹션 (샘플 사용자용)"""
    if user_input_mode == "샘플 사용자 선택" and user_info:
        st.markdown("---")
        st.subheader("🏷️ 관심 키워드 관리")
        
        # 모든 사용 가능한 태그 수집
        all_tags = collect_all_tags(all_contents)
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            current_interests = user_info["interests_categories"]
            # 현재 관심사 중 유효한 것들만 기본값으로 설정
            valid_defaults = [tag for tag in current_interests if tag in all_tags]

            selected_tags = st.multiselect(
                "관심 있는 분야 선택",
                all_tags,
                default=valid_defaults
            )
        
        with col2:
            st.write("**현재 관심 분야:**")
            for tag in current_interests:
                st.write(f"- {tag}")
            
            # 관심 분야 업데이트 버튼
            if st.button("🔄 관심 분야 업데이트"):
                user_key = st.session_state.selected_user_key
                # 샘플 사용자 데이터 업데이트
                SAMPLE_USERS[user_key]["interests_categories"] = selected_tags
                SAMPLE_USERS[user_key]["tags"] = selected_tags
                # 기존 추천 결과 초기화 (관심사 변경 시)
                st.session_state.recommendation_results = []
                st.session_state.show_recommendations = False
                st.session_state.selected_card = None
                st.success("관심 키워드가 업데이트되었습니다!")
                st.rerun()

# ===========================
# 메인 애플리케이션 렌더링
# ===========================

def render():
    """메인 콘텐츠 추천 시스템 실행 함수"""
    # Streamlit 페이지 제목 및 구분선
    st.title("🎯 맞춤형 금융 콘텐츠 추천")
    st.markdown("여러분의 관심사, 지식 레벨에 딱 맞는 다양한 금융 콘텐츠를 추천할게요")
    st.markdown("---")
    
    # 세션 상태 초기화 (페이지 로드 시 한 번만 실행)
    initialize_session_state()
    
    # Supabase에서 데이터 로드
    all_contents, topics_dict = render_data_loading()
    
    # 사용자 설정 방식 선택
    st.subheader("👤 사용자 설정")
    user_input_mode = st.radio(
        "사용자 설정 방식",
        ["샘플 사용자 선택", "직접 입력"],
        index=0,  # 샘플 사용자를 기본값으로
        horizontal=True
    )
    
    # 선택된 방식에 따라 사용자 정보 입력/선택
    if user_input_mode == "샘플 사용자 선택":
        user_info = render_sample_user_selection()
    else:
        user_info = render_custom_user_input(all_contents)
    
    # 사용자 정보가 유효한 경우에만 추천 시스템 실행
    if user_info:
        render_recommendations(user_info, all_contents)
    else:
        st.info("👆 사용자 정보를 설정한 후 추천을 받아보세요.")
    
    # 관심 키워드 관리 (샘플 사용자 모드에서만)
    render_keyword_management(user_info, all_contents, user_input_mode)
    
    # 시스템 통계 정보
    render_statistics(all_contents, topics_dict)
    
    # 최근 본 카드 및 피드백 통계
    render_recent_and_feedback()
    
    # 사이드바 정보 및 관리 기능
    render_sidebar(all_contents, user_info)

# ===========================
# 애플리케이션 진입점
# ===========================

if __name__ == "__main__":
    # Streamlit 페이지 기본 설정
    st.set_page_config(
        page_title="콘텐츠 추천 시스템", 
        page_icon="🎯",
        layout="wide",  # 와이드 레이아웃 사용
        initial_sidebar_state="expanded"  # 사이드바 기본 확장
    )
    
    # 메인 애플리케이션 실행
    render()