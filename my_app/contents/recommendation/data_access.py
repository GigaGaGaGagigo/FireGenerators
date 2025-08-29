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
    """Supabase에서 콘텐츠 데이터를 가져와서 반환"""
    try:
        from dotenv import load_dotenv
        from supabase import create_client
        import os
        
        # .env 파일 로드
        env_path = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(env_path)
        
        # Supabase 연결
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        
        if not url or not key:
            # 환경변수가 없으면 폴백용 더미 데이터
            return [
                {"card_id": "dummy_1", "title": "투자 기초", "content": "투자의 기본 개념", 
                 "level": "Beginner", "tags": ["투자", "기초"], "topic_id": "investment"},
                {"card_id": "dummy_2", "title": "주식 분석", "content": "주식 분석 방법", 
                 "level": "Intermediate", "tags": ["주식", "분석"], "topic_id": "stock"}
            ]
        
        client = create_client(url, key)
        
        # contents 테이블에서 모든 데이터 가져오기
        result = client.table('contents').select('*').execute()
        
        if not result.data:
            # DB에 데이터가 없으면 폴백용 더미 데이터
            return [
                {"card_id": "dummy_1", "title": "투자 기초", "content": "투자의 기본 개념", 
                 "level": "Beginner", "tags": ["투자", "기초"], "topic_id": "investment"},
                {"card_id": "dummy_2", "title": "주식 분석", "content": "주식 분석 방법", 
                 "level": "Intermediate", "tags": ["주식", "분석"], "topic_id": "stock"}
            ]
        
        # DB 데이터를 정규화하여 반환
        all_data = []
        for raw_item in result.data:
            normalized_item = _normalize_content(raw_item)
            all_data.append(normalized_item)
            
        return all_data
        
    except Exception as e:
        print(f"DB 연결 오류, 폴백 데이터 사용: {e}")
        # 오류 발생시 폴백용 더미 데이터
        return [
            {"card_id": "fallback_1", "title": "투자 기초", "content": "투자의 기본 개념을 알아보세요", 
             "level": "Beginner", "tags": ["투자", "기초", "경제"], "topic_id": "investment"},
            {"card_id": "fallback_2", "title": "주식 분석", "content": "주식 분석 방법을 배워보세요", 
             "level": "Intermediate", "tags": ["주식", "분석", "금융"], "topic_id": "stock"},
            {"card_id": "fallback_3", "title": "부동산 투자", "content": "부동산 투자 전략 가이드", 
             "level": "Advanced", "tags": ["부동산", "투자", "자산"], "topic_id": "realestate"}
        ]

def make_content_text(content: Dict) -> str:
    tags_txt = " ".join(content.get("tags") or [])
    return f"{content['title']} [태그:{tags_txt}] {content['content']}"

def id_index_maps(contents: List[Dict]) -> Tuple[Dict[str, int], Dict[int, str]]:
    id2idx, idx2id = {}, {}
    for i, c in enumerate(contents):
        id2idx[c["content_id"]] = i
        idx2id[i] = c["content_id"]
    return id2idx, idx2id