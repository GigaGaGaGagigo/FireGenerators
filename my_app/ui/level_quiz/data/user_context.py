import os
from typing import List
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

DEFAULT_KEYWORDS = ["기초", "저위험", "ETF", "예금", "채권"]

def _normalize_tags(raw) -> List[str]:
    """[' 주식 ', 'ETF', ''] -> ['주식','ETF']"""
    if raw is None:
        return []
    if isinstance(raw, list):
        tags = [str(x).strip() for x in raw]
    elif isinstance(raw, str):
        # 혹시 문자열로 직렬화되어 오는 경우(예: '["주식","ETF"]' or '주식')
        if raw.startswith("[") and raw.endswith("]"):
            try:
                import json
                tags = [str(x).strip() for x in json.loads(raw)]
            except Exception:
                tags = [raw.strip()]
        else:
            tags = [raw.strip()]
    else:
        tags = []
    # 중복/빈값 제거
    return [t for i, t in enumerate(tags) if t and t not in tags[:i]]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_user_keywords(user_id: str) -> List[str]:
    """
    profiles 테이블의 interests_categories(text[])를 조회해 키워드 리스트로 반환.
    - user_id: auth.users의 id(UUID) == profiles.id
    - 실패/없음: DEFAULT_KEYWORDS 반환
    """
    if not supabase or not user_id:
        return DEFAULT_KEYWORDS

    try:
        res = (
            supabase.table("profiles")
            .select("interests_categories")
            .eq("id", user_id)
            .single()            # 한 행만 기대
            .execute()
        )
        raw = (res.data or {}).get("interests_categories", [])
        tags = _normalize_tags(raw)
        return tags if tags else DEFAULT_KEYWORDS
    except Exception as e:
        # 필요하다면 st.warning(f"키워드 조회 실패: {e}")
        return DEFAULT_KEYWORDS