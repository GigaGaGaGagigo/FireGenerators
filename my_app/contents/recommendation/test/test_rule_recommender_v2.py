from dotenv import load_dotenv
import streamlit as st
import random
import pandas as pd
import os
from explanation_generator import generate_explanation
from supabase import create_client, Client

load_dotenv()

# Supabase 연결하여 실행

# ========================================
# Supabase 연결 클래스
# ========================================

class SupabaseConnector:
    """Supabase 데이터베이스 연결 및 데이터 조회를 담당하는 클래스"""
    
    def __init__(self):
        """Supabase 클라이언트 초기화"""
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY를 .env 파일에 설정해주세요")
        
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
    
    @st.cache_data
    def load_contents(_self):
        """
        Supabase에서 모든 콘텐츠 데이터를 불러오는 메서드
        @st.cache_data 데코레이터로 캐싱 적용 (성능 최적화)
        
        Returns:
            list: 콘텐츠 데이터 리스트
        """
        try:
            # contents 테이블에서 모든 데이터 조회
            response = _self.supabase.table("contents").select("*").execute()
            
            if response.data:
                # 데이터 형식을 기존 JSON 형식에 맞게 변환
                contents = []
                for item in response.data:
                    content = {
                        "id": item.get("id"),
                        "card_id": item.get("card_id"),
                        "title": item.get("title"),
                        "content": item.get("content"),
                        "description": item.get("content"),  # content를 description으로도 사용
                        "level": item.get("level").title(),  # 'beginner' -> 'Beginner'
                        "style": item.get("style"),
                        "media_type": item.get("media_type"),
                        "topic_id": item.get("topic_id"),
                        "tags": item.get("tags", []),
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
        Supabase에서 토픽 데이터를 불러오는 메서드
        
        Returns:
            dict: {topic_id: topic_name} 형태의 딕셔너리
        """
        try:
            response = _self.supabase.table("topics").select("*").execute()
            
            if response.data:
                return {topic["id"]: topic["name"] for topic in response.data}
            else:
                return {}
                
        except Exception as e:
            st.error(f"토픽 데이터 로드 오류: {e}")
            return {}
    
    def get_contents_by_level(self, level: str):
        """특정 레벨의 콘텐츠만 조회"""
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
        
# ========================================
# 콘텐츠 추천 클래스 
# ========================================        

class Recommender:
    """
    콘텐츠 추천 시스템 클래스
    사용자의 레벨, 관심 분야, 감정 점수를 기반으로 콘텐츠를 추천하는 클래스
    """
    
    def __init__(self, contents):
        """
        추천 시스템 초기화
         
        Args:
            contents (list): 추천할 콘텐츠들의 리스트 (각각 딕셔너리 형태)
        """
        self.contents = contents  # 전체 콘텐츠 데이터 저장
        self.level_order = ["Beginner", "Intermediate", "Advanced"]  # 레벨 순서 정의

    def adjust_level_by_emotion(self, knowledge_level, emotions):
        """
        감정 점수에 따라 사용자의 학습 레벨을 조정하는 메서드
        - 부정적 감정(-30 이하): 한 단계 쉬운 레벨로 조정
        - 긍정적 감정(30 이상): 한 단계 어려운 레벨로 조정
        
        Args:
            knowledge_level (str): 사용자의 원래 지식 레벨
            emotions (int): 감정 점수 (-100 ~ 100)
            
        Returns:
            str: 조정된 레벨
        """
        # 현재 레벨의 인덱스 찾기
        idx = self.level_order.index(knowledge_level)
        
        # 감정 점수에 따른 레벨 조정
        if emotions <= -30:  # 부정적 감정: 더 쉬운 레벨로
            idx = max(0, idx - 1)  # 인덱스가 0보다 작아지지 않도록 제한
        elif emotions >= 30:  # 긍정적 감정: 더 어려운 레벨로
            idx = min(len(self.level_order) - 1, idx + 1)  # 인덱스가 최대값을 넘지 않도록 제한
            
        return self.level_order[idx]  # 조정된 레벨 반환

    def recommend(self, knowledge_level, interests_categories, emotions, top_k=3):
        """
        사용자 정보를 바탕으로 콘텐츠를 추천하는 메인 메서드
        
        Args:
            knowledge_level (str): 사용자의 학습 레벨
            interests_categories (list): 사용자의 관심 카테고리 리스트
            emotions (int): 사용자의 감정 점수
            top_k (int): 추천할 콘텐츠 개수 (기본값: 3)
            
        Returns:
            list: 추천된 콘텐츠 리스트
        """
        # 1. 감정 점수를 고려하여 레벨 조정
        adjusted_level = self.adjust_level_by_emotion(knowledge_level, emotions)

        # 2. 조정된 레벨에 맞는 콘텐츠 후보 필터링
        candidates = [
            c for c in self.contents
            if c.get("level") == adjusted_level  # 레벨이 일치하는 콘텐츠만 선택
        ]

        def tag_score(content):
            """
            콘텐츠의 태그 점수를 계산하는 내부 함수
            사용자 관심 카테고리와 콘텐츠 태그의 일치 개수를 반환
            
            Args:
                content (dict): 콘텐츠 딕셔너리
                
            Returns:
                int: 일치하는 태그의 개수
            """
            return sum(tag in interests_categories for tag in content.get("tags", []))

        # 3. 각 후보 콘텐츠에 대해 태그 점수 계산
        scored = [(c, tag_score(c)) for c in candidates]
        
        # 4. 후보가 없는 경우 빈 리스트 반환
        if not scored:
            return []

        # 5. 최고 점수를 가진 콘텐츠들 찾기
        max_score = max(score for _, score in scored)
        best = [c for c, score in scored if score == max_score]

        # 6. 추천 결과 선정
        if len(best) >= top_k:
            # 최고 점수 콘텐츠가 충분히 많으면 랜덤하게 선택
            return random.sample(best, top_k)
        else:
            # 점수 순으로 정렬하여 상위 top_k개 선택
            scored.sort(key=lambda x: x[1], reverse=True)  # 점수 내림차순 정렬
            return [c for c, _ in scored][:top_k]
        
        
# ========================================
# 피드백 관련 함수들 (향후 DB 연결 필요)
# ======================================== 

def save_feedback(card_id, title, user_name, feedback_type):
    """
    콘텐츠 피드백을 저장하는 함수 (향후 DB 연결 예정)
    현재는 세션 상태에만 저장
    
    Args:
        card_id (str): 콘텐츠 ID (없으면 title 기반으로 생성)
        title (str): 콘텐츠 제목
        user_name (str): 사용자 이름
        feedback_type (str): 피드백 타입 ('positive', 'neutral', 'negative')
    """
    # 세션 상태에 피드백 저장소가 없으면 초기화
    if 'feedback_data' not in st.session_state:
        st.session_state.feedback_data = []
    
    if not card_id:
        card_id = f"content_{hash(title) % 10000}"
    
    # 피드백 데이터 생성
    feedback_entry = {
        'card_id': card_id,
        'content_title': title,  # 수정: 'title'을 'content_title'로 변경
        'user_name': user_name,
        'feedback_type': feedback_type,
        'timestamp': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # 세션 상태에 피드백 추가
    st.session_state.feedback_data.append(feedback_entry)
    
    # 향후 DB 저장 로직이 들어갈 자리
    # TODO: 데이터베이스 연결 시 아래 코드 활성화
    # save_to_database(feedback_entry)
    
def display_feedback_buttons(content, user_name, content_identifier):
    """
    콘텐츠별 피드백 버튼을 표시하는 함수
    
    Args:
        content (dict): 콘텐츠 정보
        user_name (str): 사용자 이름
        content_identifier (str/int): 콘텐츠 식별자 (ID 또는 인덱스)
    """
    card_id = content.get('id', content.get('card_id', ''))
    title = content.get('title', 'Unknown Title')
    
    st.write("**💬 이 콘텐츠가 도움이 되셨나요?**")
    
    # 안정적인 고유 키 생성
    user_hash = hash(user_name) % 10000
    content_hash = hash(str(content_identifier)) % 10000
    feedback_key = f"feedback_{user_hash}_{content_hash}"
    
    # 피드백 데이터에서 해당 사용자-콘텐츠 조합의 기존 피드백 확인
    existing_feedback = None
    if 'feedback_data' in st.session_state:
        for feedback in st.session_state.feedback_data:
            if (feedback['user_name'] == user_name and 
                feedback['content_title'] == title):
                existing_feedback = feedback['feedback_type']
                break
    
    # 이미 피드백을 받은 경우 표시만 하고 버튼 비활성화
    if existing_feedback:
        emoji_map = {"positive": "👍", "neutral": "😐", "negative": "👎"}
        status_map = {
            "positive": "도움됨으로 평가하셨습니다",
            "neutral": "보통으로 평가하셨습니다", 
            "negative": "아쉬움으로 평가하셨습니다"
        }
        st.success(f"{emoji_map[existing_feedback]} {status_map[existing_feedback]}")
        return
    
    # 3개의 피드백 버튼을 한 줄에 배치
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button(
            "👍 도움됨", 
            key=f"positive_{feedback_key}",
            help="콘텐츠가 유용하고 만족스러워요"
        ):
            save_feedback(card_id, title, user_name, "positive")
            st.success("피드백이 저장되었습니다! 👍")
    
    with col2:
        if st.button(
            "😐 보통", 
            key=f"neutral_{feedback_key}",
            help="나쁘지 않지만 특별하지 않아요"
        ):
            save_feedback(card_id, title, user_name, "neutral")
            st.info("피드백이 저장되었습니다! 😐")
    
    with col3:
        if st.button(
            "👎 아쉬움", 
            key=f"negative_{feedback_key}",
            help="내용이 기대에 못 미치거나 개선이 필요해요"
        ):
            save_feedback(card_id, title, user_name, "negative")
            st.warning("피드백이 저장되었습니다! 개선하겠습니다 👎")

# ========================================
# Streamlit 웹 애플리케이션 UI 구성
# ========================================

# 페이지 기본 설정
st.set_page_config(page_title="콘텐츠 추천 시스템", layout="wide")
st.title("📚 콘텐츠 추천 시스템 (DB 연동)")

# ========================================
# 데이터베이스에서 콘텐츠 데이터 불러오기
# ========================================

try:
    # Supabase 연결 초기화
    db = SupabaseConnector()
    
    # 데이터 로드 (캐싱 적용)
    with st.spinner("데이터베이스에서 콘텐츠를 불러오는 중..."):
        all_contents = db.load_contents()
        topics_dict = db.load_topics()
    
    if not all_contents:
        st.error("불러올 콘텐츠 데이터가 없습니다. 데이터베이스를 확인해주세요.")
        st.stop()
    
    st.success(f"✅ 총 {len(all_contents)}개의 콘텐츠를 성공적으로 불러왔습니다!")

    # Recommender 인스턴스를 미리 생성하여 앱 전체에서 사용 가능하도록 함
    rec = Recommender(all_contents)

except Exception as e:
    st.error(f"데이터베이스 연결 실패: {e}")
    st.stop()

# ========================================
# 사용자 정보 직접 입력 섹션
# ========================================

st.subheader("👤 사용자 정보 입력")

# 사용자 정보 입력을 위한 컬럼 나누기
col1, col2 = st.columns(2)

with col1:
    # 사용자 이름 입력
    user_name = st.text_input(
        "사용자 이름 *",
        value="사용자1",
        help="피드백 저장을 위한 사용자 식별 이름",
        placeholder="예: 김구름, 학습자A 등"
    )
    
    # 지식 레벨 선택
    knowledge_level = st.selectbox(
        "지식 레벨 *",
        options=["Beginner", "Intermediate", "Advanced"],
        index=0,
        help="현재 학습 수준을 선택해주세요"
    )
    
    # 감정 상태 선택 (슬라이더 방식)
    emotions = st.slider(
        "감정 점수 (-100 ~ 100)",
        min_value=-100,
        max_value=100,
        value=0,
        step=10,
        help="현재 감정 상태를 점수로 표현해주세요"
    )

with col2:
    # 관심 카테고리 선택 (다중 선택)
    st.write("관심 카테고리 *")
    
    # 사용 가능한 모든 태그 수집
    all_tags = set()
    for content in all_contents:
        tags = content.get('tags', [])
        if isinstance(tags, list):
            all_tags.update(tags)
        elif isinstance(tags, str):
            # 문자열인 경우 쉼표로 분리
            all_tags.update([tag.strip() for tag in tags.split(',')])
    
    all_tags = sorted(list(all_tags))
    
    # 기본값 설정 (처음 3개 태그)
    default_interests = all_tags[:3] if len(all_tags) >= 3 else all_tags
    
    interests_categories = st.multiselect(
        "관심 있는 카테고리를 선택하세요",
        options=all_tags,
        default=default_interests,
        help="여러 개 선택 가능합니다"
    )
    
    # 선택된 카테고리가 없는 경우 경고
    if not interests_categories:
        st.warning("⚠️ 최소 하나 이상의 관심 카테고리를 선택해주세요")

# 감정 점수에 따른 상태 표시
emotion_status = ""
if emotions <= -60:
    emotion_status = "😭 매우 부정적"
    emotion_color = "red"
elif emotions <= -30:
    emotion_status = "😔 부정적"
    emotion_color = "orange"
elif emotions <= -10:
    emotion_status = "😐 약간 부정적"
    emotion_color = "yellow"
elif emotions <= 29:
    emotion_status = "😐 중립적"
    emotion_color = "gray"
elif emotions <= 49:
    emotion_status = "🙂 약간 긍정적"
    emotion_color = "lightgreen"
elif emotions <= 79:
    emotion_status = "😊 긍정적"
    emotion_color = "green"
else:
    emotion_status = "🤩 매우 긍정적"
    emotion_color = "darkgreen"

st.markdown(f"**현재 감정 상태:** <span style='color: {emotion_color}'>{emotion_status}</span>", 
            unsafe_allow_html=True)

# 입력 검증
input_valid = True
error_messages = []

if not user_name.strip():
    error_messages.append("사용자 이름을 입력해주세요")
    input_valid = False

if not interests_categories:
    error_messages.append("최소 하나 이상의 관심 카테고리를 선택해주세요")
    input_valid = False

# 에러 메시지 표시
if error_messages:
    for msg in error_messages:
        st.error(msg)

# 사용자 정보 요약 표시 (입력이 유효한 경우)
if input_valid:
    with st.expander("✅ 입력한 사용자 정보 요약", expanded=False):
        st.write(f"**이름:** {user_name}")
        st.write(f"**지식 레벨:** {knowledge_level}")
        st.write(f"**감정 점수:** {emotions} ({emotion_status})")
        st.write(f"**관심 카테고리:** {', '.join(interests_categories)}")

# 선택된 사용자 정보를 딕셔너리로 생성 (기존 코드와 호환)
if input_valid:
    selected_user = {
        "name": user_name,
        "knowledge_level": knowledge_level,
        "interests_categories": interests_categories,
        "emotions": emotions
    }
    
    # 추천 시스템 실행 버튼    
    col_btn, col_info = st.columns([1, 2])
    
    with col_btn:
        recommend_button = st.button(
            "🚀 콘텐츠 추천 받기",
            type="primary",
            help="입력한 정보를 바탕으로 맞춤 콘텐츠를 추천합니다"
        )
    
    with col_info:
        if recommend_button:
            st.success("✅ 추천을 실행합니다!")
else:
    selected_user = None
    recommend_button = False

# ========================================
# 추천 시스템 실행 (조건부)
# ========================================

if input_valid and (recommend_button or st.session_state.get('show_recommendations', False)):
    # 추천 결과를 세션에 저장하여 지속적으로 표시
    if recommend_button:
        st.session_state['show_recommendations'] = True
        st.session_state['current_user'] = selected_user.copy()
    
    # 세션에 저장된 사용자 정보 사용
    current_user = st.session_state.get('current_user', selected_user)
    
    # Recommender 인스턴스 생성
    rec = Recommender(all_contents)
    
    # 선택된 사용자에 대해 콘텐츠 추천 실행
    results = rec.recommend(
        current_user["knowledge_level"],
        current_user["interests_categories"],
        current_user["emotions"],
        top_k=3
    )
    
    # ========================================
    # 추천 결과 표시
    # ========================================

    st.subheader(f"📌 {current_user['name']}님을 위한 추천 결과")

    if results:
        # (이전 코드는 동일)
        # ... df_results 및 display_columns 설정 ...
        # st.dataframe(df_results[display_columns])
        
        st.subheader("ℹ️ 추천 상세 정보")
        
        # LLM 설명 캐싱을 위한 세션 상태 초기화
        if 'llm_explanations' not in st.session_state:
            st.session_state.llm_explanations = {}
        
        # 어떤 expander가 열려야 하는지 추적하기 위한 세션 상태
        if 'expanded_content_id' not in st.session_state:
            st.session_state.expanded_content_id = None
            
        for i, content in enumerate(results, 1):
            content_id = content.get('id', content.get('card_id', f"content_{abs(hash(content.get('title', '')))}"))
            content_title = content.get('title', 'Unknown Title')
            user_level = current_user["knowledge_level"]
            
            # 현재 content가 열려야 하는지 확인
            is_expanded = (st.session_state.expanded_content_id == content_id)

            # 각 콘텐츠별로 확장 가능한 박스 생성 (상태에 따라 열림/닫힘 제어)
            with st.expander(f"{i}. {content_title}", expanded=is_expanded):
                st.write(f"**레벨:** {content.get('level', 'Unknown')}")
                st.write(f"**태그:** {', '.join(content.get('tags', []))}")
                
                topic_id = content.get('topic_id')
                topic_name = topics_dict.get(topic_id, f"Unknown({topic_id})")
                st.write(f"**토픽:** {topic_name}")

                original_expl = content.get('content', content.get('description', ''))[:400]
                st.markdown(f"**📝 원래 설명:** {original_expl}")

                # --- Gemini 맞춤 설명 기능 ---
                content_key = f"{content_id}___{user_level}"
                generating_key = f"generating_{content_key}"

                st.markdown(f"**💬 맞춤 설명:**")

                # 1. 이미 생성된 설명이 있으면 표시 (캐시된 결과)
                if content_key in st.session_state.llm_explanations:
                    cached_explanation = st.session_state.llm_explanations[content_key]
                    if "오류" in cached_explanation:
                        st.warning(cached_explanation)
                    else:
                        st.info(cached_explanation)
                
                # 2. 현재 생성 중인 상태이면 스피너 표시
                elif st.session_state.get(generating_key, False):
                    try:
                        with st.spinner("AI가 맞춤 설명을 생성하고 있습니다... ⏳"):
                            custom_expl = generate_explanation(
                                level=user_level,
                                content_title=content_title,
                                content_description=content.get('description', content.get('content', ''))[:400]
                            )
                            st.session_state.llm_explanations[content_key] = custom_expl # 결과 저장
                            st.session_state[generating_key] = False # 생성 상태 해제
                            st.rerun() # 설명 표시를 위해 한번 더 재실행
                            
                    except Exception as e:
                        error_msg = f"설명 생성 오류: {e}"
                        st.session_state.llm_explanations[content_key] = error_msg
                        st.session_state[generating_key] = False
                        st.rerun() # 오류 표시를 위해 한번 더 재실행

                # 3. 아직 생성 전이면 버튼 표시
                else:
                    generate_btn_key = f"generate_{content_id}_{user_level}"
                    if st.button("➡️ AI 설명 생성", key=generate_btn_key, help="이 버튼을 클릭하면 AI가 맞춤 설명을 생성합니다"):
                        # 버튼 클릭 시 '생성 중' 상태와 'expander 열림' 상태를 동시에 설정
                        st.session_state[generating_key] = True
                        st.session_state.expanded_content_id = content_id
                        st.rerun() # 상태 변경을 적용하기 위해 재실행

                st.markdown("---")
                
                # 피드백 버튼 추가
                display_feedback_buttons(content, current_user["name"], content_id)
    else:
        st.warning("추천할 콘텐츠가 없습니다.")

elif not input_valid:
    st.info("👆 위의 사용자 정보를 모두 입력한 후 '콘텐츠 추천 받기' 버튼을 클릭하세요.")

# ========================================
# 추가 기능: 데이터베이스 통계 및 관리
# ========================================

# 메인 페이지 하단에 DB 통계 정보 추가
st.markdown("---")
st.subheader("📊 데이터베이스 통계")

# 통계 정보를 컬럼으로 나누어 표시
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="총 콘텐츠",
        value=len(all_contents),
        help="데이터베이스에 저장된 전체 콘텐츠 수"
    )

with col2:
    beginner_count = len([c for c in all_contents if c.get('level') == 'Beginner'])
    st.metric(
        label="초급 콘텐츠",
        value=beginner_count,
        help="Beginner 레벨 콘텐츠 수"
    )

with col3:
    intermediate_count = len([c for c in all_contents if c.get('level') == 'Intermediate'])
    st.metric(
        label="중급 콘텐츠",
        value=intermediate_count,
        help="Intermediate 레벨 콘텐츠 수"
    )

with col4:
    advanced_count = len([c for c in all_contents if c.get('level') == 'Advanced'])
    st.metric(
        label="고급 콘텐츠",
        value=advanced_count,
        help="Advanced 레벨 콘텐츠 수"
    )

# 토픽별 분포 차트 (선택적 표시)
if st.checkbox("📈 토픽별 분포 차트 보기"):
    import plotly.express as px
    
    topic_data = []
    for content in all_contents:
        topic_id = content.get('topic_id')
        topic_name = topics_dict.get(topic_id, f"Unknown({topic_id})")
        topic_data.append({"토픽": topic_name, "레벨": content.get('level')})
    
    topic_df = pd.DataFrame(topic_data)
    
    if not topic_df.empty:
        fig = px.histogram(
            topic_df, 
            x="토픽", 
            color="레벨",
            title="토픽별 콘텐츠 분포",
            labels={"count": "콘텐츠 수"}
        )
        st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ========================================
# 기타 코드 (감정 점수 설명, 피드백 결과, 사이드바 등)
# ========================================

# 피드백 상세 결과 (기존과 동일)
if 'feedback_data' in st.session_state and st.session_state.feedback_data:
    st.subheader("📋 피드백 상세 결과")
    feedback_df = pd.DataFrame(st.session_state.feedback_data)
    
    col1, col2 = st.columns([1, 3])

    with col1:
        st.write(f"**총 피드백 수:** {len(feedback_df)}개")
        feedback_counts = feedback_df['feedback_type'].value_counts()
        for feedback_type, count in feedback_counts.items():
            emoji = {"positive": "👍", "neutral": "😐", "negative": "👎"}
            st.write(f"{emoji.get(feedback_type, '❓')} {feedback_type}: {count}개")
    
    with col2:
        st.dataframe(feedback_df[['content_title', 'feedback_type', 'timestamp']], 
                    use_container_width=True)
        
# 감정 점수 기준 설명 (기존과 동일)
with st.expander("💡 감정 기준 및 레벨 조정 설명"):
    st.write(
    """
    **감정 점수 (emotions) 기준 (-100 ~ 100):**
    - 매우 부정적: -60 이하 (심한 스트레스, 우울감)
    - 부정적: -30 ~ -59 (스트레스, 걱정)
    - 약간 부정적: -10 ~ -29 (가벼운 우려)
    - 중립적: -9 ~ 29 (평범한 상태)
    - 약간 긍정적: 30 ~ 49 (기분 좋음)
    - 긍정적: 50 ~ 79 (의욕적, 활기참)
    - 매우 긍정적: 80 이상 (열정적, 흥미진진)

    **레벨 조정 로직:**
    - emotions <= -30: 한 단계 쉬운 레벨로 조정
    - emotions >= 30: 한 단계 어려운 레벨로 조정
    - -29 ~ 29: 레벨 유지
    """
    )

# 사이드바 사용자 정보 및 추천 로직
st.sidebar.subheader("1. 선택된 사용자 정보")

for key, value in selected_user.items():
    if key != "name":
        st.sidebar.write(f"**{key}:** {value}")

adjusted_level = rec.adjust_level_by_emotion(
    selected_user["knowledge_level"], 
    selected_user["emotions"]
)


st.sidebar.subheader("2. 추천 로직 정보")
st.sidebar.write(f"**원래 레벨:** {selected_user['knowledge_level']}")

if selected_user["emotions"] <= -30:
    emotion_status = "부정적 😔"
    level_change = "더 쉬운 레벨로 조정"
elif selected_user["emotions"] >= 30:
    emotion_status = "긍정적 😊"
    level_change = "더 어려운 레벨로 조정"
else:
    emotion_status = "중립적 😐"
    level_change = "레벨 유지"

st.sidebar.write(f"**감정 상태:** {emotion_status}")
st.sidebar.write(f"**레벨 조정:** {level_change}")
st.sidebar.write(f"**최종 추천 레벨:** {adjusted_level}")


st.sidebar.subheader("3. 피드백 관리")
# 세션에 피드백 데이터가 있으면 통계 표시
if 'feedback_data' in st.session_state and st.session_state.feedback_data:
    feedback_df = pd.DataFrame(st.session_state.feedback_data)
    
    # 피드백 초기화 버튼 (LLM 캐시도 함께 초기화)
    if st.sidebar.button("🗑️ 피드백 데이터 초기화"):
        st.session_state.feedback_data = []
        # LLM 설명 캐시도 초기화
        if 'llm_explanations' in st.session_state:
            st.session_state.llm_explanations = {}
        # 생성 상태도 초기화
        keys_to_remove = [key for key in st.session_state.keys() if key.startswith('generating_')]
        for key in keys_to_remove:
            del st.session_state[key]
        st.sidebar.success("피드백 데이터가 초기화되었습니다!")
else:
    st.sidebar.write("아직 피드백이 없습니다.")
