# 벡터 검색 유틸 (모델/인덱스 로드 캐시)
from pathlib import Path
import json, faiss, numpy as np
from typing import Tuple, List, Dict
from sentence_transformers import SentenceTransformer

INDEX_DIR = Path(__file__).resolve().parent / "indexes"
INDEX_PATH = INDEX_DIR / "card.index"
CARD_IDS_PATH = INDEX_DIR / "card_ids.json"

MODEL_NAME = "jhgan/ko-sroberta-multitask"

_MODEL = None
_INDEX = None
_ID_LIST: List[str] = []

def _get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL

def _get_index_and_ids():
    global _INDEX, _ID_LIST
    if _INDEX is None:
        _INDEX = faiss.read_index(str(INDEX_PATH))
    if not _ID_LIST:
        _ID_LIST = json.load(CARD_IDS_PATH.open("r", encoding="utf-8"))
    return _INDEX, _ID_LIST

def vector_candidates(user_context_text: str, k: int = 10) -> Tuple[List[str], List[float]]:
    """
    입력 텍스트를 임베딩하여 FAISS TopK 반환.
    리턴: ([card_id...], [유사도...])
    """
    model = _get_model()
    index, id_list = _get_index_and_ids()

    q = model.encode([user_context_text], normalize_embeddings=True)
    D, I = index.search(np.asarray(q, dtype="float32"), k)
    ids = [id_list[i] for i in I[0]]
    scores = [float(d) for d in D[0]]
    return ids, scores