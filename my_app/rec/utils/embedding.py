import os
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
INDEX_PATH = os.path.join(DATA_DIR, 'faiss_index.idx')
DOCS_PATH = os.path.join(DATA_DIR, 'documents.jsonl')
EMBEDDINGS_PATH = os.path.join(DATA_DIR, 'embeddings.npy')
MODEL_NAME = 'all-MiniLM-L6-v2'

_model = None

def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model

def build_embeddings_and_index(documents):
    texts = [d['text'] for d in documents]
    model = _get_model()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
    np.save(EMBEDDINGS_PATH, embeddings)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings.astype('float32'))
    faiss.write_index(index, INDEX_PATH)

def load_documents_and_index():
    docs = []
    if os.path.exists(DOCS_PATH):
        with open(DOCS_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                docs.append(json.loads(line))
    else:
        return [], None
    if os.path.exists(INDEX_PATH):
        index = faiss.read_index(INDEX_PATH)
        embeddings = np.load(EMBEDDINGS_PATH)
        return docs, (index, embeddings)
    return docs, None

def retrieve_topk(query, docs, index_tuple, top_k=5):
    if index_tuple is None:
        return []
    index, _ = index_tuple
    model = _get_model()
    q_emb = model.encode([query]).astype('float32')
    D, I = index.search(q_emb, top_k)
    return [docs[i] for i in I[0] if i < len(docs)]
