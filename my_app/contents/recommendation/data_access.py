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

def load_cards_from_json(contents_dir: str = None):
    """JSON 파일들에서 콘텐츠 데이터를 가져와서 반환"""
    if contents_dir is None:
        contents_dir = str(CONTENTS_DIR)
    
    try:
        all_data = []
        json_files = glob.glob(os.path.join(contents_dir, "contents_*.json"))
        
        if not json_files:
            print(f"경고: {contents_dir}에서 contents_*.json 파일을 찾을 수 없습니다")
            return []
        
        for json_path in json_files:
            print(f"로딩 중: {os.path.basename(json_path)}")
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                
                # 각 항목을 정규화하여 추가
                for raw_item in raw_data:
                    normalized_item = _normalize_content(raw_item)
                    all_data.append(normalized_item)
                    
            except Exception as e:
                print(f"파일 읽기 오류 {json_path}: {e}")
                continue
        
        print(f"✅ JSON에서 총 {len(all_data)}개 콘텐츠 로드됨")
        return all_data
        
    except Exception as e:
        print(f"JSON 파일 로딩 중 오류: {e}")
        return []

def load_all_cards(contents_dir: str = None, use_db: bool = True):
    """Supabase 또는 JSON 파일에서 콘텐츠 데이터를 가져와서 반환"""
    # JSON 파일에서 먼저 시도
    if not use_db:
        print("📁 JSON 파일에서 데이터 로드 시도...")
        return load_cards_from_json(contents_dir)
    
    # Supabase DB에서 시도
    try:
        from dotenv import load_dotenv
        from supabase import create_client
        import os
        
        print("🗄️ Supabase DB에서 데이터 로드 시도...")
        
        # .env 파일 로드
        env_path = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(env_path)
        
        # Supabase 연결
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        
        if not url or not key:
            print("⚠️ Supabase 환경변수 없음, JSON 파일로 폴백")
            return load_cards_from_json(contents_dir)
        
        client = create_client(url, key)
        
        # contents 테이블에서 모든 데이터 가져오기
        result = client.table('contents').select('*').execute()
        
        if not result.data:
            print("⚠️ Supabase DB 데이터 없음, JSON 파일로 폴백")
            return load_cards_from_json(contents_dir)
        
        # DB 데이터를 정규화하여 반환
        all_data = []
        for raw_item in result.data:
            normalized_item = _normalize_content(raw_item)
            all_data.append(normalized_item)
        
        print(f"✅ Supabase에서 총 {len(all_data)}개 콘텐츠 로드됨")
        return all_data
        
    except Exception as e:
        print(f"⚠️ Supabase 연결 오류, JSON 파일로 폴백: {e}")
        return load_cards_from_json(contents_dir)

def make_content_text(content: Dict) -> str:
    tags_txt = " ".join(content.get("tags") or [])
    return f"{content['title']} [태그:{tags_txt}] {content['content']}"

def id_index_maps(contents: List[Dict]) -> Tuple[Dict[str, int], Dict[int, str]]:
    id2idx, idx2id = {}, {}
    for i, c in enumerate(contents):
        # card_id 또는 content_id 사용
        content_id = c.get("card_id") or c.get("content_id")
        if content_id:
            id2idx[content_id] = i
            idx2id[i] = content_id
    return id2idx, idx2id