from pathlib import Path
import json, faiss, numpy as np
import os
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from openai import OpenAI

# ===== 모델별 설정 =====
MODEL_INDEX_MAP = {
    "ko-sroberta": {
        "model_name": "jhgan/ko-sroberta-multitask",
        "index_dir": Path(__file__).resolve().parent / "index" / "ko-sroberta"
    },
    "sentence": {
        "model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "index_dir": Path(__file__).resolve().parent / "index" / "sentence"
    },
    "upstage": {
        "model_name": "upstage-api",  # API 방식 표시
        "index_dir": Path(__file__).resolve().parent / "index" / "upstage"
    },
    "bge-m3": {
        "model_name": "BAAI/bge-m3", 
        "index_dir": Path(__file__).resolve().parent / "index" / "bge-m3"
    }
}

# ===== 전역 캐시 =====
_MODELS: Dict[str, SentenceTransformer] = {}
_INDEXES: Dict[str, faiss.Index] = {}
_ID_LISTS: Dict[str, List[str]] = {}
_META_MAPS: Dict[str, Dict[str, Dict]] = {}
_UPSTAGE_CLIENT = None

# ===== 모델 로딩 =====
def _get_model(model_key: str):
    if model_key == "upstage":
        return _get_upstage_client()
    
    if model_key not in _MODELS:
        _MODELS[model_key] = SentenceTransformer(MODEL_INDEX_MAP[model_key]["model_name"])
    return _MODELS[model_key]

def _get_upstage_client():
    global _UPSTAGE_CLIENT
    if _UPSTAGE_CLIENT is None:
        load_dotenv()
        api_key = os.getenv("UPSTAGE_API_KEY")
        if not api_key:
            raise ValueError("UPSTAGE_API_KEY가 환경변수에 설정되지 않았습니다.")
        
        _UPSTAGE_CLIENT = OpenAI(
            api_key=api_key,
            base_url="https://api.upstage.ai/v1"
        )
    return _UPSTAGE_CLIENT

# ===== 인덱스 및 메타 로딩 =====
def _get_index_and_meta(model_key: str):
    if model_key not in _INDEXES:
        index_dir = MODEL_INDEX_MAP[model_key]["index_dir"]
        _INDEXES[model_key] = faiss.read_index(str(index_dir / "content.index"))
        _ID_LISTS[model_key] = json.load(open(index_dir / "content_ids.json", "r", encoding="utf-8"))
        metas = json.load(open(index_dir / "content_meta.json", "r", encoding="utf-8"))
        _META_MAPS[model_key] = {m["card_id"]: m for m in metas}
    return _INDEXES[model_key], _ID_LISTS[model_key], _META_MAPS[model_key]

# ===== 벡터 검색 =====
def vector_candidates(user_context_text: str, k: int = 5, model_key: str = "ko-sroberta") -> List[Dict[str, Any]]:
    """
    입력 텍스트를 임베딩해 FAISS TopK 반환
    model_key: "ko-sroberta", "sentence", "upstage", "bge-m3"
    """
    model = _get_model(model_key)
    index, id_list, meta_map = _get_index_and_meta(model_key)

    # 입력 텍스트 임베딩
    if model_key == "upstage":
        # Upstage API 사용
        try:
            response = model.embeddings.create(
                input=user_context_text,
                model="embedding-query"  # 쿼리용 모델
            )
            q = np.array([response.data[0].embedding], dtype="float32")
        except Exception as e:
            print(f"Upstage API 임베딩 실패: {e}")
            return []
    else:
        # sentence-transformers 사용
        q = model.encode([user_context_text], normalize_embeddings=True)
        q = np.asarray(q, dtype="float32")

    # FAISS 검색
    D, I = index.search(q, k)

    results: List[Dict[str, Any]] = []
    for idx, score in zip(I[0], D[0]):
        card_id = id_list[idx]
        meta = meta_map.get(card_id, {})
        results.append({
            "card_id": card_id,
            "score": float(score),
            "title": meta.get("title", ""),
            "tags": meta.get("tags", []),
            "content": meta.get("content", ""),
            "embedding_model": model_key  # 사용된 임베딩 모델 추가
        })
    return results