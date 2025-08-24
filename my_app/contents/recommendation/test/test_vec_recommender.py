from vector_search import vector_candidates
import json
import os

# ========================================
# 1. 콘텐츠 메타데이터 로드
# ========================================
current_dir = os.path.dirname(os.path.abspath(__file__))

# 사용자에게 모델 선택
print("모델을 선택하세요:")
print("1. ko-sroberta (한국어 특화)")
print("2. sentence (한글+영어 다중언어)")
model_choice = input("선택 (1 또는 2, 기본 1): ").strip()

if model_choice == "2":
    model_key = "sentence"
else:
    model_key = "ko-sroberta"

# index 폴더 경로 자동 선택
index_dir = os.path.join(current_dir, "index", model_key)

# contents_meta.json 불러오기
meta_file = os.path.join(index_dir, "content_meta.json")
with open(meta_file, "r", encoding="utf-8") as f:
    all_contents = json.load(f)

print(f"[INFO] 총 콘텐츠 수: {len(all_contents)}")
print(f"[INFO] 선택된 모델: {model_key}")

# ========================================
# 2. 사용자 입력 텍스트
# ========================================
ctx_text = input("검색할 텍스트를 입력하세요: ")

# ========================================
# 3. 벡터 검색 실행
# ========================================
k = 5  # 상위 k개 후보
results = vector_candidates(ctx_text, k=k, model_key=model_key)

# ========================================
# 4. 유사도 기준 필터링 (예: 0.3 이상)
# ========================================
SIM_THRESHOLD = 0.15 # 지금은 sentence 모델이 너무 낮아서 낮춰 중 상태
filtered_results = [r for r in results if r['score'] >= SIM_THRESHOLD]

if not filtered_results:
    print("⚠️ 유사도가 높은 콘텐츠가 없습니다.")
else:
    for r in filtered_results:
        card_id = r['card_id']
        score = r['score']
        
        # ID로 콘텐츠 찾기
        content = next((c for c in all_contents if c.get('card_id') == card_id), None)
        
        if content:
            title = content.get('title', 'Unknown')
            text = content.get('content', content.get('description', ''))
            tags = content.get('tags', [])
            
            print(f"\nID: {card_id} ({score:.4f})")
            print(f"Title: {title}")
            print(f"Content: {text[:200]}...")  # 앞부분 200자만 출력
            print(f"Tags: {tags}")
            print("-" * 50)
        else:
            print(f"ID: {card_id} ({score:.4f}) - 콘텐츠를 찾을 수 없음")
            print("-" * 50)