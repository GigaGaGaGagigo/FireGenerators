import json
import time
import os
from dotenv import load_dotenv
import google.generativeai as genai

# .env 파일에서 API 키 불러오기
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ GEMINI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

# Gemini API 설정
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-2.0-flash")  # 필요 시 모델 교체 가능

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

# 키워드 추출 프롬프트 생성
def build_keyword_prompt(title, content):
    return f"""
다음 금융/경제 용어와 설명에서 핵심 키워드 5-8개를 추출해 주세요.

용어: {title}
설명: {content}

조건:
1. 용어명("{title}")은 제외하고 추출해 주세요
2. 금융/경제 분야의 전문 용어나 중요한 개념 위주로 선별
3. 2글자 이상의 의미있는 단어만 포함
4. 일반적인 조사, 접속사, 부사는 제외
5. 투자자나 학습자가 검색할 만한 키워드 위주

출력 형식: 키워드1, 키워드2, 키워드3, 키워드4, 키워드5
(쉼표로 구분된 키워드만 출력하고 다른 설명은 포함하지 마세요)
"""

# Gemini로 키워드 추출
def get_keywords_from_gemini(title, content, retries=5):
    """Gemini를 사용해 키워드 추출"""
    for attempt in range(retries):
        try:
            prompt = build_keyword_prompt(title, content)
            response = model.generate_content(prompt)
            keywords_text = response.text.strip()
            
            # 쉼표로 구분된 키워드를 리스트로 변환
            keywords = [keyword.strip() for keyword in keywords_text.split(',') if keyword.strip()]
            
            # 빈 키워드나 타이틀과 동일한 키워드 제거
            filtered_keywords = []
            for keyword in keywords:
                if keyword and keyword != title and len(keyword) >= 2:
                    filtered_keywords.append(keyword)
            
            return filtered_keywords[:8]  # 최대 8개까지
            
        except Exception as e:
            if "429" in str(e):
                wait_time = 5 + attempt * 2
                print(f"🚦 키워드 추출 429 에러 — {wait_time}초 대기 중... ({attempt+1}/{retries})")
                time.sleep(wait_time)
            else:
                print(f"⚠️ 키워드 추출 오류: {e}")
                time.sleep(1)
    
    print(f"❌ '{title}' 키워드 추출 실패 → 빈 배열 반환")
    return []
# Gemini로 난이도 분류
def get_level_from_gemini(term, retries=5):
    for attempt in range(retries):
        try:
            prompt = build_prompt(term)
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
    print("📂 파일을 읽는 중...")
    with open("./output_by_category/경제.json", "r", encoding="utf-8") as infile:
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
        
        # 키워드 추출 (Gemini 사용)
        keywords = get_keywords_from_gemini(title, content)
        
        # 최종 태그 설정
        tags = keywords
        
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
        
        time.sleep(5.0)  # 기본 대기 시간
    
    # 결과 저장, 해당 파일명으로 변경
    print("💾 파일로 저장 중...")
    with open("contents_경제.json", "w", encoding="utf-8") as outfile:
        json.dump(result, outfile, ensure_ascii=False, indent=2)
    
    print("✅ Gemini 기반 난이도 분류 및 키워드 추출 완료!")
    print(f"📁 총 {len(result)}개 카드가 contents_경제.json에 저장되었습니다.")

if __name__ == "__main__":
    main()