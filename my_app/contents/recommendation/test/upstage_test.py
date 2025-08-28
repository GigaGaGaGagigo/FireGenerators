# 필요한 라이브러리 설치 (터미널에서 실행)
# pip install openai python-dotenv

import os
from dotenv import load_dotenv
from openai import OpenAI
import numpy as np

# .env 파일에서 환경변수 로드
load_dotenv()

# API 키 가져오기
api_key = os.getenv("UPSTAGE_API_KEY")

if not api_key:
    print("❌ UPSTAGE_API_KEY가 .env 파일에 설정되지 않았습니다.")
    print("💡 .env 파일에 다음과 같이 추가해주세요:")
    print("UPSTAGE_API_KEY=your_actual_api_key_here")
    exit()

print("✅ API 키 로드 완료")

# 업스테이지 클라이언트 초기화
try:
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.upstage.ai/v1"
    )
    print("✅ 업스테이지 클라이언트 초기화 완료")
except Exception as e:
    print(f"❌ 클라이언트 초기화 실패: {e}")
    exit()

# 테스트할 텍스트들
test_texts = [
    "안녕하세요. 업스테이지 임베딩 테스트입니다.",
    "인공지능과 머신러닝은 현대 기술의 핵심입니다.",
    "오늘 날씨가 정말 좋네요.",
    "Python은 데이터 사이언스에 널리 사용되는 언어입니다.",
    "Solar embeddings are awesome",
    "Hello, this is an English sentence for testing."
]

print("\n🔍 임베딩 테스트 시작...")

# 개별 텍스트 임베딩 테스트
vectors = []
for i, text in enumerate(test_texts):
    try:
        print(f"\n📝 텍스트 {i+1}: {text}")
        
        # 임베딩 요청
        response = client.embeddings.create(
            input=text,
            model="embedding-query"
        )
        
        vector = response.data[0].embedding
        vectors.append(vector)
        
        print(f"   📊 벡터 차원: {len(vector)}")
        print(f"   📈 첫 5개 값: {vector[:5]}")
        print(f"   📉 벡터 크기(norm): {np.linalg.norm(vector):.4f}")
        
    except Exception as e:
        print(f"   ❌ 에러 발생: {e}")
        vectors.append(None)

# 배치 임베딩 테스트
print("\n🚀 배치 임베딩 테스트...")
try:
    batch_response = client.embeddings.create(
        input=test_texts,
        model="embedding-query"
    )
    
    batch_vectors = [data.embedding for data in batch_response.data]
    print(f"✅ 배치 임베딩 완료: {len(batch_vectors)}개 벡터 생성")
    
    # 유사도 계산 예시
    print("\n📊 텍스트 간 코사인 유사도:")
    for i in range(len(batch_vectors)):
        for j in range(i+1, len(batch_vectors)):
            # 코사인 유사도 계산
            vec1 = np.array(batch_vectors[i])
            vec2 = np.array(batch_vectors[j])
            similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
            print(f"   텍스트 {i+1} ↔ 텍스트 {j+1}: {similarity:.4f}")
            
            # 특별히 유사한 문장들 표시
            if similarity > 0.7:
                print(f"      🔥 높은 유사도 발견!")
                print(f"         '{test_texts[i][:30]}...'")
                print(f"         '{test_texts[j][:30]}...'")

except Exception as e:
    print(f"❌ 배치 임베딩 실패: {e}")

# 사용량 정보 (가능하다면)
print("\n📋 응답 정보:")
try:
    if 'batch_response' in locals():
        print(f"   모델: {batch_response.model}")
        print(f"   사용량: {batch_response.usage}")
except:
    print("   사용량 정보 없음")

print("\n✨ 테스트 완료!")

# 임베딩 품질 간단 체크
print("\n🧪 임베딩 품질 체크:")
if len(vectors) >= 2 and vectors[0] and vectors[1]:
    # 한국어 문장들 간 유사도
    korean_sim = np.dot(vectors[0], vectors[1]) / (np.linalg.norm(vectors[0]) * np.linalg.norm(vectors[1]))
    print(f"   한국어 문장 간 유사도: {korean_sim:.4f}")
    
    # 한영 문장 간 유사도  
    if len(vectors) >= 5 and vectors[4]:
        korean_english_sim = np.dot(vectors[0], vectors[4]) / (np.linalg.norm(vectors[0]) * np.linalg.norm(vectors[4]))
        print(f"   한국어-영어 문장 간 유사도: {korean_english_sim:.4f}")