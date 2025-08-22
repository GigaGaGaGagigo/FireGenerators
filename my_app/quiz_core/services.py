import os, json, re, time, random
import streamlit as st
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, BadRequestError
from supabase import create_client
from pathlib import Path
from dotenv import load_dotenv

# 루트(.env) 경로를 명시적으로 로드
PROJECT_ROOT = Path(__file__).resolve().parents[2]  
load_dotenv(PROJECT_ROOT / ".env")

# ---- Supabase ----
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# ---- OpenAI ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("OPENAI_API_KEY가 설정되지 않았습니다. .env에 OPENAI_API_KEY를 넣어주세요.")
    raise SystemExit("Missing OPENAI_API_KEY")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
client = OpenAI(api_key=OPENAI_API_KEY)

# ---- 공용 유틸(JSON 추출/재시도) ----
_JSON_RE = re.compile(r"\{[\s\S]*\}|\[[\s\S]*\]")

def _extract_json(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^```json\s*|\s*```$", "", t, flags=re.IGNORECASE)
    m = _JSON_RE.search(t)
    return m.group(0) if m else ""

def _safe_json_loads(s: str, fallback=None):
    try:
        return json.loads(s)
    except Exception:
        return fallback

def _with_retry(fn, max_tries=4):
    for i in range(max_tries):
        try:
            return fn()
        except (RateLimitError, APIConnectionError, APIError):
            if i == max_tries - 1: raise
            time.sleep((2 ** i) + random.random() * 0.5)

def chat_json(system_prompt: str, user_prompt: str, json_schema: dict | None = None):
    """
    Chat Completions로 JSON 결과 받기.
    - response_format(json_schema) 먼저 시도 -> 400/구버전이면 평문 JSON 강제 프롬프트로 재시도
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    def _call_with_schema():
        kwargs = {"model": OPENAI_MODEL, "messages": messages}
        if json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "structured_output", "schema": json_schema, "strict": True}
            }
        return client.chat.completions.create(**kwargs)

    # 1) 스키마 시도
    try:
        resp = _with_retry(_call_with_schema)
        raw = (resp.choices[0].message.content or "").strip()
        return _safe_json_loads(_extract_json(raw), None)
    except (TypeError, BadRequestError, APIError):
        pass

    # 2) 평문 JSON 강제
    def _call_plain():
        msgs = [
            {"role": "system", "content": system_prompt + "\n반드시 순수 JSON만 출력하세요."},
            {"role": "user", "content": user_prompt + "\nJSON 외 텍스트/마크다운/설명 금지."},
        ]
        return client.chat.completions.create(model=OPENAI_MODEL, messages=msgs)

    resp = _with_retry(_call_plain)
    raw = (resp.choices[0].message.content or "").strip()
    return _safe_json_loads(_extract_json(raw), None)
