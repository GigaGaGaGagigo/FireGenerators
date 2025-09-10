# Upstage API를 사용한 임베딩 인덱스 생성 스크립트

import json
import os
import numpy as np
import faiss
from dotenv import load_dotenv
from openai import OpenAI
import time

from data_access import load_all_cards  # 여러 json 합쳐서 콘텐츠 리스트 반환

# 환경변수 로드
load_dotenv()

# ===== 경로 설정 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENTS_DIR = os.path.join(BASE_DIR, "..", "contents")
INDEX_DIR = os.path.join(BASE_DIR, "index", "upstage")  # Upstage API용 인덱스 폴더

os.makedirs(INDEX_DIR, exist_ok=True)

CONTENT_INDEX_PATH = os.path.join(INDEX_DIR, "content.index")
CONTENT_IDS_PATH = os.path.join(INDEX_DIR, "content_ids.json")
CONTENT_META_PATH = os.path.join(INDEX_DIR, "content_meta.json")

# ===== 1) Upstage API 클라이언트 초기화 =====
api_key = os.getenv("UPSTAGE_API_KEY")

if not api_key:
    print("❌ UPSTAGE_API_KEY가 .env 파일에 설정되지 않았습니다.")
    print("💡 .env 파일에 다음과 같이 추가해주세요:")
    print("UPSTAGE_API_KEY=your_actual_api_key_here")
    exit()

print("✅ API 키 로드 완료")

try:
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.upstage.ai/v1"
    )
    print("✅ 업스테이지 클라이언트 초기화 완료")
except Exception as e:
    print(f"❌ 클라이언트 초기화 실패: {e}")
    exit()

# ===== 2) 콘텐츠 로드 =====
contents = load_all_cards(CONTENTS_DIR)
if not contents:
    raise ValueError("contents 폴더 안에 콘텐츠 JSON이 없습니다. 샘플 데이터를 넣어주세요.")

print(f"[INFO] 총 {len(contents)}개의 콘텐츠 로드 완료")

# ===== 3) 텍스트 합치기 =====
def content_text(content):
    tags_txt = " ".join(content.get("tags", []))
    level = content.get("level", "")
    style = content.get("style", "")
    media_type = content.get("media_type", "")
    topic_id = str(content.get("topic_id", ""))
    
    return (
        f"{content.get('title','')}" 
        f"[태그:{tags_txt}] "
        f"[레벨:{level}] "
        f"[스타일:{style}] "
        f"[미디어:{media_type}] "
        f"[토픽:{topic_id}] "
        f"{content.get('content','')}"
    )

texts = [content_text(c) for c in contents]
print(f"[INFO] {len(texts)}개 텍스트 준비 완료")

# ===== 4) Upstage API로 임베딩 생성 =====
print("[INFO] Upstage API를 사용한 임베딩 생성 시작...")

def get_embeddings_batch(texts, batch_size=10, delay=0.1):
    """배치 단위로 임베딩 생성 (API 제한 고려)"""
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        print(f"[INFO] 배치 {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1} 처리 중... ({len(batch)}개)")
        
        try:
            response = client.embeddings.create(
                input=batch,
                model="embedding-passage"  # 문서 임베딩용 모델
            )
            
            batch_embeddings = [data.embedding for data in response.data]
            all_embeddings.extend(batch_embeddings)
            
            print(f"   ✅ 배치 완료 ({len(batch_embeddings)}개 벡터)")
            
            # API 호출 제한을 위한 대기
            if delay > 0:
                time.sleep(delay)
                
        except Exception as e:
            print(f"   ❌ 배치 처리 실패: {e}")
            # 실패한 배치는 건너뛰고 계속 진행
            print(f"   ⚠️  배치를 건너뛰고 계속 진행합니다...")
            # 실패한 배치만큼 빈 벡터로 채움 (나중에 처리)
            for _ in batch:
                all_embeddings.append(None)
    
    return all_embeddings

# 임베딩 생성 실행
embeddings = get_embeddings_batch(texts, batch_size=10, delay=0.1)

# None 값 제거 및 유효한 임베딩만 선별
valid_embeddings = []
valid_contents = []
valid_texts = []

for i, emb in enumerate(embeddings):
    if emb is not None:
        valid_embeddings.append(emb)
        valid_contents.append(contents[i])
        valid_texts.append(texts[i])

print(f"[INFO] 유효한 임베딩: {len(valid_embeddings)}개 / 전체: {len(contents)}개")

if len(valid_embeddings) == 0:
    print("❌ 생성된 임베딩이 없습니다. API 키와 네트워크를 확인해주세요.")
    exit()

# NumPy 배열로 변환
emb_array = np.array(valid_embeddings, dtype='float32')
print(f"[INFO] 임베딩 형태: {emb_array.shape}")
print(f"[INFO] 임베딩 차원: {emb_array.shape[1]}")

# ===== 5) FAISS 인덱스 생성 =====
print("[INFO] FAISS 인덱스 생성 중...")

# 코사인 유사도 검색을 위해 벡터를 정규화합니다.
faiss.normalize_L2(emb_array)  # type: ignore

index = faiss.IndexFlatIP(emb_array.shape[1])  # 정규화된 벡터에는 IndexFlatIP가 코사인 유사도와 동일
index.add(emb_array) # type: ignore
faiss.write_index(index, CONTENT_INDEX_PATH)
print(f"[INFO] FAISS 인덱스 저장 완료: {CONTENT_INDEX_PATH}")

# ===== 6) 콘텐츠 ID 및 메타 저장 =====
content_ids = [c["card_id"] for c in valid_contents]
json.dump(content_ids, open(CONTENT_IDS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(valid_contents, open(CONTENT_META_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[INFO] content_ids.json, content_meta.json 저장 완료")

print(f"""
[SUCCESS] Upstage API 임베딩 인덱스 생성 완료!

저장된 파일들:
- 인덱스: {CONTENT_INDEX_PATH}
- ID 리스트: {CONTENT_IDS_PATH}  
- 메타데이터: {CONTENT_META_PATH}

API 모델: embedding-passage
콘텐츠 수: {len(valid_contents)}개 (성공)
실패: {len(contents) - len(valid_contents)}개
임베딩 차원: {emb_array.shape[1]}
""")

# ===== 7) 간단한 유사도 테스트 =====
if len(valid_embeddings) >= 2:
    print("\n🧪 임베딩 품질 테스트:")
    vec1 = np.array(valid_embeddings[0])
    vec2 = np.array(valid_embeddings[1])
    similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    print(f"   첫 번째 vs 두 번째 콘텐츠 유사도: {similarity:.4f}")
    print(f"   콘텐츠 1: {valid_contents[0]['title']}")
    print(f"   콘텐츠 2: {valid_contents[1]['title']}")
