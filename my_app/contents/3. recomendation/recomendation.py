import streamlit as st
import json
import glob
import random
import pandas as pd
import os

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
# Streamlit 웹 애플리케이션 UI 구성
# ========================================

# 페이지 기본 설정
st.set_page_config(page_title="콘텐츠 추천 시스템", layout="wide")
st.title("📚 콘텐츠 추천 시스템")

# ========================================
# 1. 콘텐츠 데이터 불러오기
# ========================================

# 현재 스크립트의 디렉토리를 기준으로 상위 디렉토리의 "2. contents" 폴더를 참조
current_dir = os.path.dirname(os.path.abspath(__file__))  # 현재 파일의 절대 경로
parent_dir = os.path.dirname(current_dir)  # 상위 디렉토리 경로
contents_path = os.path.join(parent_dir, "2. contents", "contents_*.json")  # JSON 파일 경로 패턴

# glob을 사용하여 패턴에 맞는 모든 JSON 파일 찾기
content_files = glob.glob(contents_path)

# 파일이 없는 경우를 위한 예외 처리
if not content_files:
    st.error(f"콘텐츠 파일을 찾을 수 없습니다. 경로를 확인하세요: {contents_path}")
    st.stop()  # 애플리케이션 실행 중단

# 모든 JSON 파일에서 콘텐츠 데이터 로드
all_contents = []
for file in content_files:
    try:
        # UTF-8 인코딩으로 JSON 파일 읽기
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            all_contents.extend(data)  # 리스트에 데이터 추가
    except Exception as e:
        # 파일 읽기 오류 처리
        st.error(f"파일 읽기 오류 ({file}): {e}")
        continue

# 콘텐츠 데이터가 없는 경우 처리
if not all_contents:
    st.error("불러올 콘텐츠 데이터가 없습니다.")
    st.stop()

# ========================================
# 2. 사이드바에 데이터 개요 표시
# ========================================

st.sidebar.subheader("1. 데이터 개요")

# 콘텐츠 데이터를 DataFrame으로 변환하여 분석
df_contents = pd.DataFrame(all_contents)
st.sidebar.write(f"총 콘텐츠 수: {len(df_contents)}")

# 레벨별 콘텐츠 수 표시
st.sidebar.write("레벨별 콘텐츠 수:")
st.sidebar.write(df_contents.groupby("level").size().rename("count"))

# 스타일 컬럼이 있는 경우에만 스타일별 통계 표시
if "style" in df_contents.columns:
    st.sidebar.write("스타일별 콘텐츠 수:")
    st.sidebar.write(df_contents.groupby("style").size().rename("count"))

# 발견된 콘텐츠 파일 목록 표시 (디버깅용)
st.sidebar.subheader("2. 로드된 파일")
for file in content_files:
    st.sidebar.write(f"✓ {os.path.basename(file)}")

# ========================================
# 3. 샘플 사용자 정의 및 선택
# ========================================


# 테스트용 샘플 사용자 데이터 (수정된 필드명으로 업데이트)
sample_users = [
    {
        "name": "사용자A - 경제 초보자",
        "knowledge_level": "Beginner",
        "interests_categories": ["경제", "금융", "투자"],
        "emotions": -40  # 부정적 감정 (스트레스, 우울감)
    },
    {
        "name": "사용자B - 정치 관심자", 
        "knowledge_level": "Intermediate",
        "interests_categories": ["정치", "사회", "국제"],
        "emotions": 10  # 중립적 감정
    },
    {
        "name": "사용자C - 기술 전문가",
        "knowledge_level": "Advanced",
        "interests_categories": ["산업", "기술", "동향"],
        "emotions": 50  # 긍정적 감정 (의욕적, 활기참)
    },
    {
        "name": "사용자D - 스트레스 받는 학생",
        "knowledge_level": "Intermediate",
        "interests_categories": ["교육", "학습", "시험"],
        "emotions": -60  # 매우 부정적 (시험 스트레스)
    },
    {
        "name": "사용자E - 열정적인 창업자",
        "knowledge_level": "Advanced",
        "interests_categories": ["창업", "비즈니스", "마케팅"],
        "emotions": 80  # 매우 긍정적 (도전 의욕)
    },
    {
        "name": "사용자F - 문화 애호가",
        "knowledge_level": "Beginner",
        "interests_categories": ["문화", "예술", "역사"],
        "emotions": 25  # 약간 긍정적
    },
    {
        "name": "사용자G - 건강 관심자",
        "knowledge_level": "Intermediate",
        "interests_categories": ["건강", "의료", "운동"],
        "emotions": -15  # 약간 부정적 (건강 걱정)
    },
    {
        "name": "사용자H - 환경 운동가",
        "knowledge_level": "Advanced",
        "interests_categories": ["환경", "기후", "지속가능성"],
        "emotions": -25  # 환경 문제로 인한 우려
    },
    {
        "name": "사용자I - 여행 초보자",
        "knowledge_level": "Beginner",
        "interests_categories": ["여행", "문화", "언어"],
        "emotions": 40  # 새로운 경험에 대한 설렘
    },
    {
        "name": "사용자J - IT 중급자",
        "knowledge_level": "Intermediate",
        "interests_categories": ["프로그래밍", "IT", "인공지능"],
        "emotions": 15  # 학습 의욕
    },
    {
        "name": "사용자K - 이직 준비 직장인",
        "knowledge_level": "Intermediate",
        "interests_categories": ["커리어", "자기계발", "취업"],
        "emotions": -45  # 직장 스트레스
    },
    {
        "name": "사용자L - 행복한 은퇴자",
        "knowledge_level": "Beginner",
        "interests_categories": ["취미", "여가", "건강"],
        "emotions": 65  # 여유로운 마음
    },
    {
        "name": "사용자M - 미디어 전문가",
        "knowledge_level": "Advanced",
        "interests_categories": ["미디어", "언론", "커뮤니케이션"],
        "emotions": 5   # 중립적
    },
    {
        "name": "사용자N - 불안한 대학생",
        "knowledge_level": "Beginner",
        "interests_categories": ["진로", "취업", "학업"],
        "emotions": -35  # 미래에 대한 불안
    },
    {
        "name": "사용자O - 성취욕 높은 관리자",
        "knowledge_level": "Advanced",
        "interests_categories": ["리더십", "경영", "전략"],
        "emotions": 70  # 성과에 대한 만족감
    }
]

# 사용자 선택 드롭다운 메뉴
user_names = [u["name"] for u in sample_users]
selected_user_name = st.selectbox("샘플 사용자 선택", user_names)

# 선택된 사용자의 정보 가져오기
selected_user = next(u for u in sample_users if u["name"] == selected_user_name)

# ========================================
# 4. 추천 시스템 실행
# ========================================

# Recommender 인스턴스 생성
rec = Recommender(all_contents)

# 선택된 사용자에 대해 콘텐츠 추천 실행
results = rec.recommend(
    selected_user["knowledge_level"],        # 사용자 지식 레벨
    selected_user["interests_categories"],   # 관심 카테고리
    selected_user["emotions"],               # 감정 점수
    top_k=3  # 최대 5개까지 추천
)

# ========================================
# 5. 추천 결과 표시
# ========================================

st.subheader(f"📌 {selected_user_name} 추천 결과")

if results:
    # 추천된 콘텐츠가 있는 경우
    df_results = pd.DataFrame(results)
    
    # 사용 가능한 컬럼만 선택하여 테이블 형태로 표시
    available_columns = ["title", "level", "tags"]
    display_columns = [col for col in available_columns if col in df_results.columns]
    st.dataframe(df_results[display_columns])
    
    # 추천 결과 상세 정보를 확장 가능한 형태로 표시
    st.subheader("# 추천 상세 정보")
    for i, content in enumerate(results, 1):
        # 각 콘텐츠별로 확장 가능한 박스 생성
        with st.expander(f"{i}. {content.get('title', 'Unknown Title')}"):
            st.write(f"**레벨:** {content.get('level', 'Unknown')}")
            st.write(f"**태그:** {', '.join(content.get('tags', []))}")
            
            # 설명이 있는 경우에만 표시
            if 'description' in content:
                st.write(f"**설명:** {content['description']}")
                
            # 내용이 있는 경우 처음 200자만 미리보기로 표시
            if 'content' in content:
                st.write(f"**내용:** {content['content'][:400]}")
else:
    # 추천된 콘텐츠가 없는 경우
    st.warning("추천할 콘텐츠가 없습니다.")

# 감정 점수 기준 설명
st.subheader("# 감정 기준 및 레벨 조정")

"""
감정 점수 (emotions) 기준 (-100 ~ 100):
- 매우 부정적: -60 이하 (심한 스트레스, 우울감)
- 부정적: -30 ~ -59 (스트레스, 걱정)
- 약간 부정적: -10 ~ -29 (가벼운 우려)
- 중립적: -9 ~ 29 (평범한 상태)
- 약간 긍정적: 30 ~ 49 (기분 좋음)
- 긍정적: 50 ~ 79 (의욕적, 활기참)
- 매우 긍정적: 80 이상 (열정적, 흥미진진)

레벨 조정 로직:
- emotions <= -30: 한 단계 쉬운 레벨로 조정
- emotions >= 30: 한 단계 어려운 레벨로 조정
- -29 ~ 29: 레벨 유지
"""

# ========================================
# 6. 선택된 사용자 정보 표시
# ========================================

st.sidebar.subheader("3. 선택된 사용자 정보")

# 사용자의 모든 정보를 키-값 쌍으로 표시
for key, value in selected_user.items():
    st.sidebar.write(f"**{key}:** {value}")

# 감정 점수에 따른 레벨 조정 정보 표시
adjusted_level = rec.adjust_level_by_emotion(
    selected_user["knowledge_level"], 
    selected_user["emotions"]
)

st.sidebar.subheader("4. 추천 로직 정보")
st.sidebar.write(f"**원래 레벨:** {selected_user['knowledge_level']}")

# 감정 점수 해석
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
st.sidebar.write(f"**사용자 맞춤 레벨:** {adjusted_level}")