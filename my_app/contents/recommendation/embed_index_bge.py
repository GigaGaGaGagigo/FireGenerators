# BGE-M3 임베딩 모델을 위한 인덱스 생성 스크립트

import json
import os
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

from data_access import load_all_cards  # 여러 json 합쳐서 콘텐츠 리스트 반환

# ===== 경로 설정 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENTS_DIR = os.path.join(BASE_DIR, "..", "contents")
INDEX_DIR = os.path.join(BASE_DIR, "index", "bge-m3")  # BGE-M3 모델용 인덱스 폴더

os.makedirs(INDEX_DIR, exist_ok=True)

CONTENT_INDEX_PATH = os.path.join(INDEX_DIR, "content.index")
CONTENT_IDS_PATH = os.path.join(INDEX_DIR, "content_ids.json")
CONTENT_META_PATH = os.path.join(INDEX_DIR, "content_meta.json")

# ===== 1) 콘텐츠 로드 =====
contents = load_all_cards(CONTENTS_DIR)
if not contents:
    raise ValueError("contents 폴더 안에 콘텐츠 JSON이 없습니다. 샘플 데이터를 넣어주세요.")

print(f"[INFO] 총 {len(contents)}개의 콘텐츠 로드 완료")

# ===== 2) 텍스트 합치기 =====
def content_text(content):
    tags_txt = " ".join(content.get("tags", []))
    level = content.get("level", "")
    style = content.get("style", "")
    media_type = content.get("media_type", "")
    topic_id = str(content.get("topic_id", ""))
    
    return (
        f"{content.get('title','')} "
        f"[태그:{tags_txt}] "
        f"[레벨:{level}] "
        f"[스타일:{style}] "
        f"[미디어:{media_type}] "
        f"[토픽:{topic_id}] "
        f"{content.get('content','')}"
    )

texts = [content_text(c) for c in contents]

# ===== 3) BGE-M3 임베딩 모델로 임베딩 생성 =====
MODEL_NAME = "BAAI/bge-m3"
print(f"[INFO] BGE-M3 모델 로딩: {MODEL_NAME}")

model = SentenceTransformer(MODEL_NAME)
print(f"[INFO] BGE-M3 모델 로딩 성공!")

print("[INFO] BGE-M3 임베딩 생성 시작...")
emb = model.encode(texts, batch_size=8, show_progress_bar=True, normalize_embeddings=True)
emb = np.array(emb, dtype='float32')

print(f"[INFO] 임베딩 형태: {emb.shape}")
print(f"[INFO] 임베딩 차원: {emb.shape[1]}")

# ===== 4) FAISS 인덱스 생성 =====
print("[INFO] FAISS 인덱스 생성 중...")
index = faiss.IndexFlatIP(emb.shape[1])  # normalize=True면 코사인 내적
index.add(emb)
faiss.write_index(index, CONTENT_INDEX_PATH)
print(f"[INFO] FAISS 인덱스 저장 완료: {CONTENT_INDEX_PATH}")

# ===== 5) 콘텐츠 ID 및 메타 저장 =====
content_ids = [c["card_id"] for c in contents]
json.dump(content_ids, open(CONTENT_IDS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(contents, open(CONTENT_META_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[INFO] content_ids.json, content_meta.json 저장 완료")

print(f"""
[SUCCESS] BGE-M3 임베딩 인덱스 생성 완료!

저장된 파일들:
- 인덱스: {CONTENT_INDEX_PATH}
- ID 리스트: {CONTENT_IDS_PATH}  
- 메타데이터: {CONTENT_META_PATH}

모델: {MODEL_NAME}
콘텐츠 수: {len(contents)}개
임베딩 차원: {emb.shape[1]}
""")