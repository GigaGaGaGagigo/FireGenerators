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
client = OpenAI(api_key=OPENAI_API_KEY)

# 모델 이름 상수 정의
MODEL_QGEN   = "gpt-4.1"         # 문제 생성 전용
MODEL_EVAL   = "gpt-4o-mini"   # 채점 전용
MODEL_SUMMARY = "gpt-4.1"  # 요약 전용

if not OPENAI_API_KEY:
    st.error("OPENAI_API_KEY가 설정되지 않았습니다. .env에 OPENAI_API_KEY를 넣어주세요.")
    raise SystemExit("Missing OPENAI_API_KEY")


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

def chat_json(system_prompt: str, user_prompt: str, json_schema: dict | None = None, model: str = "gpt-4o-mini"):
    """
    Chat Completions로 JSON 결과 받기.
    - response_format(json_schema) 먼저 시도 -> 안 되면 평문 JSON 강제 프롬프트
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    def _call_with_schema():
        kwargs = {"model": model, "messages": messages}
        if json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "structured_output", "schema": json_schema, "strict": True}
            }
        return client.chat.completions.create(**kwargs)

    try:
        resp = _with_retry(_call_with_schema)
        raw = (resp.choices[0].message.content or "").strip()
        return _safe_json_loads(_extract_json(raw), None)
    except Exception:
        pass

    def _call_plain():
        msgs = [
            {"role": "system", "content": system_prompt + "\n반드시 JSON만 출력하세요."},
            {"role": "user", "content": user_prompt + "\nJSON 외 텍스트/마크다운/설명 금지."},
        ]
        return client.chat.completions.create(model=model, messages=msgs)

    resp = _with_retry(_call_plain)
    raw = (resp.choices[0].message.content or "").strip()
    return _safe_json_loads(_extract_json(raw), None)


# 현재 상태를 모두 반영하는 롤링 요약 갱신
def update_rolling_summary(
    prev_summary: str,
    new_turns: list[dict],
    *,
    proficiency: int,
    score: int,
    total_weight: int,
    level_hint: str | None = None,           # 예: "Beginner"/"Intermediate"/"Advanced"
    keywords: list[str] | None = None,       # 사용자 관심사
    topic_hint: dict | None = None,          # {topic: {"total": n, "correct": m}} 같은 집계(있으면 좋고 없어도 됨)
    max_chars: int = 300
) -> str:
    """
    금융 퀴즈 세션 히스토리를 누적 요약(≤300자)한다.
    - 입력 신호(정답/오답, 숙련도, 점수/가중치, 레벨 힌트, 관심사, 토픽 집계)를 모두 전달해
      LLM이 요약에 반영하도록 한다.
    - 출력은 항상 1~3문장, 최대 max_chars자로 압축.
    """
    if not new_turns:
        return (prev_summary or "")[:max_chars]

    # 새 턴(보통 마지막 1문항)을 간결 문자열로 정리
    # new_turn = {"q": "...", "ua":"...", "ans":"...", "ok":True/False, "w":1/2}
    new_text = "; ".join([
        f"Q: {t.get('q','')[:120]} / 내답: {t.get('ua','')} / 정답: {t.get('ans','')} / "
        f"{'정답' if t.get('ok') else '오답'} / 가중치:{t.get('w',1)}"
        for t in new_turns
    ])

    # 참고 힌트 구성 (있을 때만 짧게)
    level_str = f"{level_hint}" if level_hint else "(미정)"
    kw_str = ", ".join(keywords) if keywords else "(없음)"
    # topic_hint를 간단 요약으로(너무 길면 요약 품질↓, 그래서 2~3개만)
    topic_brief = ""
    if isinstance(topic_hint, dict) and topic_hint:
        # 정확도 높은 순으로 상위 2~3개 요약
        rows = []
        for t, s in topic_hint.items():
            tot, cor = int(s.get("total", 0)), int(s.get("correct", 0))
            acc = (cor / tot) if tot else 0.0
            rows.append((t, tot, cor, acc))
        rows.sort(key=lambda x: (x[3], x[1]), reverse=True)
        top = rows[:3]
        topic_brief = "; ".join([f"{t}: {int(a*100)}%({c}/{tot})" for t, tot, c, a in top])

    system_prompt = (
        "너는 금융 퀴즈 세션의 롤링 요약을 갱신하는 코치다. "
        "출력은 1~3문장, 최대 글자수 제한 내에서 한국어 자연문으로 압축한다. "
        "핵심 개념/오개념, 강·약점, 다음 문항에 도움이 되는 힌트를 우선한다. "
        "숫자 나열은 최소한으로 하되, 필요한 핵심 수치(정답/오답 경향, 숙련도 추이 등)는 간단히 포함해라."
    )

    user_prompt = (
        f"[이전요약]\n{(prev_summary or '(없음)')}\n\n"
        f"[새 문항]\n{new_text}\n\n"
        f"[현재 상태]\n"
        f"- 숙련도(proficiency): {proficiency}/10\n"
        f"- 누적 점수: {score}/{max_score if (max_score:=total_weight) else 1}\n"
        f"- 레벨 힌트: {level_str}\n"
        f"- 관심사: {kw_str}\n"
        f"- 토픽 집계 요약: {topic_brief or '(없음)'}\n\n"
        f"요구사항:\n"
        f"- 위 정보를 반영해 전체 요약을 갱신해라.\n"
        f"- 반드시 1~3문장, {max_chars}자 이내 한국어로 출력.\n"
        f"- 정답/오답 이유나 개념 혼선 포인트, 다음 문항을 위한 간단한 코칭 팁을 포함.\n"
        f"- 출력은 요약 문장만(메타/마크다운 금지)."
    )

    out = chat_json(system_prompt, user_prompt, json_schema=None)
    # chat_json이 문자열/딕셔너리 등으로 올 수 있으니 방어
    if isinstance(out, dict):
        # 혹시라도 dict로 올 때 'summary' 키를 쓰는 모델이라면
        candidate = out.get("summary") or out.get("text") or str(out)
        return str(candidate)[:max_chars]
    if isinstance(out, str):
        return out.strip()[:max_chars]

    # LLM 실패 시 간단 룰베이스 폴백
    base = prev_summary or ""
    hint = f"(숙련도 {proficiency}/10, 점수 {score}/{total_weight})"
    merged = (base + " " + new_text + " " + hint).strip()
    return merged[:max_chars]
