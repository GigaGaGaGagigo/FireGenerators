import json
import time
import os
from dotenv import load_dotenv
import google.generativeai as genai
from krwordrank.word import KRWordRank
from krwordrank.hangle import normalize
import re

# .env 파일에서 API 키 불러오기
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ GEMINI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

# Gemini API 안전한 설정
try:
    if hasattr(genai, 'configure') and hasattr(genai, 'GenerativeModel'):
        configure_func = getattr(genai, 'configure')
        model_class = getattr(genai, 'GenerativeModel')
        configure_func(api_key=api_key)
        model = model_class("gemini-1.5-flash")
    else:
        raise AttributeError("genai 모듈의 필요한 속성을 찾을 수 없습니다")
except (AttributeError, Exception) as e:
    print(f"⚠️ Gemini API 초기화 실패: {e}")
    model = None

# 프롬프트 생성
def build_prompt(term):
    return f"""
다음 금융 용어의 난이도를 판단해 주세요: "{term}"
아래 3가지 중 하나로 답변만 출력하세요:
- Beginner
- Intermediate
- Advanced
기준: 이 용어가 금융 투자 입문자에게 얼마나 익숙하고 이해하기 쉬운지를 기준으로 판단해 주세요.
답변 형식은 반드시 위 3가지 중 하나만 반환해 주세요.
"""

# 텍스트 전처리 함수
def preprocess_text(text):
    """텍스트 전처리: 특수문자 제거, 정규화"""
    # 한글, 영문, 숫자, 공백만 남기기
    text = re.sub(r'[^\w\s가-힣]', ' ', text)
    # 정규화
    text = normalize(text)
    return text

# kr-word-bank를 사용한 키워드 추출
def extract_keywords_krwordrank(text, min_count=1, max_length=10, beta=0.85, max_iter=10):
    """
    KRWordRank를 사용해 키워드 추출
    """
    try:
        # 텍스트 전처리
        processed_text = preprocess_text(text)
        
        if not processed_text.strip():
            return []
        
        # 문서를 리스트로 변환 (KRWordRank는 문서 리스트를 입력으로 받음)
        texts = [processed_text]
        
        # KRWordRank 객체 생성 및 학습
        wordrank_extractor = KRWordRank(
            min_count=min_count,
            max_length=max_length
        )
        
        beta = beta
        max_iter = max_iter
        keywords, rank, graph = wordrank_extractor.extract(texts, beta, max_iter)
        
        # 상위 키워드 추출 (점수 기준으로 정렬)
        sorted_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)
        
        # 키워드만 추출 (최대 10개)
        extracted_keywords = [keyword for keyword, score in sorted_keywords[:10] if len(keyword) >= 2]
        
        return extracted_keywords
        
    except Exception as e:
        print(f"⚠️ 키워드 추출 오류: {e}")
        return []

# 키워드 후처리 (불용어 제거, 품질 개선)
def filter_keywords(keywords, title="", stopwords=None):
    """키워드 필터링 및 후처리"""
    if stopwords is None:
        # 기본 불용어 리스트
        stopwords = {
            '있는', '있을', '있습니다', '합니다', '됩니다', '입니다', '것입니다',
            '통해', '대한', '위한', '같은', '이런', '그런', '이것', '그것',
            '하는', '되는', '있다', '한다', '이다', '수', '등', '및', '의해',
            '경우', '때문', '따라', '위해', '대해', '관련', '포함', '이용',
            '사용', '발생', '진행', '실시', '시행', '추진', '도입', '확대', '의',
        }
    
    filtered_keywords = []
    title_lower = title.lower() if title else ""
    
    for keyword in keywords:
        # 불용어 제거
        if keyword in stopwords:
            continue
            
        # 너무 짧은 키워드 제거 (1글자)
        if len(keyword) < 2:
            continue
            
        # 숫자만 있는 키워드 제거
        if keyword.isdigit():
            continue
            
        # 타이틀과 동일한 키워드는 제외 (선택사항)
        if keyword.lower() == title_lower:
            continue
            
        filtered_keywords.append(keyword)
    
    return filtered_keywords

# Gemini 호출 함수 (429 에러 재시도 포함)
def get_level_from_gemini(term, retries=5):
    for attempt in range(retries):
        try:
            prompt = build_prompt(term)
            if model is None:
                raise ValueError("Gemini 모델이 초기화되지 않았습니다")
            response = model.generate_content(prompt)
            level = response.text.strip()
            if level in ["Beginner", "Intermediate", "Advanced"]:
                return level
            else:
                print(f"⚠️ 예상치 못한 응답: {level}")
        except Exception as e:
            if "429" in str(e):
                wait_time = 5 + attempt * 2
                print(f"🚦 429 Too Many Requests — {wait_time}초 대기 후 재시도 중... ({attempt+1}/{retries})")
                time.sleep(wait_time)
            else:
                print(f"⚠️ 오류 발생: {e}")
                time.sleep(1)
    print(f"❌ '{term}' → 기본값 'Intermediate'로 설정")
    return "Intermediate"

# 메인 실행 함수
def main():
    print("📂 sample.json 파일을 읽는 중...")
    with open("./sample.json", "r", encoding="utf-8") as infile:
        raw_data = json.load(infile)
    
    result = []
    topic_id_map = {
        "경영": 1,
        "경제": 2,
        "공공": 3,
        "과학": 4,
        "금융": 5,
        "사회": 6
    }
    
    print(f"📊 총 {len(raw_data)}개 항목 처리 시작...\n")
    
    for i, item in enumerate(raw_data, 1):
        card_id = f"card_{i:04d}"
        title = item["용어"]
        content = item["설명"]
        topic_name = item["주제"]
        topic_id = topic_id_map.get(topic_name, 0)
        
        print(f"🔄 [{i}/{len(raw_data)}] 처리 중: {title}")
        
        # 난이도 분류
        level = get_level_from_gemini(title)
        
        # 키워드 추출 (제목 + 내용)
        full_text = f"{title} {content}"
        raw_keywords = extract_keywords_krwordrank(full_text)
        
        # 키워드 필터링 (타이틀 제외)
        filtered_keywords = filter_keywords(raw_keywords, title)
        
        # 최종 태그 (키워드만 사용, 타이틀 제외)
        tags = filtered_keywords[:8]  # 최대 8개 키워드
        
        card = {
            "card_id": card_id,
            "title": title,
            "tags": tags,
            "level": level,
            "content": content,
            "style": "설명형",
            "media_type": "텍스트",
            "topic_id": topic_id
        }
        
        result.append(card)
        
        print(f"✅ {card_id} - {title}")
        print(f"   📈 난이도: {level}")
        print(f"   🏷️  키워드: {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")
        print()
        
        time.sleep(2.0)  # 기본 대기 시간
    
    # 결과 저장
    print("💾 contents_krword.json 파일로 저장 중...")
    with open("contents_krword", "w", encoding="utf-8") as outfile:
        json.dump(result, outfile, ensure_ascii=False, indent=2)
    
    print("✅ Gemini 기반 난이도 분류 및 키워드 추출 완료!")
    print(f"📁 총 {len(result)}개 카드가 contents_krword.json에 저장되었습니다.")

if __name__ == "__main__":
    main()