import json
import google.generativeai as genai
import time

# Gemini API 설정
genai.configure(api_key="YOUR_GEMINI_API_KEY")
model = genai.GenerativeModel("gemini-pro")

# 프롬프트 생성 함수
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

def get_level_from_gemini(term, retries=3):
    for _ in range(retries):
        try:
            prompt = build_prompt(term)
            response = model.generate_content(prompt)
            level = response.text.strip()
            if level in ["Beginner", "Intermediate", "Advanced"]:
                return level
        except Exception as e:
            time.sleep(1)  # 잠깐 대기 후 재시도
    return "Intermediate"  # 기본값

# 예시 데이터 처리
def main():
    with open("raw_data.json", "r", encoding="utf-8") as infile:
        raw_data = json.load(infile)

    result = []

    for i, item in enumerate(raw_data, 1):
        card_id = f"card_{i:04}"
        title = item["용어"]
        content = item["설명"]
        topic_name = item["주제"]
        topic_id = {
            "경영": 1,
            "경제": 2,
            "공공": 3,
            "과학": 4,
            "금융": 5,
            "사회": 6
        }.get(topic_name, 0)

        level = get_level_from_gemini(title)
        tags = [title]  # 최소한 용어는 태그에 포함
        # 핵심 키워드 추출 (예: krwordrank, 여기선 생략 또는 후처리로 대체)

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
        print(f"{card_id} - {title} : {level}")

        time.sleep(0.8)  # API rate limit 대응

    with open("contents.json", "w", encoding="utf-8") as outfile:
        json.dump(result, outfile, ensure_ascii=False, indent=2)

    print("✅ Gemini 기반 난이도 분류 완료")

if __name__ == "__main__":
    main()