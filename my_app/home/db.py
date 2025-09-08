import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import streamlit as st

def _load_dotenv_once():
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / ".env",  # my_app/.env
        here.parents[2] / ".env",  # project/.env
        here.parent / ".env",      # my_app/home/.env
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=True)
            return
    load_dotenv(override=True)

_load_dotenv_once()

@st.cache_resource(show_spinner=False)
def _create_supabase_client(url: str, key: str):
    from supabase import create_client
    return create_client(url, key)

def get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        return _create_supabase_client(url, key)
    except Exception as e:
        print("Supabase 연결 실패:", e)
        return None

def _get_user_id(user) -> Optional[str]:
    if not user:
        return None
    if isinstance(user, dict):
        return user.get("user_id") or user.get("id")
    return getattr(user, "user_id", None) or getattr(user, "id", None)

def fetch_profile_by_user_id(user_id: str) -> Optional[Dict[str, Any]]:
    sb = get_supabase_client()
    if not sb or not user_id:
        return None
    try:
        res = (
            sb.table("profiles")
              .select("id,email,name,role,knowledge_level,investment_level,risk_tolerance,"
                      "interests_categories,investment_emotions,investment_goal,"
                      "user_summary,knowledge_summary,updated_at")
              .eq("id", user_id)
              .single()
              .execute()
        )
        return getattr(res, "data", None) or (res.get("data") if isinstance(res, dict) else None)
    except Exception as e:
        print("profiles 조회 실패:", e)
        return None

def fetch_trades_by_user_id(user_id: str) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    if not sb or not user_id:
        return []
    try:
        res = (
            sb.table("trade_history")
              .select("symbol,market,action,price,qty,commission,trade_time")
              .eq("user_id", user_id)
              .order("trade_time", desc=False)
              .execute()
        )
        return (res.data or []) if hasattr(res, "data") else (res.get("data") or [])
    except Exception as e:
        print("trade_history 조회 실패:", e)
        return []

__all__ = [
    "get_supabase_client",
    "_get_user_id",
    "fetch_profile_by_user_id",
    "fetch_trades_by_user_id",
]
