# 임베딩 진행 코드 

import json
import os
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

from data_access import load_all_cards  # 여러 json 합쳐서 콘텐츠 리스트 반환

# ===== 경로 설정 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENTS_DIR = os.path.join(BASE_DIR, "..", "contents")
INDEX_DIR = os.path.join(BASE_DIR, "index", "ko-sroberta")  # 새 인덱스용 폴더 (모델 추가시 바꾸기)

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

# ===== 3) 임베딩 생성 =====
# 필요시 모델 변경
MODEL_NAME = "jhgan/ko-sroberta-multitask" #'sentence-transformers/all-MiniLM-L6-v2' 택 1
print(f"[INFO] 모델 로딩: {MODEL_NAME}")
model = SentenceTransformer(MODEL_NAME)

print("[INFO] 임베딩 생성 시작...")
emb = model.encode(texts, batch_size=32, show_progress_bar=True, normalize_embeddings=True)
emb = np.array(emb, dtype='float32')

# ===== 4) FAISS 인덱스 생성 =====
index = faiss.IndexFlatIP(emb.shape[1])  # normalize=True면 코사인 내적
index.add(emb)
faiss.write_index(index, CONTENT_INDEX_PATH)
print(f"[INFO] FAISS 인덱스 저장 완료: {CONTENT_INDEX_PATH}")

# ===== 5) 콘텐츠 ID 및 메타 저장 =====
content_ids = [c["card_id"] for c in contents]
json.dump(content_ids, open(CONTENT_IDS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(contents, open(CONTENT_META_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[INFO] content_ids.json, content_meta.json 저장 완료")