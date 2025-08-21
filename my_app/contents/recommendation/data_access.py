# 콘텐츠 로딩/정규화 (여러 json 합치기)
import glob
import os
from pathlib import Path
import json, hashlib
from typing import List, Dict, Tuple

BASE = Path(__file__).resolve().parents[1]  # my_app/
CONTENTS_DIR = BASE / "contents" / "contents"

def _stable_content_id(title: str, content: str) -> str:
    # 제목+내용 기반의 안정적인 해시 ID (DB id 없을 때 사용)
    h = hashlib.sha256((title + "||" + content).encode("utf-8")).hexdigest()[:16]
    return f"content_{h}"

def _normalize_content(raw: Dict) -> Dict:
    """
    입력 JSON 스키마가 다를 수 있으므로 유연하게 맞출 수 있도록 
    필요한 필드: card_id, title, content, level, tags(list), topic_id, style, media_type
    """
    title = raw.get("title") or raw.get("제목") or ""
    content_text = raw.get("content") or raw.get("본문") or raw.get("요약") or ""
    level = raw.get("level") or raw.get("난이도") or "Beginner"
    tags = raw.get("tags") or raw.get("키워드") or []
    topic_id = raw.get("topic_id") or raw.get("카테고리") or "unknown"
    style = raw.get("style") or "기본"
    media_type = raw.get("media_type") or "text"

    content_id = raw.get("id") or raw.get("card_id")
    if not content_id:
        content_id = _stable_content_id(title, content_text)

    # 태그를 문자열로 저장해둔 JSON도 있을 수 있어 안전 처리
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return {
        "card_id": content_id,
        "title": title,
        "content": content_text,
        "level": level,
        "tags": tags,
        "topic_id": topic_id,
        "style": style,
        "media_type": media_type,
    }

def load_all_cards(contents_dir: str = None):
    """여러 json 파일을 합쳐 리스트로 반환"""
    if contents_dir is None:
        # 기본값: 현재 디렉토리 ../contents
        base_dir = os.path.dirname(os.path.abspath(__file__))
        contents_dir = os.path.join(base_dir, "..", "contents")
    
    all_data = []
    for file_path in glob.glob(os.path.join(contents_dir, "contents_*.json")):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            all_data.extend(data)
    return all_data

def make_content_text(content: Dict) -> str:
    tags_txt = " ".join(content.get("tags") or [])
    return f"{content['title']} [태그:{tags_txt}] {content['content']}"

def id_index_maps(contents: List[Dict]) -> Tuple[Dict[str, int], Dict[int, str]]:
    id2idx, idx2id = {}, {}
    for i, c in enumerate(contents):
        id2idx[c["content_id"]] = i
        idx2id[i] = c["content_id"]
    return id2idx, idx2id